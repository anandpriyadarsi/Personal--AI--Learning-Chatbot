"""Phone runtime contracts execute the production app in isolated processes."""
import os
import subprocess
import sys
import textwrap


def run(root, script):
    env = dict(os.environ, ANVAYA_ANDROID_DATA_ROOT=str(root))
    result = subprocess.run([sys.executable, '-c', textwrap.dedent(script)],
                            env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_private_bootstrap_and_saved_note_survive_new_process(tmp_path):
    run(tmp_path, '''
        from personal_learning_assistant.android_runtime import start
        import urllib.request, urllib.error, urllib.parse, sqlite3, json
        runtime = start()
        base = runtime.origin
        try:
            urllib.request.urlopen(base + '/healthz')
            raise AssertionError('Other app reached local backend')
        except urllib.error.HTTPError as e:
            assert e.code == 403
        cookie = 'anvaya_native=' + runtime.token
        def req(path, data=None):
            return urllib.request.urlopen(urllib.request.Request(base+path, data=data,
                headers={'Cookie':cookie, 'Origin':base}))
        assert req('/learning').status == 200
        note = urllib.parse.urlencode({'title':'Synthetic offline note',
             'body':'Restart preserves this synthetic study record.'}).encode()
        assert req('/notes/create/typed', note).status == 200
        for path in ['/','/notes','/assessments','/library','/planning','/analysis','/agent']:
            
            try: assert req(path).status == 200, path
            except urllib.error.HTTPError as e: raise AssertionError(path + ' ' + str(e.code))
        with sqlite3.connect(runtime.root / 'data/learning_assistant.db') as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert db.execute('SELECT count(*) FROM schema_migrations').fetchone()[0] == 15
        print(runtime.token)
        runtime.stop()
    ''')
    run(tmp_path, '''
        from personal_learning_assistant.android_runtime import start
        import urllib.request
        r = start()
        req = urllib.request.Request(r.origin+'/notes', headers={'Cookie':'anvaya_native='+r.token})
        assert 'Synthetic offline note' in urllib.request.urlopen(req).read().decode()
        r.stop()
    ''')


def test_boundary_rejects_cross_origin_wrong_host_and_missing_origin(tmp_path):
    run(tmp_path, '''
        from personal_learning_assistant.android_runtime import start
        import urllib.request, urllib.error
        r = start()
        cases = [('/healthz',None,{}), ('/static/js/app.js',None,{}),
           ('/notes/create/typed', b'title=bad', {'Cookie':'anvaya_native='+r.token}),
           ('/healthz',None,{'Cookie':'anvaya_native='+r.token,'Origin':'https://evil.example'}),
           ('/healthz',None,{'Cookie':'anvaya_native='+r.token,'Host':'localhost:1'}),
           ('/healthz',None,{'Cookie':'anvaya_native='+r.token,'Sec-Fetch-Site':'cross-site'})]
        for path,data,headers in cases:
            try:
                urllib.request.urlopen(urllib.request.Request(r.origin+path,data=data,headers=headers))
                raise AssertionError((path, headers))
            except urllib.error.HTTPError as e:
                assert e.code in (400,403)
        r.stop()
    ''')
