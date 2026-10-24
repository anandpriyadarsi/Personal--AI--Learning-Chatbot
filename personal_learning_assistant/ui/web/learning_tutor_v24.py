"""Review and explicitly save a minimal receipt for exact offline learning help."""
from contextlib import nullcontext
from copy import copy
from secrets import token_bytes
from urllib.parse import quote, urlencode, urlsplit
import sqlite3

from flask import Blueprint, current_app, redirect, render_template, request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from personal_learning_assistant.learning_studio.educational_projection import build_preview
from personal_learning_assistant.learning_studio.grounded_help import consume
from personal_learning_assistant.learning_studio.validation import PackageError, require
from personal_learning_assistant.repositories.sqlite.tutor_repository import TutorRepositoryError
from personal_learning_assistant.services.learning_tutor_session_v24 import (
    _safe_path, default_owner, project_session_metadata_snapshot, save_session_metadata,
)
from personal_learning_assistant.services.tutor_session_service import TutorSessionError


def learning_tutor_v24_url(module, revision, event_id, question_id, level):
    return '/academic-evidence/learning/'+quote(str(module), safe='')+'/'+str(revision)+'/tutor-session?'+urlencode(
        {'event_id': event_id, 'question_id': question_id, 'level': level})


def register_learning_tutor_v24(app):
    bp = Blueprint('learning_tutor_v24', __name__)
    signer = URLSafeTimedSerializer(token_bytes(32), salt='learning-tutor-v24-receipt')

    @bp.before_request
    def boundary():
        if (current_app.config.get('ACADEMIC_EVIDENCE_ENABLED', True) is not True or
                current_app.config.get('LEARNING_TUTOR_V24_ENABLED', True) is not True):
            return 'Learning Tutor receipts are disabled.', 404
        if request.method == 'POST':
            request.max_content_length = 12000
            origin = request.headers.get('Origin')
            if request.headers.get('Sec-Fetch-Site') == 'cross-site' or (origin and
                    (urlsplit(origin).scheme, urlsplit(origin).netloc) != (request.scheme, request.host)):
                return 'Cross-site Tutor actions are not allowed.', 403

    @bp.after_request
    def no_store(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @bp.errorhandler(PackageError)
    def invalid(error):
        return render_template('learning_tutor_v24.html', active_page='evidence',
            error_message=str(error)), error.status

    def academic_service():
        factory = current_app.config.get('ACADEMIC_EVIDENCE_SERVICE_FACTORY')
        if factory:
            return factory()
        import config as installed
        from personal_learning_assistant.services.academic_evidence_service import AcademicEvidenceService
        from .learning_studio import service
        return AcademicEvidenceService(current_app.config.get('ACADEMIC_DATABASE_PATH', installed.DATABASE_PATH),
            studio=service(), wal_snapshot_provider=current_app.config.get('ACADEMIC_WAL_SNAPSHOT_PROVIDER'),
            local_timezone=current_app.config.get('ACADEMIC_TIMEZONE', 'Asia/Kolkata'))

    def context(module, revision, event, question, level):
        academic = academic_service()
        frozen, catalogue = academic.frozen_learning(module, revision)
        bound = copy(academic)
        bound.studio = frozen
        view = bound.learning(module, revision)
        preview = build_preview(frozen, module, revision, catalogue=catalogue, as_of=academic.now())
        help_view = consume(preview, view, event_id=event, question_id=question,
                            level=level, explicit_action=True)
        return academic, view, preview, help_view

    def web_owner():
        from .routes import _academic_agent_service
        return _academic_agent_service()

    def save_available(academic, history):
        if not history['available']:
            return False
        try:
            _safe_path(academic.path)
            if current_app.config.get('LEARNING_TUTOR_V24_OWNER_FACTORY') is None:
                require(_safe_path(web_owner().database_path) == _safe_path(academic.path),
                        'Tutor and evidence owners differ.', 503)
            return True
        except (PackageError, OSError, ValueError, TypeError, AttributeError, RuntimeError):
            return False

    route = '/academic-evidence/learning/<module_id>/<int:revision>/tutor-session'

    @bp.get(route)
    def review(module_id, revision):
        fields = {'event_id', 'question_id', 'level'}
        require(set(request.args) == fields and all(len(request.args.getlist(k)) == 1 for k in fields),
                'Choose one exact practice event, question and assistance level.')
        academic, view, preview, help_view = context(module_id, revision,
            request.args['event_id'], request.args['question_id'], request.args['level'])
        history = project_session_metadata_snapshot(academic, view)
        available = save_available(academic, history)
        token = signer.dumps({'module_id': module_id, 'revision': revision,
            'event_id': help_view['event_id'], 'question_id': help_view['question']['id'],
            'level': help_view['assistance_level'], 'fingerprint': view.fingerprint,
            'reviewed_at': view.as_of}) if available else None
        return render_template('learning_tutor_v24.html', active_page='evidence', view=view,
            help=help_view, history=history, receipt_token=token, error_message='')

    @bp.post(route)
    def save(module_id, revision):
        fields = {'receipt_token', 'confirm_save'}
        require(not request.args and set(request.form) == fields and
                all(len(request.form.getlist(k)) == 1 for k in fields) and request.form['confirm_save'] == 'yes',
                'Explicit approval of the minimal metadata is required.')
        try:
            payload = signer.loads(request.form['receipt_token'], max_age=900)
            require(isinstance(payload, dict) and set(payload) == {'module_id', 'revision', 'event_id',
                'question_id', 'level', 'fingerprint', 'reviewed_at'} and payload['module_id'] == module_id and
                payload['revision'] == revision, 'Invalid receipt context.')
        except (BadSignature, TypeError, ValueError) as error:
            raise PackageError('Invalid or expired review. Review the exact help again.') from error
        academic, view, preview, help_view = context(module_id, revision, payload['event_id'],
            payload['question_id'], payload['level'])
        require(payload['fingerprint'] == view.fingerprint, 'Academic context changed. Review this help again.', 409)
        try:
            factory = current_app.config.get('LEARNING_TUTOR_V24_OWNER_FACTORY')
            owner_context = factory() if factory else default_owner(academic, web_owner())
            with (owner_context if hasattr(owner_context, '__enter__') else nullcontext(owner_context)) as owner:
                save_session_metadata(owner, academic, view, preview, help_view, reviewed_at=payload['reviewed_at'])
        except PackageError:
            raise
        except (TutorRepositoryError, TutorSessionError, sqlite3.Error, OSError, RuntimeError, TypeError, ValueError) as error:
            raise PackageError('Canonical Tutor storage is unavailable; no save is claimed.', 503) from error
        return redirect('/academic-evidence/learning/'+quote(module_id, safe='')+'/'+str(revision)+'#tutor-session-history', code=303)

    app.register_blueprint(bp)
