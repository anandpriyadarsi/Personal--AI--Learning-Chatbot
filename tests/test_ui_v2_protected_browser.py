"""Real protected-page smoke gate for the minimal UI V2 shared-shell change.

Every data service below uses disposable synthetic stores. No protected product
template or service is replaced, and no mutation control is submitted.
"""
from __future__ import annotations

import os
from pathlib import Path
from threading import Thread

import pytest
from werkzeug.serving import make_server

from tests.test_assessment_studio_phase_c import (
    Clock,
    _database as assessment_database,
    _service as assessment_runner,
)
from tests.test_phase7_5_academic_agent_web import FakeWebService
from tests.test_phase7_5_assessments import _catalogue_fixture
from tests.test_phase7_5_15_10_notes_obsidian_separation import _service as notes_service
from tests.test_planning_analysis_v2 import NOW, _database as planning_database, service as overview_service
from tests.learning_studio.helpers import catalogue, package, source_pdf
from tests.learning_studio.test_service import publish


pytestmark = pytest.mark.skipif(
    os.environ.get("ANVAYA_BROWSER_TESTS") != "1",
    reason="Set ANVAYA_BROWSER_TESTS=1 for protected-page real Chromium acceptance",
)

SURFACES = ["planning", "analysis", "assessments", "assessment-runner", "learning", "learning-reader", "tutor"]


@pytest.fixture(scope="module")
def protected_browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def protected_live(tmp_path, monkeypatch):
    from personal_learning_assistant.learning_studio.service import LearningStudioService
    from personal_learning_assistant.services.home_dashboard_service import unavailable_home_dashboard
    from personal_learning_assistant.services.planning_dashboard_service import unavailable_planning_dashboard
    from personal_learning_assistant.services.operational_planner_web_service import build_operational_planner_web_service
    from personal_learning_assistant.services.assessment_studio_service import build_assessment_studio_service
    from personal_learning_assistant.ui.web import create_app, routes

    # Resolve incidental relative paths within the disposable fixture as well.
    monkeypatch.chdir(tmp_path)
    planning_root = tmp_path / "planning"
    assessment_root = tmp_path / "assessment"
    planning_root.mkdir()
    assessment_root.mkdir()
    plan_path = planning_database(planning_root)
    assessment_path = assessment_database(assessment_root)
    clock = Clock()
    runner = assessment_runner(assessment_path, clock)
    session_id = runner.start("assessment-1", confirmed=True)["session_id"]
    notes, _ = notes_service(tmp_path)
    # Assessment subject visuals use this module-level builder rather than the
    # injected Notes factory. Keep that existing read inside the synthetic store.
    monkeypatch.setattr(routes, "build_anvaya_notes_service", lambda: notes)
    learning = LearningStudioService(
        tmp_path / "learning_studio.sqlite3",
        source_loader=lambda _: source_pdf(),
        catalogue_loader=catalogue,
    )
    publish(learning, package(mapped=True))
    tutor = FakeWebService()
    app = create_app({
        "TESTING": True,
        "ASSESSMENT_EXTENDED_ENABLED": False,
        "PLANNING_NOW": lambda: NOW.isoformat(),
        "ACADEMIC_OVERVIEW_SERVICE_FACTORY": lambda: overview_service(plan_path),
        "OPERATIONAL_PLANNER_WEB_SERVICE_FACTORY": lambda: build_operational_planner_web_service(plan_path),
        "HOME_DASHBOARD_PROVIDER": unavailable_home_dashboard,
        "PLANNING_DASHBOARD_PROVIDER": unavailable_planning_dashboard,
        "ASSESSMENT_CATALOGUE_PROVIDER": _catalogue_fixture,
        "ASSESSMENT_STUDIO_SERVICE_FACTORY": lambda: build_assessment_studio_service(assessment_path),
        "ASSESSMENT_RUNNER_SERVICE_FACTORY": lambda: runner,
        "ANVAYA_NOTES_SERVICE_FACTORY": lambda: notes,
        "LEARNING_STUDIO_SERVICE_FACTORY": lambda: learning,
        "ACADEMIC_AGENT_WEB_SERVICE_FACTORY": lambda: tutor,
    })
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    yield {
        "base": base,
        "app": app,
        "plan_path": plan_path,
        "runner": runner,
        "session_id": session_id,
        "root": tmp_path,
        "tutor": tutor,
        "routes": {
            "planning": "/planning?view=week&date=2026-09-28",
            "analysis": "/analysis",
            "assessments": "/assessments",
            "assessment-runner": f"/assessments/sessions/{session_id}",
            "learning": "/learning",
            "learning-reader": "/learning/modules/synthetic/1?view=learn",
            "tutor": "/agent",
        },
    }
    server.shutdown()
    thread.join(timeout=5)
    server.server_close()


@pytest.mark.parametrize("width", [390, 1366])
@pytest.mark.parametrize("surface", SURFACES)
def test_protected_surfaces_retain_shell_controls_and_dark_layout(protected_browser, protected_live, width, surface):
    from playwright.sync_api import expect

    with protected_browser.new_context(viewport={"width": width, "height": 844}, reduced_motion="reduce") as context:
        context.set_default_timeout(5000)
        base = protected_live["base"]
        context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(base + "/") else route.abort())
        page = context.new_page()
        errors = []
        requests = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append((request.method, request.url)))
        response = page.goto(base + protected_live["routes"][surface], wait_until="networkidle")
        assert response.status == 200
        assert page.locator("main").count() == 1
        assert not page.locator("body.workspace-v2").count()
        assert not page.locator('link[href*="workspace_v2.css"],link[href*="workspace_sources.css"],script[src*="workspace_v2.js"]').count()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (surface, width)
        # Check the rendered protected canvas is still dark rather than relying
        # on an asset-name assertion alone.
        channels = page.locator("body").evaluate("e => getComputedStyle(e).backgroundColor.match(/[\\d.]+/g).slice(0,3).map(Number)")
        assert max(channels) < 80, channels

        if surface in ("planning", "analysis"):
            expect(page.locator(".pa-hero")).to_be_visible()
            page.locator('main select[name="course"]').select_option("MA103N")
            page.get_by_role("button", name="Apply filters", exact=True).click()
            expect(page.locator('main select[name="course"]')).to_have_value("MA103N")
            if surface == "planning":
                assert "view=week" in page.url and "date=2026-09-28" in page.url
            else:
                expect(page.locator(".pa-table")).to_contain_text("3 / 4")
        elif surface == "assessments":
            expect(page.locator("#assessments-title")).to_have_text("Assessment Studio")
            page.locator('main a[href="/assessments/import"]').first.click(trial=True)
            assert page.locator('link[href*="assessment_studio.css"]').count() == 1
        elif surface == "assessment-runner":
            expect(page.locator(".exam-question-text")).to_contain_text("lower triangular")
            expect(page.locator('input[name="option_ids"]')).to_have_count(4)
            page.get_by_role("button", name="Save & Next", exact=True).click(trial=True)
            assert "SECRET-MCQ-SOLUTION" not in page.locator("main").inner_text()
        elif surface == "learning":
            expect(page.locator(".ls-subject-card")).to_have_count(6)
            page.locator(".ls-subject-card").first.click(trial=True)
        elif surface == "learning-reader":
            expect(page.locator("#ls-reading-column")).to_contain_text("Learn this concept")
            page.locator("#ls-focus").click(trial=True)
            page.locator("#ls-contents").click(trial=True)
        else:
            page.locator("#tutor-mentor > summary").click()
            page.locator("#mentor-course").select_option("MA103N")
            page.get_by_role("button", name="Show mentor advice", exact=True).click()
            expect(page.locator("#mentor-course")).to_have_value("MA103N")
            page.get_by_role("button", name="Create tutor session", exact=True).click(trial=True)
            assert protected_live["tutor"].llm_calls == 0
            assert protected_live["tutor"].created == []

        # A submitted native filter can expose its DOM before the next CSS load finishes.
        page.wait_for_load_state("networkidle")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (surface, width, "after controls")
        assert not errors
        # Learning's preexisting reader records progress automatically. This is
        # a shell-isolation gate, not a claim that protected reader behavior was
        # redesigned. All other non-GET traffic is unexpected in this smoke.
        assert all(method == "GET" or (surface == "learning-reader" and method == "POST"
                   and url == base + "/learning/modules/synthetic/1/progress")
                   for method, url in requests)
        output = os.environ.get("ANVAYA_UI_V2_ARTIFACTS")
        if output:
            target = Path(output)
            target.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(target / f"protected-{surface}-{width}.png"), full_page=True)
