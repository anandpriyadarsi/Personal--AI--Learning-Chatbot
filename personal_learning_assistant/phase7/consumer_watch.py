"""Phase 7.4 privacy-minimal Legacy Usage Observation / Consumer Watch.

Phase 7.1 establishes a conservative static candidate inventory.  This module
adds runtime evidence without modifying the legacy modules themselves.

Observation is opt-in: the operator launches an existing repository Python
script through the Phase 7.4 runner.  A Python profile hook records only calls
whose executing source file is one of the Phase 7.1 candidates.

Never captured:
- function arguments or return values;
- locals/globals;
- note/resource/query/assessment content;
- environment variables;
- absolute project/source/vault paths;
- provider/network traffic.

The observation directory must remain outside the project.  Session evidence is
append-only: each session receives new started/events/completed files and
existing evidence is never overwritten.
"""

from __future__ import annotations

import hashlib
import json
import os
import runpy
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from personal_learning_assistant.phase7.runtime_inventory import build_inventory


OBSERVATION_SCHEMA_VERSION = 1
SESSION_SCHEMA_VERSION = 1
REPORT_SCHEMA_VERSION = 1

_REQUIRED_ROOT_MARKERS = ("phase7", "consumer", "watch", "observation")
_SKIP_CALLER_PARTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".phase5_retrieval",
}


class ConsumerWatchError(RuntimeError):
    pass


class ObservationSafetyError(ConsumerWatchError):
    pass


class ObservationIntegrityError(ConsumerWatchError):
    pass


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _canonical_bytes(value) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_new_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise ObservationSafetyError(
            "observation evidence already exists: {}".format(path.name)
        )
    path.write_bytes(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ).encode("utf-8")
        + b"\n"
    )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _assert_no_symlink_chain(path: Path) -> None:
    current = path
    while True:
        if current.exists() and current.is_symlink():
            raise ObservationSafetyError(
                "observation path cannot traverse a symlink"
            )
        if current.parent == current:
            break
        current = current.parent


def validate_observation_root(
    observation_root,
    *,
    project_root,
    create: bool,
) -> Path:
    project = Path(project_root).resolve()
    root = Path(observation_root)

    if root.exists() and root.is_symlink():
        raise ObservationSafetyError(
            "observation root must not be a symlink"
        )
    _assert_no_symlink_chain(root.parent)

    resolved = root.resolve(strict=False)
    if resolved == project or _is_relative_to(resolved, project):
        raise ObservationSafetyError(
            "observation root must remain outside the project"
        )
    if _is_relative_to(project, resolved):
        raise ObservationSafetyError(
            "observation root must not contain the project"
        )

    leaf = root.name.casefold()
    if not any(marker in leaf for marker in _REQUIRED_ROOT_MARKERS):
        raise ObservationSafetyError(
            "observation root name must clearly identify Phase 7 consumer observation"
        )

    if root.exists():
        if not root.is_dir():
            raise ObservationSafetyError(
                "observation root must be a directory"
            )
    elif create:
        if not root.parent.is_dir():
            raise ObservationSafetyError(
                "observation root parent must already exist"
            )
        root.mkdir()
    return root


def _portable_project_path(project_root: Path, filename: str) -> str:
    if not filename:
        return "<external>"
    candidate = Path(filename)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    try:
        resolved = candidate.resolve(strict=False)
        relative = resolved.relative_to(project_root)
    except (OSError, ValueError):
        return "<external>"
    if any(part in _SKIP_CALLER_PARTS for part in relative.parts):
        return "<external>"
    return relative.as_posix()


def _candidate_map(project_root: Path, inventory: Mapping[str, object]):
    by_path = {}
    by_abs = {}
    for item in inventory["items"]:
        rel = str(item["path"]).replace("\\", "/")
        by_path[rel] = item
        absolute = os.path.normcase(
            os.path.abspath(os.fspath(project_root / Path(rel)))
        )
        by_abs[absolute] = rel
    return by_path, by_abs


@dataclass(frozen=True)
class ObservationRunResult:
    session_id: str
    state: str
    unique_event_count: int
    observed_component_count: int
    event_stream_sha256: str
    exit_code: int


class ConsumerProfiler:
    """Collect first-seen runtime use of Phase 7.1 candidates."""

    def __init__(
        self,
        *,
        project_root: Path,
        inventory: Mapping[str, object],
        events_path: Path,
    ):
        self.project_root = project_root
        self.inventory = inventory
        self.by_path, self.by_abs = _candidate_map(project_root, inventory)
        self.events_path = events_path
        self._file_cache: Dict[str, Optional[str]] = {}
        self._seen = set()
        self._observed_components = set()
        self._sequence = 0
        self._handle = None
        self._previous_profile = None
        self._previous_thread_profile = None

    def _component_for_filename(self, filename: str) -> Optional[str]:
        cached = self._file_cache.get(filename)
        if filename in self._file_cache:
            return cached
        candidate = Path(filename)
        if not candidate.is_absolute():
            candidate = self.project_root / candidate
        absolute = os.path.normcase(
            os.path.abspath(os.fspath(candidate))
        )
        component = self.by_abs.get(absolute)
        self._file_cache[filename] = component
        return component

    def _caller_path(self, frame) -> str:
        caller = frame.f_back
        if caller is None:
            return "<external>"
        return _portable_project_path(
            self.project_root,
            str(caller.f_code.co_filename),
        )

    def _record(self, frame) -> None:
        component = self._component_for_filename(
            str(frame.f_code.co_filename)
        )
        if component is None:
            return
        symbol = str(frame.f_code.co_name)
        activity = "module_load" if symbol == "<module>" else "python_call"
        caller_path = self._caller_path(frame)
        caller_component = (
            caller_path if caller_path in self.by_path else None
        )
        key = (
            component,
            activity,
            symbol,
            caller_path,
            int(frame.f_code.co_firstlineno),
        )
        if key in self._seen:
            return
        self._seen.add(key)
        self._observed_components.add(component)
        self._sequence += 1

        item = self.by_path[component]
        event = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "event_sequence": self._sequence,
            "observed_at": _utc_now(),
            "component_path": component,
            "component_module": str(item["module"]),
            "component_kind": str(item["component_kind"]),
            "static_status": str(item["status"]),
            "activity": activity,
            "symbol": symbol,
            "first_line": int(frame.f_code.co_firstlineno),
            "caller_path": caller_path,
            "caller_component": caller_component,
            "privacy": {
                "arguments_captured": False,
                "locals_captured": False,
                "return_value_captured": False,
                "content_captured": False,
                "absolute_project_path_captured": False,
            },
        }
        line = json.dumps(
            event,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self._handle.write(line + "\n")
        self._handle.flush()

    def _profile(self, frame, event, arg):
        if event == "call":
            self._record(frame)
        return self._profile

    def start(self) -> None:
        if self.events_path.exists() or self.events_path.is_symlink():
            raise ObservationSafetyError(
                "session event stream already exists"
            )
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.events_path.open(
            "x",
            encoding="utf-8",
            newline="\n",
        )
        self._previous_profile = sys.getprofile()
        get_thread_profile = getattr(threading, "getprofile", None)
        self._previous_thread_profile = (
            get_thread_profile() if get_thread_profile is not None else None
        )
        sys.setprofile(self._profile)
        threading.setprofile(self._profile)

    def stop(self) -> None:
        sys.setprofile(self._previous_profile)
        threading.setprofile(self._previous_thread_profile)
        if self._handle is not None:
            self._handle.flush()
            self._handle.close()
            self._handle = None

    @property
    def unique_event_count(self) -> int:
        return len(self._seen)

    @property
    def observed_component_count(self) -> int:
        return len(self._observed_components)


def preview_consumer_watch(project_root) -> dict:
    project = Path(project_root).resolve()
    inventory = build_inventory(project)
    return {
        "mode": "preview",
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "candidate_count": int(inventory["summary"]["candidate_count"]),
        "inventory_sha256": str(inventory["inventory_sha256"]),
        "static_status_counts": dict(
            inventory["summary"]["status_counts"]
        ),
        "privacy": {
            "arguments_captured": False,
            "locals_captured": False,
            "return_values_captured": False,
            "academic_content_captured": False,
            "environment_captured": False,
            "absolute_project_path_captured": False,
        },
        "writes_performed": False,
        "retirement_decisions_performed": False,
    }


def _validate_script(project_root: Path, script_path) -> Tuple[Path, str]:
    script = Path(script_path)
    if not script.is_absolute():
        script = project_root / script
    if not script.is_file() or script.is_symlink():
        raise ObservationSafetyError(
            "observed script must be an existing regular project file"
        )
    resolved = script.resolve()
    try:
        relative = resolved.relative_to(project_root)
    except ValueError as error:
        raise ObservationSafetyError(
            "observed script must remain inside the project"
        ) from error
    if any(part in _SKIP_CALLER_PARTS for part in relative.parts):
        raise ObservationSafetyError(
            "observed script is inside an excluded runtime directory"
        )
    return resolved, relative.as_posix()


def run_observed_script(
    *,
    project_root,
    observation_root,
    script_path,
    script_args: Sequence[str] = (),
) -> ObservationRunResult:
    project = Path(project_root).resolve()
    root = validate_observation_root(
        observation_root,
        project_root=project,
        create=True,
    )
    script, relative_script = _validate_script(project, script_path)
    inventory = build_inventory(project)

    session_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex
    )
    sessions = root / "sessions"
    sessions.mkdir(exist_ok=True)
    started_path = sessions / (session_id + ".started.json")
    events_path = sessions / (session_id + ".events.jsonl")
    completed_path = sessions / (session_id + ".completed.json")

    started_at = _utc_now()
    started_mono = time.monotonic()
    _write_new_json(
        started_path,
        {
            "schema_version": SESSION_SCHEMA_VERSION,
            "session_id": session_id,
            "state": "started",
            "started_at": started_at,
            "inventory_sha256": str(inventory["inventory_sha256"]),
            "target": {
                "kind": "project_script",
                "path": relative_script,
                "argument_count": len(tuple(script_args)),
                "argument_values_captured": False,
            },
            "privacy": {
                "arguments_captured": False,
                "locals_captured": False,
                "return_values_captured": False,
                "academic_content_captured": False,
                "environment_captured": False,
                "absolute_project_path_captured": False,
            },
        },
    )

    profiler = ConsumerProfiler(
        project_root=project,
        inventory=inventory,
        events_path=events_path,
    )
    state = "completed"
    exit_code = 0
    error_type = None
    old_argv = sys.argv[:]
    old_cwd = Path.cwd()
    old_sys_path = sys.path[:]
    local_names = {
        path.stem
        for path in script.parent.glob("*.py")
        if path.name != "__init__.py"
    }
    local_names.update(
        path.name
        for path in script.parent.iterdir()
        if path.is_dir() and (path / "__init__.py").is_file()
    )
    previous_local_modules = {
        name: module
        for name, module in sys.modules.items()
        if name.partition(".")[0] in local_names
    }

    try:
        # runpy does not give file scripts the import path that python script.py
        # provides. Hide cached modules from other projects for this run only.
        for name, module in previous_local_modules.items():
            origin = getattr(module, "__file__", None)
            if origin and not _is_relative_to(
                Path(origin).resolve(strict=False), project
            ):
                sys.modules.pop(name, None)
        sys.path.insert(0, str(script.parent))
        sys.argv = [str(script)] + [str(value) for value in script_args]
        os.chdir(project)
        profiler.start()
        try:
            runpy.run_path(str(script), run_name="__main__")
        except SystemExit as error:
            raw = error.code
            if raw is None:
                exit_code = 0
            elif isinstance(raw, int):
                exit_code = raw
            else:
                exit_code = 1
            if exit_code != 0:
                state = "system_exit"
        except KeyboardInterrupt:
            state = "interrupted"
            exit_code = 130
            error_type = "KeyboardInterrupt"
        except BaseException as error:
            state = "error"
            exit_code = 1
            error_type = type(error).__name__
            raise
        finally:
            profiler.stop()
    finally:
        sys.path[:] = old_sys_path
        for name in tuple(sys.modules):
            if name.partition(".")[0] in local_names and (
                name not in previous_local_modules
                or sys.modules[name] is not previous_local_modules[name]
            ):
                sys.modules.pop(name, None)
        sys.modules.update(previous_local_modules)
        os.chdir(old_cwd)
        sys.argv = old_argv
        ended_at = _utc_now()
        duration = max(0.0, time.monotonic() - started_mono)
        stream_sha = (
            _sha256_file(events_path)
            if events_path.is_file()
            else _sha256_bytes(b"")
        )
        completion = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "session_id": session_id,
            "state": state,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": round(duration, 6),
            "exit_code": int(exit_code),
            "error_type": error_type,
            "inventory_sha256": str(inventory["inventory_sha256"]),
            "target_path": relative_script,
            "event_stream_sha256": stream_sha,
            "unique_event_count": profiler.unique_event_count,
            "observed_component_count": profiler.observed_component_count,
            "privacy": {
                "argument_values_captured": False,
                "locals_captured": False,
                "return_values_captured": False,
                "academic_content_captured": False,
                "environment_captured": False,
                "absolute_project_path_captured": False,
            },
        }
        _write_new_json(completed_path, completion)

    return ObservationRunResult(
        session_id=session_id,
        state=state,
        unique_event_count=profiler.unique_event_count,
        observed_component_count=profiler.observed_component_count,
        event_stream_sha256=_sha256_file(events_path),
        exit_code=exit_code,
    )


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ObservationIntegrityError(
            "invalid observation evidence {}".format(path.name)
        ) from error


def _load_events(path: Path) -> Tuple[dict, ...]:
    events = []
    if not path.is_file() or path.is_symlink():
        raise ObservationIntegrityError(
            "session event stream is missing or unsafe"
        )
    for number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError as error:
            raise ObservationIntegrityError(
                "invalid event JSON at {} line {}".format(
                    path.name, number
                )
            ) from error
        if not isinstance(event, dict):
            raise ObservationIntegrityError(
                "observation event must be an object"
            )
        events.append(event)
    return tuple(events)


def _session_records(observation_root: Path):
    sessions_dir = observation_root / "sessions"
    if not sessions_dir.exists():
        return (), (), ()
    if not sessions_dir.is_dir() or sessions_dir.is_symlink():
        raise ObservationIntegrityError(
            "sessions path is missing or unsafe"
        )

    started = {
        path.name[: -len(".started.json")]: path
        for path in sessions_dir.glob("*.started.json")
        if path.is_file() and not path.is_symlink()
    }
    completed = {
        path.name[: -len(".completed.json")]: path
        for path in sessions_dir.glob("*.completed.json")
        if path.is_file() and not path.is_symlink()
    }

    complete_records = []
    incomplete_records = []
    orphan_completed = []

    for session_id, started_path in sorted(started.items()):
        start = _load_json(started_path)
        events_path = sessions_dir / (session_id + ".events.jsonl")
        completion_path = completed.get(session_id)
        events = _load_events(events_path)

        if completion_path is None:
            incomplete_records.append(
                {
                    "session_id": session_id,
                    "started": start,
                    "events": events,
                }
            )
            continue

        completion = _load_json(completion_path)
        actual_sha = _sha256_file(events_path)
        if actual_sha != str(completion.get("event_stream_sha256", "")):
            raise ObservationIntegrityError(
                "event stream hash mismatch for session {}".format(
                    session_id
                )
            )
        if int(completion.get("unique_event_count", -1)) != len(events):
            raise ObservationIntegrityError(
                "event count mismatch for session {}".format(session_id)
            )
        complete_records.append(
            {
                "session_id": session_id,
                "started": start,
                "completed": completion,
                "events": events,
            }
        )

    for session_id, path in sorted(completed.items()):
        if session_id not in started:
            orphan_completed.append(session_id)

    return (
        tuple(complete_records),
        tuple(incomplete_records),
        tuple(orphan_completed),
    )


def build_observation_report(
    *,
    project_root,
    observation_root,
) -> dict:
    project = Path(project_root).resolve()
    root = validate_observation_root(
        observation_root,
        project_root=project,
        create=False,
    )
    if not root.is_dir():
        raise ObservationSafetyError(
            "observation root does not exist"
        )

    inventory = build_inventory(project)
    complete, incomplete, orphan_completed = _session_records(root)
    if orphan_completed:
        raise ObservationIntegrityError(
            "orphan completed session evidence exists: {}".format(
                ", ".join(orphan_completed)
            )
        )

    candidate_by_path = {
        str(item["path"]): item
        for item in inventory["items"]
    }
    observed: Dict[str, dict] = {}

    def apply_event(session_id: str, event: Mapping[str, object], complete_session: bool):
        component = str(event.get("component_path", ""))
        if component not in candidate_by_path:
            raise ObservationIntegrityError(
                "session references component absent from current Phase 7.1 inventory: {}".format(
                    component
                )
            )
        record = observed.setdefault(
            component,
            {
                "session_ids": set(),
                "complete_session_ids": set(),
                "activities": set(),
                "symbols": set(),
                "caller_paths": set(),
                "first_observed_at": None,
                "last_observed_at": None,
                "unique_event_count": 0,
            },
        )
        record["session_ids"].add(session_id)
        if complete_session:
            record["complete_session_ids"].add(session_id)
        record["activities"].add(str(event.get("activity", "")))
        record["symbols"].add(str(event.get("symbol", "")))
        record["caller_paths"].add(str(event.get("caller_path", "")))
        timestamp = str(event.get("observed_at", ""))
        if (
            record["first_observed_at"] is None
            or timestamp < record["first_observed_at"]
        ):
            record["first_observed_at"] = timestamp
        if (
            record["last_observed_at"] is None
            or timestamp > record["last_observed_at"]
        ):
            record["last_observed_at"] = timestamp
        record["unique_event_count"] += 1

    for session in complete:
        for event in session["events"]:
            apply_event(
                session["session_id"],
                event,
                True,
            )
    for session in incomplete:
        for event in session["events"]:
            apply_event(
                session["session_id"],
                event,
                False,
            )

    component_rows = []
    for item in inventory["items"]:
        path = str(item["path"])
        evidence = observed.get(path)
        if evidence is None:
            runtime_state = "not_observed_yet"
            session_count = 0
            complete_session_count = 0
            activities = ()
            symbols = ()
            callers = ()
            first = None
            last = None
            event_count = 0
        else:
            runtime_state = "observed_runtime_use"
            session_count = len(evidence["session_ids"])
            complete_session_count = len(
                evidence["complete_session_ids"]
            )
            activities = tuple(sorted(evidence["activities"]))
            symbols = tuple(sorted(evidence["symbols"]))
            callers = tuple(sorted(evidence["caller_paths"]))
            first = evidence["first_observed_at"]
            last = evidence["last_observed_at"]
            event_count = int(evidence["unique_event_count"])

        component_rows.append(
            {
                "path": path,
                "module": str(item["module"]),
                "component_kind": str(item["component_kind"]),
                "static_status": str(item["status"]),
                "replacement": str(item["replacement"]),
                "runtime_observation_state": runtime_state,
                "observed_session_count": session_count,
                "observed_complete_session_count": complete_session_count,
                "unique_event_count": event_count,
                "activities": activities,
                "symbols": symbols,
                "caller_paths": callers,
                "first_observed_at": first,
                "last_observed_at": last,
                "retirement_decision": "not_made",
            }
        )

    complete_starts = [
        str(row["completed"]["started_at"])
        for row in complete
    ]
    complete_ends = [
        str(row["completed"]["ended_at"])
        for row in complete
    ]
    total_duration = sum(
        float(row["completed"]["duration_seconds"])
        for row in complete
    )

    payload = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "analysis_kind": "runtime_consumer_observation",
        "inventory_sha256": str(inventory["inventory_sha256"]),
        "observation_root_identity": ".",
        "summary": {
            "candidate_count": len(component_rows),
            "complete_session_count": len(complete),
            "incomplete_session_count": len(incomplete),
            "observed_component_count": sum(
                1
                for row in component_rows
                if row["runtime_observation_state"]
                == "observed_runtime_use"
            ),
            "not_observed_yet_count": sum(
                1
                for row in component_rows
                if row["runtime_observation_state"]
                == "not_observed_yet"
            ),
            "total_complete_session_duration_seconds": round(
                total_duration, 6
            ),
            "first_complete_session_started_at": (
                min(complete_starts) if complete_starts else None
            ),
            "last_complete_session_ended_at": (
                max(complete_ends) if complete_ends else None
            ),
            "retirement_candidate_count": 0,
        },
        "components": component_rows,
        "limitations": (
            "Observation proves use when an event exists; absence of events does not prove non-use.",
            "Only Python execution launched through the Phase 7.4 runner is observed.",
            "Subprocesses or external processes are not automatically traced.",
            "Incomplete sessions are reported and never treated as a completed observation interval.",
            "Phase 7.4 never declares a component safe to retire.",
            "The academic-cycle observation requirement remains for Phase 7.8.",
        ),
        "privacy": {
            "arguments_captured": False,
            "locals_captured": False,
            "return_values_captured": False,
            "academic_content_captured": False,
            "environment_captured": False,
            "absolute_project_path_captured": False,
        },
        "retirement_decisions_performed": False,
    }
    canonical = dict(payload)
    payload["report_sha256"] = _sha256_bytes(
        _canonical_bytes(canonical)
    )
    return payload


def render_observation_markdown(report: Mapping[str, object]) -> str:
    summary = report["summary"]
    lines = [
        "# Phase 7.4 Legacy Usage Observation / Consumer Watch",
        "",
        "Report SHA-256: `{}`".format(report["report_sha256"]),
        "",
        "## Summary",
        "",
        "- Candidate components: {}".format(summary["candidate_count"]),
        "- Complete observed sessions: {}".format(
            summary["complete_session_count"]
        ),
        "- Incomplete sessions: {}".format(
            summary["incomplete_session_count"]
        ),
        "- Components observed in runtime: {}".format(
            summary["observed_component_count"]
        ),
        "- Components not observed yet: {}".format(
            summary["not_observed_yet_count"]
        ),
        "- Retirement candidates declared: **0**",
        "",
        "> Runtime absence is not retirement proof. Phase 7.4 records evidence; it does not authorize deletion.",
        "",
        "## Components",
        "",
        "| Component | Static status | Runtime observation | Sessions | Replacement |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for item in report["components"]:
        lines.append(
            "| `{}` | `{}` | `{}` | {} | {} |".format(
                item["path"],
                item["static_status"],
                item["runtime_observation_state"],
                item["observed_session_count"],
                str(item["replacement"]).replace("|", "\\|"),
            )
        )
    lines.extend(["", "## Limitations", ""])
    for item in report["limitations"]:
        lines.append("- {}".format(item))
    return "\n".join(lines) + "\n"
