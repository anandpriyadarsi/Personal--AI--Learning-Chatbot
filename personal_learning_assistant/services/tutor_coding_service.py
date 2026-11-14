"""Tutor-owned coding use cases. Assessment runner state is never loaded."""
from contextlib import contextmanager
from threading import Lock
from pathlib import Path

from personal_learning_assistant.domain.coding_models import (CodingError, CodingRequest, WORKSPACE_KEY,
    canonical, digest, fields, integer, request_identity, text)
from personal_learning_assistant.repositories.sqlite.tutor_coding_repository import SQLiteTutorCodingRepository
from personal_learning_assistant.services.tutor_session_service import TutorSessionService, _utc_now
from personal_learning_assistant.tutor.source_freshness import source_snapshot, TutorSourceChangedError

_GATES = set()
_GUARD = Lock()


@contextmanager
def session_gate(database, sid):
    key = (str(Path(database).resolve()), sid)
    with _GUARD:
        if key in _GATES:
            raise CodingError('in_flight', 'A reply is already in progress. Reopen the conversation to reconcile it.', 429)
        _GATES.add(key)
    try:
        yield
    finally:
        with _GUARD:
            _GATES.discard(key)


class TutorCodingService:
    def __init__(self, repository, web_service):
        self.repository = repository
        self.coding = SQLiteTutorCodingRepository(repository)
        self.sessions = TutorSessionService(repository)
        self.web = web_service

    def workspace(self, sid, value, selected_task_id=None):
        if value not in {'academic','coding'}:
            raise CodingError('invalid_workspace', 'Choose Academic or Coding.')
        if value == 'coding' or selected_task_id is not None:
            self.coding.require(sid)
        with self.repository.atomic_exchange(sid):
            session = self.repository.get_session(sid)
            metadata = dict(session.metadata)
            state = dict(metadata.get(WORKSPACE_KEY) or {})
            if selected_task_id is not None:
                text(selected_task_id,'selected task',80,required=True)
                self.coding.task(sid,selected_task_id)
                state['selected_task_id'] = selected_task_id
            state.update(version=1,workspace=value)
            metadata[WORKSPACE_KEY] = state
            self.sessions.update_session_metadata(sid,metadata)
        return state

    def create(self, sid, payload):
        from personal_learning_assistant.services.coding_notebooks import TEMPLATES
        fields(payload, {'request_id','title','objective','language','template_id','code'})
        title = text(payload.get('title',''),'title',160,required=True).strip()
        language = payload.get('language','python')
        if language != 'python':
            raise CodingError('unsupported_language','Only Python notebook practice is enabled.')
        template = payload.get('template_id','')
        if not isinstance(template,str) or (template and template not in TEMPLATES):
            raise CodingError('invalid_template','Choose a practice template.')
        data = {'request_id':request_identity(payload.get('request_id')), 'title':title, 'language':language,
                'template_id':template, 'snapshot':{
                    'objective':text(payload.get('objective',''),'objective',2000),
                    'code':text(payload.get('code',''),'code',12000)}}
        if template:
            spec = TEMPLATES[template]
            data['snapshot']['public_spec'] = {key:spec[key] for key in ('objective','data','task')}
        canonical(data['snapshot'])
        with self.repository.atomic_exchange(sid):
            task, created = self.coding.create(sid,data,digest(data))
            session = self.repository.get_session(sid)
            metadata = dict(session.metadata)
            state = dict(metadata.get(WORKSPACE_KEY) or {})
            state.update(version=1,selected_task_id=task['id'])
            metadata[WORKSPACE_KEY] = state
            self.sessions.update_session_metadata(sid,metadata)
        return task, created

    def edit(self, sid, tid, payload):
        fields(payload, {'expected_task_revision','title','objective','code'})
        current = self.coding.task(sid,tid)
        snapshot = dict(current['snapshot'])
        for key, maximum in [('objective',2000),('code',12000)]:
            if key in payload:
                snapshot[key] = text(payload[key],key,maximum)
        title = text(payload.get('title',current['title']),'title',160,required=True).strip()
        return self.coding.update(sid,tid,integer(payload.get('expected_task_revision'),'task revision'),title=title,snapshot=snapshot)

    def _sources(self, session, ids=()):
        try:
            return source_snapshot(self.repository.connection,session,ids)
        except TutorSourceChangedError as exc:
            raise CodingError('stale_source',str(exc),409) from exc

    def consent(self, sid, payload):
        """Explicit review is bounded to the server-resolved candidate source set."""
        fields(payload, {'expected_consent_revision', 'review_token', 'topic', 'message'})
        integer(payload.get('expected_consent_revision'),'consent revision',0)
        session = self.repository.get_session(sid)
        preview = self.source_preview(sid,topic=text(payload.get('topic',''),'topic',200), message=text(payload.get('message',''),'message',2000))
        if payload.get('review_token') != preview['review_token']:
            raise CodingError('stale_source','Sources or provider changed. Review them again.',409)
        with self.repository.atomic_exchange(sid):
            metadata = dict(session.metadata)
            state = dict(metadata.get(WORKSPACE_KEY) or {})
            if state.get('consent_revision',0) != payload['expected_consent_revision']:
                raise CodingError('stale_consent','Review the current source selection.',409)
            state.update(version=1,consent_revision=state.get('consent_revision',0)+1,
                         consent_time=_utc_now(), source_allowlist=preview['sources'], provider_identity=preview['provider_identity'])
            metadata[WORKSPACE_KEY]=state
            self.sessions.update_session_metadata(sid,metadata)
        return state

    def provider_identity(self):
        provider = self.web._provider()
        return digest({'provider':type(provider).__name__, 'model':str(getattr(provider,'model','')),
                       'url':str(getattr(provider,'api_url',''))})

    def source_preview(self, sid, *, topic='', message=''):
        session = self.repository.get_session(sid)
        # Server-owned current scope; no filename/hash-based authority or client IDs.
        from personal_learning_assistant.tutor.grounding import TutorGroundingPlanner
        retrieval, store = self.web._retrieval()
        try:
            plan = TutorGroundingPlanner(retrieval,self.sessions).plan(session,(topic + ' ' + message).strip() or 'Python NumPy Pandas coding practice', transcript=(),top_k=3,max_chars=8000)
            sources = self._sources(session,[e.document_id for e in plan.evidence])
            # Configuration identity excludes credentials.
            identity = self.provider_identity()
            result = {'sources':sources, 'provider_identity':identity,'source_policy':session.source_policy}
            result['review_token'] = digest(result)
            return result
        finally:
            if store is not None:
                store.close()

    def ask(self, sid, tid, payload):
        data = CodingRequest.parse(payload).data
        # Digest includes revision/consent and all validated semantic fields.
        request_digest = digest(data)
        self.coding.require(sid)
        old = self.coding.receipt(sid,tid,data['request_id'],request_digest)
        if old:
            return old
        with session_gate(self.web.database_path,sid):
            with self.repository.atomic_exchange(sid):
                task = self.coding.task(sid,tid)
                if task['revision'] != data['expected_task_revision']:
                    raise CodingError('stale_task','Review the updated task and retry.',409)
                session = self.repository.get_session(sid)
                state = dict(session.metadata.get(WORKSPACE_KEY) or {})
                if state.get('workspace') != 'coding':
                    raise CodingError('workspace_required','Switch to Coding before sending coding context.',409)
                if data['source_consent_revision'] != state.get('consent_revision'):
                    raise CodingError('consent_required','Review sources and provider before sending.',409)
                preview = self.source_preview(sid)
                if preview['provider_identity'] != state.get('provider_identity'):
                    raise CodingError('consent_required','Provider changed. Review your consent.',409)
                allowed = state.get('source_allowlist',[])
                if self._sources(session,[s['id'] for s in allowed]) != allowed:
                    raise CodingError('stale_source','Sources changed. Review or reselect them.',409)
                def validate_sources(ids):
                    snapshot = self._sources(session,ids)
                    if any(s not in allowed for s in snapshot):
                        raise CodingError('consent_required','This request found a different source. Review selection before sending.',409)
                    return snapshot
                def persist(sources, user, assistant):
                    # First turn acquired the optimistic session write lock; task CAS
                    # is checked inside that same transaction as a durable backstop.
                    if self.provider_identity() != state.get('provider_identity'):
                        raise CodingError('consent_required','Provider changed during generation. Review your consent.',409)
                    current = self.coding.task(sid,tid)
                    if current['revision'] != task['revision']:
                        raise CodingError('stale_task','The task changed during generation. Review and retry.',409)
                    validate_sources([s['id'] for s in sources])
                    self.coding.append_context(tid,data,request_digest,sources,user,assistant)
                from personal_learning_assistant.services.grounded_tutor_service import GroundedTutorService
                retrieval, store = self.web._retrieval()
                provider = self.web._provider()
                if hasattr(provider,'timeout_seconds'):
                    provider.timeout_seconds = min(provider.timeout_seconds,45)
                try:
                    engine = GroundedTutorService(tutor_session_service=self.sessions,retrieval_service=retrieval,provider=provider)
                    history = {} if data['action']=='rebuild' else self.coding.history(tid,allow_solution=data['full_solution'])
                    return engine.answer_coding(sid,data,history=history,
                        task_context={'title':task['title'],'objective':task['snapshot']['objective'],
                                      'language':task['language'],'template_id':task['template_id'],
                                      'public_spec':task['snapshot'].get('public_spec',{})},
                        validate_sources=validate_sources,persist_context=persist)
                finally:
                    if store is not None:
                        store.close()
