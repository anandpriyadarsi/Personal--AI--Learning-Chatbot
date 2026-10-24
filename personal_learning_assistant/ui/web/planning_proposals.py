"""Explicit availability previews with signed, stale-safe canonical draft saves."""
from secrets import token_bytes, token_urlsafe
from threading import RLock
from urllib.parse import urlsplit

from flask import Blueprint, current_app, redirect, render_template, request, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer

from personal_learning_assistant.services.operational_planner_web_service import (
    OperationalPlannerWebConflictError, OperationalPlannerWebUnavailableError,
    OperationalPlannerWebValidationError,
)


def proposal_settings():
    return {'local_timezone': current_app.config.get('PLANNING_LOCAL_TIMEZONE', current_app.config.get('ACADEMIC_TIMEZONE', 'Asia/Kolkata')),
            'now': current_app.config.get('PLANNING_NOW'),
            'break_minutes': current_app.config.get('PLANNING_BREAK_MINUTES', 10)}


def saved_proposal_context(agenda_date):
    # Deliberately process-local: no unreviewed persistence contract is introduced.
    # A restart or eviction requires a new explicit availability preview.
    with current_app.extensions['planning_proposal_context_lock']:
        context = current_app.extensions['planning_proposal_contexts'].get(agenda_date)
        return dict(context) if context is not None else None


def register_planning_proposals(app, service_factory):
    signer = URLSafeTimedSerializer(token_bytes(32), salt='planning-proposal-v1')
    blueprint = Blueprint('planning_proposals', __name__)

    app.extensions['planning_proposal_contexts'] = {}
    app.extensions['planning_proposal_context_lock'] = RLock()

    @blueprint.route('/planning/proposal/<agenda_date>', methods=['GET', 'POST'])
    def proposal(agenda_date):
        try:
            config = proposal_settings()
            if request.method == 'POST':
                origin = request.headers.get('Origin')
                if request.headers.get('Sec-Fetch-Site') == 'cross-site':
                    return 'Cross-site planner changes are not allowed.', 403
                if origin and (urlsplit(origin).scheme, urlsplit(origin).netloc) != (request.scheme, request.host):
                    return 'Cross-site planner changes are not allowed.', 403
                try:
                    payload = signer.loads(request.form.get('proposal_token', ''), max_age=900)
                    if (payload['date'] != agenda_date or payload['timezone'] != config['local_timezone']
                            or payload.get('break_minutes') != config['break_minutes']
                            or payload.get('policy') != 'explicit-availability-v1'):
                        raise ValueError('Proposal context changed')
                except (BadSignature, KeyError, TypeError, ValueError):
                    return 'Invalid or expired proposal. Preview again before saving.', 400
                with current_app.extensions['planning_proposal_context_lock']:
                    service = service_factory()
                    saved = service.save_proposal(
                        agenda_date, payload['start'], payload['end'],
                        fingerprint=payload['fingerprint'], semantic_hash=payload['semantic_hash'], **config,
                    )
                    contexts = current_app.extensions['planning_proposal_contexts']
                    contexts[agenda_date] = {**payload, 'saved_fingerprint': saved['planning_fingerprint'],
                                             'nonce': token_urlsafe(24)}
                    # Bound transient memory without storing personal planner state.
                    while len(contexts) > 128:
                        del contexts[next(iter(contexts))]
                return redirect(url_for('web.planning_day', agenda_date=agenda_date), code=303)
            start, end = request.args.get('start', ''), request.args.get('end', '')
            preview = service_factory().preview_proposal(agenda_date, start, end, **config)
            token = signer.dumps({'date': agenda_date, 'start': start, 'end': end,
                                  'timezone': config['local_timezone'],
                                  'break_minutes': config['break_minutes'],
                                  'policy': 'explicit-availability-v1',
                                  'fingerprint': preview['fingerprint'],
                                  'semantic_hash': preview['semantic_hash']})
            return render_template('planning_day.html', active_page='planning', day=preview['day'],
                                   error_message='', proposal_token=token,
                                   proposal_start=start, proposal_end=end,
                                   proposal_timezone=config['local_timezone'],
                                   proposal_break_minutes=config['break_minutes'])
        except OperationalPlannerWebValidationError as error:
            return str(error), 400
        except OperationalPlannerWebConflictError as error:
            return str(error), 409
        except OperationalPlannerWebUnavailableError as error:
            return str(error), 503

    app.register_blueprint(blueprint)
