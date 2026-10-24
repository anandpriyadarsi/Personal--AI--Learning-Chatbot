"""Android private-runtime navigation optimizations and privacy regressions."""
from tests.test_android_runtime import run


def test_static_assets_are_privately_cacheable_but_every_page_is_no_store(tmp_path):
    run(tmp_path, r'''
        from personal_learning_assistant.android_runtime import start
        r = start()
        c = r.app.test_client()
        c.set_cookie('anvaya_native', r.token, domain='127.0.0.1')
        js = c.get('/static/js/app.js', base_url=r.origin)
        assert js.status_code == 200
        assert b'global-study-search' in js.data
        assert js.headers['Cache-Control'] == 'private, max-age=300'
        # Cacheable responses are sufficient for repeat navigation. Depending
        # on the bundled static implementation, validators may not be emitted.
        if js.headers.get('ETag'):
            cached = c.get('/static/js/app.js', base_url=r.origin,
                           headers={'If-None-Match': js.headers['ETag']})
            assert cached.status_code == 304
            assert cached.headers['Cache-Control'] == 'private, max-age=300'
        assert c.head('/static/js/app.js', base_url=r.origin).status_code == 200
        assert c.get('/static/js/does-not-exist.js', base_url=r.origin).headers['Cache-Control'] == 'no-store'
        for path in ('/', '/notes', '/learning', '/assessments', '/library', '/mobile/device'):
            response = c.get(path, base_url=r.origin)
            assert response.status_code == 200, path
            assert response.headers['Cache-Control'] == 'no-store', path
        # A cached CSS or JS URL still requires the private capability on the server.
        without_cookie = r.app.test_client().get('/static/js/app.js', base_url=r.origin)
        assert without_cookie.status_code == 403
        assert without_cookie.headers['Cache-Control'] == 'no-store'
        bad_origin = c.get('/static/js/app.js', base_url=r.origin,
                           headers={'Origin': 'https://malicious.invalid'})
        assert bad_origin.status_code == 403
        assert bad_origin.headers['Cache-Control'] == 'no-store'
        r.stop()
    ''')


def test_static_file_does_not_block_an_authenticated_navigation(tmp_path):
    run(tmp_path, r'''
        from personal_learning_assistant.android_runtime import start
        from flask import request
        from threading import Event, Thread
        import urllib.request
        r = start()
        static_entered, release_static = Event(), Event()
        failures = []
        @r.app.before_request
        def hold_a_static_file():
            if request.endpoint == 'static' and request.path == '/static/css/app.css':
                static_entered.set()
                assert release_static.wait(12), 'test did not release blocked static response'
        def fetch_static():
            try:
                req = urllib.request.Request(r.origin + '/static/css/app.css',
                    headers={'Cookie': 'anvaya_native=' + r.token})
                with urllib.request.urlopen(req, timeout=15) as response:
                    assert response.status == 200
            except Exception as error:
                failures.append(str(error))
        worker = Thread(target=fetch_static, daemon=True)
        worker.start()
        try:
            assert static_entered.wait(10), 'static request never entered'
            # A user clicking Notes should not queue behind a slow image/CSS file.
            req = urllib.request.Request(r.origin + '/notes',
                headers={'Cookie': 'anvaya_native=' + r.token})
            with urllib.request.urlopen(req, timeout=6) as response:
                assert response.status == 200
                assert response.headers['Cache-Control'] == 'no-store'
        finally:
            release_static.set()
            worker.join(15)
            r.stop()
        assert not worker.is_alive() and not failures, failures
    ''')
