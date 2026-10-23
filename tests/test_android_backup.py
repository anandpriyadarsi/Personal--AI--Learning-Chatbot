import hashlib
import io
import json
import sqlite3
import zipfile
import pytest


def test_backup_restore_integrity_and_existing_data_kept(tmp_path):
    from personal_learning_assistant.android_backup import export_backup, stage_restore, apply_pending_restore
    source = tmp_path/'source'; (source/'data').mkdir(parents=True)
    (source/'data/notes.json').write_text('[{"synthetic":"offline"}]')
    from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
    apply_migrations(source/'data/learning_assistant.db')
    with sqlite3.connect(source/'data/learning_assistant.db') as db:
        db.execute('CREATE TABLE saved(id TEXT)'); db.execute("INSERT INTO saved VALUES('synthetic')")
    raw = export_backup(source)
    dest = tmp_path/'dest'; (dest/'data').mkdir(parents=True)
    (dest/'data/old.txt').write_text('must survive as recovery copy')
    stage_restore(dest, raw)
    assert (dest/'data/old.txt').exists()
    apply_pending_restore(dest)
    assert (dest/'data/notes.json').read_bytes() == (source/'data/notes.json').read_bytes()
    with sqlite3.connect(dest/'data/learning_assistant.db') as db:
        assert db.execute('SELECT id FROM saved').fetchone()[0]=='synthetic'
    assert list(dest.glob('data-before-restore-*/old.txt'))


@pytest.mark.parametrize('name',['../escape','data/../../escape','/data/escape','data\\escape','code.py'])
def test_restore_refuses_traversal_and_non_data_paths(tmp_path,name):
    from personal_learning_assistant.android_backup import stage_restore
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        z.writestr(name,b'x')
        z.writestr('manifest.json',json.dumps({'format':'anvaya.android-backup.v1','files':{name:hashlib.sha256(b'x').hexdigest()}}))
    with pytest.raises(ValueError):stage_restore(tmp_path,out.getvalue())
    assert not (tmp_path/'restore-pending.zip').exists()


def test_restore_refuses_tampering_and_symlink_export(tmp_path):
    from personal_learning_assistant.android_backup import stage_restore,export_backup
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        z.writestr('data/notes.json',b'tampered')
        z.writestr('manifest.json',json.dumps({'format':'anvaya.android-backup.v1','files':{'data/notes.json':'0'*64}}))
    with pytest.raises(ValueError):stage_restore(tmp_path,out.getvalue())
    (tmp_path/'data').mkdir()
    (tmp_path/'secret.txt').write_text('synthetic')
    (tmp_path/'data/link').symlink_to(tmp_path/'secret.txt')
    with pytest.raises(ValueError):export_backup(tmp_path)


def test_restore_rejects_incompatible_schema_before_replacing_current_data(tmp_path):
    from personal_learning_assistant.android_backup import export_backup,stage_restore
    source=tmp_path/'source';(source/'data').mkdir(parents=True)
    with sqlite3.connect(source/'data/learning_assistant.db') as db:
        db.execute('CREATE TABLE schema_migrations(name TEXT)')
    raw=export_backup(source)
    dest=tmp_path/'dest';(dest/'data').mkdir(parents=True)
    (dest/'data/notes.json').write_text('original synthetic notes')
    with pytest.raises(ValueError):stage_restore(dest,raw)
    assert (dest/'data/notes.json').read_text()=='original synthetic notes'
    assert not (dest/'restore-pending.zip').exists()
