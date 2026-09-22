from __future__ import annotations

import json
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
from personal_learning_assistant.tutor.student_model import (
    build_persistent_student_model,
    student_model_mapping,
    student_model_prompt,
)


def _course(connection, course_id, code, name):
    connection.execute(
        "INSERT INTO courses("
        "id,code,name,status,created_at,updated_at,deleted_at"
        ") VALUES (?,?,?,'active','2026-09-01T00:00:00Z',"
        "'2026-09-01T00:00:00Z',NULL)",
        (course_id, code, name),
    )


def _env(tmp_path):
    path = tmp_path / "tutor22.db"
    apply_migrations(path)
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    _course(connection, "course-ma", "MA103N", "Linear Algebra")
    _course(connection, "course-ds", "UC100N", "Data Science and AI")
    repository = SQLiteTutorRepository(connection)
    sessions = TutorSessionService(
        repository,
        now=lambda: "2026-09-23T00:00:00Z",
        id_factory=lambda prefix: prefix + "-generated",
    )
    return connection, repository, sessions


def _session(
    sessions,
    *,
    session_id,
    course_id,
    metadata=None,
    updated_at="2026-09-22T20:00:00Z",
):
    repository = sessions.repository
    repository.create_session(
        session_id=session_id,
        course_id=course_id,
        topic_id=None,
        assessment_id=None,
        resource_id=None,
        mode="doubt",
        source_policy="source_first",
        title=session_id,
        metadata_json=json.dumps(metadata or {}),
        created_at=updated_at,
    )
    return repository.get_session(session_id)


def test_student_model_reads_prior_same_course_session_state_only(tmp_path):
    connection, repository, sessions = _env(tmp_path)
    _session(
        sessions,
        session_id="old-ma",
        course_id="course-ma",
        metadata={
            "adaptive_tutor_state": {
                "answer_status": "partial",
                "unresolved_doubt": "I still do not understand LU multipliers.",
                "last_misconception": "Confuses L with the eliminated matrix.",
                "last_math_verification": "repaired",
                "last_math_claims_checked": 1,
            }
        },
    )
    _session(
        sessions,
        session_id="old-ds",
        course_id="course-ds",
        metadata={
            "adaptive_tutor_state": {
                "answer_status": "incorrect",
                "unresolved_doubt": "I do not understand pandas merge.",
                "last_misconception": "Confuses rows and columns.",
            }
        },
    )
    current = _session(
        sessions,
        session_id="current-ma",
        course_id="course-ma",
        metadata={
            "adaptive_tutor_state": {
                "answer_status": "correct",
                "unresolved_doubt": "Current session must not count as history.",
            }
        },
        updated_at="2026-09-23T00:00:00Z",
    )

    model = build_persistent_student_model(repository, current)

    assert model.previous_sessions_considered == 1
    assert model.answer_status_counts == {"partial": 1}
    assert model.recurring_doubts == (
        "I still do not understand LU multipliers.",
    )
    assert model.recurring_misconceptions == (
        "Confuses L with the eliminated matrix.",
    )
    assert model.repaired_calculation_count == 1
    assert "pandas" not in student_model_prompt(model).casefold()
    assert "Current session must not count" not in student_model_prompt(model)
    connection.close()


def test_student_model_reads_existing_learning_memory_and_progress(tmp_path):
    connection, repository, sessions = _env(tmp_path)
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
    connection.execute(
        "INSERT INTO learning_memory_entries("
        "id,scope_type,scope_id,kind,topic_id,raw_topic,memory_text,"
        "source_entity_type,source_entity_id,created_at,updated_at,archived_at"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)",
        (
            "memory-1",
            "course",
            "course-ma",
            "weakness",
            "topic-lu",
            "LU Factorization",
            "Needs more practice connecting elimination multipliers to L.",
            "manual",
            "manual-1",
            "2026-09-20T00:00:00Z",
            "2026-09-22T00:00:00Z",
        ),
    )
    connection.execute(
        "INSERT INTO topic_progress_events("
        "id,topic_id,event_type,previous_status,new_status,confidence,"
        "evidence_type,evidence_id,occurred_at,note"
        ") VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            "event-1",
            "topic-lu",
            "study_update",
            "learning",
            "practicing",
            3,
            "manual",
            "manual-1",
            "2026-09-22T18:00:00Z",
            "Can perform basic 2x2 LU.",
        ),
    )

    current = repository.create_session(
        session_id="current-ma",
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

    model = build_persistent_student_model(repository, current)

    assert len(model.learning_memory) == 1
    assert "elimination multipliers" in model.learning_memory[0]
    assert len(model.recent_progress) == 1
    assert "LU Factorization" in model.recent_progress[0]
    assert "practicing" in model.recent_progress[0]
    connection.close()


def test_building_student_model_is_read_only(tmp_path):
    connection, repository, sessions = _env(tmp_path)
    _session(
        sessions,
        session_id="old-ma",
        course_id="course-ma",
        metadata={
            "adaptive_tutor_state": {
                "answer_status": "correct",
                "unresolved_doubt": "Historical doubt.",
            }
        },
    )
    current = _session(
        sessions,
        session_id="current-ma",
        course_id="course-ma",
        updated_at="2026-09-23T00:00:00Z",
    )

    before = connection.total_changes
    model = build_persistent_student_model(repository, current)
    after = connection.total_changes

    assert model.previous_sessions_considered == 1
    assert after == before
    connection.close()


def test_no_course_scope_returns_empty_model(tmp_path):
    connection, repository, _sessions = _env(tmp_path)
    session = repository.create_session(
        session_id="free-session",
        course_id=None,
        topic_id=None,
        assessment_id=None,
        resource_id=None,
        mode="free",
        source_policy="source_first",
        title="free",
        metadata_json="{}",
        created_at="2026-09-23T00:00:00Z",
    )

    model = build_persistent_student_model(repository, session)

    assert model.previous_sessions_considered == 0
    assert model.learning_memory == ()
    assert student_model_prompt(model) == "(none)"
    connection.close()


def test_mapping_and_prompt_accept_dataclass_or_mapping(tmp_path):
    connection, repository, sessions = _env(tmp_path)
    _session(
        sessions,
        session_id="old-ma",
        course_id="course-ma",
        metadata={
            "adaptive_tutor_state": {
                "answer_status": "incorrect",
                "last_misconception": "Adds elimination multipliers with wrong sign.",
            }
        },
    )
    current = _session(
        sessions,
        session_id="current-ma",
        course_id="course-ma",
        updated_at="2026-09-23T00:00:00Z",
    )

    model = build_persistent_student_model(repository, current)
    mapping = student_model_mapping(model)

    assert student_model_prompt(model) == student_model_prompt(mapping)
    assert mapping["previous_sessions_considered"] == 1
    assert mapping["answer_status_counts"] == {"incorrect": 1}
    connection.close()



class _EmptyRetrieval:
    def search(self, *args, **kwargs):
        return ()


def test_grounding_prompt_includes_persistent_model_but_current_question_has_priority(
    tmp_path,
):
    from personal_learning_assistant.tutor.grounding import TutorGroundingPlanner

    connection, repository, sessions = _env(tmp_path)
    _session(
        sessions,
        session_id="old-ma",
        course_id="course-ma",
        metadata={
            "adaptive_tutor_state": {
                "answer_status": "partial",
                "unresolved_doubt": "I still do not understand basis redundancy.",
                "last_misconception": "Thinks spanning guarantees uniqueness.",
            }
        },
    )
    current = _session(
        sessions,
        session_id="current-ma",
        course_id="course-ma",
        updated_at="2026-09-23T00:00:00Z",
    )

    planner = TutorGroundingPlanner(_EmptyRetrieval(), sessions)
    plan = planner.plan(
        current,
        "Now explain LU factorization and why it helps repeated solves.",
        transcript=(),
    )

    prompt = plan.messages[-1]["content"]
    system = plan.messages[0]["content"]

    assert "PERSISTENT STUDENT MODEL (historical/advisory only)" in prompt
    assert "previous_course_sessions=1" in prompt
    assert "previous_doubt=I still do not understand basis redundancy." in prompt
    assert "CURRENT QUESTION" in prompt
    assert "Now explain LU factorization" in prompt
    assert "CURRENT QUESTION always has priority" in system
    assert "not proof of current mastery" in system
    assert plan.persistent_student_model["previous_sessions_considered"] == 1
    connection.close()


def test_persistent_model_is_present_in_provider_request_metadata(tmp_path):
    from personal_learning_assistant.tutor.grounding import TutorGroundingPlanner

    connection, repository, sessions = _env(tmp_path)
    _session(
        sessions,
        session_id="old-ma",
        course_id="course-ma",
        metadata={
            "adaptive_tutor_state": {
                "answer_status": "correct",
            }
        },
    )
    current = _session(
        sessions,
        session_id="current-ma",
        course_id="course-ma",
        updated_at="2026-09-23T00:00:00Z",
    )

    planner = TutorGroundingPlanner(_EmptyRetrieval(), sessions)
    plan = planner.plan(current, "Explain LU factorization.", transcript=())
    request = planner.provider_request(current, plan, transcript=())

    model = request.metadata["persistent_student_model"]
    assert model["previous_sessions_considered"] == 1
    assert model["answer_status_counts"] == {"correct": 1}
    connection.close()


def test_tutor22_template_labels_history_as_advisory():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    template = (
        root
        / "personal_learning_assistant"
        / "ui"
        / "web"
        / "templates"
        / "agent_session.html"
    ).read_text(encoding="utf-8")

    assert "ANVAYA Tutor 2.2" in template
    assert "Across sessions" in template
    assert "Historical/advisory context only" in template
    assert "not a mastery score" in template
