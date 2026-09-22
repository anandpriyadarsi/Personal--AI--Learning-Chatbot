from __future__ import annotations

import sqlite3

from personal_learning_assistant.domain.tutor_models import TutorSessionSpec
from personal_learning_assistant.repositories.sqlite.migration_runner import (
    apply_migrations,
)
from personal_learning_assistant.repositories.sqlite.tutor_repository import (
    SQLiteTutorRepository,
)
from personal_learning_assistant.services.tutor_session_service import (
    TutorSessionService,
)
from personal_learning_assistant.tutor.personalized_policy import (
    build_personalized_teaching_policy,
    teaching_policy_instruction,
    teaching_policy_mapping,
    teaching_policy_prompt,
)


def _model(*, memory=(), stable=()):
    return {
        "learning_memory": tuple(memory),
        "stable_signals": tuple(stable),
    }


def _signal(kind, *, text="", sessions=2, events=2):
    return {
        "kind": kind,
        "text": text,
        "course_id": "course-ma",
        "topic_id": "topic-lu",
        "session_count": sessions,
        "event_count": events,
        "first_observed_at": "2026-09-20T10:00:00Z",
        "last_observed_at": "2026-09-22T18:00:00Z",
        "provenance": ("s1:t1", "s2:t2"),
    }


def test_default_policy_is_neutral():
    policy = build_personalized_teaching_policy(
        _model(),
        {},
        teaching_intent="explain",
    )
    view = teaching_policy_mapping(policy)

    assert view["scaffolding"] == "standard"
    assert view["prerequisite_depth"] == "normal"
    assert view["explanation_style"] == "balanced"
    assert view["practice_difficulty"] == "standard"
    assert view["quiz_progression"] == "normal"
    assert view["reasons"] == ()


def test_repeated_hint_signal_increases_scaffolding_without_claiming_mastery():
    policy = build_personalized_teaching_policy(
        _model(stable=(_signal("hint_requested"),)),
        {},
        teaching_intent="explain",
    )
    view = teaching_policy_mapping(policy)
    prompt = teaching_policy_prompt(policy)
    instruction = teaching_policy_instruction(policy)

    assert view["scaffolding"] == "guided"
    assert view["prerequisite_depth"] == "brief_reinforcement"
    assert view["practice_difficulty"] == "supported"
    assert view["quiz_progression"] == "hold"
    assert "repeated_historical_support_signal" in view["reasons"]
    assert "scaffolding=guided" in prompt
    assert "Never replace the current question" in instruction
    assert "proof of mastery" in instruction


def test_accepted_misconception_memory_is_available_for_targeted_revisit():
    policy = build_personalized_teaching_policy(
        _model(
            memory=(
                "misconception / LU Factorization: Recurring misconception: "
                "Confuses L with the eliminated matrix.",
            )
        ),
        {},
        teaching_intent="explain",
    )
    view = teaching_policy_mapping(policy)

    assert view["scaffolding"] == "guided"
    assert len(view["revisit_misconceptions"]) == 1
    assert "Confuses L with the eliminated matrix" in view[
        "revisit_misconceptions"
    ][0]
    assert "only if it is directly relevant" in teaching_policy_instruction(
        policy
    )


def test_historical_strength_alone_never_escalates_difficulty():
    policy = build_personalized_teaching_policy(
        _model(stable=(_signal("answer_correct", sessions=4, events=5),)),
        {},
        teaching_intent="quiz",
    )
    view = teaching_policy_mapping(policy)

    assert view["scaffolding"] == "standard"
    assert view["practice_difficulty"] == "standard"
    assert view["quiz_progression"] == "normal"
    assert "current_success_plus_repeated_strength" not in view["reasons"]


def test_current_success_plus_repeated_strength_allows_modest_challenge():
    policy = build_personalized_teaching_policy(
        _model(
            stable=(
                _signal("answer_correct", sessions=3, events=4),
                _signal("math_verified", sessions=2, events=3),
            )
        ),
        {
            "answer_status": "correct",
            "last_math_verification": "passed",
        },
        teaching_intent="quiz_answer",
    )
    view = teaching_policy_mapping(policy)
    instruction = teaching_policy_instruction(policy)

    assert view["scaffolding"] == "light"
    assert view["prerequisite_depth"] == "minimal"
    assert view["practice_difficulty"] == "challenge"
    assert view["quiz_progression"] == "advance"
    assert "current_success_plus_repeated_strength" in view["reasons"]
    assert "one modest step harder" in instruction


def test_current_confusion_overrides_historical_strength():
    policy = build_personalized_teaching_policy(
        _model(
            stable=(
                _signal("answer_correct", sessions=5, events=7),
                _signal("math_verified", sessions=4, events=6),
            )
        ),
        {
            "answer_status": "incorrect",
            "last_misconception": "Uses a row operation with the wrong multiplier.",
            "last_math_verification": "blocked",
        },
        teaching_intent="quiz_answer",
    )
    view = teaching_policy_mapping(policy)

    assert view["scaffolding"] == "guided"
    assert view["prerequisite_depth"] == "reinforce"
    assert view["practice_difficulty"] == "supported"
    assert view["quiz_progression"] == "slow"
    assert "current_session_needs_support" in view["reasons"]
    assert "current_success_plus_repeated_strength" not in view["reasons"]


def test_hint_intent_can_request_guidance_without_historical_profile():
    policy = build_personalized_teaching_policy(
        _model(),
        {},
        teaching_intent="hint",
    )
    view = teaching_policy_mapping(policy)

    assert view["scaffolding"] == "guided"
    assert view["explanation_style"] == "intuition_then_steps"
    assert "current_teaching_intent_requests_support" in view["reasons"]


class _EmptyRetrieval:
    def search(self, *args, **kwargs):
        return ()


def _database(tmp_path):
    path = tmp_path / "tutor22_policy.db"
    apply_migrations(path)
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(
        "INSERT INTO courses("
        "id,code,name,status,created_at,updated_at,deleted_at"
        ") VALUES (?,?,?,'active',?,?,NULL)",
        (
            "course-ma",
            "MA103N",
            "Linear Algebra",
            "2026-09-01T00:00:00Z",
            "2026-09-01T00:00:00Z",
        ),
    )
    connection.execute(
        "INSERT INTO topics("
        "id,course_id,name,normalized_name,position,status,confidence,"
        "raw_import_status,created_at,updated_at,deleted_at"
        ") VALUES (?,?,?,?,1,'active',3,NULL,?,?,NULL)",
        (
            "topic-lu",
            "course-ma",
            "LU Factorization",
            "lu factorization",
            "2026-09-01T00:00:00Z",
            "2026-09-01T00:00:00Z",
        ),
    )
    repository = SQLiteTutorRepository(connection)
    sessions = TutorSessionService(
        repository,
        now=lambda: "2026-09-23T00:00:00Z",
    )
    return connection, repository, sessions


def test_grounding_plan_and_provider_request_carry_same_personalized_policy(
    tmp_path,
):
    from personal_learning_assistant.tutor.grounding import TutorGroundingPlanner

    connection, repository, sessions = _database(tmp_path)

    repository.create_session(
        session_id="old-lu-1",
        course_id="course-ma",
        topic_id="topic-lu",
        assessment_id=None,
        resource_id=None,
        mode="doubt",
        source_policy="source_first",
        title="old 1",
        metadata_json=(
            '{"adaptive_tutor_state":{"last_intent":"hint",'
            '"answer_status":"partial"}}'
        ),
        created_at="2026-09-20T00:00:00Z",
    )
    repository.create_session(
        session_id="old-lu-2",
        course_id="course-ma",
        topic_id="topic-lu",
        assessment_id=None,
        resource_id=None,
        mode="doubt",
        source_policy="source_first",
        title="old 2",
        metadata_json=(
            '{"adaptive_tutor_state":{"last_intent":"hint",'
            '"answer_status":"partial"}}'
        ),
        created_at="2026-09-21T00:00:00Z",
    )
    current = repository.create_session(
        session_id="current-lu",
        course_id="course-ma",
        topic_id="topic-lu",
        assessment_id=None,
        resource_id=None,
        mode="doubt",
        source_policy="source_first",
        title="current",
        metadata_json="{}",
        created_at="2026-09-23T00:00:00Z",
    )

    planner = TutorGroundingPlanner(_EmptyRetrieval(), sessions)
    plan = planner.plan(
        current,
        "Explain why elimination multipliers are stored in L.",
        transcript=(),
    )
    request = planner.provider_request(current, plan, transcript=())

    assert plan.teaching_policy["scaffolding"] == "guided"
    assert plan.teaching_policy["practice_difficulty"] == "supported"
    assert request.metadata["teaching_policy"] == plan.teaching_policy

    prompt = request.messages[-1]["content"]
    assert "PERSONALIZED TEACHING POLICY" in prompt
    assert "scaffolding=guided" in prompt
    assert "CURRENT QUESTION" in prompt
    assert "Explain why elimination multipliers are stored in L." in prompt
    assert "Never replace the current question" in prompt
    connection.close()


def test_building_personalized_plan_is_read_only(tmp_path):
    from personal_learning_assistant.tutor.grounding import TutorGroundingPlanner

    connection, repository, sessions = _database(tmp_path)
    current = repository.create_session(
        session_id="current-lu",
        course_id="course-ma",
        topic_id="topic-lu",
        assessment_id=None,
        resource_id=None,
        mode="doubt",
        source_policy="source_first",
        title="current",
        metadata_json="{}",
        created_at="2026-09-23T00:00:00Z",
    )
    before = connection.total_changes

    plan = TutorGroundingPlanner(_EmptyRetrieval(), sessions).plan(
        current,
        "Explain LU factorization.",
        transcript=(),
    )

    assert plan.teaching_policy["scaffolding"] == "standard"
    assert connection.total_changes == before
    connection.close()
