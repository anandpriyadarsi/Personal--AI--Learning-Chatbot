# Phase 5.6 — Unified Ingestion Pipeline

Phase 5.6 starts from `f8f211a6109c43697b90c9a26bf13bd8d2fdb864` on `phase5/knowledge-notes-resources`.

The objective is to turn already-registered local documents into deterministic, versioned chunks with provenance and a retrieval-index handoff, without running FTS, embeddings, semantic retrieval or RAG.

## Versioned adapters

- `markdown-v1`: UTF-8 Markdown; top frontmatter is excluded from body extraction; nested heading path retained.
- `text-v1`: UTF-8 plain text.
- `transcript-v1`: SRT/VTT cues with millisecond timestamp ranges.
- `pptx-v1`: read-only OOXML ZIP/XML slide extraction with slide number/title; no `python-pptx` dependency.
- `pdf-v1`: `pypdf` text extraction with true page number. OCR is not attempted; scanned PDFs with no text fail explicitly.

## Deterministic chunking and extraction version

`char-window-v1` creates deterministic non-overlapping chunks. The extraction version combines pipeline version, adapter version, chunker version and the registered content-hash prefix. Old versions remain historical; only the completed version named by `knowledge_documents.extraction_version` is active.

## Provenance

The existing Phase 3 schema has native page and character fields but no dedicated section/slide/time columns. Phase 5.6 keeps historical migrations immutable and uses a versioned machine-readable locator envelope in `chunk_type`:

`<kind>;locator=v1:{canonical-json}`

It carries Markdown section path, PPTX slide, transcript time range, extracted-unit index and character range. PDF page is also stored natively in `page_number`. `decode_chunk_type()` is the compatibility decoder.

## Source and failure safety

The local file is resolved only through an explicit logical root. Symlink/path escapes are rejected. A stable byte snapshot is SHA-256 checked against the registered document hash before extraction. Mismatch requires Phase 5.2 rescan/re-registration.

Extraction status uses `pending`, `running`, `completed`, and `failed`. A bounded error is stored for failures. A failed extraction creates no retrieval handoff.

## Stale derivatives and index handoff

When registered content changes, previous index jobs for old content hashes are marked `stale`. Old chunks are preserved. Successful extraction creates one idempotent `retrieval_handoff` `index_jobs` row with index version `phase5.8-pending-v1` and one `knowledge.document.ingested` outbox event. This is handoff only: no lexical or semantic index is built in Phase 5.6.

## CLI

Read-only preview:

```powershell
python .\phase5_ingest_documents.py --database .\data\learning_assistant.db --root "project-documents=.\knowledge\documents"
```

Real ingestion requires `--apply --confirm INGEST_PHASE5_DOCUMENTS` and should not be run until the gate is green and reviewed.

## Non-goals

No remote URL download, OCR, DOC/DOCX extraction, JSONL package ingestion, FTS, embeddings, hybrid retrieval, RAG, or MIT-package reconciliation occurs here. Those belong to later Phase 5 work.

## Next boundary

Phase 5.7 uses this ingestion contract for the MIT 18.06/external-course package. Phase 5.8 consumes retrieval handoff jobs to build rebuildable lexical and semantic indexes.
