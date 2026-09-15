from __future__ import annotations

import ast
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from personal_learning_assistant.migration.authority_promotion import (
    AuthorityControlState,
    LegacyWriteBlockedError,
    write_authority_control_atomic,
)
from personal_learning_assistant.migration.compatibility_projection_seed import (
    SEED_MANIFEST_SETTING,
    seed_phase4_compatibility_projections,
)
from personal_learning_assistant.repositories.sqlite.compatibility_repository import (
    PROJECTION_PREFIX,
    SQLiteCompatibilityProjectionMissingError,
    SQLiteCompatibilityProjectionRepository,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
from personal_learning_assistant.repositories.structured_authority_router import (
    DeferredStructuredDomainWriteError,
    StructuredDatabaseUnavailableError,
    database_path_for_store,
    maybe_load_sqlite_structured_store,
    maybe_save_sqlite_structured_store,
)


ROOT = Path(__file__).resolve().parents[1]
BASELINE = "0a92938ba468bd78d8188e45a661a080c85f1f8e"


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _control_path(root: Path) -> Path:
    return root / ".phase4_authority.json"


def _sqlite_state() -> AuthorityControlState:
    return AuthorityControlState(
        storage_backend="sqlite",
        cutover_id="phase4-11-test",
        source_manifest_hash="a" * 64,
        sqlite_sha256="b" * 64,
        promoted_at="2099-01-01T00:00:00Z",
        legacy_writes_blocked=True,
    )


def _source_payloads():
    return {
        "courses.json": {
            "version": 1,
            "active_course_id": "c1",
            "courses": [
                {
                    "id": "c1",
                    "code": "C1",
                    "name": "Synthetic Course",
                    "semester": "1",
                    "status": "active",
                    "topics": [
                        {"name": "Topic A", "status": "learning", "confidence": 2}
                    ],
                    "created_at": "2099-01-01T00:00:00",
                    "updated_at": "2099-01-01T00:00:00",
                }
            ],
            "document_links": {
                "legacy:doc": {
                    "course_id": "c1",
                    "topic": "Topic A",
                    "source_type": "document",
                    "display_path": "legacy.md",
                    "linked_at": "2099-01-01T00:00:00",
                }
            },
        },
        "assessments.json": {
            "version": 2,
            "assessments": [
                {
                    "id": "a1",
                    "course_id": "c1",
                    "type": "quiz",
                    "title": "Synthetic Quiz",
                    "due_date": "2099-01-10",
                    "weightage_percent": 10,
                    "total_marks": 20,
                    "obtained_marks": 15,
                    "topics": ["Topic A"],
                    "status": "pending",
                    "created_at": "2099-01-02T00:00:00",
                    "updated_at": "2099-01-02T00:00:00",
                }
            ],
        },
        "assessment_workspace.json": {
            "version": 1,
            "workspaces": {
                "a1": {
                    "assessment_id": "a1",
                    "questions": [
                        {
                            "id": "q1",
                            "text": "Synthetic question?",
                            "topic": "Topic A",
                            "marks": 2,
                            "status": "attempted",
                            "notes": "",
                            "attempts": [],
                            "created_at": "2099-01-03T00:00:00",
                            "updated_at": "2099-01-03T00:00:00",
                        }
                    ],
                }
            },
        },
        "learning_memory.json": {
            "version": 2,
            "weak_topics": [],
            "mastered_topics": [],
            "recent_activity": [],
            "notes": [],
            "course_memory": {
                "c1": {
                    "weak_topics": ["Topic A"],
                    "mastered_topics": [],
                    "recent_activity": [],
                    "notes": [{"text": "Synthetic memory", "created_at": "2099-01-04"}],
                }
            },
        },
        "course_progress_history.json": {
            "version": 1,
            "courses": {
                "c1": [
                    {
                        "captured_at": "2099-01-05T10:00:00",
                        "date": "2099-01-05",
                        "course_id": "c1",
                        "status_counts": {"learning": 1},
                        "progress_percent": 0,
                    }
                ]
            },
        },
        "weekly_study_plans.json": {"version": 1, "plans": []},
        "multi_course_weekly_plans.json": {"version": 1, "plans": []},
    }


def _prepare_project(tmp_path: Path):
    root = tmp_path / "project"
    data = root / "data"
    data.mkdir(parents=True)
    for name, payload in _source_payloads().items():
        _write_json(data / name, payload)
    db = data / "learning_assistant.db"
    assert apply_migrations(db)
    connection = sqlite3.connect(str(db), isolation_level=None)
    connection.execute("PRAGMA foreign_keys = ON")
    return root, data, db, connection


def _seed(connection, root, data):
    return seed_phase4_compatibility_projections(
        connection,
        data_directory=data,
        authority_control_path=_control_path(root),
        seeded_at="2099-01-06T00:00:00Z",
    )


def _promote(root):
    write_authority_control_atomic(_control_path(root), _sqlite_state())


def _seed_relational_core(repo: SQLiteCompatibilityProjectionRepository, payloads):
    # The final cutover normally gets these rows from the final delta import.
    # Focused routing tests use the same write-through adapter to synthesize them.
    repo.save_projection("courses", {**payloads["courses.json"], "document_links": {}})
    repo.save_projection("assessments", payloads["assessments.json"])
    repo.save_projection("assessment_workspace", payloads["assessment_workspace.json"])


def test_database_path_is_project_local_and_does_not_create_it(tmp_path):
    store = tmp_path / "project" / "data" / "courses.json"
    expected = tmp_path / "project" / "data" / "learning_assistant.db"
    assert database_path_for_store(store) == expected
    assert not expected.exists()


def test_missing_legacy_control_never_opens_or_creates_sqlite(tmp_path):
    store = tmp_path / "project" / "data" / "assessments.json"
    assert maybe_load_sqlite_structured_store("assessments", store) is None
    assert maybe_save_sqlite_structured_store("assessments", store, {"version": 2, "assessments": []}) is False
    assert not database_path_for_store(store).exists()


def test_dual_read_control_preserves_legacy_path_without_opening_db(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    control = AuthorityControlState(storage_backend="dual_read")
    write_authority_control_atomic(_control_path(root), control)
    store = root / "data" / "assessments.json"
    assert maybe_load_sqlite_structured_store("assessments", store) is None
    assert maybe_save_sqlite_structured_store("assessments", store, {"version": 2, "assessments": []}) is False
    assert not database_path_for_store(store).exists()


def test_sqlite_authority_refuses_missing_database_instead_of_creating_one(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    write_authority_control_atomic(_control_path(root), _sqlite_state())
    store = root / "data" / "assessments.json"
    with pytest.raises(StructuredDatabaseUnavailableError):
        maybe_load_sqlite_structured_store("assessments", store)
    assert not database_path_for_store(store).exists()


def test_projection_seed_is_pre_promotion_only_and_atomic(tmp_path):
    root, data, db, connection = _prepare_project(tmp_path)
    try:
        result = _seed(connection, root, data)
        assert "courses" in result.seeded_stores
        assert "intelligent_study_plans" in result.optional_defaults
        assert "semester_grade_config" in result.optional_defaults
        row = connection.execute("SELECT value_json FROM app_settings WHERE key=?", (SEED_MANIFEST_SETTING,)).fetchone()
        assert row is not None
        assert json.loads(row[0]) == result.manifest_hash
        assert connection.execute(
            "SELECT count(*) FROM app_settings WHERE key LIKE ?",
            (PROJECTION_PREFIX + "%",),
        ).fetchone()[0] == 9
    finally:
        connection.close()


def test_course_seed_does_not_move_phase5_document_links_into_sqlite(tmp_path):
    root, data, db, connection = _prepare_project(tmp_path)
    try:
        _seed(connection, root, data)
        raw = connection.execute(
            "SELECT value_json FROM app_settings WHERE key=?",
            (PROJECTION_PREFIX + "courses",),
        ).fetchone()[0]
        assert json.loads(raw)["document_links"] == {}
    finally:
        connection.close()


def test_sqlite_load_requires_seeded_projection(tmp_path):
    root, data, db, connection = _prepare_project(tmp_path)
    connection.close()
    _promote(root)
    with pytest.raises(SQLiteCompatibilityProjectionMissingError):
        maybe_load_sqlite_structured_store("assessments", data / "assessments.json")


def test_promoted_read_uses_sqlite_projection_not_changed_legacy_bytes(tmp_path):
    root, data, db, connection = _prepare_project(tmp_path)
    try:
        _seed(connection, root, data)
    finally:
        connection.close()
    _promote(root)
    before = maybe_load_sqlite_structured_store("assessments", data / "assessments.json")
    _write_json(data / "assessments.json", {"version": 2, "assessments": [{"id": "stale-json"}]})
    after = maybe_load_sqlite_structured_store("assessments", data / "assessments.json")
    assert before == after
    assert after["assessments"][0]["id"] == "a1"


def test_promoted_course_read_merges_only_deferred_legacy_document_links(tmp_path):
    root, data, db, connection = _prepare_project(tmp_path)
    try:
        _seed(connection, root, data)
    finally:
        connection.close()
    _promote(root)
    value = maybe_load_sqlite_structured_store("courses", data / "courses.json")
    assert value["courses"][0]["id"] == "c1"
    assert "legacy:doc" in value["document_links"]


def test_promoted_course_write_rejects_phase5_document_link_change(tmp_path):
    root, data, db, connection = _prepare_project(tmp_path)
    try:
        _seed(connection, root, data)
    finally:
        connection.close()
    _promote(root)
    value = maybe_load_sqlite_structured_store("courses", data / "courses.json")
    value["document_links"]["new:doc"] = {"course_id": "c1"}
    with pytest.raises(DeferredStructuredDomainWriteError):
        maybe_save_sqlite_structured_store("courses", data / "courses.json", value)


def test_promoted_write_changes_sqlite_not_legacy_json(tmp_path):
    root, data, db, connection = _prepare_project(tmp_path)
    payloads = _source_payloads()
    try:
        _seed(connection, root, data)
    finally:
        connection.close()
    _promote(root)
    legacy_before = (data / "courses.json").read_bytes()
    state = maybe_load_sqlite_structured_store("courses", data / "courses.json")
    state["courses"][0]["status"] = "completed"
    assert maybe_save_sqlite_structured_store("courses", data / "courses.json", state)
    assert (data / "courses.json").read_bytes() == legacy_before
    connection = sqlite3.connect(str(db))
    try:
        assert connection.execute("SELECT status FROM courses WHERE code='C1'").fetchone()[0] == "completed"
    finally:
        connection.close()


def test_assessment_write_through_is_relational_and_keeps_source_bytes(tmp_path):
    root, data, db, connection = _prepare_project(tmp_path)
    payloads = _source_payloads()
    try:
        # promote before synthetic relational setup because runtime command writes are authority-gated
        _seed(connection, root, data)
    finally:
        connection.close()
    _promote(root)
    course_state = maybe_load_sqlite_structured_store("courses", data / "courses.json")
    maybe_save_sqlite_structured_store("courses", data / "courses.json", course_state)
    source_before = (data / "assessments.json").read_bytes()
    state = maybe_load_sqlite_structured_store("assessments", data / "assessments.json")
    state["assessments"][0]["status"] = "completed"
    maybe_save_sqlite_structured_store("assessments", data / "assessments.json", state)
    assert (data / "assessments.json").read_bytes() == source_before
    connection = sqlite3.connect(str(db))
    try:
        assert connection.execute("SELECT status FROM assessments").fetchone()[0] == "completed"
        assert connection.execute("SELECT count(*) FROM academic_events").fetchone()[0] == 1
    finally:
        connection.close()


def test_workspace_write_is_atomic_on_missing_assessment(tmp_path):
    root, data, db, connection = _prepare_project(tmp_path)
    try:
        _seed(connection, root, data)
    finally:
        connection.close()
    _promote(root)
    bad = {"version": 1, "workspaces": {"missing": {"assessment_id": "missing", "questions": []}}}
    connection = sqlite3.connect(str(db))
    before = connection.iterdump()
    before_dump = "\n".join(before)
    connection.close()
    with pytest.raises(Exception):
        maybe_save_sqlite_structured_store("assessment_workspace", data / "assessment_workspace.json", bad)
    connection = sqlite3.connect(str(db))
    try:
        after_dump = "\n".join(connection.iterdump())
        # The failing transaction must not change relational/projection state.
        assert after_dump == before_dump
    finally:
        connection.close()


def test_memory_progress_plan_and_grade_runtime_writes_use_sqlite(tmp_path):
    root, data, db, connection = _prepare_project(tmp_path)
    try:
        _seed(connection, root, data)
    finally:
        connection.close()
    _promote(root)
    # First materialize courses needed by relational FKs.
    course_state = maybe_load_sqlite_structured_store("courses", data / "courses.json")
    maybe_save_sqlite_structured_store("courses", data / "courses.json", course_state)

    memory = maybe_load_sqlite_structured_store("learning_memory", data / "learning_memory.json")
    memory["course_memory"]["c1"]["notes"].append({"text": "SQLite note", "created_at": "2099-02-01"})
    maybe_save_sqlite_structured_store("learning_memory", data / "learning_memory.json", memory)

    progress = maybe_load_sqlite_structured_store("course_progress_history", data / "course_progress_history.json")
    maybe_save_sqlite_structured_store("course_progress_history", data / "course_progress_history.json", progress)

    weekly = {"version": 1, "plans": [{
        "id": "p1", "engine_version": "V9.1", "created_at": "2099-02-01",
        "course_id": "c1", "start_date": "2099-02-01", "total_weekly_minutes": 60,
        "days": [{"date": "2099-02-01", "sessions": [{"course_id": "c1", "topic": "Topic A", "minutes": 60, "actions": ["Study"]}]}],
    }]}
    maybe_save_sqlite_structured_store("weekly_study_plans", data / "weekly_study_plans.json", weekly)

    grade_default = maybe_load_sqlite_structured_store("semester_grade_config", data / "semester_grade_config.json")
    grade_default["courses"] = [{"course_id": "c1", "credits": 4, "manual_grade_point": 9, "manual_letter_grade": "A"}]
    maybe_save_sqlite_structured_store("semester_grade_config", data / "semester_grade_config.json", grade_default)

    connection = sqlite3.connect(str(db))
    try:
        assert connection.execute("SELECT count(*) FROM learning_memory_entries WHERE source_entity_type='phase4_compatibility'").fetchone()[0] >= 1
        assert connection.execute("SELECT count(*) FROM progress_snapshots").fetchone()[0] >= 1
        assert connection.execute("SELECT count(*) FROM study_plans").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM grade_scales").fetchone()[0] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_routed_course_repository_does_not_import_root_course_manager():
    path = ROOT / "personal_learning_assistant" / "repositories" / "routed_course_repository.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "course_manager" not in imported


def test_all_compatibility_writers_have_phase411_router_before_legacy_guard():
    expectations = {
        "course_manager.py": ("courses", "save_course_data"),
        "assignment_exam_assistant.py": ("assessments", "save_store"),
        "assessment_question_workspace.py": ("assessment_workspace", "save_store"),
        "learning_memory.py": ("learning_memory", "save_memory"),
        "academic_progress.py": ("course_progress_history", "save_history"),
        "weekly_planner.py": ("weekly_study_plans", "save_store"),
        "multi_course_planner.py": ("multi_course_weekly_plans", "save_store"),
        "intelligent_study_planner.py": ("intelligent_study_plans", "save_store"),
        "semester_grade_intelligence.py": ("semester_grade_config", "save_config"),
    }
    for filename, (store_name, function_name) in expectations.items():
        text = (ROOT / filename).read_text(encoding="utf-8")
        tree = ast.parse(text)
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == function_name)
        calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
        router_lines = [node.lineno for node in calls if isinstance(node.func, ast.Name) and node.func.id == "maybe_save_sqlite_structured_store"]
        guard_lines = [node.lineno for node in calls if isinstance(node.func, ast.Name) and node.func.id == "guard_legacy_structured_write"]
        assert router_lines, filename
        assert guard_lines, filename
        assert min(router_lines) < min(guard_lines), filename
        assert store_name in text


def test_all_compatibility_reads_check_router_before_legacy_io():
    files = (
        "course_manager.py",
        "assignment_exam_assistant.py",
        "assessment_question_workspace.py",
        "learning_memory.py",
        "academic_progress.py",
        "weekly_planner.py",
        "multi_course_planner.py",
        "intelligent_study_planner.py",
        "semester_grade_intelligence.py",
    )
    for filename in files:
        text = (ROOT / filename).read_text(encoding="utf-8")
        assert "maybe_load_sqlite_structured_store" in text, filename


def test_phase411_modules_have_no_implicit_authority_flip_or_production_creation():
    paths = (
        ROOT / "personal_learning_assistant/repositories/structured_authority_router.py",
        ROOT / "personal_learning_assistant/repositories/sqlite/compatibility_repository.py",
        ROOT / "personal_learning_assistant/migration/compatibility_projection_seed.py",
        ROOT / "personal_learning_assistant/repositories/routed_course_repository.py",
    )
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert "write_authority_control_atomic(" not in source
        assert "mkdir(" not in source
    assert "mode=rw" in (paths[0]).read_text(encoding="utf-8")


def test_baseline_constant_matches_phase410_commit():
    assert BASELINE.startswith("0a92938")


def test_promoted_write_missing_database_preserves_phase410_legacy_block_contract(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    write_authority_control_atomic(_control_path(root), _sqlite_state())
    store = root / "data" / "weekly_study_plans.json"

    with pytest.raises(LegacyWriteBlockedError) as captured:
        maybe_save_sqlite_structured_store(
            "weekly_study_plans",
            store,
            {"version": 1, "plans": []},
        )

    assert isinstance(captured.value.__cause__, StructuredDatabaseUnavailableError)
    assert not store.parent.exists()
    assert not database_path_for_store(store).exists()
