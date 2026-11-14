"""Real loopback HTTP probes; no external network or paid model calls."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import subprocess
import threading
import time

import pytest

from personal_learning_assistant.tutor.vision_provider import bounded_post


@contextmanager
def endpoint(mode):
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            seen.append(self.path)
            self.rfile.read(int(self.headers.get('Content-Length', '0')))
            if mode == 'redirect':
                self.send_response(307)
                self.send_header('Location', '/do-not-follow')
                self.end_headers()
                return
            self.send_response(200 if mode != 'error' else 500)
            self.end_headers()
            try:
                if mode == 'slow':
                    for _ in range(80):
                        self.wfile.write(b' ' * 8192)
                        self.wfile.flush()
                        time.sleep(.05)  # Every read succeeds; total must still expire.
                elif mode == 'large':
                    self.wfile.write(b' ' * 128001)
                elif mode == 'broken':
                    self.wfile.write(b'{"secret upstream URL and key":')
                else:
                    self.wfile.write(b'{"ok":true}')
            except (BrokenPipeError, ConnectionResetError):
                pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield 'http://127.0.0.1:%s/' % server.server_port, seen
    finally:
        server.shutdown()
        server.server_close()
        worker.join(2)


@pytest.fixture
def children(monkeypatch):
    spawned = []
    popen = subprocess.Popen
    def record(*args, **kwargs):
        process = popen(*args, **kwargs)
        spawned.append(process)
        return process
    monkeypatch.setattr(subprocess, 'Popen', record)
    return spawned


def assert_reaped(children):
    assert len(children) == 1
    assert children[0].poll() is not None
    assert children[0].stdin.closed and children[0].stdout.closed


def test_total_deadline_kills_slow_stream_and_leaves_no_worker(children):
    with endpoint('slow') as (url, seen):
        start = time.monotonic()
        with pytest.raises(ValueError, match='Provider outcome unavailable'):
            bounded_post(url, 'synthetic', {}, wall_timeout=.8)
        assert time.monotonic() - start < 2.5
        assert seen == ['/']
    assert_reaped(children)


@pytest.mark.parametrize('mode', ['large', 'redirect', 'error', 'broken'])
def test_transport_bounds_no_redirect_retry_or_upstream_error(mode):
    with endpoint(mode) as (url, seen):
        with pytest.raises(ValueError) as error:
            bounded_post(url, 'synthetic', {}, wall_timeout=3)
        assert str(error.value) == 'Provider outcome unavailable; review before retrying'
        assert seen == ['/']


def test_transport_success_and_cleanup(children):
    with endpoint('ok') as (url, seen):
        assert bounded_post(url, 'synthetic', {}, wall_timeout=3) == {'ok': True}
        assert seen == ['/']
    assert_reaped(children)


@pytest.mark.parametrize('value', [0, -1, 91, float('nan'), float('inf'), True])
def test_invalid_deadline_cannot_disable_bound(value):
    with pytest.raises(ValueError):
        bounded_post('http://127.0.0.1:1/', 'synthetic', {}, wall_timeout=value)
