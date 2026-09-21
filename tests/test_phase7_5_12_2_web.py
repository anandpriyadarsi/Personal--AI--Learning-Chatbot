from __future__ import annotations

from personal_learning_assistant.domain.study_search_models import (
    SearchSuggestion,
    StudySearchResult,
)
from personal_learning_assistant.ui.web import create_app


class SearchFake:
    def filter_options(self):
        return {
            "courses": ({"id": "c-ma", "code": "MA103N", "name": "Linear Algebra"},),
            "topics": ({"id": "t-lu", "name": "LU Factorization", "course_id": "c-ma"},),
            "source_types": ("lecture",),
            "providers": ("MIT OCW",),
        }

    def search(self, query, **kwargs):
        return (
            StudySearchResult(
                item_kind="knowledge_document",
                item_id="d-lu",
                version_hash="a" * 64,
                title="MIT 18.06 Lecture 4",
                subtitle="MA103N · LU Factorization",
                source_label="Lecture",
                snippet="LU factorization records elimination multipliers.",
                open_target="/knowledge/item/d-lu",
                relevance_reasons=("Text match",),
            ),
        )

    def suggest(self, query, *, limit=8):
        return (
            SearchSuggestion(
                kind="topic",
                label="LU Factorization",
                subtitle="Academic topic",
                value="LU Factorization",
            ),
        )


class ReaderFake:
    def view(self, document_id):
        return {
            "document_id": document_id,
            "version_hash": "a" * 64,
            "title": "MIT 18.06 Lecture 4",
            "source_label": "Lecture",
            "course_labels": ("MA103N · Linear Algebra",),
            "topic_labels": ("LU Factorization",),
            "open_original_url": "https://example.com/lu",
            "history": {
                "last_read_at": None,
                "times_opened": 0,
                "total_active_seconds": 0,
                "max_scroll_bps": 0,
            },
            "companion": {
                "key_points": (),
                "doubts": (),
                "personal_notes": (),
            },
            "content": (
                {
                    "chunk_id": "ch1",
                    "ordinal": 0,
                    "page_number": None,
                    "text": "LU factorization records elimination multipliers.",
                },
            ),
        }


class AgentFake:
    def create_source_session(self, **kwargs):
        assert kwargs["document_id"] == "d-lu"
        assert kwargs["version_hash"] == "a" * 64
        return "session-1"


def test_unified_knowledge_page_and_suggestions_are_student_facing():
    app = create_app(
        {
            "TESTING": True,
            "UNIFIED_SEARCH_SERVICE_FACTORY": lambda: SearchFake(),
        }
    )
    client = app.test_client()

    response = client.get("/knowledge?q=LU")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "MIT 18.06 Lecture 4" in text
    assert "LU factorization records elimination multipliers." in text
    assert "document d-lu" not in text

    suggestion = client.get("/api/search/suggest?q=LU")
    assert suggestion.status_code == 200
    assert suggestion.get_json()["results"][0]["label"] == "LU Factorization"


def test_knowledge_reader_and_source_ask_route():
    app = create_app(
        {
            "TESTING": True,
            "KNOWLEDGE_READER_SERVICE_FACTORY": lambda: ReaderFake(),
            "ACADEMIC_AGENT_WEB_SERVICE_FACTORY": lambda: AgentFake(),
        }
    )
    client = app.test_client()

    response = client.get("/knowledge/item/d-lu")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "ANVAYA Companion" in text
    assert "Ask ANVAYA" in text
    assert "LU factorization records elimination multipliers." in text

    ask = client.post(
        "/knowledge/item/d-lu/ask",
        data={"version_hash": "a" * 64, "prefill_question": "Why?"},
        follow_redirects=False,
    )
    assert ask.status_code == 303
    assert ask.headers["Location"].endswith("/agent/sessions/session-1")
