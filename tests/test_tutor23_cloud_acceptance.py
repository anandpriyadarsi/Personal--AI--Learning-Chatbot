"""A–K through real Flask/Chromium/SQLite, with explicitly scripted providers.

These tests certify orchestration contracts, NOT configured-LLM pedagogy.
Every scenario owns a new synthetic database; no installed database is copied.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
from threading import Thread

import pytest
from playwright.sync_api import expect
from werkzeug.serving import make_server

from personal_learning_assistant.ui.web import create_app
from tests.learning_studio.test_browser import browser
from tests.test_phase7_5_academic_agent_web import build_test_web_service, open_database, table_counts
from tests.test_tutor21_correctness import SequenceProvider
from tutor23_live_inspect import inspect_session

pytestmark = pytest.mark.skipif(os.environ.get("ANVAYA_BROWSER_TESTS") != "1",
                              reason="Requires actual Chromium: ANVAYA_BROWSER_TESTS=1")

PROMPTS = {
    "A": "I don't understand LU factorization. Help me figure out what part I am missing before you explain everything.",
    "B": "Give me one hint only. Keep the question for me to answer.",
    "C": "I understand Gaussian elimination, but I do not understand elimination multipliers in LU factorization. Explain only what I need so I can return to LU.",
    "D": "Give me one computational practice problem on elimination multipliers in LU factorization. Wait for my answer.",
    "E": "Give me a harder computational practice problem. One problem only.",
    "F": "Skip the practice question. Now explain determinant expansion by cofactors. Do not continue LU.",
    "G": "I understand span but why does a basis need linear independence?",
    "H": "I understand it now.",
    "I": "I am still confused about why the elimination multiplier appears with a positive sign in L.",
    "J": "Check if I understand this.",
    "K": "Take the matrix A = [[2,1,1],[4,3,3],[8,7,9]]. Compute its LU factorization step by step and verify that LU = A before giving the final result.",
}


def evaluation(status, text):
    return '<!--ANVAYA_EVAL ' + json.dumps({"status": status, "reason": "Scripted acceptance evaluation"}) + '-->' + text


def lu_answer(*, wrong=False):
    left = [[1, 0, 0], [2, 1, 0], [4, 3, 1]]
    # R3 - 4R1 = [0,3,5]; its second multiplier is 3.
    upper = [[2, 1, 1], [0, 1, 1], [0, 0, 3 if wrong else 2]]
    claim = {"type": "matrix_product", "left": left, "right": upper,
             "result": [[2, 1, 1], [4, 3, 3], [8, 7, 9]]}
    marker = '<!--ANVAYA_MATH ' + json.dumps({"claims": [claim]}) + '-->'
    if wrong:
        return marker + "This deliberately faulty scripted factorization must never reach the student."
    return marker + (
        "## LU factorisation\n\n"
        r"Use $m_{21}=2$, $m_{31}=4$, then $m_{32}=3$. "
        "Subtract twice row 1 from row 2, four times row 1 from row 3, "
        "then three times the new row 2 from row 3.\n\n"
        r"\[L=\begin{bmatrix}1&0&0\\2&1&0\\4&3&1\end{bmatrix}\]" "\n\n"
        r"\[U=\begin{bmatrix}2&1&1\\0&1&1\\0&0&2\end{bmatrix}\]" "\n\n"
        r"\[LU=\begin{bmatrix}2&1&1\\4&3&3\\8&7&9\end{bmatrix}=A\]"
    )


def protected_hashes(connection):
    """Detect updates/deletes too, rather than relying only on row counts."""
    allowed = {"tutor_sessions", "tutor_turns", "tutor_evidence_links", "tutor_feedback"}
    result = {}
    for name in table_counts(connection):
        if name in allowed:
            continue
        rows = sorted(repr(tuple(row)) for row in connection.execute('SELECT * FROM "' + name + '"'))
        result[name] = hashlib.sha256("\n".join(rows).encode()).hexdigest()
    return result


class Journey:
    def __init__(self, page, base, path, provider, output, width):
        self.page, self.base, self.path = page, base, path
        self.provider, self.output, self.width = provider, output, width
        self.session_id = None
        self.steps = []
        self.errors = []
        page.on("pageerror", lambda error: self.errors.append(str(error)))
        page.on("response", lambda response: self.errors.append(f"HTTP {response.status}")
                if response.status >= 500 else None)

    def create(self, policy="source_first", mode="doubt", topic="synthetic-topic-2"):
        self.page.goto(self.base + "/agent")
        self.page.locator("#session-course").select_option("synthetic-ma")
        self.page.locator("#session-topic").select_option(topic)
        self.page.locator("#session-policy").select_option(policy)
        self.page.locator("#session-mode").select_option(mode)
        self.page.locator("#session-title").fill("Disposable A–K acceptance · scripted provider")
        self.page.get_by_role("button", name="Create tutor session").click()
        self.session_id = self.page.url.rsplit("/", 1)[-1]
        assert self.page.locator(".error-panel").count() == 0
        assert self.state()["session"]["topic_id"] == (topic or None)
        if topic:
            expect(self.page.locator(".metric-grid")).to_contain_text("Topic: LU Factorization")

    def state(self):
        return inspect_session(self.path, self.session_id)

    def ask(self, question, response=None):
        if response is not None:
            self.provider.responses.append(response)
        self.page.locator("#agent-question").fill(question)
        self.page.get_by_role("button", name="Ask tutor", exact=True).click()
        expect(self.page.locator("#agent-question")).to_be_visible()
        assert self.page.locator(".error-panel").count() == 0
        state = self.state()
        visible = self.page.locator(".agent-turn-assistant .agent-message").last.inner_text()
        self.steps.append({"question": question, "visible_response": visible, "persisted_state": state})
        assert state["all_state_checks_pass"], state["state_checks"]
        assert "ANVAYA_EVAL" not in visible and "ANVAYA_MATH" not in visible
        # Refresh must preserve the exact turn count and question, with no provider call.
        calls = len(self.provider.requests)
        self.page.reload()
        assert self.state() == state
        assert len(self.provider.requests) == calls
        pending = state["current_learning_state"]["pending_question"]
        if pending:
            expect(self.page.locator(".tutor-pending-question p")).to_have_text(pending)
        else:
            assert self.page.locator(".tutor-pending-question").count() == 0
        assert self.page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        # Visual acceptance: never ship a tiny 150px Tutor input in a wide form.
        # Inspect actual layout after Chromium paints, not just source CSS.
        assert self.page.locator("#agent-question").evaluate(
            "(el) => { const form = el.closest('form');"
            " const width = el.getBoundingClientRect().width;"
            " const available = form.getBoundingClientRect().width;"
            " return width >= 0.85 * available && width <= available + 1; }"
        )
        return state

    def snapshot(self, label):
        if not self.output:
            return
        self.output.mkdir(parents=True, exist_ok=True)
        stem = f"tutor-AK-{label}-{self.width}"
        self.page.screenshot(path=str(self.output / (stem + ".png")), full_page=True)
        (self.output / (stem + ".json")).write_text(json.dumps(self.steps[-1] if self.steps else {}, indent=2), encoding="utf-8")

    @contextmanager
    def scenario(self, label, expected):
        result = "FAIL"
        try:
            yield
            assert not self.errors, self.errors
            result = "PASS"
        finally:
            if self.output:
                self.snapshot(label)
                report = {"scenario": label, "expected": expected, "browser_contract_result": result,
                          "configured_provider_result": "BLOCKED: no real provider used; scripted boundary only",
                          "source_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                          "platform": platform.platform(), "viewport_width": self.width,
                          "provider": "SequenceProvider (scripted; not an LLM)",
                          "provider_calls": len(self.provider.requests), "browser_errors": self.errors,
                          "steps": self.steps}
                (self.output / f"tutor-AK-{label}-{self.width}-report.json").write_text(
                    json.dumps(report, indent=2), encoding="utf-8")


@pytest.fixture(params=[390, 768, 1366])
def journey(browser, tmp_path, request):
    provider = SequenceProvider([])
    service, path, _, _, retrieval = build_test_web_service(tmp_path, provider=provider)
    connection = open_database(path)
    for position, name in enumerate(("LU Factorization", "Gaussian Elimination", "Elimination Multipliers"), 2):
        connection.execute("INSERT INTO topics(id,course_id,name,normalized_name,position,status,created_at,updated_at) "
                           "VALUES(?,?,?,?,?,'not_started',?,?)",
                           (f"synthetic-topic-{position}", "synthetic-ma", name, name.lower(), position,
                            "2026-10-22T00:00:00Z", "2026-10-22T00:00:00Z"))
    before = protected_hashes(connection)
    counts = table_counts(connection)
    connection.close()
    # Observe every actual retrieval request, while returning no synthetic grounding.
    retrieval.queries = []
    def search(query, **kwargs):
        retrieval.queries.append({"query": query, **kwargs})
        return ()
    retrieval.search = search
    application = create_app({"TESTING": True, "ACADEMIC_AGENT_WEB_SERVICE_FACTORY": lambda: service})
    server = make_server("127.0.0.1", 0, application, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    page = browser.new_page(viewport={"width": request.param, "height": 950})
    root = os.environ.get("ANVAYA_VALIDATION_ARTIFACTS")
    run = Journey(page, f"http://127.0.0.1:{server.server_port}", path, provider,
                  Path(root) if root else None, request.param)
    run.retrieval = retrieval
    try:
        run.create()
        yield run
    finally:
        page.close()
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        connection = open_database(path)
        try:
            assert protected_hashes(connection) == before
            assert "tutor_memory_candidates" not in table_counts(connection)
            if run.output:
                (run.output / f"{request.node.name}-safety.json").write_text(json.dumps({
                    "protected_hashes_before": before, "protected_hashes_after": protected_hashes(connection),
                    "counts_before": counts, "counts_after": table_counts(connection),
                    "installed_data_accessed": False, "optional_tutor_migration_applied": False,
                }, indent=2), encoding="utf-8")
        finally:
            connection.close()


def test_scenario_A_diagnostic(journey):
    with journey.scenario("A", "One diagnostic, persisted pending question, no provider call"):
        state = journey.ask(PROMPTS["A"])
        assert state["teaching_plan"]["next_move"] == "ask_diagnostic"
        assert state["current_learning_state"]["pending_question_kind"] == "diagnostic"
        assert journey.steps[-1]["visible_response"].count("?") == 1
        assert not journey.provider.requests


def test_scenario_B_hint_and_socratic_continuation(journey):
    with journey.scenario("B", "Hint preserves diagnostic, actual reply follows Socratic lineage"):
        original = journey.ask(PROMPTS["A"])["current_learning_state"]["pending_question"]
        state = journey.ask(PROMPTS["B"], "Think about which elimination step is unclear; keep the original question.")
        assert state["current_learning_state"]["pending_question"] == original
        journey.snapshot("B-hint")
        state = journey.ask("I know elimination but cannot connect the multiplier to L.",
                            evaluation("partial", "L records each multiplier. What multiplier eliminates 6 below pivot 2?"))
        assert state["current_learning_state"]["last_socratic_outcome"] in {"advance", "clarify", "repair", "unclear"}
        assert state["teaching_plan"]["reason"] == "pending_socratic_answer"
        assert journey.steps[-1]["visible_response"].count("?") <= 1


def test_scenario_C_prerequisite_and_short_answer(journey):
    with journey.scenario("C", "Scoped multiplier repair; pending follow-up survives refresh and evaluates 3"):
        state = journey.ask(PROMPTS["C"], "Divide the entry by the pivot. Store the multiplier in L to return to LU. What multiplier eliminates 6 below pivot 2?")
        plan = state["teaching_plan"]
        assert plan["next_move"] == "review_prerequisite"
        assert plan["prerequisite_concept"] == "Elimination Multipliers"
        assert plan["target_concept"] == "LU Factorization" and plan["return_to_goal"]
        assert state["current_learning_state"]["pending_question_kind"] == "socratic_check"
        scoped = [q for q in journey.retrieval.queries if q.get("topic_ids")]
        assert scoped and all(q["topic_ids"] == ("synthetic-topic-4",) for q in scoped)
        assert all(q.get("course_ids") == ("synthetic-ma",) for q in journey.retrieval.queries)
        journey.snapshot("C-prerequisite")
        state = journey.ask("3", evaluation("correct", "Correct. Put 3 in the corresponding position of L and continue LU."))
        assert state["current_learning_state"]["answer_status"] == "correct"
        assert state["teaching_plan"]["reason"] == "pending_socratic_answer"


def begin_practice(journey):
    return journey.ask(PROMPTS["D"], "What multiplier eliminates 6 below pivot 2?")


def test_scenario_D_adaptive_computational_practice(journey):
    with journey.scenario("D", "One unsolved computational task; correct +1, incorrect -1, bounded 1..5"):
        state = begin_practice(journey)
        adaptive = state["current_learning_state"]
        assert adaptive["pending_question_kind"] == "practice" and adaptive["practice_active"]
        assert adaptive["practice_format"] == "computational"
        level = adaptive["practice_level"]
        assert 1 <= level <= 5
        assert "3" not in journey.steps[-1]["visible_response"]
        journey.snapshot("D-problem")
        state = journey.ask("3", evaluation("correct", "Correct. What multiplier eliminates 8 below pivot 2?"))
        next_level = state["current_learning_state"]["practice_level"]
        assert next_level == min(5, level + 1)
        journey.snapshot("D-correct")
        state = journey.ask("0.25", evaluation("incorrect", "Divide entry by pivot. What multiplier eliminates 4 below pivot 2?"))
        assert state["current_learning_state"]["practice_level"] == max(1, next_level - 1)
        assert journey.steps[-1]["visible_response"].count("?") <= 1


def test_scenario_E_explicit_easier_harder(journey):
    with journey.scenario("E", "Explicit harder/easier retains computational format, changes level by one"):
        level = begin_practice(journey)["current_learning_state"]["practice_level"]
        state = journey.ask(PROMPTS["E"], "What multiplier eliminates 15 below pivot 3?")
        harder = state["current_learning_state"]
        assert harder["practice_level"] == min(5, level + 1)
        assert harder["practice_format"] == "computational"
        journey.snapshot("E-harder")
        state = journey.ask("Give me an easier computational practice problem. One problem only.", "What multiplier eliminates 4 below pivot 2?")
        assert state["current_learning_state"]["practice_level"] == max(1, harder["practice_level"] - 1)
        assert state["current_learning_state"]["practice_format"] == "computational"


def test_scenario_F_topic_shift(journey):
    with journey.scenario("F", "Skip clears obsolete pending/practice and replaces LU goal with cofactor goal"):
        journey.create(topic="")
        begin_practice(journey)
        state = journey.ask(PROMPTS["F"], "Cofactor expansion sums signed minors multiplied by entries from one row or column.")
        adaptive = state["current_learning_state"]
        assert not adaptive["practice_active"]
        assert adaptive["pending_question"] == adaptive["pending_question_kind"] == ""
        assert "cofactor" in state["session_goal"]["goal"].lower()
        assert state["teaching_plan"]["next_move"] != "practice"
        journey.snapshot("F-topic-shift")
        journey.create(topic="")
        begin_practice(journey)
        state = journey.ask(
            "Skip the practice question. Please explain determinant expansion by cofactors. Do not continue LU.",
            "Cofactor expansion combines entries with their signed minors.",
        )
        assert state["current_learning_state"]["last_intent"] == "explain"
        assert state["teaching_plan"]["next_move"] != "practice"
        assert "cofactor" in state["session_goal"]["goal"].lower()
        journey.snapshot("F-polite")
        journey.create(topic="")
        goal = begin_practice(journey)["session_goal"]["goal"]
        calls = len(journey.provider.requests)
        state = journey.ask("Skip the practice question.")
        assert len(journey.provider.requests) == calls
        assert not state["current_learning_state"]["practice_active"]
        assert state["current_learning_state"]["pending_question"] == ""
        assert state["session_goal"]["goal"] == goal
        assert state["teaching_plan"]["reason"] == "student_cancelled_pending"


def test_scenario_G_mixed_understanding_remains_teaching(journey):
    with journey.scenario("G", "Mixed understanding plus basis question is teaching, not an exit check"):
        journey.create(topic="")
        state = journey.ask(PROMPTS["G"], "Linear independence removes redundant vectors; spanning alone permits redundancy.")
        assert state["current_learning_state"]["pending_question_kind"] != "exit_check"
        assert state["teaching_plan"]["reason"] != "student_reports_understanding"
        assert "redundan" in journey.steps[-1]["visible_response"]


def exit_check(journey):
    journey.ask("Explain why the elimination multipliers are stored in L in LU factorization.",
                "L records the multipliers used during elimination; reversing those row operations reconstructs A from U.")
    state = journey.ask(PROMPTS["H"])
    assert state["session_goal"]["status"] in {"active", "unresolved"}
    assert state["current_learning_state"]["pending_question_kind"] == "exit_check"
    assert journey.steps[-1]["visible_response"].count("?") == 1
    journey.snapshot("H-exit-check")
    return journey.ask("L stores positive multipliers because it reverses the subtraction row operations used to produce U.",
                       evaluation("correct", "That meets this session check; this is not mastery."))


def test_scenario_H_exit_check_not_mastery(journey):
    with journey.scenario("H", "Self report waits for one exit check; correct answer gives session-local likely_met"):
        state = exit_check(journey)
        assert state["session_goal"]["status"] == "likely_met"
        assert state["current_learning_state"]["pending_question_kind"] == ""
        assert state["current_learning_state"]["exit_check_count"] == 1
        expect(journey.page.locator(".tutor-learning-status")).to_contain_text("Session evidence, not mastery")


def test_scenario_I_goal_can_reopen(journey):
    with journey.scenario("I", "New confusion reopens likely_met as unresolved with qualified evidence"):
        assert exit_check(journey)["session_goal"]["status"] == "likely_met"
        state = journey.ask(PROMPTS["I"], "Elimination subtracts the multiplier; reconstruction adds it back, which explains the positive sign in L.")
        assert state["session_goal"]["status"] == "unresolved"
        assert any(e.startswith("student_reported_unresolved:") for e in state["session_goal"]["goal_evidence"])


def test_scenario_J_strict_source_neutral_check(journey):
    with journey.scenario("J", "Strict Source Only offers neutral deterministic exit check without sources or provider"):
        journey.create(policy="source_only", mode="concept", topic="")
        journey.ask("Explain LU factorization.")
        state = journey.ask(PROMPTS["J"])
        assert state["current_learning_state"]["pending_question_kind"] == "exit_check"
        assert state["recent_turns"][-1]["support_level"] == "insufficient"
        assert state["recent_turns"][-1]["evidence_count"] == 0
        assert not journey.provider.requests
        assert "Exit check" in journey.page.locator(".tutor-pending-question").inner_text()


@pytest.mark.parametrize("verification", ["passed", "repaired", "blocked"])
def test_scenario_K_lu_math_and_repair(journey, verification):
    with journey.scenario("K-" + verification, "Correct 3x3 LU renders; one repair or fail closed, no hidden metadata/500"):
        if verification != "passed":
            journey.provider.responses.append(lu_answer(wrong=True))
        response = lu_answer(wrong=verification == "blocked")
        state = journey.ask(PROMPTS["K"], response)
        assert state["current_learning_state"]["last_math_verification"] == verification
        visible = journey.steps[-1]["visible_response"]
        assert "deliberately faulty" not in visible
        if verification != "blocked":
            assert journey.page.locator(".tutor-markdown .assessment-matrix").count() == 3
            assert journey.page.locator(".tutor-markdown .assessment-matrix-cell").all_text_contents() == [
                "1", "0", "0", "2", "1", "0", "4", "3", "1",
                "2", "1", "1", "0", "1", "1", "0", "0", "2",
                "2", "1", "1", "4", "3", "3", "8", "7", "9"]
            assert "\\begin" not in visible and "\\[" not in visible
        assert len(journey.provider.requests) == (1 if verification == "passed" else 2)



def test_scenario_K_ascii_rows_render_as_matrices_in_browser(journey):
    """A genuine provider can emit bracketed ASCII rows instead of TeX."""
    with journey.scenario(
        "K-ascii",
        "3x3 ASCII A/L/U rows render as readable math, across all viewports and refresh",
    ):
        # Reuse the already-correct deterministic matrix-product claim, but
        # deliberately replace the visible TeX with model-style ASCII rows.
        verified_claim = lu_answer().split("-->", 1)[0] + "-->"
        provider_text = (
            "## Verified LU factorization\n\n"
            "A = [2 1 1]\n[4 3 3]\n[8 7 9]\n\n"
            "L = [1 0 0]\n[2 1 0]\n[4 3 1]\n\n"
            "U = [2 1 1]\n[0 1 1]\n[0 0 2]\n\n"
            "The product LU reproduces A."
        )
        state = journey.ask(PROMPTS["K"], verified_claim + provider_text)
        assert state["current_learning_state"]["last_math_verification"] == "passed"
        matrices = journey.page.locator(".tutor-markdown .assessment-matrix")
        assert matrices.count() == 3, "The ASCII A, L and U blocks must become DOM matrices"
        assert matrices.nth(1).locator(".assessment-matrix-cell").all_text_contents() == [
            "1", "0", "0", "2", "1", "0", "4", "3", "1",
        ]
        assert matrices.nth(2).locator(".assessment-matrix-cell").all_text_contents() == [
            "2", "1", "1", "0", "1", "1", "0", "0", "2",
        ]
        assert r"\begin{bmatrix}" not in journey.steps[-1]["visible_response"]
        assert not journey.errors


def test_unconfigured_http_provider_is_truthful_in_browser(browser, tmp_path):
    from personal_learning_assistant.tutor.http_provider import OpenAICompatibleTutorProvider
    # Use the actual HTTP adapter, explicitly unconfigured, without a network mock.
    # Configuration availability is reported as booleans only; never export values.
    available = {key: bool(os.environ.get(key, "").strip())
                 for key in ("LLM_API_URL", "LLM_API_KEY", "LLM_MODEL")}
    provider = OpenAICompatibleTutorProvider(api_url="", api_key="", model="")
    service, path, course, _, _ = build_test_web_service(tmp_path, provider=provider)
    app = create_app({"TESTING": True, "ACADEMIC_AGENT_WEB_SERVICE_FACTORY": lambda: service})
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    page = browser.new_page(viewport={"width": 390, "height": 950})
    connection = open_database(path)
    protected = protected_hashes(connection)
    connection.close()
    try:
        page.goto(f"http://127.0.0.1:{server.server_port}/agent")
        expect(page.get_by_text("Not configured", exact=True)).to_be_visible()
        page.locator("#session-course").select_option(course["id"])
        page.get_by_role("button", name="Create tutor session").click()
        session_id = page.url.rsplit("/", 1)[-1]
        before = inspect_session(path, session_id)
        page.locator("#agent-question").fill("Explain why multipliers go into L.")
        page.get_by_role("button", name="Ask tutor", exact=True).click()
        expect(page.locator(".error-panel")).to_contain_text("not configured")
        after = inspect_session(path, session_id)
        assert after == before  # A failed provider call cannot save partial turns/state.
        folder = os.environ.get("ANVAYA_VALIDATION_ARTIFACTS")
        if folder:
            root = Path(folder)
            root.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(root / "tutor-provider-unconfigured-390.png"), full_page=True)
            (root / "tutor-provider-availability.json").write_text(json.dumps({
                "configuration_presence_only": available,
                "actual_adapter_unconfigured_ux": "PASS",
                "configured_provider_A_K": "BLOCKED" if not all(available.values()) else "NOT_RUN",
                "provider_calls_charged": 0, "persisted_before": before, "persisted_after": after,
            }, indent=2), encoding="utf-8")
    finally:
        page.close()
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        connection = open_database(path)
        assert protected_hashes(connection) == protected
        connection.close()
