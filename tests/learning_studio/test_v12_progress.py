import copy,json,sqlite3
import pytest
from .helpers import catalogue,package,source_pdf
from .test_service import publish,event
from personal_learning_assistant.learning_studio.service import LearningStudioService,canonical
from personal_learning_assistant.learning_studio.store import APPLICATION_ID,DDL
from personal_learning_assistant.learning_studio.validation import PackageError


def service(tmp_path):
    return LearningStudioService(tmp_path/'learning_studio.sqlite3',source_loader=lambda _:source_pdf(),catalogue_loader=catalogue)


def populated_v1(tmp_path):
    s=service(tmp_path);p=package();raw=source_pdf()
    with sqlite3.connect(s.store.path) as c:
        c.executescript(DDL+f'PRAGMA application_id={APPLICATION_ID}; PRAGMA user_version=1;')
        from hashlib import sha256
        c.execute('INSERT INTO modules VALUES(?,?,?,?,?,?,?,?,?,?)',('synthetic',1,sha256(canonical(p).encode()).hexdigest(),p['title'],p['unit'],None,None,canonical(p),raw,'2026-01-01T00:00:00Z'))
        c.execute('INSERT INTO publications VALUES(?,?,?)',('synthetic',1,'2026-01-01T00:00:00Z'))
        c.execute('INSERT INTO active_modules VALUES(?,?)',('synthetic',1))
        c.execute('INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(1,'old-wrong','local-owner','synthetic',1,p['source']['sha256'],'q1',1,0,0,1,'2026-01-01T00:00:00Z'))
    return s,p


def test_populated_v1_migrates_only_on_write_preserving_every_old_row(tmp_path):
    s,p=populated_v1(tmp_path);before=s.store.path.read_bytes()
    assert hasattr(s,'record_progress'),'Durable reading progress is not implemented'
    assert s.reading_state('synthetic',1)['current'] is None
    assert s.module('synthetic',1)['questions'][0]['id']=='q1'
    assert s.store.path.read_bytes()==before
    with sqlite3.connect(s.store.path) as c:old={t:c.execute('SELECT * FROM '+t).fetchall() for t in ('modules','assets','publications','active_modules','attempts')}
    s.record_progress('synthetic',1,{'event_id':'read-1','section_id':'lesson-1','view':'learn','completed':True,'text_size':20})
    with sqlite3.connect(s.store.path) as c:
        assert c.execute('PRAGMA user_version').fetchone()[0]==2
        assert old=={t:c.execute('SELECT * FROM '+t).fetchall() for t in old}
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not c.execute('PRAGMA foreign_key_check').fetchall()
    backups=list(tmp_path.glob('learning_studio.sqlite3.v1-backup-*.sqlite3'))
    assert len(backups)==1
    with sqlite3.connect(backups[0]) as c:assert c.execute('PRAGMA user_version').fetchone()[0]==1
    assert s.attempt('synthetic',event(p,'new-correct',1))['correct'] is True
    assert s.weak('synthetic',1)[0]['status']=='recovered_needs_recheck'


def test_progress_idempotent_restart_and_prior_revision_is_explicit(tmp_path):
    s=service(tmp_path);p=publish(s)
    assert hasattr(s,'record_progress'),'Durable reading progress is not implemented'
    payload={'event_id':'read-1','section_id':'lesson-1','view':'practice','question_id':'q1','practice_mode':'recheck','completed':False}
    first=s.record_progress('synthetic',1,payload)
    assert s.record_progress('synthetic',1,payload)==first
    altered=dict(payload,view='learn')
    with pytest.raises(PackageError):s.record_progress('synthetic',1,altered)
    reopened=service(tmp_path);assert reopened.reading_state('synthetic',1)['current']['question_id']=='q1'
    newer=copy.deepcopy(p);newer['module_revision']=2;publish(s,newer)
    state=s.reading_state('synthetic',2)
    assert state['current'] is None and state['prior_revision']==1
    assert s.evidence()['attempts']==0


def test_forged_progress_and_engagement_cannot_change_accuracy(tmp_path):
    s=service(tmp_path);p=publish(s)
    assert hasattr(s,'record_progress'),'Progress write boundary is not implemented'
    for extra in ({'owner':'other'},{'is_correct':True},{'timestamp':'2020'},{'section_id':'unknown'},{'question_id':'unknown'},{'text_size':999}):
        payload={'event_id':'bad','section_id':'lesson-1','view':'learn',**extra}
        with pytest.raises(PackageError):s.record_progress('synthetic',1,payload)
    s.record_engagement('synthetic',1,{'event_id':'reflect-1','section_id':'lesson-1','block_index':1,'response':'I compared the cases','action':'reflection'})
    assert s.evidence()['attempts']==0 and s.export()['events']==[]


def test_foreign_feature_named_db_and_future_version_refused_without_writes(tmp_path):
    s=service(tmp_path)
    with sqlite3.connect(s.store.path) as c:c.execute('CREATE TABLE official_grades(x)')
    before=s.store.path.read_bytes()
    with pytest.raises(PackageError):s.stage(package())
    assert s.store.path.read_bytes()==before


def test_concurrent_first_writes_migrate_once(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    s,p=populated_v1(tmp_path)
    def write(i):
        return service(tmp_path).record_progress('synthetic',1,{'event_id':f'concurrent-{i}','section_id':'lesson-1','view':'learn'})
    with ThreadPoolExecutor(max_workers=8) as workers:
        assert len(list(workers.map(write,range(8))))==8
    assert len(list(tmp_path.glob('learning_studio.sqlite3.v1-backup-*.sqlite3')))==1


def test_future_database_version_refused_read_write_without_backup(tmp_path):
    s,p=populated_v1(tmp_path)
    with sqlite3.connect(s.store.path) as c:c.execute('PRAGMA user_version=3')
    before=s.store.path.read_bytes()
    with pytest.raises(PackageError):s.module('synthetic',1)
    with pytest.raises(PackageError):s.stage(p)
    assert before==s.store.path.read_bytes() and not list(tmp_path.glob('*backup*'))


def test_failed_migration_rolls_back_and_can_retry(tmp_path,monkeypatch):
    from personal_learning_assistant.learning_studio import store
    s,p=populated_v1(tmp_path);original=store.execute_ddl
    def fail(con,script):
        con.execute('CREATE TABLE reading_events(x)')
        raise RuntimeError('simulated migration failure')
    monkeypatch.setattr(store,'execute_ddl',fail)
    with pytest.raises(RuntimeError):s.record_progress('synthetic',1,{'event_id':'r1','section_id':'lesson-1','view':'learn'})
    with sqlite3.connect(s.store.path) as c:
        assert c.execute('PRAGMA user_version').fetchone()[0]==1
        assert not c.execute("SELECT name FROM sqlite_master WHERE name='reading_events'").fetchall()
        assert c.execute('SELECT count(*) FROM attempts').fetchone()[0]==1
    monkeypatch.setattr(store,'execute_ddl',original)
    assert s.record_progress('synthetic',1,{'event_id':'r1','section_id':'lesson-1','view':'learn'})['ungraded']


def test_completion_is_explicit_and_survives_bookmark_only_event(tmp_path):
    s=service(tmp_path);publish(s)
    s.record_progress('synthetic',1,{'event_id':'done','section_id':'lesson-1','view':'learn','completed':True})
    s.record_progress('synthetic',1,{'event_id':'bookmark','section_id':'lesson-1','view':'practice'})
    assert s.reading_state('synthetic',1)['completed_sections']==['lesson-1']
    assert s.evidence()['attempts']==0


def test_source_page_and_revision_budget_bookmarks_are_exact(tmp_path):
    s=service(tmp_path);publish(s)
    s.record_progress('synthetic',1,{'event_id':'page-2','section_id':'lesson-1','view':'source','page':2,'budget':'15'})
    assert s.reading_state('synthetic',1)['current']['page']==2
    assert s.reading_state('synthetic',1)['current']['budget']=='15'
    with pytest.raises(PackageError):s.record_progress('synthetic',1,{'event_id':'badpage','section_id':'lesson-1','view':'source','page':999})


def test_engagement_reopen_is_bounded_ungraded_and_rejects_private_fields(tmp_path):
    s=service(tmp_path);publish(s)
    payload={'event_id':'engagement-1','section_id':'lesson-1','block_index':1,'response':'My comparison','action':'reflection'}
    s.record_engagement('synthetic',1,payload)
    assert service(tmp_path).engagement_state('synthetic',1,'lesson-1')[0]['response']=='My comparison'
    assert s.evidence()['attempts']==0
    with pytest.raises(PackageError):s.record_engagement('synthetic',1,dict(payload,correct=True))


def test_revision_card_self_report_has_module_wide_scope(tmp_path):
    s=service(tmp_path);p=package();p['sections'].append(dict(copy.deepcopy(p['sections'][0]),id='lesson-2'))
    p['revision'].append({'kind':'recall','pages':[1],'text':'Recall contrast','answer':'Authored answer'});publish(s,p)
    s.record_engagement('synthetic',1,{'event_id':'recall','section_id':'lesson-1','block_index':1,'block_scope':'revision','response':'revisit','action':'remembered'})
    assert s.engagement_state('synthetic',1,'lesson-2')[0]['response']=='revisit'
