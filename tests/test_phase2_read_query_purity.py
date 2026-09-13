import ast
import json
from pathlib import Path

import academic_progress
import intelligent_study_planner


def _fake_course():
    return {
        "id": "ma103n",
        "code": "MA103N",
        "name": "Linear Algebra",
        "topics": [
            {
                "name": "LU Factorization",
                "status": "learning",
                "confidence": 3,
            },
            {
                "name": "Vector Spaces",
                "status": "not_started",
                "confidence": 0,
            },
        ],
    }


def _fake_progress():
    return {
        "total_topics": 2,
        "mastered_topics": 0,
        "progress_percent": 25,
        "weak_topics": [],
        "missing_topics": ["Vector Spaces"],
    }


def _calls(function, target_name):
    module = __import__(function.__module__)
    module_path = Path(module.__file__)
    tree = ast.parse(module_path.read_text(encoding="utf-8"))

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function.__name__:
            for child in ast.walk(node):
                if not isinstance(child, ast.Call):
                    continue
                if (
                    isinstance(child.func, ast.Name)
                    and child.func.id == target_name
                ):
                    return True
            return False

    raise AssertionError(f"Function {function.__name__} not found")


def _configure_progress(monkeypatch, history_file):
    course = _fake_course()

    monkeypatch.setattr(
        academic_progress,
        "HISTORY_FILE",
        str(history_file),
    )
    monkeypatch.setattr(
        academic_progress,
        "DATA_DIR",
        str(history_file.parent),
    )
    monkeypatch.setattr(
        academic_progress,
        "find_course",
        lambda course_id: course
        if str(course_id).lower() in {"ma103n", "linear algebra"}
        else None,
    )
    monkeypatch.setattr(
        academic_progress,
        "get_course_progress",
        lambda course_id: _fake_progress(),
    )

    return course


def test_build_course_tasks_is_progress_history_query_only():
    assert not _calls(
        intelligent_study_planner.build_course_tasks,
        "record_progress_snapshot",
    )


def test_progress_trend_does_not_record_snapshot():
    assert not _calls(
        academic_progress.get_progress_trend,
        "record_progress_snapshot",
    )


def test_progress_dashboard_does_not_record_snapshot():
    assert not _calls(
        academic_progress.print_progress_dashboard,
        "record_progress_snapshot",
    )


def test_load_history_does_not_create_missing_directory(
    monkeypatch,
    tmp_path,
):
    missing_dir = tmp_path / "not-created-by-read"
    history_file = missing_dir / "course_progress_history.json"

    monkeypatch.setattr(
        academic_progress,
        "DATA_DIR",
        str(missing_dir),
    )
    monkeypatch.setattr(
        academic_progress,
        "HISTORY_FILE",
        str(history_file),
    )

    assert not missing_dir.exists()
    assert academic_progress.load_history() == academic_progress.default_history()
    assert not missing_dir.exists()


def test_get_progress_trend_preserves_history_bytes(
    monkeypatch,
    tmp_path,
):
    history_file = tmp_path / "course_progress_history.json"
    _configure_progress(monkeypatch, history_file)

    stored = {
        "version": 1,
        "courses": {
            "ma103n": [
                {
                    "captured_at": "2026-09-01T20:00:00",
                    "date": "2026-09-01",
                    "course_id": "ma103n",
                    "course_code": "MA103N",
                    "course_name": "Linear Algebra",
                    "total_topics": 2,
                    "mastered_topics": 0,
                    "progress_percent": 10,
                    "average_confidence": 1.0,
                    "status_counts": {},
                    "weak_topics": [],
                    "missing_topics": ["LU Factorization", "Vector Spaces"],
                }
            ]
        },
    }
    history_file.write_text(
        json.dumps(stored, indent=2),
        encoding="utf-8",
    )
    before = history_file.read_bytes()

    trend = academic_progress.get_progress_trend("ma103n")

    assert trend is not None
    assert trend["current"]["progress_percent"] == 25
    assert history_file.read_bytes() == before


def test_progress_dashboard_preserves_history_bytes(
    monkeypatch,
    tmp_path,
    capsys,
):
    history_file = tmp_path / "course_progress_history.json"
    _configure_progress(monkeypatch, history_file)

    stored = {
        "version": 1,
        "courses": {
            "ma103n": []
        },
    }
    history_file.write_text(
        json.dumps(stored, indent=2),
        encoding="utf-8",
    )
    before = history_file.read_bytes()

    academic_progress.print_progress_dashboard("ma103n")
    output = capsys.readouterr().out

    assert "MA103N PROGRESS DASHBOARD" in output
    assert history_file.read_bytes() == before


def test_explicit_snapshot_command_still_writes(
    monkeypatch,
    tmp_path,
):
    history_file = tmp_path / "course_progress_history.json"
    _configure_progress(monkeypatch, history_file)

    assert not history_file.exists()

    snapshot = academic_progress.record_progress_snapshot(
        "ma103n",
        force=True,
    )

    assert snapshot is not None
    assert history_file.exists()

    stored = json.loads(
        history_file.read_text(encoding="utf-8")
    )
    assert len(stored["courses"]["ma103n"]) == 1


def test_planner_no_longer_imports_snapshot_command():
    path = Path(intelligent_study_planner.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "academic_progress"
        ):
            assert all(
                alias.name != "record_progress_snapshot"
                for alias in node.names
            )
