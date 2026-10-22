"""Exact, read-only Library/Knowledge bridge over disposable canonical owners."""
from contextlib import closing
import copy
import hashlib
import sqlite3
from pathlib import Path
import pytest
from tests.academic_evidence_v23_fixtures import uc_owners
from tests.test_academic_evidence_v23 import NOW
from personal_learning_assistant.learning_studio.validation import PackageError


def registered(owners, *, did=None, digest=None):
    db, studio, package = owners
    did = did or package['source']['source_id']
    digest = digest or package['source']['sha256']
    with closing(sqlite3.connect(db)) as con, con:
        con.execute('INSERT INTO knowledge_documents(id,kind,path_key,mime_type,content_hash,extraction_status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',
                    (did,'pdf','synthetic/'+did+'.pdf','application/pdf',digest,'completed',NOW.isoformat(),NOW.isoformat()))
    return did,digest


def bridge(owners, **paths):
    from personal_learning_assistant.services.academic_evidence_service import AcademicEvidenceService
    from personal_learning_assistant.services.learning_source_links_v24 import LearningSourceLinksV24
    db, studio, _ = owners
    return LearningSourceLinksV24(AcademicEvidenceService(db,studio=studio,now=lambda:NOW),
        library_database_path=paths.get('library',db),knowledge_database_path=paths.get('knowledge',db),
        learning_database_path=paths.get('learning',studio.store.path))


def inventory(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def test_exact_source_links_use_active_published_owner_without_writes(uc_owners,tmp_path):
    did,digest=registered(uc_owners)
    before=inventory(tmp_path)
    view=bridge(uc_owners).project(did,digest)
    assert view['schema']=='anvaya.learning-source-links.v1'
    assert view['state']=='available' and not view['has_more']
    assert view['blocked_matches']==0
    assert view['lessons'][0]['lesson_url']=='/learning/modules/uc100n-demo/1?view=learn'
    assert view['lessons'][0]['evidence_url']=='/academic-evidence/learning/uc100n-demo/1'
    assert inventory(tmp_path)==before


def test_exact_id_prevents_same_hash_from_linking_another_document(uc_owners):
    _,digest=registered(uc_owners)
    did,_=registered(uc_owners,did='another-document')
    assert bridge(uc_owners).project(did,digest)['lessons']==[]


def test_unknown_document_and_stale_registry_hash_fail_closed(uc_owners):
    did,digest=registered(uc_owners)
    for target,sha,status in [('missing',digest,404),(did,'b'*64,409)]:
        with pytest.raises(PackageError) as error:bridge(uc_owners).project(target,sha)
        assert error.value.status==status


def test_stale_mapping_blocks_lesson_instead_of_trusting_saved_topic(uc_owners):
    did,digest=registered(uc_owners)
    with closing(sqlite3.connect(uc_owners[0])) as con,con:
        con.execute("UPDATE topics SET name='Renamed topic' WHERE id='v23-data'")
    view=bridge(uc_owners).project(did,digest)
    assert view['lessons']==[] and view['blocked_matches']==1


def test_archived_only_document_is_hidden_but_active_relation_restores_visibility(uc_owners):
    did,digest=registered(uc_owners)
    with closing(sqlite3.connect(uc_owners[0])) as con,con:
        con.execute('INSERT INTO resources(id,resource_type,title,status,created_at,updated_at,archived_at) VALUES (?,?,?,?,?,?,?)',
            ('hidden','pdf','Hidden','in_progress',NOW.isoformat(),NOW.isoformat(),NOW.isoformat()))
        con.execute("INSERT INTO resource_documents VALUES (?,?, 'source')",('hidden',did))
    with pytest.raises(PackageError) as error:bridge(uc_owners).project(did,digest)
    assert error.value.status==404
    with closing(sqlite3.connect(uc_owners[0])) as con,con:
        con.execute("UPDATE resources SET archived_at=NULL WHERE id='hidden'")
    assert len(bridge(uc_owners).project(did,digest)['lessons'])==1


def test_colliding_document_ids_in_another_database_do_not_cross_namespace(uc_owners,tmp_path):
    did,digest=registered(uc_owners)
    other=tmp_path/'other.db';other.write_bytes(Path(uc_owners[0]).read_bytes())
    for paths in [{'library':other},{'knowledge':other},{'learning':tmp_path/'foreign'/'learning_studio.sqlite3'}]:
        with pytest.raises(PackageError) as error:bridge(uc_owners,**paths).project(did,digest)
        assert error.value.status==503


def test_source_with_no_lesson_is_valid_empty(uc_owners):
    did,digest=registered(uc_owners,did='source-without-lesson')
    result=bridge(uc_owners).project(did,digest)
    assert result['state']=='empty' and result['lessons']==[]


def test_pagination_is_stable_bounded_and_counts_only_valid_lessons(uc_owners):
    did,digest=registered(uc_owners)
    studio=uc_owners[1]
    for number in range(3):
        p=copy.deepcopy(uc_owners[2]);p['module_id']='uc-extra-'+str(number)
        assets={'assets/cases.png':studio.asset('uc100n-demo',1,'assets/cases.png')}
        studio.stage(p,assets);studio.publish(p['module_id'],1)
    first=bridge(uc_owners).project(did,digest,limit=2)
    second=bridge(uc_owners).project(did,digest,offset=2,limit=2)
    assert first['has_more'] and not second['has_more']
    assert len({r['module_id'] for r in first['lessons']+second['lessons']})==4
    assert bridge(uc_owners).project(did,digest,offset=1000)['lessons']==[]
    for offset,limit in [(-1,1),(1001,1),(0,0),(0,21),(True,1)]:
        with pytest.raises(PackageError):bridge(uc_owners).project(did,digest,offset=offset,limit=limit)


def application(owners, **config):
    from personal_learning_assistant.ui.web import create_app
    from personal_learning_assistant.ui.web.learning_source_links_v24 import register_learning_source_links_v24
    app=create_app({'TESTING':True,'LEARNING_SOURCE_LINKS_V24_SERVICE_FACTORY':lambda:bridge(owners),
        'ACADEMIC_EVIDENCE_SERVICE_FACTORY':lambda:bridge(owners).evidence,
        'LEARNING_STUDIO_SERVICE_FACTORY':lambda:owners[1],**config})
    if 'learning_source_links_v24' not in app.blueprints:register_learning_source_links_v24(app)
    return app


def test_http_json_html_and_safe_link_helper(uc_owners,tmp_path):
    from personal_learning_assistant.ui.web.learning_source_links_v24 import source_links_target
    did,digest=registered(uc_owners)
    app=application(uc_owners)
    with app.app_context():
        url=source_links_target(did,digest)
        assert url.startswith('/learning/source-links?document_id=')
        assert source_links_target('../private',digest) is None
        assert source_links_target(did,'invalid') is None
    before=inventory(tmp_path);client=app.test_client()
    result=client.get(url+'&format=json')
    assert result.status_code==200 and len(result.json['lessons'])==1
    html=client.get(url)
    assert html.status_code==200 and b'Open lesson' in html.data and b'Review evidence' in html.data
    assert client.get(result.json['lessons'][0]['lesson_url']).status_code==200
    assert client.get(result.json['lessons'][0]['evidence_url']).status_code==200
    assert html.headers['Cache-Control']=='no-store'
    assert b'synthetic/source.pdf' not in html.data
    assert inventory(tmp_path)==before


@pytest.mark.parametrize('query',['','document_id=x&content_hash=x','format=xml','offset=-1','offset=1001','limit=21',
    'offset=0&offset=1','format=json&format=json','other=1'])
def test_http_rejects_missing_or_unsupported_query(uc_owners,query):
    did,digest=registered(uc_owners)
    base=f'/learning/source-links?document_id={did}&content_hash={digest}'
    url='/learning/source-links' if not query else base+'&'+query
    assert application(uc_owners).test_client().get(url).status_code==400


@pytest.mark.parametrize('flag',['ACADEMIC_EVIDENCE_ENABLED','LEARNING_LIBRARY_ENABLED','LEARNING_SOURCE_LINKS_V24_ENABLED'])
def test_disabled_feature_never_reads_owners_or_advertises_link(uc_owners,flag):
    from personal_learning_assistant.ui.web.learning_source_links_v24 import source_links_target
    def forbidden():raise AssertionError('Disabled bridge opened an owner')
    app=application(uc_owners,**{flag:False,'LEARNING_SOURCE_LINKS_V24_SERVICE_FACTORY':forbidden})
    with app.app_context():assert source_links_target('doc','a'*64) is None
    assert app.test_client().get('/learning/source-links?document_id=doc&content_hash='+'a'*64).status_code==404


def test_http_refuses_all_write_methods(uc_owners):
    client=application(uc_owners).test_client()
    for method in ['post','put','patch','delete']:
        assert getattr(client,method)('/learning/source-links').status_code==405


def test_inactive_historical_publication_does_not_leak_source_links(uc_owners):
    did,digest=registered(uc_owners)
    with closing(sqlite3.connect(uc_owners[1].store.path)) as con,con:
        con.execute("DELETE FROM active_modules WHERE module_id='uc100n-demo'")
    result=bridge(uc_owners).project(did,digest)
    assert result['lessons']==[] and result['blocked_matches']==0


def test_corrupted_published_source_bytes_are_not_linked(uc_owners):
    did,digest=registered(uc_owners)
    with closing(sqlite3.connect(uc_owners[1].store.path)) as con,con:
        con.execute('DROP TRIGGER immutable_modules_update')
        con.execute("UPDATE modules SET source_blob=? WHERE module_id='uc100n-demo'",(b'%PDF-corrupt',))
    result=bridge(uc_owners).project(did,digest)
    assert result['lessons']==[] and result['blocked_matches']==1


def test_source_registry_revision_changed_does_not_link_old_published_snapshot(uc_owners):
    did,digest=registered(uc_owners)
    with closing(sqlite3.connect(uc_owners[0])) as con,con:
        con.execute('UPDATE knowledge_documents SET content_hash=? WHERE id=?',('b'*64,did))
    result=bridge(uc_owners).project(did,'b'*64)
    assert result['lessons']==[]
    with pytest.raises(PackageError) as error:bridge(uc_owners).project(did,digest)
    assert error.value.status==409


def test_one_registry_snapshot_and_one_learning_capture(uc_owners,monkeypatch):
    from contextlib import contextmanager
    from personal_learning_assistant.repositories.sqlite.learning_library_repository import LearningLibraryRepository
    did,digest=registered(uc_owners);owner=bridge(uc_owners)
    actual=LearningLibraryRepository._capture_delete_source
    captures=[]
    def capture(self,path):
        captures.append(Path(path).resolve())
        return actual(self,path)
    monkeypatch.setattr(LearningLibraryRepository,'_capture_delete_source',capture)
    assert len(owner.project(did,digest)['lessons'])==1
    assert captures==[Path(uc_owners[0]).resolve(),uc_owners[1].store.path.resolve()]


def test_learning_candidate_inventory_is_bounded(uc_owners):
    did,digest=registered(uc_owners)
    with closing(sqlite3.connect(uc_owners[1].store.path)) as con,con:
        for number in range(1000):
            module_id='bound-'+str(number)
            con.execute("INSERT INTO modules SELECT ?,revision,digest,title,unit,course_id,topic_name,package_json,source_blob,created_at FROM modules WHERE module_id='uc100n-demo'",(module_id,))
            con.execute('INSERT INTO publications VALUES (?,1,?)',(module_id,NOW.isoformat()))
            con.execute('INSERT INTO active_modules VALUES (?,1)',(module_id,))
    with pytest.raises(PackageError) as error:bridge(uc_owners).project(did,digest)
    assert error.value.status==503


def test_default_web_service_reuses_existing_owners_and_validates_actual_learning_namespace(uc_owners,tmp_path):
    from types import SimpleNamespace
    from personal_learning_assistant.ui.web import create_app
    from personal_learning_assistant.ui.web.learning_source_links_v24 import register_learning_source_links_v24
    from personal_learning_assistant.services.learning_library_service import LearningLibraryService
    from personal_learning_assistant.learning_studio.service import LearningStudioService
    did,digest=registered(uc_owners)
    app=create_app({'TESTING':True,'ACADEMIC_EVIDENCE_SERVICE_FACTORY':lambda:bridge(uc_owners).evidence,
        'LEARNING_STUDIO_SERVICE_FACTORY':lambda:uc_owners[1],
        'LEARNING_LIBRARY_SERVICE_FACTORY':lambda:LearningLibraryService(database_path=uc_owners[0]),
        'KNOWLEDGE_READER_SERVICE_FACTORY':lambda:SimpleNamespace(database_path=uc_owners[0])})
    if 'learning_source_links_v24' not in app.blueprints:register_learning_source_links_v24(app)
    url=f'/learning/source-links?document_id={did}&content_hash={digest}&format=json'
    assert app.test_client().get(url).status_code==200
    foreign=LearningStudioService(tmp_path/'foreign'/'learning_studio.sqlite3',source_loader=lambda _:None,catalogue_loader=lambda:{})
    app.config['LEARNING_STUDIO_SERVICE_FACTORY']=lambda:foreign
    assert app.test_client().get(url).status_code==503


def test_live_wal_is_refused_without_checkpointing_or_inventory_changes(uc_owners,tmp_path):
    did,digest=registered(uc_owners)
    with closing(sqlite3.connect(uc_owners[0])) as writer:
        assert writer.execute('PRAGMA journal_mode=WAL').fetchone()[0]=='wal'
        writer.execute("UPDATE topics SET name=name WHERE id='v23-data'");writer.commit()
        before=inventory(tmp_path)
        with pytest.raises(PackageError) as error:bridge(uc_owners).project(did,digest)
        assert error.value.status==503
        assert inventory(tmp_path)==before


def test_non_pdf_registry_source_never_links_even_when_ids_and_hashes_match(uc_owners):
    did,digest=registered(uc_owners)
    with closing(sqlite3.connect(uc_owners[0])) as con,con:
        con.execute('UPDATE knowledge_documents SET mime_type=? WHERE id=?',('text/plain',did))
    with pytest.raises(PackageError) as error:bridge(uc_owners).project(did,digest)
    assert error.value.status==404
