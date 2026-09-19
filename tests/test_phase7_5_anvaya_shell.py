from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "personal_learning_assistant" / "ui" / "web"


def _client():
    from personal_learning_assistant.ui.web import create_app

    return create_app({"TESTING": True}).test_client()


def test_home_renders_anvaya_identity_and_local_brand_assets():
    response = _client().get("/")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "ANVAYA" in text
    assert "Personal Learning Intelligence" in text
    assert "/static/brand/anvaya-wordmark-white.png" in text
    assert "/static/brand/anvaya-mark.png" in text
    assert 'rel="icon"' in text
    assert "Personal AI Learning Assistant" not in text
    assert "https://" not in text
    assert "http://" not in text


def test_primary_navigation_keeps_core_workspaces_visible_and_uses_more_for_secondary_items():
    source = (WEB / "templates" / "base.html").read_text(encoding="utf-8")
    markers = (
        ">Home<",
        ">ANVAYA<",
        ">Tutor<",
        ">Learning<",
        ">Notes<",
        ">Resources<",
        ">Academics<",
        ">Courses<",
        ">Assessments<",
        ">Calendar<",
        ">More <span",
        ">Knowledge<",
        ">Planning<",
        ">Obsidian<",
        ">Progress<",
        ">Grades<",
        ">Settings<",
    )
    positions = [source.index(marker) for marker in markers]
    assert positions == sorted(positions)
    assert '<details class="nav-more"' in source


def test_real_destinations_are_links_and_future_destinations_are_disabled():
    source = (WEB / "templates" / "base.html").read_text(encoding="utf-8")
    for endpoint in (
        "web.home",
        "web.academic_agent",
        "web.notes",
        "web.resources",
        "web.knowledge",
        "web.courses",
        "web.assessments",
        "web.calendar",
        "web.planning",
    ):
        assert "url_for('{}')".format(endpoint) in source
    for label in ("Obsidian", "Progress", "Grades", "Settings"):
        assert 'aria-disabled="true"' in source
        assert label in source
    assert "web.obsidian" not in source
    assert "web.progress" not in source
    assert "web.grades" not in source
    assert "web.settings" not in source


def test_shell_assets_are_served_locally():
    client = _client()
    for path, expected_type in (
        ("/static/css/app.css", "text/css"),
        ("/static/js/app.js", "javascript"),
        ("/static/brand/anvaya-mark.png", "image/png"),
        ("/static/brand/anvaya-wordmark-white.png", "image/png"),
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert expected_type in response.content_type


def test_brand_assets_are_real_png_files():
    for name in ("anvaya-mark.png", "anvaya-wordmark-white.png"):
        payload = (WEB / "static" / "brand" / name).read_bytes()
        assert payload.startswith(b"\x89PNG\r\n\x1a\n")
        assert len(payload) > 1024


def test_css_is_dark_first_and_contains_approved_brand_tokens():
    css = (WEB / "static" / "css" / "app.css").read_text(encoding="utf-8")
    for token in ("#0B0F14", "#E8EDF2", "#55C2B8", "#64748B", "color-scheme: dark"):
        assert token in css
    assert "prefers-color-scheme: dark" not in css
    assert "prefers-reduced-motion" in css


def test_mobile_drawer_is_keyboard_accessible_and_dependency_free():
    base = (WEB / "templates" / "base.html").read_text(encoding="utf-8")
    script = (WEB / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert 'id="nav-toggle"' in base
    assert 'aria-controls="app-sidebar"' in base
    assert 'aria-expanded="false"' in base
    assert 'id="nav-backdrop"' in base
    assert "Escape" in script
    assert "aria-expanded" in script
    assert "fetch(" not in script
    assert "XMLHttpRequest" not in script
    assert "localStorage" not in script


def test_existing_phase75_get_routes_keep_working():
    client = _client()
    for path in (
        "/",
        "/agent",
        "/notes",
        "/resources",
        "/knowledge",
        "/courses",
        "/assessments",
        "/calendar",
        "/planning",
    ):
        assert client.get(path).status_code == 200, path
