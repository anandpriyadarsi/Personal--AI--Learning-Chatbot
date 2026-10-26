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


def test_explicit_records_only_backup_preserves_academics_with_large_media(tmp_path):
    import json
    from personal_learning_assistant.android_backup import export_backup, _checked
    data=tmp_path/'data';media=data/'anvaya_notes_assets/note/media'
    media.mkdir(parents=True)
    blob=media/'lecture.mp4'
    with blob.open('wb') as out: out.truncate(101*1024*1024)
    (data/'anvaya_notes_assets/note/page.pdf').write_bytes(b'%PDF-1.4 synthetic')
    notes=[{'id':'note','title':'Chemistry','note_kind':'handwritten','assets':[{'id':'page'}],
            'media':[{'id':'lecture','size':blob.stat().st_size}]}]
    path=data/'anvaya_notes.json';path.write_text(json.dumps(notes))
    (data/'academic.json').write_text('{"progress":42}')
    raw=export_backup(tmp_path,include_media=False)
    files=_checked(raw)
    assert files['data/academic.json']==b'{"progress":42}'
    assert json.loads(files['data/anvaya_notes.json'])[0]['media']==[]
    assert json.loads(path.read_text())==notes
    assert blob.exists()
    assert not any('/media/' in key for key in files)
    assert files['data/anvaya_notes_assets/note/page.pdf']==b'%PDF-1.4 synthetic'


def test_backup_keeps_attachment_metadata_and_bytes_in_one_snapshot(tmp_path, monkeypatch):
    from pathlib import Path
    from threading import Event, Thread, current_thread
    from personal_learning_assistant.android_backup import export_backup, _checked
    from personal_learning_assistant.repositories.json.anvaya_notes_repository import AnvayaNotesRepository
    from personal_learning_assistant.services.anvaya_notes_service import AnvayaNotesService
    from personal_learning_assistant.services.notes_media_service import NotesMediaStore
    from tests.test_notes_media import SAMPLES
    repo=AnvayaNotesRepository(notes_path=tmp_path/'data/anvaya_notes.json',assets_root=tmp_path/'data/anvaya_notes_assets')
    note=AnvayaNotesService(repo).create_typed_note({'title':'Synthetic backup','body':'Keep attachments'})
    media=NotesMediaStore(repo)
    media.add(note['id'],[('recording.mp3',io.BytesIO(SAMPLES['mp3']))])
    item=repo.get_note(note['id'])['media'][0]
    relative='data/anvaya_notes_assets/'+note['id']+'/media/'+item['stored_name']
    reading=Event();attempted=Event();finished=Event();main=current_thread()
    original=Path.read_bytes
    def read(path):
        result=original(path)
        if path==repo.notes_path and current_thread() is main:
            reading.set();assert attempted.wait(5)
            finished.wait(0.2)
        return result
    def delete():
        assert reading.wait(5);attempted.set()
        media.delete(note['id'],item['id']);finished.set()
    monkeypatch.setattr(Path,'read_bytes',read)
    worker=Thread(target=delete);worker.start()
    try:
        files=_checked(export_backup(tmp_path))
    finally:
        worker.join(5)
    assert not worker.is_alive()
    assert json.loads(files['data/anvaya_notes.json'])[0]['media'][0]['id']==item['id']
    assert files[relative]==SAMPLES['mp3']
