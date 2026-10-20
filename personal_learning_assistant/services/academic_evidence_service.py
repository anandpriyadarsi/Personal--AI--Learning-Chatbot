"""Bounded source-qualified projections over existing owners. No writes/providers."""
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo
import copy
import hashlib
import json
import sqlite3

from personal_learning_assistant.domain.academic_evidence import AcademicEvidenceRecord as Record, AcademicEvidenceView as View, SourceReference as Ref
from personal_learning_assistant.learning_studio.read_snapshot import frozen_studio
from personal_learning_assistant.learning_studio.validation import PackageError, identity, integer, require, validate_mapping, validate_package
from personal_learning_assistant.repositories.sqlite.learning_library_repository import LearningLibraryRepository, LibraryUnavailableError
from personal_learning_assistant.repositories.sqlite.topic_intelligence_repository import SQLiteTopicIntelligenceRepository, TopicIdentityError, TopicSchemaError
from .academic_overview_service import AcademicOverviewService
from .academic_wal_snapshot import AcademicSnapshotUnavailable

MAX_EVENTS = 500

def _aware(value):
    if not isinstance(value,datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('An aware academic as_of is required.')
    return value.astimezone(timezone.utc)

def _stamp(raw, now, reasons):
    try:
        value = datetime.fromisoformat(raw.replace('Z','+00:00'))
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError()
        value = value.astimezone(timezone.utc)
    except (AttributeError,TypeError,ValueError,OverflowError):
        reasons.add('occurrence_invalid')
        return None
    if value > now:
        reasons.add('occurrence_after_as_of')
    return value.isoformat()

def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,
        separators=(',',':')).encode()).hexdigest()

def qualify_learning_events(package, events, *, as_of, mapping_status):
    """Validate captured owner events; duplicate identity is blocked, never doubled."""
    now = _aware(as_of)
    require(isinstance(events,(list,tuple)) and len(events)<=MAX_EVENTS,
            'Practice projection exceeds the bounded inventory.',413)
    require(all(isinstance(r,dict) for r in events),'Structured owner events required.')
    questions = {q['id']:q for q in package['questions']}
    counts = Counter(str(r.get('event_id','')) for r in events)
    mapping = package.get('mapping') or {}
    records, seen = [], set()
    for row in events:
        eid = row.get('event_id')
        identity(eid)
        if eid in seen:
            continue
        seen.add(eid)
        reasons = set()
        if counts[eid]!=1: reasons.add('duplicate_event')
        if row.get('module_id')!=package['module_id'] or row.get('revision')!=package['module_revision']:
            reasons.add('module_revision_mismatch')
        if row.get('source_hash')!=package['source']['sha256']:
            reasons.add('source_revision_mismatch')
        q = questions.get(row.get('question_id'))
        if q is None:
            reasons.add('question_identity_unavailable')
        elif type(row.get('question_revision')) is not int or row['question_revision']!=q['revision']:
            reasons.add('question_revision_mismatch')
        selection = row.get('selection')
        if q is not None and (type(selection) is not int or not 0<=selection<len(q['options']) or
                type(row.get('correct')) is not int or row['correct'] not in (0,1) or
                row['correct']!=int(selection==q['correct_index'])):
            reasons.add('practice_outcome_conflict')
        occurred = _stamp(row.get('timestamp'),now,reasons)
        refs = tuple(Ref('learning_source',package['source']['source_id'],
            package['source']['sha256'],package['module_revision'],page,
            None if reasons else '/academic-evidence/learning/'+quote(package['module_id'],safe='')+
            '/'+str(package['module_revision'])+'/source.pdf#page='+str(page))
            for page in (q['pages'] if q else ()))
        refs += (Ref('learning_event',eid),)
        if q:
            refs += (Ref('learning_question',q['id'],revision=q['revision'],url=None if reasons else
                '/learning/modules/'+quote(package['module_id'],safe='')+'/'+str(package['module_revision'])+
                '?view=practice&question='+quote(q['id'],safe='')+'#question-'+quote(q['id'],safe='')),)
        records.append(Record('learning_practice','learning_attempt:'+eid,
            mapping.get('course_id'),mapping.get('topic_id'),
            'blocked' if reasons else 'study_signal','published_snapshot_validated',
            mapping_status,'deterministic_practice',
            'unverified' if reasons else ('correct' if row['correct'] else 'incorrect'),
            occurred,refs,tuple(sorted(reasons)),package['module_revision'],
            q['revision'] if q else None,question_id=q['id'] if q else None))
    return tuple(records)

class AcademicEvidenceService:
    def __init__(self,database_path,*,studio=None,now=None,wal_snapshot_provider=None,
                 local_timezone='Asia/Kolkata'):
        self.path=Path(database_path).absolute()
        self.studio=studio
        self.now=now or (lambda:datetime.now(timezone.utc))
        self.wal_snapshot_provider=wal_snapshot_provider
        self.zone=ZoneInfo(local_timezone)

    @contextmanager
    def _connection(self):
        con=None
        try:
            guard=LearningLibraryRepository(self.path)
            guard._source_stamp(self.path)
            if self.wal_snapshot_provider is not None:
                reader=AcademicOverviewService(self.path,now=self.now,
                    wal_snapshot_provider=self.wal_snapshot_provider)
                con=reader._open_authorized_wal_snapshot({'limits':[]},_aware(self.now()))
            else:
                payload=guard._capture_delete_source(self.path)
                con=sqlite3.connect(':memory:',isolation_level=None)
                con.deserialize(payload)
                con.row_factory=sqlite3.Row
                con.execute('PRAGMA query_only=ON')
                con.execute('BEGIN')
            yield con
        except PackageError:
            raise
        except (sqlite3.Error,OSError,ValueError,LibraryUnavailableError,AcademicSnapshotUnavailable) as error:
            raise PackageError('Academic evidence unavailable; existing records were not changed.',503) from error
        finally:
            if con is not None:con.close()

    @staticmethod
    def _catalogue(con):
        courses=[dict(r) for r in con.execute('SELECT id,code,name FROM courses WHERE deleted_at IS NULL ORDER BY id LIMIT 101')]
        require(len(courses)<=100,'Course inventory exceeds the evidence bound.',503)
        topics=[dict(r) for r in con.execute('SELECT t.id,t.course_id,t.name FROM topics t JOIN courses c ON c.id=t.course_id WHERE t.deleted_at IS NULL AND c.deleted_at IS NULL ORDER BY t.id LIMIT 501')]
        require(len(topics)<=500,'Topic inventory exceeds the evidence bound.',503)
        for course in courses:
            course['topics']=[{'id':t['id'],'name':t['name']} for t in topics if t['course_id']==course['id']]
        return {'available':True,'courses':courses}

    def catalogue(self):
        try:
            with self._connection() as con:return self._catalogue(con)
        except PackageError:
            return {'available':False,'courses':[],'reason':'Academic snapshot unavailable.'}

    def _topic_records(self,con,course_id,topic_id,now):
        identity(course_id);identity(topic_id)
        count=con.execute('SELECT COUNT(*) FROM assessment_response_evaluations e JOIN assessment_test_session_questions q ON q.id=e.session_question_id WHERE q.topic_id=?',(topic_id,)).fetchone()[0]
        require(count<=MAX_EVENTS,'Assessment inventory exceeds the evidence bound.',503)
        # Reuse the existing owner parser on our RAM connection. Never call its
        # file-based closed-snapshot/immutable entry point on a live source.
        owner=SQLiteTopicIntelligenceRepository(self.path,closed_snapshot=True)
        try:
            topic,observations=owner._read(con,course_id,topic_id,now,self.zone)
        except TopicIdentityError as error:
            raise PackageError('Active exact course/topic pair unavailable.',404) from error
        except TopicSchemaError as error:
            raise PackageError('Historical academic evidence is unavailable.',503) from error
        records=[]
        for e in observations:
            reasons=set(e.exclusion_reasons)
            grading=con.execute("""SELECT ev.created_at,ev.updated_at,ev.confirmed_at,
                se.created_at,se.updated_at,se.confirmed_at FROM assessment_response_evaluations ev
                LEFT JOIN assessment_session_evaluations se ON se.id=ev.session_evaluation_id
                WHERE ev.id=?""",(e.evidence_id,)).fetchone()
            if grading is None:
                reasons.add('evaluation_timestamp_invalid')
            else:
                for index,raw in enumerate(grading):
                    # Confirmation is legitimately absent for provisional rows;
                    # mandatory creation/update clocks cannot be absent.
                    if raw is None and index in (2,5):continue
                    clock_reasons=set();_stamp(raw,now,clock_reasons)
                    if 'occurrence_after_as_of' in clock_reasons:reasons.add('evaluation_after_as_of')
                    if 'occurrence_invalid' in clock_reasons:reasons.add('evaluation_timestamp_invalid')
            blocked=bool(reasons-{'mapping_snapshot_unknown','independence_unknown','self_reported_outcome'})
            refs=tuple(Ref(r.kind,r.identifier,url=(
                '/assessments/sessions/'+quote(e.session_id,safe='')+'/evaluation'
                if r.kind=='session' and not blocked else None)) for r in e.source_refs)
            records.append(Record('assessment_evaluation','assessment_response_evaluation:'+e.evidence_id,
                e.course_id,e.topic_id,'blocked' if blocked else 'provisional',
                'historical_unverified','unverified',
                'self_report' if e.evaluator_type=='user' else e.evaluator_type,
                'unverified' if blocked else e.outcome,
                e.occurred_at_utc.isoformat() if e.occurred_at_utc else None,
                refs,tuple(sorted(reasons)),grading_confidence=e.grading_confidence))
        tasks=con.execute('SELECT id,status,completed_at,updated_at FROM planner_tasks WHERE course_id=? AND topic_id=? ORDER BY id LIMIT 101',(course_id,topic_id)).fetchall()
        require(len(tasks)<=100,'Task inventory exceeds the evidence bound.',503)
        for task in tasks:
            reasons=set()
            stamp=_stamp(task['completed_at'] or task['updated_at'],now,reasons)
            minutes=con.execute("""SELECT SUM(i.actual_minutes) FROM daily_agenda_items i
                JOIN daily_agendas a ON a.id=i.agenda_id WHERE i.source_type='planner_task'
                AND i.source_id=? AND i.status='completed' AND a.status IN ('approved','active','closed')
                AND a.agenda_date<=?""",(task['id'],now.astimezone(self.zone).date().isoformat())).fetchone()[0]
            records.append(Record('planner_task','planner_task:'+task['id'],course_id,topic_id,
                'blocked' if reasons else ('completion_signal' if task['status']=='completed' else 'planning_intent'),'canonical_task','canonical_links',
                'self_report',task['status'],stamp,
                (Ref('planner_task',task['id'],url=None if reasons else '/planning/tasks?status='+task['status']+'&course_id='+quote(course_id,safe='')),),
                tuple(sorted(reasons)),actual_minutes=minutes))
        return tuple(records)

    def topic(self,course_id,topic_id):
        now=_aware(self.now())
        with self._connection() as con:records=self._topic_records(con,course_id,topic_id,now)
        return View(now.isoformat(),_digest([asdict(r) for r in records]),course_id,topic_id,
            'historical_unverified','unverified',records,
            ('Historical mapping/source and independence remain unverified; current joins cannot backfill authority.',
             'Task completion is a self-reported study signal, not independent mastery.'))

    def frozen_learning(self,module_id,revision):
        identity(module_id);integer(revision,1,1_000_000)
        require(self.studio is not None,'Learning owner unavailable.',503)
        cat=self.catalogue()
        return frozen_studio(self.studio,catalogue=cat),cat

    def learning(self,module_id,revision):
        now=_aware(self.now())
        studio,cat=self.frozen_learning(module_id,revision)
        p=studio.module(module_id,revision,public=False)
        history=p.pop('history',[])
        raw=studio.source(module_id,revision)
        mapping=copy.deepcopy(p['mapping'])
        structural=copy.deepcopy(p);structural['mapping']=None
        with studio.store.connection() as con:
            assets={r['name']:r['bytes'] for r in con.execute('SELECT name,bytes FROM assets WHERE module_id=? AND revision=?',(module_id,revision))}
            events=[dict(r) for r in con.execute('SELECT event_id,module_id,revision,source_hash,question_id,question_revision,selection,correct,timestamp FROM attempts WHERE owner=? AND module_id=? AND revision=? ORDER BY seq LIMIT ?',
                ('local-owner',module_id,revision,MAX_EVENTS+1))]
        validate_package(structural,{'available':False,'courses':[]},raw,assets)
        mapping_status='unverified'
        if mapping and mapping.get('topic_id'):
            try:validate_mapping(mapping,cat);mapping_status='reviewed_current_catalogue'
            except PackageError:pass
        records=qualify_learning_events(p,events,as_of=now,mapping_status=mapping_status)
        course_id=(mapping or {}).get('course_id');topic_id=(mapping or {}).get('topic_id')
        academic=()
        if mapping_status=='reviewed_current_catalogue':
            try:
                with self._connection() as con:academic=self._topic_records(con,course_id,topic_id,now)
            except PackageError:
                # A disappearing/changeable second owner never grants authority.
                mapping_status='unverified'
        records=qualify_learning_events(p,events,as_of=now,mapping_status=mapping_status)
        historical=bool(history and max(history)!=revision)
        explanations=['Practice is low-stakes; assistance/independence are unknown. Repetition does not prove mastery.',
            'Source integrity validates the published snapshot, not live registry freshness or semantic correctness.',
            'Owners were read independently; no cross-database atomic snapshot is claimed.']
        if not events:explanations.append('No practice evidence is recorded; this is unknown, not a failed grade.')
        if mapping_status!='reviewed_current_catalogue':explanations.append('Mapping is unavailable, stale or unreviewed; a manual linked proposal is blocked.')
        if historical:explanations.append('Historical module revision; open the current revision before proposing new practice.')
        context={'module':p,'mapping_status':mapping_status,'catalogue':cat,'practice':[asdict(r) for r in records],
                 'assessment':[asdict(r) for r in academic if r.kind=='assessment_evaluation'],'historical':historical}
        return View(now.isoformat(),_digest(context),course_id,topic_id,'published_snapshot_validated',
            mapping_status,records+academic,tuple(explanations),module_id,revision,p['title'],historical,
            mapping_status=='reviewed_current_catalogue' and not historical,
            source_id=p['source']['source_id'],source_sha256=p['source']['sha256'])
