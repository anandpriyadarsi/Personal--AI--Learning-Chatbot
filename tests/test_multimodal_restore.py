"""Stopped synthetic owners only. Restore copies never replace active data."""
from contextlib import closing
from io import BytesIO
import hashlib
import json
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import pytest
from personal_learning_assistant.services import multimodal_schema as schema
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary
from test_multimodal_jobs import image_bytes


def tree_hashes(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def rows(path):
    with closing(sqlite3.connect(Path(path).absolute().as_uri()+'?mode=ro&immutable=1',uri=True)) as con:
        tables=[r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {name:sorted(con.execute('SELECT * FROM "'+name+'"').fetchall(),key=repr) for name in tables}


@pytest.fixture
def stopped_owners(tmp_path):
    root=tmp_path/'owners';root.mkdir();db=root/'academic.db';apply_migrations(db)
    library=NativeDocumentLibrary(root/'native_library',autostart=False)
    doc=library.upload(BytesIO(image_bytes()),'matrix.png',indexing=False)
    library.close()
    (root/'notes').mkdir();(root/'notes'/'note.md').write_text('Retained synthetic note')
    (root/'config.json').write_text('{"synthetic": true}')
    external=tmp_path/'external-vault';external.mkdir();(external/'outside.md').write_text('Separate owner')
    return root,db,root/'native_library',doc,external


def test_preview_uses_read_only_sqlite_and_preserves_bytes_rows(stopped_owners,monkeypatch):
    root,db,native,doc,external=stopped_owners
    before=tree_hashes(root);academic=rows(db);library=rows(native/'library.sqlite3')
    original=schema.sqlite3.connect;opened=[]
    def connect(database,*args,**kwargs):
        opened.append((database,kwargs));return original(database,*args,**kwargs)
    monkeypatch.setattr(schema.sqlite3,'connect',connect)
    value=schema.activate(db,native,apply=False)
    assert value['pending']
    assert opened and all('?mode=ro&immutable=1' in str(path) and options.get('uri') for path,options in opened)
    assert tree_hashes(root)==before
    assert rows(db)==academic and rows(native/'library.sqlite3')==library
    assert not (root/'backups').exists()


def test_preview_refuses_uncheckpointed_wal_without_modifying_bytes(stopped_owners):
    root,db,native,doc,external=stopped_owners
    with closing(sqlite3.connect(db)) as writer:
        writer.execute('CREATE TABLE synthetic_pending_wal(value TEXT)')
        writer.execute("INSERT INTO synthetic_pending_wal VALUES('committed WAL row')")
        writer.commit()
        assert Path(str(db)+'-wal').stat().st_size>0
        before=tree_hashes(root)
        with pytest.raises(ValueError,match='Stop writers and checkpoint'):
            schema.activate(db,native,apply=False)
        assert tree_hashes(root)==before


def test_preview_missing_owner_cannot_create_anything(tmp_path):
    with pytest.raises(ValueError):schema.activate(tmp_path/'missing.db',tmp_path/'native',apply=False)
    assert not list(tmp_path.iterdir())


def test_synthetic_backup_restores_new_root_hashes_rows_and_idempotence(stopped_owners,tmp_path):
    root,db,native,doc,external=stopped_owners
    academic=rows(db);library=rows(native/'library.sqlite3');external_before=tree_hashes(external)
    value=schema.activate(db,native,apply=True);backup=value['backup']
    manifest=json.loads((backup/'checksums.json').read_text())
    assert manifest and all(hashlib.sha256((backup/name).read_bytes()).hexdigest()==digest for name,digest in manifest.items())
    assert not (backup/'external-vault').exists() and tree_hashes(external)==external_before
    restored=tmp_path/'independent-restored-root';restored.mkdir()
    shutil.copy2(backup/'academic.sqlite3',restored/'academic.db')
    shutil.copytree(backup/'native',restored/'native_library')
    shutil.copy2(backup/'library.sqlite3',restored/'native_library'/'library.sqlite3')
    shutil.copytree(backup/'notes',restored/'notes');shutil.copy2(backup/'config.json',restored/'config.json')
    assert rows(restored/'academic.db')==academic
    assert rows(restored/'native_library'/'library.sqlite3')==library
    for path in (restored/'academic.db',restored/'native_library'/'library.sqlite3'):
        with closing(sqlite3.connect(Path(path).absolute().as_uri()+'?mode=ro&immutable=1',uri=True)) as con:assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    clone=NativeDocumentLibrary(restored/'native_library',autostart=False)
    try:assert hashlib.sha256(clone.original(doc['id']).read_bytes()).hexdigest()==doc['sha256']
    finally:clone.close()
    assert (restored/'notes'/'note.md').read_bytes()==(root/'notes'/'note.md').read_bytes()
    assert (restored/'config.json').read_bytes()==(root/'config.json').read_bytes()
    backups=list((root/'backups').iterdir());after=tree_hashes(root)
    assert not schema.activate(db,native,apply=True)['pending']
    assert list((root/'backups').iterdir())==backups and tree_hashes(root)==after
    # Restored pre-activation copy can be activated independently and twice.
    schema.activate(restored/'academic.db',restored/'native_library',apply=True)
    assert not schema.activate(restored/'academic.db',restored/'native_library',apply=True)['pending']


def test_second_owner_failure_rolls_back_both_owners(stopped_owners,monkeypatch):
    root,db,native,doc,external=stopped_owners
    academic=rows(db);library=rows(native/'library.sqlite3');original=schema.sqlite3.connect
    class FailingConnection(sqlite3.Connection):
        def executescript(self,script):
            if 'BEGIN IMMEDIATE;' in script:raise sqlite3.OperationalError('injected second-owner apply failure')
            return super().executescript(script)
    def connect(database,*args,**kwargs):
        if str(database)==str(db):kwargs['factory']=FailingConnection
        return original(database,*args,**kwargs)
    monkeypatch.setattr(schema.sqlite3,'connect',connect)
    with pytest.raises(sqlite3.OperationalError,match='injected second-owner'):
        schema.activate(db,native,apply=True)
    assert rows(db)==academic and rows(native/'library.sqlite3')==library
    assert schema.activate(db,native,apply=False)['pending']
    monkeypatch.setattr(schema.sqlite3,'connect',original)
    assert not schema.activate(db,native,apply=True)['pending']


def test_integrity_historical_migration_and_schema_checksum_unchanged():
    # Fixed baseline approved migration bytes; no history edits to enable Phase 1.5.
    expected='c2318f564a1d519b85c6effc52c4a2a352be2e53c5b4654b8c85149b27e999b3'
    assert hashlib.sha256(schema.CANONICAL_SQL.encode()).hexdigest()==expected
    assert schema.CHECKSUM=='ad996b405780ed9f812e306764aed31e659a97340b204113eabd08905a697fc8'


def test_integrity_offline_guard_denies_external_and_allows_loopback_and_children(tmp_path):
    from scripts.multimodal_validate import offline_environment
    root=Path(__file__).resolve().parents[1];env=offline_environment(root,tmp_path)
    code='''import socket, subprocess, sys
for address in [("example.com",443),("8.8.8.8",443)]:
    try: socket.create_connection(address,timeout=.1)
    except PermissionError: pass
    else: raise AssertionError("outbound connection allowed")
server=socket.socket(); server.bind(("127.0.0.1",0)); server.listen(1)
client=socket.create_connection(server.getsockname(),timeout=1)
accepted,_=server.accept(); accepted.close(); client.close(); server.close()
result=subprocess.run([sys.executable,"-c","import socket; socket.create_connection(('8.8.8.8',443),timeout=.1)"],capture_output=True,text=True,timeout=5)
assert result.returncode!=0 and "Offline validation denies" in result.stderr
print("guard verified")
'''
    result=subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    assert 'guard verified' in result.stdout
