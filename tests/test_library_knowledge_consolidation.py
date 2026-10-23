"""Unified Library UI must preserve independent knowledge and source systems."""
from __future__ import annotations

from personal_learning_assistant.domain.study_search_models import StudySearchResult
from personal_learning_assistant.ui.web import create_app
from test_learning_library_read_model import library_db


class SourceSearch:
    last_warning = ""

    def filter_options(self):
        return {"courses": (), "topics": (), "source_types": ("lecture",), "providers": ()}

    def search(self, query, **filters):
        self.query = query
        self.filters = filters
        return (StudySearchResult(
            item_kind="knowledge_document",
            item_id="doc-example",
            version_hash="a" * 64,
            title="Rank & RREF <example>",
            subtitle="MA103N",
            source_label="Lecture",
            snippet="Rows and pivots; sourced passage.",
            open_target="/knowledge/item/doc-example",
            relevance_reasons=("Text match",),
        ),)


def app(search):
    return create_app({"TESTING": True, "UNIFIED_SEARCH_SERVICE_FACTORY": lambda: search})


def test_library_search_reuses_existing_unified_engine_and_provenance():
    service = SourceSearch()
    client = app(service).test_client()
    response = client.get("/library?view=search&q=rank&source_type=lecture")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert service.query == "rank"
    assert service.filters["source_types"] == ("lecture",)
    assert 'name="view" value="search"' in body
    assert 'action="/library"' in body
    assert "Search inside content" in body
    assert 'href="/knowledge/item/doc-example"' in body
    assert 'action="/knowledge/item/doc-example/ask"' in body
    assert "Rank &amp; RREF &lt;example&gt;" in body
    assert "Rank & RREF <example>" not in body
    assert "Read source" in body
    assert "Related sources" in body


def test_search_view_works_without_constructing_library_browse_service():
    search = SourceSearch()
    def forbidden_library():
        raise AssertionError("Search view must not construct browse service")
    client = create_app({
        "TESTING": True, "UNIFIED_SEARCH_SERVICE_FACTORY": lambda: search,
        "LEARNING_LIBRARY_SERVICE_FACTORY": forbidden_library,
    }).test_client()
    assert client.get("/library?view=search&q=rank").status_code == 200


def test_navigation_and_source_reader_keep_one_library_destination():
    service = SourceSearch()
    client = app(service).test_client()
    body = client.get("/library?view=search").get_data(as_text=True)
    assert 'href="/library" aria-current="page"' in body
    assert 'href="/library?view=search" aria-current="page"' in body
    assert "Library" in body
    assert 'href="/knowledge" class="nav-item"' not in body
    assert client.get("/knowledge?q=rank").status_code == 200
    assert client.get("/library?view=other").status_code == 400
    assert client.get("/library?view=search&q=one&q=two").status_code == 400
    assert client.post("/library?view=search").status_code == 405


def test_source_search_does_not_mutate_library_database(library_db):
    from test_learning_library_read_model import fingerprint
    before = fingerprint(library_db)
    service = SourceSearch()
    client = create_app({
        "TESTING": True,
        "LEARNING_LIBRARY_DATABASE_PATH": library_db,
        "UNIFIED_SEARCH_SERVICE_FACTORY": lambda: service,
    }).test_client()
    assert client.get("/library").status_code == 200
    assert client.get("/library?view=search&q=LU").status_code == 200
    assert fingerprint(library_db) == before
