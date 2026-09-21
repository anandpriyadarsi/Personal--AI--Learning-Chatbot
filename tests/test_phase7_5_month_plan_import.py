from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/phase7_5/month_plan_minimal.yaml"


def _db(tmp_path):
    path = tmp_path / "planner.db"
    assert apply_migrations(path) == (1, 2, 3, 4, 5, 6)
    c = sqlite3.connect(path)
    c.execute(
        "INSERT INTO courses "
        "(id,code,name,status,description,created_at,updated_at,deleted_at) "
        "VALUES ('c-ma','MA103N','Linear Algebra','active','','2026-09-20T00:00:00Z','2026-09-20T00:00:00Z',NULL)"
    )
    c.commit()
    c.close()
    return path


def test_0006_schema_and_fresh_integrity(tmp_path):
    path = _db(tmp_path)
    c = sqlite3.connect(path)
    versions = tuple(row[0] for row in c.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ))
    assert versions == (1, 2, 3, 4, 5, 6)
    tables = {row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "month_plan_imports", "month_plan_import_items", "planner_tasks",
        "routine_templates", "daily_agendas", "daily_agenda_items",
        "task_rollover_events", "daily_reviews", "weekly_reviews",
    } <= tables
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert c.execute("PRAGMA foreign_key_check").fetchall() == []
    with pytest.raises(sqlite3.IntegrityError):
        c.execute(
            "INSERT INTO planner_tasks "
            "(id,title,priority,status,manual_revision,created_at,updated_at) "
            "VALUES ('bad','Bad','P3','backlog',0,'x','x')"
        )
    c.close()


def test_preview_is_write_free_and_preserves_unknown_midsem_slots(tmp_path):
    from personal_learning_assistant.services.month_plan_import_service import (
        build_month_plan_import_service,
    )

    path = _db(tmp_path)
    service = build_month_plan_import_service(path)
    payload = FIXTURE.read_bytes()

    before = sqlite3.connect(path).execute(
        "SELECT COUNT(*) FROM month_plan_imports"
    ).fetchone()[0]
    preview = service.preview(FIXTURE.name, payload)
    after = sqlite3.connect(path).execute(
        "SELECT COUNT(*) FROM month_plan_imports"
    ).fetchone()[0]

    assert before == after == 0
    assert preview["valid"] is True
    assert preview["waiting_exam_slots"] == ("ASM-MIDSEM-MA103N",)
    assessment = preview["plan"]["assessments"][0]
    assert assessment["due_on"] is None
    assert assessment["due_time"] is None


def test_preview_rejects_subject_exam_slot_before_official_datesheet(tmp_path):
    from personal_learning_assistant.services.month_plan_import_service import (
        build_month_plan_import_service,
    )

    path = _db(tmp_path)
    text = FIXTURE.read_text(encoding="utf-8").replace(
        "    due_on:\n", "    due_on: 2026-10-08\n", 1
    )
    preview = build_month_plan_import_service(path).preview("bad.yaml", text.encode())
    assert preview["valid"] is False
    assert any("before the official datesheet" in item for item in preview["errors"])


def test_approval_is_atomic_provenanced_and_idempotent(tmp_path):
    from personal_learning_assistant.services.month_plan_import_service import (
        build_month_plan_import_service,
    )

    path = _db(tmp_path)
    service = build_month_plan_import_service(path)
    payload = FIXTURE.read_bytes()
    preview = service.preview(FIXTURE.name, payload)
    result = service.approve(FIXTURE.name, payload, preview["source_sha256"])
    assert result["created"] is True

    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    assert c.execute("SELECT COUNT(*) FROM month_plan_imports WHERE status='active'").fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM planner_tasks").fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM routine_templates").fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM academic_events").fetchone()[0] == 2
    assessment = c.execute(
        "SELECT due_on,due_time FROM assessments WHERE title='MA103N Mid-Semester'"
    ).fetchone()
    assert assessment["due_on"] is None
    assert assessment["due_time"] is None
    assert c.execute("SELECT COUNT(*) FROM month_plan_import_items").fetchone()[0] >= 5
    c.close()

    second = service.approve(FIXTURE.name, payload, preview["source_sha256"])
    assert second["created"] is False
    assert second["idempotent"] is True


def test_changed_import_refuses_to_overwrite_manually_revised_task(tmp_path):
    from personal_learning_assistant.services.month_plan_import_service import (
        MonthPlanImportConflictError,
        build_month_plan_import_service,
    )

    path = _db(tmp_path)
    service = build_month_plan_import_service(path)
    payload = FIXTURE.read_bytes()
    preview = service.preview(FIXTURE.name, payload)
    service.approve(FIXTURE.name, payload, preview["source_sha256"])

    c = sqlite3.connect(path)
    c.execute("UPDATE planner_tasks SET manual_revision=1")
    c.commit()
    c.close()

    changed = payload.replace(b"Solve and explain one LU set.", b"Solve two LU sets independently.")
    changed_preview = service.preview("changed.yaml", changed)
    assert changed_preview["valid"] is True
    with pytest.raises(MonthPlanImportConflictError):
        service.approve("changed.yaml", changed, changed_preview["source_sha256"])


def test_unsafe_yaml_python_tag_is_rejected(tmp_path):
    from personal_learning_assistant.services.month_plan_import_service import (
        MonthPlanImportValidationError,
        build_month_plan_import_service,
    )

    path = _db(tmp_path)
    payload = b"!!python/object/apply:os.system ['echo unsafe']"
    with pytest.raises(MonthPlanImportValidationError):
        build_month_plan_import_service(path).preview("unsafe.yaml", payload)
