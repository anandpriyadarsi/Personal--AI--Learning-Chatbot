"""Production phone runtime, offline source identity and actual process restart."""
from tests.test_android_runtime import run


def test_library_name_survives_phone_runtime_restart_without_source_changes(tmp_path):
    run(tmp_path,r'''
        import io,json,sqlite3
        from tests.learning_studio.helpers import source_pdf
        from personal_learning_assistant.android_runtime import start
        r=start();c=r.app.test_client()
        c.set_cookie('anvaya_native',r.token,domain='127.0.0.1')
        raw=source_pdf()
        uploaded=c.post('/library/upload',base_url=r.origin,headers={'Origin':r.origin},
            data={'csrf_token':r.app.extensions['tutor_action_csrf'],
                  'source':(io.BytesIO(raw),'original.pdf')})
        assert uploaded.status_code==303,uploaded.data
        with sqlite3.connect(r.root/'data/learning_assistant.db') as con:
            document=con.execute('SELECT id,path_key,content_hash FROM knowledge_documents').fetchone()
        from personal_learning_assistant.ui.web.routes import _learning_library_service
        import time
        from personal_learning_assistant.repositories.sqlite.learning_library_repository import LibraryNotFoundError
        deadline=time.monotonic()+5
        while True:
            try:
                with r.app.app_context():
                    original=_learning_library_service().repository.original_title('document',document[0])
                break
            except LibraryNotFoundError:
                assert time.monotonic()<deadline, 'owner snapshot did not publish uploaded source'
                time.sleep(.01)
        headers={'Origin':r.origin,'X-Library-CSRF':r.app.extensions['library_rename_csrf']}
        result=c.post('/library/items/document/'+document[0]+'/rename',base_url=r.origin,headers=headers,
            json={'title':'Offline friendly name','expected_title':original})
        assert result.status_code==200,result.data
        assert (r.root/'data'/document[1]).read_bytes()==raw
        (r.root/'delivery-identity.json').write_text(json.dumps(document))
        r.stop()
    ''')
    run(tmp_path,r'''
        import json,sqlite3
        from personal_learning_assistant.android_runtime import start
        r=start();c=r.app.test_client()
        c.set_cookie('anvaya_native',r.token,domain='127.0.0.1')
        document=json.loads((r.root/'delivery-identity.json').read_text())
        page=c.get('/library?q=Offline',base_url=r.origin)
        assert page.status_code==200,page.data
        assert b'Offline friendly name' in page.data
        with sqlite3.connect(r.root/'data/learning_assistant.db') as con:
            assert list(con.execute('SELECT id,path_key,content_hash FROM knowledge_documents').fetchone())==document
        from personal_learning_assistant.android_backup import export_backup
        from zipfile import ZipFile
        import io
        assert 'data/learning_assistant.db.display.sqlite3' in ZipFile(io.BytesIO(export_backup(r.root))).namelist()
        r.stop()
    ''')
