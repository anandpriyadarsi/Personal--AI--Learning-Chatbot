"""Synthetic architecture / Library coexistence contract. No user data or migrations."""
from __future__ import annotations

from pathlib import Path
from hashlib import sha256

from personal_learning_assistant.ui.web import create_app
from test_learning_library_read_model import library_db


def test_library_and_architecture_routes_are_registered_without_side_effects(library_db):
    before = sha256(Path(library_db).read_bytes()).hexdigest()
    app = create_app({"TESTING": True, "LEARNING_LIBRARY_DATABASE_PATH": library_db})
    routes = {rule.rule: (rule.endpoint, set(rule.methods)) for rule in app.url_map.iter_rules()}
    assert routes["/library"][0] == "web.learning_library"
    assert routes["/library/resources/<resource_id>"][0] == "web.learning_library_resource"
    assert "POST" not in routes["/library"][1]
    assert "POST" not in routes["/library/resources/<resource_id>"][1]
    assert "/resources" in routes
    assert "/planning" in routes
    assert "/analysis" in routes
    assert "/assessments" in routes
    client = app.test_client()
    # Preserve the legacy Resources control label during visual redesign.
    resources_page = client.get("/resources")
    assert resources_page.status_code == 200
    assert b"+ Add Resource" in resources_page.data
    listing = client.get("/library")
    assert listing.status_code == 200
    assert b"Lecture collection" in listing.data
    detail = client.get("/library/resources/r1")
    assert detail.status_code == 200
    assert b"/knowledge/item/d1" in detail.data
    assert client.post("/library").status_code == 405
    assert sha256(Path(library_db).read_bytes()).hexdigest() == before


def test_architecture_disabled_library_does_not_shadow_existing_surfaces(library_db):
    app = create_app({
        "TESTING": True,
        "LEARNING_LIBRARY_ENABLED": False,
        "LEARNING_LIBRARY_DATABASE_PATH": library_db,
    })
    client = app.test_client()
    assert client.get("/library").status_code == 404
    assert client.get("/library/resources/r1").status_code == 404
    resources = client.get("/resources")
    assert resources.status_code == 200
    assert b'href="/library"' not in resources.data


def test_library_hub_links_independent_learning_collections_without_import(library_db):
    from sqlite3 import connect
    app = create_app({"TESTING": True, "LEARNING_LIBRARY_DATABASE_PATH": library_db})
    with connect(library_db) as database:
        before = tuple(database.iterdump())
    response = app.test_client().get("/library")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Other learning workspaces' in html
    assert 'not imported or counted as registered Library documents' in html
    for target in ('/notes', '/obsidian', '/knowledge'):
        assert f'href="{target}"' in html
    assert 'Learning Studio' in html
    with connect(library_db) as database:
        assert tuple(database.iterdump()) == before
