"""Final locked Phase-4 promotion of structured authority to SQLite.

Importing this module is inert.  The authority switch can happen only through
``promote_final_locked_sqlite_authority`` with the exact operator confirmation
phrase.  All destructive-looking work is staged against an isolated candidate
and a verified backup before the small authority-control file is replaced.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple, Union
from urllib.parse import quote

from personal_learning_assistant.migration.authority_promotion import (
    AuthorityControlState,
    BACKEND_DUAL_READ,
    BACKEND_LEGACY,
    BACKEND_SQLITE,
    LocalMutationLock,
    PromotionInputError,
    PromotionSafetyError,
    PromotionValidationError,
    build_sqlite_authority_state,
    create_final_cutover_backup,
    read_authority_control,
    scan_structured_sources,
    validate_sqlite_readiness,
    validate_structured_manifest,
    verify_manifest_unchanged,
    write_authority_control_atomic,
)
from personal_learning_assistant.migration.compatibility_projection_seed import (
    SEED_MANIFEST_SETTING,
    seed_phase4_compatibility_projections,
)
from personal_learning_assistant.repositories.sqlite.connection import connect_database, transaction
from personal_learning_assistant.repositories.sqlite.migration_runner import (
    apply_migrations,
    discover_migrations,
)


PathLike = Union[str, Path]
CONFIRMATION_PHRASE = "PROMOTE_PHASE4_SQLITE_AUTHORITY"
DATABASE_FILENAME = "learning_assistant.db"
CONTROL_FILENAME = ".phase4_authority.json"
LOCK_FILENAME = ".phase4_cutover.lock"
WORK_DIRECTORY_NAME = ".phase4_cutover_work"
ATTENTION_FILENAME = "PROMOTION_REQUIRES_ATTENTION.json"
EVIDENCE_FILENAME = "final_promotion_evidence.json"
PROGRESS_ENGINE_VERSION = "legacy_course_progress_history_v1"


class FinalLockedPromotionError(RuntimeError):
    """Base error for the explicit final Phase-4 promotion operation."""


class FinalPromotionPreflightError(FinalLockedPromotionError):
    """Raised when real promotion inputs are not safe to use."""


class FinalPromotionExecutionError(FinalLockedPromotionError):
    """Raised when the locked operation cannot complete safely."""


class FinalPromotionRequiresAttention(FinalLockedPromotionError):
    """Raised after authority switched and automatic rollback is unsafe."""


@dataclass(frozen=True)
class PromotionPaths:
    project_root: Path
    data_directory: Path
    production_database: Path
    authority_control: Path
    mutation_lock: Path
    work_directory: Path
    backup_directory: Path


@dataclass(frozen=True)
class FinalPromotionPreflight:
    paths: PromotionPaths
    authority_state: AuthorityControlState
    source_manifest_hash: str
    source_count: int
    optional_sources_missing: Tuple[str, ...]
    production_database_exists: bool
    production_database_sha256: str
    migration_versions: Tuple[int, ...]
    integrity_check: Tuple[str, ...]
    foreign_key_violation_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_root": str(self.paths.project_root),
            "data_directory": str(self.paths.data_directory),
            "production_database": str(self.paths.production_database),
            "authority_control": str(self.paths.authority_control),
            "mutation_lock": str(self.paths.mutation_lock),
            "work_directory": str(self.paths.work_directory),
            "backup_directory": str(self.paths.backup_directory),
            "authority_state": self.authority_state.to_dict(),
            "source_manifest_hash": self.source_manifest_hash,
            "source_count": self.source_count,
            "optional_sources_missing": list(self.optional_sources_missing),
            "production_database_exists": self.production_database_exists,
            "production_database_sha256": self.production_database_sha256,
            "migration_versions": list(self.migration_versions),
            "integrity_check": list(self.integrity_check),
            "foreign_key_violation_count": self.foreign_key_violation_count,
            "preflight_writes_performed": False,
        }


@dataclass(frozen=True)
class FinalPromotionResult:
    cutover_id: str
    promoted_at: str
    source_manifest_hash: str
    sqlite_sha256: str
    backup_directory: Path
    backup_manifest_sha256: str
    evidence_path: Path
    compatibility_stores: Tuple[str, ...]
    progress_snapshots_bridged: int
    previous_database_existed: bool
    previous_database_backup_sha256: str
    import_summaries: Mapping[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cutover_id": self.cutover_id,
            "promoted_at": self.promoted_at,
            "source_manifest_hash": self.source_manifest_hash,
            "sqlite_sha256": self.sqlite_sha256,
            "backup_directory": str(self.backup_directory),
            "backup_manifest_sha256": self.backup_manifest_sha256,
            "evidence_path": str(self.evidence_path),
            "compatibility_stores": list(self.compatibility_stores),
            "progress_snapshots_bridged": self.progress_snapshots_bridged,
            "previous_database_existed": self.previous_database_existed,
            "previous_database_backup_sha256": self.previous_database_backup_sha256,
            "import_summaries": dict(self.import_summaries),
        }


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _fsync_parent_best_effort(path: Path) -> None:
    try:
        descriptor = os.open(str(path.parent), os.O_RDONLY)
    except (AttributeError, OSError):
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    if not path.parent.exists():
        raise FinalPromotionExecutionError(
            "evidence parent directory does not exist: {}".format(path.parent)
        )
    temporary = path.with_name(".{}.{}.tmp".format(path.name, uuid.uuid4().hex))
    raw = _canonical_json_bytes(dict(payload))
    try:
        with temporary.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary), str(path))
        _fsync_parent_best_effort(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _resolve_path(project_root: Path, value: PathLike) -> Path:
    path = Path(value)
    return path.resolve(strict=False) if path.is_absolute() else (project_root / path).resolve(strict=False)


def resolve_promotion_paths(project_root: PathLike, backup_directory: PathLike) -> PromotionPaths:
    root = Path(project_root).resolve(strict=False)
    backup = _resolve_path(root, backup_directory)
    data = root / "data"
    return PromotionPaths(
        project_root=root,
        data_directory=data,
        production_database=data / DATABASE_FILENAME,
        authority_control=root / CONTROL_FILENAME,
        mutation_lock=root / LOCK_FILENAME,
        work_directory=root / WORK_DIRECTORY_NAME,
        backup_directory=backup,
    )


def _sqlite_uri(path: Path, mode: str) -> str:
    resolved = str(path.resolve(strict=False)).replace("\\", "/")
    return "file:{}?mode={}".format(quote(resolved, safe="/:"), mode)


def _open_existing_database_read_only(path: Path) -> sqlite3.Connection:
    if not path.exists() or not path.is_file() or path.is_symlink():
        raise FinalPromotionPreflightError(
            "existing production/shadow database must be a regular non-symlink file: {}".format(path)
        )
    try:
        connection = sqlite3.connect(
            _sqlite_uri(path, "ro"), uri=True, isolation_level=None, timeout=5.0
        )
    except sqlite3.Error as error:
        raise FinalPromotionPreflightError(
            "unable to open existing SQLite database read-only: {}".format(error)
        ) from error
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _validate_exact_migration_history(connection: sqlite3.Connection) -> Tuple[int, ...]:
    discovered = discover_migrations()
    expected = tuple(item.version for item in discovered)
    rows = connection.execute(
        "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
    ).fetchall()
    actual = tuple(int(row[0]) for row in rows)
    if actual != expected:
        raise PromotionValidationError(
            "SQLite migration history is not exact; expected {} but found {}".format(
                expected, actual
            )
        )
    expected_by_version = {item.version: (item.name, item.checksum) for item in discovered}
    for row in rows:
        version = int(row[0])
        expected_name, expected_checksum = expected_by_version[version]
        if str(row[1]) != expected_name or str(row[2]) != expected_checksum:
            raise PromotionValidationError(
                "SQLite migration {:04d} name/checksum differs from repository source".format(
                    version
                )
            )
    return actual


def _optional_missing(manifest: Any) -> Tuple[str, ...]:
    return tuple(
        sorted(
            Path(item.canonical_path).name
            for item in tuple(getattr(manifest, "sources", ()))
            if not item.required and item.status == "missing"
        )
    )


def preflight_final_locked_promotion(
    *,
    project_root: PathLike,
    backup_directory: PathLike,
) -> FinalPromotionPreflight:
    """Perform a strictly read-only real-checkout promotion preflight."""
    paths = resolve_promotion_paths(project_root, backup_directory)
    if not paths.project_root.exists() or not paths.project_root.is_dir():
        raise FinalPromotionPreflightError(
            "project root does not exist as a directory: {}".format(paths.project_root)
        )
    if (
        not paths.data_directory.exists()
        or not paths.data_directory.is_dir()
        or paths.data_directory.is_symlink()
    ):
        raise FinalPromotionPreflightError(
            "project data directory must exist as a regular non-symlink directory: {}".format(
                paths.data_directory
            )
        )
    resolved_backup = paths.backup_directory.resolve(strict=False)
    resolved_data = paths.data_directory.resolve(strict=False)
    if resolved_backup == resolved_data or resolved_data in resolved_backup.parents:
        raise FinalPromotionPreflightError(
            "final backup directory must not be inside the live data directory"
        )
    if paths.backup_directory.exists() or paths.backup_directory.is_symlink():
        raise FinalPromotionPreflightError(
            "final backup directory already exists and will not be overwritten: {}".format(
                paths.backup_directory
            )
        )
    if not paths.backup_directory.parent.exists():
        raise FinalPromotionPreflightError(
            "final backup parent directory must already exist: {}".format(
                paths.backup_directory.parent
            )
        )
    if paths.authority_control.is_symlink():
        raise FinalPromotionPreflightError(
            "authority-control path must not be a symlink: {}".format(paths.authority_control)
        )
    if paths.mutation_lock.exists() or paths.mutation_lock.is_symlink():
        raise FinalPromotionPreflightError(
            "cutover lock already exists; do not steal it: {}".format(paths.mutation_lock)
        )
    if paths.work_directory.exists() or paths.work_directory.is_symlink():
        raise FinalPromotionPreflightError(
            "stale cutover work directory exists; review/remove it before promotion: {}".format(
                paths.work_directory
            )
        )

    state = read_authority_control(paths.authority_control)
    if state.storage_backend == BACKEND_SQLITE:
        raise FinalPromotionPreflightError(
            "SQLite is already authoritative; final promotion is a one-way reviewed operation"
        )
    if state.storage_backend not in {BACKEND_LEGACY, BACKEND_DUAL_READ}:
        raise FinalPromotionPreflightError(
            "unsupported current structured authority state: {}".format(state.storage_backend)
        )

    manifest = scan_structured_sources(paths.data_directory)
    validate_structured_manifest(manifest)

    if paths.production_database.is_symlink():
        raise FinalPromotionPreflightError(
            "production/shadow SQLite path must not be a symlink: {}".format(
                paths.production_database
            )
        )
    if paths.production_database.exists() and not paths.production_database.is_file():
        raise FinalPromotionPreflightError(
            "production/shadow SQLite path exists but is not a regular file: {}".format(
                paths.production_database
            )
        )
    db_exists = paths.production_database.exists()
    db_hash = ""
    migration_versions: Tuple[int, ...] = ()
    integrity: Tuple[str, ...] = ()
    fk_count = 0
    if db_exists:
        connection = _open_existing_database_read_only(paths.production_database)
        try:
            readiness = validate_sqlite_readiness(connection)
            migration_versions = _validate_exact_migration_history(connection)
            integrity = readiness.integrity_check
            fk_count = len(readiness.foreign_key_check)
            db_hash = _sha256_file(paths.production_database)
        finally:
            connection.close()

    return FinalPromotionPreflight(
        paths=paths,
        authority_state=state,
        source_manifest_hash=str(manifest.manifest_hash),
        source_count=len(tuple(manifest.sources)),
        optional_sources_missing=_optional_missing(manifest),
        production_database_exists=db_exists,
        production_database_sha256=db_hash,
        migration_versions=migration_versions,
        integrity_check=integrity,
        foreign_key_violation_count=fk_count,
    )


def _online_backup_database(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FinalPromotionExecutionError(
            "refusing to overwrite SQLite backup/candidate: {}".format(destination)
        )
    source_connection = _open_existing_database_read_only(source)
    try:
        destination_connection = sqlite3.connect(str(destination), isolation_level=None)
        try:
            source_connection.backup(destination_connection)
        finally:
            destination_connection.close()
    finally:
        source_connection.close()


def _build_candidate(paths: PromotionPaths) -> Tuple[Path, bool]:
    if paths.work_directory.exists():
        raise FinalPromotionExecutionError(
            "cutover work directory unexpectedly exists: {}".format(paths.work_directory)
        )
    paths.work_directory.mkdir()
    candidate = paths.work_directory / "promotion_candidate.db"
    previous_exists = paths.production_database.exists()
    if previous_exists:
        _online_backup_database(paths.production_database, candidate)
        apply_migrations(candidate)
    else:
        apply_migrations(candidate)
    return candidate, previous_exists


def _manifest_by_path(manifest: Any) -> Dict[str, Any]:
    return {str(item.canonical_path): item for item in tuple(manifest.sources)}


def _small_tally(value: Any) -> Mapping[str, int]:
    result: Dict[str, int] = {}
    for name in ("created", "updated", "matched", "total"):
        if hasattr(value, name):
            try:
                result[name] = int(getattr(value, name))
            except (TypeError, ValueError):
                pass
    return result


def _sanitize_import_result(value: Any) -> Mapping[str, Any]:
    """Return count/hash metadata only; never copy raw private source values."""
    result: Dict[str, Any] = {"result_type": type(value).__name__}
    scalar_names = (
        "changed_rows",
        "review_required_items",
        "review_required_questions",
        "questions_scanned",
        "questions_with_attempts",
        "total_attempts",
        "total_mistakes",
        "deferred_mistakes",
        "deferred_activity_records",
        "unresolved_courses",
        "unresolved_topics",
        "unresolved_course_refs",
        "unresolved_topic_refs",
        "assessments_without_due_date",
        "sources_scanned",
    )
    for name in scalar_names:
        if hasattr(value, name):
            raw = getattr(value, name)
            if isinstance(raw, (bool, int, float, str)) or raw is None:
                result[name] = raw
    for name in (
        "courses",
        "topics",
        "assessments",
        "assessment_topics",
        "questions",
        "question_sources",
        "question_topic_mappings",
        "mappings",
        "attempts",
        "mistake_events",
        "learning_memory_entries",
        "topic_progress_events",
        "progress_snapshots",
        "study_plans",
        "study_plan_items",
        "grade_scales",
        "grade_bands",
        "semester_grade_settings",
        "semester_course_credits",
        "manual_grade_entries",
        "semester_results",
        "academic_events",
    ):
        if hasattr(value, name):
            tally = _small_tally(getattr(value, name))
            if tally:
                result[name] = tally
    for name in (
        "source_hash",
        "memory_source_hash",
        "progress_source_hash",
        "import_batch_id",
    ):
        if hasattr(value, name):
            raw = str(getattr(value, name) or "")
            if raw:
                result[name] = raw
    return result


def _run_final_imports(
    connection: sqlite3.Connection,
    manifest: Any,
    *,
    imported_at: str,
) -> Mapping[str, Any]:
    """Run all established Phase-3 importers in dependency order."""
    from personal_learning_assistant.migration.assessments_topics_importer import (
        import_assessments_and_topics,
    )
    from personal_learning_assistant.migration.attempts_performance_importer import (
        import_attempts_mistakes_and_performance,
    )
    from personal_learning_assistant.migration.courses_topics_importer import (
        import_courses_and_topics,
    )
    from personal_learning_assistant.migration.grades_calendar_importer import (
        import_grades_and_academic_calendar,
    )
    from personal_learning_assistant.migration.learning_progress_importer import (
        import_learning_memory_and_progress,
    )
    from personal_learning_assistant.migration.question_topic_mappings_importer import (
        import_question_topic_mappings,
    )
    from personal_learning_assistant.migration.questions_sources_importer import (
        import_questions_and_sources,
    )
    from personal_learning_assistant.migration.study_plans_importer import import_study_plans

    snapshots = _manifest_by_path(manifest)
    courses = snapshots["data/courses.json"]
    assessments = snapshots["data/assessments.json"]
    workspace = snapshots["data/assessment_workspace.json"]
    memory = snapshots["data/learning_memory.json"]
    progress = snapshots["data/course_progress_history.json"]
    weekly = snapshots["data/weekly_study_plans.json"]
    multi = snapshots["data/multi_course_weekly_plans.json"]
    intelligent = snapshots["data/intelligent_study_plans.json"]
    grade = snapshots["data/semester_grade_config.json"]

    raw_results = {
        "courses_topics": import_courses_and_topics(
            connection, courses, imported_at=imported_at
        ),
        "assessments_topics": import_assessments_and_topics(
            connection, assessments, imported_at=imported_at
        ),
        "questions_sources": import_questions_and_sources(
            connection, workspace, imported_at=imported_at
        ),
        "question_topic_mappings": import_question_topic_mappings(
            connection, workspace, imported_at=imported_at
        ),
        "attempts_performance": import_attempts_mistakes_and_performance(
            connection, workspace, imported_at=imported_at
        ),
        "learning_progress": import_learning_memory_and_progress(
            connection, memory, progress, imported_at=imported_at
        ),
        "study_plans": import_study_plans(
            connection, (weekly, multi, intelligent), imported_at=imported_at
        ),
        "grades_calendar": import_grades_and_academic_calendar(
            connection, grade, assessments, imported_at=imported_at
        ),
    }
    return {name: _sanitize_import_result(value) for name, value in raw_results.items()}


def _load_snapshot_json(snapshot: Any) -> Mapping[str, Any]:
    raw = Path(snapshot.physical_path).read_bytes()
    if _sha256_bytes(raw) != str(snapshot.source_hash):
        raise PromotionValidationError(
            "source changed after locked manifest scan: {}".format(snapshot.canonical_path)
        )
    try:
        value = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PromotionValidationError(
            "locked source is no longer valid JSON: {}".format(snapshot.canonical_path)
        ) from error
    if not isinstance(value, Mapping):
        raise PromotionValidationError(
            "locked progress source must contain a JSON object"
        )
    return dict(value)


def _progress_facts(raw: Any, course_id: str, position: int) -> Tuple[str, Any, Any, Any]:
    if not isinstance(raw, Mapping):
        raise PromotionValidationError(
            "progress snapshot {} for course {!r} must be an object".format(position, course_id)
        )
    date = str(raw.get("date") or "").strip()
    if not date:
        raise PromotionValidationError(
            "progress snapshot {} for course {!r} has no date".format(position, course_id)
        )
    return (
        date,
        raw.get("mastered_topics"),
        raw.get("total_topics"),
        raw.get("progress_percent"),
    )


def _progress_map(value: Any, field: str) -> Dict[Tuple[str, str], Tuple[Any, Any, Any]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise PromotionValidationError(
            "course_progress_history.json field {!r} must be an object".format(field)
        )
    result: Dict[Tuple[str, str], Tuple[Any, Any, Any]] = {}
    for raw_course, raw_items in value.items():
        course_id = str(raw_course or "").strip()
        if not course_id:
            raise PromotionValidationError("progress-history course key is blank")
        if not isinstance(raw_items, list):
            raise PromotionValidationError(
                "progress history for course {!r} must be an array".format(course_id)
            )
        for position, raw in enumerate(raw_items):
            date, mastered, total, percent = _progress_facts(raw, course_id, position)
            key = (course_id.casefold(), date)
            if key in result:
                raise PromotionValidationError(
                    "duplicate progress snapshot date {} for course {!r}".format(date, course_id)
                )
            result[key] = (mastered, total, percent)
    return result


def _resolve_bridge_course(
    connection: sqlite3.Connection,
    course_snapshot: Any,
    raw_course_id: str,
) -> str:
    keys = (
        "course:id:{}".format(raw_course_id),
        "course:code:{}".format(raw_course_id.casefold()),
    )
    placeholders = ",".join("?" for _ in keys)
    rows = connection.execute(
        "SELECT DISTINCT mi.target_id FROM migration_imports AS mi "
        "JOIN courses AS c ON c.id = mi.target_id "
        "WHERE mi.source_path = 'data/courses.json' AND mi.source_hash = ? "
        "AND mi.source_type = 'legacy_json' AND mi.target_table = 'courses' "
        "AND mi.legacy_key IN ({}) AND c.deleted_at IS NULL".format(placeholders),
        (str(course_snapshot.source_hash),) + keys,
    ).fetchall()
    targets = sorted({str(row[0]) for row in rows})
    if len(targets) != 1:
        raise PromotionValidationError(
            "current progress course {!r} resolves to {} imported course targets; expected exactly one".format(
                raw_course_id, len(targets)
            )
        )
    return targets[0]


def _bridge_current_progress_history(
    connection: sqlite3.Connection,
    progress_snapshot: Any,
    course_snapshot: Any,
    *,
    imported_at: str,
) -> int:
    """Bridge current V9 ``courses`` history without hiding contradictory evidence."""
    from personal_learning_assistant.migration.import_ledger import (
        MigrationImportLedger,
        build_import_identity,
    )
    from personal_learning_assistant.migration.legacy_json_import import (
        source_sha256,
        stable_target_id,
    )

    data = _load_snapshot_json(progress_snapshot)
    current = data.get("courses")
    older = data.get("history")
    current_map = _progress_map(current, "courses")
    older_map = _progress_map(older, "history")
    for key in sorted(set(current_map) & set(older_map)):
        if current_map[key] != older_map[key]:
            raise PromotionValidationError(
                "contradictory progress-history evidence for course/date {} / {}: history={} courses={}".format(
                    key[0], key[1], older_map[key], current_map[key]
                )
            )

    if current is None:
        return 0
    assert isinstance(current, Mapping)
    ledger = MigrationImportLedger(connection)
    processed = 0
    with transaction(connection, immediate=True):
        for raw_course, raw_items in sorted(current.items(), key=lambda item: str(item[0]).casefold()):
            course_id = str(raw_course or "").strip()
            if not course_id or not isinstance(raw_items, list):
                # _progress_map above already produced a precise validation error.
                raise PromotionValidationError("invalid current progress-history structure")
            target_course_id = _resolve_bridge_course(
                connection, course_snapshot, course_id
            )
            for position, raw in enumerate(raw_items):
                date, mastered, total, percent = _progress_facts(raw, course_id, position)
                stable_key = "course:{}/date:{}/engine:{}".format(
                    course_id, date, PROGRESS_ENGINE_VERSION
                )
                target_id = stable_target_id(
                    progress_snapshot.canonical_path,
                    "progress_snapshot",
                    stable_key,
                )
                identity = build_import_identity(
                    source_path=progress_snapshot.canonical_path,
                    source_hash=progress_snapshot.source_hash,
                    source_type=progress_snapshot.source_type,
                    source_version=progress_snapshot.source_version,
                    legacy_key=stable_key,
                    target_table="progress_snapshots",
                )
                existing_ledger = ledger.find(identity)
                existing_row = connection.execute(
                    "SELECT course_id, snapshot_date, counts_json, score_json, engine_version "
                    "FROM progress_snapshots WHERE id = ?",
                    (target_id,),
                ).fetchone()
                if existing_ledger is not None and existing_ledger.target_id != target_id:
                    raise PromotionValidationError(
                        "progress bridge identity maps to a different target: {}".format(stable_key)
                    )
                counts_json = json.dumps(
                    {"mastered_topics": mastered, "total_topics": total},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                score_json = json.dumps(
                    {"progress_percent": percent},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                if existing_row is not None:
                    actual = (
                        str(existing_row[0]),
                        str(existing_row[1]),
                        str(existing_row[2]),
                        str(existing_row[3]),
                        str(existing_row[4]),
                    )
                    expected = (
                        target_course_id,
                        date,
                        counts_json,
                        score_json,
                        PROGRESS_ENGINE_VERSION,
                    )
                    if actual != expected:
                        connection.execute(
                            "UPDATE progress_snapshots SET course_id=?, snapshot_date=?, "
                            "counts_json=?, score_json=?, engine_version=?, created_at=? "
                            "WHERE id=?",
                            expected + (imported_at, target_id),
                        )
                else:
                    connection.execute(
                        "INSERT INTO progress_snapshots "
                        "(id, course_id, snapshot_date, counts_json, score_json, engine_version, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            target_id,
                            target_course_id,
                            date,
                            counts_json,
                            score_json,
                            PROGRESS_ENGINE_VERSION,
                            imported_at,
                        ),
                    )
                if existing_ledger is None:
                    ledger.record_snapshot_import(
                        progress_snapshot,
                        legacy_key=stable_key,
                        target_table="progress_snapshots",
                        target_id=target_id,
                        details={
                            "kind": "course_progress_snapshot",
                            "course_id": target_course_id,
                            "snapshot_date": date,
                            "engine_version": PROGRESS_ENGINE_VERSION,
                            "source_shape": "courses",
                            "bridge": "final_phase4_current_progress_history",
                            "raw": dict(raw),
                        },
                        imported_at=imported_at,
                    )
                processed += 1
        source_sha256(progress_snapshot)
        source_sha256(course_snapshot)
    return processed


_LEDGER_ID_COLUMNS: Mapping[str, str] = {
    "semesters": "id",
    "courses": "id",
    "topics": "id",
    "assessments": "id",
    "assessment_topics": "id",
    "questions": "id",
    "question_sources": "id",
    "question_topic_mappings": "id",
    "question_attempts": "id",
    "mistake_events": "id",
    "learning_memory_entries": "id",
    "topic_progress_events": "id",
    "progress_snapshots": "id",
    "study_plans": "id",
    "study_plan_items": "id",
    "grade_scales": "id",
    "grade_bands": "id",
    "semester_grade_settings": "semester_id",
    "manual_grade_entries": "id",
    "semester_results": "id",
    "academic_events": "id",
    "app_settings": "key",
}


def _ledger_target_failures(connection: sqlite3.Connection) -> Tuple[Mapping[str, str], ...]:
    rows = connection.execute(
        "SELECT source_path, source_hash, legacy_key, target_table, target_id "
        "FROM migration_imports ORDER BY source_path, legacy_key, target_table, target_id"
    ).fetchall()
    failures = []
    tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }
    for row in rows:
        table = str(row[3])
        target = str(row[4])
        if table == "semester_courses":
            exists = False
            if table in tables and "|" in target:
                semester_id, course_id = target.split("|", 1)
                exists = connection.execute(
                    "SELECT 1 FROM semester_courses WHERE semester_id=? AND course_id=?",
                    (semester_id, course_id),
                ).fetchone() is not None
        else:
            column = _LEDGER_ID_COLUMNS.get(table)
            if column is None:
                continue
            exists = False
            if table in tables:
                sql = 'SELECT 1 FROM "{}" WHERE "{}"=?'.format(table, column)
                exists = connection.execute(sql, (target,)).fetchone() is not None
        if not exists:
            failures.append(
                {
                    "source_path": str(row[0]),
                    "source_hash": str(row[1]),
                    "legacy_key": str(row[2]),
                    "target_table": table,
                    "target_id": target,
                }
            )
    return tuple(failures)


def _duplicate_import_identities(connection: sqlite3.Connection) -> Tuple[Mapping[str, Any], ...]:
    rows = connection.execute(
        "SELECT source_path, source_hash, source_type, source_version, legacy_key, "
        "target_table, COUNT(DISTINCT target_id) "
        "FROM migration_imports GROUP BY source_path, source_hash, source_type, "
        "source_version, legacy_key, target_table HAVING COUNT(DISTINCT target_id) > 1 "
        "ORDER BY source_path, legacy_key, target_table"
    ).fetchall()
    return tuple(
        {
            "source_path": str(row[0]),
            "source_hash": str(row[1]),
            "source_type": str(row[2]),
            "source_version": str(row[3]),
            "legacy_key": str(row[4]),
            "target_table": str(row[5]),
            "target_count": int(row[6]),
        }
        for row in rows
    )


def _validate_candidate(connection: sqlite3.Connection) -> Tuple[int, ...]:
    validate_sqlite_readiness(connection)
    versions = _validate_exact_migration_history(connection)
    missing_targets = _ledger_target_failures(connection)
    if missing_targets:
        first = missing_targets[0]
        raise PromotionValidationError(
            "migration ledger target is missing: {target_table}:{target_id} from {source_path}".format(
                **first
            )
        )
    duplicates = _duplicate_import_identities(connection)
    if duplicates:
        first = duplicates[0]
        raise PromotionValidationError(
            "one migration identity maps to multiple targets: {} {} {}".format(
                first["source_path"], first["legacy_key"], first["target_table"]
            )
        )
    return versions


def _projection_store_names() -> Tuple[str, ...]:
    from personal_learning_assistant.repositories.sqlite.compatibility_repository import (
        STORE_ASSESSMENTS,
        STORE_ASSESSMENT_WORKSPACE,
        STORE_COURSES,
        STORE_GRADE_CONFIG,
        STORE_INTELLIGENT_PLANS,
        STORE_LEARNING_MEMORY,
        STORE_MULTI_COURSE_PLANS,
        STORE_PROGRESS_HISTORY,
        STORE_WEEKLY_PLANS,
    )

    return tuple(
        sorted(
            (
                STORE_COURSES,
                STORE_ASSESSMENTS,
                STORE_ASSESSMENT_WORKSPACE,
                STORE_LEARNING_MEMORY,
                STORE_PROGRESS_HISTORY,
                STORE_WEEKLY_PLANS,
                STORE_MULTI_COURSE_PLANS,
                STORE_INTELLIGENT_PLANS,
                STORE_GRADE_CONFIG,
            )
        )
    )


def _verify_compatibility_seed(
    connection: sqlite3.Connection,
    *,
    expected_manifest_hash: str,
) -> Tuple[str, ...]:
    from personal_learning_assistant.repositories.sqlite.compatibility_repository import PROJECTION_PREFIX

    stores = _projection_store_names()
    missing = []
    for store in stores:
        row = connection.execute(
            "SELECT value_json FROM app_settings WHERE key=?",
            (PROJECTION_PREFIX + store,),
        ).fetchone()
        if row is None:
            missing.append(store)
            continue
        try:
            json.loads(str(row[0]))
        except json.JSONDecodeError as error:
            raise PromotionValidationError(
                "compatibility projection is invalid JSON: {}".format(store)
            ) from error
    if missing:
        raise PromotionValidationError(
            "missing Phase-4 compatibility projections: {}".format(", ".join(missing))
        )
    row = connection.execute(
        "SELECT value_json FROM app_settings WHERE key=?", (SEED_MANIFEST_SETTING,)
    ).fetchone()
    if row is None:
        raise PromotionValidationError("compatibility seed manifest hash is missing")
    try:
        seeded_hash = json.loads(str(row[0]))
    except json.JSONDecodeError as error:
        raise PromotionValidationError("compatibility seed manifest hash is invalid JSON") from error
    if str(seeded_hash) != expected_manifest_hash:
        raise PromotionValidationError(
            "compatibility projection seed hash does not match locked source manifest"
        )
    return stores


def _preserve_pre_promotion_shadow(paths: PromotionPaths) -> Tuple[Optional[Path], str]:
    if not paths.production_database.exists():
        return None, ""
    shadow = paths.backup_directory / "sqlite" / "pre_promotion_shadow.db"
    _online_backup_database(paths.production_database, shadow)
    check = _open_existing_database_read_only(shadow)
    try:
        validate_sqlite_readiness(check)
        _validate_exact_migration_history(check)
    finally:
        check.close()
    return shadow, _sha256_file(shadow)


def _quiesce_existing_database(path: Path) -> None:
    if not path.exists():
        return
    if not path.is_file() or path.is_symlink():
        raise FinalPromotionExecutionError(
            "production database is not a regular non-symlink file: {}".format(path)
        )
    try:
        connection = sqlite3.connect(
            _sqlite_uri(path, "rw"), uri=True, isolation_level=None, timeout=3.0
        )
        try:
            connection.execute("PRAGMA busy_timeout = 3000")
            checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if checkpoint is not None and int(checkpoint[0]) != 0:
                raise FinalPromotionExecutionError(
                    "existing SQLite WAL could not be checkpointed; stop all application processes"
                )
            mode = str(connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0]).lower()
            if mode != "delete":
                raise FinalPromotionExecutionError(
                    "existing SQLite database could not switch to DELETE journal mode"
                )
        finally:
            connection.close()
    except sqlite3.Error as error:
        raise FinalPromotionExecutionError(
            "unable to quiesce existing SQLite database: {}".format(error)
        ) from error
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(path) + suffix)
        if sidecar.exists():
            try:
                sidecar.unlink()
            except OSError as error:
                raise FinalPromotionExecutionError(
                    "SQLite sidecar remains locked; stop all application processes: {}".format(sidecar)
                ) from error
        if sidecar.exists():
            raise FinalPromotionExecutionError(
                "SQLite sidecar could not be cleared: {}".format(sidecar)
            )


def _copy_verified_file(source: Path, destination: Path, expected_hash: str) -> None:
    raw_hash = _sha256_file(source)
    if raw_hash != expected_hash:
        raise FinalPromotionExecutionError("source SQLite backup hash changed before install")
    with source.open("rb") as src, destination.open("xb") as dst:
        shutil.copyfileobj(src, dst, length=1024 * 1024)
        dst.flush()
        os.fsync(dst.fileno())
    if _sha256_file(destination) != expected_hash:
        destination.unlink(missing_ok=True)
        raise FinalPromotionExecutionError("staged SQLite database hash differs from verified backup")


def _install_verified_database(
    paths: PromotionPaths,
    backup_database: Path,
    *,
    expected_hash: str,
    cutover_id: str,
) -> None:
    stage = paths.data_directory / ".{}.{}.stage".format(DATABASE_FILENAME, cutover_id)
    if stage.exists():
        raise FinalPromotionExecutionError("SQLite install stage already exists: {}".format(stage))
    _quiesce_existing_database(paths.production_database)
    try:
        _copy_verified_file(backup_database, stage, expected_hash)
        os.replace(str(stage), str(paths.production_database))
        _fsync_parent_best_effort(paths.production_database)
    finally:
        if stage.exists():
            stage.unlink()
    if _sha256_file(paths.production_database) != expected_hash:
        raise FinalPromotionExecutionError("installed authoritative SQLite hash differs from verified backup")


def _restore_database_before_switch(
    paths: PromotionPaths,
    *,
    previous_database_existed: bool,
    previous_shadow_backup: Optional[Path],
) -> None:
    for suffix in ("-wal", "-shm"):
        Path(str(paths.production_database) + suffix).unlink(missing_ok=True)
    if not previous_database_existed:
        paths.production_database.unlink(missing_ok=True)
        return
    if previous_shadow_backup is None or not previous_shadow_backup.exists():
        raise FinalPromotionExecutionError(
            "cannot restore pre-promotion SQLite shadow: verified shadow backup is missing"
        )
    stage = paths.data_directory / ".{}.restore.{}.stage".format(
        DATABASE_FILENAME, uuid.uuid4().hex
    )
    _online_backup_database(previous_shadow_backup, stage)
    try:
        os.replace(str(stage), str(paths.production_database))
        _fsync_parent_best_effort(paths.production_database)
    finally:
        if stage.exists():
            stage.unlink()


def _runtime_store_paths(paths: PromotionPaths) -> Mapping[str, Path]:
    from personal_learning_assistant.repositories.sqlite.compatibility_repository import (
        STORE_ASSESSMENTS,
        STORE_ASSESSMENT_WORKSPACE,
        STORE_COURSES,
        STORE_GRADE_CONFIG,
        STORE_INTELLIGENT_PLANS,
        STORE_LEARNING_MEMORY,
        STORE_MULTI_COURSE_PLANS,
        STORE_PROGRESS_HISTORY,
        STORE_WEEKLY_PLANS,
    )

    return {
        STORE_COURSES: paths.data_directory / "courses.json",
        STORE_ASSESSMENTS: paths.data_directory / "assessments.json",
        STORE_ASSESSMENT_WORKSPACE: paths.data_directory / "assessment_workspace.json",
        STORE_LEARNING_MEMORY: paths.data_directory / "learning_memory.json",
        STORE_PROGRESS_HISTORY: paths.data_directory / "course_progress_history.json",
        STORE_WEEKLY_PLANS: paths.data_directory / "weekly_study_plans.json",
        STORE_MULTI_COURSE_PLANS: paths.data_directory / "multi_course_weekly_plans.json",
        STORE_INTELLIGENT_PLANS: paths.data_directory / "intelligent_study_plans.json",
        STORE_GRADE_CONFIG: paths.data_directory / "semester_grade_config.json",
    }


def _post_promotion_checks(
    paths: PromotionPaths,
    *,
    expected_state: AuthorityControlState,
    locked_manifest: Any,
) -> Tuple[str, ...]:
    actual_state = read_authority_control(paths.authority_control)
    if actual_state != expected_state:
        raise PromotionValidationError("authority control differs immediately after atomic promotion")
    if not paths.production_database.exists() or not paths.production_database.is_file() or paths.production_database.is_symlink():
        raise PromotionValidationError("authoritative SQLite database is unavailable after promotion")
    if _sha256_file(paths.production_database) != expected_state.sqlite_sha256:
        raise PromotionValidationError("authoritative SQLite hash differs from authority-control evidence")

    connection = _open_existing_database_read_only(paths.production_database)
    try:
        _validate_candidate(connection)
        stores = _verify_compatibility_seed(
            connection, expected_manifest_hash=expected_state.source_manifest_hash
        )
    finally:
        connection.close()

    after = scan_structured_sources(paths.data_directory)
    validate_structured_manifest(after)
    verify_manifest_unchanged(locked_manifest, after)

    from personal_learning_assistant.repositories.structured_authority_router import (
        maybe_load_sqlite_structured_store,
    )

    loaded = []
    for store, path in sorted(_runtime_store_paths(paths).items()):
        value = maybe_load_sqlite_structured_store(store, path)
        if value is None:
            raise PromotionValidationError(
                "runtime router did not use SQLite after promotion for store {}".format(store)
            )
        loaded.append(store)
    if tuple(sorted(loaded)) != tuple(sorted(stores)):
        raise PromotionValidationError("runtime compatibility smoke set differs from seeded stores")
    if _sha256_file(paths.production_database) != expected_state.sqlite_sha256:
        raise PromotionValidationError("post-smoke SQLite bytes changed before lock release")
    return tuple(sorted(loaded))


def _attention_payload(
    *,
    cutover_id: str,
    promoted_at: str,
    error: BaseException,
    state: Optional[AuthorityControlState],
) -> Mapping[str, Any]:
    return {
        "version": 1,
        "cutover_id": cutover_id,
        "promoted_at": promoted_at,
        "status": "requires_attention",
        "error_type": type(error).__name__,
        "error": str(error),
        "authority_state": state.to_dict() if state is not None else None,
        "instruction": (
            "Do not run the application and do not delete the cutover lock. "
            "Review the authority control and final backup before any rollback."
        ),
    }


def promote_final_locked_sqlite_authority(
    *,
    project_root: PathLike,
    backup_directory: PathLike,
    confirmation: str,
) -> FinalPromotionResult:
    """Execute the one explicit locked Phase-4 structured authority switch."""
    if confirmation != CONFIRMATION_PHRASE:
        raise FinalPromotionExecutionError(
            "final promotion requires exact confirmation phrase: {}".format(CONFIRMATION_PHRASE)
        )

    preflight = preflight_final_locked_promotion(
        project_root=project_root,
        backup_directory=backup_directory,
    )
    paths = preflight.paths
    cutover_id = str(uuid.uuid4())
    promoted_at = _utc_now_text()
    lock = LocalMutationLock(paths.mutation_lock)
    lock.acquire()

    authority_switched = False
    database_installed = False
    previous_database_existed = preflight.production_database_exists
    previous_shadow_backup: Optional[Path] = None
    previous_shadow_hash = ""
    backup_result = None
    import_summaries: Mapping[str, Any] = {}
    bridge_count = 0
    intended_state: Optional[AuthorityControlState] = None

    try:
        # Fresh scan while the mutation lock is held; the preflight hash is not
        # accepted as final evidence if anything changed before lock acquisition.
        locked_manifest = scan_structured_sources(paths.data_directory)
        validate_structured_manifest(locked_manifest)
        if locked_manifest.manifest_hash != preflight.source_manifest_hash:
            raise PromotionValidationError(
                "structured sources changed between preflight and lock acquisition"
            )
        current_state = read_authority_control(paths.authority_control)
        if current_state != preflight.authority_state:
            raise PromotionSafetyError(
                "authority control changed between preflight and lock acquisition"
            )

        candidate_path, candidate_started_from_existing = _build_candidate(paths)
        connection = connect_database(candidate_path, synchronous="FULL")
        try:
            _validate_exact_migration_history(connection)
            import_summaries = _run_final_imports(
                connection, locked_manifest, imported_at=promoted_at
            )
            snapshots = _manifest_by_path(locked_manifest)
            bridge_count = _bridge_current_progress_history(
                connection,
                snapshots["data/course_progress_history.json"],
                snapshots["data/courses.json"],
                imported_at=promoted_at,
            )
            _validate_candidate(connection)

            seed_result = seed_phase4_compatibility_projections(
                connection,
                data_directory=paths.data_directory,
                authority_control_path=paths.authority_control,
                seeded_at=promoted_at,
                replace=True,
            )
            if seed_result.manifest_hash != locked_manifest.manifest_hash:
                raise PromotionValidationError(
                    "compatibility projection seed used a different source manifest"
                )
            compatibility_stores = _verify_compatibility_seed(
                connection,
                expected_manifest_hash=locked_manifest.manifest_hash,
            )
            _validate_candidate(connection)

            after_import = scan_structured_sources(paths.data_directory)
            validate_structured_manifest(after_import)
            verify_manifest_unchanged(locked_manifest, after_import)

            backup_result = create_final_cutover_backup(
                connection,
                locked_manifest,
                data_directory=paths.data_directory,
                output_directory=paths.backup_directory,
                authority_state_before=current_state,
            )
        finally:
            connection.close()

        # The final backup directory now exists. Preserve the old shadow DB as
        # separate rollback evidence before replacing anything under data/.
        previous_shadow_backup, previous_shadow_hash = _preserve_pre_promotion_shadow(paths)

        intended_state = build_sqlite_authority_state(
            source_manifest_hash=locked_manifest.manifest_hash,
            sqlite_backup_path=backup_result.sqlite_backup_path,
            cutover_id=cutover_id,
            promoted_at=promoted_at,
        )
        _install_verified_database(
            paths,
            backup_result.sqlite_backup_path,
            expected_hash=intended_state.sqlite_sha256,
            cutover_id=cutover_id,
        )
        database_installed = True

        immediately_before_switch = scan_structured_sources(paths.data_directory)
        validate_structured_manifest(immediately_before_switch)
        verify_manifest_unchanged(locked_manifest, immediately_before_switch)

        write_authority_control_atomic(
            paths.authority_control,
            intended_state,
            expected_current=current_state,
        )
        authority_switched = True

        smoked_stores = _post_promotion_checks(
            paths,
            expected_state=intended_state,
            locked_manifest=locked_manifest,
        )

        evidence_path = paths.backup_directory / EVIDENCE_FILENAME
        evidence = {
            "version": 1,
            "status": "promoted",
            "cutover_id": cutover_id,
            "promoted_at": promoted_at,
            "source_manifest_hash": locked_manifest.manifest_hash,
            "initial_sqlite_authority_sha256": intended_state.sqlite_sha256,
            "backup_manifest_sha256": backup_result.backup_manifest_sha256,
            "previous_authority_state": current_state.to_dict(),
            "new_authority_state": intended_state.to_dict(),
            "previous_database_existed": previous_database_existed,
            "candidate_started_from_existing_database": candidate_started_from_existing,
            "pre_promotion_shadow_backup_sha256": previous_shadow_hash,
            "progress_snapshots_bridged": bridge_count,
            "compatibility_stores_seeded": list(compatibility_stores),
            "compatibility_stores_smoked": list(smoked_stores),
            "import_summaries": dict(import_summaries),
            "legacy_structured_json_retained": True,
            "legacy_structured_writes_blocked": True,
            "deferred_phase5_domain": "courses.json.document_links",
        }
        _write_json_atomic(evidence_path, evidence)

        # Success is the only path that releases the lock after the authority
        # switch.  Remove the isolated candidate first so stale-work preflight is
        # clean for future maintenance operations.
        shutil.rmtree(paths.work_directory)
        if paths.work_directory.exists():
            raise FinalPromotionExecutionError(
                "cutover work directory could not be removed before lock release"
            )
        lock.release()
        return FinalPromotionResult(
            cutover_id=cutover_id,
            promoted_at=promoted_at,
            source_manifest_hash=locked_manifest.manifest_hash,
            sqlite_sha256=intended_state.sqlite_sha256,
            backup_directory=paths.backup_directory,
            backup_manifest_sha256=backup_result.backup_manifest_sha256,
            evidence_path=evidence_path,
            compatibility_stores=tuple(smoked_stores),
            progress_snapshots_bridged=bridge_count,
            previous_database_existed=previous_database_existed,
            previous_database_backup_sha256=previous_shadow_hash,
            import_summaries=import_summaries,
        )
    except Exception as error:
        observed_state: Optional[AuthorityControlState] = None
        try:
            observed_state = read_authority_control(paths.authority_control)
        except Exception:
            observed_state = None

        # Never blindly roll back if SQLite authority is active *or* if another
        # actor changed authority-control state after our preflight.  In either
        # case the safe response is to retain the lock and require review.
        control_drifted = (
            observed_state is None
            or observed_state != preflight.authority_state
        )
        if authority_switched or control_drifted:
            if paths.backup_directory.exists():
                try:
                    _write_json_atomic(
                        paths.backup_directory / ATTENTION_FILENAME,
                        _attention_payload(
                            cutover_id=cutover_id,
                            promoted_at=promoted_at,
                            error=error,
                            state=observed_state,
                        ),
                    )
                except Exception:
                    pass
            reason = (
                "authority switched"
                if authority_switched
                else "authority control changed concurrently"
            )
            raise FinalPromotionRequiresAttention(
                "{}; automatic rollback was refused and the cutover lock was intentionally retained: {}".format(
                    reason, error
                )
            ) from error

        # Before the authority switch, with authority-control still exactly at
        # the preflight state, legacy/current storage remains authority. If
        # verified SQLite bytes were installed already, restore the prior shadow
        # (or remove the new DB when none existed).
        restore_error: Optional[BaseException] = None
        if database_installed:
            try:
                _restore_database_before_switch(
                    paths,
                    previous_database_existed=previous_database_existed,
                    previous_shadow_backup=previous_shadow_backup,
                )
            except Exception as restore_problem:
                restore_error = restore_problem
        shutil.rmtree(paths.work_directory, ignore_errors=True)
        if lock.acquired:
            try:
                lock.release()
            except Exception as release_error:
                if restore_error is None:
                    restore_error = release_error
        if restore_error is not None:
            raise FinalPromotionExecutionError(
                "promotion failed before authority switch and cleanup also failed: {}; cleanup={}".format(
                    error, restore_error
                )
            ) from error
        raise


__all__ = (
    "ATTENTION_FILENAME",
    "CONFIRMATION_PHRASE",
    "CONTROL_FILENAME",
    "DATABASE_FILENAME",
    "EVIDENCE_FILENAME",
    "FinalLockedPromotionError",
    "FinalPromotionExecutionError",
    "FinalPromotionPreflight",
    "FinalPromotionPreflightError",
    "FinalPromotionRequiresAttention",
    "FinalPromotionResult",
    "LOCK_FILENAME",
    "PromotionPaths",
    "WORK_DIRECTORY_NAME",
    "preflight_final_locked_promotion",
    "promote_final_locked_sqlite_authority",
    "resolve_promotion_paths",
)
