"""Explicit phone-local launcher. Import is inert; start is called by Android.

There is no JavaScript bridge. A per-process capability cookie, installed by
native code before navigation, authenticates every request including assets.
"""
from __future__ import annotations

import hmac
import logging
import os
from pathlib import Path
import secrets
import sys
from threading import Thread, RLock

_runtime = None


class Runtime:
    def __init__(self, root, app, token):
        from werkzeug.serving import WSGIRequestHandler, make_server

        class QuietHandler(WSGIRequestHandler):
            def log(self, *args, **kwargs):
                pass

        self.root, self.token, self.app = root, token, app
        self.server = make_server('127.0.0.1', 0, app, threaded=True,
                                  request_handler=QuietHandler)
        self.origin = f'http://127.0.0.1:{self.server.server_port}'
        from flask import abort, request, g
        request_lock = RLock()

        @app.before_request
        def authenticate_native_request():
            if request.host_url.rstrip('/') != self.origin:
                abort(403)
            supplied = request.cookies.get('anvaya_native', '')
            if not hmac.compare_digest(supplied, self.token):
                abort(403)
            origin = request.headers.get('Origin')
            if origin and origin != self.origin:
                abort(403)
            if request.headers.get('Sec-Fetch-Site') == 'cross-site':
                abort(403)
            if request.method not in ('GET', 'HEAD') and origin != self.origin:
                abort(403)
            request_lock.acquire()
            g.native_request_lock = True

        @app.teardown_request
        def release_native_request(error):
            if getattr(g, 'native_request_lock', False):
                g.native_request_lock = False
                request_lock.release()

        @app.after_request
        def native_headers(response):
            response.headers['Cache-Control'] = 'no-store'
            return response

        self.thread = Thread(target=self.server.serve_forever,
                             name='anvaya-private-runtime', daemon=True)
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        self.app.extensions['academic_wal_publisher'].stop()


def _offline_network_policy():
    """This build permits Python networking only to numeric loopback addresses."""
    import socket
    from ipaddress import ip_address
    resolve = socket.getaddrinfo
    connect = socket.socket.connect
    connect_ex = socket.socket.connect_ex
    def local(host):
        try: return ip_address(host).is_loopback
        except (ValueError, TypeError): return False
    def checked_resolve(host, port, *args, **kwargs):
        if not local(host): raise PermissionError('Internet is disabled in the Android-local build')
        return resolve(host, port, *args, **kwargs)
    def checked_connect(sock, address):
        if not isinstance(address, tuple) or not local(address[0]):
            raise PermissionError('Internet is disabled in the Android-local build')
        return connect(sock, address)
    def checked_connect_ex(sock, address):
        if not isinstance(address, tuple) or not local(address[0]):
            raise PermissionError('Internet is disabled in the Android-local build')
        return connect_ex(sock, address)
    socket.getaddrinfo = checked_resolve
    socket.socket.connect = checked_connect
    socket.socket.connect_ex = checked_connect_ex


def start(root_path=None):
    """Initialize app-private paths before any legacy config import, then serve.

    Caller must pass Android Context.filesDir, never external/shared storage.
    Existing schemas are inspected/backed up by the production migration owner.
    """
    global _runtime
    if _runtime is not None:
        return _runtime
    root = Path(root_path or os.environ['ANVAYA_ANDROID_DATA_ROOT']).absolute()
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError('Runtime root must not contain symlinks')
    root.mkdir(parents=True, exist_ok=True)
    os.environ['ANVAYA_ANDROID_DATA_ROOT'] = str(root)
    os.environ['ANVAYA_PRIVATE_MOBILE'] = 'true'
    os.environ['ANVAYA_MOBILE_ALLOW_CLOUD_AI'] = 'false'
    os.environ.pop('ANVAYA_MOBILE_AI_DATA_ACK', None)
    # Preserve desktop import resolution when moving legacy relative data paths.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    os.chdir(root)
    from personal_learning_assistant.android_backup import apply_pending_restore
    apply_pending_restore(root)
    import config
    if config.BASE_PATH != root:
        raise RuntimeError('Academic configuration loaded before private runtime root')
    config.ensure_runtime_directories()
    from personal_learning_assistant.services.assessment_activation import activate_assessment_extension
    activate_assessment_extension(database_path=config.DATABASE_PATH, backup_path=config.BACKUP_PATH)
    from personal_learning_assistant.services.academic_wal_installation import InstalledAcademicWalPublisher
    publisher = InstalledAcademicWalPublisher(config.DATABASE_PATH, interval_seconds=10)
    publisher.start()
    from personal_learning_assistant.ui.web import create_app
    app = create_app({'PRIVATE_MOBILE_MODE': True, 'ANDROID_LOCAL_RUNTIME': True,
        'MOBILE_ALLOW_CLOUD_AI': False, 'MOBILE_AI_DATA_ACK': '',
        'ASSESSMENT_EXTENDED_ENABLED': True, 'ACADEMIC_DATABASE_PATH': config.DATABASE_PATH,
        'LEARNING_LIBRARY_DATABASE_PATH': config.DATABASE_PATH,
        'LEARNING_STUDIO_DATABASE': str(root/'data/learning_studio.sqlite3'),
        'LEARNING_STUDIO_SOURCE_DATABASE': str(config.DATABASE_PATH),
        'LEARNING_STUDIO_SOURCE_ROOTS': {'documents': root/'data/documents'},
        'ACADEMIC_WAL_SNAPSHOT_PROVIDER': publisher.feed.latest,
        'ACADEMIC_WAL_SNAPSHOT_MAX_AGE': 120,
        'MAX_CONTENT_LENGTH': 50 * 1024 * 1024})
    logging.getLogger('werkzeug').disabled = True
    # Academic errors are shown in UI; do not copy records or paths to logcat.
    app.logger.disabled = True
    app.extensions['academic_wal_publisher'] = publisher
    from personal_learning_assistant.ui.web.android_device import register_android_device
    register_android_device(app, root)
    _offline_network_policy()
    _runtime = Runtime(root, app, secrets.token_urlsafe(32))
    return _runtime


def launch(root_path):
    """Native-only return value, never inserted into URLs, DOM, logs or intents."""
    runtime = start(root_path)
    return [runtime.origin, runtime.token]
