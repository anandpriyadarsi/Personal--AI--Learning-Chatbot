"""UI contracts for source identity and progressive, read-only research views."""
from html.parser import HTMLParser

from personal_learning_assistant.domain.study_search_models import StudySearchResult
from personal_learning_assistant.ui.web import create_app


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.items = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.items.append((tag, dict(attrs)))


class Search:
    def filter_options(self):
        return {"courses": (), "topics": (), "source_types": ("lecture",), "providers": ()}

    def search(self, query, **kwargs):
        self.filters = kwargs
        if query == "missing":
            return ()
        return (StudySearchResult(
            item_kind="knowledge_document", item_id="source-1", version_hash="a" * 64,
            title="Matrices <script>alert(1)</script>", subtitle="MA103N · Linear algebra",
            source_label="Lecture", snippet="A source excerpt, not assessment evidence.",
            open_target="/knowledge/item/source-1", relevance_reasons=("Text match",),
        ),)


def test_knowledge_initial_state_offers_source_navigation_and_native_search():
    service = Search()
    app = create_app({"TESTING": True, "UNIFIED_SEARCH_SERVICE_FACTORY": lambda: service})
    html = app.test_client().get("/knowledge").get_data(as_text=True)
    elements = Elements(html).items
    assert "Start with a question" in html
    assert "workspace-v2" in html
    assert any(tag == "form" and attrs.get("method") == "get" and attrs.get("action") == "/knowledge" for tag, attrs in elements)
    assert any(tag == "a" and attrs.get("href") == "/notes" for tag, attrs in elements)
    assert any(tag == "a" and attrs.get("href") == "/obsidian" for tag, attrs in elements)


def test_knowledge_active_filters_are_visible_and_keep_query_contract():
    service = Search()
    app = create_app({"TESTING": True, "UNIFIED_SEARCH_SERVICE_FACTORY": lambda: service})
    html = app.test_client().get("/knowledge?q=LU&source_type=lecture").get_data(as_text=True)
    elements = Elements(html).items
    assert service.filters["source_types"] == ("lecture",)
    assert any(tag == "details" and "knowledge-filter-disclosure" in attrs.get("class", "") and "open" in attrs for tag, attrs in elements)
    assert "Matrices &lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert '<script>alert(1)</script>' not in html
    assert 'name="version_hash" value="' + "a" * 64 in html
    assert "Text match" in html
    assert sum(tag == "main" for tag, attrs in elements) == 1


def test_knowledge_empty_results_explain_recovery_without_confidence_claims():
    service = Search()
    app = create_app({"TESTING": True, "UNIFIED_SEARCH_SERVICE_FACTORY": lambda: service})
    html = app.test_client().get("/knowledge?q=missing").get_data(as_text=True)
    assert "No matching sources" in html
    assert "Clear search" in html
    assert "confidence" not in html.casefold()
