"""Phase 4 authority-promotion safety primitives.

This module is intentionally infrastructure-only.  It does *not* promote the
application to SQLite by importing it, and it never opens a production database
implicitly.  The final cutover sequence needs an explicit mutation lock, a
fresh legacy-source manifest, verified SQLite integrity, an immutable backup,
and one atomic backend-control change.  These helpers make those operations
explicit and testable without changing application authority by import side
effect.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple, Union


PathLike = Union[str, Path]
CONTROL_VERSION = 1
BACKEND_LEGACY = "legacy"
BACKEND_DUAL_READ = "dual_read"
BACKEND_SQLITE = "sqlite"
_ALLOWED_BACKENDS = {BACKEND_LEGACY, BACKEND_DUAL_READ, BACKEND_SQLITE}

# Only Phase-4 structured domains are included here.  Notes, Resources and
# Obsidian remain Phase-5 concerns and must not be silently promoted by this
# structured-data cutover.
STRUCTURED_SOURCE_FILENAMES: Tuple[str, ...] = (
    "courses.json",
    "assessments.json",
    "assessment_workspace.json",
    "learning_memory.json",
    "course_progress_history.json",
    "weekly_study_plans.json",
    "multi_course_weekly_plans.json",
    "intelligent_study_plans.json",
    "semester_grade_config.json",
)
OPTIONAL_STRUCTURED_SOURCE_FILENAMES = {
    "intelligent_study_plans.json",
    "semester_grade_config.json",
}

REQUIRED_STRUCTURED_TABLES: Tuple[str, ...] = (
    "schema_migrations",
    "app_settings",
    "migration_imports",
    "semesters",
    "courses",
    "semester_courses",
    "topics",
    "assessments",
    "assessment_topics",
    "questions",
    "question_sources",
    "question_topic_mappings",
    "question_attempts",
    "mistake_events",
    "topic_progress_events",
    "progress_snapshots",
    "learning_memory_entries",
    "study_plans",
    "study_plan_items",
    "grade_scales",
    "grade_bands",
    "semester_grade_settings",
    "manual_grade_entries",
    "semester_results",
    "academic_events",
)


class AuthorityPromotionError(RuntimeError):
    """Base error for Phase-4 authority-promotion infrastructure."""


class PromotionInputError(AuthorityPromotionError, ValueError):
    """Raised when explicit cutover inputs are malformed."""


class PromotionSafetyError(AuthorityPromotionError):
    """Raised before a cutover helper could violate a safety boundary."""


class PromotionLockError(AuthorityPromotionError):
    """Raised when the local mutation lock cannot be safely acquired/released."""


class PromotionValidationError(AuthorityPromotionError):
    """Raised when manifest/database/backup evidence fails validation."""


class LegacyWriteBlockedError(AuthorityPromotionError):
    """Raised by application adapters after SQLite authority is promoted."""


@dataclass(frozen=True)
class AuthorityControlState:
    version: int = CONTROL_VERSION
    storage_backend: str = BACKEND_LEGACY
    cutover_id: str = ""
    source_manifest_hash: str = ""
    sqlite_sha256: str = ""
    promoted_at: str = ""
    legacy_writes_blocked: bool = False

    def __post_init__(self) -> None:
        backend = str(self.storage_backend or "").strip().lower().replace("-", "_")
        if self.version != CONTROL_VERSION:
            raise PromotionInputError(
                "unsupported authority-control version: {}".format(self.version)
            )
        if backend not in _ALLOWED_BACKENDS:
            raise PromotionInputError(
                "storage_backend must be one of: {}".format(
                    ", ".join(sorted(_ALLOWED_BACKENDS))
                )
            )
        object.__setattr__(self, "storage_backend", backend)

        if backend == BACKEND_SQLITE:
            if not self.legacy_writes_blocked:
                raise PromotionInputError(
                    "SQLite authority requires legacy_writes_blocked=true in the same atomic control state."
                )
            if not str(self.cutover_id).strip():
                raise PromotionInputError("SQLite authority requires a cutover_id.")
            if not _is_sha256(self.source_manifest_hash):
                raise PromotionInputError(
                    "SQLite authority requires a 64-character source_manifest_hash."
                )
            if not _is_sha256(self.sqlite_sha256):
                raise PromotionInputError(
                    "SQLite authority requires a 64-character sqlite_sha256."
                )
            if not str(self.promoted_at).strip():
                raise PromotionInputError("SQLite authority requires promoted_at evidence.")
        elif self.legacy_writes_blocked:
            raise PromotionInputError(
                "legacy_writes_blocked may be true only when storage_backend=sqlite."
            )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MutationLockEvidence:
    path: Path
    token: str
    pid: int
    acquired_at: str


@dataclass(frozen=True)
class SQLiteReadiness:
    integrity_check: Tuple[str, ...]
    foreign_key_check: Tuple[Tuple[Any, ...], ...]
    migration_versions: Tuple[int, ...]
    missing_tables: Tuple[str, ...]
    total_changes_before: int
    total_changes_after: int

    @property
    def passed(self) -> bool:
        return (
            self.integrity_check == ("ok",)
            and not self.foreign_key_check
            and {1, 2}.issubset(set(self.migration_versions))
            and not self.missing_tables
            and self.total_changes_before == self.total_changes_after
        )


@dataclass(frozen=True)
class CutoverBackupArtifact:
    relative_path: str
    kind: str
    sha256: str
    byte_count: int


@dataclass(frozen=True)
class CutoverBackupResult:
    output_directory: Path
    manifest_path: Path
    sqlite_backup_path: Path
    artifacts: Tuple[CutoverBackupArtifact, ...]
    source_manifest_hash: str
    backup_manifest_sha256: str


@dataclass(frozen=True)
class ManifestVerification:
    before_hash: str
    after_hash: str
    changed_sources: Tuple[str, ...]

    @property
    def unchanged(self) -> bool:
        return self.before_hash == self.after_hash and not self.changed_sources


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _is_sha256(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _ensure_parent_exists(path: Path, label: str) -> None:
    if not path.parent.exists():
        raise PromotionInputError("{} parent directory does not exist: {}".format(label, path.parent))


def _fsync_parent_best_effort(path: Path) -> None:
    # Directory fsync is unavailable on normal Windows directory handles.  The
    # file itself is always flushed; directory fsync is best-effort on POSIX.
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


def read_authority_control(path: PathLike) -> AuthorityControlState:
    """Read explicit backend-control state without creating a file.

    A missing control file means the pre-cutover legacy authority state.  This
    makes upgrades safe for existing installations while keeping file creation
    an explicit cutover action.
    """
    control_path = Path(path)
    if not control_path.exists():
        return AuthorityControlState()
    if not control_path.is_file() or control_path.is_symlink():
        raise PromotionSafetyError(
            "authority-control path must be a regular non-symlink file: {}".format(
                control_path
            )
        )
    try:
        payload = json.loads(control_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PromotionInputError("authority-control file is not valid UTF-8 JSON") from error
    if not isinstance(payload, Mapping):
        raise PromotionInputError("authority-control JSON must be an object")
    allowed = {
        "version",
        "storage_backend",
        "cutover_id",
        "source_manifest_hash",
        "sqlite_sha256",
        "promoted_at",
        "legacy_writes_blocked",
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise PromotionInputError(
            "authority-control contains unsupported fields: {}".format(
                ", ".join(unknown)
            )
        )
    return AuthorityControlState(
        version=int(payload.get("version", CONTROL_VERSION)),
        storage_backend=str(payload.get("storage_backend", BACKEND_LEGACY)),
        cutover_id=str(payload.get("cutover_id", "")),
        source_manifest_hash=str(payload.get("source_manifest_hash", "")),
        sqlite_sha256=str(payload.get("sqlite_sha256", "")),
        promoted_at=str(payload.get("promoted_at", "")),
        legacy_writes_blocked=bool(payload.get("legacy_writes_blocked", False)),
    )


def validate_control_transition(
    current: AuthorityControlState,
    new: AuthorityControlState,
    *,
    allow_rollback: bool = False,
) -> None:
    """Reject accidental authority flips and unapproved rollback transitions."""
    if current == new:
        return
    if current.storage_backend == BACKEND_SQLITE and new.storage_backend != BACKEND_SQLITE:
        if not allow_rollback:
            raise PromotionSafetyError(
                "rollback from SQLite authority requires explicit allow_rollback=True and separate reconciliation evidence."
            )
    if new.storage_backend == BACKEND_SQLITE:
        # AuthorityControlState already enforces backup/hash/lock evidence shape.
        if current.storage_backend not in {BACKEND_LEGACY, BACKEND_DUAL_READ}:
            raise PromotionSafetyError("unsupported promotion source backend")
    elif current.storage_backend == BACKEND_SQLITE and allow_rollback:
        if new.legacy_writes_blocked:
            raise PromotionSafetyError(
                "rollback target must explicitly re-enable the selected legacy authority before legacy writes are used."
            )


def write_authority_control_atomic(
    path: PathLike,
    state: AuthorityControlState,
    *,
    expected_current: Optional[AuthorityControlState] = None,
    allow_rollback: bool = False,
) -> None:
    """Atomically replace the small backend-control file on the same volume."""
    control_path = Path(path)
    _ensure_parent_exists(control_path, "authority-control")
    if control_path.exists() and (control_path.is_symlink() or not control_path.is_file()):
        raise PromotionSafetyError(
            "authority-control path must be a regular non-symlink file"
        )
    current = read_authority_control(control_path)
    if expected_current is not None and current != expected_current:
        raise PromotionSafetyError(
            "authority-control changed since preflight; refusing compare-and-swap replacement"
        )
    validate_control_transition(current, state, allow_rollback=allow_rollback)

    token = uuid.uuid4().hex
    temporary = control_path.with_name(".{}.{}.tmp".format(control_path.name, token))
    raw = _canonical_json_bytes(state.to_dict())
    try:
        with temporary.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary), str(control_path))
        _fsync_parent_best_effort(control_path)
    finally:
        if temporary.exists():
            temporary.unlink()


def assert_legacy_write_allowed(control_path: PathLike) -> AuthorityControlState:
    """Application-layer guard to call before any legacy structured JSON write."""
    state = read_authority_control(control_path)
    if state.storage_backend == BACKEND_SQLITE or state.legacy_writes_blocked:
        raise LegacyWriteBlockedError(
            "Legacy structured JSON writes are blocked because SQLite is authoritative."
        )
    return state


class LocalMutationLock:
    """Exclusive local cutover lock; stale locks are never stolen automatically."""

    def __init__(self, path: PathLike) -> None:
        self.path = Path(path)
        self._evidence: Optional[MutationLockEvidence] = None

    @property
    def acquired(self) -> bool:
        return self._evidence is not None

    @property
    def evidence(self) -> MutationLockEvidence:
        if self._evidence is None:
            raise PromotionLockError("mutation lock has not been acquired")
        return self._evidence

    def acquire(self) -> MutationLockEvidence:
        if self._evidence is not None:
            raise PromotionLockError("mutation lock is already held by this object")
        _ensure_parent_exists(self.path, "mutation-lock")
        if self.path.is_symlink():
            raise PromotionSafetyError("mutation-lock path must not be a symlink")
        token = uuid.uuid4().hex
        acquired_at = _utc_now_text()
        payload = {
            "version": 1,
            "token": token,
            "pid": os.getpid(),
            "acquired_at": acquired_at,
        }
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            descriptor = os.open(str(self.path), flags, 0o600)
        except FileExistsError as error:
            raise PromotionLockError(
                "structured mutation lock already exists; do not steal it automatically: {}".format(
                    self.path
                )
            ) from error
        try:
            raw = _canonical_json_bytes(payload)
            os.write(descriptor, raw)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self._evidence = MutationLockEvidence(
            path=self.path,
            token=token,
            pid=os.getpid(),
            acquired_at=acquired_at,
        )
        return self._evidence

    def release(self) -> None:
        evidence = self.evidence
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PromotionLockError(
                "mutation-lock file cannot be verified; refusing to remove it"
            ) from error
        if not isinstance(payload, Mapping) or payload.get("token") != evidence.token:
            raise PromotionLockError(
                "mutation-lock ownership changed; refusing to remove another owner's lock"
            )
        self.path.unlink()
        self._evidence = None

    def __enter__(self) -> "LocalMutationLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._evidence is not None:
            self.release()


def structured_source_specs():
    """Build the exact Phase-4 structured source specs lazily.

    Importing authority-promotion infrastructure therefore has no project I/O.
    """
    from .legacy_source_scanner import LegacySourceSpec

    return tuple(
        LegacySourceSpec(
            filename,
            required=filename not in OPTIONAL_STRUCTURED_SOURCE_FILENAMES,
        )
        for filename in STRUCTURED_SOURCE_FILENAMES
    )


def scan_structured_sources(data_directory: PathLike):
    from .legacy_source_scanner import scan_legacy_sources

    return scan_legacy_sources(
        data_directory,
        specs=structured_source_specs(),
    )


def validate_structured_manifest(manifest: Any) -> None:
    """Require every mandatory structured source to be importable and stable."""
    seen = set()
    failures = []
    for snapshot in tuple(getattr(manifest, "sources", ())):
        filename = Path(str(snapshot.canonical_path)).name
        seen.add(filename)
        if filename not in STRUCTURED_SOURCE_FILENAMES:
            continue
        if filename in OPTIONAL_STRUCTURED_SOURCE_FILENAMES:
            if snapshot.status not in {"valid_json", "missing"}:
                failures.append("{}:{}".format(filename, snapshot.status))
        elif snapshot.status != "valid_json":
            failures.append("{}:{}".format(filename, snapshot.status))
    missing_specs = sorted(set(STRUCTURED_SOURCE_FILENAMES) - seen)
    if missing_specs:
        failures.extend("{}:not_scanned".format(name) for name in missing_specs)
    if failures:
        raise PromotionValidationError(
            "structured source manifest is not cutover-ready: {}".format(
                ", ".join(failures)
            )
        )


def verify_manifest_unchanged(before_manifest: Any, after_manifest: Any) -> ManifestVerification:
    before = {
        snapshot.canonical_path: (snapshot.status, snapshot.source_hash, snapshot.byte_count)
        for snapshot in tuple(getattr(before_manifest, "sources", ()))
    }
    after = {
        snapshot.canonical_path: (snapshot.status, snapshot.source_hash, snapshot.byte_count)
        for snapshot in tuple(getattr(after_manifest, "sources", ()))
    }
    changed = tuple(
        sorted(
            set(before) ^ set(after)
            | {key for key in set(before) & set(after) if before[key] != after[key]}
        )
    )
    result = ManifestVerification(
        before_hash=str(getattr(before_manifest, "manifest_hash", "")),
        after_hash=str(getattr(after_manifest, "manifest_hash", "")),
        changed_sources=changed,
    )
    if not result.unchanged:
        raise PromotionValidationError(
            "legacy structured sources changed during cutover lock: {}".format(
                ", ".join(changed) if changed else "manifest hash changed"
            )
        )
    return result


def validate_sqlite_readiness(connection: sqlite3.Connection) -> SQLiteReadiness:
    """Run schema, migration, integrity and FK checks without writes."""
    before = connection.total_changes
    table_names = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }
    missing_tables = tuple(sorted(set(REQUIRED_STRUCTURED_TABLES) - table_names))
    if "schema_migrations" in table_names:
        migration_versions = tuple(
            int(row[0])
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
        )
    else:
        migration_versions = ()
    integrity = tuple(
        str(row[0]) for row in connection.execute("PRAGMA integrity_check").fetchall()
    )
    foreign_keys = tuple(
        tuple(row) for row in connection.execute("PRAGMA foreign_key_check").fetchall()
    )
    after = connection.total_changes
    result = SQLiteReadiness(
        integrity_check=integrity,
        foreign_key_check=foreign_keys,
        migration_versions=migration_versions,
        missing_tables=missing_tables,
        total_changes_before=before,
        total_changes_after=after,
    )
    if not result.passed:
        raise PromotionValidationError(
            "SQLite is not promotion-ready: migrations={!r}, missing_tables={!r}, integrity={!r}, foreign_key_violations={}, total_changes={} -> {}".format(
                migration_versions,
                missing_tables,
                integrity,
                len(foreign_keys),
                before,
                after,
            )
        )
    return result


def _portable_relative(value: Path, root: Path) -> str:
    try:
        return value.relative_to(root).as_posix()
    except ValueError as error:
        raise PromotionSafetyError("backup artifact escaped its output directory") from error


def _ensure_safe_backup_directory(output_directory: Path, data_directory: Path) -> None:
    resolved_output = output_directory.resolve(strict=False)
    resolved_data = data_directory.resolve(strict=False)
    if resolved_output == resolved_data or resolved_data in resolved_output.parents:
        raise PromotionSafetyError(
            "final cutover backup must not be created inside the live data directory"
        )
    if output_directory.exists():
        raise PromotionSafetyError(
            "final cutover backup directory already exists and will not be overwritten: {}".format(
                output_directory
            )
        )
    if not output_directory.parent.exists():
        raise PromotionInputError(
            "backup parent directory does not exist: {}".format(output_directory.parent)
        )


def create_final_cutover_backup(
    connection: sqlite3.Connection,
    manifest: Any,
    *,
    data_directory: PathLike,
    output_directory: PathLike,
    authority_state_before: Optional[AuthorityControlState] = None,
) -> CutoverBackupResult:
    """Create a no-overwrite JSON + SQLite backup with a hash manifest.

    The supplied connection is backed up with SQLite's online backup API.  No
    database path is opened implicitly and live legacy sources are copied byte
    for byte from the already-validated source manifest.
    """
    validate_structured_manifest(manifest)
    validate_sqlite_readiness(connection)

    data_dir = Path(data_directory)
    output_dir = Path(output_directory)
    _ensure_safe_backup_directory(output_dir, data_dir)
    before_changes = connection.total_changes
    output_dir.mkdir()
    legacy_dir = output_dir / "legacy_structured_json"
    sqlite_dir = output_dir / "sqlite"
    legacy_dir.mkdir()
    sqlite_dir.mkdir()

    artifacts = []
    try:
        for snapshot in tuple(getattr(manifest, "sources", ())):
            filename = Path(str(snapshot.canonical_path)).name
            if filename not in STRUCTURED_SOURCE_FILENAMES:
                continue
            if snapshot.status == "missing":
                continue
            source_path = Path(snapshot.physical_path)
            if source_path.parent.resolve(strict=False) != data_dir.resolve(strict=False):
                raise PromotionSafetyError(
                    "source snapshot is not from the explicit data directory: {}".format(
                        snapshot.canonical_path
                    )
                )
            raw = source_path.read_bytes()
            if _sha256_bytes(raw) != snapshot.source_hash:
                raise PromotionValidationError(
                    "source changed after manifest scan: {}".format(snapshot.canonical_path)
                )
            target = legacy_dir / filename
            target.write_bytes(raw)
            artifacts.append(
                CutoverBackupArtifact(
                    relative_path=_portable_relative(target, output_dir),
                    kind="legacy_structured_json",
                    sha256=_sha256_bytes(raw),
                    byte_count=len(raw),
                )
            )

        sqlite_backup = sqlite_dir / "learning_assistant.db"
        destination = sqlite3.connect(str(sqlite_backup), isolation_level=None)
        try:
            connection.backup(destination)
        finally:
            destination.close()
        artifacts.append(
            CutoverBackupArtifact(
                relative_path=_portable_relative(sqlite_backup, output_dir),
                kind="sqlite_online_backup",
                sha256=_sha256_file(sqlite_backup),
                byte_count=sqlite_backup.stat().st_size,
            )
        )

        payload = {
            "version": 1,
            "created_at": _utc_now_text(),
            "source_manifest_hash": str(manifest.manifest_hash),
            "authority_state_before": (
                authority_state_before.to_dict()
                if authority_state_before is not None
                else None
            ),
            "artifacts": [asdict(item) for item in sorted(artifacts, key=lambda item: item.relative_path)],
        }
        manifest_path = output_dir / "cutover_backup_manifest.json"
        manifest_raw = _canonical_json_bytes(payload)
        manifest_path.write_bytes(manifest_raw)
        backup_manifest_sha256 = _sha256_bytes(manifest_raw)

        if connection.total_changes != before_changes:
            raise PromotionValidationError(
                "final backup unexpectedly changed the SQLite source connection"
            )

        # Validate the backup itself before returning success.
        check = sqlite3.connect(str(sqlite_backup), isolation_level=None)
        try:
            integrity = tuple(str(row[0]) for row in check.execute("PRAGMA integrity_check").fetchall())
            foreign_keys = tuple(tuple(row) for row in check.execute("PRAGMA foreign_key_check").fetchall())
        finally:
            check.close()
        if integrity != ("ok",) or foreign_keys:
            raise PromotionValidationError(
                "SQLite backup failed post-copy integrity validation"
            )

        return CutoverBackupResult(
            output_directory=output_dir,
            manifest_path=manifest_path,
            sqlite_backup_path=sqlite_backup,
            artifacts=tuple(sorted(artifacts, key=lambda item: item.relative_path)),
            source_manifest_hash=str(manifest.manifest_hash),
            backup_manifest_sha256=backup_manifest_sha256,
        )
    except Exception:
        # A failed backup is incomplete evidence.  Remove only the newly-created
        # output directory; never touch live sources or an existing directory.
        import shutil

        shutil.rmtree(output_dir, ignore_errors=True)
        raise


def build_sqlite_authority_state(
    *,
    source_manifest_hash: str,
    sqlite_backup_path: PathLike,
    cutover_id: Optional[str] = None,
    promoted_at: Optional[str] = None,
) -> AuthorityControlState:
    """Build, but do not write, the final atomic SQLite authority state."""
    sqlite_path = Path(sqlite_backup_path)
    if not sqlite_path.exists() or not sqlite_path.is_file():
        raise PromotionInputError("verified SQLite backup path does not exist")
    return AuthorityControlState(
        storage_backend=BACKEND_SQLITE,
        cutover_id=cutover_id or str(uuid.uuid4()),
        source_manifest_hash=str(source_manifest_hash),
        sqlite_sha256=_sha256_file(sqlite_path),
        promoted_at=promoted_at or _utc_now_text(),
        legacy_writes_blocked=True,
    )


__all__ = (
    "AuthorityControlState",
    "AuthorityPromotionError",
    "BACKEND_DUAL_READ",
    "BACKEND_LEGACY",
    "BACKEND_SQLITE",
    "CONTROL_VERSION",
    "CutoverBackupArtifact",
    "CutoverBackupResult",
    "LegacyWriteBlockedError",
    "LocalMutationLock",
    "ManifestVerification",
    "MutationLockEvidence",
    "OPTIONAL_STRUCTURED_SOURCE_FILENAMES",
    "REQUIRED_STRUCTURED_TABLES",
    "PromotionInputError",
    "PromotionLockError",
    "PromotionSafetyError",
    "PromotionValidationError",
    "SQLiteReadiness",
    "STRUCTURED_SOURCE_FILENAMES",
    "assert_legacy_write_allowed",
    "build_sqlite_authority_state",
    "create_final_cutover_backup",
    "read_authority_control",
    "scan_structured_sources",
    "structured_source_specs",
    "validate_control_transition",
    "validate_sqlite_readiness",
    "validate_structured_manifest",
    "verify_manifest_unchanged",
    "write_authority_control_atomic",
)
