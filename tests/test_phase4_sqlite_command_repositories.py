from __future__ import annotations

import ast
import hashlib
import inspect
import json
import sqlite3
from pathlib import Path

import pytest

from personal_learning_assistant.migration.authority_promotion import (
    AuthorityControlState,
    BACKEND_DUAL_READ,
    BACKEND_SQLITE,
    LegacyWriteBlockedError,
    write_authority_control_atomic,
)
from personal_learning_assistant.repositories.authority_guard import (
    AUTHORITY_CONTROL_FILENAME,
    infer_authority_control_path,
)
from personal_learning_assistant.repositories.json.assessment_repository import (
    LegacyJsonAssessmentRepository,
)
from personal_learning_assistant.repositories.json.course_repository import (
    LegacyJsonCourseRepository,
)
from personal_learning_assistant.repositories.json.grade_calendar_repository import (
    LegacyJsonGradeCalendarRepository,
)
from personal_learning_assistant.repositories.json.learning_progress_repository import (
    LegacyJsonLearningProgressRepository,
)
from personal_learning_assistant.repositories.json.question_repository import (
    LegacyJsonQuestionRepository,
)
from personal_learning_assistant.repositories.json.study_plan_repository import (
    LegacyJsonStudyPlanRepository,
)
from personal_learning_assistant.repositories.sqlite.command_repositories import (
    SQLiteAssessmentCommandRepository,
    SQLiteAuthorityCommandError,
    SQLiteAuthorityDataError,
    SQLiteAuthorityNotActiveError,
    SQLiteAuthoritySchemaError,
    SQLiteCourseCommandRepository,
    SQLiteGradeCalendarCommandRepository,
    SQLiteLearningProgressCommandRepository,
    SQLiteQuestionCommandRepository,
    SQLiteStudyPlanCommandRepository,
)
from personal_learning_assistant.repositories.sqlite.connection import connect_database
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations


STAMP = "2026-09-15T06:30:00Z"


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _database(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "authority.db"
    applied = apply_migrations(db)
    assert set((1, 2)).issubset(set(applied))
    return connect_database(db, synchronous="FULL")


def _control(tmp_path: Path, *, backend: str = BACKEND_SQLITE) -> Path:
    path = tmp_path / AUTHORITY_CONTROL_FILENAME
    if backend == BACKEND_SQLITE:
        state = AuthorityControlState(
            storage_backend=BACKEND_SQLITE,
            cutover_id="fixture-cutover",
            source_manifest_hash="a" * 64,
            sqlite_sha256="b" * 64,
            promoted_at=STAMP,
            legacy_writes_blocked=True,
        )
    else:
        state = AuthorityControlState(storage_backend=backend)
    write_authority_control_atomic(path, state)
    return path


def _seed_academic_structure(connection: sqlite3.Connection, control: Path):
    repo = SQLiteCourseCommandRepository(connection, authority_control_path=control)
    repo.upsert_semester(
        {
            "id": "sem-1",
            "name": "Semester 1",
            "academic_year": "2026-27",
            "status": "active",
            "created_at": STAMP,
            "updated_at": STAMP,
        }
    )
    repo.upsert_course(
        {
            "id": "course-1",
            "code": "MA103N",
            "name": "Linear Algebra",
            "status": "active",
            "created_at": STAMP,
            "updated_at": STAMP,
        }
    )
    repo.upsert_semester_course(
        {
            "semester_id": "sem-1",
            "course_id": "course-1",
            "credits_milli": 4000,
            "enrollment_status": "enrolled",
        }
    )
    repo.upsert_topic(
        {
            "id": "topic-1",
            "course_id": "course-1",
            "name": "LU Factorization",
            "position": 0,
            "status": "learning",
            "confidence": 2,
            "created_at": STAMP,
            "updated_at": STAMP,
        }
    )
    repo.set_active_course("course-1", updated_at=STAMP)
    return repo


def _seed_assessment(connection: sqlite3.Connection, control: Path):
    repo = SQLiteAssessmentCommandRepository(connection, authority_control_path=control)
    repo.upsert_assessment(
        {
            "id": "assessment-1",
            "course_id": "course-1",
            "assessment_type": "quiz",
            "title": "Synthetic Quiz",
            "due_on": "2026-09-20",
            "status": "pending",
            "weight_bps": 1000,
            "max_points_milli": 10000,
            "created_at": STAMP,
            "updated_at": STAMP,
        }
    )
    return repo


def test_explicit_connection_is_required(tmp_path):
    control = _control(tmp_path)
    with pytest.raises(TypeError):
        SQLiteCourseCommandRepository(None, authority_control_path=control)  # type: ignore[arg-type]


def test_incomplete_schema_is_rejected(tmp_path):
    control = _control(tmp_path)
    connection = sqlite3.connect(":memory:")
    try:
        with pytest.raises(SQLiteAuthoritySchemaError):
            SQLiteCourseCommandRepository(connection, authority_control_path=control)
    finally:
        connection.close()


def test_commands_are_disabled_in_legacy_state(tmp_path):
    connection = _database(tmp_path)
    control = tmp_path / AUTHORITY_CONTROL_FILENAME  # missing => legacy
    repo = SQLiteCourseCommandRepository(connection, authority_control_path=control)
    try:
        with pytest.raises(SQLiteAuthorityNotActiveError):
            repo.upsert_course(
                {
                    "id": "course-1",
                    "code": "MA103N",
                    "name": "Linear Algebra",
                    "created_at": STAMP,
                    "updated_at": STAMP,
                }
            )
        assert connection.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 0
    finally:
        connection.close()


def test_commands_are_disabled_in_dual_read_state(tmp_path):
    connection = _database(tmp_path)
    control = _control(tmp_path, backend=BACKEND_DUAL_READ)
    repo = SQLiteCourseCommandRepository(connection, authority_control_path=control)
    try:
        with pytest.raises(SQLiteAuthorityNotActiveError):
            repo.upsert_course(
                {
                    "id": "course-1",
                    "code": "MA103N",
                    "name": "Linear Algebra",
                    "created_at": STAMP,
                    "updated_at": STAMP,
                }
            )
    finally:
        connection.close()


def test_course_commands_write_after_atomic_sqlite_authority(tmp_path):
    connection = _database(tmp_path)
    control = _control(tmp_path)
    try:
        _seed_academic_structure(connection, control)
        course = connection.execute(
            "SELECT code, name, status FROM courses WHERE id='course-1'"
        ).fetchone()
        assert tuple(course) == ("MA103N", "Linear Algebra", "active")
        topic = connection.execute(
            "SELECT course_id, status, confidence FROM topics WHERE id='topic-1'"
        ).fetchone()
        assert tuple(topic) == ("course-1", "learning", 2)
        setting = connection.execute(
            "SELECT value_json FROM app_settings WHERE key='active_course_id'"
        ).fetchone()[0]
        assert json.loads(setting) == "course-1"
    finally:
        connection.close()


def test_course_soft_delete_is_explicit(tmp_path):
    connection = _database(tmp_path)
    control = _control(tmp_path)
    try:
        repo = _seed_academic_structure(connection, control)
        repo.soft_delete_topic("topic-1", deleted_at="2026-09-15T07:00:00Z")
        assert connection.execute(
            "SELECT deleted_at FROM topics WHERE id='topic-1'"
        ).fetchone()[0] == "2026-09-15T07:00:00Z"
    finally:
        connection.close()


def test_assessment_topics_replace_atomically(tmp_path):
    connection = _database(tmp_path)
    control = _control(tmp_path)
    try:
        _seed_academic_structure(connection, control)
        repo = _seed_assessment(connection, control)
        ids = repo.replace_topics(
            "assessment-1",
            [
                {
                    "id": "assessment-topic-1",
                    "topic_id": "topic-1",
                    "raw_label": "LU Factorization",
                    "source": "manual",
                    "created_at": STAMP,
                }
            ],
        )
        assert ids == ("assessment-topic-1",)
        assert connection.execute(
            "SELECT COUNT(*) FROM assessment_topics WHERE assessment_id='assessment-1'"
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_assessment_topic_replace_rolls_back_on_invalid_topic(tmp_path):
    connection = _database(tmp_path)
    control = _control(tmp_path)
    try:
        _seed_academic_structure(connection, control)
        repo = _seed_assessment(connection, control)
        repo.replace_topics(
            "assessment-1",
            [{"id": "at-1", "raw_label": "Unresolved", "created_at": STAMP}],
        )
        with pytest.raises(SQLiteAuthorityDataError):
            repo.replace_topics(
                "assessment-1",
                [
                    {
                        "id": "at-2",
                        "topic_id": "missing-topic",
                        "created_at": STAMP,
                    }
                ],
            )
        assert connection.execute(
            "SELECT id FROM assessment_topics WHERE assessment_id='assessment-1'"
        ).fetchall()[0][0] == "at-1"
    finally:
        connection.close()


def test_question_mapping_attempt_and_mistake_commands(tmp_path):
    connection = _database(tmp_path)
    control = _control(tmp_path)
    try:
        _seed_academic_structure(connection, control)
        _seed_assessment(connection, control)
        repo = SQLiteQuestionCommandRepository(connection, authority_control_path=control)
        repo.upsert_question(
            {
                "id": "question-1",
                "assessment_id": "assessment-1",
                "ordinal": 1,
                "question_text": "Factor the matrix.",
                "max_marks_milli": 5000,
                "status": "attempted",
                "created_at": STAMP,
                "updated_at": STAMP,
            }
        )
        repo.replace_sources(
            "question-1",
            [
                {
                    "id": "source-1",
                    "raw_source_label": "Synthetic Sheet p.1",
                    "page_number": 1,
                    "created_at": STAMP,
                }
            ],
        )
        repo.replace_topic_mappings(
            "question-1",
            [
                {
                    "id": "mapping-1",
                    "topic_id": "topic-1",
                    "score": 0.9,
                    "rank": 1,
                    "method": "manual",
                    "state": "accepted",
                    "created_at": STAMP,
                    "reviewed_at": STAMP,
                }
            ],
        )
        repo.upsert_attempt(
            {
                "id": "attempt-1",
                "question_id": "question-1",
                "attempt_number": 1,
                "outcome": "partially_correct",
                "earned_marks_milli": 3000,
                "max_marks_milli": 5000,
                "occurred_at": STAMP,
            }
        )
        repo.upsert_mistake(
            {
                "id": "mistake-1",
                "attempt_id": "attempt-1",
                "category": "algebra",
                "mistake_text": "Synthetic sign error",
                "created_at": STAMP,
            }
        )
        assert connection.execute("SELECT COUNT(*) FROM question_sources").fetchone()[0] == 1
        assert connection.execute("SELECT state FROM question_topic_mappings").fetchone()[0] == "accepted"
        assert connection.execute("SELECT outcome FROM question_attempts").fetchone()[0] == "partially_correct"
        assert connection.execute("SELECT category FROM mistake_events").fetchone()[0] == "algebra"
    finally:
        connection.close()


def test_learning_memory_progress_commands_are_relational(tmp_path):
    connection = _database(tmp_path)
    control = _control(tmp_path)
    try:
        _seed_academic_structure(connection, control)
        repo = SQLiteLearningProgressCommandRepository(
            connection, authority_control_path=control
        )
        repo.upsert_memory_entry(
            {
                "id": "memory-1",
                "scope_type": "course",
                "scope_id": "course-1",
                "kind": "note",
                "topic_id": "topic-1",
                "raw_topic": "LU Factorization",
                "memory_text": "Review elimination matrices.",
                "created_at": STAMP,
                "updated_at": STAMP,
            }
        )
        repo.upsert_topic_progress_event(
            {
                "id": "progress-event-1",
                "topic_id": "topic-1",
                "event_type": "status_change",
                "previous_status": "not_started",
                "new_status": "learning",
                "confidence": 2,
                "occurred_at": STAMP,
            }
        )
        repo.upsert_progress_snapshot(
            {
                "id": "snapshot-1",
                "course_id": "course-1",
                "snapshot_date": "2026-09-15",
                "counts": {"learning": 1},
                "score": {"progress_percent": 0},
                "engine_version": "fixture-v1",
                "created_at": STAMP,
            }
        )
        assert connection.execute("SELECT memory_text FROM learning_memory_entries").fetchone()[0].startswith("Review")
        assert json.loads(connection.execute("SELECT counts_json FROM progress_snapshots").fetchone()[0]) == {"learning": 1}
        with pytest.raises(SQLiteAuthorityDataError, match="mapping"):
            repo.upsert_progress_snapshot(
                {
                    "id": "snapshot-encoded",
                    "course_id": "course-1",
                    "snapshot_date": "2026-09-16",
                    "counts": '{"learning":1}',
                    "score": {"progress_percent": 0},
                    "engine_version": "fixture-v1",
                    "created_at": STAMP,
                }
            )
    finally:
        connection.close()


def test_study_plan_items_replace_atomically(tmp_path):
    connection = _database(tmp_path)
    control = _control(tmp_path)
    try:
        _seed_academic_structure(connection, control)
        _seed_assessment(connection, control)
        repo = SQLiteStudyPlanCommandRepository(connection, authority_control_path=control)
        repo.upsert_plan(
            {
                "id": "plan-1",
                "kind": "weekly",
                "horizon": "7_days",
                "starts_on": "2026-09-15",
                "ends_on": "2026-09-21",
                "requested_minutes": 120,
                "allocated_minutes": 120,
                "status": "proposed",
                "engine_name": "fixture",
                "engine_version": "1",
                "created_at": STAMP,
                "updated_at": STAMP,
            }
        )
        repo.replace_plan_items(
            "plan-1",
            [
                {
                    "id": "item-1",
                    "plan_date": "2026-09-15",
                    "ordinal": 1,
                    "course_id": "course-1",
                    "topic_id": "topic-1",
                    "minutes": 120,
                    "action": "Practice",
                    "status": "planned",
                }
            ],
        )
        assert connection.execute("SELECT minutes FROM study_plan_items").fetchone()[0] == 120
    finally:
        connection.close()


def test_grade_calendar_commands_cover_credits_scale_result_and_event(tmp_path):
    connection = _database(tmp_path)
    control = _control(tmp_path)
    try:
        _seed_academic_structure(connection, control)
        repo = SQLiteGradeCalendarCommandRepository(connection, authority_control_path=control)
        repo.upsert_grade_scale(
            {
                "id": "scale-1",
                "name": "Planning Scale",
                "source": "user",
                "verified": False,
                "created_at": STAMP,
                "updated_at": STAMP,
            }
        )
        repo.replace_grade_bands(
            "scale-1",
            [
                {"id": "band-a", "minimum_bps": 8000, "letter_grade": "A", "grade_point_milli": 9000},
                {"id": "band-f", "minimum_bps": 0, "letter_grade": "F", "grade_point_milli": 0},
            ],
        )
        repo.set_semester_course_credits("sem-1", "course-1", 5000)
        repo.upsert_semester_grade_settings(
            {
                "semester_id": "sem-1",
                "scale_id": "scale-1",
                "target_sgpa_milli": 8500,
                "updated_at": STAMP,
            }
        )
        repo.upsert_manual_grade_entry(
            {
                "id": "grade-1",
                "semester_id": "sem-1",
                "course_id": "course-1",
                "score_bps": 8200,
                "entry_kind": "current_estimate",
                "recorded_at": STAMP,
            }
        )
        repo.upsert_semester_result(
            {
                "id": "result-1",
                "semester_id": "sem-1",
                "earned_credits_milli": 5000,
                "earned_grade_points_milli": 45000,
                "sgpa_milli": 9000,
                "verified": False,
                "source": "fixture",
                "recorded_at": STAMP,
            }
        )
        repo.upsert_academic_event(
            {
                "id": "event-1",
                "semester_id": "sem-1",
                "course_id": "course-1",
                "event_kind": "assessment_deadline",
                "title": "Synthetic deadline",
                "starts_at": "2026-09-20",
                "all_day": True,
                "created_at": STAMP,
                "updated_at": STAMP,
            }
        )
        assert connection.execute(
            "SELECT credits_milli FROM semester_courses WHERE semester_id='sem-1' AND course_id='course-1'"
        ).fetchone()[0] == 5000
        assert connection.execute("SELECT COUNT(*) FROM grade_bands").fetchone()[0] == 2
        assert connection.execute("SELECT event_kind FROM academic_events").fetchone()[0] == "assessment_deadline"
    finally:
        connection.close()


def test_command_repository_refuses_nested_transaction(tmp_path):
    connection = _database(tmp_path)
    control = _control(tmp_path)
    repo = SQLiteCourseCommandRepository(connection, authority_control_path=control)
    try:
        connection.execute("BEGIN")
        with pytest.raises(SQLiteAuthorityCommandError, match="nested"):
            repo.upsert_course(
                {
                    "id": "course-1",
                    "code": "MA103N",
                    "name": "Linear Algebra",
                    "created_at": STAMP,
                    "updated_at": STAMP,
                }
            )
        connection.rollback()
    finally:
        connection.close()


def test_authority_control_is_inferred_outside_data_directory(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    path = infer_authority_control_path(data / "courses.json")
    assert path == tmp_path / AUTHORITY_CONTROL_FILENAME
    assert data not in path.parents


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_legacy_course_repository_is_blocked_after_sqlite_promotion(tmp_path):
    data = tmp_path / "data"
    course_path = data / "courses.json"
    _write_json(course_path, {"version": 1, "active_course_id": None, "courses": [], "document_links": {}})
    before = course_path.read_bytes()
    _control(tmp_path)
    repo = LegacyJsonCourseRepository(path=course_path)
    with pytest.raises(LegacyWriteBlockedError):
        repo.save_state(repo.load_state())
    assert course_path.read_bytes() == before


def test_legacy_assessment_and_question_repositories_are_blocked(tmp_path):
    data = tmp_path / "data"
    assessments = data / "assessments.json"
    workspace = data / "assessment_workspace.json"
    _write_json(assessments, {"version": 2, "assessments": []})
    _write_json(workspace, {"version": 1, "workspaces": {}})
    before_a = _hash(assessments)
    before_q = _hash(workspace)
    _control(tmp_path)
    with pytest.raises(LegacyWriteBlockedError):
        LegacyJsonAssessmentRepository(path=assessments).save_state({"version": 2, "assessments": []})
    with pytest.raises(LegacyWriteBlockedError):
        LegacyJsonQuestionRepository(path=workspace).save_state({"version": 1, "workspaces": {}})
    assert _hash(assessments) == before_a
    assert _hash(workspace) == before_q


def test_legacy_learning_progress_writers_are_blocked(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    memory = data / "learning_memory.json"
    history = data / "course_progress_history.json"
    courses = data / "courses.json"
    _write_json(memory, {"version": 2, "weak_topics": [], "mastered_topics": [], "recent_activity": [], "notes": [], "course_memory": {}})
    _write_json(history, {"version": 1, "courses": {}})
    _write_json(courses, {"version": 1, "courses": []})
    before = (memory.read_bytes(), history.read_bytes())
    _control(tmp_path)
    repo = LegacyJsonLearningProgressRepository(memory, history, courses)
    with pytest.raises(LegacyWriteBlockedError):
        repo.save_memory(repo.load_memory())
    with pytest.raises(LegacyWriteBlockedError):
        repo.save_progress_history(repo.load_progress_history())
    assert (memory.read_bytes(), history.read_bytes()) == before


def test_legacy_study_plan_and_grade_writers_are_blocked(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    weekly = data / "weekly_study_plans.json"
    multi = data / "multi_course_weekly_plans.json"
    intelligent = data / "intelligent_study_plans.json"
    grades = data / "semester_grade_config.json"
    assessments = data / "assessments.json"
    for path in (weekly, multi, intelligent):
        _write_json(path, {"version": 1, "plans": []})
    _write_json(grades, {"version": 1, "courses": [], "grade_scale": []})
    _write_json(assessments, {"version": 2, "assessments": []})
    before = {path: path.read_bytes() for path in (weekly, multi, intelligent, grades)}
    _control(tmp_path)
    plans = LegacyJsonStudyPlanRepository(
        weekly_path=weekly,
        multi_course_path=multi,
        intelligent_path=intelligent,
    )
    with pytest.raises(LegacyWriteBlockedError):
        plans.save_weekly_store({"version": 1, "plans": []})
    with pytest.raises(LegacyWriteBlockedError):
        plans.save_multi_course_store({"version": 1, "plans": []})
    with pytest.raises(LegacyWriteBlockedError):
        plans.save_intelligent_store({"version": 1, "plans": []})
    grade_repo = LegacyJsonGradeCalendarRepository(
        grade_config_path=grades,
        assessments_path=assessments,
    )
    with pytest.raises(LegacyWriteBlockedError):
        grade_repo.save_grade_config(grade_repo.load_grade_config())
    assert {path: path.read_bytes() for path in before} == before


def test_missing_control_preserves_legacy_write_behavior(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    weekly = data / "weekly_study_plans.json"
    multi = data / "multi_course_weekly_plans.json"
    intelligent = data / "intelligent_study_plans.json"
    repo = LegacyJsonStudyPlanRepository(
        weekly_path=weekly,
        multi_course_path=multi,
        intelligent_path=intelligent,
    )
    repo.save_weekly_store({"version": 1, "plans": [{"id": "legacy-ok"}]})
    assert json.loads(weekly.read_text(encoding="utf-8"))["plans"][0]["id"] == "legacy-ok"
    assert not (tmp_path / AUTHORITY_CONTROL_FILENAME).exists()


def test_dual_read_control_preserves_legacy_write_behavior(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    weekly = data / "weekly_study_plans.json"
    multi = data / "multi_course_weekly_plans.json"
    intelligent = data / "intelligent_study_plans.json"
    _control(tmp_path, backend=BACKEND_DUAL_READ)
    repo = LegacyJsonStudyPlanRepository(
        weekly_path=weekly,
        multi_course_path=multi,
        intelligent_path=intelligent,
    )
    repo.save_weekly_store({"version": 1, "plans": [{"id": "dual-ok"}]})
    assert json.loads(weekly.read_text(encoding="utf-8"))["plans"][0]["id"] == "dual-ok"


def test_sqlite_command_path_does_not_change_legacy_source_bytes(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    legacy = data / "courses.json"
    legacy.write_bytes(b'{"version":1,"courses":[]}\n')
    before = legacy.read_bytes()
    connection = _database(tmp_path)
    control = _control(tmp_path)
    try:
        repo = SQLiteCourseCommandRepository(connection, authority_control_path=control)
        repo.upsert_course(
            {
                "id": "course-1",
                "code": "MA103N",
                "name": "Linear Algebra",
                "created_at": STAMP,
                "updated_at": STAMP,
            }
        )
        assert legacy.read_bytes() == before
    finally:
        connection.close()


def test_no_command_repository_contains_implicit_production_database_path():
    import personal_learning_assistant.repositories.sqlite.command_repositories as module

    source = inspect.getsource(module)
    assert "learning_assistant.db" not in source
    assert "DATABASE_PATH" not in source
    assert "connect_database(" not in source


def test_procedural_legacy_writers_are_blocked_after_sqlite_promotion(
    tmp_path,
    monkeypatch,
):
    """Direct compatibility writers cannot bypass the repository-level guard."""
    import academic_progress
    import assessment_question_workspace
    import assignment_exam_assistant
    import course_manager
    import intelligent_study_planner
    import learning_memory
    import multi_course_planner
    import semester_grade_intelligence
    import weekly_planner

    data = tmp_path / "data"
    data.mkdir()
    cases = (
        (
            course_manager,
            "COURSES_FILE",
            "courses.json",
            course_manager.save_course_data,
            {"version": 1, "active_course_id": None, "courses": [], "document_links": {}},
        ),
        (
            assignment_exam_assistant,
            "ASSESSMENTS_FILE",
            "assessments.json",
            assignment_exam_assistant.save_store,
            {"version": 2, "assessments": []},
        ),
        (
            assessment_question_workspace,
            "WORKSPACE_FILE",
            "assessment_workspace.json",
            assessment_question_workspace.save_store,
            {"version": 1, "workspaces": {}},
        ),
        (
            learning_memory,
            "MEMORY_FILE",
            "learning_memory.json",
            learning_memory.save_memory,
            learning_memory.default_memory(),
        ),
        (
            academic_progress,
            "HISTORY_FILE",
            "course_progress_history.json",
            academic_progress.save_history,
            academic_progress.default_history(),
        ),
        (
            weekly_planner,
            "PLANS_FILE",
            "weekly_study_plans.json",
            weekly_planner.save_store,
            {"version": 1, "plans": []},
        ),
        (
            multi_course_planner,
            "MULTI_PLANS_FILE",
            "multi_course_weekly_plans.json",
            multi_course_planner.save_store,
            {"version": 1, "plans": []},
        ),
        (
            intelligent_study_planner,
            "STUDY_PLANS_FILE",
            "intelligent_study_plans.json",
            intelligent_study_planner.save_store,
            {"version": 1, "plans": []},
        ),
        (
            semester_grade_intelligence,
            "GRADE_CONFIG_FILE",
            "semester_grade_config.json",
            semester_grade_intelligence.save_config,
            semester_grade_intelligence.default_config(),
        ),
    )

    originals = {}
    for module, file_attr, filename, _writer, payload in cases:
        path = data / filename
        _write_json(path, payload)
        originals[path] = path.read_bytes()
        monkeypatch.setattr(module, file_attr, str(path))
        if hasattr(module, "DATA_DIR"):
            monkeypatch.setattr(module, "DATA_DIR", str(data))

    _control(tmp_path)
    for _module, _file_attr, filename, writer, payload in cases:
        with pytest.raises(LegacyWriteBlockedError):
            writer(payload)
        path = data / filename
        assert path.read_bytes() == originals[path]


def test_procedural_guard_blocks_before_creating_legacy_data_directory(
    tmp_path,
    monkeypatch,
):
    import weekly_planner

    data = tmp_path / "data"
    plan_path = data / "weekly_study_plans.json"
    _control(tmp_path)
    monkeypatch.setattr(weekly_planner, "DATA_DIR", str(data))
    monkeypatch.setattr(weekly_planner, "PLANS_FILE", str(plan_path))

    assert not data.exists()
    with pytest.raises(LegacyWriteBlockedError):
        weekly_planner.save_store({"version": 1, "plans": []})
    assert not data.exists()
    assert not plan_path.exists()


def test_procedural_writer_still_works_when_control_is_missing(
    tmp_path,
    monkeypatch,
):
    import weekly_planner

    data = tmp_path / "data"
    plan_path = data / "weekly_study_plans.json"
    monkeypatch.setattr(weekly_planner, "DATA_DIR", str(data))
    monkeypatch.setattr(weekly_planner, "PLANS_FILE", str(plan_path))

    weekly_planner.save_store({"version": 1, "plans": [{"id": "legacy-direct"}]})
    assert json.loads(plan_path.read_text(encoding="utf-8"))["plans"][0]["id"] == "legacy-direct"
    assert not (tmp_path / AUTHORITY_CONTROL_FILENAME).exists()


def test_procedural_writer_still_works_in_dual_read_state(
    tmp_path,
    monkeypatch,
):
    import weekly_planner

    data = tmp_path / "data"
    plan_path = data / "weekly_study_plans.json"
    _control(tmp_path, backend=BACKEND_DUAL_READ)
    monkeypatch.setattr(weekly_planner, "DATA_DIR", str(data))
    monkeypatch.setattr(weekly_planner, "PLANS_FILE", str(plan_path))

    weekly_planner.save_store({"version": 1, "plans": [{"id": "dual-direct"}]})
    assert json.loads(plan_path.read_text(encoding="utf-8"))["plans"][0]["id"] == "dual-direct"


def test_phase410_course_repository_keeps_phase2_dependency_direction():
    """Guard wiring must not reintroduce the legacy course_manager dependency."""
    import personal_learning_assistant.repositories.json.course_repository as module

    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert "course_manager" not in imported
    assert all(not name.startswith("course_manager.") for name in imported)
    assert "personal_learning_assistant.domain.course_normalization" in imported
