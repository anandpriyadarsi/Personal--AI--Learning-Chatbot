from __future__ import annotations

import hashlib
import importlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from personal_learning_assistant.migration.authority_promotion import (
    BACKEND_SQLITE,
    read_authority_control,
    scan_structured_sources,
)
from personal_learning_assistant.migration.final_locked_promotion import (
    ATTENTION_FILENAME,
    CONFIRMATION_PHRASE,
    CONTROL_FILENAME,
    DATABASE_FILENAME,
    EVIDENCE_FILENAME,
    FinalPromotionExecutionError,
    FinalPromotionPreflightError,
    FinalPromotionRequiresAttention,
    LOCK_FILENAME,
    WORK_DIRECTORY_NAME,
    _bridge_current_progress_history,
    _run_final_imports,
    preflight_final_locked_promotion,
    promote_final_locked_sqlite_authority,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations


MANDATORY = (
    "courses.json",
    "assessments.json",
    "assessment_workspace.json",
    "learning_memory.json",
    "course_progress_history.json",
    "weekly_study_plans.json",
    "multi_course_weekly_plans.json",
)
OPTIONAL = ("intelligent_study_plans.json", "semester_grade_config.json")


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _minimal_sources(root: Path, *, optional: bool = True) -> Path:
    data = root / "data"
    data.mkdir(parents=True)
    payloads = {
        "courses.json": {"version": 1, "active_course_id": None, "courses": [], "document_links": {}},
        "assessments.json": {"version": 2, "assessments": []},
        "assessment_workspace.json": {"version": 1, "workspaces": {}},
        "learning_memory.json": {
            "version": 2,
            "weak_topics": [],
            "mastered_topics": [],
            "recent_activity": [],
            "notes": [],
            "course_memory": {},
        },
        "course_progress_history.json": {"version": 1, "courses": {}},
        "weekly_study_plans.json": {"version": 1, "plans": []},
        "multi_course_weekly_plans.json": {"version": 1, "plans": []},
        "intelligent_study_plans.json": {"version": 1, "plans": []},
        "semester_grade_config.json": {
            "version": 1,
            "semester_name": "Semester 1",
            "target_sgpa": None,
            "courses": [],
            "grade_scale": [],
        },
    }
    names = list(MANDATORY) + (list(OPTIONAL) if optional else [])
    for name in names:
        _write_json(data / name, payloads[name])
    (root / "backups").mkdir()
    return root / "backups" / "final"


def _mock_delta(monkeypatch):
    import personal_learning_assistant.migration.final_locked_promotion as module

    monkeypatch.setattr(module, "_run_final_imports", lambda *a, **k: {"mock": {"changed_rows": 0}})
    monkeypatch.setattr(module, "_bridge_current_progress_history", lambda *a, **k: 0)


def _production_connection(root: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(root / "data" / DATABASE_FILENAME), isolation_level=None)
    connection.row_factory = sqlite3.Row
    return connection


def test_preflight_is_read_only_and_creates_no_runtime_artifact(tmp_path):
    backup = _minimal_sources(tmp_path)
    before = {name: (tmp_path / "data" / name).read_bytes() for name in MANDATORY + OPTIONAL}

    report = preflight_final_locked_promotion(project_root=tmp_path, backup_directory=backup)

    assert report.source_manifest_hash
    assert not report.production_database_exists
    assert not (tmp_path / CONTROL_FILENAME).exists()
    assert not (tmp_path / LOCK_FILENAME).exists()
    assert not (tmp_path / WORK_DIRECTORY_NAME).exists()
    assert not backup.exists()
    assert not (tmp_path / "data" / DATABASE_FILENAME).exists()
    assert before == {name: (tmp_path / "data" / name).read_bytes() for name in before}


def test_preflight_existing_database_is_validated_without_mutating_it(tmp_path):
    backup = _minimal_sources(tmp_path)
    db = tmp_path / "data" / DATABASE_FILENAME
    apply_migrations(db)
    before = _hash(db)

    report = preflight_final_locked_promotion(project_root=tmp_path, backup_directory=backup)

    assert report.production_database_exists
    assert report.migration_versions == (1, 2)
    assert report.integrity_check == ("ok",)
    assert report.foreign_key_violation_count == 0
    assert _hash(db) == before
    assert not (tmp_path / CONTROL_FILENAME).exists()


def test_execution_requires_exact_confirmation_phrase(tmp_path):
    backup = _minimal_sources(tmp_path)
    with pytest.raises(FinalPromotionExecutionError, match="exact confirmation phrase"):
        promote_final_locked_sqlite_authority(
            project_root=tmp_path,
            backup_directory=backup,
            confirmation="yes",
        )
    assert not (tmp_path / LOCK_FILENAME).exists()
    assert not (tmp_path / CONTROL_FILENAME).exists()


def test_existing_lock_blocks_preflight_without_stealing_it(tmp_path):
    backup = _minimal_sources(tmp_path)
    lock = tmp_path / LOCK_FILENAME
    lock.write_text("operator-owned", encoding="utf-8")
    with pytest.raises(FinalPromotionPreflightError, match="lock already exists"):
        preflight_final_locked_promotion(project_root=tmp_path, backup_directory=backup)
    assert lock.read_text(encoding="utf-8") == "operator-owned"


def test_successful_mocked_promotion_switches_authority_and_releases_lock(tmp_path, monkeypatch):
    backup = _minimal_sources(tmp_path)
    _mock_delta(monkeypatch)
    legacy_hashes = {name: _hash(tmp_path / "data" / name) for name in MANDATORY + OPTIONAL}

    result = promote_final_locked_sqlite_authority(
        project_root=tmp_path,
        backup_directory=backup,
        confirmation=CONFIRMATION_PHRASE,
    )

    state = read_authority_control(tmp_path / CONTROL_FILENAME)
    assert state.storage_backend == BACKEND_SQLITE
    assert state.legacy_writes_blocked is True
    assert state.cutover_id == result.cutover_id
    assert _hash(tmp_path / "data" / DATABASE_FILENAME) == state.sqlite_sha256
    assert not (tmp_path / LOCK_FILENAME).exists()
    assert not (tmp_path / WORK_DIRECTORY_NAME).exists()
    assert (backup / EVIDENCE_FILENAME).is_file()
    assert legacy_hashes == {name: _hash(tmp_path / "data" / name) for name in legacy_hashes}


def test_optional_sources_absent_receive_seed_defaults(tmp_path, monkeypatch):
    backup = _minimal_sources(tmp_path, optional=False)
    _mock_delta(monkeypatch)

    result = promote_final_locked_sqlite_authority(
        project_root=tmp_path,
        backup_directory=backup,
        confirmation=CONFIRMATION_PHRASE,
    )

    assert "intelligent_study_plans" in result.compatibility_stores
    assert "semester_grade_config" in result.compatibility_stores
    connection = _production_connection(tmp_path)
    try:
        intelligent = json.loads(
            connection.execute(
                "SELECT value_json FROM app_settings WHERE key=?",
                ("phase4.compatibility_projection.intelligent_study_plans",),
            ).fetchone()[0]
        )
        grade = json.loads(
            connection.execute(
                "SELECT value_json FROM app_settings WHERE key=?",
                ("phase4.compatibility_projection.semester_grade_config",),
            ).fetchone()[0]
        )
    finally:
        connection.close()
    assert intelligent == {"version": 1, "plans": []}
    assert grade["version"] == 1 and grade["courses"] == []


def test_final_backup_preserves_locked_legacy_bytes_exactly(tmp_path, monkeypatch):
    backup = _minimal_sources(tmp_path)
    _mock_delta(monkeypatch)
    originals = {name: (tmp_path / "data" / name).read_bytes() for name in MANDATORY + OPTIONAL}

    promote_final_locked_sqlite_authority(
        project_root=tmp_path,
        backup_directory=backup,
        confirmation=CONFIRMATION_PHRASE,
    )

    for name, raw in originals.items():
        assert (backup / "legacy_structured_json" / name).read_bytes() == raw


def test_existing_shadow_database_is_preserved_before_replacement(tmp_path, monkeypatch):
    backup = _minimal_sources(tmp_path)
    db = tmp_path / "data" / DATABASE_FILENAME
    apply_migrations(db)
    connection = sqlite3.connect(str(db), isolation_level=None)
    try:
        connection.execute(
            "INSERT INTO app_settings(key,value_json,updated_at) VALUES('shadow.marker','\"before\"','2026-09-15T00:00:00Z')"
        )
    finally:
        connection.close()
    _mock_delta(monkeypatch)

    result = promote_final_locked_sqlite_authority(
        project_root=tmp_path,
        backup_directory=backup,
        confirmation=CONFIRMATION_PHRASE,
    )

    preserved = backup / "sqlite" / "pre_promotion_shadow.db"
    assert result.previous_database_existed is True
    assert preserved.is_file()
    check = sqlite3.connect(str(preserved))
    try:
        assert check.execute(
            "SELECT value_json FROM app_settings WHERE key='shadow.marker'"
        ).fetchone()[0] == '"before"'
    finally:
        check.close()


def test_source_drift_before_atomic_switch_aborts_and_restores_legacy_authority(tmp_path, monkeypatch):
    backup = _minimal_sources(tmp_path)
    _mock_delta(monkeypatch)
    import personal_learning_assistant.migration.final_locked_promotion as module

    real_install = module._install_verified_database

    def install_then_drift(*args, **kwargs):
        real_install(*args, **kwargs)
        path = tmp_path / "data" / "courses.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["drift"] = True
        _write_json(path, value)

    monkeypatch.setattr(module, "_install_verified_database", install_then_drift)
    with pytest.raises(Exception, match="changed"):
        promote_final_locked_sqlite_authority(
            project_root=tmp_path,
            backup_directory=backup,
            confirmation=CONFIRMATION_PHRASE,
        )
    assert not (tmp_path / CONTROL_FILENAME).exists()
    assert not (tmp_path / LOCK_FILENAME).exists()
    assert not (tmp_path / "data" / DATABASE_FILENAME).exists()


def test_failure_before_switch_restores_existing_shadow_and_releases_lock(tmp_path, monkeypatch):
    backup = _minimal_sources(tmp_path)
    db = tmp_path / "data" / DATABASE_FILENAME
    apply_migrations(db)
    connection = sqlite3.connect(str(db), isolation_level=None)
    try:
        connection.execute(
            "INSERT INTO app_settings(key,value_json,updated_at) VALUES('restore.marker','\"old\"','2026-09-15T00:00:00Z')"
        )
    finally:
        connection.close()
    _mock_delta(monkeypatch)
    import personal_learning_assistant.migration.final_locked_promotion as module

    monkeypatch.setattr(
        module,
        "write_authority_control_atomic",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("switch denied")),
    )
    with pytest.raises(RuntimeError, match="switch denied"):
        promote_final_locked_sqlite_authority(
            project_root=tmp_path,
            backup_directory=backup,
            confirmation=CONFIRMATION_PHRASE,
        )
    assert not (tmp_path / CONTROL_FILENAME).exists()
    assert not (tmp_path / LOCK_FILENAME).exists()
    check = sqlite3.connect(str(db))
    try:
        assert check.execute(
            "SELECT value_json FROM app_settings WHERE key='restore.marker'"
        ).fetchone()[0] == '"old"'
    finally:
        check.close()


def test_post_switch_failure_leaves_lock_and_attention_evidence(tmp_path, monkeypatch):
    backup = _minimal_sources(tmp_path)
    _mock_delta(monkeypatch)
    import personal_learning_assistant.migration.final_locked_promotion as module

    monkeypatch.setattr(
        module,
        "_post_promotion_checks",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("post smoke failed")),
    )
    with pytest.raises(FinalPromotionRequiresAttention, match="lock was intentionally retained"):
        promote_final_locked_sqlite_authority(
            project_root=tmp_path,
            backup_directory=backup,
            confirmation=CONFIRMATION_PHRASE,
        )
    assert read_authority_control(tmp_path / CONTROL_FILENAME).storage_backend == BACKEND_SQLITE
    assert (tmp_path / LOCK_FILENAME).is_file()
    assert (backup / ATTENTION_FILENAME).is_file()



def test_control_change_during_switch_refuses_automatic_database_rollback(tmp_path, monkeypatch):
    backup = _minimal_sources(tmp_path)
    _mock_delta(monkeypatch)
    import personal_learning_assistant.migration.final_locked_promotion as module

    real_writer = module.write_authority_control_atomic

    def write_then_raise(*args, **kwargs):
        real_writer(*args, **kwargs)
        raise RuntimeError("simulated exception after external/control replacement")

    monkeypatch.setattr(module, "write_authority_control_atomic", write_then_raise)
    with pytest.raises(FinalPromotionRequiresAttention, match="automatic rollback was refused"):
        promote_final_locked_sqlite_authority(
            project_root=tmp_path,
            backup_directory=backup,
            confirmation=CONFIRMATION_PHRASE,
        )
    assert read_authority_control(tmp_path / CONTROL_FILENAME).storage_backend == BACKEND_SQLITE
    assert (tmp_path / LOCK_FILENAME).is_file()
    assert (tmp_path / "data" / DATABASE_FILENAME).is_file()
    assert (backup / ATTENTION_FILENAME).is_file()

def test_second_promotion_is_rejected_after_success(tmp_path, monkeypatch):
    backup = _minimal_sources(tmp_path)
    _mock_delta(monkeypatch)
    promote_final_locked_sqlite_authority(
        project_root=tmp_path,
        backup_directory=backup,
        confirmation=CONFIRMATION_PHRASE,
    )
    other = tmp_path / "backups" / "second"
    with pytest.raises(FinalPromotionPreflightError, match="already authoritative"):
        preflight_final_locked_promotion(project_root=tmp_path, backup_directory=other)


def _bridge_project(tmp_path: Path):
    backup = _minimal_sources(tmp_path)
    _write_json(
        tmp_path / "data" / "courses.json",
        {
            "version": 1,
            "active_course_id": "c1",
            "courses": [
                {
                    "id": "c1",
                    "code": "MA1",
                    "name": "Synthetic Algebra",
                    "semester": "1",
                    "status": "active",
                    "topics": [],
                    "created_at": "2026-09-01T00:00:00",
                    "updated_at": "2026-09-01T00:00:00",
                }
            ],
            "document_links": {},
        },
    )
    _write_json(
        tmp_path / "data" / "course_progress_history.json",
        {
            "version": 1,
            "courses": {
                "c1": [
                    {
                        "date": "2026-09-15",
                        "course_id": "c1",
                        "mastered_topics": 2,
                        "total_topics": 4,
                        "progress_percent": 50,
                    }
                ]
            },
        },
    )
    manifest = scan_structured_sources(tmp_path / "data")
    db = tmp_path / "bridge.db"
    apply_migrations(db)
    connection = sqlite3.connect(str(db), isolation_level=None)
    connection.row_factory = sqlite3.Row
    from personal_learning_assistant.migration.courses_topics_importer import import_courses_and_topics

    by_path = {item.canonical_path: item for item in manifest.sources}
    import_courses_and_topics(
        connection,
        by_path["data/courses.json"],
        imported_at="2026-09-15T10:00:00Z",
    )
    return connection, by_path


def test_current_courses_shape_progress_bridge_records_recognized_ledger_evidence(tmp_path):
    connection, by_path = _bridge_project(tmp_path)
    try:
        count = _bridge_current_progress_history(
            connection,
            by_path["data/course_progress_history.json"],
            by_path["data/courses.json"],
            imported_at="2026-09-15T10:01:00Z",
        )
        row = connection.execute(
            "SELECT ps.snapshot_date, ps.counts_json, ps.score_json, mi.details_json "
            "FROM progress_snapshots ps JOIN migration_imports mi ON mi.target_id=ps.id "
            "WHERE mi.target_table='progress_snapshots'"
        ).fetchone()
    finally:
        connection.close()
    assert count == 1
    assert row[0] == "2026-09-15"
    assert json.loads(row[1]) == {"mastered_topics": 2, "total_topics": 4}
    assert json.loads(row[2]) == {"progress_percent": 50}
    details = json.loads(row[3])
    assert details["kind"] == "course_progress_snapshot"
    assert details["source_shape"] == "courses"


def test_progress_bridge_blocks_contradictory_history_and_courses_shapes(tmp_path):
    connection, by_path = _bridge_project(tmp_path)
    connection.close()
    progress_path = tmp_path / "data" / "course_progress_history.json"
    payload = json.loads(progress_path.read_text(encoding="utf-8"))
    payload["history"] = {
        "c1": [
            {
                "date": "2026-09-15",
                "mastered_topics": 1,
                "total_topics": 4,
                "progress_percent": 25,
            }
        ]
    }
    _write_json(progress_path, payload)
    manifest = scan_structured_sources(tmp_path / "data")
    by_path = {item.canonical_path: item for item in manifest.sources}
    db = tmp_path / "bridge2.db"
    apply_migrations(db)
    connection = sqlite3.connect(str(db), isolation_level=None)
    connection.row_factory = sqlite3.Row
    from personal_learning_assistant.migration.courses_topics_importer import import_courses_and_topics

    import_courses_and_topics(
        connection,
        by_path["data/courses.json"],
        imported_at="2026-09-15T10:00:00Z",
    )
    try:
        with pytest.raises(Exception, match="contradictory progress-history evidence"):
            _bridge_current_progress_history(
                connection,
                by_path["data/course_progress_history.json"],
                by_path["data/courses.json"],
                imported_at="2026-09-15T10:01:00Z",
            )
    finally:
        connection.close()


def test_final_import_orchestration_uses_dependency_order(tmp_path, monkeypatch):
    _minimal_sources(tmp_path)
    manifest = scan_structured_sources(tmp_path / "data")
    db = tmp_path / "order.db"
    apply_migrations(db)
    connection = sqlite3.connect(str(db), isolation_level=None)
    connection.row_factory = sqlite3.Row
    order = []
    patches = [
        ("personal_learning_assistant.migration.courses_topics_importer", "import_courses_and_topics", "courses"),
        ("personal_learning_assistant.migration.assessments_topics_importer", "import_assessments_and_topics", "assessments"),
        ("personal_learning_assistant.migration.questions_sources_importer", "import_questions_and_sources", "questions"),
        ("personal_learning_assistant.migration.question_topic_mappings_importer", "import_question_topic_mappings", "mappings"),
        ("personal_learning_assistant.migration.attempts_performance_importer", "import_attempts_mistakes_and_performance", "attempts"),
        ("personal_learning_assistant.migration.learning_progress_importer", "import_learning_memory_and_progress", "learning"),
        ("personal_learning_assistant.migration.study_plans_importer", "import_study_plans", "plans"),
        ("personal_learning_assistant.migration.grades_calendar_importer", "import_grades_and_academic_calendar", "grades"),
    ]
    for module_name, function_name, label in patches:
        module = importlib.import_module(module_name)

        def fake(*args, _label=label, **kwargs):
            order.append(_label)
            return SimpleNamespace(changed_rows=0, review_required_items=0)

        monkeypatch.setattr(module, function_name, fake)
    try:
        summaries = _run_final_imports(
            connection,
            manifest,
            imported_at="2026-09-15T10:00:00Z",
        )
    finally:
        connection.close()
    assert order == [
        "courses",
        "assessments",
        "questions",
        "mappings",
        "attempts",
        "learning",
        "plans",
        "grades",
    ]
    assert set(summaries) == {
        "courses_topics",
        "assessments_topics",
        "questions_sources",
        "question_topic_mappings",
        "attempts_performance",
        "learning_progress",
        "study_plans",
        "grades_calendar",
    }


def test_existing_backup_directory_is_never_overwritten(tmp_path):
    backup = _minimal_sources(tmp_path)
    backup.mkdir()
    marker = backup / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    with pytest.raises(FinalPromotionPreflightError, match="already exists"):
        preflight_final_locked_promotion(project_root=tmp_path, backup_directory=backup)
    assert marker.read_text(encoding="utf-8") == "keep"
