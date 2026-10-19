"""Real responsive Chromium checks with disposable canonical Library data."""
from __future__ import annotations

import os
from pathlib import Path
from threading import Thread

import pytest
from werkzeug.serving import make_server

from test_learning_library_read_model import library_db
from personal_learning_assistant.ui.web import create_app

pytestmark = pytest.mark.skipif(
    os.environ.get("ANVAYA_BROWSER_TESTS") != "1",
    reason="Set ANVAYA_BROWSER_TESTS=1 for real Library browser acceptance",
)


@pytest.fixture
def library_server(library_db):
    app = create_app({
        "TESTING": True,
        "LEARNING_LIBRARY_ENABLED": True,
        "LEARNING_LIBRARY_DATABASE_PATH": library_db,
    })
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:" + str(server.server_port)
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@pytest.mark.parametrize("width,height", [(320,700),(390,844),(768,1024),(1366,768),(1920,1080)])
@pytest.mark.parametrize("path", ["/library", "/library/resources/r1"])
def test_library_read_and_detail_real_browser_no_overflow_or_errors(library_server, width, height, path):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(viewport={"width": width, "height": height},
                                      reduced_motion="reduce")
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        result = page.goto(library_server + path, wait_until="networkidle")
        assert result.status == 200
        assert page.locator("main").count() == 1
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), f"overflow: {path} at {width}"
        assert not errors
        assert page.locator('nav a[href="/library"]').count() >= 1
        assert "Lecture collection" in page.locator("main").inner_text()
        if path == "/library":
            assert page.locator("article.library-card").count() == 3
            assert page.locator("select[name='course_id']").count() == 1
        else:
            assert page.locator("a[href='/knowledge/item/d1']").count() >= 1
            assert page.locator("main form[method='post']").count() == 0
        out = os.environ.get("ANVAYA_LIBRARY_V2_ARTIFACTS")
        if out and width in (390,1366):
            output = Path(out)
            output.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(output / f"library-{'detail' if path.endswith('r1') else 'index'}-{width}.png"), full_page=True)
        context.close()
        browser.close()


def test_resources_primary_action_reveals_form_with_javascript_and_native_fallback(tmp_path):
    from tests.ui_v2_fixtures import live_ui
    from playwright.sync_api import sync_playwright
    with live_ui(tmp_path) as ui:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(reduced_motion="reduce")
            page = context.new_page()
            assert page.goto(ui["base"] + "/resources").status == 200
            panel = page.locator("details#new-resource")
            assert not panel.evaluate("el => el.open")
            page.locator('.materials-hero-actions a[href="#new-resource"]').click()
            assert panel.evaluate("el => el.open")
            assert page.locator("input[name='title']").is_visible()
            context.close()
            no_js = browser.new_context(java_script_enabled=False)
            fallback = no_js.new_page()
            assert fallback.goto(ui["base"] + "/resources").status == 200
            native_panel = fallback.locator("details#new-resource")
            native_panel.locator("summary").click()
            assert native_panel.evaluate("el => el.open")
            assert fallback.locator("input[name='title']").is_visible()
            no_js.close()
            browser.close()
