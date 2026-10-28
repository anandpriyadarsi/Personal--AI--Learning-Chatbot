"""Notes lifecycle remains additive and versioned in the personal JSON store."""
import pytest
from tests.test_phase7_5_15_10_notes_obsidian_separation import _service, _app
from personal_learning_assistant.repositories.json.anvaya_notes_repository import AnvayaNotesConflictError


def test_pin_keeps_existing_order_within_groups_and_metadata(tmp_path):
    service, repo = _service(tmp_path)
    ids = [service.create_typed_note({'title': title, 'body': '**Original**'})['id'] for title in ('First', 'Second', 'Third')]
    row = repo.get_note(ids[0]); row['custom_metadata'] = {'retain': True}; row['sections'] = [{'id': 's1', 'title': 'Section', 'body': 'Content'}]
    repo.update_note(ids[0], expected_updated_at=row['updated_at'], changes=row)
    before = repo.get_note(ids[0])
    result = service.change_note(ids[0], 'pin', {'expected_updated_at': before['updated_at']})
    assert result['pinned'] is True
    assert service.library()['cards'][0]['id'] == ids[0]
    assert [x['id'] for x in service.library(pinned='1')['cards']] == [ids[0]]
    after = repo.get_note(ids[0])
    assert after['custom_metadata'] == before['custom_metadata']
    assert after['sections'] == before['sections']
    assert after['body'] == before['body']
    assert after['created_at'] == before['created_at']
    with pytest.raises(AnvayaNotesConflictError):
        service.change_note(ids[0], 'rename', {'expected_updated_at': before['updated_at'], 'title': 'Stale'})


def test_lifecycle_preserves_files_and_supports_archive_restore_and_trash(tmp_path):
    service, repo = _service(tmp_path)
    note = service.create_handwritten_note({'title': 'Pages'}, [('page.pdf', b'%PDF-1.4\n%%EOF')])['id']
    before = repo.get_note(note)
    def change(action, **values):
        return service.change_note(note, action, {'expected_updated_at': repo.get_note(note)['updated_at'], **values})
    change('rename', title='New name'); change('course', course='MA103N'); change('archive')
    assert service.library()['cards'] == []
    assert service.library(view='archived')['cards'][0]['title'] == 'New name'
    change('restore'); assert service.library()['cards'][0]['course'] == 'MA103N'
    change('delete'); assert service.library()['cards'] == []
    assert service.library(view='deleted')['cards'][0]['id'] == note
    assert repo.read_asset(note, before['assets'][0]['id'])['bytes'] == b'%PDF-1.4\n%%EOF'
    change('restore'); assert service.library()['cards'][0]['id'] == note


def test_note_actions_require_csrf_and_reject_stale_or_invalid_mutations(tmp_path):
    service, repo = _service(tmp_path); app = _app(service); c = app.test_client()
    note = service.create_typed_note({'title': 'Protected', 'body': 'Keep this'})['id']
    base = f'/notes/action/{note}'
    data = {'action': 'pin', 'expected_updated_at': repo.get_note(note)['updated_at']}
    assert c.post(base, json=data).status_code == 403
    headers = {'X-Notes-CSRF': app.extensions['notes_media_csrf']}
    result = c.post(base, json=data, headers=headers)
    assert result.status_code == 200 and result.json['pinned']
    assert c.post(base, json=data, headers=headers).status_code == 409
    for values in ({'action': 'rename', 'title': ''}, {'action': 'unknown'}, {'action': 'pin'}):
        if values['action'] != 'pin': values['expected_updated_at'] = repo.get_note(note)['updated_at']
        assert c.post(base, json=values, headers=headers).status_code == 400


def test_compact_library_and_reader_keep_authoring_actions_accessible(tmp_path):
    service, repo = _service(tmp_path); c = _app(service).test_client()
    note = service.create_typed_note({'title': 'Visible main', 'body': 'Main reading content'})['id']
    page = c.get('/notes').text
    assert 'data-notes-layout' in page and 'notes-create-menu' in page
    for label in ('Text Note', 'Handwritten Note', 'Checklist', 'Image Note', 'Audio Note', 'Import Document'):
        assert label in page
    reader = c.get(f'/notes/view/{note}').text
    assert 'notes-reader-menu' in reader
    for label in ('Edit Note', 'Rename', 'Pin', 'Move to Course', 'Add Section', 'Manage Sections', 'Manage Attachments', 'Focus Reading', 'Archive', 'Delete'):
        assert label in reader


@pytest.mark.parametrize(('kind', 'filename', 'raw'), [('audio','Lecture.mp3',b'ID3'+b'x'*50),('image','Diagram.png',b'\x89PNG\r\n\x1a\n'+b'x'*50),('document','Reading.txt',b'Keep my original document')])
def test_capture_creates_personal_note_with_original_media(tmp_path, kind, filename, raw):
    import io
    service, repo = _service(tmp_path); app = _app(service); c = app.test_client()
    url = f'/notes/create/media/{kind}'
    assert c.get(url).status_code == 200
    assert c.post(url, data={'title':'Capture', 'files':(io.BytesIO(raw), filename)}).status_code == 403
    response = c.post(url, data={'title':'Capture', 'course':'CS101', 'csrf_token':app.extensions['notes_media_csrf'], 'files':(io.BytesIO(raw),filename)})
    assert response.status_code == 303
    row = repo.list_notes()[0]
    assert row['title'] == 'Capture' and row['course'] == 'CS101'
    assert row['media'][0]['filename'] == filename
    path = repo.assets_root / row['id'] / 'media' / row['media'][0]['stored_name']
    assert path.read_bytes() == raw


def test_capture_invalid_media_does_not_leave_an_empty_library_note(tmp_path):
    import io
    service, repo = _service(tmp_path); app = _app(service); c = app.test_client()
    result = c.post('/notes/create/media/audio',data={'title':'Bad audio','csrf_token':app.extensions['notes_media_csrf'],'files':(io.BytesIO(b'fake mp3'),'bad.mp3')})
    assert result.status_code == 400
    assert repo.list_notes() == []


def test_library_preview_uses_existing_body_without_rewriting_record(tmp_path):
    service, repo = _service(tmp_path)
    note = service.create_typed_note({'title':'Preview','body':'## Main idea\n\nRemember **this** topic.'})['id']
    before = repo.get_note(note)
    assert 'Remember' in service.library()['cards'][0]['preview']
    assert repo.get_note(note) == before


def test_capture_storage_failure_returns_retryable_response_without_new_record(tmp_path, monkeypatch):
    import io
    from personal_learning_assistant.repositories.json.anvaya_notes_repository import AnvayaNotesRepositoryError
    service, repo = _service(tmp_path); app = _app(service)
    def unavailable(*args, **kwargs):
        raise AnvayaNotesRepositoryError('Disk unavailable')
    monkeypatch.setattr(repo, 'create_note', unavailable)
    result = app.test_client().post('/notes/create/media/audio',data={'title':'Lecture','csrf_token':app.extensions['notes_media_csrf'],'files':(io.BytesIO(b'ID3'+b'x'*40),'lecture.mp3')})
    assert result.status_code == 503
    assert repo.list_notes() == []


def test_capture_attachment_failure_rolls_back_new_note_and_keeps_existing_data(tmp_path, monkeypatch):
    import io
    from personal_learning_assistant.services.notes_media_service import NotesMediaStore
    from personal_learning_assistant.services.anvaya_notes_service import AnvayaNotesUnavailableError
    service, repo = _service(tmp_path)
    service.create_typed_note({'title':'Keep me', 'body':'Existing note'})
    before = repo.list_notes()
    def unavailable(*args, **kwargs):
        raise AnvayaNotesUnavailableError('Media disk unavailable')
    monkeypatch.setattr(NotesMediaStore, '_commit_add', unavailable)
    with pytest.raises(AnvayaNotesUnavailableError):
        service.create_media_note({'title':'Failed capture'}, [('audio.mp3',io.BytesIO(b'ID3'+b'x'*40))], capture_kind='audio')
    assert repo.list_notes() == before
    assert not list(repo.assets_root.rglob('*.mp3'))
