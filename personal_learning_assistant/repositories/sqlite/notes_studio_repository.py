"""SQLite metadata repository for Phase 5.4 Notes Studio."""
from __future__ import annotations
import json, sqlite3, unicodedata, uuid
from typing import Optional, Sequence, Tuple
from personal_learning_assistant.domain.notes_studio_models import NoteStudioView
from personal_learning_assistant.repositories.sqlite.connection import transaction

_NS=uuid.UUID("8618c2cb-f7a2-4a62-8df2-1c095fda46df")
class NotesStudioRepositoryError(RuntimeError): pass
class NotesStudioNotFoundError(NotesStudioRepositoryError): pass

def _tag_id(normalized:str)->str: return str(uuid.uuid5(_NS,"tag|"+normalized))

class SQLiteNotesStudioRepository:
    def __init__(self, connection: sqlite3.Connection):
        if not isinstance(connection, sqlite3.Connection): raise TypeError("explicit sqlite3.Connection required")
        self.connection=connection; self.connection.row_factory=sqlite3.Row; self.validate_schema()
    def validate_schema(self):
        needed={"note_metadata","vaults","tags","note_tags","operation_journal","outbox_events"}
        actual={str(r[0]) for r in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing=sorted(needed-actual)
        if missing: raise NotesStudioRepositoryError("required Notes Studio tables missing: "+", ".join(missing))
    def get(self,note_id:str)->NoteStudioView:
        row=self.connection.execute("SELECT * FROM note_metadata WHERE id=?",(note_id,)).fetchone()
        if row is None: raise NotesStudioNotFoundError("unknown note")
        tags=tuple(str(r[0]) for r in self.connection.execute("SELECT t.name FROM tags t JOIN note_tags nt ON nt.tag_id=t.id WHERE nt.note_id=? ORDER BY t.normalized_name",(note_id,)))
        return NoteStudioView(str(row['id']),str(row['relative_path']),str(row['title']),str(row['note_type']),None if row['confidence'] is None else int(row['confidence']),str(row['revision_status']),None if row['pinned_at'] is None else str(row['pinned_at']),None if row['archived_at'] is None else str(row['archived_at']),None if row['trashed_at'] is None else str(row['trashed_at']),str(row['source_hash']),tags)
    def list_active(self,vault_id:str)->Tuple[NoteStudioView,...]:
        ids=[str(r[0]) for r in self.connection.execute("SELECT id FROM note_metadata WHERE vault_id=? AND archived_at IS NULL AND trashed_at IS NULL ORDER BY CASE WHEN pinned_at IS NULL THEN 1 ELSE 0 END,pinned_at DESC,updated_at DESC,id",(vault_id,))]
        return tuple(self.get(i) for i in ids)
    def insert_note(self, *, note_id,vault_id,relative_path,path_key,title,note_type,confidence,revision_status,source_hash,file_mtime_ns,frontmatter_extra,now,tags):
        with transaction(self.connection,immediate=True):
            self.connection.execute("INSERT INTO note_metadata (id,vault_id,relative_path,path_key,title,note_type,confidence,revision_status,pinned_at,archived_at,trashed_at,source_hash,file_mtime_ns,frontmatter_extra_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,NULL,NULL,NULL,?,?,?,?,?)",(note_id,vault_id,relative_path,path_key,title,note_type,confidence,revision_status,source_hash,int(file_mtime_ns),json.dumps(dict(frontmatter_extra),sort_keys=True,separators=(',',':')),now,now))
            self._set_tags(note_id,tags,now)
        return self.get(note_id)
    def update_note(self, *, note_id,relative_path,path_key,title,note_type,confidence,revision_status,source_hash,file_mtime_ns,frontmatter_extra,now,tags):
        self.get(note_id)
        with transaction(self.connection,immediate=True):
            self.connection.execute("UPDATE note_metadata SET relative_path=?,path_key=?,title=?,note_type=?,confidence=?,revision_status=?,source_hash=?,file_mtime_ns=?,frontmatter_extra_json=?,updated_at=? WHERE id=?",(relative_path,path_key,title,note_type,confidence,revision_status,source_hash,int(file_mtime_ns),json.dumps(dict(frontmatter_extra),sort_keys=True,separators=(',',':')),now,note_id))
            self._set_tags(note_id,tags,now)
        return self.get(note_id)
    def _set_tags(self,note_id,tags,now):
        self.connection.execute("DELETE FROM note_tags WHERE note_id=?",(note_id,))
        seen={}
        for display in tags:
            display=unicodedata.normalize('NFC',str(display).strip().lstrip('#'))
            if display: seen.setdefault(display.casefold(),display)
        for normalized,display in sorted(seen.items()):
            tid=_tag_id(normalized)
            self.connection.execute("INSERT INTO tags (id,name,normalized_name,created_at) VALUES (?,?,?,?) ON CONFLICT(normalized_name) DO NOTHING",(tid,display,normalized,now))
            row=self.connection.execute("SELECT id FROM tags WHERE normalized_name=?",(normalized,)).fetchone()
            self.connection.execute("INSERT OR IGNORE INTO note_tags(note_id,tag_id) VALUES (?,?)",(note_id,str(row[0])))
    def set_pinned(self,note_id,*,pinned_at,now):
        self.get(note_id)
        with transaction(self.connection,immediate=True):
            self.connection.execute(
                "UPDATE note_metadata SET pinned_at=?,updated_at=? WHERE id=?",
                (pinned_at,now,note_id),
            )
        return self.get(note_id)
    def set_archived(self,note_id,*,archived_at,now):
        self.get(note_id)
        with transaction(self.connection,immediate=True):
            self.connection.execute(
                "UPDATE note_metadata SET archived_at=?,updated_at=? WHERE id=?",
                (archived_at,now,note_id),
            )
        return self.get(note_id)
    def set_lifecycle(self,note_id,*,pinned_at=None,archived_at=None,trashed_at=None,now,keep_existing=False):
        current=self.connection.execute("SELECT pinned_at,archived_at,trashed_at FROM note_metadata WHERE id=?",(note_id,)).fetchone()
        if current is None: raise NotesStudioNotFoundError("unknown note")
        pin=current[0] if keep_existing and pinned_at is None else pinned_at
        archive=current[1] if keep_existing and archived_at is None else archived_at
        trash=current[2] if keep_existing and trashed_at is None else trashed_at
        with transaction(self.connection,immediate=True): self.connection.execute("UPDATE note_metadata SET pinned_at=?,archived_at=?,trashed_at=?,updated_at=? WHERE id=?",(pin,archive,trash,now,note_id))
        return self.get(note_id)
    def update_path_and_trash(self,note_id,*,relative_path,path_key,trashed_at,now):
        with transaction(self.connection,immediate=True): self.connection.execute("UPDATE note_metadata SET relative_path=?,path_key=?,trashed_at=?,updated_at=? WHERE id=?",(relative_path,path_key,trashed_at,now,note_id))
        return self.get(note_id)
