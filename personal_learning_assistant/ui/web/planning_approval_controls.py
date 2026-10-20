"""Scoped explicit approval tokens; no server-side planning state on GET."""
import re
from secrets import token_bytes
from urllib.parse import urlsplit
from flask import current_app, request
from itsdangerous import BadSignature, URLSafeTimedSerializer


def register_approval_controls(app):
    app.extensions['planner_approval_signer'] = URLSafeTimedSerializer(token_bytes(32), salt='planner-approve-v1')
    app.context_processor(lambda: {'planner_approval_token': approval_token})


def approval_token(agenda_date, revision=None, nonce=None):
    return current_app.extensions['planner_approval_signer'].dumps({'date': agenda_date, 'revision': revision, 'nonce': nonce})


def valid_approval(agenda_date):
    origin = request.headers.get('Origin')
    if request.headers.get('Sec-Fetch-Site')=='cross-site':
        return False
    if origin and (urlsplit(origin).scheme, urlsplit(origin).netloc)!=(request.scheme,request.host):
        return False
    try:
        payload = current_app.extensions['planner_approval_signer'].loads(request.form.get('approval_token',''),max_age=900)
        return (isinstance(payload, dict) and set(payload) == {'date', 'revision', 'nonce'}
                and payload['date'] == agenda_date
                and isinstance(payload['revision'],str) and re.fullmatch(r'[0-9a-f]{64}',payload['revision']) is not None
                and (payload['nonce'] is None or isinstance(payload['nonce'],str)))
    except (BadSignature, ValueError, TypeError):
        return False


def approval_context_revision():
    # Call only after valid_approval has checked origin, signature and expiry.
    return current_app.extensions['planner_approval_signer'].loads(
        request.form.get('approval_token', ''), max_age=900,
    )
