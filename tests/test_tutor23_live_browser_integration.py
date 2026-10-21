"""Real Chromium integration of recovered Tutor state, explicit prompts and feedback.

The test uses a disposable in-process fake Tutor service and an actual Flask
browser runtime. No installed database, provider, internet or private fixture.
"""
from __future__ import annotations

import os
from pathlib import Path
from threading import Thread

import pytest
from playwright.sync_api import expect
from werkzeug.serving import make_server

from tests.learning_studio.test_browser import browser
from tests.test_phase7_5_academic_agent_web import FakeWebService, fake_web_app

pytestmark = pytest.mark.skipif(
    os.environ.get("ANVAYA_BROWSER_TESTS") != "1",
    reason="Requires real Chromium acceptance with ANVAYA_BROWSER_TESTS=1.",
)


@pytest.fixture
def local_tutor():
    fake = FakeWebService()
    seen = []
    fake.record_feedback = (
        lambda session_id, turn_id, *, helpful:
        seen.append((session_id, turn_id, helpful))
    )
    fake.session["turns"] = [
        {
            "turn_id": "user-1", "ordinal": 1, "role": "user",
            "content": "Help me with **LU**.",
            "support_level": "not_evaluated",
            "provider_name": "", "provider_model": "",
            "created_at": "2026-10-21T08:00:00Z", "evidence": [],
        },
        {
            "turn_id": "assistant-1", "ordinal": 2, "role": "assistant",
            "content": "## Pivot idea\n\n**Eliminate** the entry under the pivot.",
            "support_level": "mixed", "provider_name": "offline-test",
            "provider_model": "synthetic", "created_at": "2026-10-21T08:01:00Z",
            "evidence": [],
        },
    ]
    fake.session["adaptive_state"] = {
        "awaiting_student_answer": True,
        "pending_question": "What multiplier eliminates 4 below pivot 2?",
        "last_misconception": "",
        "practice_active": True,
        "practice_level": 2,
    }
    fake.session["session_goal"] = {
        "goal": "Understand LU Factorization", "status": "active",
    }
    fake.session["teaching_plan"] = {"next_move": "practice"}
    application = fake_web_app(fake)
    server = make_server("127.0.0.1", 0, application, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:" + str(server.server_port), fake, seen
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@pytest.mark.parametrize("width", [390, 768, 1366])
def test_tutor_original_routes_and_new_controls_in_real_browser(browser, local_tutor, width):
    base, fake, seen = local_tutor
    context = browser.new_context(viewport={"width": width, "height": 900})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(base + "/agent/sessions/session-1", wait_until="load")
        expect(page.get_by_role("heading", name="Pivot idea")).to_be_visible()
        expect(page.get_by_text("Understand LU Factorization")).to_be_visible()
        expect(page.get_by_text("What multiplier eliminates 4 below pivot 2?")).to_be_visible()
        expect(page.get_by_text("Practice level 2 of 5")).to_be_visible()
        assert page.get_by_text("Help me with **LU**.").count() == 1
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        assert fake.llm_calls == 0
        page.get_by_role("button", name="Hint only").click()
        expect(page.locator("#agent-question")).to_have_value(
            "Give me one hint only; do not reveal the solution."
        )
        assert fake.llm_calls == 0  # Clicking a helper never sends the prompt.
        folder = os.environ.get("ANVAYA_VALIDATION_ARTIFACTS")
        if folder:
            root = Path(folder)
            root.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(root / f"tutor23-reconciled-{width}.png"), full_page=True)
        page.get_by_role("button", name="Not helpful").click()
        expect(page.get_by_role("heading", name="Pivot idea")).to_be_visible()
        assert seen == [("session-1", "assistant-1", False)]
        assert not errors, errors
        assert fake.llm_calls == 0
    finally:
        context.close()
