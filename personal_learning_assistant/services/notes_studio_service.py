"""Notes Studio foundation: safe Markdown + SQLite coordinated commands."""
from __future__ import annotations
import hashlib, os, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from personal_learning_assistant.domain.notes_studio_models import CreateNoteRequest,UpdateNoteRequest
from personal_learning_assistant.repositories.filesystem.markdown_note_store import AtomicMarkdownNoteStore,MarkdownConflictError
from personal_learning_assistant.repositories.filesystem.obsidian_vault_scanner import normalized_note_path_key
from personal_learning_assistant.repositories.sqlite.knowledge_registry_repository import SQLiteKnowledgeRegistryRepository
from personal_learning_assistant.repositories.sqlite.notes_studio_repository import SQLiteNotesStudioRepository
from personal_learning_assistant.services.operation_coordination_service import OperationCoordinationService

_CANON={'unreviewed','learning','needs_practice','review_due','revised','mastered'}
def _now(): return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
def _hash(raw): return hashlib.sha256(raw).hexdigest()

def _frontmatter(note_id,title,note_type,confidence,status,tags):
    lines=['---',f'assistant_id: {note_id}',f'title: {title}',f'note_type: {note_type}',f'revision_status: {status}']
    if confidence is not None: lines.append(f'confidence: {confidence}')
    if tags:
        lines.append('tags:'); lines.extend('  - '+str(t).strip().lstrip('#') for t in tags if str(t).strip())
    lines.extend(['---',''])
    return '\n'.join(lines)

def _replace_frontmatter(text:str,generated:str)->str:
    lines=text.splitlines()
    if lines and lines[0].lstrip('\ufeff').strip()=='---':
        end=None
        for i in range(1,len(lines)):
            if lines[i].strip() in ('---','...'): end=i; break
        if end is not None: return generated+'\n'+'\n'.join(lines[end+1:]).lstrip('\n')
    return generated+'\n'+text.lstrip('\n')

class NotesStudioService:
    def __init__(self, *, vault_id:str, store:AtomicMarkdownNoteStore, notes:SQLiteNotesStudioRepository, journal_repository:SQLiteKnowledgeRegistryRepository, inbox='01 INBOX', now=_now):
        self.vault_id=vault_id; self.store=store; self.notes=notes; self.coordination=OperationCoordinationService(journal_repository,now=now); self.inbox=inbox; self._now=now
    def _validate(self,note_type,confidence,status):
        if confidence is not None and not 0<=int(confidence)<=5: raise ValueError('confidence must be 0-5 or null')
        if status not in _CANON: raise ValueError('unsupported revision_status')
        if not str(note_type).strip(): raise ValueError('note_type is required')
    def create_note(self,request:CreateNoteRequest):
        self._validate(request.note_type,request.confidence,request.revision_status)
        note_id=str(uuid.uuid4()); rel=self.store.choose_create_path(self.inbox,request.title)
        meta=_frontmatter(note_id,request.title,request.note_type,request.confidence,request.revision_status,request.tags)
        payload=(meta+'\n'+request.body).encode('utf-8')
        op=self.coordination.begin_operation(kind='notes_studio_create',target_path=rel,before_hash=None)
        try:
            new_hash=self.store.atomic_write(rel,payload)
            self.coordination.mark_file_applied(op.id,after_hash=new_hash)
            stat=(self.store.root/rel).stat()
            view=self.notes.insert_note(note_id=note_id,vault_id=self.vault_id,relative_path=rel,path_key=normalized_note_path_key(rel),title=request.title,note_type=request.note_type,confidence=request.confidence,revision_status=request.revision_status,source_hash=new_hash,file_mtime_ns=stat.st_mtime_ns,frontmatter_extra={'notes_studio':'phase5.4'},now=self._now(),tags=request.tags)
            self.coordination.mark_database_committed(op.id)
            self.coordination.enqueue_event(event_type='note.saved',entity_type='note',entity_id=note_id,payload={'source_hash':new_hash})
            self.coordination.complete_operation(op.id)
            return view
        except Exception as exc:
            try: self.coordination.fail_operation(op.id,error=type(exc).__name__)
            except Exception: pass
            raise
    def update_note(self,request:UpdateNoteRequest):
        current=self.notes.get(request.note_id); raw,current_hash=self.store.read(current.relative_path)
        if current_hash!=request.expected_hash: raise MarkdownConflictError('note changed on disk; refresh before saving')
        title=current.title if request.title is None else request.title; typ=current.note_type if request.note_type is None else request.note_type
        confidence=current.confidence if request.confidence is None else request.confidence; status=current.revision_status if request.revision_status is None else request.revision_status; tags=current.tags if request.tags is None else request.tags
        self._validate(typ,confidence,status)
        body=raw.decode('utf-8-sig') if request.body is None else request.body
        generated=_frontmatter(current.id,title,typ,confidence,status,tags)
        payload=_replace_frontmatter(body,generated).encode('utf-8')
        op=self.coordination.begin_operation(kind='notes_studio_update',target_path=current.relative_path,before_hash=current_hash)
        try:
            new_hash=self.store.atomic_write(current.relative_path,payload,expected_hash=current_hash); self.coordination.mark_file_applied(op.id,after_hash=new_hash)
            stat=(self.store.root/current.relative_path).stat()
            view=self.notes.update_note(note_id=current.id,relative_path=current.relative_path,path_key=normalized_note_path_key(current.relative_path),title=title,note_type=typ,confidence=confidence,revision_status=status,source_hash=new_hash,file_mtime_ns=stat.st_mtime_ns,frontmatter_extra={'notes_studio':'phase5.4'},now=self._now(),tags=tags)
            self.coordination.mark_database_committed(op.id); self.coordination.enqueue_event(event_type='note.saved',entity_type='note',entity_id=current.id,payload={'source_hash':new_hash}); self.coordination.complete_operation(op.id); return view
        except Exception as exc:
            try:self.coordination.fail_operation(op.id,error=type(exc).__name__)
            except Exception:pass
            raise
    def pin(self,note_id,pinned=True): return self.notes.set_lifecycle(note_id,pinned_at=self._now() if pinned else None,archived_at=None,trashed_at=None,now=self._now(),keep_existing=True)
    def archive(self,note_id,archived=True): return self.notes.set_lifecycle(note_id,pinned_at=None,archived_at=self._now() if archived else None,trashed_at=None,now=self._now(),keep_existing=True)
    def trash(self,note_id):
        current=self.notes.get(note_id); raw,current_hash=self.store.read(current.relative_path); target='.trash/Personal AI Learning Assistant/'+current.relative_path
        op=self.coordination.begin_operation(kind='notes_studio_trash',target_path=current.relative_path,before_hash=current_hash)
        try:
            self.store.move(current.relative_path,target,expected_hash=current_hash); self.coordination.mark_file_applied(op.id,after_hash=current_hash)
            view=self.notes.update_path_and_trash(note_id,relative_path=target,path_key=normalized_note_path_key(target),trashed_at=self._now(),now=self._now()); self.coordination.mark_database_committed(op.id); self.coordination.complete_operation(op.id); return view
        except Exception as exc:
            try:self.coordination.fail_operation(op.id,error=type(exc).__name__)
            except Exception:pass
            raise
    def restore(self,note_id,relative_path):
        current=self.notes.get(note_id)
        if current.trashed_at is None: raise ValueError('note is not trashed')
        raw,current_hash=self.store.read(current.relative_path); op=self.coordination.begin_operation(kind='notes_studio_restore',target_path=current.relative_path,before_hash=current_hash)
        try:
            self.store.move(current.relative_path,relative_path,expected_hash=current_hash); self.coordination.mark_file_applied(op.id,after_hash=current_hash)
            view=self.notes.update_path_and_trash(note_id,relative_path=relative_path,path_key=normalized_note_path_key(relative_path),trashed_at=None,now=self._now()); self.coordination.mark_database_committed(op.id); self.coordination.complete_operation(op.id); return view
        except Exception as exc:
            try:self.coordination.fail_operation(op.id,error=type(exc).__name__)
            except Exception:pass
            raise
