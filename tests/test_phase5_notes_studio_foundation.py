from __future__ import annotations
import sqlite3
from pathlib import Path
import pytest
from personal_learning_assistant.domain.notes_studio_models import CreateNoteRequest,UpdateNoteRequest
from personal_learning_assistant.repositories.filesystem.markdown_note_store import AtomicMarkdownNoteStore,MarkdownConflictError,safe_filename
from personal_learning_assistant.repositories.sqlite.knowledge_registry_repository import SQLiteKnowledgeRegistryRepository
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
from personal_learning_assistant.repositories.sqlite.notes_studio_repository import SQLiteNotesStudioRepository
from personal_learning_assistant.services.notes_studio_service import NotesStudioService
from personal_learning_assistant.services.legacy_note_reconciliation import preview_legacy_notes

NOW='2026-09-16T12:00:00Z'
def _env(tmp_path):
    vault=tmp_path/'Vault'; vault.mkdir(); db=tmp_path/'db.sqlite'; apply_migrations(db); c=sqlite3.connect(str(db),isolation_level=None); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON')
    c.execute("INSERT INTO vaults(id,name,root_path,path_key,enabled,last_scanned_at,created_at,updated_at) VALUES ('v1','Vault',?,'vault',1,NULL,?,?)",(str(vault),NOW,NOW))
    ns=SQLiteNotesStudioRepository(c); kr=SQLiteKnowledgeRegistryRepository(c); svc=NotesStudioService(vault_id='v1',store=AtomicMarkdownNoteStore(vault),notes=ns,journal_repository=kr,now=lambda:NOW)
    return vault,c,ns,kr,svc

def test_safe_filename_windows_rules():
    assert safe_filename('CON')=='CON-note.md'; assert safe_filename('A:B? C').endswith('.md'); assert ':' not in safe_filename('A:B')

def test_create_writes_one_markdown_and_metadata_with_stable_id(tmp_path):
    vault,c,repo,kr,svc=_env(tmp_path); view=svc.create_note(CreateNoteRequest(title='LU Factorization',body='Body',tags=('linear-algebra',),note_type='concept',confidence=3,revision_status='needs_practice'))
    p=vault/view.relative_path; text=p.read_text(encoding='utf-8'); assert f'assistant_id: {view.id}' in text; assert text.endswith('Body'); assert repo.get(view.id).tags==('linear-algebra',); assert kr.list_open_journal_entries()==(); assert len(kr.list_pending_outbox())==1; c.close()

def test_create_collision_gets_readable_suffix(tmp_path):
    vault,c,repo,kr,svc=_env(tmp_path); a=svc.create_note(CreateNoteRequest(title='Same')); b=svc.create_note(CreateNoteRequest(title='Same')); assert a.relative_path!=b.relative_path; assert '(2)' in b.relative_path; c.close()

def test_update_requires_expected_hash_and_preserves_id(tmp_path):
    vault,c,repo,kr,svc=_env(tmp_path); v=svc.create_note(CreateNoteRequest(title='A',body='old')); updated=svc.update_note(UpdateNoteRequest(v.id,v.source_hash,body='new',title='A2')); assert updated.id==v.id; assert 'new' in (vault/updated.relative_path).read_text(encoding='utf-8'); c.close()

def test_external_edit_blocks_update_without_overwrite(tmp_path):
    vault,c,repo,kr,svc=_env(tmp_path); v=svc.create_note(CreateNoteRequest(title='A',body='old')); p=vault/v.relative_path; p.write_text(p.read_text(encoding='utf-8')+'external',encoding='utf-8'); before=p.read_bytes();
    with pytest.raises(MarkdownConflictError): svc.update_note(UpdateNoteRequest(v.id,v.source_hash,body='mine'))
    assert p.read_bytes()==before; c.close()

def test_pin_and_archive_are_metadata_only(tmp_path):
    vault,c,repo,kr,svc=_env(tmp_path); v=svc.create_note(CreateNoteRequest(title='A',body='body')); p=vault/v.relative_path; before=p.read_bytes(); assert svc.pin(v.id).pinned_at==NOW; assert svc.archive(v.id).archived_at==NOW; assert p.read_bytes()==before; c.close()

def test_trash_and_restore_move_same_bytes(tmp_path):
    vault,c,repo,kr,svc=_env(tmp_path); v=svc.create_note(CreateNoteRequest(title='A',body='body')); before=(vault/v.relative_path).read_bytes(); t=svc.trash(v.id); assert t.trashed_at==NOW; assert (vault/t.relative_path).read_bytes()==before; r=svc.restore(v.id,'01 INBOX/Restored.md'); assert r.trashed_at is None; assert (vault/'01 INBOX/Restored.md').read_bytes()==before; c.close()

def test_journal_records_failure_after_file_applied_when_database_fails(tmp_path,monkeypatch):
    vault,c,repo,kr,svc=_env(tmp_path)
    def boom(**kwargs): raise RuntimeError('db failure')
    monkeypatch.setattr(repo,'insert_note',boom)
    with pytest.raises(RuntimeError): svc.create_note(CreateNoteRequest(title='A',body='body'))
    rows=c.execute("SELECT state FROM operation_journal ORDER BY created_at,id").fetchall(); assert rows[-1][0]=='failed'; assert len(list(vault.rglob('*.md')))==1; c.close()

def test_legacy_reconciliation_is_preview_only(tmp_path):
    vault,c,repo,kr,svc=_env(tmp_path); v=svc.create_note(CreateNoteRequest(title='Existing',body='Body')); legacy=tmp_path/'notes.json'; legacy.write_text('[{"title":"Existing","content":"Body"},{"title":"New","content":"X"}]',encoding='utf-8'); raw=legacy.read_bytes(); decisions=preview_legacy_notes(legacy,repo.list_active('v1')); assert decisions[0].decision=='needs_review'; assert decisions[1].decision=='create_markdown'; assert legacy.read_bytes()==raw; c.close()

def test_integrity_and_foreign_keys_after_commands(tmp_path):
    vault,c,repo,kr,svc=_env(tmp_path); svc.create_note(CreateNoteRequest(title='A')); assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; assert c.execute('PRAGMA foreign_key_check').fetchall()==[]; c.close()
