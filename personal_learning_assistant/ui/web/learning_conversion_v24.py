"""Native Learning Studio review/edit/stage routes; explicit publication stays separate."""
from flask import current_app, jsonify, make_response, redirect, render_template, request, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from secrets import token_bytes
import hashlib
import hmac
import json
from werkzeug.exceptions import RequestEntityTooLarge
from personal_learning_assistant.learning_studio.validation import PackageError, require
from personal_learning_assistant.learning_studio.reviewed_conversion import prepare, stage_review


def register_learning_conversion_v24(app):
    from .learning_studio import service
    # The signing key must be independent of the browser-visible CSRF token.
    app.extensions['learning_conversion_signer'] = URLSafeTimedSerializer(token_bytes(32), salt='reviewed-conversion-v24')

    def signer():
        return current_app.extensions['learning_conversion_signer']

    def csrf_digest():
        return hashlib.sha256(current_app.extensions['learning_studio_csrf'].encode()).hexdigest()

    def render(context, review_token=None):
        response = make_response(render_template('learning_conversion_v24.html', active_page='learning',
            context=context, review_token=review_token, csrf_token=current_app.extensions['learning_studio_csrf']))
        response.headers['Cache-Control'] = 'no-store'
        return response

    def strict_json():
        def distinct(pairs):
            obj = {}
            for key, value in pairs:
                require(key not in obj, 'Duplicate JSON fields are unsupported.')
                obj[key] = value
            return obj
        try:
            value = json.loads(request.get_data(cache=True), object_pairs_hook=distinct,
                parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
        except (ValueError, UnicodeError, RecursionError) as error:
            if isinstance(error, PackageError):
                raise
            raise PackageError('Supply a bounded JSON object with distinct fields.') from error
        require(isinstance(value, dict), 'Supply a conversion review object.')
        return value

    def boundary(fn):
        from functools import wraps
        @wraps(fn)
        def wrapped(*args, **kwargs):
            try:
                # Apply route-specific bounds before form/CSRF or JSON parsing.
                request.max_content_length = 450000 if fn.__name__ == 'stage' else 20000
                require(not request.args, 'Conversion query fields are unsupported.')
                if request.method == 'POST':
                    if request.is_json:
                        payload = strict_json()
                    else:
                        payload = request.form
                        for key in ('csrf_token', 'review_token', 'approve'):
                            require(len(payload.getlist(key)) <= 1, 'Repeated scalar conversion fields are unsupported.')
                    for key in ('csrf_token', 'review_token'):
                        if key in payload:
                            require(isinstance(payload[key], str) and len(payload[key]) <= 30000, 'Invalid conversion request token.')
                    if request.is_json and 'approve' in payload:
                        require(type(payload['approve']) is bool, 'JSON approval must be a boolean.')
                    allowed = {'csrf_token', 'review_token', 'notes', 'reviewed_pages', 'approve'} if fn.__name__ == 'stage' else {'csrf_token'}
                    require(not set(payload) - allowed, 'Unsupported conversion fields.')
                    require(not request.files, 'Conversion uses the existing registered original; uploads are unsupported.')
                    expected = current_app.extensions['learning_studio_csrf']
                    actual = request.headers.get('X-Learning-CSRF') or (payload.get('csrf_token', '') if not request.is_json else '')
                    origin = request.headers.get('Origin')
                    require(hmac.compare_digest(str(actual), expected) and
                        (not origin or origin.rstrip('/') == request.host_url.rstrip('/')) and
                        request.headers.get('Sec-Fetch-Site') != 'cross-site',
                        'Invalid local request token. Reload Learning Studio and retry.', 403)
                    # Retain the strictly parsed JSON object; do not parse it again.
                    request.conversion_payload = payload
                return fn(*args, **kwargs)
            except (PackageError, RequestEntityTooLarge) as error:
                status = error.status if isinstance(error, PackageError) else 413
                message = str(error) if isinstance(error, PackageError) else 'Conversion review exceeds its request size bound.'
                if request.is_json:
                    return jsonify(error=message), status
                return render_template('learning_error.html', active_page='learning', message=message), status
        return wrapped

    @app.get('/learning/modules/<module_id>/<int:revision>/conversion', endpoint='learning_conversion')
    @boundary
    def conversion(module_id, revision):
        # GET verifies original availability without starting the parser.
        from personal_learning_assistant.learning_studio.reviewed_conversion import _snapshot
        package, _, _, _, _ = _snapshot(service(), module_id, revision)
        return render({'module': package})

    @app.get('/learning/modules/<module_id>/<int:revision>/conversion/original.pdf', endpoint='learning_conversion_original')
    @boundary
    def original(module_id, revision):
        from io import BytesIO
        from flask import send_file
        studio = service()
        package = studio.module(module_id, revision)
        response = send_file(BytesIO(studio.source(module_id, revision)), mimetype='application/pdf',
            download_name=package['source']['filename'], as_attachment=False)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = 'sandbox'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.post('/learning/modules/<module_id>/<int:revision>/conversion/preview', endpoint='learning_conversion_preview')
    @boundary
    def preview(module_id, revision):
        require(not current_app.config.get('ANDROID_LOCAL_RUNTIME'),
            'PDF draft conversion is unavailable in this Android build. Read the locally extracted Library text or import an authored Learning package.',422)
        context = prepare(service(), module_id, revision)
        context['binding']['csrf_digest'] = csrf_digest()
        return render(context, signer().dumps(context['binding']))

    @app.post('/learning/modules/<module_id>/<int:revision>/conversion/stage', endpoint='learning_conversion_stage')
    @boundary
    def stage(module_id, revision):
        payload = request.conversion_payload
        require(isinstance(payload, dict) or hasattr(payload, 'getlist'), 'Missing conversion review.')
        try:
            binding = signer().loads(payload.get('review_token', ''), max_age=1800)
        except (BadSignature, SignatureExpired):
            raise PackageError('Conversion review expired or was changed. Reload and review the original again.', 400)
        require(isinstance(binding, dict) and binding.get('csrf_digest') == csrf_digest(), 'Conversion review request context changed.', 409)
        notes = payload.get('notes') if request.is_json else payload.getlist('notes')
        reviewed = payload.get('reviewed_pages') if request.is_json else payload.getlist('reviewed_pages')
        if not request.is_json:
            require(all(p.isascii() and p.isdecimal() for p in reviewed), 'Invalid page review confirmation.')
            reviewed = [int(p) for p in reviewed]
        result = stage_review(service(), module_id, revision, binding, notes, reviewed,
            approved=payload.get('approve') is True if request.is_json else payload.get('approve') == 'stage')
        if request.is_json:
            return jsonify(result), 201
        return redirect(url_for('learning.preview', module_id=module_id, revision=result['revision']), code=303)
