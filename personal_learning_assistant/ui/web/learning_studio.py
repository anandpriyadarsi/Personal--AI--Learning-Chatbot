"""Lazy, local-owner Learning Studio HTTP boundary."""
from __future__ import annotations
import hmac
import io
import os
from flask import Blueprint, current_app, jsonify, redirect, render_template, request, send_file, url_for
from werkzeug.exceptions import RequestEntityTooLarge

learning_blueprint = Blueprint('learning', __name__)
VIEWS = {'overview', 'learn', 'visualise', 'practice', 'revision', 'weak', 'source'}


def service():
    factory = current_app.config.get('LEARNING_STUDIO_SERVICE_FACTORY')
    if factory is not None: return factory()
    from personal_learning_assistant.learning_studio.service import LearningStudioService
    from personal_learning_assistant.learning_studio.sources import RegisteredSources, catalogue
    return LearningStudioService(
        current_app.config.get('LEARNING_STUDIO_DATABASE', os.environ.get('ANVAYA_LEARNING_STUDIO_DB', 'data/learning_studio.sqlite3')),
        source_loader=RegisteredSources(current_app.config.get('LEARNING_STUDIO_SOURCE_DATABASE', 'data/learning_assistant.db'),
                                        current_app.config.get('LEARNING_STUDIO_SOURCE_ROOTS', {})),
        catalogue_loader=current_app.config.get('LEARNING_STUDIO_CATALOGUE_LOADER', catalogue))


@learning_blueprint.before_request
def guard_writes():
    if request.method != 'POST': return None
    request.max_content_length = 25_000_000
    expected = current_app.extensions['learning_studio_csrf']
    actual = request.headers.get('X-Learning-CSRF') or request.form.get('csrf_token', '')
    origin = request.headers.get('Origin')
    if (not hmac.compare_digest(str(actual), expected) or
        (origin and origin.rstrip('/') != request.host_url.rstrip('/')) or
        request.headers.get('Sec-Fetch-Site') == 'cross-site'):
        return jsonify(error='Invalid local request token. Reload Learning Studio and retry.'), 403


@learning_blueprint.errorhandler(RequestEntityTooLarge)
def too_large(error):
    return jsonify(error='Learning Studio upload exceeds 25 MB.'), 413


def register_errors():
    from personal_learning_assistant.learning_studio.validation import PackageError
    @learning_blueprint.errorhandler(PackageError)
    def invalid(error):
        if request.is_json or request.path.endswith('/package'):
            return jsonify(error=str(error)), error.status
        return render_template('learning_error.html', active_page='learning', message=str(error)), error.status


register_errors()


@learning_blueprint.get('/learning')
def library():
    from personal_learning_assistant.learning_studio.course_views import subject_template
    view = service().library()
    templates = {c['id']: subject_template(c) for c in view['courses']}
    return render_template('learning_library.html', active_page='learning', library=view,
        course=None, profile=None, templates=templates, search='', topic='', section='',
        chemistry_sections=(), selected_chemistry_section=None)


@learning_blueprint.get('/learning/courses/<course_id>')
def course(course_id):
    from personal_learning_assistant.learning_studio.validation import PackageError
    from personal_learning_assistant.learning_studio.course_views import (
        CHEMISTRY_SECTIONS, chemistry_section, subject_template)
    try: offset = int(request.args.get('offset', '0'))
    except ValueError: raise PackageError('Invalid pagination offset.')
    search = request.args.get('q', '')
    topic = request.args.get('topic', '')
    section = request.args.get('section', '')
    view = service().library(course_id=course_id, search=search, topic=topic, section=section, offset=offset)
    selected = next((c for c in view['courses'] if c['id'] == course_id), None)
    if course_id == 'unmapped':
        selected = {'id': 'unmapped', 'code': 'Unmapped', 'name': 'Needs mapping review', 'topics': []}
    if course_id == 'unavailable':
        selected = {'id': 'unavailable', 'code': 'Course unavailable / needs review',
                    'name': 'Course unavailable / needs review', 'topics': []}
    if selected is None: raise PackageError('Course not registered.', 404)
    profile = subject_template(selected)
    return render_template('learning_library.html', active_page='learning', library=view,
        course=selected, profile=profile, templates={}, search=search, topic=topic, section=section,
        chemistry_sections=CHEMISTRY_SECTIONS if profile['chemistry'] else (),
        selected_chemistry_section=chemistry_section(section) if profile['chemistry'] else None)


def module_view(module_id, revision, *, staged=False):
    from personal_learning_assistant.learning_studio.validation import require
    from personal_learning_assistant.learning_studio.rendering import markdown, trusted_graph, trusted_activity
    from personal_learning_assistant.learning_studio.review_brief import format_review_brief
    view = request.args.get('view', 'overview')
    require(view in VIEWS, 'Unknown reader view.', 404)
    s = service()
    p = s.module(module_id, revision, staged=staged)
    from personal_learning_assistant.learning_studio.reader import select
    weak=[] if staged else s.weak(module_id,revision)
    reader=select(p,request.args,weak)
    if view=='revision' and not staged:
        reader=select(p,request.args,weak,engagement=s.engagement_state(module_id,revision,reader['selected_section']['id']))
    quality_questions={}
    if view=='practice' and not staged:
        from personal_learning_assistant.learning_studio.quality import quality_report
        quality_questions={q['question_id']:q for q in quality_report(s,module_id,revision,
            question_ids=[q['id'] for q in reader['practice_questions']])['questions']}
    source_element=None
    if request.args.get('element'):
        report=s.coverage_report(module_id,revision)
        source_element=next((e for e in (report or {}).get('inventory',[]) if e['id']==request.args['element'] and e['page']==reader['selected_page']['page']),None)
        require(source_element is not None,'Requested source element is unavailable on this page.',404)
    cat = s.catalogue_loader()
    mapping = p['mapping']
    mapping_current=False
    if mapping:
        from personal_learning_assistant.learning_studio.validation import PackageError, validate_mapping
        try:
            validate_mapping(mapping,cat)
            mapping_current=True
        except PackageError:
            pass  # Preserve the immutable historical mapping; never promote stale names.
    course = next((c for c in cat.get('courses', []) if mapping and c['id'] == mapping['course_id']), None)
    if mapping and course is None:
        course = {'id': 'unavailable', 'code': 'Course unavailable / needs review'}
    return render_template('learning_module.html', active_page='learning', module=p, view=view, staged=staged,
        course=course, mapping_current=mapping_current, markdown=markdown, trusted_graph=trusted_graph, trusted_activity=trusted_activity, **reader,
        practice_state={} if staged else s.practice_state(module_id,revision), source_element=source_element,quality_questions=quality_questions,
        pending_question=request.args.get('question') or (reader['practice_questions'][0]['id'] if view=='practice' and reader['practice_questions'] else None),
        reading_state=None if staged else s.reading_state(module_id,revision), weak=weak,
        csrf_token=current_app.extensions['learning_studio_csrf'],
        review_brief='' if staged or view!='weak' else format_review_brief(s.review_context(module_id,revision)))


@learning_blueprint.get('/learning/modules/<module_id>/<int:revision>')
def module(module_id, revision):
    return module_view(module_id, revision)


@learning_blueprint.get('/learning/staged/<module_id>/<int:revision>')
def preview(module_id, revision):
    return module_view(module_id, revision, staged=True)


@learning_blueprint.get('/learning/modules/<module_id>/<int:revision>/package')
def public_package(module_id, revision):
    return jsonify(service().module(module_id, revision))


@learning_blueprint.post('/learning/modules/<module_id>/<int:revision>/publish')
def publish(module_id, revision):
    service().publish(module_id, revision)
    return redirect(url_for('learning.module', module_id=module_id, revision=revision))


@learning_blueprint.post('/learning/modules/<module_id>/<int:revision>/attempts')
def attempt(module_id, revision):
    from personal_learning_assistant.learning_studio.validation import require
    request.max_content_length = 20000
    payload = request.get_json(silent=True)
    require(isinstance(payload, dict) and payload.get('module_revision') == revision, 'Route and attempt revisions disagree.', 409)
    s=service();result=s.attempt(module_id,payload);states=s.practice_state(module_id,revision)
    return jsonify(dict(result,practice_state=states[payload['question_id']],
                        practised_questions=sum(state['status']!='never_practised' for state in states.values()),total_questions=len(states)))


@learning_blueprint.route('/learning/import', methods=['GET', 'POST'])
def import_module():
    from personal_learning_assistant.learning_studio.validation import PackageError, require
    if request.method == 'GET':
        return render_template('learning_import.html', active_page='learning', csrf_token=current_app.extensions['learning_studio_csrf'])
    from personal_learning_assistant.learning_studio.archive import decode_bundle
    upload = request.files.get('package')
    require(upload is not None, 'Choose an authored learning package.')
    package, assets, coverage = decode_bundle(upload.read(25_000_001), upload.filename)
    try:
        result = service().stage(package, assets, coverage)
    except PackageError: raise
    except Exception as error:
        current_app.logger.warning('Learning source/import unavailable (%s).', type(error).__name__)
        raise PackageError('Registered source is unavailable. Configure existing source roots; academic data was not changed.', 503) from error
    return redirect(url_for('learning.preview', module_id=result['module_id'], revision=result['revision']))


@learning_blueprint.get('/learning/modules/<module_id>/<int:revision>/source.pdf')
def original(module_id, revision):
    s = service()
    staged = request.args.get('preview') == '1'
    raw = s.source(module_id, revision, staged=staged)
    p = s.module(module_id, revision, staged=staged)
    response = send_file(io.BytesIO(raw), mimetype='application/pdf', download_name=p['source']['filename'], as_attachment=True)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = 'sandbox'
    return response


@learning_blueprint.get('/learning/modules/<module_id>/<int:revision>/assets/<path:name>')
def asset(module_id, revision, name):
    from personal_learning_assistant.learning_studio.validation import require
    require(name.rsplit('.', 1)[-1] in {'png', 'jpg', 'jpeg', 'webp'}, 'Unsupported media type.', 404)
    raw = service().asset(module_id, revision, 'assets/' + name, staged=request.args.get('preview') == '1')
    mime = 'image/jpeg' if name.endswith(('.jpg', '.jpeg')) else 'image/' + name.rsplit('.', 1)[-1]
    response = send_file(io.BytesIO(raw), mimetype=mime)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@learning_blueprint.get('/learning/analysis')
def analysis():
    return render_template('learning_analysis.html', active_page='analysis', evidence=service().evidence())


@learning_blueprint.get('/learning/evidence')
def evidence():
    return jsonify(service().evidence())


@learning_blueprint.get('/learning/modules/<module_id>/<int:revision>/quality')
def learning_quality(module_id,revision):
    from personal_learning_assistant.learning_studio.quality import quality_report
    from personal_learning_assistant.learning_studio.validation import require

    allowed={'format','status','page','offset','limit'}
    require(not set(request.args)-allowed and all(len(request.args.getlist(key))==1 for key in request.args)
            and request.args.get('format','json') in {'json','html'},
            'Only bounded queue filters are allowed; evidence time and identity are server-owned.')

    def bounded_query_number(key, default, lower, upper):
        raw=request.args.get(key)
        if raw is None or raw=='':return default
        require(len(raw)<=7 and raw.isascii() and raw.isdecimal(),
                'Invalid revision queue pagination or source page.')
        number=int(raw)
        require(lower<=number<=upper,'Revision queue filter is out of range.')
        return number

    result=quality_report(service(),module_id,revision,
        status=request.args.get('status','all'),
        page=bounded_query_number('page',None,1,500),
        offset=bounded_query_number('offset',0,0,1000000),
        limit=bounded_query_number('limit',100,1,100))
    response=(render_template('learning_quality.html',active_page='learning',quality=result)
        if request.args.get('format')=='html' else jsonify(result))
    if isinstance(response,str):
        from flask import make_response
        response=make_response(response)
    response.headers['Cache-Control']='no-store'
    return response


@learning_blueprint.get('/learning/evidence/export')
def export():
    response = jsonify(service().export())
    response.headers['Content-Disposition'] = 'attachment; filename=learning-evidence.json'
    return response


@learning_blueprint.get('/learning/modules/<module_id>/<int:revision>/review-context')
def review_context(module_id, revision):
    return jsonify(service().review_context(module_id, revision))


@learning_blueprint.get('/learning/modules/<module_id>/<int:revision>/review-brief')
def review_brief(module_id, revision):
    from flask import Response
    from personal_learning_assistant.learning_studio.review_brief import format_review_brief
    response=Response(format_review_brief(service().review_context(module_id,revision)),mimetype='text/plain')
    response.headers['Content-Disposition']='attachment; filename=learning-review-brief.txt'
    return response


@learning_blueprint.route('/learning/modules/<module_id>/<int:revision>/progress', methods=['GET','POST'])
def progress(module_id, revision):
    if request.method == 'GET':
        return jsonify(service().reading_state(module_id,revision))
    request.max_content_length = 10000
    return jsonify(service().record_progress(module_id,revision,request.get_json(silent=True)))


@learning_blueprint.route('/learning/modules/<module_id>/<int:revision>/engagement',methods=['GET','POST'])
def engagement(module_id, revision):
    if request.method=='GET':return jsonify(service().engagement_state(module_id,revision,request.args.get('section','')))
    request.max_content_length = 10000
    return jsonify(service().record_engagement(module_id,revision,request.get_json(silent=True)))


@learning_blueprint.post('/learning/tutor-review')
def tutor_compatibility_review():
    from personal_learning_assistant.learning_studio.tutor_bridge import prepare_review
    request.max_content_length=10000
    return jsonify(prepare_review(service(),request.get_json(silent=True),explicit_action=True)),409


@learning_blueprint.get('/learning/modules/<module_id>/<int:revision>/coverage')
def coverage_review(module_id,revision):
    s=service();p=s.module(module_id,revision,staged=True);report=s.coverage_report(module_id,revision)
    from personal_learning_assistant.learning_studio.coverage_view import project_coverage
    projection=project_coverage(p,report,request.args,catalogue=s.catalogue_loader()) if report else None
    with s.store.connection() as con:
        next_revision=con.execute('SELECT max(revision)+1 FROM modules WHERE module_id=?',(module_id,)).fetchone()[0]
    return render_template('learning_coverage.html',active_page='learning',module=p,report=report,coverage_view=projection,staged=revision not in p['history'],
        next_revision=next_revision,csrf_token=current_app.extensions['learning_studio_csrf'])


@learning_blueprint.post('/learning/modules/<module_id>/<int:revision>/coverage/candidate')
def correction_candidate(module_id,revision):
    from personal_learning_assistant.learning_studio.validation import PackageError
    request.max_content_length=40000
    payload=request.get_json(silent=True) if request.is_json else request.form.to_dict()
    if not request.is_json:
        payload.pop('csrf_token',None);target=payload.pop('target','')
        try:
            section,index=target.rsplit(':',1)
            payload.update(section_id=section,block_index=int(index),target_revision=int(payload['target_revision']))
        except (ValueError,KeyError):raise PackageError('Select an authored teaching block and a new revision.')
    result=service().create_candidate(module_id,revision,payload)
    if request.is_json:return jsonify(result),201
    return redirect(url_for('learning.preview',module_id=module_id,revision=result['revision'],view='learn',section=payload['section_id']))


@learning_blueprint.route('/learning/modules/<module_id>/<int:revision>/mapping',methods=['GET','POST'])
def mapping_review(module_id,revision):
    s=service()
    if request.method=='POST':
        request.max_content_length=10000
        result=s.confirm_mapping(module_id,revision,request.get_json(silent=True))
        return jsonify(result)
    return render_template('learning_mapping.html',active_page='learning',review=s.mapping_candidates(module_id,revision),csrf_token=current_app.extensions['learning_studio_csrf'])
