"""Saved references remain editable through Library without altering registered sources."""
from __future__ import annotations

from personal_learning_assistant.services.notes_resources_dashboard_service import build_resources_dashboard
from personal_learning_assistant.services.notes_resources_web_service import NotesResourcesWebValidationError
from personal_learning_assistant.ui.web import create_app


class InMemoryReferences:
    def __init__(self):
        self.items = [
            {"position": 1, "title": "<script>unsafe</script> lecture", "resource_type": "video",
             "link": "javascript:alert(1)", "status": "Not Started"},
            {"position": 2, "title": "LU Factorisation lecture", "resource_type": "video",
             "link": "https://example.com/lecture", "status": "In Progress"},
        ]

    def resources_workspace(self, search="", resource_type="", status=""):
        filtered = [
            item for item in self.items
            if (not search or search.casefold() in item["title"].casefold())
            and (not resource_type or resource_type.casefold() == item["resource_type"].casefold())
            and (not status or status == item["status"])
        ]
        dashboard = build_resources_dashboard({"resources": filtered})
        dashboard["query"] = {"search": search, "type": resource_type, "status": status}
        return dashboard

    def create_resource(self, title, resource_type, link):
        if not str(title).strip():
            raise NotesResourcesWebValidationError("Title is required")
        self.items.append({"position": len(self.items) + 1, "title": title,
                           "resource_type": resource_type, "link": link,
                           "status": "Not Started"})

    def update_resource_status(self, position, status):
        if status not in ("Not Started", "In Progress", "Completed"):
            raise NotesResourcesWebValidationError("Invalid status")
        self.items[position - 1]["status"] = status


def _client(service):
    def no_canonical_browse():
        raise AssertionError("Saved view must not load the canonical Library")
    return create_app({
        "TESTING": True,
        "NOTES_RESOURCES_WEB_SERVICE_FACTORY": lambda: service,
        "LEARNING_LIBRARY_SERVICE_FACTORY": no_canonical_browse,
    }).test_client()


def test_library_saved_view_retains_bookmarks_filters_and_safe_links():
    store = InMemoryReferences()
    client = _client(store)
    page = client.get("/library?view=saved")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert "Saved links &amp; progress" in body
    assert "LU Factorisation lecture" in body
    assert "&lt;script&gt;unsafe&lt;/script&gt;" in body
    assert "<script>unsafe</script>" not in body
    assert 'href="javascript:alert(1)"' not in body
    assert 'href="https://example.com/lecture"' in body
    assert 'href="/resources" class="nav-item' not in body
    assert 'action="/resources"' in body
    assert 'name="return_to" value="library"' in body
    filtered = client.get("/library?view=saved&saved_q=Factorisation&saved_status=In+Progress")
    assert filtered.status_code == 200
    assert "LU Factorisation lecture" in filtered.get_data(as_text=True)
    assert "unsafe" not in filtered.get_data(as_text=True)
    assert client.get("/library?view=saved&saved_q=a&saved_q=b").status_code == 400


def test_saved_reference_mutations_return_to_library_without_migration():
    store = InMemoryReferences()
    client = _client(store)
    result = client.post("/resources", data={
        "return_to": "library", "title": "New note link", "resource_type": "website",
        "link": "https://example.org/note",
    })
    assert result.status_code == 303
    assert result.headers["Location"].endswith("/library?view=saved&created=1#saved-resources")
    assert store.items[-1]["title"] == "New note link"
    status = client.post("/resources/3/status", data={
        "return_to": "library", "status": "Completed",
    })
    assert status.status_code == 303
    assert status.headers["Location"].endswith("/library?view=saved&updated=1#saved-resources")
    assert store.items[-1]["status"] == "Completed"
    bad = client.post("/resources", data={"return_to": "library", "title": ""})
    assert bad.status_code == 400
    assert "Enter a title before adding" in bad.get_data(as_text=True)
    assert client.get("/resources").status_code == 200  # Existing deep links remain valid.
