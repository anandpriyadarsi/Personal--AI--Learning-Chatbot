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
    return render_template('learning_library.html', active_page='learning', library=service().library(), course=None, search='', topic='')


@learning_blueprint.get('/learning/courses/<course_id>')
def course(course_id):
    from personal_learning_assistant.learning_studio.validation import PackageError
    try: offset = int(request.args.get('offset', '0'))
    except ValueError: raise PackageError('Invalid pagination offset.')
    search = request.args.get('q', '')
    topic = request.args.get('topic', '')
    view = service().library(course_id=course_id, search=search, topic=topic, offset=offset)
    selected = next((c for c in view['courses'] if c['id'] == course_id), None)
    if course_id == 'unmapped': selected = {'id': 'unmapped', 'code': 'Unmapped', 'name': 'Needs mapping review', 'topics': []}
    if course_id == 'unavailable': selected = {'id': 'unavailable', 'code': 'Course unavailable / needs review', 'name': 'Course unavailable / needs review', 'topics': []}
    if selected is None: raise PackageError('Course not registered.', 404)
    return render_template('learning_library.html', active_page='learning', library=view, course=selected, search=search, topic=topic)


def module_view(module_id, revision, *, staged=False):
    from personal_learning_assistant.learning_studio.validation import require
    from personal_learning_assistant.learning_studio.rendering import markdown
    from personal_learning_assistant.learning_studio.review_brief import format_review_brief
    view = request.args.get('view', 'overview')
    require(view in VIEWS, 'Unknown reader view.', 404)
    s = service()
    p = s.module(module_id, revision, staged=staged)
    cat = s.catalogue_loader()
    mapping = p['mapping']
    course = next((c for c in cat.get('courses', []) if mapping and c['id'] == mapping['course_id']), None)
    if mapping and course is None:
        course = {'id': 'unavailable', 'code': 'Course unavailable / needs review'}
    return render_template('learning_module.html', active_page='learning', module=p, view=view, staged=staged,
        course=course, markdown=markdown, weak=[] if staged else s.weak(module_id, revision),
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
    return jsonify(service().attempt(module_id, payload))


@learning_blueprint.route('/learning/import', methods=['GET', 'POST'])
def import_module():
    from personal_learning_assistant.learning_studio.validation import PackageError, require
    if request.method == 'GET':
        return render_template('learning_import.html', active_page='learning', csrf_token=current_app.extensions['learning_studio_csrf'])
    from personal_learning_assistant.learning_studio.archive import decode_upload
    upload = request.files.get('package')
    require(upload is not None, 'Choose an authored learning package.')
    package, assets = decode_upload(upload.read(25_000_001), upload.filename)
    try:
        result = service().stage(package, assets)
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
