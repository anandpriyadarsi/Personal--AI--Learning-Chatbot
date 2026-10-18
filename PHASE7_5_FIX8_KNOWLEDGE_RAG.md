# Phase 7.5.8 — Knowledge Base / RAG

## Objective

Expose the existing Phase 5.8 retrieval generation in the local Flask interface without rebuilding indexes, changing academic data, or calling an LLM.

## Browser surface

- `GET /knowledge` shows the current retrieval-generation status.
- `GET /knowledge?q=...` performs a read-only retrieval query.
- `POST /knowledge` is intentionally unsupported.
- The sidebar `Knowledge` entry is now active.

The search form uses the GET query string and therefore does not create application state.

## Retrieval boundary

The adapter opens the existing `.phase5_retrieval` generation through `RetrievalIndexStore`, which opens the lexical index read-only. It uses the existing `HybridRetriever` when semantic retrieval is available, and assembles the existing `RAGContext` with `assemble_context`.

If semantic search cannot run for a query, the adapter falls back to lexical search against the same current generation. It does not rebuild the index or change its pointer.

## Deliberately excluded from Phase 7.5.8

- no LLM call or generated tutor answer;
- no index build/rebuild/ingestion;
- no document, resource, course, topic, or learning-memory mutation;
- no authority switch or migration;
- no modification of Phase 5 retrieval modules;
- no use of the older `semantic_retrieval.py`, `hybrid_retrieval.py`, or `rag_answer.py` runtime as a new web authority.

Actual source-grounded tutoring belongs to Phase 7.5.9 Academic Agent.

## Safety

The web boundary hides retrieval exception content. Result snippets are bounded for browser rendering. Only stored HTTP/HTTPS source URLs are rendered as clickable links. The gate hashes the complete current retrieval index before and after validation to prove immutability.
