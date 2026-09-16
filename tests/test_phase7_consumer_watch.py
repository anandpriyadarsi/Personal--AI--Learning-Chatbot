from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from personal_learning_assistant.phase7.consumer_watch import (
    ObservationIntegrityError,
    ObservationSafetyError,
    build_observation_report,
    preview_consumer_watch,
    run_observed_script,
)


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    _write(
        project,
        "main.py",
        "import notes\n"
        "def run():\n"
        "    secret = 'DO-NOT-LOG-ACADEMIC-CONTENT'\n"
        "    return notes.view_notes(secret)\n"
        "if __name__ == '__main__':\n"
        "    run()\n",
    )
    _write(
        project,
        "notes.py",
        "def view_notes(value):\n"
        "    return len(value)\n",
    )
    _write(
        project,
        "helper.py",
        "def helper():\n"
        "    return 'not-a-candidate'\n",
    )
    return project


def _run(tmp_path: Path):
    project = _project(tmp_path)
    observation = tmp_path / "phase7-consumer-watch"
    result = run_observed_script(
        project_root=project,
        observation_root=observation,
        script_path="main.py",
    )
    report = build_observation_report(
        project_root=project,
        observation_root=observation,
    )
    return project, observation, result, report


def _component(report, path):
    return next(
        item for item in report["components"]
        if item["path"] == path
    )


def test_preview_is_read_only_and_declares_zero_retirement_decisions(tmp_path):
    project = _project(tmp_path)
    before = sorted(
        path.relative_to(project).as_posix()
        for path in project.rglob("*")
        if path.is_file()
    )
    preview = preview_consumer_watch(project)
    after = sorted(
        path.relative_to(project).as_posix()
        for path in project.rglob("*")
        if path.is_file()
    )
    assert preview["writes_performed"] is False
    assert preview["retirement_decisions_performed"] is False
    assert preview["candidate_count"] >= 2
    assert before == after


def test_observed_script_records_candidate_runtime_use(tmp_path):
    project, observation, result, report = _run(tmp_path)
    assert result.state == "completed"
    assert result.exit_code == 0
    assert _component(
        report,
        "main.py",
    )["runtime_observation_state"] == "observed_runtime_use"
    assert _component(
        report,
        "notes.py",
    )["runtime_observation_state"] == "observed_runtime_use"
    assert report["summary"]["observed_component_count"] >= 2


def test_event_stream_contains_no_argument_or_academic_content(tmp_path):
    project, observation, result, report = _run(tmp_path)
    events_path = (
        observation
        / "sessions"
        / (result.session_id + ".events.jsonl")
    )
    raw = events_path.read_text(encoding="utf-8")
    assert "DO-NOT-LOG-ACADEMIC-CONTENT" not in raw
    for line in raw.splitlines():
        event = json.loads(line)
        assert event["privacy"]["arguments_captured"] is False
        assert event["privacy"]["locals_captured"] is False
        assert event["privacy"]["return_value_captured"] is False
        assert event["privacy"]["content_captured"] is False


def test_event_paths_are_project_relative_or_external(tmp_path):
    project, observation, result, report = _run(tmp_path)
    events_path = (
        observation
        / "sessions"
        / (result.session_id + ".events.jsonl")
    )
    raw = events_path.read_text(encoding="utf-8")
    assert str(project.resolve()) not in raw
    for line in raw.splitlines():
        event = json.loads(line)
        assert not Path(event["component_path"]).is_absolute()
        caller = event["caller_path"]
        assert caller == "<external>" or not Path(caller).is_absolute()


def test_noncandidate_helper_is_not_logged(tmp_path):
    project = _project(tmp_path)
    _write(
        project,
        "main.py",
        "import helper\n"
        "if __name__ == '__main__':\n"
        "    helper.helper()\n",
    )
    observation = tmp_path / "phase7-consumer-watch"
    result = run_observed_script(
        project_root=project,
        observation_root=observation,
        script_path="main.py",
    )
    raw = (
        observation
        / "sessions"
        / (result.session_id + ".events.jsonl")
    ).read_text(encoding="utf-8")
    assert '"component_path":"helper.py"' not in raw


def test_observed_scripts_use_their_own_modules_across_projects(tmp_path):
    original_path = sys.path[:]
    original_notes = sys.modules.get("notes")

    for name in ("first", "second"):
        parent = tmp_path / name
        parent.mkdir()
        project = _project(parent)
        observation = parent / "phase7-consumer-watch"
        result = run_observed_script(
            project_root=project,
            observation_root=observation,
            script_path="main.py",
        )
        report = build_observation_report(
            project_root=project,
            observation_root=observation,
        )

        assert result.state == "completed"
        assert _component(report, "notes.py")["observed_session_count"] == 1
        assert sys.path == original_path
        assert sys.modules.get("notes") is original_notes


def test_report_never_converts_unobserved_into_retirement_candidate(tmp_path):
    project = _project(tmp_path)
    _write(project, "resources.py", "def view_resources():\n    return []\n")
    observation = tmp_path / "phase7-consumer-watch"
    run_observed_script(
        project_root=project,
        observation_root=observation,
        script_path="main.py",
    )
    report = build_observation_report(
        project_root=project,
        observation_root=observation,
    )
    resources = _component(report, "resources.py")
    assert resources["runtime_observation_state"] == "not_observed_yet"
    assert resources["retirement_decision"] == "not_made"
    assert report["summary"]["retirement_candidate_count"] == 0


def test_multiple_sessions_aggregate_without_overwriting_evidence(tmp_path):
    project = _project(tmp_path)
    observation = tmp_path / "phase7-consumer-watch"
    first = run_observed_script(
        project_root=project,
        observation_root=observation,
        script_path="main.py",
    )
    second = run_observed_script(
        project_root=project,
        observation_root=observation,
        script_path="main.py",
    )
    assert first.session_id != second.session_id
    report = build_observation_report(
        project_root=project,
        observation_root=observation,
    )
    assert report["summary"]["complete_session_count"] == 2
    assert _component(report, "notes.py")["observed_session_count"] == 2


def test_tampered_event_stream_is_rejected(tmp_path):
    project, observation, result, report = _run(tmp_path)
    events_path = (
        observation
        / "sessions"
        / (result.session_id + ".events.jsonl")
    )
    events_path.write_text(
        events_path.read_text(encoding="utf-8") + "{}\n",
        encoding="utf-8",
    )
    with pytest.raises(ObservationIntegrityError):
        build_observation_report(
            project_root=project,
            observation_root=observation,
        )


def test_observation_root_inside_project_is_rejected(tmp_path):
    project = _project(tmp_path)
    with pytest.raises(ObservationSafetyError):
        run_observed_script(
            project_root=project,
            observation_root=project / "phase7-consumer-watch",
            script_path="main.py",
        )


def test_observed_script_outside_project_is_rejected(tmp_path):
    project = _project(tmp_path)
    external = tmp_path / "external.py"
    external.write_text("print('x')\n", encoding="utf-8")
    with pytest.raises(ObservationSafetyError):
        run_observed_script(
            project_root=project,
            observation_root=tmp_path / "phase7-consumer-watch",
            script_path=external,
        )


def test_incomplete_session_is_reported_not_treated_as_complete(tmp_path):
    project = _project(tmp_path)
    observation = tmp_path / "phase7-consumer-watch"
    result = run_observed_script(
        project_root=project,
        observation_root=observation,
        script_path="main.py",
    )
    completed = (
        observation
        / "sessions"
        / (result.session_id + ".completed.json")
    )
    completed.unlink()
    report = build_observation_report(
        project_root=project,
        observation_root=observation,
    )
    assert report["summary"]["complete_session_count"] == 0
    assert report["summary"]["incomplete_session_count"] == 1
    assert _component(
        report,
        "main.py",
    )["runtime_observation_state"] == "observed_runtime_use"
    assert _component(
        report,
        "main.py",
    )["observed_complete_session_count"] == 0
