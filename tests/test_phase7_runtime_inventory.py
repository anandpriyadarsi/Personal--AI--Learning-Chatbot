from __future__ import annotations

from pathlib import Path

from personal_learning_assistant.phase7.runtime_inventory import (
    build_inventory,
    render_markdown,
)


def _write(root: Path, rel: str, text: str):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _item(report, path):
    return next(item for item in report["items"] if item["path"] == path)


def test_static_runtime_import_marks_candidate_active(tmp_path):
    _write(tmp_path, "notes.py", "def view_notes():\n    return []\n")
    _write(tmp_path, "app.py", "import notes\n")
    report = build_inventory(tmp_path)
    item = _item(report, "notes.py")
    assert item["status"] == "active_consumer"
    assert item["runtime_consumers"] == ("app.py",)


def test_test_only_import_does_not_prove_runtime_use(tmp_path):
    _write(tmp_path, "notes.py", "def view_notes():\n    return []\n")
    _write(tmp_path, "tests/test_notes.py", "import notes\n")
    report = build_inventory(tmp_path)
    item = _item(report, "notes.py")
    assert item["status"] == "observation_required"
    assert item["runtime_consumers"] == ()
    assert item["test_consumers"] == ("tests/test_notes.py",)
    assert report["summary"]["retirement_candidate_count"] == 0


def test_feature_actions_are_counted_as_dynamic_menu_consumers(tmp_path):
    _write(tmp_path, "dashboard.py", "def show_dashboard():\n    return None\n")
    _write(
        tmp_path,
        "main.py",
        'FEATURE_ACTIONS = {"1": ("dashboard", "show_dashboard")}\n',
    )
    report = build_inventory(tmp_path)
    item = _item(report, "dashboard.py")
    assert item["status"] == "active_consumer"
    assert item["runtime_consumers"] == ("main.py",)
    assert item["dynamic_menu_consumers"] == ("main.py",)


def test_json_repository_family_is_compatibility_required(tmp_path):
    _write(
        tmp_path,
        "personal_learning_assistant/repositories/json/course_repository.py",
        "class LegacyJsonCourseRepository:\n    pass\n",
    )
    report = build_inventory(tmp_path)
    item = _item(
        report,
        "personal_learning_assistant/repositories/json/course_repository.py",
    )
    assert item["component_kind"] == "legacy_json_repository"
    assert item["status"] == "compatibility_required"


def test_phase4_backend_family_is_compatibility_required(tmp_path):
    _write(
        tmp_path,
        "personal_learning_assistant/repositories/course_backend.py",
        "MODE = 'sqlite'\n",
    )
    report = build_inventory(tmp_path)
    item = _item(
        report,
        "personal_learning_assistant/repositories/course_backend.py",
    )
    assert item["component_kind"] == "phase4_compatibility_backend"
    assert item["status"] == "compatibility_required"


def test_data_literals_and_write_signals_are_evidence_not_retirement_proof(tmp_path):
    _write(
        tmp_path,
        "backup.py",
        "from pathlib import Path\n"
        "P = Path('backup/notes_backup.json')\n"
        "def save():\n"
        "    P.write_text('{}', encoding='utf-8')\n",
    )
    report = build_inventory(tmp_path)
    item = _item(report, "backup.py")
    assert "backup/notes_backup.json" in item["data_literals"]
    assert item["write_signal_count"] >= 1
    assert item["status"] == "observation_required"


def test_inventory_is_deterministic_and_markdown_has_warning(tmp_path):
    _write(tmp_path, "notes.py", "VALUE = 1\n")
    first = build_inventory(tmp_path)
    second = build_inventory(tmp_path)
    assert first == second
    markdown = render_markdown(first)
    assert "Static absence is not retirement proof" in markdown
    assert first["inventory_sha256"] == second["inventory_sha256"]


def test_ignored_runtime_directories_are_not_scanned(tmp_path):
    _write(tmp_path, "notes.py", "VALUE = 1\n")
    _write(tmp_path, ".venv/site.py", "import notes\n")
    _write(tmp_path, ".phase5_retrieval/generated.py", "import notes\n")
    report = build_inventory(tmp_path)
    item = _item(report, "notes.py")
    assert item["runtime_consumers"] == ()
