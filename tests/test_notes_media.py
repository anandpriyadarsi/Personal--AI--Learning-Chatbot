"""Synthetic media only: ownership, bounded I/O, persistence and HTTP contracts."""
import io
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from personal_learning_assistant.repositories.json.anvaya_notes_repository import AnvayaNotesRepository
from personal_learning_assistant.services.anvaya_notes_service import AnvayaNotesService

SAMPLES = {
    'mp3': b'ID3\x04\x00\x00\x00\x00\x00\x00' + b'\x00' * 40,
    'wav': b'RIFF\x30\x00\x00\x00WAVEfmt ' + b'\x00' * 40,
    'm4a': b'\x00\x00\x00\x18ftypM4A ' + b'\x00' * 44,
    'aac': b'\xff\xf1\x50\x80\x00\x1f\xfc' + b'\x00' * 48,
    'mp4': b'\x00\x00\x00\x18ftypisom' + b'\x00' * 44,
    'mkv': b'\x1a\x45\xdf\xa3' + b'\x00' * 8 + b'matroska' + b'\x00' * 40,
    'mov': b'\x00\x00\x00\x18ftypqt  ' + b'\x00' * 44,
    'webm': b'\x1a\x45\xdf\xa3' + b'\x00' * 8 + b'webm' + b'\x00' * 40,
}
MIMES = ['audio/mpeg', 'audio/wav', 'audio/mp4', 'audio/aac', 'video/mp4', 'video/x-matroska', 'video/quicktime', 'video/webm']

@pytest.fixture
def setup(tmp_path):
    repo = AnvayaNotesRepository(notes_path=tmp_path/'notes.json', assets_root=tmp_path/'assets')
    service = AnvayaNotesService(repo)
    note = service.create_handwritten_note({'title':'Spectroscopy','course':'CY100N'}, [('page.pdf',b'%PDF-1.4\n%%EOF')])['id']
    return repo, service, note

def store(repo):
    from personal_learning_assistant.services.notes_media_service import NotesMediaStore
    return NotesMediaStore(repo)

@pytest.mark.parametrize('ext,mime', list(zip(SAMPLES, MIMES)))
def test_format_upload_stream_and_restart(setup, ext, mime):
    repo, service, note = setup
    item = store(repo).add(note, [(f'Lecture.{ext}', io.BytesIO(SAMPLES[ext]))])[0]
    assert item['mimetype'] == mime
    restarted = AnvayaNotesRepository(notes_path=repo.notes_path, assets_root=repo.assets_root)
    assert store(restarted).list(note) == [item]
    resolved = store(restarted).resolve(note, item['id'])
    assert resolved['path'].read_bytes() == SAMPLES[ext]
    assert 'path' not in item and 'stored_name' not in item and 'sha256' not in item
    assert len(service.reader(note)['assets']) == 1

def test_multiple_rename_delete_preserves_pages_and_fields(setup):
    repo, service, note = setup
    media = store(repo)
    first, second = media.add(note, [('one.mp3',io.BytesIO(SAMPLES['mp3'])),('two.mp4',io.BytesIO(SAMPLES['mp4']))])
    before = repo.get_note(note)
    media.rename(note, first['id'], 'Teacher Explanation')
    renamed = media.list(note)[0]
    assert renamed['filename'] == 'Teacher Explanation.mp3'
    media.delete(note, first['id'])
    assert media.list(note) == [second]
    after = repo.get_note(note)
    for key in ('title','course','body','assets','created_at'):
        assert after.get(key) == before.get(key)
    assert not list((repo.assets_root/note/'media').glob('*.mp3'))

def test_repeat_parallel_taps_deduplicate(setup):
    repo, _, note = setup
    def add(_): return store(repo).add(note, [('lecture.mp4', io.BytesIO(SAMPLES['mp4']))])[0]['id']
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(add,range(4)))
    assert len(set(ids)) == 1
    assert len(store(repo).list(note)) == 1
    assert len(list((repo.assets_root/note/'media').glob('*.mp4'))) == 1

def test_stream_is_bounded_and_failed_batch_is_atomic(setup, monkeypatch):
    from personal_learning_assistant.services import notes_media_service as module
    repo, _, note = setup
    class Bounded(io.BytesIO):
        def read(self, size=-1):
            assert 0 < size <= 65536
            return super().read(size)
    media = store(repo)
    media.add(note,[('valid.mp3',Bounded(SAMPLES['mp3']))])
    with pytest.raises(module.AnvayaNotesValidationError):
        media.add(note,[('valid.mp4',Bounded(SAMPLES['mp4'])),('bad.mp3',io.BytesIO(b'<script>invalid</script>'))])
    assert len(media.list(note)) == 1
    assert not list((repo.assets_root/note/'media').glob('*.mp4'))
    monkeypatch.setattr(module,'MAX_MEDIA_BYTES',32)
    with pytest.raises(module.AnvayaNotesValidationError):
        media.add(note,[('big.mp4',io.BytesIO(SAMPLES['mp4']))])

@pytest.mark.parametrize('name',['../secret.mp3','wrong.wav','bad\r\n.mp3','', 'folder/name.mp3'])
def test_rename_rejects_unsafe_or_changed_extension(setup,name):
    from personal_learning_assistant.services.notes_media_service import AnvayaNotesValidationError
    repo, _, note = setup
    media = store(repo)
    item = media.add(note,[('ok.mp3',io.BytesIO(SAMPLES['mp3']))])[0]
    with pytest.raises(AnvayaNotesValidationError): media.rename(note,item['id'],name)
    assert media.list(note)[0]['filename']=='ok.mp3'

def test_integrity_missing_and_symlink_fail_closed(setup,tmp_path):
    from personal_learning_assistant.services.notes_media_service import AnvayaNotesUnavailableError
    from personal_learning_assistant.repositories.json.anvaya_notes_repository import AnvayaNotesNotFoundError
    repo, _, note = setup
    media = store(repo)
    item=media.add(note,[('ok.mp3',io.BytesIO(SAMPLES['mp3']))])[0]
    path=media.resolve(note,item['id'])['path']
    path.write_bytes(b'X'*len(SAMPLES['mp3']))
    with pytest.raises(AnvayaNotesUnavailableError): media.resolve(note,item['id'])
    path.unlink()
    with pytest.raises(AnvayaNotesNotFoundError): media.resolve(note,item['id'])
    private=tmp_path/'secret'; private.write_bytes(SAMPLES['mp3'])
    path.symlink_to(private)
    with pytest.raises(AnvayaNotesNotFoundError): media.resolve(note,item['id'])

def test_json_failure_rolls_back_and_delete_rename_are_atomic(setup,monkeypatch):
    from personal_learning_assistant.services.notes_media_service import AnvayaNotesUnavailableError
    from personal_learning_assistant.repositories.json.anvaya_notes_repository import AnvayaNotesRepositoryError
    repo, _, note=setup
    media=store(repo)
    item=media.add(note,[('ok.mp3',io.BytesIO(SAMPLES['mp3']))])[0]
    original=repo.notes_path.read_bytes()
    def fail(_): raise AnvayaNotesRepositoryError('synthetic disk failure')
    monkeypatch.setattr(repo,'_save',fail)
    for operation in (lambda:media.add(note,[('ok.mp4',io.BytesIO(SAMPLES['mp4']))]),lambda:media.delete(note,item['id']),lambda:media.rename(note,item['id'],'new')):
        with pytest.raises(AnvayaNotesUnavailableError): operation()
        assert repo.notes_path.read_bytes()==original
    assert media.resolve(note,item['id'])['path'].exists()
    assert not list((repo.assets_root/note/'media').glob('*.mp4'))

def test_http_lazy_list_csrf_upload_download_and_note_ownership(setup):
    from personal_learning_assistant.ui.web import create_app
    repo, service, note=setup
    app=create_app({'TESTING':True,'ANVAYA_NOTES_SERVICE_FACTORY':lambda:service})
    client=app.test_client()
    root=f'/notes/media/{note}'
    result=client.get(root)
    assert result.status_code==200
    assert result.json=={'attachments':[]}
    assert client.post(root,data={'files':(io.BytesIO(SAMPLES['mp3']),'audio.mp3')}).status_code==403
    token=app.extensions['notes_media_csrf']
    result=client.post(root,data={'files':[(io.BytesIO(SAMPLES['mp3']),'audio.mp3'),(io.BytesIO(SAMPLES['mp4']),'video.mp4')]},headers={'X-Notes-CSRF':token})
    assert result.status_code==201
    item=result.json['attachments'][0]
    download=client.get(item['url'])
    assert download.data==SAMPLES['mp3']
    assert download.mimetype=='audio/mpeg'
    assert download.headers['Content-Disposition'].startswith('attachment;')
    assert download.headers['Cache-Control']=='no-store'
    download.close()
    with client.get(item['url'],headers={'Range':'bytes=0-9'}) as partial:
        assert partial.status_code==206
        assert partial.data==SAMPLES['mp3'][:10]
    assert client.get(f"/notes/media/unknown/{item['id']}/open").status_code==404
    assert client.post(f"{root}/{item['id']}/rename",json={'filename':'Teacher'},headers={'X-Notes-CSRF':token}).status_code==200
    assert client.post(f"{root}/{item['id']}/delete",headers={'X-Notes-CSRF':token}).status_code==200
    assert len(client.get(root).json['attachments'])==1
    assert len(repo.get_note(note)['assets'])==1

@pytest.mark.parametrize('damage',['missing','corrupt'])
def test_reattach_original_repairs_damaged_duplicate(setup,damage):
    repo,_,note=setup
    media=store(repo)
    item=media.add(note,[('Teacher.mp3',io.BytesIO(SAMPLES['mp3']))])[0]
    path=media.resolve(note,item['id'])['path']
    if damage=='missing': path.unlink()
    else: path.write_bytes(b'broken')
    repaired=media.add(note,[('original.mp3',io.BytesIO(SAMPLES['mp3']))])[0]
    assert repaired['id']==item['id']
    assert len(media.list(note))==1
    assert media.resolve(note,item['id'])['path'].read_bytes()==SAMPLES['mp3']


def test_repair_rollback_restores_corrupt_original_on_metadata_failure(setup,monkeypatch):
    from personal_learning_assistant.services.notes_media_service import AnvayaNotesUnavailableError
    from personal_learning_assistant.repositories.json.anvaya_notes_repository import AnvayaNotesRepositoryError
    repo,_,note=setup
    media=store(repo)
    item=media.add(note,[('Teacher.mp3',io.BytesIO(SAMPLES['mp3']))])[0]
    path=media.resolve(note,item['id'])['path'];path.write_bytes(b'broken')
    def fail(_): raise AnvayaNotesRepositoryError('disk failure')
    monkeypatch.setattr(repo,'_save',fail)
    with pytest.raises(AnvayaNotesUnavailableError): media.add(note,[('original.mp3',io.BytesIO(SAMPLES['mp3']))])
    assert path.read_bytes()==b'broken'


def test_slow_stream_does_not_hold_notes_write_lock(setup):
    from threading import Event
    repo,service,note=setup
    media=store(repo)
    existing=media.add(note,[('ok.mp3',io.BytesIO(SAMPLES['mp3']))])[0]
    entered,release=Event(),Event()
    class Slow(io.BytesIO):
        def read(self,size=-1):
            if not entered.is_set():
                entered.set(); assert release.wait(5)
            return super().read(size)
    with ThreadPoolExecutor(max_workers=2) as pool:
        upload=pool.submit(media.add,note,[('video.mp4',Slow(SAMPLES['mp4']))])
        assert entered.wait(2)
        rename=pool.submit(media.rename,note,existing['id'],'Renamed')
        try:
            assert rename.result(timeout=1)['filename']=='Renamed.mp3'
        finally: release.set()
        upload.result(timeout=3)
    assert [item['filename'] for item in media.list(note)]==['Renamed.mp3','video.mp4']
