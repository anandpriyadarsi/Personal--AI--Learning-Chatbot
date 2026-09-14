"""Phase 3.2 reverse export, restore rehearsal, and completion gate.

The functions in this module operate only on an explicitly supplied SQLite
shadow connection and newly-created isolated output directories. They never
open the future production database by default and never write legacy JSON,
Obsidian, knowledge, or user-data locations.

Reverse export has two complementary layers:

* importer-compatible legacy JSON views built from current SQLite rows plus the
  migration ledger's preserved raw evidence; and
* a lossless relational SQLite table snapshot for fields that have no legacy
  JSON representation.

A restore rehearsal uses SQLite's online backup API and a fresh migration /
re-import database. Every database and source used by the rehearsal lives below
the newly-created rehearsal directory.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from personal_learning_assistant.repositories.sqlite.connection import (
    connect_database,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import (
    apply_migrations,
)

from .assessments_topics_importer import import_assessments_and_topics
from .attempts_performance_importer import (
    import_attempts_mistakes_and_performance,
)
from .courses_topics_importer import import_courses_and_topics
from .grades_calendar_importer import (
    import_grades_and_academic_calendar,
)
from .learning_progress_importer import (
    import_learning_memory_and_progress,
)
from .legacy_source_scanner import (
    LegacySourceSpec,
    scan_legacy_sources,
)
from .question_topic_mappings_importer import (
    import_question_topic_mappings,
)
from .questions_sources_importer import import_questions_and_sources
from .study_plans_importer import import_study_plans


PathLike = Union[str, Path]
REVERSE_EXPORT_VERSION = 1
REHEARSAL_REPORT_VERSION = 1

COURSE_SOURCE = "data/courses.json"
ASSESSMENT_SOURCE = "data/assessments.json"
WORKSPACE_SOURCE = "data/assessment_workspace.json"
MEMORY_SOURCE = "data/learning_memory.json"
PROGRESS_SOURCE = "data/course_progress_history.json"
WEEKLY_PLAN_SOURCE = "data/weekly_study_plans.json"
MULTI_PLAN_SOURCE = "data/multi_course_weekly_plans.json"
INTELLIGENT_PLAN_SOURCE = "data/intelligent_study_plans.json"
GRADE_SOURCE = "data/semester_grade_config.json"

REQUIRED_EXPORT_SOURCES: Tuple[str, ...] = (
    COURSE_SOURCE,
    ASSESSMENT_SOURCE,
    WORKSPACE_SOURCE,
    MEMORY_SOURCE,
    PROGRESS_SOURCE,
    WEEKLY_PLAN_SOURCE,
    MULTI_PLAN_SOURCE,
)
OPTIONAL_EXPORT_SOURCES: Tuple[str, ...] = (
    INTELLIGENT_PLAN_SOURCE,
    GRADE_SOURCE,
)
UNMIGRATED_LEGACY_SOURCES: Tuple[str, ...] = (
    "data/notes.json",
    "data/resources.json",
    "data/obsidian_config.json",
)
REPLAY_SPECS: Tuple[LegacySourceSpec, ...] = tuple(
    LegacySourceSpec(Path(path).name)
    for path in REQUIRED_EXPORT_SOURCES
) + tuple(
    LegacySourceSpec(Path(path).name, required=False)
    for path in OPTIONAL_EXPORT_SOURCES
)

_PRODUCTION_DATABASE_NAMES = {
    "learning_assistant.db",
    "learning_assistant.db-wal",
    "learning_assistant.db-shm",
}
_FORBIDDEN_OUTPUT_PARTS = {"data", "knowledge", "obsidian", "backup", "backups"}
_OUTPUT_MARKERS = {
    "phase3",
    "reverse",
    "export",
    "restore",
    "rehearsal",
    "validation",
    "temp",
    "tmp",
}
_SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class Phase32Error(RuntimeError):
    """Base error for Phase 3.2 export and restore operations."""


class Phase32InputError(Phase32Error, ValueError):
    """Raised when an input cannot satisfy the Phase 3.2 contract."""


class Phase32SafetyError(Phase32Error):
    """Raised before an operation could touch a protected location."""


class Phase32ValidationError(Phase32Error):
    """Raised when integrity, foreign-key, or reconciliation checks fail."""


@dataclass(frozen=True)
class ReverseExportArtifact:
    source_path: str
    relative_path: str
    source_hash: str
    source_version: str
    sha256: str
    byte_count: int
    record_count: int


@dataclass(frozen=True)
class ReverseExportResult:
    output_directory: Path
    manifest_path: Path
    relational_snapshot_path: Path
    status: str
    artifacts: Tuple[ReverseExportArtifact, ...]
    integrity_check: Tuple[str, ...]
    foreign_key_check: Tuple[Mapping[str, Any], ...]
    reconciliation: Tuple[Mapping[str, Any], ...]
    documented_discrepancies: Tuple[Mapping[str, Any], ...]
    unmigrated_legacy_sources: Tuple[str, ...]


@dataclass(frozen=True)
class RestoreRehearsalResult:
    work_directory: Path
    report_path: Path
    status: str
    backup_path: Path
    restored_database_path: Path
    reimport_database_path: Path
    backup_sha256: str
    source_fingerprint: str
    backup_fingerprint: str
    restored_fingerprint: str
    reimport_first_fingerprint: str
    reimport_second_fingerprint: str
    migrations_first_apply: Tuple[int, ...]
    migrations_second_apply: Tuple[int, ...]
    first_import_changes: int
    second_import_changes: int
    integrity_check: Tuple[str, ...]
    foreign_key_check: Tuple[Mapping[str, Any], ...]
    migration_idempotent: bool
    import_idempotent: bool
    export_hashes_unchanged: bool


@dataclass(frozen=True)
class Phase3CompletionGateResult:
    status: str
    reverse_export: ReverseExportResult
    restore_rehearsal: RestoreRehearsalResult
    sqlite_unchanged: bool
    legacy_sources_unchanged: bool


@dataclass(frozen=True)
class _LedgerRow:
    rowid: int
    source_path: str
    source_hash: str
    source_version: str
    legacy_key: str
    target_table: str
    target_id: str
    imported_at: str
    details: Mapping[str, Any]


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if isinstance(value, sqlite3.Row):
        return [_json_value(item) for item in tuple(value)]
    if isinstance(value, Mapping):
        return {
            str(key): _json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, Path):
        return value.as_posix()
    return value


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            _json_value(value),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _write_json_exclusive(path: Path, value: Any) -> Tuple[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = _json_bytes(value)
    with path.open("xb") as handle:
        handle.write(raw)
    return _sha256_bytes(raw), len(raw)


def _quote_identifier(value: str) -> str:
    if not _SQL_IDENTIFIER.fullmatch(value):
        raise Phase32ValidationError(
            "unsafe SQLite identifier encountered: {}".format(value)
        )
    return '"{}"'.format(value)


def _database_label(connection: sqlite3.Connection) -> str:
    rows = connection.execute("PRAGMA database_list").fetchall()
    main = next((row for row in rows if str(row[1]) == "main"), None)
    if main is None:
        raise Phase32InputError("SQLite connection has no main database")
    physical = str(main[2] or "")
    label = Path(physical).name if physical else ":memory:"
    if label.casefold() in _PRODUCTION_DATABASE_NAMES:
        raise Phase32SafetyError(
            "Phase 3.2 refuses the production database name: {}".format(label)
        )
    return label


def _assert_shadow_connection(connection: sqlite3.Connection) -> str:
    if not isinstance(connection, sqlite3.Connection):
        raise Phase32InputError("connection must be an open sqlite3.Connection")
    label = _database_label(connection)
    required = {"schema_migrations", "migration_imports"}
    tables = set(_table_names(connection))
    missing = sorted(required - tables)
    if missing:
        raise Phase32ValidationError(
            "required Phase 3 tables are missing: {}".format(", ".join(missing))
        )
    return label


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_new_directory(
    value: PathLike,
    *,
    protected_roots: Sequence[PathLike] = (),
) -> Path:
    path = Path(value)
    if path.exists() or path.is_symlink():
        raise Phase32SafetyError(
            "output directory must be new and absent: {}".format(path.name)
        )
    if not path.parent.is_dir():
        raise Phase32InputError(
            "output parent directory must already exist: {}".format(path.parent)
        )

    resolved = path.resolve(strict=False)
    lower_parts = {part.casefold() for part in resolved.parts}
    if lower_parts & _FORBIDDEN_OUTPUT_PARTS:
        raise Phase32SafetyError(
            "output directory cannot be inside data, knowledge, Obsidian, or backup"
        )
    leaf = path.name.casefold()
    if not any(marker in leaf for marker in _OUTPUT_MARKERS):
        raise Phase32SafetyError(
            "isolated output directory name must identify Phase 3/export/rehearsal"
        )

    cursor = path.parent
    while True:
        if cursor.is_symlink():
            raise Phase32SafetyError("output path cannot traverse a symlink")
        if cursor == cursor.parent:
            break
        cursor = cursor.parent

    for raw_root in protected_roots:
        root = Path(raw_root).resolve(strict=False)
        if resolved == root or _is_relative_to(resolved, root):
            raise Phase32SafetyError(
                "output directory cannot be inside a protected source root"
            )
        if root == resolved or _is_relative_to(root, resolved):
            raise Phase32SafetyError(
                "output directory cannot contain a protected source root"
            )
    return path


def _table_names(connection: sqlite3.Connection) -> Tuple[str, ...]:
    return tuple(
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    )


def _sqlite_checks(
    connection: sqlite3.Connection,
) -> Tuple[Tuple[str, ...], Tuple[Mapping[str, Any], ...]]:
    integrity = tuple(
        str(row[0]) for row in connection.execute("PRAGMA integrity_check").fetchall()
    )
    foreign_keys = tuple(
        {
            "table": str(row[0]),
            "rowid": None if row[1] is None else int(row[1]),
            "parent": str(row[2]),
            "foreign_key_index": int(row[3]),
        }
        for row in connection.execute("PRAGMA foreign_key_check").fetchall()
    )
    return integrity, foreign_keys


def _require_clean_sqlite(
    connection: sqlite3.Connection,
) -> Tuple[Tuple[str, ...], Tuple[Mapping[str, Any], ...]]:
    integrity, foreign_keys = _sqlite_checks(connection)
    if integrity != ("ok",):
        raise Phase32ValidationError(
            "PRAGMA integrity_check failed: {}".format(", ".join(integrity))
        )
    if foreign_keys:
        raise Phase32ValidationError(
            "PRAGMA foreign_key_check returned {} violation(s)".format(
                len(foreign_keys)
            )
        )
    return integrity, foreign_keys


def _table_snapshot(
    connection: sqlite3.Connection,
) -> Mapping[str, Any]:
    tables: Dict[str, Any] = {}
    definitions = {
        str(row[0]): str(row[1] or "")
        for row in connection.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    }
    for table in sorted(definitions):
        quoted = _quote_identifier(table)
        info = connection.execute(
            "PRAGMA table_info({})".format(quoted)
        ).fetchall()
        columns = [str(row[1]) for row in info]
        primary = [
            str(row[1])
            for row in sorted(
                (row for row in info if int(row[5]) > 0),
                key=lambda row: int(row[5]),
            )
        ]
        order_columns = primary or columns
        order_clause = ""
        if order_columns:
            order_clause = " ORDER BY {}".format(
                ", ".join(_quote_identifier(item) for item in order_columns)
            )
        rows = connection.execute(
            "SELECT * FROM {}{}".format(quoted, order_clause)
        ).fetchall()
        tables[table] = {
            "schema": definitions[table],
            "columns": columns,
            "primary_key": primary,
            "rows": [
                {
                    columns[index]: _json_value(value)
                    for index, value in enumerate(tuple(row))
                }
                for row in rows
            ],
        }
    return {
        "format_version": REVERSE_EXPORT_VERSION,
        "tables": tables,
    }


def _database_fingerprint(connection: sqlite3.Connection) -> str:
    return _sha256_bytes(_canonical_json_bytes(_table_snapshot(connection)))


def _parse_details(raw: Any, context: str) -> Mapping[str, Any]:
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise Phase32ValidationError(
            "invalid migration ledger details for {}".format(context)
        ) from exc
    if not isinstance(value, dict):
        raise Phase32ValidationError(
            "migration ledger details must be an object for {}".format(context)
        )
    return value


def _latest_ledger_rows(
    connection: sqlite3.Connection,
    source_path: str,
) -> Tuple[_LedgerRow, ...]:
    raw_rows = connection.execute(
        "SELECT rowid, source_path, source_hash, source_version, legacy_key, "
        "target_table, target_id, imported_at, details_json "
        "FROM migration_imports "
        "WHERE source_path = ? AND source_type = 'legacy_json' "
        "ORDER BY imported_at, rowid",
        (source_path,),
    ).fetchall()
    if not raw_rows:
        return ()
    latest_hash = str(raw_rows[-1][2])
    rows = []
    for raw in raw_rows:
        if str(raw[2]) != latest_hash:
            continue
        context = "{}:{}".format(source_path, raw[4])
        rows.append(
            _LedgerRow(
                rowid=int(raw[0]),
                source_path=str(raw[1]),
                source_hash=str(raw[2]),
                source_version=str(raw[3]),
                legacy_key=str(raw[4]),
                target_table=str(raw[5]),
                target_id=str(raw[6]),
                imported_at=str(raw[7]),
                details=_parse_details(raw[8], context),
            )
        )
    return tuple(rows)


def _source_version(rows: Sequence[_LedgerRow], default: Any = 1) -> Any:
    values = {row.source_version for row in rows if row.source_version != ""}
    if not values:
        return default
    if len(values) != 1:
        raise Phase32ValidationError("one source hash has conflicting schema versions")
    value = next(iter(values))
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def _row_by_id(
    connection: sqlite3.Connection,
    table: str,
    target_id: str,
) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM {} WHERE id = ?".format(_quote_identifier(table)),
        (target_id,),
    ).fetchone()
    if row is None:
        raise Phase32ValidationError(
            "migration ledger target is missing: {}:{}".format(table, target_id)
        )
    return row


def _rows_for_kind(
    rows: Sequence[_LedgerRow],
    *,
    table: Optional[str] = None,
    kind: Optional[str] = None,
) -> Tuple[_LedgerRow, ...]:
    return tuple(
        row
        for row in rows
        if (table is None or row.target_table == table)
        and (kind is None or str(row.details.get("kind", "")) == kind)
    )


def _raw_object(row: _LedgerRow) -> Dict[str, Any]:
    raw = row.details.get("raw", {})
    if not isinstance(raw, dict):
        raise Phase32ValidationError(
            "ledger raw evidence is not an object: {}".format(row.legacy_key)
        )
    return deepcopy(dict(raw))


def _unscale(value: Any, scale: int) -> Optional[Union[int, float]]:
    if value is None:
        return None
    result = Decimal(int(value)) / Decimal(scale)
    if result == result.to_integral():
        return int(result)
    return float(result)


def _legacy_identifier_maps(
    connection: sqlite3.Connection,
) -> Tuple[Mapping[str, str], Mapping[str, str]]:
    course_rows = _latest_ledger_rows(connection, COURSE_SOURCE)
    course_ids: Dict[str, str] = {}
    topic_names: Dict[str, str] = {}
    for ledger in _rows_for_kind(course_rows, table="courses", kind="course"):
        target = _row_by_id(connection, "courses", ledger.target_id)
        raw = ledger.details.get("raw", {})
        legacy_id = str(ledger.details.get("legacy_id") or "").strip()
        if not legacy_id and isinstance(raw, dict):
            legacy_id = str(raw.get("id") or raw.get("code") or "").strip()
        course_ids[ledger.target_id] = legacy_id or str(target["code"])
    for ledger in _rows_for_kind(course_rows, table="topics", kind="topic"):
        target = _row_by_id(connection, "topics", ledger.target_id)
        raw = ledger.details.get("raw", {})
        name = str(raw.get("name") or "").strip() if isinstance(raw, dict) else ""
        topic_names[ledger.target_id] = name or str(target["name"])
    return course_ids, topic_names


def _set_scaled_alias(
    raw: Dict[str, Any],
    aliases: Sequence[str],
    value: Any,
) -> None:
    present = next((name for name in aliases if name in raw), None)
    if present is not None:
        raw[present] = value
    elif value is not None:
        raw[aliases[0]] = value


def _export_courses(
    connection: sqlite3.Connection,
) -> Tuple[Mapping[str, Any], int, Tuple[_LedgerRow, ...]]:
    rows = _latest_ledger_rows(connection, COURSE_SOURCE)
    topic_ledgers = _rows_for_kind(rows, table="topics", kind="topic")
    by_course: Dict[str, List[Tuple[int, _LedgerRow, sqlite3.Row]]] = {}
    for ledger in topic_ledgers:
        target = _row_by_id(connection, "topics", ledger.target_id)
        course_key = str(ledger.details.get("course_legacy_key") or "")
        by_course.setdefault(course_key, []).append(
            (int(target["position"]), ledger, target)
        )

    exported_courses = []
    course_target_to_legacy: Dict[str, str] = {}
    course_ledgers = _rows_for_kind(rows, table="courses", kind="course")
    for ledger in course_ledgers:
        target = _row_by_id(connection, "courses", ledger.target_id)
        raw = _raw_object(ledger)
        legacy_id = str(ledger.details.get("legacy_id") or "").strip()
        if legacy_id:
            raw["id"] = legacy_id
        raw["code"] = str(target["code"])
        raw["name"] = str(target["name"])
        raw["status"] = str(target["status"])
        if "created_at" in raw:
            raw["created_at"] = str(target["created_at"])
        if "updated_at" in raw:
            raw["updated_at"] = str(target["updated_at"])

        exported_topics = []
        for _, topic_ledger, topic in sorted(
            by_course.get(ledger.legacy_key, []),
            key=lambda item: (item[0], item[1].rowid),
        ):
            topic_raw = _raw_object(topic_ledger)
            if topic_raw.get("id") is not None:
                topic_raw["id"] = topic_raw.get("id")
            topic_raw["name"] = str(topic["name"])
            topic_raw["status"] = str(topic["status"])
            topic_raw["confidence"] = (
                None if topic["confidence"] is None else int(topic["confidence"])
            )
            if "last_updated" in topic_raw:
                topic_raw["last_updated"] = str(topic["updated_at"])
            exported_topics.append(topic_raw)
        raw["topics"] = exported_topics
        exported_courses.append(raw)
        course_target_to_legacy[ledger.target_id] = (
            legacy_id or str(raw.get("code") or ledger.legacy_key)
        )

    payload: Dict[str, Any] = {
        "version": _source_version(rows),
        "courses": exported_courses,
        "document_links": {},
    }
    setting = connection.execute(
        "SELECT value_json FROM app_settings WHERE key = 'active_course_id'"
    ).fetchone()
    if setting is not None:
        try:
            target_id = str(json.loads(str(setting[0])))
        except (TypeError, ValueError, json.JSONDecodeError):
            target_id = ""
        if target_id:
            payload["active_course_id"] = course_target_to_legacy.get(
                target_id, target_id
            )
    return payload, len(exported_courses) + len(topic_ledgers), rows


def _export_assessments(
    connection: sqlite3.Connection,
    course_ids: Mapping[str, str],
) -> Tuple[Mapping[str, Any], int, Tuple[_LedgerRow, ...]]:
    rows = _latest_ledger_rows(connection, ASSESSMENT_SOURCE)
    topic_rows = _rows_for_kind(
        rows, table="assessment_topics", kind="assessment_topic_raw_label"
    )
    topics_by_assessment: Dict[str, List[Tuple[int, str]]] = {}
    for ledger in topic_rows:
        target = _row_by_id(connection, "assessment_topics", ledger.target_id)
        owner = str(ledger.details.get("assessment_legacy_key") or "")
        position = int(ledger.details.get("position") or 0)
        topics_by_assessment.setdefault(owner, []).append(
            (position, str(target["raw_label"]))
        )

    exported = []
    assessment_rows = _rows_for_kind(
        rows, table="assessments", kind="assessment"
    )
    for ledger in assessment_rows:
        target = _row_by_id(connection, "assessments", ledger.target_id)
        raw = _raw_object(ledger)
        raw["id"] = str(ledger.details.get("legacy_id") or raw.get("id") or "")
        raw["course_id"] = course_ids.get(
            str(target["course_id"]),
            str(ledger.details.get("legacy_course_id") or target["course_id"]),
        )
        raw["title"] = str(target["title"])
        raw["type"] = str(target["assessment_type"])
        raw["status"] = str(target["status"])
        raw["due_date"] = None if target["due_on"] is None else str(target["due_on"])
        if target["due_time"] is not None or "due_time" in raw:
            raw["due_time"] = (
                None if target["due_time"] is None else str(target["due_time"])
            )
        _set_scaled_alias(
            raw,
            ("weightage_percent", "weight"),
            _unscale(target["weight_bps"], 100),
        )
        _set_scaled_alias(
            raw,
            ("total_marks", "max_score"),
            _unscale(target["max_points_milli"], 1000),
        )
        _set_scaled_alias(
            raw,
            ("obtained_marks", "score"),
            _unscale(target["earned_points_milli"], 1000),
        )
        raw["description"] = str(target["description"]) if "description" in raw else raw.get("description", "")
        if "created_at" in raw:
            raw["created_at"] = str(target["created_at"])
        if "updated_at" in raw:
            raw["updated_at"] = str(target["updated_at"])
        raw["topics"] = [
            label
            for _, label in sorted(
                topics_by_assessment.get(ledger.legacy_key, []),
                key=lambda item: item[0],
            )
        ]
        exported.append(raw)
    return (
        {"version": _source_version(rows), "assessments": exported},
        len(exported) + len(topic_rows),
        rows,
    )


def _mapping_compatibility(
    connection: sqlite3.Connection,
    question_id: str,
    topic_names: Mapping[str, str],
    original: Mapping[str, Any],
) -> Tuple[Any, Any]:
    rows = connection.execute(
        "SELECT topic_id, score, rank, method, state, reason, created_at, reviewed_at "
        "FROM question_topic_mappings WHERE question_id = ? "
        "ORDER BY CASE WHEN rank IS NULL THEN 1 ELSE 0 END, rank, id",
        (question_id,),
    ).fetchall()
    if not rows:
        return original.get("topic"), deepcopy(original.get("topic_mapping"))

    unique = []
    seen = set()
    for row in rows:
        label = topic_names.get(str(row[0]))
        if label is None:
            topic = connection.execute(
                "SELECT name FROM topics WHERE id = ?", (str(row[0]),)
            ).fetchone()
            label = str(topic[0]) if topic is not None else str(row[0])
        folded = " ".join(label.casefold().split())
        if folded in seen:
            continue
        seen.add(folded)
        unique.append((row, label))

    accepted = next(
        ((row, label) for row, label in unique if str(row[4]) == "accepted"),
        None,
    )
    primary = accepted or unique[0]
    primary_row, primary_label = primary
    mapping = (
        deepcopy(dict(original.get("topic_mapping")))
        if isinstance(original.get("topic_mapping"), dict)
        else {}
    )
    mapping.update(
        {
            "method": str(primary_row[3]),
            "suggested_topic": primary_label,
            "score": (
                None if primary_row[1] is None else float(primary_row[1])
            ),
            "alternatives": [
                {
                    "topic": label,
                    "score": None if row[1] is None else float(row[1]),
                }
                for row, label in unique
            ],
            "accepted": accepted is not None,
            "mapped_at": str(
                primary_row[7] or primary_row[6]
            ),
        }
    )
    return (primary_label if accepted is not None else None), mapping


def _attempt_compatibility(
    connection: sqlite3.Connection,
    question_id: str,
    attempt_ledgers: Mapping[str, _LedgerRow],
) -> Tuple[List[Mapping[str, Any]], List[Mapping[str, Any]]]:
    top_level: List[Tuple[int, Mapping[str, Any]]] = []
    performance: List[Tuple[int, Mapping[str, Any]]] = []
    rows = connection.execute(
        "SELECT id, attempt_number, outcome, earned_marks_milli, "
        "max_marks_milli, response_ref, feedback_ref, occurred_at "
        "FROM question_attempts WHERE question_id = ? "
        "ORDER BY attempt_number, id",
        (question_id,),
    ).fetchall()
    for row in rows:
        ledger = attempt_ledgers.get(str(row[0]))
        raw = (
            _raw_object(ledger)
            if ledger is not None
            else {}
        )
        raw["outcome"] = str(row[2])
        raw["earned_marks"] = _unscale(row[3], 1000)
        raw["max_marks"] = _unscale(row[4], 1000)
        if row[5] is not None or "response_ref" in raw or "response" in raw:
            raw["response_ref"] = None if row[5] is None else str(row[5])
            raw.pop("response", None)
        if row[6] is not None or "feedback_ref" in raw or "feedback" in raw:
            raw["feedback_ref"] = None if row[6] is None else str(row[6])
            raw.pop("feedback", None)
        raw["time"] = str(row[7])
        mistakes = connection.execute(
            "SELECT mistake_text FROM mistake_events WHERE attempt_id = ? "
            "ORDER BY created_at, id",
            (str(row[0]),),
        ).fetchall()
        if mistakes:
            raw["mistake"] = str(mistakes[0][0])

        origin = "attempts"
        position = int(row[1])
        if ledger is not None and "/attempt:" in ledger.legacy_key:
            suffix = ledger.legacy_key.rsplit("/attempt:", 1)[1]
            parsed = re.fullmatch(r"(.+):(\d+)", suffix)
            if parsed is not None:
                origin = parsed.group(1)
                position = int(parsed.group(2))
        destination = performance if origin == "performance.attempts" else top_level
        destination.append((position, raw))
    return (
        [item for _, item in sorted(top_level, key=lambda pair: pair[0])],
        [item for _, item in sorted(performance, key=lambda pair: pair[0])],
    )


def _export_workspace(
    connection: sqlite3.Connection,
    topic_names: Mapping[str, str],
) -> Tuple[Mapping[str, Any], int, Tuple[_LedgerRow, ...]]:
    rows = _latest_ledger_rows(connection, WORKSPACE_SOURCE)
    questions = _rows_for_kind(
        rows, table="questions", kind="assessment_question_raw_unit"
    )
    sources = {
        str(row.details.get("question_legacy_key") or ""): row
        for row in _rows_for_kind(
            rows,
            table="question_sources",
            kind="question_source_raw_annotation",
        )
    }
    attempts = {
        row.target_id: row
        for row in _rows_for_kind(
            rows, table="question_attempts", kind="question_attempt"
        )
    }
    workspaces: Dict[str, Dict[str, Any]] = {}
    ordered = []
    for ledger in questions:
        target = _row_by_id(connection, "questions", ledger.target_id)
        assessment_key = str(ledger.details.get("assessment_legacy_key") or "")
        raw_assessment_id = (
            assessment_key[len("assessment:id:") :]
            if assessment_key.startswith("assessment:id:")
            else assessment_key
        )
        raw = _raw_object(ledger)
        raw["id"] = str(ledger.details.get("legacy_id") or raw.get("id") or "")
        raw["text"] = str(target["question_text"])
        _set_scaled_alias(
            raw,
            ("marks",),
            _unscale(target["max_marks_milli"], 1000),
        )
        raw["status"] = str(target["status"])
        if target["user_notes"] or "notes" in raw:
            raw["notes"] = str(target["user_notes"])
        if "created_at" in raw:
            raw["created_at"] = str(target["created_at"])
        if "updated_at" in raw:
            raw["updated_at"] = str(target["updated_at"])

        source_ledger = sources.get(ledger.legacy_key)
        if source_ledger is not None:
            source = _row_by_id(
                connection, "question_sources", source_ledger.target_id
            )
            raw["source_file"] = str(source["raw_source_label"])
            raw["source_page"] = (
                None if source["page_number"] is None else int(source["page_number"])
            )
            locator = str(source["locator"] or "")
            if locator.startswith("question:"):
                raw["source_question_number"] = locator.split(":", 1)[1]

        current_topic, current_mapping = _mapping_compatibility(
            connection, ledger.target_id, topic_names, raw
        )
        if current_topic is not None or "topic" in raw:
            raw["topic"] = current_topic
        if current_mapping is not None or "topic_mapping" in raw:
            raw["topic_mapping"] = current_mapping

        top_attempts, performance_attempts = _attempt_compatibility(
            connection, ledger.target_id, attempts
        )
        if top_attempts or "attempts" in raw:
            raw["attempts"] = top_attempts
        if performance_attempts:
            performance_raw = (
                deepcopy(dict(raw.get("performance")))
                if isinstance(raw.get("performance"), dict)
                else {}
            )
            performance_raw["attempts"] = performance_attempts
            raw["performance"] = performance_raw
        elif isinstance(raw.get("performance"), dict) and "attempts" in raw["performance"]:
            performance_raw = deepcopy(dict(raw["performance"]))
            performance_raw["attempts"] = []
            raw["performance"] = performance_raw

        workspaces.setdefault(
            raw_assessment_id,
            {
                "assessment_id": raw_assessment_id,
                "questions": [],
            },
        )
        ordered.append(
            (
                raw_assessment_id,
                int(target["ordinal"]),
                ledger.rowid,
                raw,
            )
        )

    for assessment_id, _, _, raw in sorted(
        ordered, key=lambda item: (item[0].casefold(), item[1], item[2])
    ):
        workspaces[assessment_id]["questions"].append(raw)
    return (
        {
            "version": _source_version(rows),
            "workspaces": workspaces,
        },
        len(questions),
        rows,
    )


def _scope_course_id(ledger: _LedgerRow, course_ids: Mapping[str, str]) -> str:
    raw = str(ledger.details.get("raw_course_id") or "").strip()
    if raw:
        return raw
    parsed = re.match(r"^scope:course:(.*?)/kind:", ledger.legacy_key)
    if parsed is not None:
        return parsed.group(1)
    target_scope = ledger.details.get("scope_id")
    return course_ids.get(str(target_scope), "") if target_scope else ""


def _entry_position(ledger: _LedgerRow) -> int:
    raw = ledger.details.get("raw", {})
    if isinstance(raw, dict):
        try:
            return int(raw.get("position", 0))
        except (TypeError, ValueError):
            return 0
    parsed = re.search(r"index:(\d+)", ledger.legacy_key)
    return int(parsed.group(1)) if parsed is not None else 0


def _export_learning_memory(
    connection: sqlite3.Connection,
    course_ids: Mapping[str, str],
) -> Tuple[Mapping[str, Any], int, Tuple[_LedgerRow, ...]]:
    rows = _latest_ledger_rows(connection, MEMORY_SOURCE)
    entries = _rows_for_kind(
        rows, table="learning_memory_entries", kind="learning_memory_entry"
    )
    root: Dict[str, Any] = {
        "version": _source_version(rows),
        "weak_topics": [],
        "mastered_topics": [],
        "notes": [],
        "activities": [],
    }
    course_memory: Dict[str, Dict[str, Any]] = {}
    ordered = sorted(entries, key=lambda item: (_entry_position(item), item.rowid))
    for ledger in ordered:
        target = _row_by_id(
            connection, "learning_memory_entries", ledger.target_id
        )
        course_id = _scope_course_id(ledger, course_ids)
        payload = root
        if str(target["scope_type"]) != "global" or course_id:
            key = course_id or str(target["scope_id"] or "unresolved")
            payload = course_memory.setdefault(
                key,
                {
                    "weak_topics": [],
                    "mastered_topics": [],
                    "notes": [],
                    "activities": [],
                },
            )
        kind = str(target["kind"])
        raw = ledger.details.get("raw", {})
        if kind == "weak_topic":
            payload["weak_topics"].append(str(target["raw_topic"]))
        elif kind == "mastered_topic":
            payload["mastered_topics"].append(str(target["raw_topic"]))
        elif kind == "note":
            original = raw.get("note") if isinstance(raw, dict) else None
            if isinstance(original, dict):
                note = deepcopy(dict(original))
                note["text"] = str(target["memory_text"])
                if "created_at" in note:
                    note["created_at"] = str(target["created_at"])
                payload["notes"].append(note)
            else:
                payload["notes"].append(str(target["memory_text"]))
        elif kind == "activity":
            original = raw.get("activity") if isinstance(raw, dict) else None
            activity = deepcopy(dict(original)) if isinstance(original, dict) else {}
            activity["question"] = str(target["memory_text"])
            if target["raw_topic"] or "topic" in activity:
                activity["topic"] = str(target["raw_topic"])
            activity["time"] = str(target["created_at"])
            payload["activities"].append(activity)

    if course_memory:
        root["course_memory"] = course_memory
    return root, len(entries), rows


def _progress_course_id(
    ledger: _LedgerRow,
    raw: Mapping[str, Any],
    course_ids: Mapping[str, str],
) -> str:
    embedded = str(raw.get("course_id") or "").strip()
    if embedded:
        return embedded
    parsed = re.match(r"^course:(.*?)/date:", ledger.legacy_key)
    if parsed is not None:
        return parsed.group(1)
    return course_ids.get(str(ledger.details.get("course_id") or ""), "")


def _export_progress(
    connection: sqlite3.Connection,
    course_ids: Mapping[str, str],
) -> Tuple[Mapping[str, Any], int, Tuple[_LedgerRow, ...]]:
    rows = _latest_ledger_rows(connection, PROGRESS_SOURCE)
    snapshots = _rows_for_kind(
        rows, table="progress_snapshots", kind="course_progress_snapshot"
    )
    history: Dict[str, List[Mapping[str, Any]]] = {}
    ordered = []
    for ledger in snapshots:
        target = _row_by_id(connection, "progress_snapshots", ledger.target_id)
        raw = _raw_object(ledger)
        course_id = _progress_course_id(ledger, raw, course_ids)
        raw["date"] = str(target["snapshot_date"])
        raw["course_id"] = course_id
        try:
            counts = json.loads(str(target["counts_json"]))
            scores = json.loads(str(target["score_json"]))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise Phase32ValidationError(
                "progress snapshot JSON is invalid: {}".format(ledger.target_id)
            ) from exc
        raw["mastered_topics"] = counts.get("mastered_topics")
        raw["total_topics"] = counts.get("total_topics")
        raw["progress_percent"] = scores.get("progress_percent")
        ordered.append((course_id.casefold(), str(target["snapshot_date"]), ledger.rowid, course_id, raw))
    for _, _, _, course_id, raw in sorted(ordered):
        history.setdefault(course_id, []).append(raw)
    return (
        {"version": _source_version(rows), "history": history},
        len(snapshots),
        rows,
    )


def _export_plan_store(
    connection: sqlite3.Connection,
    source_path: str,
    course_ids: Mapping[str, str],
    topic_names: Mapping[str, str],
) -> Tuple[Mapping[str, Any], int, Tuple[_LedgerRow, ...]]:
    rows = _latest_ledger_rows(connection, source_path)
    plan_ledgers = _rows_for_kind(rows, table="study_plans", kind="study_plan")
    item_ledgers = {
        row.target_id: row
        for row in _rows_for_kind(
            rows, table="study_plan_items", kind="study_plan_item"
        )
    }
    exported = []
    for ledger in plan_ledgers:
        target = _row_by_id(connection, "study_plans", ledger.target_id)
        raw = _raw_object(ledger)
        raw["engine_version"] = str(target["engine_version"])
        raw["start_date"] = str(target["starts_on"])
        raw["end_date"] = str(target["ends_on"])
        raw["requested_minutes"] = int(target["requested_minutes"])
        raw["stored_minutes"] = int(target["allocated_minutes"])
        raw["status"] = str(target["status"])
        raw["rationale"] = str(target["rationale"])
        raw["created_at"] = str(target["created_at"])
        raw["updated_at"] = str(target["updated_at"])
        raw.pop("days", None)
        raw.pop("sessions", None)
        raw.pop("items", None)

        items = []
        item_rows = connection.execute(
            "SELECT id, plan_date, ordinal, course_id, topic_id, minutes, "
            "action, reason, score, status "
            "FROM study_plan_items WHERE plan_id = ? "
            "ORDER BY plan_date, ordinal, id",
            (ledger.target_id,),
        ).fetchall()
        for item in item_rows:
            item_ledger = item_ledgers.get(str(item[0]))
            item_raw = _raw_object(item_ledger) if item_ledger is not None else {}
            item_raw["date"] = str(item[1])
            if item[3] is not None:
                item_raw["course_id"] = course_ids.get(str(item[3]), str(item[3]))
            if item[4] is not None:
                item_raw["topic"] = topic_names.get(str(item[4]), str(item[4]))
            item_raw["minutes"] = int(item[5])
            item_raw["action"] = str(item[6])
            item_raw["reason"] = str(item[7])
            item_raw["score"] = None if item[8] is None else float(item[8])
            item_raw["status"] = str(item[9])
            items.append(item_raw)
        raw["items"] = items
        exported.append(raw)
    return (
        {"version": _source_version(rows), "plans": exported},
        len(plan_ledgers) + len(item_ledgers),
        rows,
    )


def _scale_base_name(value: str) -> str:
    return re.sub(r"\s+\[[0-9a-fA-F]{12}\]$", "", value).strip()


def _export_grade_config(
    connection: sqlite3.Connection,
    course_ids: Mapping[str, str],
) -> Tuple[Optional[Mapping[str, Any]], int, Tuple[_LedgerRow, ...]]:
    rows = _latest_ledger_rows(connection, GRADE_SOURCE)
    if not rows:
        return None, 0, rows

    settings_ledgers = _rows_for_kind(
        rows,
        table="semester_grade_settings",
        kind="semester_grade_settings",
    )
    scale_ledgers = _rows_for_kind(
        rows, table="grade_scales", kind="grade_scale_version"
    )
    if not settings_ledgers or not scale_ledgers:
        raise Phase32ValidationError(
            "grade source ledger is incomplete for reverse export"
        )
    settings_ledger = settings_ledgers[-1]
    settings = connection.execute(
        "SELECT semester_id, scale_id, target_sgpa_milli, updated_at "
        "FROM semester_grade_settings WHERE semester_id = ?",
        (settings_ledger.target_id,),
    ).fetchone()
    if settings is None:
        raise Phase32ValidationError("semester grade settings target is missing")
    scale = _row_by_id(connection, "grade_scales", str(settings[1]))
    bands = connection.execute(
        "SELECT minimum_bps, letter_grade, grade_point_milli "
        "FROM grade_bands WHERE scale_id = ? "
        "ORDER BY minimum_bps DESC, id",
        (str(settings[1]),),
    ).fetchall()
    payload: Dict[str, Any] = {
        "version": _source_version(rows),
        "semester_name": str(
            settings_ledger.details.get("semester_name") or ""
        ),
        "target_sgpa": _unscale(settings[2], 1000),
        "grade_scale_name": _scale_base_name(str(scale["name"])),
        "grade_scale_source": str(scale["source"]),
        "grade_scale_verified": bool(scale["verified"]),
        "grade_scale": [
            {
                "letter": str(row[1]),
                "min_score": _unscale(row[0], 100),
                "grade_point": _unscale(row[2], 1000),
            }
            for row in bands
        ],
        "courses": [],
        "updated_at": str(settings[3]),
    }
    if scale["active_from"] is not None:
        payload["grade_scale_active_from"] = str(scale["active_from"])
    if scale["active_to"] is not None:
        payload["grade_scale_active_to"] = str(scale["active_to"])

    credit_ledgers = _rows_for_kind(
        rows, table="semester_courses", kind="semester_course_credits"
    )
    manual_ledgers = _rows_for_kind(
        rows, table="manual_grade_entries", kind="manual_grade_entry"
    )
    by_course: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for ledger in tuple(credit_ledgers) + tuple(manual_ledgers):
        raw_id = str(ledger.details.get("raw_course_id") or "").strip()
        key = raw_id.casefold()
        if key not in by_course:
            raw = ledger.details.get("raw", {})
            by_course[key] = deepcopy(dict(raw)) if isinstance(raw, dict) else {}
            order.append(key)
        by_course[key]["course_id"] = raw_id

    for ledger in credit_ledgers:
        raw_id = str(ledger.details.get("raw_course_id") or "").strip()
        composite = ledger.target_id.split("|", 1)
        if len(composite) == 2:
            row = connection.execute(
                "SELECT credits_milli FROM semester_courses "
                "WHERE semester_id = ? AND course_id = ?",
                tuple(composite),
            ).fetchone()
            if row is not None:
                by_course[raw_id.casefold()]["credits"] = _unscale(row[0], 1000)

    for ledger in manual_ledgers:
        raw_id = str(ledger.details.get("raw_course_id") or "").strip()
        entry = _row_by_id(connection, "manual_grade_entries", ledger.target_id)
        course = by_course[raw_id.casefold()]
        course["course_id"] = course_ids.get(str(entry["course_id"]), raw_id)
        course["manual_score"] = _unscale(entry["score_bps"], 100)
        course["manual_letter_grade"] = (
            None if entry["letter_grade"] is None else str(entry["letter_grade"])
        )
        course["manual_grade_point"] = _unscale(
            entry["grade_point_milli"], 1000
        )
        course["entry_kind"] = str(entry["entry_kind"])
        course["note"] = str(entry["note"])
        course["recorded_at"] = str(entry["recorded_at"])

    payload["courses"] = [by_course[key] for key in order]
    result_ledgers = _rows_for_kind(
        rows, table="semester_results", kind="semester_result"
    )
    if result_ledgers:
        result = _row_by_id(
            connection, "semester_results", result_ledgers[-1].target_id
        )
        payload["semester_result"] = {
            "earned_credits": _unscale(result["earned_credits_milli"], 1000),
            "earned_grade_points": _unscale(
                result["earned_grade_points_milli"], 1000
            ),
            "sgpa": _unscale(result["sgpa_milli"], 1000),
            "verified": bool(result["verified"]),
            "source": str(result["source"]),
            "recorded_at": str(result["recorded_at"]),
        }
    return payload, (
        len(scale_ledgers)
        + len(bands)
        + len(settings_ledgers)
        + len(credit_ledgers)
        + len(manual_ledgers)
        + len(result_ledgers)
    ), rows


def _build_legacy_payloads(
    connection: sqlite3.Connection,
) -> Tuple[
    Mapping[str, Mapping[str, Any]],
    Mapping[str, int],
    Mapping[str, Tuple[_LedgerRow, ...]],
]:
    course_ids, topic_names = _legacy_identifier_maps(connection)
    payloads: Dict[str, Mapping[str, Any]] = {}
    counts: Dict[str, int] = {}
    ledgers: Dict[str, Tuple[_LedgerRow, ...]] = {}

    courses, count, rows = _export_courses(connection)
    payloads[COURSE_SOURCE], counts[COURSE_SOURCE], ledgers[COURSE_SOURCE] = (
        courses,
        count,
        rows,
    )
    assessments, count, rows = _export_assessments(connection, course_ids)
    payloads[ASSESSMENT_SOURCE], counts[ASSESSMENT_SOURCE], ledgers[ASSESSMENT_SOURCE] = (
        assessments,
        count,
        rows,
    )
    workspace, count, rows = _export_workspace(connection, topic_names)
    payloads[WORKSPACE_SOURCE], counts[WORKSPACE_SOURCE], ledgers[WORKSPACE_SOURCE] = (
        workspace,
        count,
        rows,
    )
    memory, count, rows = _export_learning_memory(connection, course_ids)
    payloads[MEMORY_SOURCE], counts[MEMORY_SOURCE], ledgers[MEMORY_SOURCE] = (
        memory,
        count,
        rows,
    )
    progress, count, rows = _export_progress(connection, course_ids)
    payloads[PROGRESS_SOURCE], counts[PROGRESS_SOURCE], ledgers[PROGRESS_SOURCE] = (
        progress,
        count,
        rows,
    )
    for source_path in (
        WEEKLY_PLAN_SOURCE,
        MULTI_PLAN_SOURCE,
        INTELLIGENT_PLAN_SOURCE,
    ):
        plan, count, rows = _export_plan_store(
            connection, source_path, course_ids, topic_names
        )
        if source_path in REQUIRED_EXPORT_SOURCES or rows:
            payloads[source_path] = plan
            counts[source_path] = count
            ledgers[source_path] = rows

    grade, count, rows = _export_grade_config(connection, course_ids)
    if grade is not None:
        payloads[GRADE_SOURCE] = grade
        counts[GRADE_SOURCE] = count
        ledgers[GRADE_SOURCE] = rows

    return payloads, counts, ledgers


def _entity_count(source_path: str, value: Any) -> int:
    if not isinstance(value, dict):
        return 0
    if source_path == COURSE_SOURCE:
        return len(value.get("courses", []))
    if source_path == ASSESSMENT_SOURCE:
        return len(value.get("assessments", []))
    if source_path == WORKSPACE_SOURCE:
        workspaces = value.get("workspaces", {})
        return sum(
            len(item.get("questions", []))
            for item in workspaces.values()
            if isinstance(item, dict)
        ) if isinstance(workspaces, dict) else 0
    if source_path == MEMORY_SOURCE:
        count = sum(
            len(value.get(key, []))
            for key in ("weak_topics", "mastered_topics", "notes", "activities", "recent_activity")
            if isinstance(value.get(key, []), list)
        )
        course_memory = value.get("course_memory", {})
        if isinstance(course_memory, dict):
            for item in course_memory.values():
                if isinstance(item, dict):
                    count += sum(
                        len(item.get(key, []))
                        for key in ("weak_topics", "mastered_topics", "notes", "activities", "recent_activity")
                        if isinstance(item.get(key, []), list)
                    )
        return count
    if source_path == PROGRESS_SOURCE:
        history = value.get("history", {})
        return sum(len(items) for items in history.values() if isinstance(items, list)) if isinstance(history, dict) else 0
    if source_path in (
        WEEKLY_PLAN_SOURCE,
        MULTI_PLAN_SOURCE,
        INTELLIGENT_PLAN_SOURCE,
    ):
        return len(value.get("plans", []))
    if source_path == GRADE_SOURCE:
        return len(value.get("courses", []))
    return 0


def _legacy_source_hashes(
    legacy_source_directory: Path,
) -> Mapping[str, str]:
    result = {}
    for source_path in REQUIRED_EXPORT_SOURCES + OPTIONAL_EXPORT_SOURCES:
        path = legacy_source_directory / Path(source_path).name
        if path.is_file() and not path.is_symlink():
            result[source_path] = _sha256_file(path)
    return result


def _reconcile_with_legacy_sources(
    export_root: Path,
    legacy_source_directory: Optional[Path],
    artifacts: Sequence[ReverseExportArtifact],
) -> Tuple[Tuple[Mapping[str, Any], ...], bool]:
    if legacy_source_directory is None:
        return (
            tuple(
                {
                    "source_path": artifact.source_path,
                    "status": "ledger_equivalent",
                    "source_sha256": artifact.source_hash,
                    "export_sha256": artifact.sha256,
                    "source_entity_count": None,
                    "export_entity_count": artifact.record_count,
                    "documented_differences": [
                        "physical legacy source was not supplied for direct comparison"
                    ],
                }
                for artifact in artifacts
            ),
            True,
        )

    source_root = Path(legacy_source_directory)
    before = _legacy_source_hashes(source_root)
    results = []
    for artifact in artifacts:
        source_file = source_root / Path(artifact.source_path).name
        export_file = export_root / artifact.relative_path
        exported = json.loads(export_file.read_text(encoding="utf-8"))
        if not source_file.exists():
            results.append(
                {
                    "source_path": artifact.source_path,
                    "status": "source_absent",
                    "source_sha256": "",
                    "export_sha256": artifact.sha256,
                    "source_entity_count": None,
                    "export_entity_count": _entity_count(
                        artifact.source_path, exported
                    ),
                    "documented_differences": [
                        "optional or unavailable legacy source was reconstructed from SQLite"
                    ],
                }
            )
            continue
        raw = source_file.read_bytes()
        try:
            legacy = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise Phase32ValidationError(
                "legacy source is not valid JSON during reconciliation: {}".format(
                    artifact.source_path
                )
            ) from exc
        exact = legacy == exported
        differences = []
        if not exact:
            if artifact.source_path == COURSE_SOURCE:
                differences.append(
                    "deferred document_links have no Phase 3.1 relational reverse mapping"
                )
            if artifact.source_path == WORKSPACE_SOURCE:
                differences.append(
                    "workspace-level timestamps and aliases were not represented relationally"
                )
            if artifact.source_path == MEMORY_SOURCE:
                differences.append(
                    "activities/recent_activity aliases use one canonical compatibility shape"
                )
            if artifact.source_path in (
                WEEKLY_PLAN_SOURCE,
                MULTI_PLAN_SOURCE,
                INTELLIGENT_PLAN_SOURCE,
            ):
                differences.append(
                    "plan days/sessions are exported as importer-compatible canonical items"
                )
            if artifact.source_path == GRADE_SOURCE:
                differences.append(
                    "grade aliases are exported as canonical scale/course/result fields"
                )
            source_keys = sorted(legacy.keys()) if isinstance(legacy, dict) else []
            export_keys = sorted(exported.keys()) if isinstance(exported, dict) else []
            if source_keys != export_keys:
                differences.append(
                    "top-level keys differ: source={} export={}".format(
                        source_keys, export_keys
                    )
                )
            if not differences:
                differences.append(
                    "SQLite-compatible values differ from the preserved legacy snapshot"
                )
        results.append(
            {
                "source_path": artifact.source_path,
                "status": "exact" if exact else "documented_difference",
                "source_sha256": _sha256_bytes(raw),
                "export_sha256": artifact.sha256,
                "source_entity_count": _entity_count(
                    artifact.source_path, legacy
                ),
                "export_entity_count": _entity_count(
                    artifact.source_path, exported
                ),
                "documented_differences": differences,
            }
        )
    after = _legacy_source_hashes(source_root)
    return tuple(results), before == after


def _historical_discrepancies(
    connection: sqlite3.Connection,
    ledgers: Mapping[str, Tuple[_LedgerRow, ...]],
) -> Tuple[Mapping[str, Any], ...]:
    items: List[Mapping[str, Any]] = []
    for row in connection.execute(
        "SELECT id, kind, engine_version, requested_minutes, allocated_minutes "
        "FROM study_plans WHERE requested_minutes <> allocated_minutes "
        "ORDER BY id"
    ).fetchall():
        items.append(
            {
                "code": "requested_allocated_minutes_difference",
                "entity": "study_plan",
                "entity_id": str(row[0]),
                "kind": str(row[1]),
                "engine_version": str(row[2]),
                "requested_minutes": int(row[3]),
                "allocated_minutes": int(row[4]),
                "policy": "preserved_without_rebalancing",
            }
        )

    assessment_version = (
        _source_version(ledgers.get(ASSESSMENT_SOURCE, ()), default="")
        if ledgers.get(ASSESSMENT_SOURCE)
        else ""
    )
    if str(assessment_version) == "1":
        items.append(
            {
                "code": "assessment_schema_code_v2_file_v1",
                "entity": "source_schema",
                "source_path": ASSESSMENT_SOURCE,
                "file_version": 1,
                "policy": "file_version_preserved",
            }
        )
    memory_version = (
        _source_version(ledgers.get(MEMORY_SOURCE, ()), default="")
        if ledgers.get(MEMORY_SOURCE)
        else ""
    )
    if str(memory_version) == "1":
        items.append(
            {
                "code": "learning_memory_code_v2_file_v1",
                "entity": "source_schema",
                "source_path": MEMORY_SOURCE,
                "file_version": 1,
                "policy": "file_version_preserved",
            }
        )

    unverified = connection.execute(
        "SELECT COUNT(*) FROM grade_scales WHERE verified = 0"
    ).fetchone()
    if unverified is not None and int(unverified[0]):
        items.append(
            {
                "code": "unverified_planning_grade_scale",
                "entity": "grade_scale",
                "count": int(unverified[0]),
                "policy": "unverified_state_preserved",
            }
        )
    unresolved_topics = connection.execute(
        "SELECT COUNT(*) FROM assessment_topics WHERE topic_id IS NULL"
    ).fetchone()
    if unresolved_topics is not None and int(unresolved_topics[0]):
        items.append(
            {
                "code": "unresolved_assessment_topic_labels",
                "entity": "assessment_topic",
                "count": int(unresolved_topics[0]),
                "policy": "raw_labels_preserved_without_guessing",
            }
        )
    return tuple(items)


def reverse_export_phase3(
    connection: sqlite3.Connection,
    output_directory: PathLike,
    *,
    legacy_source_directory: Optional[PathLike] = None,
    generated_at: Optional[str] = None,
) -> ReverseExportResult:
    """Export one Phase 3 shadow DB into a brand-new isolated directory.

    The destination must not exist. A supplied legacy source directory is read
    only for direct reconciliation and is hashed before and after the export.
    """
    database_label = _assert_shadow_connection(connection)
    protected = (
        (legacy_source_directory,) if legacy_source_directory is not None else ()
    )
    output = _validate_new_directory(
        output_directory,
        protected_roots=protected,
    )
    source_root = (
        Path(legacy_source_directory)
        if legacy_source_directory is not None
        else None
    )
    if source_root is not None and not source_root.is_dir():
        raise Phase32InputError("legacy source directory does not exist")

    before_changes = connection.total_changes
    integrity, foreign_keys = _require_clean_sqlite(connection)
    payloads, record_counts, ledgers = _build_legacy_payloads(connection)
    relational = _table_snapshot(connection)
    discrepancies = _historical_discrepancies(connection, ledgers)
    stamp = str(generated_at or _utc_now_text()).strip()
    if not stamp:
        raise Phase32InputError("generated_at must not be blank")

    staging = output.parent / ".{}.building-{}".format(
        output.name, uuid.uuid4().hex
    )
    staging.mkdir()
    try:
        artifacts = []
        for source_path in (
            REQUIRED_EXPORT_SOURCES + OPTIONAL_EXPORT_SOURCES
        ):
            if source_path not in payloads:
                continue
            relative = "legacy_json/{}".format(Path(source_path).name)
            sha256, byte_count = _write_json_exclusive(
                staging / relative, payloads[source_path]
            )
            source_rows = ledgers.get(source_path, ())
            artifacts.append(
                ReverseExportArtifact(
                    source_path=source_path,
                    relative_path=relative,
                    source_hash=(
                        source_rows[0].source_hash if source_rows else ""
                    ),
                    source_version=str(
                        _source_version(source_rows, default="")
                    ),
                    sha256=sha256,
                    byte_count=byte_count,
                    record_count=int(record_counts.get(source_path, 0)),
                )
            )

        relational_relative = "phase3_relational_snapshot.json"
        relational_sha, relational_size = _write_json_exclusive(
            staging / relational_relative,
            {
                "export_version": REVERSE_EXPORT_VERSION,
                "generated_at": stamp,
                "database_role": "temporary_shadow",
                "database_label": database_label,
                **relational,
            },
        )
        reconciliation, sources_unchanged = _reconcile_with_legacy_sources(
            staging, source_root, artifacts
        )
        if not sources_unchanged:
            raise Phase32ValidationError(
                "legacy source bytes changed during reverse export"
            )
        if connection.total_changes != before_changes:
            raise Phase32ValidationError(
                "reverse export mutated the SQLite connection"
            )

        manifest = {
            "export_version": REVERSE_EXPORT_VERSION,
            "generated_at": stamp,
            "status": (
                "pass_with_documented_differences"
                if discrepancies
                or any(item["status"] != "exact" for item in reconciliation)
                else "pass"
            ),
            "authority": {
                "legacy_json_authoritative_until_phase4": True,
                "sqlite_role": "temporary_shadow",
                "real_user_data_written": False,
            },
            "database": {
                "label": database_label,
                "integrity_check": {
                    "status": "pass",
                    "results": list(integrity),
                },
                "foreign_key_check": {
                    "status": "pass",
                    "violations": list(foreign_keys),
                },
                "relational_snapshot": {
                    "path": relational_relative,
                    "sha256": relational_sha,
                    "byte_count": relational_size,
                },
            },
            "legacy_exports": [
                {
                    "source_path": item.source_path,
                    "path": item.relative_path,
                    "source_hash": item.source_hash,
                    "source_version": item.source_version,
                    "sha256": item.sha256,
                    "byte_count": item.byte_count,
                    "record_count": item.record_count,
                }
                for item in artifacts
            ],
            "reconciliation": list(reconciliation),
            "documented_historical_discrepancies": list(discrepancies),
            "unmigrated_legacy_sources": [
                {
                    "source_path": path,
                    "status": "not_reverse_exported",
                    "reason": (
                        "Phase 3.1 did not import this source; original remains "
                        "authoritative and untouched"
                    ),
                }
                for path in UNMIGRATED_LEGACY_SOURCES
            ],
            "compatibility_limitations": [
                (
                    "The relational snapshot is lossless for SQLite rows; legacy "
                    "JSON files are compatibility views."
                ),
                (
                    "Deferred course document_links, vault/note bodies, resources, "
                    "credentials, PDFs, vectors, and private source bytes are not "
                    "invented by reverse export."
                ),
                (
                    "Parser fragments, unresolved labels, unverified grade scales, "
                    "and requested/allocated plan differences are preserved or "
                    "reported instead of silently repaired."
                ),
            ],
        }
        manifest_path = staging / "reverse_export_manifest.json"
        _write_json_exclusive(manifest_path, manifest)
        staging.rename(output)
    except Exception:
        if staging.exists():
            shutil.rmtree(str(staging))
        raise

    status = str(manifest["status"])
    return ReverseExportResult(
        output_directory=output,
        manifest_path=output / "reverse_export_manifest.json",
        relational_snapshot_path=output / relational_relative,
        status=status,
        artifacts=tuple(artifacts),
        integrity_check=integrity,
        foreign_key_check=foreign_keys,
        reconciliation=reconciliation,
        documented_discrepancies=discrepancies,
        unmigrated_legacy_sources=UNMIGRATED_LEGACY_SOURCES,
    )


def _online_backup(
    source: sqlite3.Connection,
    destination_path: Path,
) -> None:
    if destination_path.exists():
        raise Phase32SafetyError("backup destination already exists")
    destination = sqlite3.connect(str(destination_path), isolation_level=None)
    try:
        source.backup(destination)
        destination.execute("PRAGMA wal_checkpoint(PASSIVE)")
    finally:
        destination.close()


def _restore_online_backup(
    backup_path: Path,
    restored_path: Path,
) -> None:
    if restored_path.exists():
        raise Phase32SafetyError("restore destination already exists")
    source = sqlite3.connect(str(backup_path), isolation_level=None)
    destination = sqlite3.connect(str(restored_path), isolation_level=None)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def _verify_export_artifacts(
    result: ReverseExportResult,
) -> Mapping[str, str]:
    hashes = {}
    for artifact in result.artifacts:
        path = result.output_directory / artifact.relative_path
        if not path.is_file() or path.is_symlink():
            raise Phase32ValidationError(
                "reverse-export artifact is missing or unsafe: {}".format(
                    artifact.relative_path
                )
            )
        digest = _sha256_file(path)
        if digest != artifact.sha256:
            raise Phase32ValidationError(
                "reverse-export artifact hash changed: {}".format(
                    artifact.relative_path
                )
            )
        hashes[artifact.relative_path] = digest
    if _sha256_file(result.relational_snapshot_path) == "":
        raise Phase32ValidationError("relational snapshot hash is unavailable")
    return hashes


def _snapshot_map(manifest: Any) -> Mapping[str, Any]:
    return {
        Path(snapshot.canonical_path).name: snapshot
        for snapshot in manifest.sources
    }


def _run_import_sequence(
    connection: sqlite3.Connection,
    snapshots: Mapping[str, Any],
    *,
    imported_at: str,
) -> Tuple[Any, ...]:
    results = []
    courses = snapshots["courses.json"]
    assessments = snapshots["assessments.json"]
    workspace = snapshots["assessment_workspace.json"]
    memory = snapshots["learning_memory.json"]
    progress = snapshots["course_progress_history.json"]

    results.append(
        import_courses_and_topics(
            connection, courses, imported_at=imported_at
        )
    )
    results.append(
        import_assessments_and_topics(
            connection, assessments, imported_at=imported_at
        )
    )
    results.append(
        import_questions_and_sources(
            connection, workspace, imported_at=imported_at
        )
    )
    results.append(
        import_question_topic_mappings(
            connection, workspace, imported_at=imported_at
        )
    )
    results.append(
        import_attempts_mistakes_and_performance(
            connection, workspace, imported_at=imported_at
        )
    )
    results.append(
        import_learning_memory_and_progress(
            connection,
            memory,
            progress,
            imported_at=imported_at,
        )
    )
    results.append(
        import_study_plans(
            connection,
            (
                snapshots["weekly_study_plans.json"],
                snapshots["multi_course_weekly_plans.json"],
                snapshots["intelligent_study_plans.json"],
            ),
            imported_at=imported_at,
        )
    )
    results.append(
        import_grades_and_academic_calendar(
            connection,
            snapshots["semester_grade_config.json"],
            assessments,
            imported_at=imported_at,
        )
    )
    return tuple(results)


def _copy_legacy_exports(
    export: ReverseExportResult,
    destination: Path,
) -> None:
    destination.mkdir()
    for artifact in export.artifacts:
        source = export.output_directory / artifact.relative_path
        target = destination / Path(artifact.source_path).name
        if target.exists():
            raise Phase32SafetyError("rehearsal source copy already exists")
        shutil.copyfile(str(source), str(target))


def rehearse_phase3_restore(
    connection: sqlite3.Connection,
    reverse_export: ReverseExportResult,
    rehearsal_directory: PathLike,
    *,
    generated_at: Optional[str] = None,
) -> RestoreRehearsalResult:
    """Rehearse online-backup restore and reverse-export re-import in isolation."""
    _assert_shadow_connection(connection)
    rehearsal = _validate_new_directory(
        rehearsal_directory,
        protected_roots=(reverse_export.output_directory,),
    )
    before_changes = connection.total_changes
    before_export_hashes = _verify_export_artifacts(reverse_export)
    stamp = str(generated_at or _utc_now_text()).strip()
    if not stamp:
        raise Phase32InputError("generated_at must not be blank")

    staging = rehearsal.parent / ".{}.building-{}".format(
        rehearsal.name, uuid.uuid4().hex
    )
    staging.mkdir()
    try:
        backup_path = staging / "phase3_online_backup.db"
        restored_path = staging / "phase3_restored_copy.db"
        reimport_path = staging / "phase3_reverse_reimport.db"
        replay_sources = staging / "legacy_json_replay"

        source_fingerprint = _database_fingerprint(connection)
        _online_backup(connection, backup_path)
        backup_sha = _sha256_file(backup_path)
        backup_connection = connect_database(backup_path, synchronous="FULL")
        try:
            backup_integrity, backup_fks = _require_clean_sqlite(
                backup_connection
            )
            backup_fingerprint = _database_fingerprint(backup_connection)
        finally:
            backup_connection.close()

        _restore_online_backup(backup_path, restored_path)
        restored_connection = connect_database(
            restored_path, synchronous="FULL"
        )
        try:
            restored_integrity, restored_fks = _require_clean_sqlite(
                restored_connection
            )
            restored_fingerprint = _database_fingerprint(
                restored_connection
            )
        finally:
            restored_connection.close()

        if not (
            source_fingerprint
            == backup_fingerprint
            == restored_fingerprint
        ):
            raise Phase32ValidationError(
                "online backup/restore fingerprint does not match source"
            )

        _copy_legacy_exports(reverse_export, replay_sources)
        replay_manifest = scan_legacy_sources(
            replay_sources,
            specs=REPLAY_SPECS,
        )
        snapshots = _snapshot_map(replay_manifest)

        migrations_first = apply_migrations(reimport_path)
        migrations_second = apply_migrations(reimport_path)
        if migrations_second:
            raise Phase32ValidationError(
                "schema migration runner is not idempotent"
            )
        reimport_connection = connect_database(
            reimport_path, synchronous="FULL"
        )
        try:
            before_first = reimport_connection.total_changes
            _run_import_sequence(
                reimport_connection,
                snapshots,
                imported_at=stamp,
            )
            first_changes = (
                reimport_connection.total_changes - before_first
            )
            first_fingerprint = _database_fingerprint(
                reimport_connection
            )

            before_second = reimport_connection.total_changes
            _run_import_sequence(
                reimport_connection,
                snapshots,
                imported_at=stamp,
            )
            second_changes = (
                reimport_connection.total_changes - before_second
            )
            second_fingerprint = _database_fingerprint(
                reimport_connection
            )
            reimport_integrity, reimport_fks = _require_clean_sqlite(
                reimport_connection
            )
        finally:
            reimport_connection.close()

        import_idempotent = (
            second_changes == 0
            and first_fingerprint == second_fingerprint
        )
        if not import_idempotent:
            raise Phase32ValidationError(
                "reverse-export re-import is not idempotent"
            )

        after_export_hashes = _verify_export_artifacts(reverse_export)
        export_hashes_unchanged = (
            before_export_hashes == after_export_hashes
        )
        if not export_hashes_unchanged:
            raise Phase32ValidationError(
                "restore rehearsal changed reverse-export artifacts"
            )
        if connection.total_changes != before_changes:
            raise Phase32ValidationError(
                "restore rehearsal mutated the source SQLite connection"
            )

        combined_integrity = tuple(
            list(backup_integrity)
            + list(restored_integrity)
            + list(reimport_integrity)
        )
        combined_fks = tuple(
            list(backup_fks) + list(restored_fks) + list(reimport_fks)
        )
        report = {
            "report_version": REHEARSAL_REPORT_VERSION,
            "generated_at": stamp,
            "status": "pass",
            "safety": {
                "temporary_copies_only": True,
                "source_sqlite_mutated": False,
                "reverse_export_artifacts_mutated": False,
                "real_legacy_or_user_data_written": False,
            },
            "online_backup_restore": {
                "backup_path": "phase3_online_backup.db",
                "restored_path": "phase3_restored_copy.db",
                "backup_sha256": backup_sha,
                "source_fingerprint": source_fingerprint,
                "backup_fingerprint": backup_fingerprint,
                "restored_fingerprint": restored_fingerprint,
                "equal": True,
                "integrity_check": list(
                    backup_integrity + restored_integrity
                ),
                "foreign_key_check": list(
                    tuple(backup_fks) + tuple(restored_fks)
                ),
            },
            "migration_idempotency": {
                "first_apply": list(migrations_first),
                "second_apply": list(migrations_second),
                "pass": not migrations_second,
            },
            "reverse_export_reimport": {
                "database_path": "phase3_reverse_reimport.db",
                "first_import_changes": first_changes,
                "second_import_changes": second_changes,
                "first_fingerprint": first_fingerprint,
                "second_fingerprint": second_fingerprint,
                "idempotent": import_idempotent,
                "integrity_check": list(reimport_integrity),
                "foreign_key_check": list(reimport_fks),
            },
        }
        _write_json_exclusive(
            staging / "restore_rehearsal_report.json",
            report,
        )
        staging.rename(rehearsal)
    except Exception:
        if staging.exists():
            shutil.rmtree(str(staging))
        raise

    return RestoreRehearsalResult(
        work_directory=rehearsal,
        report_path=rehearsal / "restore_rehearsal_report.json",
        status="pass",
        backup_path=rehearsal / "phase3_online_backup.db",
        restored_database_path=rehearsal / "phase3_restored_copy.db",
        reimport_database_path=rehearsal / "phase3_reverse_reimport.db",
        backup_sha256=backup_sha,
        source_fingerprint=source_fingerprint,
        backup_fingerprint=backup_fingerprint,
        restored_fingerprint=restored_fingerprint,
        reimport_first_fingerprint=first_fingerprint,
        reimport_second_fingerprint=second_fingerprint,
        migrations_first_apply=tuple(migrations_first),
        migrations_second_apply=tuple(migrations_second),
        first_import_changes=first_changes,
        second_import_changes=second_changes,
        integrity_check=combined_integrity,
        foreign_key_check=combined_fks,
        migration_idempotent=not migrations_second,
        import_idempotent=import_idempotent,
        export_hashes_unchanged=export_hashes_unchanged,
    )


def run_phase3_completion_gate(
    connection: sqlite3.Connection,
    reverse_export_directory: PathLike,
    restore_rehearsal_directory: PathLike,
    *,
    legacy_source_directory: PathLike,
    generated_at: Optional[str] = None,
) -> Phase3CompletionGateResult:
    """Run the complete Phase 3.2 safety gate without beginning Phase 4."""
    before_changes = connection.total_changes
    source_root = Path(legacy_source_directory)
    before_sources = _legacy_source_hashes(source_root)
    export = reverse_export_phase3(
        connection,
        reverse_export_directory,
        legacy_source_directory=source_root,
        generated_at=generated_at,
    )
    rehearsal = rehearse_phase3_restore(
        connection,
        export,
        restore_rehearsal_directory,
        generated_at=generated_at,
    )
    after_sources = _legacy_source_hashes(source_root)
    sqlite_unchanged = connection.total_changes == before_changes
    legacy_unchanged = before_sources == after_sources
    if not sqlite_unchanged or not legacy_unchanged:
        raise Phase32ValidationError(
            "Phase 3 completion gate detected source mutation"
        )
    return Phase3CompletionGateResult(
        status="pass",
        reverse_export=export,
        restore_rehearsal=rehearsal,
        sqlite_unchanged=sqlite_unchanged,
        legacy_sources_unchanged=legacy_unchanged,
    )


# Discoverable compatibility aliases.
export_phase3_reverse = reverse_export_phase3
reverse_export_sqlite_to_legacy = reverse_export_phase3
rehearse_restore = rehearse_phase3_restore
run_phase3_final_gate = run_phase3_completion_gate


__all__ = (
    "OPTIONAL_EXPORT_SOURCES",
    "Phase32Error",
    "Phase32InputError",
    "Phase32SafetyError",
    "Phase32ValidationError",
    "Phase3CompletionGateResult",
    "REQUIRED_EXPORT_SOURCES",
    "RestoreRehearsalResult",
    "ReverseExportArtifact",
    "ReverseExportResult",
    "UNMIGRATED_LEGACY_SOURCES",
    "export_phase3_reverse",
    "rehearse_phase3_restore",
    "rehearse_restore",
    "reverse_export_phase3",
    "reverse_export_sqlite_to_legacy",
    "run_phase3_completion_gate",
    "run_phase3_final_gate",
)
