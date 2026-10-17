"""Scoped explicit approval tokens; no server-side planning state on GET."""
from secrets import token_bytes
from urllib.parse import urlsplit
from flask import current_app, request
from itsdangerous import BadSignature, URLSafeTimedSerializer


def register_approval_controls(app):
    app.extensions['planner_approval_signer'] = URLSafeTimedSerializer(token_bytes(32), salt='planner-approve-v1')
    app.context_processor(lambda: {'planner_approval_token': approval_token})


def approval_token(agenda_date):
    return current_app.extensions['planner_approval_signer'].dumps({'date': agenda_date})


def valid_approval(agenda_date):
    origin = request.headers.get('Origin')
    if request.headers.get('Sec-Fetch-Site')=='cross-site':
        return False
    if origin and (urlsplit(origin).scheme, urlsplit(origin).netloc)!=(request.scheme,request.host):
        return False
    try:
        payload = current_app.extensions['planner_approval_signer'].loads(request.form.get('approval_token',''),max_age=900)
        return payload == {'date':agenda_date}
    except (BadSignature, ValueError, TypeError):
        return False
