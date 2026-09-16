"""Read-only access to a built Phase 5.8 retrieval index."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from pathlib import Path

from personal_learning_assistant.domain.retrieval_models import RetrievalFilters


_TOKEN = re.compile(r"[A-Za-z0-9_]+")


class RetrievalIndexError(RuntimeError):
    pass


def _tokens(text):
    return [item.casefold() for item in _TOKEN.findall(str(text or ""))]


def _matches_filters(row, filters: RetrievalFilters):
    resource_ids = set(json.loads(row["resource_ids_json"]))
    course_ids = set(json.loads(row["course_ids_json"]))
    topic_ids = set(json.loads(row["topic_ids_json"]))
    providers = set(json.loads(row["providers_json"]))
    locator = json.loads(row["locator_json"])

    if filters.document_ids and row["document_id"] not in set(filters.document_ids):
        return False
    if filters.resource_ids and not (resource_ids & set(filters.resource_ids)):
        return False
    if filters.course_ids and not (course_ids & set(filters.course_ids)):
        return False
    if filters.topic_ids and not (topic_ids & set(filters.topic_ids)):
        return False
    if filters.providers and not (providers & set(filters.providers)):
        return False
    if filters.lecture_numbers:
        refs = set(str(x) for x in locator.get("lecture_numbers", []))
        one = locator.get("lecture_number")
        if one is not None:
            refs.add(str(one))
        if not (refs & set(str(x) for x in filters.lecture_numbers)):
            return False
    return True


class RetrievalIndexStore:
    def __init__(self, index_root, *, embedding_provider=None):
        self.index_root = Path(index_root)
        self.embedding_provider = embedding_provider
        self.manifest = self._load_manifest()
        self.directory = (
            self.index_root / "indexes" / str(self.manifest["generation_id"])
        )
        self.connection = sqlite3.connect(
            "file:{}?mode=ro".format(
                str((self.directory / "lexical.sqlite3").resolve()).replace("\\", "/")
            ),
            uri=True,
        )
        self.connection.row_factory = sqlite3.Row
        self._semantic = None

    def close(self):
        self.connection.close()

    def _load_manifest(self):
        pointer = self.index_root / "current.json"
        if not pointer.is_file():
            raise RetrievalIndexError("no current Phase 5.8 retrieval index")
        try:
            generation = json.loads(pointer.read_text(encoding="utf-8"))["generation_id"]
            manifest = json.loads(
                (
                    self.index_root
                    / "indexes"
                    / generation
                    / "manifest.json"
                ).read_text(encoding="utf-8")
            )
        except (OSError, KeyError, json.JSONDecodeError) as error:
            raise RetrievalIndexError("retrieval index manifest is invalid") from error
        return manifest

    def lexical_search(self, query, *, filters=RetrievalFilters(), top_k=10):
        candidate_limit = max(int(top_k) * 8, 40)
        backend = str(self.manifest.get("lexical_backend"))
        rows = []
        if backend == "fts5":
            terms = _tokens(query)
            if not terms:
                return ()
            match = " OR ".join('"{}"'.format(term.replace('"', '""')) for term in terms)
            rows = self.connection.execute(
                "SELECT c.*,bm25(chunk_fts) AS raw_score "
                "FROM chunk_fts JOIN chunks c ON c.chunk_id=chunk_fts.chunk_id "
                "WHERE chunk_fts MATCH ? ORDER BY raw_score LIMIT ?",
                (match, candidate_limit),
            ).fetchall()
            scored = [
                (row, 1.0 / (1.0 + max(float(row["raw_score"]), 0.0)))
                for row in rows
            ]
        else:
            query_tokens = set(_tokens(query))
            if not query_tokens:
                return ()
            rows = self.connection.execute("SELECT * FROM chunks").fetchall()
            scored = []
            for row in rows:
                doc_tokens = set(_tokens(row["text"]))
                overlap = len(query_tokens & doc_tokens)
                if overlap:
                    scored.append((row, overlap / max(len(query_tokens), 1)))
            scored.sort(key=lambda item: (-item[1], item[0]["chunk_id"]))

        result = []
        for row, score in scored:
            if not _matches_filters(row, filters):
                continue
            result.append((row, float(score)))
            if len(result) >= top_k:
                break
        return tuple(result)

    def semantic_search(self, query, *, filters=RetrievalFilters(), top_k=10):
        if not self.manifest.get("semantic_enabled"):
            return ()
        if self.embedding_provider is None:
            raise RetrievalIndexError(
                "semantic index exists but no embedding provider was supplied"
            )
        if (
            self.embedding_provider.model_name
            != self.manifest.get("embedding_model")
            or self.embedding_provider.model_version
            != self.manifest.get("embedding_version")
        ):
            raise RetrievalIndexError(
                "embedding provider does not match current index manifest"
            )
        try:
            import numpy as np
        except ImportError as error:
            raise RetrievalIndexError("semantic search requires NumPy") from error
        if self._semantic is None:
            payload = np.load(
                self.directory / "embeddings.npz",
                allow_pickle=False,
            )
            self._semantic = (
                payload["chunk_ids"].astype(str),
                payload["embeddings"].astype(np.float32),
            )
        ids, matrix = self._semantic
        query_vector = np.asarray(
            self.embedding_provider.embed([query])[0], dtype=np.float32
        )
        norm = float(np.linalg.norm(query_vector))
        if norm == 0:
            return ()
        query_vector = query_vector / norm
        similarities = matrix @ query_vector
        order = np.argsort(-similarities)

        result = []
        for index in order:
            chunk_id = str(ids[int(index)])
            row = self.connection.execute(
                "SELECT * FROM chunks WHERE chunk_id=?",
                (chunk_id,),
            ).fetchone()
            if row is None or not _matches_filters(row, filters):
                continue
            result.append((row, float(similarities[int(index)])))
            if len(result) >= top_k:
                break
        return tuple(result)
