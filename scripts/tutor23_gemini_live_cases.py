"""Actual Gemini HTTP/Flask/Chromium A–K acceptance, never a fake-provider certificate.

Opt-in: only CI in the trusted ANVAYA PR is permitted to pass the GitHub secret.
All courses/databases are synthetic; no installed student data is opened.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import subprocess
import time
from threading import Thread

import pytest
from playwright.sync_api import expect
from werkzeug.serving import make_server

from personal_learning_assistant.tutor.http_provider import OpenAICompatibleTutorProvider
from personal_learning_assistant.ui.web import create_app
from tests.learning_studio.test_browser import browser
from tests.test_phase7_5_academic_agent_web import (
    build_test_web_service, open_database, table_counts,
)
from tests.test_tutor23_cloud_acceptance import (
    Journey, PROMPTS, protected_hashes,
)

ENABLED = os.getenv("ANVAYA_TUTOR_GEMINI_LIVE") == "1"
GOOGLE_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
EXPECTED_MODEL = "gemini-3.8-flash"
OUTPUT = Path(os.getenv("ANVAYA_LIVE_ARTIFACTS", "tutor-live-artifacts"))

pytestmark = pytest.mark.skipif(not ENABLED, reason="Real Gemini acceptance is explicit opt-in only.")


class RealGemini:
    calls = 0
    last_call = 0.0
    max_calls = 26

    def __init__(self):
        if os.getenv("LLM_API_URL") != GOOGLE_ENDPOINT:
            raise RuntimeError("Disallowed provider endpoint; refusing to send GitHub secret")
        if os.getenv("LLM_MODEL") != EXPECTED_MODEL:
            raise RuntimeError("Unexpected model; refusing provider request")
        self.inner = OpenAICompatibleTutorProvider(timeout_seconds=65)
        self.requests = []
        self.responses = []  # Journey interface only; never consumed as scripted responses.
        self.last_error = ""

    @property
    def configured(self):
        return self.inner.configured

    def complete(self, request):
        if RealGemini.calls >= RealGemini.max_calls:
            raise RuntimeError("Real-provider run-wide limit of 26 calls reached")
        elapsed = time.monotonic() - RealGemini.last_call
        if RealGemini.last_call and elapsed < 8:
            time.sleep(8 - elapsed)
        RealGemini.calls += 1
        RealGemini.last_call = time.monotonic()
        self.requests.append({"number": RealGemini.calls, "mode": request.mode})
        try:
            return self.inner.complete(request)
        except Exception as error:
            raw = str(error)
            secret = os.getenv("LLM_API_KEY", "")
            self.last_error = raw.replace(secret, "[REDACTED]")[:300] if secret else raw[:300]
            raise


@pytest.fixture
def live_journey(browser, tmp_path):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    provider = RealGemini()
    if not provider.configured:
        pytest.fail("BLOCKED: Gemini Actions secret is not present")
    service, db_path, _, _, retrieval = build_test_web_service(tmp_path, provider=provider)
    conn = open_database(db_path)
    for position, name in enumerate(("LU Factorization", "Gaussian Elimination", "Elimination Multipliers"), 2):
        conn.execute(
            "INSERT INTO topics(id,course_id,name,normalized_name,position,status,created_at,updated_at) "
            "VALUES(?,?,?,?,?,'not_started',?,?)",
            (f"synthetic-topic-{position}", "synthetic-ma", name, name.lower(), position,
             "2026-10-22T00:00:00Z", "2026-10-22T00:00:00Z"),
        )
    baseline = protected_hashes(conn)
    conn.close()
    retrieval.queries = []
    def empty_search(query, **kwargs):
        retrieval.queries.append({"query": query, **kwargs})
        return ()
    retrieval.search = empty_search
    app = create_app({"TESTING": True, "ACADEMIC_AGENT_WEB_SERVICE_FACTORY": lambda: service})
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    page = browser.new_page(viewport={"width": 1366, "height": 950})
    journey = Journey(page, f"http://127.0.0.1:{server.server_port}", db_path, provider, None, 1366)
    journey.retrieval = retrieval
    try:
        journey.create()
        yield journey
    finally:
        page.close()
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        conn = open_database(db_path)
        try:
            assert protected_hashes(conn) == baseline, "A non-Tutor academic table changed"
            assert "tutor_memory_candidates" not in table_counts(conn), "Optional memory schema was applied"
        finally:
            conn.close()


def check(ok, reason):
    assert ok, reason


def teaching_case(label, j):
    if label == "A":
        s = j.ask(PROMPTS["A"])
        check(s["teaching_plan"]["next_move"] == "ask_diagnostic", "No initial diagnostic")
        check(s["current_learning_state"]["pending_question_kind"] == "diagnostic", "No pending diagnostic")
        check(len(j.provider.requests) == 0, "Unnecessary AI call for deterministic diagnostic")
    elif label == "B":
        old = j.ask(PROMPTS["A"])["current_learning_state"]["pending_question"]
        s = j.ask(PROMPTS["B"])
        check(s["current_learning_state"]["pending_question"] == old, "Hint lost pending question")
        s = j.ask("I know elimination but cannot connect the multiplier to L.")
        check(s["teaching_plan"]["reason"] == "pending_socratic_answer", "Student answer lost Socratic continuity")
    elif label == "C":
        s = j.ask(PROMPTS["C"])
        p = s["teaching_plan"]
        check(p["next_move"] == "review_prerequisite", "Prerequisite repair was skipped")
        check(p["prerequisite_concept"] == "Elimination Multipliers", "Wrong prerequisite")
        check(p["target_concept"] == "LU Factorization" and p["return_to_goal"], "Original goal was lost")
        check(s["current_learning_state"]["pending_question_kind"] == "socratic_check", "Generated follow-up was not persisted")
        s = j.ask("3")
        check(s["teaching_plan"]["reason"] == "pending_socratic_answer", "Short answer was not interpreted as a reply")
        check(s["current_learning_state"]["answer_status"] in {"correct","incorrect","partial","unclear"}, "Real-model evaluation absent")
    elif label == "D":
        s = j.ask(PROMPTS["D"])
        a = s["current_learning_state"]
        check(a["pending_question_kind"] == "practice", "Unsolved practice question missing")
        check(a["practice_format"] == "computational", "Wrong practice format")
        level = a["practice_level"]
        check(1 <= level <= 5, "Difficulty outside bounds")
        b = j.ask("My answer is 3. Please check it before moving on.")["current_learning_state"]
        check(1 <= b["practice_level"] <= 5 and abs(b["practice_level"]-level) <= 1, "Difficulty jumped more than one step")
        check(b["answer_status"] in {"correct","incorrect","partial","unclear"}, "No real-model evaluation")
    elif label == "E":
        start = j.ask(PROMPTS["D"])["current_learning_state"]["practice_level"]
        hard = j.ask(PROMPTS["E"])["current_learning_state"]
        check(hard["practice_level"] == min(5,start+1), "Explicit harder request was ignored")
        check(hard["practice_format"] == "computational", "Lost computational format")
        easy = j.ask("Give me an easier computational practice problem. One problem only.")["current_learning_state"]
        check(easy["practice_level"] == max(1,hard["practice_level"]-1), "Explicit easier request was ignored")
        check(easy["practice_format"] == "computational", "Lost computational format")
    elif label == "F":
        j.create(topic="")
        j.ask(PROMPTS["D"])
        s = j.ask(PROMPTS["F"])
        a = s["current_learning_state"]
        check(not a["practice_active"] and not a["pending_question"], "Cancelled question remained")
        check("cofactor" in s["session_goal"]["goal"].lower(), "Topic shift did not update goal")
        check(s["teaching_plan"]["next_move"] != "practice", "Continued obsolete practice")
    elif label == "G":
        j.create(topic="")
        s = j.ask(PROMPTS["G"])
        check(s["current_learning_state"]["pending_question_kind"] != "exit_check", "Mixed teaching mistaken for exit")
        check(s["teaching_plan"]["reason"] != "student_reports_understanding", "Incorrect teaching classification")
        t = j.steps[-1]["visible_response"].lower()
        check("independen" in t and ("basis" in t or "span" in t), "Did not address linear independence")
    elif label in {"H","I"}:
        j.ask("Explain why positive multipliers are stored in L in LU factorization.")
        s = j.ask(PROMPTS["H"])
        a = s["current_learning_state"]
        check(a["pending_question_kind"] == "exit_check" and a["exit_check_count"] == 1, "Exit check was not unique")
        check(s["session_goal"]["status"] != "likely_met", "Self-report was accepted as mastery")
        s = j.ask("L stores positive multipliers because LU reverses elimination subtractions to reconstruct A.")
        check(s["session_goal"]["status"] == "likely_met", "Evaluated correct exit answer not accepted")
        if label == "I":
            s = j.ask(PROMPTS["I"])
            check(s["session_goal"]["status"] == "unresolved", "Fresh confusion did not reopen goal")
    elif label == "J":
        j.create(policy="source_only",mode="concept",topic="")
        j.ask("Explain LU factorization.")
        s = j.ask(PROMPTS["J"])
        check(s["current_learning_state"]["pending_question_kind"] == "exit_check", "No neutral exit check under strict sources")
        check(s["recent_turns"][-1]["support_level"] == "insufficient", "Unsupported response claimed project grounding")
        check(len(j.provider.requests) == 0, "Provider called despite missing strict source")
    elif label == "K":
        s = j.ask(PROMPTS["K"])
        v = s["current_learning_state"]["last_math_verification"]
        check(v in {"passed","repaired"}, "LU was not mathematically verified; state="+str(v))
        check(j.page.locator(".assessment-matrix").count() >= 2, "Verified LU matrices were not readable")
    else:
        raise ValueError("Unknown scenario")
    check(not j.errors, "Browser errors: " + repr(j.errors))


@pytest.mark.parametrize("label", list("ABCDEFGHIJK"))
def test_real_gemini_A_to_K(label, live_journey):
    """Model-specific observed verdict, separate from existing scripted test certificates."""
    j = live_journey
    report = {
        "scenario": label, "source_sha": subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
        "model": EXPECTED_MODEL, "provider": "real Gemini OpenAI-compatible HTTP",
        "viewport_width": 1366, "installed_data_used": False, "result": "FAIL",
    }
    try:
        teaching_case(label,j)
        report["result"] = "PASS"
    except Exception as exc:
        secret = os.getenv("LLM_API_KEY","")
        cause = j.provider.last_error or str(exc)
        cause = cause.replace(secret,"[REDACTED]") if secret else cause
        report["reason"] = cause[:350]
        report["result"] = "BLOCKED" if any(v in cause.lower() for v in ("429","quota","rate limit","call cap","not configured","403")) else "FAIL"
        raise
    finally:
        report["real_provider_calls"] = len(j.provider.requests)
        report["real_run_total_calls"] = RealGemini.calls
        report["steps"] = j.steps
        report["browser_errors"] = j.errors
        report["retrieval_requests"] = len(j.retrieval.queries)
        try:
            j.page.screenshot(path=str(OUTPUT / f"tutor-GEMINI-{label}-1366.png"),full_page=True)
        except Exception:
            pass
        (OUTPUT / f"tutor-GEMINI-{label}-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(f"Genuine model scenario {label}: {report['result']} (calls={report['real_provider_calls']})")
