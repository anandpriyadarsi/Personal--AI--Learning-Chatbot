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
