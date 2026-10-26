import io
import pytest
from personal_learning_assistant.repositories.json.anvaya_notes_repository import AnvayaNotesRepository, AnvayaNotesConflictError
from personal_learning_assistant.services.anvaya_notes_service import AnvayaNotesService

@pytest.fixture
def notes(tmp_path):
    repo=AnvayaNotesRepository(notes_path=tmp_path/'notes.json', assets_root=tmp_path/'assets')
    native=AnvayaNotesService(repo)
    note=native.create_typed_note({'title':'English','body':'Legacy body','course':'English'})['id']
    from personal_learning_assistant.services.nested_notes_service import NestedNotesService
    return repo,native,NestedNotesService(repo),note

def mutate(s,repo,note,action,**kw):
    return s.change(note, action, expected_updated_at=repo.get_note(note)['updated_at'], **kw)

def test_legacy_add_edit_duplicate_order_restart(notes):
    repo,native,s,note=notes
    assert s.list(note)['sections'][0]['id']=='original-content'
    a=mutate(s,repo,note,'add',title='Speaking',body='**Practice**')['section_id']
    b=mutate(s,repo,note,'duplicate',section_id=a)['section_id']
    mutate(s,repo,note,'edit',section_id=a,title='Intonation',body='- [ ] Repeat')
    mutate(s,repo,note,'reorder',order=[b,a])
    assert repo.get_note(note)['body']=='Legacy body'
    assert [x['id'] for x in s.list(note)['sections']]==['original-content',b,a]
    assert '<strong>Practice</strong>' in s.read(note,b)['html']
    assert s.read(note,a)['body']=='- [ ] Repeat'
    assert s.__class__(AnvayaNotesRepository(notes_path=repo.notes_path,assets_root=repo.assets_root)).list(note)==s.list(note)
    assert native.library(search='Repeat')['cards'][0]['id']==note

def test_stale_and_invalid_order_leave_unchanged(notes):
    repo,_,s,note=notes
    version=repo.get_note(note)['updated_at']
    a=mutate(s,repo,note,'add',title='A')['section_id']
    before=repo.get_note(note)
    with pytest.raises(AnvayaNotesConflictError): s.change(note,'add',title='Lost',expected_updated_at=version)
    with pytest.raises(ValueError): mutate(s,repo,note,'reorder',order=[a,a])
    assert repo.get_note(note)==before

def test_move_and_delete_preserve_attachments(notes):
    repo,native,s,note=notes
    from personal_learning_assistant.services.notes_media_service import NotesMediaStore
    media=NotesMediaStore(repo)
    a=mutate(s,repo,note,'add',title='A')['section_id']
    asset=media.add(note,[('कक्षा.pdf',io.BytesIO(b'%PDF-1.4\n%%EOF'))],section_id=a)[0]
    dest=native.create_typed_note({'title':'Destination','body':''})['id']
    mutate(s,repo,note,'move',section_id=a,target_note_id=dest,target_updated_at=repo.get_note(dest)['updated_at'])
    assert media.list(note)==[]
    assert media.resolve(dest,asset['id'])['path'].read_bytes()==b'%PDF-1.4\n%%EOF'
    mutate(s,repo,dest,'delete',section_id=a)
    assert media.list(dest)[0]['section_id']==''
    assert repo.get_note(dest)['sections']==[]

@pytest.mark.parametrize('kind',['typed','handwritten'])
def test_universal_files_and_section_binding(tmp_path,kind):
    from personal_learning_assistant.services.notes_media_service import NotesMediaStore
    repo=AnvayaNotesRepository(notes_path=tmp_path/'n.json',assets_root=tmp_path/'a')
    native=AnvayaNotesService(repo)
    note=(native.create_typed_note({'title':'Typed'}) if kind=='typed' else native.create_handwritten_note({'title':'Hand'},[('page.pdf',b'%PDF-1.4\n%%EOF')]))['id']
    store=NotesMediaStore(repo)
    for name,data in [('image.png',b'\x89PNG\r\n\x1a\n'+b'0'*20),('study.pdf',b'%PDF-1.4\n%%EOF'),('notes.txt','Hello हिन्दी'.encode())]:
        item=store.add(note,[(name,io.BytesIO(data))])[0]
        assert store.resolve(note,item['id'])['path'].read_bytes()==data
    with pytest.raises(ValueError): store.add(note,[('other.pdf',io.BytesIO(b'%PDF-1.4\n%%EOF'))],section_id='missing')
    assert len(store.list(note))==3

def test_duplicate_includes_independently_removable_attachments(notes):
    repo,_,s,note=notes
    from personal_learning_assistant.services.notes_media_service import NotesMediaStore
    media=NotesMediaStore(repo)
    a=mutate(s,repo,note,'add',title='A')['section_id']
    asset=media.add(note,[('copy.pdf',io.BytesIO(b'%PDF-1.4\n%%EOF'))],section_id=a)[0]
    b=mutate(s,repo,note,'duplicate',section_id=a)['section_id']
    copies=media.list(note)
    assert len(copies)==2
    copy=next(x for x in copies if x['section_id']==b)
    assert copy['id']!=asset['id']
    media.delete(note,copy['id'])
    assert media.resolve(note,asset['id'])['path'].read_bytes()==b'%PDF-1.4\n%%EOF'

def test_legacy_inline_images_are_not_eagerly_placed_outside_collapsed_content(notes):
    repo,native,s,note=notes
    updated=native.update_note(note,{'title':'English','body':'[[anvaya-upload:0]]','expected_updated_at':repo.get_note(note)['updated_at']},[('image.png',b'\x89PNG\r\n\x1a\n'+b'x'*20)])
    assert native.section_reader(note)['assets']==[]
    assert '<img' in s.read(note,'original-content')['html']

def test_failed_move_rolls_back_files_and_both_notes(notes,monkeypatch):
    repo,native,s,note=notes
    from personal_learning_assistant.services.notes_media_service import NotesMediaStore
    media=NotesMediaStore(repo)
    a=mutate(s,repo,note,'add',title='A')['section_id']
    asset=media.add(note,[('lecture.pdf',io.BytesIO(b'%PDF-1.4\n%%EOF'))],section_id=a)[0]
    destination=native.create_typed_note({'title':'Target'})['id']
    before=repo.list_notes()
    def fail(rows):raise OSError('disk full')
    monkeypatch.setattr(repo,'_save',fail)
    with pytest.raises(OSError):mutate(s,repo,note,'move',section_id=a,target_note_id=destination,target_updated_at=repo.get_note(destination)['updated_at'])
    assert repo.list_notes()==before
    assert media.resolve(note,asset['id'])['path'].exists()
    assert not list((repo.assets_root/destination/'media').glob('*'))

def test_deleting_section_during_upload_rejects_commit_and_cleans_staging(notes):
    repo,_,s,note=notes
    from personal_learning_assistant.services.notes_media_service import NotesMediaStore
    media=NotesMediaStore(repo);a=mutate(s,repo,note,'add',title='A')['section_id']
    class DeleteDuringRead(io.BytesIO):
        fired=False
        def read(self,size=-1):
            if not self.fired:
                self.fired=True;mutate(s,repo,note,'delete',section_id=a)
            return super().read(size)
    with pytest.raises(ValueError):media.add(note,[('deleted.pdf',DeleteDuringRead(b'%PDF-1.4\n%%EOF'))],section_id=a)
    assert media.list(note)==[]
    assert not list((repo.assets_root/note/'media').glob('*'))

def test_duplicate_legacy_inline_image_survives_original_asset_removal(notes):
    repo,native,s,note=notes
    native.update_note(note,{'title':'English','body':'[[anvaya-upload:0]]','expected_updated_at':repo.get_note(note)['updated_at']},[('image.png',b'\x89PNG\r\n\x1a\n'+b'x'*20)])
    original=repo.get_note(note)['assets'][0]['id']
    copy=mutate(s,repo,note,'duplicate',section_id='original-content')['section_id']
    assert len(repo.get_note(note)['assets'])==2
    native.update_note(note,{'title':'English','body':repo.get_note(note)['body'],'expected_updated_at':repo.get_note(note)['updated_at'],'remove_asset_ids':[original]})
    html=s.read(note,copy)['html']
    assert '<img' in html and 'Image unavailable' not in html
    assert original not in html
    assert native.section_reader(note)['assets']==[]

def test_duplicate_inline_asset_save_failure_rolls_back_new_file(notes,monkeypatch):
    repo,native,s,note=notes
    native.update_note(note,{'title':'English','body':'[[anvaya-upload:0]]','expected_updated_at':repo.get_note(note)['updated_at']},[('image.png',b'\x89PNG\r\n\x1a\n'+b'x'*20)])
    before=repo.get_note(note);files=set((repo.assets_root/note).iterdir())
    def fail(rows):raise OSError('disk full')
    monkeypatch.setattr(repo,'_save',fail)
    with pytest.raises(OSError):mutate(s,repo,note,'duplicate',section_id='original-content')
    assert repo.get_note(note)==before
    assert set((repo.assets_root/note).iterdir())==files
