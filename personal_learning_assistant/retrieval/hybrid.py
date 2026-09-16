"""Hybrid ranking over lexical and optional semantic Phase 5.8 indexes."""

from __future__ import annotations

import json

from personal_learning_assistant.domain.retrieval_models import RetrievalHit


RRF_K = 60


def _rrf(rank):
    return 1.0 / (RRF_K + rank)


def _hit(row, score, lexical_rank, semantic_rank):
    return RetrievalHit(
        chunk_id=str(row["chunk_id"]),
        document_id=str(row["document_id"]),
        text=str(row["text"]),
        score=float(score),
        lexical_rank=lexical_rank,
        semantic_rank=semantic_rank,
        page_number=None if row["page_number"] is None else int(row["page_number"]),
        locator=json.loads(row["locator_json"]),
        resource_ids=tuple(json.loads(row["resource_ids_json"])),
        course_ids=tuple(json.loads(row["course_ids_json"])),
        topic_ids=tuple(json.loads(row["topic_ids_json"])),
        providers=tuple(json.loads(row["providers_json"])),
    )


class HybridRetriever:
    def __init__(self, store):
        self.store = store

    def search(self, query, *, filters, top_k=8, candidate_k=20):
        lexical = self.store.lexical_search(
            query, filters=filters, top_k=candidate_k
        )
        semantic = self.store.semantic_search(
            query, filters=filters, top_k=candidate_k
        )
        combined = {}
        rows = {}

        for rank, (row, raw_score) in enumerate(lexical, 1):
            chunk_id = str(row["chunk_id"])
            rows[chunk_id] = row
            combined.setdefault(
                chunk_id,
                {
                    "score": 0.0,
                    "lexical_rank": None,
                    "semantic_rank": None,
                },
            )
            combined[chunk_id]["score"] += _rrf(rank)
            combined[chunk_id]["lexical_rank"] = rank

        for rank, (row, raw_score) in enumerate(semantic, 1):
            chunk_id = str(row["chunk_id"])
            rows[chunk_id] = row
            combined.setdefault(
                chunk_id,
                {
                    "score": 0.0,
                    "lexical_rank": None,
                    "semantic_rank": None,
                },
            )
            combined[chunk_id]["score"] += _rrf(rank)
            combined[chunk_id]["semantic_rank"] = rank

        ranked = sorted(
            combined.items(),
            key=lambda item: (-item[1]["score"], item[0]),
        )
        return tuple(
            _hit(
                rows[chunk_id],
                info["score"],
                info["lexical_rank"],
                info["semantic_rank"],
            )
            for chunk_id, info in ranked[: int(top_k)]
        )
