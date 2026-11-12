"""Lazy, local-owner Learning Studio HTTP boundary."""
from __future__ import annotations
import hmac
import io
import os
import uuid
import sqlite3
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
    studio = service()
    view = studio.library()
    templates = {c['id']: subject_template(c) for c in view['courses']}
    return render_template('learning_library.html', active_page='learning', library=view,
        course=None, profile=None, templates=templates, search='', topic='', section='',
        resume=studio.resume_learning(),
        chemistry_sections=(), selected_chemistry_section=None)


@learning_blueprint.get('/learning/materials')
def materials():
    """Browse the Library's original files without creating Learning modules."""
    from personal_learning_assistant.learning_studio.validation import PackageError
    from personal_learning_assistant.services.learning_materials_view import browse_materials
    from personal_learning_assistant.services.native_document_library import LibraryError
    from .native_library import catalogue as native_catalogue
    from .native_library import service as native_library_service, view_document

    if (any(len(request.args.getlist(key)) > 1 for key in request.args)
            or set(request.args) - {'folder_id', 'subject_id', 'collection', 'page'}):
        raise PackageError('Choose valid material filters.', 400)
    folder_id = request.args.get('folder_id') or None
    subject_id = request.args.get('subject_id') or None
    collection = request.args.get('collection') or None
    try:
        number = int(request.args.get('page', '1'))
    except (TypeError, ValueError) as error:
        raise PackageError('Choose a valid material page.', 400) from error
    course = None
    if subject_id:
        course = next((c for c in native_catalogue().get('courses', [])
                       if c['id'] == subject_id), None)
        if course is None:
            raise PackageError('Course not registered.', 404)
    try:
        result = browse_materials(native_library_service(), folder_id=folder_id,
                                  subject_id=subject_id, collection=collection,
                                  page=number)
        result['documents'] = [view_document(doc) for doc in result['documents']]
    except ValueError as error:
        raise PackageError(str(error), 400) from error
    except LibraryError as error:
        return render_template('learning_error.html', active_page='learning',
                               message=str(error)), error.status
    registered_mit = None
    if collection == 'mit':
        # MIT lecture *resources* live in the canonical academic catalogue,
        # not necessarily in the original-file manager. Link both surfaces.
        from .routes import _learning_library_service
        from personal_learning_assistant.domain.learning_library_models import LibraryQuery
        from personal_learning_assistant.services.learning_library_service import LibraryUnavailableError
        try:
            registered_mit = _learning_library_service().list_items(
                LibraryQuery(collection='mit', item_kind='resource', page_size=30))
        except LibraryUnavailableError:
            pass  # The independent original-file collection remains available.
    return render_template('learning_materials.html', active_page='learning',
                           materials=result, course=course, registered_mit=registered_mit)


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
    studio = service()
    view = studio.library(course_id=course_id, search=search, topic=topic, section=section, offset=offset)
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
        resume=studio.resume_learning(course_id),
        chemistry_sections=CHEMISTRY_SECTIONS if profile['chemistry'] else (),
        selected_chemistry_section=chemistry_section(section) if profile['chemistry'] else None)


def module_view(module_id, revision, *, staged=False):
    from personal_learning_assistant.learning_studio.validation import require
    from personal_learning_assistant.learning_studio.rendering import markdown, inline_markdown, trusted_graph, trusted_activity
    from personal_learning_assistant.learning_studio.review_brief import format_review_brief
    view = request.args.get('view', 'overview')
    require(view in VIEWS, 'Unknown reader view.', 404)
    s = service()
    p = s.module(module_id, revision, staged=staged)
    attempt_feedback = None
    if request.args.get('attempt'):
        require(view == 'practice' and not staged and request.args.get('question'),
                'Recorded feedback requires an exact published practice question.', 404)
        attempt_feedback = s.attempt_feedback(module_id, revision, request.args['attempt'],
                                              question_id=request.args['question'])
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
    section_targets = {section['id']: url_for('learning.preview' if staged else 'learning.module',
        module_id=module_id,revision=revision,view='learn',section=section['id']) for section in p['sections']}
    def reader_markdown(text, anchor_prefix=None):
        return markdown(text,anchor_prefix,section_targets=section_targets)
    from personal_learning_assistant.learning_studio.assessment_bridge import feedback,reviewed_link,formal_states
    from .routes import _assessment_intelligence_service
    assessment_choices=assessment_topic_choices(s,p) if not staged else None
    selected_assessment_link=reviewed_link(s,module_id,revision) if not staged else None
    assessment_feedback=feedback(s,p,lambda course_id:_assessment_intelligence_service().course_report(course_id),assessment_mapping=selected_assessment_link) if not staged else None
    formal_assessments=[]
    if assessment_feedback and assessment_feedback['consented'] and assessment_choices:
        try:formal_assessments=formal_states(_assessment_intelligence_service().database_path,assessment_choices['course']['id'])
        except (AttributeError,ValueError,OSError,sqlite3.Error):pass
    return render_template('learning_module.html', active_page='learning', module=p, view=view, staged=staged,
        course=course, mapping_current=mapping_current, markdown=reader_markdown, inline_markdown=inline_markdown, trusted_graph=trusted_graph, trusted_activity=trusted_activity, **reader,
        practice_state={} if staged else s.practice_state(module_id,revision), source_element=source_element,quality_questions=quality_questions,
        attempt_feedback=attempt_feedback, attempt_event_ids={q['id']: str(uuid.uuid4()) for q in reader['practice_questions']},
        inline_event_id=str(uuid.uuid4()), completion_event_id=str(uuid.uuid4()),
        assessment_feedback=assessment_feedback,assessment_choices=assessment_choices,formal_assessments=formal_assessments,
        assessment_course_id=assessment_choices['course']['id'] if assessment_choices else (mapping or {}).get('course_id'),
        original_pages={page:{**source,'position':source['positions'][index]} for source in p.get('lecture_sources',[]) for index,page in enumerate(source['pages'])},
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
    native = not request.is_json
    if native:
        from personal_learning_assistant.learning_studio.reader import select
        fields = {'event_id', 'module_revision', 'source_sha256', 'question_id', 'question_revision', 'selection',
                  'csrf_token', 'section', 'mode'}
        require(not (set(request.form) - fields) and all(len(request.form.getlist(k)) == 1 for k in request.form),
                'Invalid practice form fields.')
        payload = {key: request.form.get(key, '') for key in
                   ('event_id', 'module_revision', 'source_sha256', 'question_id', 'question_revision', 'selection')}
        for key in ('module_revision', 'question_revision', 'selection'):
            value = payload[key]
            require(value.isascii() and value.isdigit() and len(value) <= 7, 'Invalid practice number.')
            payload[key] = int(value)
    else:
        payload = request.get_json(silent=True)
    require(isinstance(payload, dict) and payload.get('module_revision') == revision, 'Route and attempt revisions disagree.', 409)
    s = service()
    if native:
        # Validate the return location before recording an attempt; URL state owns no grading data.
        return_state = select(s.module(module_id, revision),
            {'section': request.form.get('section', ''), 'mode': request.form.get('mode', ''),
             'question': payload['question_id']}, s.weak(module_id, revision))
    result = s.attempt(module_id, payload)
    if native:
        return redirect(url_for('learning.module', module_id=module_id, revision=revision, view='practice',
            section=return_state['selected_section']['id'], mode=return_state['practice_mode'],
            question=payload['question_id'], attempt=result['event_id'], _anchor='question-' + payload['question_id']), code=303)
    states = s.practice_state(module_id, revision)
    return jsonify(dict(result,practice_state=states[payload['question_id']],
                        practised_questions=sum(state['status']!='never_practised' for state in states.values()),total_questions=len(states)))


@learning_blueprint.route('/learning/import', methods=['GET', 'POST'])
def import_module():
    from personal_learning_assistant.learning_studio.validation import PackageError, require
    if request.method == 'GET':
        return render_template('learning_import.html', active_page='learning', csrf_token=current_app.extensions['learning_studio_csrf'])
    from personal_learning_assistant.learning_studio.archive import decode_bundle, read_zip
    from personal_learning_assistant.learning_studio.portable_bundle import (
        is_self_contained_bundle, decode_self_contained_bundle,
    )
    upload = request.files.get('package')
    require(upload is not None, 'Choose an authored learning package.')
    raw = upload.read(25_000_001)
    filename = str(upload.filename or '')
    if filename.lower().endswith('.zip'):
        members = read_zip(raw, pilot=True)
        if is_self_contained_bundle(members):
            require(not current_app.config.get('ANDROID_LOCAL_RUNTIME'),
                    'Self-contained bundles are currently supported on the local website, not the Android app.', 422)
            from personal_learning_assistant.learning_studio.validation import validate_package
            from personal_learning_assistant.learning_studio.coverage import validate_coverage
            prepared = decode_self_contained_bundle(members)
            s = service()
            # Prevalidate EVERY module before committing ANY staged import.
            catalogue = s.catalogue_loader()
            for package, assets, coverage, source_bytes in prepared:
                valid = validate_package(package, catalogue, source_bytes, assets)
                if coverage is not None:
                    validate_coverage(coverage, valid, source_bytes, assets)
            try:
                staged = s.stage_many_portable(prepared)
                results = [dict(result, title=package['title'])
                           for result, (package, _, _, _) in zip(staged, prepared)]
            except PackageError:
                raise
            except Exception as error:
                current_app.logger.warning('Portable bundle staging failed (%s).', type(error).__name__)
                raise PackageError('Portable bundle could not be staged; existing publications were not modified.', 503) from error
            return render_template('learning_bundle_staged.html', active_page='learning',
                                   results=results, csrf_token=current_app.extensions['learning_studio_csrf'])
        if current_app.config.get('ANDROID_LOCAL_RUNTIME'):
            from personal_learning_assistant.learning_studio.portable_vedic_import import (
                bind_vedic_work_zip, is_vedic_authoring_archive,
            )
            if is_vedic_authoring_archive(members):
                package, assets, coverage = bind_vedic_work_zip(
                    raw, database=current_app.config['LEARNING_STUDIO_SOURCE_DATABASE'],
                    roots=current_app.config['LEARNING_STUDIO_SOURCE_ROOTS'],
                    requested_source_id=request.form.get('source_id', ''),
                )
            else:
                package, assets, coverage = decode_bundle(raw, filename)
        else:
            package, assets, coverage = decode_bundle(raw, filename)
    else:
        package, assets, coverage = decode_bundle(raw, filename)
    try:
        result = service().stage(package, assets, coverage)
    except PackageError:
        raise
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


@learning_blueprint.post('/learning/modules/<module_id>/<int:revision>/mapping/catalogue')
def register_mapping_course_topic(module_id, revision):
    """Explicit local-owner course/topic setup for Learning Studio mapping.

    Uses the existing routed course repository, not an independent duplicate
    course catalogue. Learning Studio's own CSRF guard applies to this POST.
    """
    from personal_learning_assistant.learning_studio.validation import PackageError, require
    from personal_learning_assistant.services.course_service import CourseService
    from personal_learning_assistant.repositories.routed_course_repository import RoutedCourseRepository
    from personal_learning_assistant.domain.course_models import AddTopicCommand, CreateCourseCommand
    import re

    studio = service()
    studio.module(module_id, revision, staged=True)
    require(studio.catalogue_loader().get('available'),
            'Course catalogue unavailable; restore the Courses data source before linking.', 503)
    require(not set(request.form) - {'csrf_token', 'action', 'code', 'name', 'semester', 'course_id', 'topic'},
            'Unexpected course setup field.')
    require(all(len(request.form.getlist(k)) <= 1 for k in request.form),
            'Repeated course setup fields are unsupported.')
    action = request.form.get('action', '')
    topic = request.form.get('topic', '').strip()
    require(0 < len(topic) <= 150, 'Enter a topic name (maximum 150 characters).')
    factory = current_app.config.get('LEARNING_STUDIO_COURSE_SERVICE_FACTORY')
    course_service = factory() if callable(factory) else CourseService(RoutedCourseRepository())
    try:
        if action == 'create':
            code = request.form.get('code', '').strip().upper()
            name = request.form.get('name', '').strip()
            semester = request.form.get('semester', '').strip()
            require(bool(re.fullmatch(r'[A-Z0-9_-]{2,20}', code)),
                    'Use a valid course code of 2–20 letters/digits.')
            require(0 < len(name) <= 150 and len(semester) <= 80,
                    'Enter a course name of up to 150 characters.')
            course_service.create_course(CreateCourseCommand(
                code=code, name=name, semester=semester, topics=({'name': topic},)))
        elif action == 'add_topic':
            course_id = request.form.get('course_id', '').strip()
            available = {c['id'] for c in studio.catalogue_loader().get('courses', [])}
            require(course_id in available, 'Select an existing registered course.')
            course_service.add_topic(AddTopicCommand(
                course_identifier=course_id, topic_name=topic))
        else:
            raise PackageError('Choose create course or add topic.', 422)
    except ValueError as error:
        if isinstance(error, PackageError):
            raise
        raise PackageError(str(error), 422) from error
    return redirect(url_for('learning.mapping_review', module_id=module_id, revision=revision), code=303)


@learning_blueprint.route('/learning/modules/<module_id>/<int:revision>/mapping',methods=['GET','POST'])
def mapping_review(module_id,revision):
    s=service()
    if request.method=='POST':
        request.max_content_length=10000
        result=s.confirm_mapping(module_id,revision,request.get_json(silent=True))
        return jsonify(result)
    return render_template('learning_mapping.html',active_page='learning',review=s.mapping_candidates(module_id,revision),csrf_token=current_app.extensions['learning_studio_csrf'])

# Multi-lecture authoring extends the existing immutable Studio engine.
@learning_blueprint.route('/learning/author',methods=['GET','POST'])
def author():
    from .native_library import service as original_library
    from personal_learning_assistant.learning_studio.multilecture_authoring import prepare
    from personal_learning_assistant.learning_studio.validation import require
    studio=service();lib=original_library()
    if request.method=='POST':
        ordered=request.form.get('order','').strip()
        identities=[s.strip() for s in ordered.split(',') if s.strip()] if ordered else request.form.getlist('documents')
        token=prepare(studio,lib,identities,title=request.form.get('title',''),
            course_id=request.form.get('course_id',''),topic_id=request.form.get('topic_id',''))
        return redirect(url_for('learning.author_draft',token=token),code=303)
    query=request.args.get('q','').strip()
    from personal_learning_assistant.learning_studio.validation import require
    require(len(query)<=200,'Search is limited to 200 characters.')
    offset=int(request.args.get('offset',0));require(0<=offset<=100000,'Invalid file page.')
    with lib.connection() as con:
        selected_documents=[lib._doc(row) for row in con.execute("SELECT * FROM documents WHERE trashed_at IS NULL AND instr(library_normalize(display_name),library_normalize(?))>0 ORDER BY created_at DESC,id LIMIT 100 OFFSET ?",(query,offset))]
    selected_id=request.args.get('selected','');selected_course=None
    if selected_id:
        from personal_learning_assistant.services.native_document_library import LibraryError
        try:selected_document=lib.get(selected_id)
        except LibraryError:
            from personal_learning_assistant.learning_studio.validation import PackageError
            raise PackageError('Selected original is unavailable.',404)
        require(not selected_document['trashed_at'],'Restore this original from Trash before authoring.',409)
        selected_course=selected_document['subject_id']
        if all(d['id']!=selected_id for d in selected_documents):selected_documents.insert(0,selected_document)
    return render_template('learning_author.html',active_page='learning',
        documents=selected_documents,catalogue=studio.catalogue_loader(),query=query,offset=offset,selected_id=selected_id,selected_course=selected_course,
        csrf_token=current_app.extensions['learning_studio_csrf'])


@learning_blueprint.route('/learning/author/<token>',methods=['GET','POST'])
def author_draft(token):
    import json
    from personal_learning_assistant.learning_studio.multilecture_authoring import draft,stage_draft,RUBRIC,quality,edit_form
    from personal_learning_assistant.learning_studio.archive import decode_json
    studio=service();package,assets,raw=draft(studio,token)
    if request.method=='POST':
        edited=(decode_json(request.form.get('package','').encode()) if request.form.get('advanced_json')=='true' else edit_form(package,request.form))
        result=stage_draft(studio,token,edited,request.form.getlist('review'))
        return redirect(url_for('learning.preview',module_id=result['module_id'],revision=result['revision']),code=303)
    from urllib.parse import urlsplit
    provider=author_provider()
    provider_label=(urlsplit(getattr(provider,'api_url','')).hostname or type(provider).__name__)+' · '+str(getattr(provider,'model','configured model'))
    return render_template('learning_author_draft.html',active_page='learning',package=package,
        section_questions={section['id']:next((q for q in package['questions'] if set(q['pages'])&set(section['pages'])),None) for section in package['sections']},
        encoded=json.dumps(package,ensure_ascii=False,indent=2),rubric=RUBRIC,issues=quality(package),token=token,provider_label=provider_label,provider_binding=author_provider_binding(provider),provider_configured=bool(getattr(provider,'configured',False)),
        csrf_token=current_app.extensions['learning_studio_csrf'])


@learning_blueprint.get('/learning/modules/<module_id>/<int:revision>/lectures/<int:order>/original')
def lecture_original(module_id,revision,order):
    import hashlib
    from personal_learning_assistant.learning_studio.validation import require
    from personal_learning_assistant.services.native_document_formats import MIMES
    studio=service();staged=request.args.get('preview')=='1'
    p=studio.module(module_id,revision,staged=staged)
    source=next((s for s in p.get('lecture_sources',[]) if s['order']==order),None)
    require(source is not None,'Lecture not found.',404)
    raw=studio.asset(module_id,revision,source['asset'],staged=staged)
    require(hashlib.sha256(raw).hexdigest()==source['sha256'],'Lecture original integrity failure.',409)
    response=send_file(io.BytesIO(raw),mimetype=MIMES[source['kind']],as_attachment=source['kind']!='pdf',download_name=source['filename'])
    response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':'sandbox'})
    return response


@learning_blueprint.get('/learning/modules/<module_id>/<int:revision>/bundle.zip')
def lecture_bundle(module_id,revision):
    from personal_learning_assistant.learning_studio.multilecture_authoring import export_bundle
    return send_file(io.BytesIO(export_bundle(service(),module_id,revision)),mimetype='application/zip',as_attachment=True,download_name='ANVAYA-topic.zip')


@learning_blueprint.post('/learning/modules/<module_id>/<int:revision>/completion')
def completion(module_id,revision):
    from personal_learning_assistant.learning_studio.validation import require
    studio=service();section=request.form.get('section','')
    completed=request.form.get('completed')
    require(completed in ('true','false'),'Choose completed or incomplete.')
    studio.record_progress(module_id,revision,{'event_id':request.form.get('event_id',''),'section_id':section,'view':'learn','completed':completed=='true'})
    p=studio.module(module_id,revision)
    ids=[s['id'] for s in p['sections']];i=ids.index(section)
    # A failed write raises before constructing any navigation to another lesson.
    target=ids[i+1] if completed=='true' and i+1<len(ids) else section
    return redirect(url_for('learning.module',module_id=module_id,revision=revision,view='learn',section=target),code=303)


@learning_blueprint.post('/learning/modules/<module_id>/<int:revision>/assessment-consent')
def assessment_consent(module_id,revision):
    from personal_learning_assistant.learning_studio.validation import require
    consent=request.form.get('consent')
    require(consent in ('true','false'),'Choose whether to show assessment feedback.')
    studio=service();p=studio.module(module_id,revision)
    prior=studio.reading_state(module_id,revision).get('current') or {}
    studio.record_progress(module_id,revision,{'event_id':str(uuid.uuid4()),'section_id':prior.get('section_id',p['sections'][0]['id']),
        'view':'learn','assessment_feedback_consent':consent=='true'})
    return redirect(url_for('learning.module',module_id=module_id,revision=revision,view='learn'),code=303)


def author_provider():
    factory=current_app.config.get('LEARNING_AUTHOR_PROVIDER_FACTORY')
    if factory:return factory()
    from personal_learning_assistant.tutor.http_provider import OpenAICompatibleTutorProvider
    return OpenAICompatibleTutorProvider()


@learning_blueprint.post('/learning/author/<token>/generate')
def generate_author_draft(token):
    from personal_learning_assistant.learning_studio.multilecture_authoring import generate
    from personal_learning_assistant.learning_studio.validation import PackageError
    from personal_learning_assistant.tutor.provider import TutorProviderUnavailableError
    from personal_learning_assistant.tutor.http_provider import TutorProviderRequestError
    provider=author_provider()
    if not hmac.compare_digest(request.form.get('provider_binding',''),author_provider_binding(provider)):
        raise PackageError('The provider configuration changed. Reload the draft and review the destination before consenting.',403)
    try:
        next_token=generate(service(),token,provider,consented=request.form.get('provider_consent')=='true')
    except (TutorProviderUnavailableError,TutorProviderRequestError):
        raise PackageError('The configured provider could not generate this draft. Original files and local drafts are preserved; retry or author locally.',503)
    return redirect(url_for('learning.author_draft',token=next_token),code=303)


def assessment_topic_choices(studio,package):
    """Read canonical identities through the existing Assessment owner."""
    from contextlib import closing
    from pathlib import Path
    import sqlite3
    from .routes import _assessment_intelligence_service
    mapping=package['mapping']
    if not mapping:return None
    course=next((c for c in studio.catalogue_loader().get('courses',[]) if c['id']==mapping['course_id']),None)
    if not course:return None
    try:
        database=Path(_assessment_intelligence_service().database_path).absolute()
        if not database.is_file() or any(p.is_symlink() for p in (database,*database.parents)):return None
        with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as con:
            con.row_factory=sqlite3.Row;con.execute('PRAGMA query_only=ON')
            courses=con.execute('SELECT id,code,name FROM courses WHERE lower(code)=lower(?) AND deleted_at IS NULL',(course['code'],)).fetchall()
            if len(courses)!=1:return None
            canonical=dict(courses[0]);topics=[dict(t) for t in con.execute('SELECT id,name FROM topics WHERE course_id=? AND deleted_at IS NULL ORDER BY position,id',(canonical['id'],))]
        return {'course':canonical,'topics':topics}
    except (AttributeError,sqlite3.Error,OSError):return None


@learning_blueprint.post('/learning/modules/<module_id>/<int:revision>/assessment-link')
def review_assessment_link(module_id,revision):
    from personal_learning_assistant.learning_studio.validation import require
    from personal_learning_assistant.learning_studio.assessment_bridge import save_reviewed_link
    studio=service();p=studio.module(module_id,revision);choices=assessment_topic_choices(studio,p)
    require(request.form.get('reviewed')=='true' and choices is not None,'Review a real Assessment topic for this course before linking.')
    topic_id=request.form.get('topic_id','')
    require(any(t['id']==topic_id for t in choices['topics']),'Select a canonical topic in this same course.')
    save_reviewed_link(studio,module_id,revision,choices['course']['id'],topic_id)
    return redirect(url_for('learning.module',module_id=module_id,revision=revision,view='learn'),code=303)


def author_provider_binding(provider):
    import hashlib
    return hashlib.sha256((type(provider).__name__+'\0'+str(getattr(provider,'api_url',''))+'\0'+str(getattr(provider,'model',''))).encode()).hexdigest()
