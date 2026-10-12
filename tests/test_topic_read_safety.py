"""B2 desired read safety on disposable paths and exported synthetic source."""
import ast
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from scripts.architecture_validation import export_source
from tests.test_phase4_structured_authority_routing import _prepare_project, _seed, _promote
from tests.test_topic_evidence_repository import read, inventory
from tests.test_assessment_studio_phase_e import _database

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def exported(tmp_path_factory):
    path = tmp_path_factory.mktemp('b2-export') / 'source'
    export_source(ROOT, path)
    return path


def route_probe(exported, route, state):
    # Reuse the production characterization child, including its write/network audit.
    script = ast.parse((ROOT/'scripts/characterization/read_routes.py').read_text())
    child = next(ast.literal_eval(n.value) for n in script.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'child' for t in n.targets))
    # Each child receives a separate full exported source to keep actual defaults isolated.
    import tempfile, shutil
    with tempfile.TemporaryDirectory(prefix='b2-route-') as directory:
        source = Path(directory)/'source'
        shutil.copytree(exported, source)
        setup = """
if sys.argv[2] in ('valid','corrupt','corrupt-course','canonical'):
 (root/'data').mkdir(exist_ok=True)
 (root/'data/courses.json').write_text(json.dumps({'version':1,'active_course_id':'ma103n','courses':[{'id':'ma103n','code':'MA103N','name':'Linear Algebra','status':'active','topics':[{'id':'rank','name':'Matrix Rank','status':'weak','confidence':1}]}],'document_links':{}}))
 if sys.argv[2]=='valid':
  (root/'data/learning_memory.json').write_text('{"version": 1, "weak_topics": [" Matrix   Rank "]}  \\n')
 if sys.argv[2]=='corrupt':
  (root/'data/learning_memory.json').write_text('{invalid')
 if sys.argv[2]=='corrupt-course':
  (root/'data/courses.json').write_text('{invalid')
 if sys.argv[2]=='canonical':
  import sqlite3
  from contextlib import closing
  from tests.test_phase4_structured_authority_routing import _source_payloads,_seed,_promote,_seed_relational_core,_control_path
  from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
  from personal_learning_assistant.repositories.sqlite.compatibility_repository import SQLiteCompatibilityProjectionRepository
  for name,payload in _source_payloads().items():(root/'data'/name).write_text(json.dumps(payload))
  apply_migrations(root/'data/learning_assistant.db')
  with closing(sqlite3.connect(root/'data/learning_assistant.db',isolation_level=None)) as c:
   _seed(c,root,root/'data');_promote(root)
   _seed_relational_core(SQLiteCompatibilityProjectionRepository(c,authority_control_path=_control_path(root)),_source_payloads())
  (root/'data/learning_memory.json').unlink()
"""
        child = child.replace('writes=[];network=[]',setup+'\nwrites=[];network=[]')
        sql_audit = """
import sqlite3
from contextlib import closing
sql_writes=[]
connect=sqlite3.connect
def logical_dump():
 path=root/'data/learning_assistant.db'
 if not path.exists():return None
 with closing(connect(path.as_uri()+'?mode=ro',uri=True)) as c:return tuple(c.iterdump())
before_sql=logical_dump()
write_actions={getattr(sqlite3,n) for n in ('SQLITE_INSERT','SQLITE_UPDATE','SQLITE_DELETE','SQLITE_CREATE_TABLE','SQLITE_CREATE_INDEX','SQLITE_CREATE_TRIGGER','SQLITE_CREATE_VIEW','SQLITE_DROP_TABLE','SQLITE_DROP_INDEX','SQLITE_DROP_TRIGGER','SQLITE_DROP_VIEW','SQLITE_ALTER_TABLE')}
def tracked(*args,**kwargs):
 c=connect(*args,**kwargs)
 def audit_sql(action,arg1,arg2,db,trigger):
  if action in write_actions:sql_writes.append([action,arg1,arg2])
  return sqlite3.SQLITE_OK
 c.set_authorizer(audit_sql)
 return c
sqlite3.connect=tracked
"""
        child = child.replace('before=hashes()',sql_audit+'\nbefore=hashes()')
        child = child.replace("'network_attempts':network", "'network_attempts':network,'sql_write_attempts':sql_writes,'sql_unchanged':before_sql==logical_dump()")
        # Repeat real requests; capture the existing safe degraded template model.
        child = child.replace('with app.test_client() as client:r=client.get(route)',
                              "with app.test_client() as client:\n for _ in range(3):r=client.get(route)")
        r = subprocess.run([sys.executable,'-c',child,route,state],cwd=source,text=True,capture_output=True,
                           env={**__import__('os').environ,'PYTHONDONTWRITEBYTECODE':'1'},timeout=60)
        assert r.returncode == 0,r.stderr
        return json.loads(r.stdout),r.stderr


@pytest.mark.parametrize('route',['/planning','/analysis'])
@pytest.mark.parametrize('state',['empty','seeded','valid','corrupt','corrupt-course','canonical'])
def test_get_missing_legacy_files_does_not_create_files(exported,route,state):
    result,errors=route_probe(exported,route,state)
    assert result['status']==200
    # Normal live ro readers may create empty SQLite WAL/SHM files. B1's
    # closed immutable path separately requires exact inventory invariance.
    sidecars={'data/learning_assistant.db-wal','data/learning_assistant.db-shm'} if state=='canonical' else set()
    assert set(result['created']) <= sidecars and result['changed']==[]
    assert result['writes']==[] and result['network_attempts']==[]
    assert result['sql_write_attempts']==[] and result['sql_unchanged']
    if state in ('corrupt','corrupt-course'):
        assert 'unavailable' in errors.lower()


def test_missing_legacy_loads_do_not_initialize(tmp_path,monkeypatch):
    import learning_memory,course_manager
    for module,filevar,name in [(learning_memory,'MEMORY_FILE','learning_memory.json'),(course_manager,'COURSES_FILE','courses.json')]:
        monkeypatch.setattr(module,'DATA_DIR',str(tmp_path/'data'))
        monkeypatch.setattr(module,filevar,str(tmp_path/'data'/name))
    assert learning_memory.load_memory()==learning_memory.default_memory()
    assert course_manager.load_course_data()==course_manager.default_course_data()
    assert inventory(tmp_path)=={}
    assert not (tmp_path/'data').exists()
    # Explicit initialization remains a write command.
    learning_memory.ensure_memory_file()
    assert (tmp_path/'data/learning_memory.json').exists()


@pytest.mark.parametrize('raw',[b'{bad',b'[]',b'\xff'])
def test_corrupt_memory_is_unavailable_without_repair(tmp_path,monkeypatch,raw):
    import learning_memory
    path=tmp_path/'learning_memory.json';path.write_bytes(raw)
    monkeypatch.setattr(learning_memory,'MEMORY_FILE',str(path))
    with pytest.raises(ValueError):learning_memory.load_memory()
    assert path.read_bytes()==raw


def test_promoted_reads_are_query_only_and_preserve_sql(tmp_path,monkeypatch):
    from personal_learning_assistant.repositories import structured_authority_router as router
    from personal_learning_assistant.repositories.sqlite.compatibility_repository import SQLiteCompatibilityProjectionRepository
    root,data,db,c=_prepare_project(tmp_path)
    try:_seed(c,root,data)
    finally:c.close()
    _promote(root)
    with closing(sqlite3.connect(db)) as c:before_sql=tuple(c.iterdump())
    before=inventory(root)
    original=SQLiteCompatibilityProjectionRepository.load_projection
    def checked(self,name):
        assert self.connection.execute('PRAGMA query_only').fetchone()[0]==1
        with pytest.raises(sqlite3.OperationalError):self.connection.execute('CREATE TABLE forbidden (id)')
        return original(self,name)
    monkeypatch.setattr(SQLiteCompatibilityProjectionRepository,'load_projection',checked)
    for _ in range(3):assert router.maybe_load_sqlite_structured_store('learning_memory',data/'learning_memory.json')['version']==2
    after=inventory(root)
    assert all(after[k]==v for k,v in before.items())
    assert set(after)-set(before) <= {'data/learning_assistant.db-wal','data/learning_assistant.db-shm'}
    with closing(sqlite3.connect(db)) as c:
        assert tuple(c.iterdump())==before_sql
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert c.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_b1_concurrent_closed_reads_preserve_unknowns_and_inventory(tmp_path):
    path=_database(tmp_path);before=inventory(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:bundles=list(pool.map(lambda _:read(path),range(8)))
    assert all(b==bundles[0] for b in bundles)
    assert all(e.mapping.state=='unknown' and e.independence.status=='unknown' and not e.automatic_eligible for e in bundles[0].evidence)
    assert inventory(tmp_path)==before


def test_live_router_sees_committed_wal_without_immutable_reads(tmp_path,monkeypatch):
    from personal_learning_assistant.repositories import structured_authority_router as router
    from personal_learning_assistant.repositories.sqlite.compatibility_repository import PROJECTION_PREFIX
    root,data,db,c=_prepare_project(tmp_path)
    try:
        _seed(c,root,data);_promote(root)
        payload={'version':2,'notes':[{'text':'committed WAL'}]}
        c.execute('UPDATE app_settings SET value_json=? WHERE key=?',(json.dumps(payload),PROJECTION_PREFIX+'learning_memory'))
        assert Path(str(db)+'-wal').exists()
        connect=router.sqlite3.connect
        def checked(filename,*args,**kwargs):
            assert 'mode=ro' in filename and 'immutable' not in filename
            return connect(filename,*args,**kwargs)
        monkeypatch.setattr(router.sqlite3,'connect',checked)
        assert router.maybe_load_sqlite_structured_store('learning_memory',data/'learning_memory.json')==payload
    finally:c.close()


@pytest.mark.parametrize('damage',['missing-db','corrupt-db','corrupt-projection','missing-projection','corrupt-control'])
def test_invalid_promoted_authority_never_falls_back_or_repairs(tmp_path,damage):
    from personal_learning_assistant.repositories import structured_authority_router as router
    from personal_learning_assistant.repositories.sqlite.compatibility_repository import PROJECTION_PREFIX
    root,data,db,c=_prepare_project(tmp_path)
    try:
        _seed(c,root,data)
        # DELETE journal gives a strictly sidecar-free closed synthetic case.
        c.execute('PRAGMA journal_mode=DELETE')
        if damage=='corrupt-projection':c.execute('UPDATE app_settings SET value_json=? WHERE key=?',('{bad',PROJECTION_PREFIX+'learning_memory'))
        if damage=='missing-projection':c.execute('DELETE FROM app_settings WHERE key=?',(PROJECTION_PREFIX+'learning_memory',))
    finally:c.close()
    _promote(root)
    if damage=='missing-db':db.unlink()
    if damage=='corrupt-db':db.write_bytes(b'not a database')
    if damage=='corrupt-control':(root/'.phase4_authority.json').write_text('{bad')
    before=inventory(root)
    with pytest.raises((RuntimeError,sqlite3.DatabaseError)):
        router.maybe_load_sqlite_structured_store('learning_memory',data/'learning_memory.json')
    assert inventory(root)==before


def test_repeated_existing_planner_preview_is_write_free(tmp_path):
    from tests.test_phase7_5_month_plan_import import _db,FIXTURE
    from personal_learning_assistant.services.month_plan_import_service import build_month_plan_import_service
    path=_db(tmp_path)
    with closing(sqlite3.connect(path)) as c:
        c.execute('PRAGMA journal_mode=DELETE')
        before_sql=tuple(c.iterdump())
    before=inventory(tmp_path)
    service=build_month_plan_import_service(path)
    for _ in range(3):assert service.preview(FIXTURE.name,FIXTURE.read_bytes())['valid']
    assert inventory(tmp_path)==before
    with closing(sqlite3.connect(path)) as c:assert tuple(c.iterdump())==before_sql


@pytest.mark.parametrize('reader',['memory','courses','course-repository'])
@pytest.mark.parametrize('raw',[b'{bad',b'[]',b'\xff'])
def test_legacy_corrupt_authority_is_never_normal_empty(tmp_path,monkeypatch,reader,raw):
    import learning_memory,course_manager
    from personal_learning_assistant.repositories.json.course_repository import LegacyJsonCourseRepository
    path=tmp_path/'data'/'source.json';path.parent.mkdir();path.write_bytes(raw)
    if reader=='memory':
        monkeypatch.setattr(learning_memory,'MEMORY_FILE',str(path));load=learning_memory.load_memory
    elif reader=='courses':
        monkeypatch.setattr(course_manager,'COURSES_FILE',str(path));load=course_manager.load_course_data
    else:load=LegacyJsonCourseRepository(path).load_state
    before=inventory(tmp_path)
    with pytest.raises(ValueError):load()
    assert inventory(tmp_path)==before


@pytest.mark.parametrize('reader',['memory','courses','course-repository','promoted'])
def test_symlink_authority_alias_is_rejected(tmp_path,monkeypatch,reader):
    import learning_memory,course_manager
    from personal_learning_assistant.repositories.json.course_repository import LegacyJsonCourseRepository
    from personal_learning_assistant.repositories import structured_authority_router as router
    root,data,db,c=_prepare_project(tmp_path)
    try:_seed(c,root,data)
    finally:c.close()
    _promote(root)
    alias=tmp_path/'alias';alias.symlink_to(root,target_is_directory=True)
    if reader=='memory':
        monkeypatch.setattr(learning_memory,'MEMORY_FILE',str(alias/'data/learning_memory.json'));load=learning_memory.load_memory
    elif reader=='courses':
        monkeypatch.setattr(course_manager,'COURSES_FILE',str(alias/'data/courses.json'));load=course_manager.load_course_data
    elif reader=='course-repository':load=LegacyJsonCourseRepository(alias/'data/courses.json').load_state
    else:load=lambda:router.maybe_load_sqlite_structured_store('learning_memory',alias/'data/learning_memory.json')
    with pytest.raises((ValueError,RuntimeError)):load()


def test_promoted_course_document_links_cannot_follow_store_symlink(tmp_path):
    from personal_learning_assistant.repositories.routed_course_repository import RoutedCourseRepository
    root,data,db,c=_prepare_project(tmp_path)
    try:
        _seed(c,root,data)
        c.execute('PRAGMA journal_mode=DELETE')
    finally:c.close()
    _promote(root)
    outside=tmp_path/'outside.json'
    outside.write_text(json.dumps({'document_links':{'alternate':{'course_id':'different','topic':'external'}}}))
    store=data/'courses.json';store.unlink();store.symlink_to(outside)
    before=inventory(root)
    with pytest.raises(RuntimeError):RoutedCourseRepository(store).load_state()
    assert inventory(root)==before


def test_dangling_authority_control_never_means_legacy(tmp_path):
    from personal_learning_assistant.repositories import structured_authority_router as router
    root=tmp_path/'project';root.mkdir()
    control=root/'.phase4_authority.json';control.symlink_to(root/'absent-control.json')
    with pytest.raises(RuntimeError):
        router.maybe_load_sqlite_structured_store('learning_memory',root/'data/learning_memory.json')
    assert control.is_symlink() and not (root/'data').exists()


def test_route_probe_retains_detected_write_evidence(exported,tmp_path):
    import shutil
    source=tmp_path/'source';shutil.copytree(exported,source)
    service=source/'personal_learning_assistant/services/home_dashboard_service.py'
    text=service.read_text().replace('    brief = import_module("daily_academic_brief")',
         '    from pathlib import Path\n    Path("forbidden-by-get.txt").write_text("synthetic")\n    brief = import_module("daily_academic_brief")')
    service.write_text(text)
    output=tmp_path/'failure.json'
    result=subprocess.run([sys.executable,str(ROOT/'scripts/characterization/read_routes.py'),'--repo',str(source),'--output',str(output)],capture_output=True,text=True,timeout=60)
    assert result.returncode != 0
    assert output.exists(), 'Detected write evidence was lost before the assertion'
    rows=json.loads(output.read_text())
    assert any('forbidden-by-get.txt' in row['created'] for row in rows)
    assert 'forbidden-by-get.txt' in result.stdout


def test_route_probe_is_stable_with_git_auto_maintenance(exported,tmp_path):
    import os
    output=tmp_path/'routes.json'
    # Exercise real post-commit Git maintenance, not a mocked file write.
    environment={**os.environ,'GIT_CONFIG_COUNT':'1','GIT_CONFIG_KEY_0':'gc.auto','GIT_CONFIG_VALUE_0':'1'}
    result=subprocess.run([sys.executable,str(ROOT/'scripts/characterization/read_routes.py'),'--repo',str(exported),'--output',str(output)],capture_output=True,text=True,timeout=90,env=environment)
    assert result.returncode==0,result.stdout+result.stderr
    rows=json.loads(output.read_text())
    assert all(not r['created'] and not r['changed'] and not r['writes'] for r in rows)
