from __future__ import annotations
import hashlib,io,sqlite3,zipfile
from pathlib import Path
import pytest
from personal_learning_assistant.ingestion.chunking import decode_chunk_type,prepare_chunks
from personal_learning_assistant.ingestion.extractors import MarkdownExtractor,PDFExtractor,PPTXExtractor,TextExtractor,TranscriptExtractor
from personal_learning_assistant.ingestion.source_resolver import SourceRootResolver
from personal_learning_assistant.repositories.sqlite.ingestion_repository import SQLiteIngestionRepository
from personal_learning_assistant.repositories.sqlite.knowledge_registry_repository import SQLiteKnowledgeRegistryRepository
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
from personal_learning_assistant.services.knowledge_registry_service import KnowledgeRegistryService
from personal_learning_assistant.services.unified_ingestion_service import UnifiedIngestionService
NOW="2026-09-16T14:00:00Z"
def _hash(raw): return hashlib.sha256(raw).hexdigest()
def _env(tmp_path):
    db=tmp_path/"ingestion.db";apply_migrations(db);c=sqlite3.connect(str(db),isolation_level=None);c.row_factory=sqlite3.Row;c.execute("PRAGMA foreign_keys=ON")
    registry=KnowledgeRegistryService(SQLiteKnowledgeRegistryRepository(c),now=lambda:NOW);repo=SQLiteIngestionRepository(c);source=tmp_path/"documents";source.mkdir();svc=UnifiedIngestionService(repo,SourceRootResolver({"project-documents":source}),now=lambda:NOW,max_chunk_chars=300);return db,c,registry,repo,source,svc
def _register(registry,root,name,raw,kind):
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);return registry.register_document(kind=kind,path_key="project-documents/"+name.replace("\\","/"),content_hash=_hash(raw),mime_type="",size_bytes=len(raw)).document

def test_markdown_extractor_preserves_nested_section_provenance():
    raw=b"---\ntags: [x]\n---\n# A\nalpha\n## B\nbeta\n";units=MarkdownExtractor().extract(raw,source_name="a.md");assert [u.section_path for u in units]==["A","A > B"];chunks=prepare_chunks(units,max_chars=300);kind,loc=decode_chunk_type(chunks[1].chunk_type);assert kind=="markdown";assert loc["section"]=="A > B"
def test_text_chunking_is_deterministic_and_hashed():
    units=TextExtractor().extract(("word "*180).encode(),source_name="a.txt");a=prepare_chunks(units,max_chars=300);b=prepare_chunks(units,max_chars=300);assert a==b;assert len(a)>1;assert all(len(x.text_hash)==64 for x in a)
def test_vtt_transcript_preserves_timestamp_locator():
    units=TranscriptExtractor().extract(b"WEBVTT\n\n00:00:01.000 --> 00:00:03.500\nHello world\n",source_name="a.vtt");assert units[0].timestamp_start_ms==1000 and units[0].timestamp_end_ms==3500;_k,l=decode_chunk_type(prepare_chunks(units,max_chars=300)[0].chunk_type);assert l["timestamp_start_ms"]==1000 and l["timestamp_end_ms"]==3500
def test_srt_transcript_preserves_timestamp_locator():
    u=TranscriptExtractor().extract(b"1\n00:00:05,000 --> 00:00:07,250\nSecond cue\n",source_name="a.srt")[0];assert (u.timestamp_start_ms,u.timestamp_end_ms)==(5000,7250)
def _pptx_bytes():
    slide1=("<?xml version='1.0' encoding='UTF-8'?><p:sld xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main' xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main'><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>LU Factorization</a:t></a:r></a:p><a:p><a:r><a:t>PA equals LU</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>").encode();slide2=slide1.replace(b"LU Factorization",b"Applications");stream=io.BytesIO()
    with zipfile.ZipFile(stream,"w") as zf: zf.writestr("ppt/slides/slide2.xml",slide2);zf.writestr("ppt/slides/slide1.xml",slide1)
    return stream.getvalue()
def test_pptx_extractor_is_slide_ordered_and_preserves_slide_number():
    units=PPTXExtractor().extract(_pptx_bytes(),source_name="slides.pptx");assert [u.slide_number for u in units]==[1,2];assert units[0].section_path=="LU Factorization";_k,l=decode_chunk_type(prepare_chunks(units,max_chars=300)[0].chunk_type);assert l["slide"]==1
def test_pdf_adapter_preserves_real_page_number_via_reader_boundary():
    class Page:
        def __init__(self,text): self.text=text
        def extract_text(self): return self.text
    class Reader:
        def __init__(self,_stream): self.pages=[Page("Page one"),Page("Page two")]
    units=PDFExtractor(reader_factory=Reader).extract(b"synthetic",source_name="a.pdf");assert [u.page_number for u in units]==[1,2];assert [c.page_number for c in prepare_chunks(units,max_chars=300)]==[1,2]
def test_successful_ingestion_writes_current_chunks_and_handoff_job(tmp_path):
    _db,c,registry,repo,root,svc=_env(tmp_path);d=_register(registry,root,"a.md",b"# A\nAlpha\n","markdown");before=(root/"a.md").read_bytes();r=svc.ingest_document(d.id);assert r.status=="completed" and r.chunk_count==1 and r.handoff_job_id;assert repo.get_document(d.id).extraction_status=="completed";assert len(repo.active_chunks(d.id))==1;jobs=repo.list_index_jobs(d.id);assert len(jobs)==1 and jobs[0]["index_kind"]=="retrieval_handoff" and jobs[0]["status"]=="pending";assert (root/"a.md").read_bytes()==before;c.close()
def test_repeat_same_version_is_idempotent_and_does_not_duplicate_handoff(tmp_path):
    _db,c,registry,repo,root,svc=_env(tmp_path);d=_register(registry,root,"a.txt",b"hello","text");first=svc.ingest_document(d.id);changes=c.total_changes;second=svc.ingest_document(d.id);assert first.status=="completed" and second.status=="matched";assert c.total_changes==changes;assert len(repo.list_index_jobs(d.id))==1;c.close()
def test_registered_hash_mismatch_fails_without_writing_chunks(tmp_path):
    _db,c,registry,repo,root,svc=_env(tmp_path);d=_register(registry,root,"a.txt",b"registered","text");(root/"a.txt").write_bytes(b"changed outside registry");r=svc.ingest_document(d.id);assert r.status=="failed";assert repo.get_document(d.id).extraction_status=="failed";assert repo.active_chunks(d.id)==();c.close()
def test_content_revision_retains_old_chunks_but_only_new_version_is_active(tmp_path):
    _db,c,registry,repo,root,svc=_env(tmp_path);d=_register(registry,root,"a.txt",b"version one","text");first=svc.ingest_document(d.id);old=first.extraction_version;old_count=repo.current_chunk_count(d.id,old);old_hash=repo.get_document(d.id).content_hash;p=root/"a.txt";p.write_bytes(b"version two changed");new_hash=_hash(p.read_bytes());registry.register_document(kind="text",path_key="project-documents/a.txt",content_hash=new_hash,size_bytes=len(p.read_bytes()));second=svc.ingest_document(d.id);assert second.status=="completed" and second.extraction_version!=old;assert repo.current_chunk_count(d.id,old)==old_count;assert repo.get_document(d.id).extraction_version==second.extraction_version;jobs=repo.list_index_jobs(d.id);by_hash={row["content_hash"]:row["status"] for row in jobs};assert by_hash[old_hash]=="stale";assert by_hash[new_hash]=="pending";c.close()
def test_extractor_failure_sets_failed_and_creates_no_handoff(tmp_path):
    _db,c,registry,repo,root,svc=_env(tmp_path);d=_register(registry,root,"empty.md",b"   \n","markdown");r=svc.ingest_document(d.id);assert r.status=="failed";assert repo.get_document(d.id).extraction_status=="failed";assert repo.get_document(d.id).extraction_error;assert repo.list_index_jobs(d.id)==();c.close()
def test_unsupported_registered_document_is_skipped_without_db_change(tmp_path):
    _db,c,registry,repo,root,svc=_env(tmp_path);d=_register(registry,root,"a.docx",b"not parsed here","document");before=c.total_changes;r=svc.ingest_document(d.id);assert r.status=="skipped" and c.total_changes==before;c.close()
def test_preview_is_read_only_and_reports_ready(tmp_path):
    _db,c,registry,repo,root,svc=_env(tmp_path);_register(registry,root,"a.txt",b"hello","text");before_changes=c.total_changes;before_counts=(c.execute("SELECT COUNT(*) FROM knowledge_documents").fetchone()[0],c.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0],c.execute("SELECT COUNT(*) FROM index_jobs").fetchone()[0],c.execute("SELECT COUNT(*) FROM outbox_events").fetchone()[0]);preview=svc.preview();after_counts=(c.execute("SELECT COUNT(*) FROM knowledge_documents").fetchone()[0],c.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0],c.execute("SELECT COUNT(*) FROM index_jobs").fetchone()[0],c.execute("SELECT COUNT(*) FROM outbox_events").fetchone()[0]);assert preview.ready==1 and preview.total==1;assert c.total_changes==before_changes;assert after_counts==before_counts;c.close()
def test_repository_schema_uses_existing_phase3_tables_only(tmp_path):
    _db,c,registry,repo,root,svc=_env(tmp_path);repo.validate_schema();assert c.execute("PRAGMA integrity_check").fetchone()[0]=="ok";assert c.execute("PRAGMA foreign_key_check").fetchall()==[];c.close()
