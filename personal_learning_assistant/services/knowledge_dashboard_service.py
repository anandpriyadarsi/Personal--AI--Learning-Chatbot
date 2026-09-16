"""Read-only Phase 5.8 Knowledge Base / RAG adapter for the local web UI.

Phase 7.5.8 exposes the already-built retrieval generation without rebuilding
or mutating it. Retrieval modules stay lazy until the Knowledge page is read.
This adapter assembles source-grounded RAG context but never calls an LLM.
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INDEX_ROOT = PROJECT_ROOT / ".phase5_retrieval"
MAX_QUERY_CHARS = 500
MAX_RESULT_TEXT_CHARS = 1200
DEFAULT_TOP_K = 8


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clean_query(value: Any) -> str:
    return " ".join(str(value or "").strip().split())[:MAX_QUERY_CHARS]


def _safe_http_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urlparse(text)
    except ValueError:
        return ""
    return text if parsed.scheme.lower() in {"http", "https"} and parsed.netloc else ""


def _bounded_text(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) <= MAX_RESULT_TEXT_CHARS:
        return text
    return text[:MAX_RESULT_TEXT_CHARS] + "…"


def _normalize_index(manifest: Mapping[str, Any] | None) -> dict[str, Any]:
    source = dict(manifest or {})
    return {
        "generation_id": str(source.get("generation_id") or "Unknown"),
        "chunk_count": max(0, _integer(source.get("chunk_count"), 0)),
        "document_count": max(0, _integer(source.get("document_count"), 0)),
        "lexical_backend": str(source.get("lexical_backend") or "unknown"),
        "semantic_enabled": bool(source.get("semantic_enabled", False)),
        "embedding_model": str(source.get("embedding_model") or ""),
        "embedding_version": str(source.get("embedding_version") or ""),
        "source_fingerprint": str(source.get("source_fingerprint") or ""),
    }


def _normalize_hit(hit: Any) -> dict[str, Any]:
    locator = _value(hit, "locator", {})
    locator = dict(locator) if isinstance(locator, Mapping) else {}
    source = locator.get("source")
    source = dict(source) if isinstance(source, Mapping) else {}

    providers = list(_value(hit, "providers", ()) or ())
    provider = str(source.get("provider") or (providers[0] if providers else ""))
    score = _float(_value(hit, "score", 0.0), 0.0)
    page = _value(hit, "page_number")

    return {
        "chunk_id": str(_value(hit, "chunk_id", "") or ""),
        "document_id": str(_value(hit, "document_id", "") or ""),
        "text": _bounded_text(_value(hit, "text", "")),
        "score": score,
        "score_label": f"{score:.6f}",
        "lexical_rank": _value(hit, "lexical_rank"),
        "semantic_rank": _value(hit, "semantic_rank"),
        "page_number": None if page is None else _integer(page),
        "topic": str(locator.get("topic") or locator.get("section") or ""),
        "lecture_number": str(locator.get("lecture_number") or ""),
        "lecture_title": str(locator.get("lecture_title") or ""),
        "provider": provider,
        "source_kind": str(source.get("kind") or ""),
        "source_url": _safe_http_url(locator.get("source_url")),
        "resource_ids": [str(item) for item in (_value(hit, "resource_ids", ()) or ())],
        "course_ids": [str(item) for item in (_value(hit, "course_ids", ()) or ())],
        "topic_ids": [str(item) for item in (_value(hit, "topic_ids", ()) or ())],
    }


def _empty_context() -> dict[str, Any]:
    return {"source_count": 0, "total_characters": 0, "text": ""}


def build_knowledge_dashboard(
    manifest: Mapping[str, Any] | None,
    *,
    query: Any = "",
    hits: Any = (),
    context: Any = None,
    warning: str = "",
) -> dict[str, Any]:
    """Normalize current retrieval evidence for safe browser rendering."""
    clean_query = _clean_query(query)
    normalized_hits = [_normalize_hit(hit) for hit in tuple(hits or ())]
    context_model = _empty_context()
    if context is not None:
        context_model = {
            "source_count": max(0, _integer(_value(context, "source_count", 0))),
            "total_characters": max(0, _integer(_value(context, "total_characters", 0))),
            "text": str(_value(context, "context_text", "") or ""),
        }

    index = _normalize_index(manifest)
    return {
        "available": True,
        "message": "",
        "warning": str(warning or ""),
        "query": clean_query,
        "searched": bool(clean_query),
        "index": index,
        "summary": {
            "result_count": len(normalized_hits),
            "source_count": context_model["source_count"],
        },
        "results": normalized_hits,
        "context": context_model,
    }


def _manifest_with_counts(store: Any) -> dict[str, Any]:
    manifest = dict(getattr(store, "manifest", {}) or {})
    try:
        row = store.connection.execute(
            "SELECT COUNT(*) AS chunk_count, COUNT(DISTINCT document_id) AS document_count FROM chunks"
        ).fetchone()
        if row is not None:
            manifest["chunk_count"] = int(row["chunk_count"])
            manifest["document_count"] = int(row["document_count"])
    except Exception:
        # Manifest-only status remains useful if the optional count query fails.
        pass
    return manifest


def _embedding_provider_for(manifest: Mapping[str, Any]):
    if not bool(manifest.get("semantic_enabled")):
        return None
    module = import_module("personal_learning_assistant.retrieval.embedding")
    kwargs = {}
    if manifest.get("embedding_model"):
        kwargs["model_name"] = str(manifest["embedding_model"])
    if manifest.get("embedding_version"):
        kwargs["model_version"] = str(manifest["embedding_version"])
    return module.FastEmbedProvider(**kwargs)


def _lexical_hits(store: Any, query: str, filters: Any, top_k: int):
    models = import_module("personal_learning_assistant.domain.retrieval_models")
    rows = store.lexical_search(query, filters=filters, top_k=top_k)
    hits = []
    for rank, (row, score) in enumerate(rows, 1):
        hits.append(
            models.RetrievalHit(
                chunk_id=str(row["chunk_id"]),
                document_id=str(row["document_id"]),
                text=str(row["text"]),
                score=float(score),
                lexical_rank=rank,
                semantic_rank=None,
                page_number=None if row["page_number"] is None else int(row["page_number"]),
                locator=json.loads(row["locator_json"]),
                resource_ids=tuple(json.loads(row["resource_ids_json"])),
                course_ids=tuple(json.loads(row["course_ids_json"])),
                topic_ids=tuple(json.loads(row["topic_ids_json"])),
                providers=tuple(json.loads(row["providers_json"])),
            )
        )
    return tuple(hits)


def load_knowledge_dashboard(
    query: Any = "",
    *,
    index_root: Any = DEFAULT_INDEX_ROOT,
    top_k: int = DEFAULT_TOP_K,
) -> dict[str, Any]:
    """Read the current Phase 5.8 index and optionally retrieve evidence.

    No index generation, ingestion, academic-data mutation, or LLM call occurs.
    Semantic-search failures degrade to lexical retrieval for the same query.
    """
    clean_query = _clean_query(query)
    store_module = import_module("personal_learning_assistant.retrieval.index_store")
    store = store_module.RetrievalIndexStore(index_root)
    try:
        manifest = _manifest_with_counts(store)
        if not clean_query:
            return build_knowledge_dashboard(manifest, query="")

        models = import_module("personal_learning_assistant.domain.retrieval_models")
        filters = models.RetrievalFilters()
        warning = ""

        store.embedding_provider = _embedding_provider_for(manifest)
        hybrid_module = import_module("personal_learning_assistant.retrieval.hybrid")
        try:
            hits = hybrid_module.HybridRetriever(store).search(
                clean_query,
                filters=filters,
                top_k=max(1, int(top_k)),
            )
        except Exception:
            hits = _lexical_hits(store, clean_query, filters, max(1, int(top_k)))
            warning = (
                "Semantic retrieval was unavailable for this query; "
                "showing lexical matches from the current index only."
            )

        context_module = import_module("personal_learning_assistant.retrieval.rag_context")
        context = context_module.assemble_context(clean_query, hits)
        return build_knowledge_dashboard(
            manifest,
            query=clean_query,
            hits=hits,
            context=context,
            warning=warning,
        )
    finally:
        store.close()


def unavailable_knowledge_dashboard(query: Any = "") -> dict[str, Any]:
    """Return a safe degraded shape without exposing retrieval exception details."""
    return {
        "available": False,
        "message": (
            "Knowledge base is temporarily unavailable. "
            "Your academic data and retrieval index were not changed."
        ),
        "warning": "",
        "query": _clean_query(query),
        "searched": bool(_clean_query(query)),
        "index": _normalize_index({}),
        "summary": {"result_count": 0, "source_count": 0},
        "results": [],
        "context": _empty_context(),
    }
