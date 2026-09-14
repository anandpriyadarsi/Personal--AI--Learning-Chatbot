from __future__ import annotations

import sqlite3

import pytest


REQUIRED_TABLES = {
    # Foundation
    "schema_migrations",
    "app_settings",
    "migration_imports",
    "operation_journal",
    "outbox_events",
    # Academic structure
    "semesters",
    "courses",
    "semester_courses",
    "course_aliases",
    "course_relations",
    "topics",
    "topic_aliases",
    # Notes / vaults
    "vaults",
    "note_metadata",
    "tags",
    "note_tags",
    "note_courses",
    "note_topics",
    "note_links",
    "note_assessments",
    # Resources / documents
    "resources",
    "resource_courses",
    "resource_topics",
    "resource_notes",
    "resource_assessments",
    "resource_progress_events",
    "knowledge_documents",
    "resource_documents",
    "knowledge_chunks",
    "index_jobs",
    # Assessments / performance
    "assessments",
    "assessment_topics",
    "questions",
    "question_topic_mappings",
    "question_sources",
    "question_attempts",
    "mistake_events",
    # Progress / planning
    "topic_progress_events",
    "progress_snapshots",
    "learning_memory_entries",
    "study_plans",
    "study_plan_items",
    "study_sessions",
    # Grades / calendar
    "grade_scales",
    "grade_bands",
    "semester_grade_settings",
    "manual_grade_entries",
    "semester_results",
    "academic_events",
}

REQUIRED_VIEWS = {
    "active_courses_with_semester",
    "open_assessments",
    "resource_latest_progress",
    "note_active_view",
    "question_latest_attempt",
    "course_assessment_weight_summary",
}

NOW = "2026-09-14T02:00:00Z"


def _migrate(tmp_path):
    from personal_learning_assistant.repositories.sqlite.migration_runner import (
        apply_migrations,
    )

    database_path = tmp_path / "learning_assistant.db"
    applied = apply_migrations(database_path)
    return database_path, applied


def _open(database_path):
    from personal_learning_assistant.repositories.sqlite.connection import (
        connect_database,
    )

    return connect_database(database_path)


def _seed_course(connection):
    connection.execute(
        "INSERT INTO semesters "
        "(id, name, academic_year, starts_on, ends_on, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "semester-1",
            "Semester 1",
            "2026-27",
            "2026-08-01",
            "2026-12-31",
            "active",
            NOW,
            NOW,
        ),
    )
    connection.execute(
        "INSERT INTO courses "
        "(id, code, name, status, description, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "course-ma103n",
            "MA103N",
            "Linear Algebra",
            "active",
            "",
            NOW,
            NOW,
        ),
    )
    connection.execute(
        "INSERT INTO semester_courses "
        "(semester_id, course_id, credits_milli, instructor, enrollment_status) "
        "VALUES (?, ?, ?, ?, ?)",
        ("semester-1", "course-ma103n", 4000, "", "enrolled"),
    )
    connection.execute(
        "INSERT INTO topics "
        "(id, course_id, name, normalized_name, position, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "topic-lu",
            "course-ma103n",
            "LU Factorization",
            "lu factorization",
            1,
            "not_started",
            NOW,
            NOW,
        ),
    )


def _seed_assessment(connection):
    connection.execute(
        "INSERT INTO assessments "
        "(id, course_id, assessment_type, title, due_on, status, weight_bps, "
        "max_points_milli, description, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "assessment-1",
            "course-ma103n",
            "quiz",
            "Quiz 1",
            "2026-09-24",
            "pending",
            2500,
            100000,
            "",
            NOW,
            NOW,
        ),
    )
    connection.execute(
        "INSERT INTO questions "
        "(id, assessment_id, ordinal, question_text, max_marks_milli, status, "
        "user_notes, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "question-1",
            "assessment-1",
            1,
            "Solve using LU factorization.",
            10000,
            "not_started",
            "",
            NOW,
            NOW,
        ),
    )


def test_academic_schema_migration_is_complete_idempotent_and_clean(tmp_path):
    database_path, applied = _migrate(tmp_path)

    assert applied == (1, 2)

    from personal_learning_assistant.repositories.sqlite.migration_runner import (
        apply_migrations,
    )

    assert apply_migrations(database_path) == ()

    connection = sqlite3.connect(database_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        views = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'view'"
            ).fetchall()
        }

        assert REQUIRED_TABLES.issubset(tables)
        assert REQUIRED_VIEWS.issubset(views)

        migrations = connection.execute(
            "SELECT version, name, length(checksum) "
            "FROM schema_migrations ORDER BY version"
        ).fetchall()
        assert migrations == [
            (1, "foundation", 64),
            (2, "academic_schema", 64),
        ]

        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_note_metadata_keeps_markdown_body_outside_sqlite(tmp_path):
    database_path, _ = _migrate(tmp_path)

    connection = sqlite3.connect(database_path)
    try:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(note_metadata)"
            ).fetchall()
        }
        assert "body" not in columns
        assert {
            "relative_path",
            "path_key",
            "source_hash",
            "file_mtime_ns",
            "frontmatter_extra_json",
        }.issubset(columns)
    finally:
        connection.close()


def test_assessment_with_questions_cannot_be_hard_deleted(tmp_path):
    database_path, _ = _migrate(tmp_path)
    connection = _open(database_path)

    try:
        _seed_course(connection)
        _seed_assessment(connection)

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "DELETE FROM assessments WHERE id = ?",
                ("assessment-1",),
            )

        connection.execute(
            "UPDATE assessments SET deleted_at = ? WHERE id = ?",
            (NOW, "assessment-1"),
        )
        assert connection.execute(
            "SELECT deleted_at FROM assessments WHERE id = ?",
            ("assessment-1",),
        ).fetchone()[0] == NOW
    finally:
        connection.close()


def test_basis_point_and_milli_unit_constraints_are_enforced(tmp_path):
    database_path, _ = _migrate(tmp_path)
    connection = _open(database_path)

    try:
        _seed_course(connection)

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE semester_courses SET credits_milli = -1 "
                "WHERE semester_id = ? AND course_id = ?",
                ("semester-1", "course-ma103n"),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO assessments "
                "(id, course_id, assessment_type, title, status, weight_bps, "
                "description, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "bad-weight",
                    "course-ma103n",
                    "quiz",
                    "Invalid Quiz",
                    "pending",
                    10001,
                    "",
                    NOW,
                    NOW,
                ),
            )

        connection.execute(
            "INSERT INTO grade_scales "
            "(id, name, source, verified, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("scale-1", "Test Scale", "test", 0, NOW, NOW),
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO grade_bands "
                "(id, scale_id, minimum_bps, letter_grade, grade_point_milli) "
                "VALUES (?, ?, ?, ?, ?)",
                ("band-x", "scale-1", 10001, "X", 10000),
            )
    finally:
        connection.close()


def test_join_rows_cascade_but_core_records_use_restrict(tmp_path):
    database_path, _ = _migrate(tmp_path)
    connection = _open(database_path)

    try:
        connection.execute(
            "INSERT INTO vaults "
            "(id, name, root_path, path_key, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("vault-1", "Academic", "C:/vault", "c:/vault", NOW, NOW),
        )
        connection.execute(
            "INSERT INTO note_metadata "
            "(id, vault_id, relative_path, path_key, title, source_hash, "
            "file_mtime_ns, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "note-1",
                "vault-1",
                "MA103N/LU.md",
                "ma103n/lu.md",
                "LU Factorization",
                "a" * 64,
                1,
                NOW,
                NOW,
            ),
        )
        connection.execute(
            "INSERT INTO tags (id, name, normalized_name, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("tag-1", "Linear Algebra", "linear algebra", NOW),
        )
        connection.execute(
            "INSERT INTO note_tags (note_id, tag_id) VALUES (?, ?)",
            ("note-1", "tag-1"),
        )

        connection.execute("DELETE FROM tags WHERE id = ?", ("tag-1",))
        assert connection.execute(
            "SELECT COUNT(*) FROM note_tags"
        ).fetchone()[0] == 0

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM vaults WHERE id = ?", ("vault-1",))
    finally:
        connection.close()


def test_stable_views_return_expected_latest_and_summary_rows(tmp_path):
    database_path, _ = _migrate(tmp_path)
    connection = _open(database_path)

    try:
        _seed_course(connection)
        _seed_assessment(connection)

        connection.execute(
            "INSERT INTO question_attempts "
            "(id, question_id, attempt_number, outcome, earned_marks_milli, "
            "max_marks_milli, occurred_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "attempt-1",
                "question-1",
                1,
                "incorrect",
                2000,
                10000,
                "2026-09-14T01:00:00Z",
            ),
        )
        connection.execute(
            "INSERT INTO question_attempts "
            "(id, question_id, attempt_number, outcome, earned_marks_milli, "
            "max_marks_milli, occurred_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "attempt-2",
                "question-1",
                2,
                "correct",
                10000,
                10000,
                "2026-09-14T02:00:00Z",
            ),
        )

        connection.execute(
            "INSERT INTO resources "
            "(id, resource_type, title, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("resource-1", "video", "LU Lecture", "in_progress", NOW, NOW),
        )
        connection.execute(
            "INSERT INTO resource_progress_events "
            "(id, resource_id, occurred_at, status, value, max_value, unit) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "progress-1",
                "resource-1",
                "2026-09-14T01:00:00Z",
                "in_progress",
                10,
                60,
                "minutes",
            ),
        )
        connection.execute(
            "INSERT INTO resource_progress_events "
            "(id, resource_id, occurred_at, status, value, max_value, unit) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "progress-2",
                "resource-1",
                "2026-09-14T02:00:00Z",
                "in_progress",
                25,
                60,
                "minutes",
            ),
        )

        latest_attempt = connection.execute(
            "SELECT attempt_number, outcome FROM question_latest_attempt "
            "WHERE question_id = ?",
            ("question-1",),
        ).fetchone()
        assert tuple(latest_attempt) == (2, "correct")

        latest_progress = connection.execute(
            "SELECT progress_event_id, value FROM resource_latest_progress "
            "WHERE resource_id = ?",
            ("resource-1",),
        ).fetchone()
        assert tuple(latest_progress) == ("progress-2", 25.0)

        weight_summary = connection.execute(
            "SELECT assessment_count, total_weight_bps "
            "FROM course_assessment_weight_summary WHERE course_id = ?",
            ("course-ma103n",),
        ).fetchone()
        assert tuple(weight_summary) == (1, 2500)

        assert connection.execute(
            "SELECT COUNT(*) FROM open_assessments WHERE id = ?",
            ("assessment-1",),
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_no_fts_or_vector_storage_is_required_by_core_schema(tmp_path):
    database_path, _ = _migrate(tmp_path)

    connection = sqlite3.connect(database_path)
    try:
        virtual_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND sql LIKE 'CREATE VIRTUAL TABLE%'"
            ).fetchall()
        }
        assert "note_fts" not in virtual_tables
        assert "knowledge_fts" not in virtual_tables

        chunk_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(knowledge_chunks)"
            ).fetchall()
        }
        assert "embedding" not in chunk_columns
        assert "vector" not in chunk_columns
    finally:
        connection.close()
