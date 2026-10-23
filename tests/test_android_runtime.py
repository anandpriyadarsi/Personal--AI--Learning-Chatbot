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
        task=urllib.parse.urlencode({'title':'Synthetic persistent task','estimated_minutes':'30'}).encode()
        assert req('/planning/tasks',task).status==200
        for path in ['/','/notes','/assessments','/library','/planning','/analysis','/agent','/mobile/settings','/mobile/device']:

            try: assert req(path).status == 200, path
            except urllib.error.HTTPError as e: raise AssertionError(path + ' ' + str(e.code))
        with sqlite3.connect(runtime.root / 'data/learning_assistant.db') as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert db.execute("SELECT count(*) FROM planner_tasks WHERE title='Synthetic persistent task'").fetchone()[0]==1
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
        req=urllib.request.Request(r.origin+'/planning/tasks',headers={'Cookie':'anvaya_native='+r.token})
        assert 'Synthetic persistent task' in urllib.request.urlopen(req).read().decode()
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


def test_native_runtime_denies_outbound_python_network(tmp_path):
    run(tmp_path, '''
        from personal_learning_assistant.android_runtime import start
        import socket
        r = start()
        for host in ['example.com', '8.8.8.8']:
            try:
                socket.create_connection((host, 443), timeout=1)
                raise AssertionError('Outbound connection permitted')
            except PermissionError: pass
        r.stop()
    ''')


def test_phone_source_registration_course_setup_and_backup(tmp_path):
    run(tmp_path, '''
        from personal_learning_assistant.android_runtime import start
        from tests.academic_evidence_v23_fixtures import source_pdf, authored_sample
        from personal_learning_assistant.learning_studio.service import LearningStudioService
        from personal_learning_assistant.learning_studio.sources import RegisteredSources
        import io,sqlite3,zipfile,json
        r = start()
        c = r.app.test_client()
        c.set_cookie('anvaya_native', r.token, domain='127.0.0.1')
        def post(path, data):
            return c.post(path,base_url=r.origin,headers={'Origin':r.origin},data=data)
        assert post('/mobile/device/course',{'code':'SYN101','name':'Synthetic study'}).status_code==303
        raw=source_pdf()
        response=post('/mobile/device/source',{'source':(io.BytesIO(raw),'synthetic.pdf')})
        assert response.status_code==200,response.data
        with sqlite3.connect(r.root/'data/learning_assistant.db') as con:
            identity=con.execute('SELECT id FROM knowledge_documents').fetchone()[0]
            assert con.execute('SELECT count(*) FROM knowledge_chunks').fetchone()[0]>0
        p,assets=authored_sample(raw); p['source']['source_id']=identity; p['mapping']=None
        studio=LearningStudioService(r.root/'data/learning_studio.sqlite3',
            source_loader=RegisteredSources(r.root/'data/learning_assistant.db',{'documents':r.root/'data/documents'}),
            catalogue_loader=__import__('personal_learning_assistant.learning_studio.sources',fromlist=['catalogue']).catalogue)
        studio.stage(p,assets);studio.publish(p['module_id'],1)
        response=c.get('/learning/modules/uc100n-demo/1?view=learn',base_url=r.origin)
        assert response.status_code==200,response.data
        response=c.get('/learning/modules/uc100n-demo/1/conversion',base_url=r.origin)
        assert b'PDF draft conversion is unavailable in this Android build' in response.data
        assert b'Extract a temporary review draft' not in response.data
        response=c.post('/learning/modules/uc100n-demo/1/conversion/preview',base_url=r.origin,
            headers={'Origin':r.origin,'X-Learning-CSRF':r.app.extensions['learning_studio_csrf']})
        assert response.status_code==422,response.data
        assert b'PDF draft conversion is unavailable' in response.data
        response=c.post('/academic-evidence/learning/uc100n-demo/1/note-draft',base_url=r.origin,
            headers={'Origin':r.origin},data={'review_token':'unused-on-unsupported-platform'})
        assert response.status_code==422,response.data
        assert b'PDF draft conversion is unavailable' in response.data
        response=c.get('/mobile/device/export',base_url=r.origin)
        assert response.status_code==200
        with zipfile.ZipFile(io.BytesIO(response.data)) as z:
            assert 'data/learning_assistant.db' in z.namelist()
            assert 'data/learning_studio.sqlite3' in z.namelist()
            assert 'data/courses.json' in z.namelist()
        r.stop()
    ''')


def test_backup_between_50_and_100_mib_can_reach_restore_validator(tmp_path):
    run(tmp_path, '''
        from personal_learning_assistant.android_runtime import start
        import io,zipfile,json,hashlib
        r=start(); c=r.app.test_client()
        c.set_cookie('anvaya_native',r.token,domain='127.0.0.1')
        payload=b'x'*(51*1024*1024); out=io.BytesIO()
        with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_STORED) as z:
            z.writestr('data/large.txt',payload)
            z.writestr('manifest.json',json.dumps({'format':'anvaya.android-backup.v1',
                'files':{'data/large.txt':hashlib.sha256(payload).hexdigest()}}))
        response=c.post('/mobile/device/restore',base_url=r.origin,
            headers={'Origin':r.origin},data={'backup':(io.BytesIO(out.getvalue()),'backup.zip')})
        assert response.status_code==200,response.status_code
        assert (r.root/'restore-pending.zip').exists()
        r.stop()
    ''')


def test_original_semester_one_subjects_restore_without_losing_progress(tmp_path):
    """Production app shows the original subject cards, not synthetic course data."""
    run(tmp_path, '''
        from personal_learning_assistant.android_runtime import start
        from personal_learning_assistant.repositories.routed_course_repository import RoutedCourseRepository
        from personal_learning_assistant.domain.canonical_topic_catalogues import canonical_names
        r = start()
        repo = RoutedCourseRepository()
        state = repo.load_state()
        expected = ('MA103N', 'UC100N', 'CY100N', 'DE100N', 'UC103N')
        assert tuple(c['code'] for c in state['courses']) == expected
        for c in state['courses']:
            assert tuple(t['name'] for t in c['topics']) == canonical_names(c['code'])
            assert c['semester'] == 'Semester 1'
        c = r.app.test_client()
        c.set_cookie('anvaya_native', r.token, domain='127.0.0.1')
        for path, values in (
            ('/learning', (b'Linear Algebra', b'Chemistry', b'Indian Knowledge System')),
            ('/courses', (b'MA103N', b'UC100N', b'CY100N')),
            ('/learning/courses/cy100n', (b'Green Chemistry', b'Spectroscopy', b'Lab')),
            ('/mobile/device', (b'Restore missing subject templates',))
        ):
            response = c.get(path, base_url=r.origin)
            assert response.status_code == 200, (path, response.status_code)
            for text in values:
                assert text in response.data, (path, text)

        # Simulate an existing phone with an absent subject and saved progress.
        state['courses'] = [course for course in state['courses'] if course['code'] != 'DE100N']
        math = next(course for course in state['courses'] if course['code'] == 'MA103N')
        math['topics'][0]['status'] = 'mastered'
        math_id = math['id']
        repo.save_state(state)
        response = c.post('/mobile/device/restore-subjects', base_url=r.origin,
                          headers={'Origin': r.origin})
        assert response.status_code == 200, response.data
        assert b'DE100N' in response.data
        after = repo.load_state()
        assert len(after['courses']) == 5
        math_after = next(course for course in after['courses'] if course['code'] == 'MA103N')
        assert math_after['id'] == math_id
        assert math_after['topics'][0]['status'] == 'mastered'
        assert {c['code'] for c in after['courses']} == set(expected)
        response = c.post('/mobile/device/restore-subjects', base_url=r.origin,
                          headers={'Origin': r.origin})
        assert response.status_code == 200
        assert len(repo.load_state()['courses']) == 5
        r.stop()
    ''')
    run(tmp_path, '''
        from personal_learning_assistant.android_runtime import start
        from personal_learning_assistant.repositories.routed_course_repository import RoutedCourseRepository
        r = start()
        state = RoutedCourseRepository().load_state()
        assert len(state['courses']) == 5
        math = next(c for c in state['courses'] if c['code'] == 'MA103N')
        assert math['topics'][0]['status'] == 'mastered'
        r.stop()
    ''')
