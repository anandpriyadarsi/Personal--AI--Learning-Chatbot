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


def test_installed_build_identity_is_visible_in_settings(tmp_path):
    run(tmp_path, '''
        from personal_learning_assistant.android_runtime import launch, start
        sha='a'*40
        launch(None, sha, '1.2.0-unified-debug', 16)
        r=start();c=r.app.test_client()
        c.set_cookie('anvaya_native',r.token,domain='127.0.0.1')
        response=c.get('/mobile/settings',base_url=r.origin)
        assert response.status_code==200
        html=response.get_data(as_text=True)
        assert sha in html and '1.2.0-unified-debug' in html and 'Build 16' in html
        r.stop()
    ''')


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
        # Learn and Assessment must expose the same verified first-year subjects.
        picker = req('/assessments/import?kind=test').read().decode('utf-8')
        assert 'UC103N' in picker and 'MA103N' in picker
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
            assert db.execute("SELECT count(*) FROM courses WHERE code IN ('MA103N','UC100N','CY100N','DE100N','UC103N') AND deleted_at IS NULL").fetchone()[0] == 5
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
        response=c.get('/knowledge/item/'+identity,base_url=r.origin)
        assert response.status_code==200,response.data
        assert b'Open original file' in response.data
        assert b'class="knowledge-reader-chunk"' not in response.data
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


def test_phone_rebuilds_lexical_tutor_index_and_saves_source_only_response(tmp_path):
    run(tmp_path, r'''
        from personal_learning_assistant.android_runtime import start
        from tests.academic_evidence_v23_fixtures import source_pdf
        import urllib.request, urllib.error, urllib.parse, sqlite3
        r = start()
        headers={'Cookie':'anvaya_native='+r.token,'Origin':r.origin}
        def req(path,data=None,extra=None):
            return urllib.request.urlopen(urllib.request.Request(r.origin+path,data=data,headers={**headers,**(extra or {})}))
        boundary='anvaya-synthetic-boundary'
        upload=(b'--'+boundary.encode()+b'\r\nContent-Disposition: form-data; name="source"; filename="study.pdf"\r\nContent-Type: application/pdf\r\n\r\n'+source_pdf()+b'\r\n--'+boundary.encode()+b'--\r\n')
        assert req('/mobile/device/source',upload,{'Content-Type':'multipart/form-data; boundary='+boundary}).status==200
        try:
            req('/mobile/device/tutor-index',b'csrf_token=invalid')
            raise AssertionError('Index rebuild accepted bad CSRF')
        except urllib.error.HTTPError as e: assert e.code==403
        token=r.app.extensions['tutor_action_csrf']
        assert req('/mobile/device/tutor-index',urllib.parse.urlencode({'csrf_token':token}).encode()).status==200
        assert (r.root/'data/tutor_retrieval/current.json').is_file()
        service=r.app.config['ACADEMIC_AGENT_WEB_SERVICE_FACTORY']()
        sid=service.create_session(course_id='',mode='concept',source_policy='source_only')
        body=urllib.parse.urlencode({'csrf_token':token,'request_id':'native-lexical-1','question':'zqxv absent concept'}).encode()
        result=req('/agent/sessions/'+sid+'/ask',body)
        assert result.status==200
        assert len(service.session_view(sid)['turns'])==2
        assert service.session_view(sid)['turns'][-1]['support_level']=='insufficient'
        assert req('/agent/sessions/'+sid).status==200
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


def test_unified_library_source_search_and_saved_reference_survive_restart(tmp_path):
    run(tmp_path, r'''
        from personal_learning_assistant.android_runtime import start
        from tests.academic_evidence_v23_fixtures import source_pdf
        import urllib.request, urllib.parse
        r = start()
        headers={'Cookie':'anvaya_native='+r.token,'Origin':r.origin}
        def req(path,data=None,extra=None):
            return urllib.request.urlopen(urllib.request.Request(r.origin+path,data=data,headers={**headers,**(extra or {})}))
        boundary='anvaya-library-synthetic-boundary'
        upload=(b'--'+boundary.encode()+b'\r\nContent-Disposition: form-data; name="source"; filename="study.pdf"\r\nContent-Type: application/pdf\r\n\r\n'+source_pdf()+b'\r\n--'+boundary.encode()+b'--\r\n')
        assert req('/mobile/device/source',upload,{'Content-Type':'multipart/form-data; boundary='+boundary}).status == 200
        token=r.app.extensions['tutor_action_csrf']
        assert req('/mobile/device/tutor-index',urllib.parse.urlencode({'csrf_token':token}).encode()).status == 200
        search=req('/library?view=search&q=Mean').read().decode()
        assert 'knowledge-result-card' in search and 'Read source' in search
        for path in ('/knowledge?q=Mean', '/resources'):
            assert req(path).status == 200
        body=urllib.parse.urlencode({'return_to':'library','title':'Synthetic persistent reference',
            'resource_type':'website','link':'https://example.invalid/reference'}).encode()
        saved=req('/resources',body)
        assert '/library?view=saved' in saved.url
        page=saved.read().decode()
        assert 'Synthetic persistent reference' in page
        assert req('/resources/1/status',b'return_to=library&status=Completed').status == 200
        r.stop()
    ''')

    run(tmp_path, '''
        from personal_learning_assistant.android_runtime import start
        import urllib.request
        r = start()
        def page(path):
            return urllib.request.urlopen(urllib.request.Request(r.origin+path,
                headers={'Cookie':'anvaya_native='+r.token})).read().decode()
        saved=page('/library?view=saved&saved_status=Completed')
        assert 'Synthetic persistent reference' in saved
        assert 'knowledge-result-card' in page('/library?view=search&q=Mean')
        r.stop()
    ''')


def test_library_search_survives_different_live_request_threads(tmp_path):
    run(tmp_path, r'''
        from personal_learning_assistant.android_runtime import start
        from tests.academic_evidence_v23_fixtures import source_pdf
        from threading import Thread, Event
        import urllib.request, urllib.parse
        r=start()
        headers={'Cookie':'anvaya_native='+r.token,'Origin':r.origin}
        def req(path, data=None, extra=None):
            return urllib.request.urlopen(urllib.request.Request(r.origin+path,data=data,headers={**headers,**(extra or {})}))
        boundary='anvaya-library-thread-fixture'
        upload=(b'--'+boundary.encode()+b'\r\nContent-Disposition: form-data; name="source"; filename="study.pdf"\r\nContent-Type: application/pdf\r\n\r\n'+source_pdf()+b'\r\n--'+boundary.encode()+b'--\r\n')
        assert req('/mobile/device/source',upload,{'Content-Type':'multipart/form-data; boundary='+boundary}).status==200
        assert req('/mobile/device/tutor-index',urllib.parse.urlencode({'csrf_token':r.app.extensions['tutor_action_csrf']}).encode()).status==200
        ready, release=Event(),Event()
        bodies=[]
        def search(hold=False):
            client=r.app.test_client()
            client.set_cookie('anvaya_native',r.token,domain='127.0.0.1')
            bodies.append(client.get('/library?view=search&q=Mean',base_url=r.origin).text)
            if hold:
                ready.set()
                assert release.wait(10)
        first=Thread(target=search,args=(True,));first.start()
        assert ready.wait(10)
        second=Thread(target=search);second.start();second.join(10)
        release.set();first.join(10)
        assert not first.is_alive() and not second.is_alive()
        assert len(bodies)==2 and all('knowledge-result-card' in body for body in bodies)
        r.stop()
    ''')


def test_library_pdf_upload_picker_entrypoint_and_source_integrity(tmp_path):
    """Library owns the mobile PDF entry point; canonical registry owns the data."""
    run(tmp_path, r'''
        from personal_learning_assistant.android_runtime import start
        from tests.academic_evidence_v23_fixtures import source_pdf
        import hashlib, io, sqlite3
        r = start()
        client = r.app.test_client()
        client.set_cookie('anvaya_native', r.token, domain='127.0.0.1')
        def get(path):
            return client.get(path, base_url=r.origin)
        def post(path, data):
            return client.post(path, base_url=r.origin,
                               headers={'Origin': r.origin}, data=data)
        entry=get('/library')
        assert entry.status_code==302 and entry.location.endswith('/library/files')
        html=get('/library/files').get_data(as_text=True)
        assert 'id="import-form"' in html and 'multiple' in html
        assert 'Prepare supported content for Tutor on this device' in html
        for path in ('/library?view=search','/library?view=saved'):
            html=get(path).get_data(as_text=True)
            assert 'action="/library/upload"' not in html
            assert 'Rebuild local text index' not in html
        original = source_pdf()
        token = r.app.extensions['tutor_action_csrf']
        denied = post('/library/upload', {'source': (io.BytesIO(original), 'study.pdf')})
        assert denied.status_code == 403
        wrong_type = post('/library/upload', {
            'csrf_token': token, 'source': (io.BytesIO(original), 'not-a-pdf.zip')})
        assert wrong_type.status_code == 400
        wrong_magic = post('/library/upload', {
            'csrf_token': token, 'source': (io.BytesIO(b'not a pdf'), 'study.pdf')})
        assert wrong_magic.status_code == 400
        with sqlite3.connect(r.root/'data/learning_assistant.db') as con:
            assert con.execute('SELECT count(*) FROM knowledge_documents').fetchone()[0] == 0
        uploaded = post('/library/upload', {
            'csrf_token': token, 'source': (io.BytesIO(original), 'study.pdf')})
        assert uploaded.status_code == 303, uploaded.data
        assert '/library?pdf_status=extracted&source_id=' in uploaded.location
        with sqlite3.connect(r.root/'data/learning_assistant.db') as con:
            doc = con.execute('SELECT id,path_key,content_hash,extraction_status FROM knowledge_documents').fetchone()
            assert doc and doc[0] in uploaded.location
            assert doc[1].startswith('native_library/')
            assert doc[2] == hashlib.sha256(original).hexdigest()
            assert doc[3] == 'completed'
            assert con.execute('SELECT count(*) FROM knowledge_chunks').fetchone()[0] > 0
        from personal_learning_assistant.services.native_document_library import resolve_android_document
        stored=resolve_android_document(r.root,doc[1].split('/',1)[1])
        assert __import__('pathlib').Path(stored[0]).read_bytes()==original
        repeated = post('/library/upload', {
            'csrf_token': token, 'source': (io.BytesIO(original), 'second-name.pdf')})
        assert repeated.status_code == 303
        with sqlite3.connect(r.root/'data/learning_assistant.db') as con:
            assert con.execute('SELECT count(*) FROM knowledge_documents').fetchone()[0] == 1
        indexed = post('/mobile/device/tutor-index', {
            'csrf_token': token, 'return_to': 'library'})
        assert indexed.status_code == 303
        assert indexed.location.endswith('/library?index_status=rebuilt#library-pdf-upload')
        assert (r.root/'data/tutor_retrieval/current.json').is_file()
        r.stop()
    ''')
    run(tmp_path, r'''
        from personal_learning_assistant.android_runtime import start
        import sqlite3
        r = start()
        with sqlite3.connect(r.root/'data/learning_assistant.db') as con:
            assert con.execute('SELECT count(*) FROM knowledge_documents').fetchone()[0] == 1
            assert con.execute('SELECT count(*) FROM knowledge_chunks').fetchone()[0] > 0
        r.stop()
    ''')


def test_media_upload_does_not_hold_dynamic_navigation_lock(tmp_path):
    run(tmp_path, '''
        from personal_learning_assistant.android_runtime import start
        from personal_learning_assistant.services.anvaya_notes_service import AnvayaNotesService
        from personal_learning_assistant.services.notes_media_service import NotesMediaStore
        import io, threading, urllib.request
        r=start()
        note=AnvayaNotesService().create_handwritten_note({'title':'Synthetic streaming note'},[('page.pdf',b'%PDF-1.4')])['id']
        entered=threading.Event(); release=threading.Event()
        original=NotesMediaStore.add
        def slow(self,*args):
            entered.set()
            assert release.wait(5)
            return original(self,*args)
        NotesMediaStore.add=slow
        response=[]
        def upload():
            with r.app.test_client() as c:
                c.set_cookie('anvaya_native',r.token,domain='127.0.0.1')
                result=c.post('/notes/media/'+note,base_url=r.origin,headers={'Origin':r.origin,'X-Notes-CSRF':r.app.extensions['notes_media_csrf']},data={'files':(io.BytesIO(b'ID3'+b'0'*40),'audio.mp3')})
                response.append(result.status_code)
        thread=threading.Thread(target=upload);thread.start()
        assert entered.wait(3)
        try:
            req=urllib.request.Request(r.origin+'/healthz',headers={'Cookie':'anvaya_native='+r.token})
            assert urllib.request.urlopen(req,timeout=2).status==200
        finally:
            release.set();thread.join(5);r.stop()
        assert response==[201],response
    ''')
