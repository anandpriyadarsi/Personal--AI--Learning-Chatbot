from __future__ import annotations

import sqlite3
from pathlib import Path

from personal_learning_assistant.domain.tutor_models import (
    TutorProviderResponse,
    TutorSessionSpec,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import (
    apply_migrations,
)
from personal_learning_assistant.repositories.sqlite.tutor_repository import (
    SQLiteTutorRepository,
)
from personal_learning_assistant.services.grounded_tutor_service import (
    GroundedTutorService,
)
from personal_learning_assistant.services.tutor_session_service import (
    TutorSessionService,
)
from personal_learning_assistant.tutor.concept_dependencies import (
    course_context_from_repository,
    plan_prerequisite_review,
    prerequisite_retrieval_query,
)
from personal_learning_assistant.tutor.grounding import TutorGroundingPlanner
from personal_learning_assistant.tutor.teaching_orchestrator import (
    build_teaching_plan,
    load_teaching_plan,
)


def _goal():
    return {
        "goal": "Understand LU Factorization",
        "status": "active",
        "goal_evidence": (),
        "source": "inferred",
    }


def _ma_context():
    return {
        "course_id": "course-ma103n",
        "course_code": "MA103N",
        "course_name": "Linear Algebra",
        "selected_topic_id": "topic-lu",
        "selected_topic_name": "LU Factorization",
        "topics": (
            {"id": "topic-lu", "name": "LU Factorization"},
            {"id": "topic-ge", "name": "Gaussian Elimination"},
            {"id": "topic-mult", "name": "Elimination Multipliers"},
            {"id": "topic-mm", "name": "Matrix Multiplication"},
        ),
    }


def test_explicit_prerequisite_gap_selects_one_specific_prerequisite():
    decision = plan_prerequisite_review(
        "I don't understand elimination multipliers in LU factorization.",
        teaching_intent="explain",
        adaptive_state={"interaction_count": 0},
        session_goal=_goal(),
        course_context=_ma_context(),
    )

    assert decision.should_review is True
    assert decision.reason == "explicit_prerequisite_gap"
    assert decision.course_code == "MA103N"
    assert decision.target_concept == "LU Factorization"
    assert decision.prerequisite_concept == "Elimination Multipliers"
    assert decision.target_topic_id == "topic-lu"
    assert decision.prerequisite_topic_id == "topic-mult"
    assert decision.return_to_goal is True


def test_no_course_scope_means_no_automatic_prerequisite_inference():
    decision = plan_prerequisite_review(
        "I don't understand elimination multipliers in LU factorization.",
        teaching_intent="explain",
        adaptive_state={},
        session_goal=_goal(),
        course_context={},
    )

    assert decision.should_review is False
    assert decision.prerequisite_concept == ""


def test_different_course_cannot_leak_linear_algebra_dependency_graph():
    context = {
        "course_id": "course-other",
        "course_code": "UC100N",
        "course_name": "Data Science and AI",
        "selected_topic_name": "LU Factorization",
        "topics": (),
    }
    decision = plan_prerequisite_review(
        "I don't understand elimination multipliers in LU factorization.",
        teaching_intent="explain",
        adaptive_state={},
        session_goal=_goal(),
        course_context=context,
    )

    assert decision.should_review is False


def test_clear_direct_lu_explanation_does_not_force_prerequisite_review():
    decision = plan_prerequisite_review(
        "Explain LU factorization.",
        teaching_intent="explain",
        adaptive_state={},
        session_goal=_goal(),
        course_context=_ma_context(),
    )

    assert decision.should_review is False
    assert decision.target_concept == "LU Factorization"


def test_explicit_hint_request_keeps_hint_authoritative():
    plan = build_teaching_plan(
        "Give me one hint about elimination multipliers in LU factorization.",
        teaching_intent="hint",
        adaptive_state={"interaction_count": 0},
        session_goal=_goal(),
        teaching_policy={},
        course_context=_ma_context(),
    )

    assert plan.next_move == "give_hint"
    assert plan.reason == "current_teaching_intent"
    assert plan.prerequisite_concept == ""


def test_known_prerequisite_gap_beats_generic_diagnostic_question():
    plan = build_teaching_plan(
        "I don't understand elimination multipliers in LU factorization.",
        teaching_intent="explain",
        adaptive_state={"interaction_count": 0},
        session_goal=_goal(),
        teaching_policy={},
        course_context=_ma_context(),
    )

    assert plan.next_move == "review_prerequisite"
    assert plan.reason == "explicit_prerequisite_gap"
    assert plan.diagnostic_question == ""
    assert plan.prerequisite_concept == "Elimination Multipliers"
    assert plan.target_concept == "LU Factorization"


def test_unknown_lu_gap_still_uses_existing_diagnostic_behavior():
    plan = build_teaching_plan(
        "I don't understand LU factorization.",
        teaching_intent="explain",
        adaptive_state={"interaction_count": 0},
        session_goal=_goal(),
        teaching_policy={},
        course_context=_ma_context(),
    )

    assert plan.next_move == "ask_diagnostic"
    assert plan.diagnostic_question


def test_current_session_repair_evidence_can_trigger_prerequisite_review():
    decision = plan_prerequisite_review(
        "Can we continue with LU now?",
        teaching_intent="explain",
        adaptive_state={
            "interaction_count": 3,
            "last_socratic_outcome": "repair",
            "last_misconception": (
                "Student does not understand Gaussian elimination."
            ),
            "last_evaluation_reason": "The elimination step was incorrect.",
        },
        session_goal=_goal(),
        course_context=_ma_context(),
    )

    assert decision.should_review is True
    assert decision.reason == "current_session_prerequisite_gap"
    assert decision.prerequisite_concept == "Gaussian Elimination"
    assert decision.prerequisite_topic_id == "topic-ge"


def test_correct_prior_outcome_does_not_reopen_prerequisite():
    decision = plan_prerequisite_review(
        "Continue with LU.",
        teaching_intent="explain",
        adaptive_state={
            "interaction_count": 3,
            "last_socratic_outcome": "advance",
            "last_misconception": "Gaussian elimination",
        },
        session_goal=_goal(),
        course_context=_ma_context(),
    )

    assert decision.should_review is False


def test_prerequisite_retrieval_query_accepts_teaching_plan_mapping():
    query = prerequisite_retrieval_query(
        {
            "next_move": "review_prerequisite",
            "target_concept": "LU Factorization",
            "prerequisite_concept": "Elimination Multipliers",
        }
    )

    assert query == "Elimination Multipliers prerequisite for LU Factorization"


def test_prerequisite_retrieval_query_is_bounded_and_explicit():
    decision = plan_prerequisite_review(
        "I am confused about Gaussian elimination in LU factorization.",
        teaching_intent="explain",
        adaptive_state={},
        session_goal=_goal(),
        course_context=_ma_context(),
    )

    query = prerequisite_retrieval_query(decision)
    assert query == "Gaussian Elimination prerequisite for LU Factorization"


class RecordingRetrieval:
    def __init__(self):
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return ()


class Provider:
    configured = True

    def __init__(self):
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        return TutorProviderResponse(
            content=(
                "Gaussian elimination removes entries below a pivot. "
                "That is the elimination process LU records in its factors."
            ),
            provider_name="fake-provider",
            provider_model="fake-model",
            request_id="request-1",
        )


def _environment(tmp_path, *, course_code="MA103N"):
    path = tmp_path / "tutor23_fix4.db"
    apply_migrations(path)
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")

    now = "2026-09-23T14:00:00Z"
    connection.execute(
        "INSERT INTO courses("
        "id,code,name,status,description,created_at,updated_at,deleted_at"
        ") VALUES (?,?,?,?,?,?,?,NULL)",
        (
            "course-1",
            course_code,
            "Linear Algebra" if course_code == "MA103N" else "Other Course",
            "active",
            "",
            now,
            now,
        ),
    )

    topic_rows = (
        ("topic-lu", "LU Factorization", "lu factorization", 1),
        ("topic-ge", "Gaussian Elimination", "gaussian elimination", 2),
        ("topic-mult", "Elimination Multipliers", "elimination multipliers", 3),
        ("topic-mm", "Matrix Multiplication", "matrix multiplication", 4),
    )
    for topic_id, name, normalized, position in topic_rows:
        connection.execute(
            "INSERT INTO topics("
            "id,course_id,name,normalized_name,position,status,confidence,"
            "raw_import_status,created_at,updated_at,deleted_at"
            ") VALUES (?,?,?,?,?,'not_started',NULL,NULL,?,?,NULL)",
            (
                topic_id,
                "course-1",
                name,
                normalized,
                position,
                now,
                now,
            ),
        )

    repository = SQLiteTutorRepository(connection)
    counters = {"turn": 0, "other": 0}

    def id_factory(prefix):
        if prefix == "tutor-turn":
            counters["turn"] += 1
            return "turn-{}".format(counters["turn"])
        counters["other"] += 1
        return "{}-{}".format(prefix, counters["other"])

    sessions = TutorSessionService(
        repository,
        now=lambda: now,
        id_factory=id_factory,
    )
    session = sessions.create_session(
        TutorSessionSpec(
            mode="doubt",
            source_policy="source_first",
            course_id="course-1",
            topic_id="topic-lu",
            title="Tutor 2.3.4 prerequisite reasoning",
        )
    )
    retrieval = RecordingRetrieval()
    provider = Provider()
    return connection, repository, sessions, session, retrieval, provider


def test_repository_course_context_uses_canonical_course_and_topic_rows(tmp_path):
    connection, repository, _sessions, session, _retrieval, _provider = (
        _environment(tmp_path)
    )

    context = course_context_from_repository(repository, session)

    assert context["course_code"] == "MA103N"
    assert context["selected_topic_id"] == "topic-lu"
    assert context["selected_topic_name"] == "LU Factorization"
    assert {item["id"] for item in context["topics"]} >= {
        "topic-lu",
        "topic-ge",
        "topic-mult",
    }
    connection.close()


def test_grounding_planner_adds_prerequisite_query_and_uses_prerequisite_topic_scope(
    tmp_path,
):
    connection, _repository, sessions, session, retrieval, _provider = (
        _environment(tmp_path)
    )
    planner = TutorGroundingPlanner(retrieval, sessions)

    plan = planner.plan(
        session,
        "I don't understand elimination multipliers in LU factorization.",
        transcript=(),
    )

    assert plan.teaching_plan["next_move"] == "review_prerequisite"
    assert plan.teaching_plan["target_concept"] == "LU Factorization"
    assert plan.teaching_plan["prerequisite_concept"] == "Elimination Multipliers"
    assert plan.teaching_plan["prerequisite_topic_id"] == "topic-mult"
    assert any(
        query == "Elimination Multipliers prerequisite for LU Factorization"
        for query in plan.retrieval_queries
    )
    assert retrieval.calls
    assert all(
        call[1]["course_ids"] == ("course-1",)
        for call in retrieval.calls
    )
    assert all(
        call[1]["topic_ids"] == ("topic-mult",)
        for call in retrieval.calls
    )
    connection.close()


def test_provider_contract_teaches_minimum_prerequisite_then_returns_to_goal(tmp_path):
    connection, _repository, sessions, session, retrieval, _provider = (
        _environment(tmp_path)
    )
    planner = TutorGroundingPlanner(retrieval, sessions)
    plan = planner.plan(
        session,
        "I don't understand Gaussian elimination in LU factorization.",
        transcript=(),
    )
    request = planner.provider_request(session, plan, transcript=())
    prompt = request.messages[-1]["content"]

    assert "next_move=review_prerequisite" in prompt
    assert "target_concept=LU Factorization" in prompt
    assert "prerequisite_concept=Gaussian Elimination" in prompt
    assert "Repair only the minimum prerequisite needed now" in prompt
    assert "return to the original session goal" in prompt
    assert "Do not recursively descend into another prerequisite" in prompt
    connection.close()


def test_successful_prerequisite_repair_persists_only_tutor_plan_metadata(tmp_path):
    (
        connection,
        repository,
        sessions,
        session,
        retrieval,
        provider,
    ) = _environment(tmp_path)

    before_memory = connection.execute(
        "SELECT COUNT(*) FROM learning_memory_entries"
    ).fetchone()[0]
    before_progress = connection.execute(
        "SELECT COUNT(*) FROM progress_snapshots"
    ).fetchone()[0]

    engine = GroundedTutorService(
        tutor_session_service=sessions,
        retrieval_service=retrieval,
        provider=provider,
    )
    result = engine.answer(
        session.session_id,
        "I don't understand Gaussian elimination in LU factorization.",
    )

    refreshed = repository.get_session(session.session_id)
    plan = load_teaching_plan(refreshed.metadata)

    assert result.assistant_turn.content
    assert plan["next_move"] == "review_prerequisite"
    assert plan["prerequisite_concept"] == "Gaussian Elimination"
    assert plan["target_concept"] == "LU Factorization"
    assert plan["return_to_goal"] is True
    assert connection.execute(
        "SELECT COUNT(*) FROM learning_memory_entries"
    ).fetchone()[0] == before_memory
    assert connection.execute(
        "SELECT COUNT(*) FROM progress_snapshots"
    ).fetchone()[0] == before_progress
    connection.close()


def test_tutor_template_exposes_prerequisite_bridge():
    root = Path(__file__).resolve().parents[1]
    template = (
        root
        / "personal_learning_assistant"
        / "ui"
        / "web"
        / "templates"
        / "agent_session.html"
    ).read_text(encoding="utf-8")

    assert "Prerequisite repair:" in template
    assert "prerequisite_concept" in template
    assert "target_concept" in template
