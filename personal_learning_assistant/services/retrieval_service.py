"""High-level Phase 5.8 retrieval service."""

from __future__ import annotations

from personal_learning_assistant.domain.retrieval_models import RetrievalFilters
from personal_learning_assistant.retrieval.hybrid import HybridRetriever
from personal_learning_assistant.retrieval.rag_context import assemble_context


class RetrievalService:
    def __init__(self, store):
        self.store = store
        self.retriever = HybridRetriever(store)

    def search(
        self,
        query,
        *,
        course_ids=(),
        topic_ids=(),
        resource_ids=(),
        document_ids=(),
        lecture_numbers=(),
        providers=(),
        top_k=8,
    ):
        filters = RetrievalFilters(
            course_ids=tuple(course_ids),
            topic_ids=tuple(topic_ids),
            resource_ids=tuple(resource_ids),
            document_ids=tuple(document_ids),
            lecture_numbers=tuple(lecture_numbers),
            providers=tuple(providers),
        )
        return self.retriever.search(
            query,
            filters=filters,
            top_k=top_k,
        )

    def build_context(self, query, *, max_chars=12000, **search_kwargs):
        hits = self.search(query, **search_kwargs)
        return assemble_context(query, hits, max_chars=max_chars)
