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
    if not current_app.config.get('PAO_V3_ENABLED', False):
        with current_app.extensions['planning_proposal_context_lock']:
            context = current_app.extensions['planning_proposal_contexts'].get(agenda_date)
            return dict(context) if context is not None else None
    from personal_learning_assistant.repositories.sqlite.planner_proposal_repository import SQLitePlannerProposalRepository
    from personal_learning_assistant.repositories.sqlite.daily_agenda_repository import DailyAgendaRepositoryError
    try:
        service = current_app.extensions['planning_proposal_service_factory']()
        daily = getattr(service, 'daily', None)
        if daily is None:
            return None
        return SQLitePlannerProposalRepository(daily.agendas.database_path).latest(agenda_date)
    except DailyAgendaRepositoryError as error:
        raise OperationalPlannerWebUnavailableError('Saved proposal context is unavailable.') from error


def register_planning_proposals(app, service_factory):
    signer = URLSafeTimedSerializer(token_bytes(32), salt='planning-proposal-v1')
    blueprint = Blueprint('planning_proposals', __name__)

    app.extensions['planning_proposal_service_factory'] = service_factory
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
                    durable = current_app.config.get('PAO_V3_ENABLED', False)
                    saved = service.save_proposal(
                        agenda_date, payload['start'], payload['end'], windows=payload['windows'],
                        fingerprint=payload['fingerprint'], semantic_hash=payload['semantic_hash'],
                        proposal_context=payload if durable else None, **config,
                    )
                    if not durable:
                        contexts = current_app.extensions['planning_proposal_contexts']
                        contexts[agenda_date] = {**payload, 'saved_fingerprint': saved['planning_fingerprint']}
                        while len(contexts) > 128:
                            del contexts[next(iter(contexts))]
                return redirect(url_for('web.planning_day', agenda_date=agenda_date), code=303)
            starts, ends = request.args.getlist('start'), request.args.getlist('end')
            if len(starts) != len(ends):
                raise OperationalPlannerWebValidationError('Each availability window needs a start and end.')
            windows = [(start, end) for start, end in zip(starts, ends) if start or end]
            start, end = windows[0] if windows else ('', '')
            preview = service_factory().preview_proposal(agenda_date, start, end, windows=windows, **config)
            token = signer.dumps({'date': agenda_date, 'start': start, 'end': end, 'windows': windows,
                                  'command_id': token_urlsafe(24), 'nonce': token_urlsafe(24),
                                  'timezone': config['local_timezone'],
                                  'break_minutes': config['break_minutes'],
                                  'policy': 'explicit-availability-v1',
                                  'fingerprint': preview['fingerprint'],
                                  'semantic_hash': preview['semantic_hash']})
            return render_template('planning_day.html', active_page='planning', day=preview['day'],
                                   error_message='', proposal_token=token,
                                   proposal_start=start, proposal_end=end, proposal_windows=windows,
                                   proposal_timezone=config['local_timezone'],
                                   proposal_break_minutes=config['break_minutes'])
        except OperationalPlannerWebValidationError as error:
            return str(error), 400
        except OperationalPlannerWebConflictError as error:
            return str(error), 409
        except OperationalPlannerWebUnavailableError as error:
            return str(error), 503

    app.register_blueprint(blueprint)
