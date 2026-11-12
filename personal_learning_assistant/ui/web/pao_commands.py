"""Local, expiring, purpose-scoped command guards shared by PAO aliases."""
from secrets import token_bytes
from uuid import uuid4
from datetime import datetime, timezone
from urllib.parse import urlsplit
from flask import current_app, request
from itsdangerous import BadSignature, URLSafeTimedSerializer


def command_scope(path):
    if path.startswith('/planning/') or path == '/planning' or path.startswith('/calendar/assessments/'):
        return 'planning'
    if path.startswith('/obsidian/') or path == '/obsidian' or path.startswith('/library/connected-sources/obsidian'):
        return 'obsidian'
    return None


def command_token(scope):
    return current_app.extensions['pao_command_signer'].dumps({'scope': scope})


def register_pao_commands(app):
    app.extensions['pao_command_signer'] = URLSafeTimedSerializer(token_bytes(32), salt='pao-local-command-v1')
    app.context_processor(lambda: {'pao_command_token': command_token, 'pao_command_id': lambda: str(uuid4()), 'pao_now': lambda: datetime.now(timezone.utc).isoformat()})

    @app.before_request
    def require_local_command():
        scope = command_scope(request.path)
        if scope is None or request.method not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            return None
        host = request.host.split(':')[0] if not request.host.startswith('[') else request.host.split(']')[0] + ']'
        allowed = app.config.get('PAO_ALLOWED_HOSTS', ('localhost', '127.0.0.1', '[::1]'))
        if host.lower() not in allowed:
            return 'Untrusted local command host.', 403
        origin = request.headers.get('Origin')
        if request.headers.get('Sec-Fetch-Site') == 'cross-site':
            return 'Cross-site commands are not allowed.', 403
        if origin:
            parsed = urlsplit(origin)
            if (parsed.scheme, parsed.netloc) != (request.scheme, request.host):
                return 'Cross-site commands are not allowed.', 403
        request.max_content_length = (26 * 1024 * 1024 if '/connected-sources/' in request.path else 3 * 1024 * 1024)
        try:
            supplied = request.headers.get('X-PAO-Token')
            if not supplied and request.is_json and request.path.startswith('/obsidian/note/reading/'):
                request.max_content_length = 16384
                body = request.get_json(silent=True)
                if not isinstance(body, dict):
                    raise ValueError('Command body must be an object.')
                supplied = body.get('pao_token', '')
            if not supplied:
                supplied = request.form.get('pao_token', '')
            value = app.extensions['pao_command_signer'].loads(supplied, max_age=1800)
            if value != {'scope': scope}:
                raise ValueError('Wrong command purpose')
        except (BadSignature, TypeError, ValueError):
            return 'Refresh this page before making changes; the command token is missing or expired.', 403
        return None
