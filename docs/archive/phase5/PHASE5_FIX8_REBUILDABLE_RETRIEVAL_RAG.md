# Phase 5.8 — Rebuildable Retrieval / RAG

## Starting point

Phase 5.8 starts from `5ffd73cccc24fcdf2730537f3b5a2beb04a22f36`
(`feat: add Phase 5.7 MIT 18.06 external course crosswalk`) on
`phase5/knowledge-notes-resources`.

The real Phase 5.7 installation has already produced current MIT 18.06
knowledge chunks and reviewed MA103N topic provenance.

## Objective

Build retrieval as disposable derived state over authoritative SQLite
`knowledge_documents` + `knowledge_chunks`.

The authoritative academic/knowledge state remains in production SQLite.
Retrieval indexes can be deleted and rebuilt at any time.

Phase 5.8 includes:

- lexical retrieval;
- optional semantic embeddings through an explicit provider;
- reciprocal-rank hybrid retrieval;
- course/topic/resource/document/provider/lecture filtering;
- provenance-preserving result objects;
- bounded source-grounded RAG context assembly;
- deterministic index manifests and source fingerprints;
- handoff/job completion after an explicitly requested real build.

It does not call an LLM or generate final answers.

## Disposable index structure

Default local index root:

```text
.phase5_retrieval/
  current.json
  indexes/
    <generation-id>/
      manifest.json
      lexical.sqlite3
      embeddings.npz   # only for semantic builds
```

This directory is ignored by Git and is not authoritative.

The generation ID is derived from:

- retrieval format version;
- builder version;
- authoritative source fingerprint;
- lexical vs semantic mode;
- embedding model name/version.

Same source + same configuration reuses the same generation. Changed chunks,
relationships, provenance or embedding configuration create a new generation.

## Source fingerprint

The fingerprint covers active current chunks plus:

- document identity;
- content/extraction identity;
- chunk text hash;
- resource IDs;
- course IDs;
- topic IDs;
- providers;
- locator/provenance JSON.

Only chunks belonging to a completed document's current extraction version are
eligible.

## Lexical retrieval

The disposable lexical SQLite index uses FTS5 when the local SQLite build
supports it. If FTS5 is unavailable, it falls back to deterministic token
overlap without changing authoritative data.

## Semantic retrieval

Semantic indexing is optional and provider-driven.

`FastEmbedProvider` preserves the existing project's lazy dependency behavior
and defaults to `BAAI/bge-small-en-v1.5`. Merely importing or previewing Phase
5.8 does not construct/download a model.

Tests use a deterministic synthetic embedding provider and make no network
request.

Semantic vectors are normalized float32 arrays stored in `embeddings.npz`.
They are disposable and rebuildable from authoritative chunk text.

## Hybrid ranking

Hybrid retrieval uses reciprocal-rank fusion over:

- lexical candidate ranking;
- semantic cosine-similarity ranking when a semantic index is present.

No opaque score is written back into authoritative knowledge.

## Filters

Retrieval supports:

- course IDs;
- topic IDs;
- resource IDs;
- document IDs;
- provider;
- lecture number.

For Phase 5.7 package chunks, chunk-local reviewed `local_topic_ids` are used
instead of broad shared-document topic relationships when available.

This prevents all 261 MIT chunks from inheriting every topic attached to a
shared package document.

## Provenance

Every hit preserves:

- chunk ID;
- document ID;
- page number where available;
- full versioned chunk locator;
- resource/course/topic/provider relationships;
- lexical/semantic rank.

The RAG context assembler emits explicit source blocks containing chunk/document
IDs and locator JSON. This is context construction only; no LLM is invoked.

## Job handoff

Real index build is explicit.

After a successful atomic index install, Phase 5.8:

- records one completed `lexical_retrieval` or `hybrid_retrieval` job per
  represented current document;
- marks older retrieval-build generations stale;
- marks matching pending `retrieval_handoff` jobs completed.

The disposable index is installed before production job state is acknowledged.

## Operator CLI

Read-only lexical preview:

```powershell
python .\phase5_retrieval.py preview
```

Read-only semantic-generation preview:

```powershell
python .\phase5_retrieval.py preview --semantic
```

Real lexical build:

```powershell
python .\phase5_retrieval.py build `
  --confirm BUILD_PHASE5_RETRIEVAL_INDEX
```

Real semantic/hybrid build:

```powershell
python .\phase5_retrieval.py build `
  --semantic `
  --model BAAI/bge-small-en-v1.5 `
  --confirm BUILD_PHASE5_RETRIEVAL_INDEX
```

Semantic build may require the embedding model to be available/downloadable.
The gate does not require network access.

Search examples:

```powershell
python .\phase5_retrieval.py search "Why does LU factorization work?" `
  --course-id <MA103N-course-id> `
  --provider mit_ocw

python .\phase5_retrieval.py context "Explain LU factorization intuitively" `
  --topic-id <LU-topic-id> `
  --max-chars 9000
```

## Safety

- no historical SQLite migration is changed;
- production preview opens SQLite read-only;
- gate never builds a real production index;
- tests use temporary SQLite/indexes only;
- no network is required by tests/gate;
- no source documents or Obsidian files are modified;
- no LLM is called;
- index files are local derived artifacts and ignored by Git.

## Legacy retrieval

Existing `semantic_retrieval.py`, `hybrid_retrieval.py`, and `rag_answer.py`
remain unchanged in Phase 5.8 so older workflows/tests keep working. The new
Phase 5.8 path is a separate structured retrieval service over authoritative
knowledge chunks.

A later integration phase may route the academic tutor to this service after
retrieval quality is evaluated.

## Next boundary

Phase 5.9 should perform final Phase 5 reconciliation/closure:

- verify registry, Notes Studio, Resources 2, ingestion, MIT package, and
  retrieval handoff coherence;
- verify rebuildability from authoritative state;
- verify no orphan/stale derived state is treated as current;
- document final Phase 5 closure before Phase 6.
