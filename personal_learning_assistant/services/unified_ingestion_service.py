"""Phase 5.6 local extraction/chunk/index-handoff orchestration."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Sequence
from personal_learning_assistant.domain.ingestion_models import IngestionPreview,IngestionPreviewItem,IngestionResult
from personal_learning_assistant.ingestion.chunking import CHUNKER_VERSION,prepare_chunks
from personal_learning_assistant.ingestion.extractors import EmptyExtractionError,ExtractorRegistry
from personal_learning_assistant.ingestion.source_resolver import SourceResolutionError,SourceRootResolver
from personal_learning_assistant.repositories.sqlite.ingestion_repository import SQLiteIngestionRepository

PIPELINE_VERSION="unified-ingestion-v1"
HANDOFF_INDEX_VERSION="phase5.8-pending-v1"
def _utc_now(): return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

class UnifiedIngestionService:
    def __init__(self, repository: SQLiteIngestionRepository, source_resolver: SourceRootResolver, *, extractor_registry: Optional[ExtractorRegistry]=None, now=_utc_now, max_chunk_chars:int=1600):
        self.repository=repository; self.source_resolver=source_resolver; self.extractors=extractor_registry or ExtractorRegistry(); self._now=now; self.max_chunk_chars=int(max_chunk_chars)
    @staticmethod
    def _source_name(document): return str(document.path_key or document.canonical_uri or document.id)
    def _adapter(self,document): return self.extractors.select(source_name=self._source_name(document),kind=document.kind,mime_type=document.mime_type)
    @staticmethod
    def _version(document,adapter): return "{}|{}|{}|{}".format(PIPELINE_VERSION,adapter.version,CHUNKER_VERSION,document.content_hash[:16])
    def _classify(self,document):
        adapter=self._adapter(document)
        if adapter is None: return IngestionPreviewItem(document.id,"unsupported","",document.content_hash,document.extraction_status,document.extraction_version)
        version=self._version(document,adapter)
        if self.repository.is_current(document.id,version): return IngestionPreviewItem(document.id,"current",adapter.name,document.content_hash,document.extraction_status,document.extraction_version)
        if not document.path_key: return IngestionPreviewItem(document.id,"remote_only",adapter.name,document.content_hash,document.extraction_status,document.extraction_version)
        try:
            path=self.source_resolver.resolve(document.path_key); _raw,digest=self.source_resolver.snapshot(path)
            state="ready" if digest==document.content_hash else "hash_mismatch"
        except SourceResolutionError: state="missing_source"
        return IngestionPreviewItem(document.id,state,adapter.name,document.content_hash,document.extraction_status,document.extraction_version)
    def preview(self,document_ids:Optional[Sequence[str]]=None):
        wanted=None if document_ids is None else set(map(str,document_ids)); items=tuple(self._classify(d) for d in self.repository.list_documents() if wanted is None or d.id in wanted)
        counts={k:0 for k in ("ready","current","unsupported","missing_source","hash_mismatch","remote_only")}
        for item in items: counts[item.state]=counts.get(item.state,0)+1
        return IngestionPreview(len(items),counts["ready"],counts["current"],counts["unsupported"],counts["missing_source"],counts["hash_mismatch"],counts["remote_only"],items)
    def ingest_document(self,document_id:str):
        d=self.repository.get_document(document_id); adapter=self._adapter(d)
        if adapter is None: return IngestionResult(d.id,"skipped","","",0,None,"unsupported local source type")
        version=self._version(d,adapter)
        if self.repository.is_current(d.id,version): return IngestionResult(d.id,"matched",adapter.name,version,self.repository.current_chunk_count(d.id,version),None,"current extraction already exists")
        if not d.path_key: return IngestionResult(d.id,"skipped",adapter.name,version,0,None,"remote-only source fetching is outside Phase 5.6")
        try:
            path=self.source_resolver.resolve(d.path_key); raw,digest=self.source_resolver.snapshot(path)
        except SourceResolutionError as error:
            self.repository.fail_extraction(d.id,extraction_version=version,error=str(error),now=self._now()); return IngestionResult(d.id,"failed",adapter.name,version,0,None,str(error))
        if digest!=d.content_hash:
            message="source hash differs from registry; rescan/register source before ingestion"; self.repository.fail_extraction(d.id,extraction_version=version,error=message,now=self._now()); return IngestionResult(d.id,"failed",adapter.name,version,0,None,message)
        self.repository.begin_extraction(d.id,extraction_version=version,now=self._now())
        try:
            chunks=prepare_chunks(adapter.extract(raw,source_name=self._source_name(d)),max_chars=self.max_chunk_chars)
            if not chunks: raise EmptyExtractionError("extractor produced no chunks")
            handoff=self.repository.commit_extraction(document_id=d.id,content_hash=d.content_hash,extraction_version=version,chunks=chunks,now=self._now(),handoff_index_version=HANDOFF_INDEX_VERSION)
        except Exception as error:
            self.repository.fail_extraction(d.id,extraction_version=version,error="{}: {}".format(type(error).__name__,error),now=self._now()); return IngestionResult(d.id,"failed",adapter.name,version,0,None,"{}: {}".format(type(error).__name__,error))
        return IngestionResult(d.id,"completed",adapter.name,version,len(chunks),handoff,"")
    def ingest_all(self,document_ids:Optional[Sequence[str]]=None):
        wanted=None if document_ids is None else set(map(str,document_ids)); return tuple(self.ingest_document(d.id) for d in self.repository.list_documents() if wanted is None or d.id in wanted)
