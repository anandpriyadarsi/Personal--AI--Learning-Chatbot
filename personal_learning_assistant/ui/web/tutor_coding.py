"""Local-only Coding Studio JSON/form routes, using canonical Tutor ownership."""
from contextlib import contextmanager
from collections.abc import Mapping
from functools import wraps
import hmac
import sqlite3
from urllib.parse import urlsplit

from flask import Blueprint, current_app, request, jsonify, redirect, url_for, Response
from personal_learning_assistant.domain.coding_models import CodingError, fields, integer, text
from personal_learning_assistant.repositories.sqlite.tutor_repository import SQLiteTutorRepository, TutorRepositoryError
from personal_learning_assistant.services.academic_agent_web_service import _open_database, AcademicAgentWebUnavailableError
from personal_learning_assistant.services.tutor_coding_service import TutorCodingService

coding_blueprint = Blueprint('tutor_coding', __name__)


def protect_request():
    host = urlsplit(request.host_url).hostname
    if host not in {'localhost','127.0.0.1','::1'}:
        raise CodingError('local_host_required','Coding Studio is available on the local computer only.',403)
    if request.headers.get('Sec-Fetch-Site') == 'cross-site':
        raise CodingError('cross_site','Cross-site coding requests are blocked.',403)
    origin = request.headers.get('Origin')
    if origin and origin.rstrip('/') != request.host_url.rstrip('/'):
        raise CodingError('cross_origin','Use the local ANVAYA page for this action.',403)
    supplied = request.headers.get('X-CSRF-Token') if request.is_json else request.form.get('csrf_token','')
    expected = current_app.extensions.get('tutor_action_csrf','')
    if not supplied or not expected or not hmac.compare_digest(str(supplied),expected):
        raise CodingError('csrf','Tutor action token is invalid. Reload the page.',403)
    if request.content_length and request.content_length > 96*1024:
        raise CodingError('too_large','This coding request is too large.',413)
    # A disabled optional feature must still allow the explicit, protected exit
    # from a previously saved Coding workspace; never silently reroute a send.
    switch_data = (request.get_json(silent=True) or {}) if request.is_json else request.form
    academic_exit = (request.endpoint == 'tutor_coding.workspace'
                     and isinstance(switch_data, Mapping)
                     and switch_data.get('workspace') == 'academic')
    if current_app.config.get('TUTOR_CODING_ENABLED') is not True and not academic_exit:
        raise CodingError('feature_disabled','Coding Studio was explicitly disabled. Remove ANVAYA_TUTOR_CODING_ENABLED=false and restart ANVAYA.',503)



def endpoint(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        rid = ''
        try:
            protect_request()
            result = fn(*args,**kwargs)
            return result
        except CodingError as exc:
            # Identity only, never echo request fields or raw provider errors.
            if request.is_json:
                raw = request.get_json(silent=True)
                if isinstance(raw,dict) and isinstance(raw.get('request_id'),str) and len(raw['request_id'])<=80:
                    rid = raw['request_id']
            return jsonify(error={'code':exc.code,'message':str(exc),'retryable':exc.status in {429,503}}, request_id=rid), exc.status
        except TutorRepositoryError:
            return jsonify(error={'code':'session_conflict','message':'Conversation changed. Reopen and review before retrying.','retryable':False}),409
        except Exception:
            # Never log a provider exception/body or send traceback content to the student.
            return jsonify(error={'code':'unavailable','message':'Tutor or storage is unavailable. Your draft is retained. Review and retry.','retryable':True}),503
    return wrapped


@contextmanager
def service(sid, *, require_coding=True):
    from .routes import _academic_agent_service
    web = _academic_agent_service()
    connection = _open_database(web.database_path,writable=True)
    try:
        repository = SQLiteTutorRepository(connection)
        result = TutorCodingService(repository,web)
        if require_coding:
            result.coding.require(sid)
        yield result
    finally:
        connection.close()


def payload():
    if request.is_json:
        value = request.get_json(silent=True)
        if not isinstance(value,dict):
            raise CodingError('invalid_json','Send a JSON object.')
        return value
    value = request.form.to_dict()
    value.pop('csrf_token',None)
    for key in ('expected_task_revision','source_consent_revision','expected_consent_revision','hint_level'):
        if key in value:
            try:
                value[key] = int(value[key])
            except (ValueError,TypeError):
                raise CodingError('invalid_field','Choose a valid revision or hint level.')
    for key in ('full_solution','include_student_code'):
        if key in value:
            if value[key] not in {'true','false'}:
                raise CodingError('invalid_field','Choose a valid boolean option.')
            value[key] = value[key]=='true'
    return value


def respond(sid, value, status=200):
    if request.is_json:
        return jsonify(value),status
    return redirect(url_for('web.academic_agent_session',session_id=sid),code=303)


@coding_blueprint.post('/agent/sessions/<sid>/workspace')
@endpoint
def workspace(sid):
    data = payload()
    fields(data,{'workspace','selected_task_id'})
    with service(sid, require_coding=data.get('workspace') != 'academic' or 'selected_task_id' in data) as svc:
        state = svc.workspace(sid,data.get('workspace'),data.get('selected_task_id'))
    return respond(sid,state)


@coding_blueprint.post('/agent/sessions/<sid>/coding/sources/preview')
@endpoint
def preview(sid):
    data = payload()
    fields(data,{'topic','message'})
    with service(sid) as svc:
        return jsonify(svc.source_preview(sid,topic=text(data.get('topic',''),'topic',200),message=text(data.get('message',''),'message',2000)))


@coding_blueprint.post('/agent/sessions/<sid>/coding/consent')
@endpoint
def consent(sid):
    with service(sid) as svc:
        state = svc.consent(sid,payload())
    return respond(sid,state)


@coding_blueprint.post('/agent/sessions/<sid>/coding/tasks')
@endpoint
def create_task(sid):
    with service(sid) as svc:
        task, created = svc.create(sid,payload())
    return respond(sid,{'task':task},201 if created else 200)


@coding_blueprint.post('/agent/sessions/<sid>/coding/tasks/<tid>')
@endpoint
def edit_task(sid,tid):
    with service(sid) as svc:
        task = svc.edit(sid,tid,payload())
    return respond(sid,{'task':task})


@coding_blueprint.post('/agent/sessions/<sid>/coding/tasks/<tid>/archive')
@endpoint
def archive_task(sid,tid):
    data = payload()
    fields(data,{'expected_task_revision'})
    with service(sid) as svc:
        task = svc.coding.update(sid,tid,integer(data.get('expected_task_revision'),'task revision'),archive=True)
    return respond(sid,{'task':task})


@coding_blueprint.post('/agent/sessions/<sid>/coding/tasks/<tid>/ask')
@endpoint
def ask(sid,tid):
    with service(sid) as svc:
        result = svc.ask(sid,tid,payload())
    return respond(sid,dict(result,provenance='ai_feedback',execution='not_executed'))


@coding_blueprint.post('/agent/sessions/<sid>/coding/tasks/<tid>/notebook')
@endpoint
def notebook(sid,tid):
    from personal_learning_assistant.services.coding_notebooks import export_notebook
    data = payload()
    fields(data,{'expected_task_revision','template_id','include_student_code'})
    with service(sid) as svc:
        task = svc.coding.task(sid,tid)
        if task['revision'] != integer(data.get('expected_task_revision'),'task revision'):
            raise CodingError('stale_task','Review the updated task and retry.',409)
        session = svc.repository.get_session(sid)
        state = session.metadata.get('coding_workspace_v1') or {}
        svc._sources(session,[s['id'] for s in state.get('source_allowlist',[])])
        encoded = export_notebook(task,template_id=data.get('template_id',''),include_student_code=data.get('include_student_code',False))
    response = Response(encoded,mimetype='application/x-ipynb+json')
    response.headers.update({'Content-Disposition':f'attachment; filename="anvaya-practice-{task["id"][:8]}.ipynb"',
                             'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
    return response
