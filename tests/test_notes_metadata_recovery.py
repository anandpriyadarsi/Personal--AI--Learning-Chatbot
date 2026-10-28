"""Storage failures during metadata actions stay recoverable and read-only."""
import pytest
from tests.test_phase7_5_15_10_notes_obsidian_separation import _service
from personal_learning_assistant.services.anvaya_notes_service import AnvayaNotesUnavailableError


@pytest.mark.parametrize('action', ['pin', 'rename'])
def test_unreadable_notes_during_metadata_change_preserve_original_failure(tmp_path, action):
    service, repo = _service(tmp_path)
    note = service.create_typed_note({'title':'Preserve me', 'body':'Original'})['id']
    version = repo.get_note(note)['updated_at']
    repo.notes_path.write_text('{interrupted external write', encoding='utf-8')
    before = repo.notes_path.read_bytes()
    with pytest.raises(AnvayaNotesUnavailableError):
        service.change_note(note, action, {'expected_updated_at':version, 'title':'Rename'})
    assert repo.notes_path.read_bytes() == before
