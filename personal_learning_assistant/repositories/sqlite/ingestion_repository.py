"""SQLite write boundary for Phase 5.6 extraction/chunks/index handoff."""
from __future__ import annotations
import json
import sqlite3
import uuid
from typing import Sequence, Tuple
from personal_learning_assistant.domain.knowledge_registry_models import KnowledgeDocumentRecord
from personal_learning_assistant.domain.ingestion_models import PreparedChunk
from personal_learning_assistant.repositories.sqlite.connection import transaction

_NAMESPACE = uuid.UUID("d4128d1d-3b44-4a65-a6df-58977f5dbe3b")
class IngestionRepositoryError(RuntimeError): pass
class IngestionSchemaError(IngestionRepositoryError): pass
class IngestionNotFoundError(IngestionRepositoryError): pass
_REQUIRED = {
    "knowledge_documents": {"id","kind","canonical_uri","path_key","mime_type","content_hash","size_bytes","source_timestamp","extraction_status","extraction_version","extraction_error","created_at","updated_at"},
    "knowledge_chunks": {"id","document_id","ordinal","page_number","char_start","char_end","chunk_type","text_hash","extraction_version","chunk_text"},
    "index_jobs": {"id","document_id","content_hash","index_kind","model_name","model_version","index_version","status","created_at","started_at","completed_at","failed_at","error"},
    "outbox_events": {"id","event_type","entity_type","entity_id","payload_json","created_at","processed_at","failed_at","error","attempts"},
}

def _document(row):
    return KnowledgeDocumentRecord(id=str(row["id"]),kind=str(row["kind"]),canonical_uri=None if row["canonical_uri"] is None else str(row["canonical_uri"]),path_key=None if row["path_key"] is None else str(row["path_key"]),mime_type=str(row["mime_type"]),content_hash=str(row["content_hash"]),size_bytes=None if row["size_bytes"] is None else int(row["size_bytes"]),source_timestamp=None if row["source_timestamp"] is None else str(row["source_timestamp"]),extraction_status=str(row["extraction_status"]),extraction_version=str(row["extraction_version"]),extraction_error=None if row["extraction_error"] is None else str(row["extraction_error"]),created_at=str(row["created_at"]),updated_at=str(row["updated_at"]))

class SQLiteIngestionRepository:
    def __init__(self, connection: sqlite3.Connection, *, validate_schema: bool = True):
        if not isinstance(connection, sqlite3.Connection): raise TypeError("connection must be an explicit sqlite3.Connection")
        self.connection = connection; self.connection.row_factory = sqlite3.Row
        if validate_schema: self.validate_schema()
    def validate_schema(self):
        tables={str(r[0]) for r in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        missing=sorted(set(_REQUIRED)-tables)
        if missing: raise IngestionSchemaError("Phase 5.6 required tables are missing: {}".format(", ".join(missing)))
        issues=[]
        for table,required in _REQUIRED.items():
            cols={str(r[1]) for r in self.connection.execute('PRAGMA table_info("{}")'.format(table))}
            miss=sorted(required-cols)
            if miss: issues.append("{}:[{}]".format(table,",".join(miss)))
        if issues: raise IngestionSchemaError("Phase 5.6 schema is incomplete: {}".format("; ".join(issues)))
    def get_document(self, document_id: str):
        row=self.connection.execute("SELECT * FROM knowledge_documents WHERE id=?",(str(document_id),)).fetchone()
        if row is None: raise IngestionNotFoundError("unknown knowledge document")
        return _document(row)
    def list_documents(self):
        return tuple(_document(r) for r in self.connection.execute("SELECT * FROM knowledge_documents ORDER BY path_key,canonical_uri,id").fetchall())
    def current_chunk_count(self, document_id: str, extraction_version: str) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM knowledge_chunks WHERE document_id=? AND extraction_version=?",(document_id,extraction_version)).fetchone()[0])
    def is_current(self, document_id: str, extraction_version: str) -> bool:
        d=self.get_document(document_id)
        return d.extraction_status=="completed" and d.extraction_version==extraction_version and self.current_chunk_count(document_id,extraction_version)>0
    def begin_extraction(self, document_id: str, *, extraction_version: str, now: str):
        d=self.get_document(document_id)
        with transaction(self.connection,immediate=True):
            self.connection.execute("UPDATE knowledge_documents SET extraction_status='running',extraction_version=?,extraction_error=NULL,updated_at=? WHERE id=?",(extraction_version,now,document_id))
            self.connection.execute("UPDATE index_jobs SET status='stale',error=? WHERE document_id=? AND content_hash<>? AND status IN ('pending','running','completed')",("superseded by current registered content hash",document_id,d.content_hash))
    def fail_extraction(self, document_id: str, *, extraction_version: str, error: str, now: str):
        message=" ".join(str(error or "extraction failed").split())[:500]
        with transaction(self.connection,immediate=True): self.connection.execute("UPDATE knowledge_documents SET extraction_status='failed',extraction_version=?,extraction_error=?,updated_at=? WHERE id=?",(extraction_version,message,now,document_id))
    def commit_extraction(self, *, document_id: str, content_hash: str, extraction_version: str, chunks: Sequence[PreparedChunk], now: str, handoff_index_version: str) -> str:
        if not chunks: raise ValueError("successful extraction requires at least one chunk")
        handoff_job_id=str(uuid.uuid5(_NAMESPACE,"handoff|{}|{}|{}".format(document_id,content_hash,handoff_index_version)))
        outbox_id=str(uuid.uuid5(_NAMESPACE,"outbox|{}|{}|{}".format(document_id,content_hash,extraction_version)))
        with transaction(self.connection,immediate=True):
            current=self.connection.execute("SELECT content_hash FROM knowledge_documents WHERE id=?",(document_id,)).fetchone()
            if current is None: raise IngestionNotFoundError("document disappeared during extraction")
            if str(current[0])!=content_hash: raise IngestionRepositoryError("registered content hash changed during extraction")
            self.connection.execute("DELETE FROM knowledge_chunks WHERE document_id=? AND extraction_version=?",(document_id,extraction_version))
            for chunk in chunks:
                cid=str(uuid.uuid5(_NAMESPACE,"chunk|{}|{}|{}".format(document_id,extraction_version,chunk.ordinal)))
                self.connection.execute("INSERT INTO knowledge_chunks (id,document_id,ordinal,page_number,char_start,char_end,chunk_type,text_hash,extraction_version,chunk_text) VALUES (?,?,?,?,?,?,?,?,?,?)",(cid,document_id,chunk.ordinal,chunk.page_number,chunk.char_start,chunk.char_end,chunk.chunk_type,chunk.text_hash,extraction_version,chunk.text))
            self.connection.execute("UPDATE knowledge_documents SET extraction_status='completed',extraction_version=?,extraction_error=NULL,updated_at=? WHERE id=?",(extraction_version,now,document_id))
            self.connection.execute("UPDATE index_jobs SET status='stale',error=? WHERE document_id=? AND content_hash<>? AND status IN ('pending','running','completed')",("superseded by current registered content hash",document_id,content_hash))
            existing=self.connection.execute("SELECT id FROM index_jobs WHERE document_id=? AND content_hash=? AND index_kind='retrieval_handoff' AND model_name='' AND model_version='' AND index_version=?",(document_id,content_hash,handoff_index_version)).fetchone()
            if existing is None:
                self.connection.execute("INSERT INTO index_jobs (id,document_id,content_hash,index_kind,model_name,model_version,index_version,status,created_at,started_at,completed_at,failed_at,error) VALUES (?,?,?,'retrieval_handoff','','',?,'pending',?,NULL,NULL,NULL,NULL)",(handoff_job_id,document_id,content_hash,handoff_index_version,now))
            else: handoff_job_id=str(existing[0])
            payload=json.dumps({"content_hash":content_hash,"extraction_version":extraction_version,"chunk_count":len(chunks),"handoff_job_id":handoff_job_id},sort_keys=True,separators=(",",":"))
            self.connection.execute("INSERT OR IGNORE INTO outbox_events (id,event_type,entity_type,entity_id,payload_json,created_at,processed_at,failed_at,error,attempts) VALUES (?,'knowledge.document.ingested','knowledge_document',?,?,?,NULL,NULL,NULL,0)",(outbox_id,document_id,payload,now))
        return handoff_job_id
    def active_chunks(self, document_id: str):
        d=self.get_document(document_id)
        if d.extraction_status!="completed" or not d.extraction_version: return ()
        return tuple(self.connection.execute("SELECT * FROM knowledge_chunks WHERE document_id=? AND extraction_version=? ORDER BY ordinal,id",(document_id,d.extraction_version)).fetchall())
    def list_index_jobs(self, document_id: str):
        return tuple(self.connection.execute("SELECT * FROM index_jobs WHERE document_id=? ORDER BY created_at,id",(document_id,)).fetchall())
