"""Real Chromium against loopback-only disposable stores; no provider/network data."""

import json
import multiprocessing
import os
from pathlib import Path
from threading import Thread

import pytest
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from scripts.assessment_execution_fixture import create_fixture
from personal_learning_assistant.services.assessment_execution_service import (
    AssessmentExecutionService,
)
from personal_learning_assistant.ui.web.assessment_execution_candidate import (
    create_candidate_app,
)
from test_assessment_studio_phase_c import Clock


@pytest.fixture(scope="module")
def chromium():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def live(tmp_path):
    clock = Clock()
    service, ids, key = create_fixture(tmp_path / "fixture", now_fn=clock)
    app = create_candidate_app(service, secret_key=key)
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", service, ids, clock
    server.shutdown()
    thread.join()
    server.server_close()


def screenshot(page, name):
    folder = os.environ.get("ANVAYA_VALIDATION_ARTIFACTS")
    if folder:
        path = Path(folder)
        path.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path / (name + ".png")), full_page=True)


@pytest.mark.parametrize("width", [390, 768, 1024, 1366, 1536, 1920])
@pytest.mark.parametrize("kind", ["paper", "online"])
def test_responsive_pause_and_paper(chromium, live, width, kind):
    base, s, ids, clock = live
    context = chromium.new_context(viewport={"width": width, "height": 900})
    page = context.new_page()
    page.on("dialog", lambda dialog: dialog.accept())
    url = base + "/assessments/candidate/sessions/" + ids[kind]
    page.goto(url)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    if kind == "online":
        page.locator('input[value="B"]').check()
    page.get_by_role("button", name="Pause", exact=True).click()
    expect(page.locator("#state-banner")).to_contain_text("Paused — answers saved")
    assert s.state(ids[kind])["status"] == "paused"
    assert page.evaluate("document.activeElement.id") == "state-banner"
    screenshot(page, f"assessment-{kind}-paused-{width}")
    clock.advance(36000)
    page.reload()
    expect(page.locator("#timer")).to_contain_text("30:00")
    page.get_by_role("button", name="Resume", exact=True).click()
    expect(page.locator("#state-banner")).to_contain_text("Solving in progress")
    if kind == "online":
        expect(page.locator('input[value="B"]')).to_be_checked()
    else:
        page.get_by_role("button", name="Finish solving", exact=True).click()
        expect(page.locator("#state-banner")).to_contain_text("Self-check workspace")
        page.get_by_role(
            "button", name="Reveal solution and marking guide"
        ).first.click()
        expect(page.locator(".guide")).to_contain_text("Solve Ly = b")
        assert page.locator("textarea").count() == 0
        for select in page.locator('select[name^="step_"]').all():
            select.select_option("1.0")
        page.get_by_role("button", name="Save question review").first.click()
        expect(page.locator(".mark-state").first).to_contain_text("3.0 marks")
        page.get_by_role(
            "button", name="Reveal solution and marking guide"
        ).first.click()
        page.locator('input[name="marks"]').fill("1.5")
        page.get_by_role("button", name="Save question review").nth(1).click()
        expect(page.locator(".mark-state").nth(1)).to_contain_text("1.5 marks")
        page.locator('input[name="confirmed"]').check()
        page.get_by_role("button", name="Submit self-review").click()
        expect(page.locator(".review-final")).to_contain_text("Status: submitted")
        assert s.review_summary(ids[kind])["total_marks_milli"] == 4500
        screenshot(page, f"assessment-paper-marked-{width}")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    context.close()


def test_offline_failed_pause_keeps_visible_answer(chromium, live):
    base, s, ids, _ = live
    context = chromium.new_context()
    page = context.new_page()
    page.goto(base + "/assessments/candidate/sessions/" + ids["online"])
    page.locator('input[value="B"]').check()
    page.route("**/save", lambda route: route.abort())
    page.get_by_role("button", name="Pause", exact=True).click()
    expect(page.locator("#save-status")).to_contain_text(
        "No successful acknowledgement"
    )
    expect(page.locator('input[value="B"]')).to_be_checked()
    assert s.state(ids["online"])["status"] == "active"
    page.unroute("**/save")
    page.get_by_role("button", name="Pause", exact=True).click()
    expect(page.locator("#state-banner")).to_contain_text("Paused — answers saved")
    context.close()


def test_no_javascript_native_save_pause_resume(chromium, live):
    base, s, ids, clock = live
    context = chromium.new_context(java_script_enabled=False)
    page = context.new_page()
    url = base + "/assessments/candidate/sessions/" + ids["online"]
    page.goto(url)
    page.locator('input[value="B"]').check()
    page.get_by_role("button", name="Pause", exact=True).click()
    expect(page.locator("#state-banner")).to_contain_text("Paused — answers saved")
    clock.advance(7200)
    page.reload()
    page.get_by_role("button", name="Resume", exact=True).click()
    expect(page.locator('input[value="B"]')).to_be_checked()
    assert s.state(ids["online"])["remaining_ms"] == 1800000
    context.close()


def _process_server(path, key, clock_value, queue):
    from datetime import datetime

    service = AssessmentExecutionService(
        path, now_fn=lambda: datetime.fromisoformat(clock_value)
    )
    server = make_server(
        "127.0.0.1", 0, create_candidate_app(service, secret_key=key), threaded=True
    )
    queue.put(server.server_port)
    server.serve_forever()


def test_pause_close_hours_restart_new_process_resume(chromium, tmp_path):
    clock = Clock()
    s, ids, key = create_fixture(tmp_path / "fixture", now_fn=clock)
    ctx = multiprocessing.get_context("spawn")
    queue = ctx.Queue()
    processes = []
    try:

        def launch():
            p = ctx.Process(
                target=_process_server,
                args=(
                    str(tmp_path / "fixture/synthetic.db"),
                    key,
                    clock.value.isoformat(),
                    queue,
                ),
            )
            p.start()
            processes.append(p)
            return queue.get(timeout=20)

        port = launch()
        context = chromium.new_context()
        page = context.new_page()
        page.goto(
            f"http://127.0.0.1:{port}/assessments/candidate/sessions/" + ids["online"]
        )
        page.locator('input[value="B"]').check()
        page.locator('input[name="marked"]').check()
        page.get_by_role("button", name="Pause", exact=True).click()
        expect(page.locator("#state-banner")).to_contain_text("Paused — answers saved")
        remaining = s.state(ids["online"])["remaining_ms"]
        context.close()
        processes[0].terminate()
        processes[0].join(timeout=10)
        clock.advance(36000)
        port = launch()
        context = chromium.new_context()
        page = context.new_page()
        page.goto(
            f"http://127.0.0.1:{port}/assessments/candidate/sessions/" + ids["online"]
        )
        expect(page.locator("#state-banner")).to_contain_text("Paused — answers saved")
        assert s.state(ids["online"])["remaining_ms"] == remaining
        page.get_by_role("button", name="Resume", exact=True).click()
        expect(page.locator("#state-banner")).to_contain_text("Solving in progress")
        expect(page.locator('input[value="B"]')).to_be_checked()
        expect(page.locator('input[name="marked"]')).to_be_checked()
        assert s.state(ids["online"])["session_id"] == ids["online"]
        context.close()
    finally:
        for p in processes:
            if p.is_alive():
                p.terminate()
            p.join(timeout=10)
        queue.close()
        queue.join_thread()


def test_lost_ack_retry_returns_current_paused_state(chromium, live):
    base, s, ids, _ = live
    context = chromium.new_context()
    page = context.new_page()
    page.goto(base + "/assessments/candidate/sessions/" + ids["online"])
    page.locator('input[value="B"]').check()

    def lose_response(route):
        route.fetch()
        route.abort()

    page.route("**/save", lose_response)
    page.get_by_role("button", name="Pause", exact=True).click()
    expect(page.locator("#save-status")).to_contain_text(
        "No successful acknowledgement"
    )
    assert s.state(ids["online"])["status"] == "paused"
    page.unroute("**/save")
    page.get_by_role("button", name="Pause", exact=True).click()
    expect(page.locator("#state-banner")).to_contain_text("Paused — answers saved")
    assert s.state(ids["online"])["revision"] == 2
    context.close()


def test_two_tabs_stale_save_preserves_unsaved_choice(chromium, live):
    base, s, ids, _ = live
    context = chromium.new_context()
    first = context.new_page()
    second = context.new_page()
    url = base + "/assessments/candidate/sessions/" + ids["online"]
    first.goto(url)
    second.goto(url)
    second.locator('input[value="A"]').check()
    first.locator('input[value="B"]').check()
    first.get_by_role("button", name="Pause", exact=True).click()
    expect(first.locator("#state-banner")).to_contain_text("Paused — answers saved")
    second.get_by_role("button", name="Save response", exact=True).click()
    expect(second.locator("#save-status")).to_contain_text("stale attempt revision")
    expect(second.locator('input[value="A"]')).to_be_checked()
    assert s.state(ids["online"])["questions"][0]["response"] == {
        "selected_option_ids": ["B"]
    }
    context.close()


def test_no_javascript_paper_review_amendment(chromium, live):
    base, s, ids, clock = live
    context = chromium.new_context(java_script_enabled=False)
    page = context.new_page()
    page.goto(base + "/assessments/candidate/sessions/" + ids["paper"])
    page.get_by_role("button", name="Finish solving", exact=True).click()
    expect(page.locator("#state-banner")).to_contain_text("Self-check workspace")
    for index in (0, 1):
        page.locator('input[name="unattempted"]').nth(index).check()
        page.get_by_role("button", name="Save question review").nth(index).click()
        expect(page.locator(".mark-state").nth(index)).to_contain_text("0.0 marks")
    page.locator('input[name="confirmed"]').check()
    page.get_by_role("button", name="Submit self-review").click()
    expect(page.locator(".review-final")).to_contain_text("Status: submitted")
    page.locator('input[name="reason"]').fill("Rechecked handwritten working")
    page.get_by_role("button", name="Amend in a new version").click()
    expect(page.locator(".review-final")).to_contain_text("version 2")
    assert len(s.review_history(ids["paper"])) == 2
    context.close()


def test_dark_palette_has_single_pause_and_saves_current_answer(chromium, live):
    base, service, ids, clock = live
    context = chromium.new_context(viewport={"width": 1366, "height": 860})
    page = context.new_page()
    page.goto(base + "/assessments/candidate/sessions/" + ids["online"])
    palette = page.get_by_role("navigation", name="Question palette")
    assert palette.get_by_role("button", name="Pause", exact=True).count() == 1
    assert page.locator(".question button[name='command'][value='pause']").count() == 0
    assert page.evaluate("getComputedStyle(document.documentElement).colorScheme") == "dark"
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(11, 15, 20)"
    page.locator('input[value="B"]').check()
    palette.get_by_role("button", name="Pause", exact=True).click()
    expect(page.locator("#state-banner")).to_contain_text("Paused — answers saved")
    saved = service.state(ids["online"])
    assert saved["status"] == "paused"
    assert saved["questions"][0]["response"]["selected_option_ids"] == ["B"]
    frozen = saved["remaining_ms"]
    clock.advance(7200)
    page.reload()
    assert service.state(ids["online"])["remaining_ms"] == frozen
    palette.get_by_role("button", name="Resume", exact=True).click()
    expect(page.locator("#state-banner")).to_contain_text("Solving in progress")
    expect(page.locator('input[value="B"]')).to_be_checked()
    context.close()


def test_paper_pause_is_only_in_palette(chromium, live):
    base, service, ids, _ = live
    context = chromium.new_context()
    page = context.new_page()
    page.goto(base + "/assessments/candidate/sessions/" + ids["paper"])
    palette = page.get_by_role("navigation", name="Question palette")
    assert palette.get_by_role("button", name="Pause", exact=True).count() == 1
    assert page.locator("#state-banner").get_by_role("button", name="Pause").count() == 0
    palette.get_by_role("button", name="Pause", exact=True).click()
    expect(page.locator("#state-banner")).to_contain_text("Paused — answers saved")
    assert service.state(ids["paper"])["status"] == "paused"
    context.close()


def test_palette_navigation_saves_before_moving_and_pause_keeps_last_question(chromium, live):
    base, service, ids, _ = live
    context = chromium.new_context(viewport={"width": 1024, "height": 768})
    page = context.new_page()
    page.goto(base + "/assessments/candidate/sessions/" + ids["online"])
    page.locator('input[value="B"]').check()
    page.locator('[data-palette-go="2"]').click()
    expect(page.locator(".question-head")).to_contain_text("QUESTION 2")
    assert service.state(ids["online"])["current_ordinal"] == 2
    assert service.state(ids["online"])["questions"][0]["response"]["selected_option_ids"] == ["B"]
    page.locator('input[value="A"]').check()
    page.get_by_role("navigation", name="Question palette").get_by_role(
        "button", name="Pause", exact=True
    ).click()
    expect(page.locator("#state-banner")).to_contain_text("Paused — answers saved")
    state = service.state(ids["online"])
    assert state["status"] == "paused"
    assert state["current_ordinal"] == 2
    assert state["questions"][1]["response"]["selected_option_ids"] == ["A"]
    page.reload()
    assert "Paused — answers saved" in page.locator("#state-banner").inner_text()
    page.get_by_role("navigation", name="Question palette").get_by_role(
        "button", name="Resume", exact=True
    ).click()
    expect(page.locator(".question-head")).to_contain_text("QUESTION 2")
    expect(page.locator('input[value="A"]')).to_be_checked()
    context.close()
