"""Read-only Phase 4 post-promotion verification and closure evidence.

This module is inert on import.  It verifies an already-completed Phase 4
SQLite authority promotion without mutating the authoritative database,
legacy structured JSON, authority control, backups, or migration ledger.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple, Union
from urllib.parse import quote

from personal_learning_assistant.migration.authority_promotion import (
    BACKEND_SQLITE,
    LegacyWriteBlockedError,
    assert_legacy_write_allowed,
    read_authority_control,
    scan_structured_sources,
    validate_sqlite_readiness,
    validate_structured_manifest,
)
from personal_learning_assistant.migration.compatibility_projection_seed import (
    SEED_MANIFEST_SETTING,
)
from personal_learning_assistant.repositories.sqlite.compatibility_repository import (
    PROJECTION_PREFIX,
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
from personal_learning_assistant.repositories.sqlite.migration_runner import (
    discover_migrations,
)
from personal_learning_assistant.repositories.structured_authority_router import (
    maybe_load_sqlite_structured_store,
)

PathLike = Union[str, Path]

DATABASE_FILENAME = "learning_assistant.db"
CONTROL_FILENAME = ".phase4_authority.json"
LOCK_FILENAME = ".phase4_cutover.lock"
WORK_DIRECTORY_NAME = ".phase4_cutover_work"

STORE_TO_FILENAME = {
    STORE_COURSES: "courses.json",
    STORE_ASSESSMENTS: "assessments.json",
    STORE_ASSESSMENT_WORKSPACE: "assessment_workspace.json",
    STORE_LEARNING_MEMORY: "learning_memory.json",
    STORE_PROGRESS_HISTORY: "course_progress_history.json",
    STORE_WEEKLY_PLANS: "weekly_study_plans.json",
    STORE_MULTI_COURSE_PLANS: "multi_course_weekly_plans.json",
    STORE_INTELLIGENT_PLANS: "intelligent_study_plans.json",
    STORE_GRADE_CONFIG: "semester_grade_config.json",
}
EXPECTED_STORES = tuple(sorted(STORE_TO_FILENAME))


class PostPromotionVerificationError(RuntimeError):
    """Raised when the promoted runtime fails a closure invariant."""


@dataclass(frozen=True)
class DeferredStudyPlanReference:
    source_path: str
    legacy_key: str
    target_id: str
    reason: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class BackupVerification:
    directory: str
    manifest_sha256: str
    artifact_count: int
    sqlite_integrity: Tuple[str, ...]
    sqlite_foreign_key_violation_count: int
    evidence_present: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "directory": self.directory,
            "manifest_sha256": self.manifest_sha256,
            "artifact_count": self.artifact_count,
            "sqlite_integrity": list(self.sqlite_integrity),
            "sqlite_foreign_key_violation_count": self.sqlite_foreign_key_violation_count,
            "evidence_present": self.evidence_present,
        }


@dataclass(frozen=True)
class PostPromotionClosureReport:
    status: str
    cutover_id: str
    promoted_at: str
    source_manifest_hash: str
    sqlite_sha256: str
    source_count: int
    optional_sources_missing: Tuple[str, ...]
    migration_versions: Tuple[int, ...]
    integrity_check: Tuple[str, ...]
    foreign_key_violation_count: int
    compatibility_stores: Tuple[str, ...]
    routed_store_count: int
    legacy_write_guard_blocked: bool
    source_manifest_unchanged: bool
    database_hash_matches_promotion: bool
    lock_absent: bool
    work_directory_absent: bool
    deferred_study_plan_references: Tuple[DeferredStudyPlanReference, ...]
    backup: Optional[BackupVerification]
    reads_only: bool = True

    @property
    def review_item_count(self) -> int:
        return len(self.deferred_study_plan_references)

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["integrity_check"] = list(self.integrity_check)
        result["migration_versions"] = list(self.migration_versions)
        result["optional_sources_missing"] = list(self.optional_sources_missing)
        result["compatibility_stores"] = list(self.compatibility_stores)
        result["deferred_study_plan_references"] = [
            item.to_dict() for item in self.deferred_study_plan_references
        ]
        result["review_item_count"] = self.review_item_count
        result["backup"] = None if self.backup is None else self.backup.to_dict()
        return result


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_uri(path: Path, mode: str = "ro") -> str:
    resolved = str(path.resolve(strict=False)).replace("\\", "/")
    return "file:{}?mode={}".format(quote(resolved, safe="/:"), mode)


def _open_read_only(path: Path) -> sqlite3.Connection:
    if not path.exists() or not path.is_file() or path.is_symlink():
        raise PostPromotionVerificationError(
            "authoritative SQLite database must be a regular non-symlink file: {}".format(path)
        )
    try:
        connection = sqlite3.connect(
            _sqlite_uri(path, "ro"),
            uri=True,
            isolation_level=None,
            timeout=5.0,
        )
    except sqlite3.Error as error:
        raise PostPromotionVerificationError(
            "unable to open authoritative SQLite read-only: {}".format(error)
        ) from error
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _validate_exact_migrations(connection: sqlite3.Connection) -> Tuple[int, ...]:
    expected = discover_migrations()
    expected_versions = tuple(item.version for item in expected)
    rows = connection.execute(
        "SELECT version,name,checksum FROM schema_migrations ORDER BY version"
    ).fetchall()
    actual_versions = tuple(int(row[0]) for row in rows)
    if actual_versions != expected_versions:
        raise PostPromotionVerificationError(
            "migration history differs from repository source: expected {} found {}".format(
                expected_versions, actual_versions
            )
        )
    expected_by_version = {
        item.version: (item.name, item.checksum) for item in expected
    }
    for row in rows:
        version = int(row[0])
        name, checksum = expected_by_version[version]
        if str(row[1]) != name or str(row[2]) != checksum:
            raise PostPromotionVerificationError(
                "migration {:04d} name/checksum differs from repository source".format(
                    version
                )
            )
    return actual_versions


def _projection_stores(connection: sqlite3.Connection, manifest_hash: str) -> Tuple[str, ...]:
    stores = []
    for store_name in EXPECTED_STORES:
        key = PROJECTION_PREFIX + store_name
        row = connection.execute(
            "SELECT value_json FROM app_settings WHERE key=?", (key,)
        ).fetchone()
        if row is None:
            raise PostPromotionVerificationError(
                "missing Phase 4 compatibility projection: {}".format(store_name)
            )
        try:
            value = json.loads(str(row[0]))
        except json.JSONDecodeError as error:
            raise PostPromotionVerificationError(
                "compatibility projection is invalid JSON: {}".format(store_name)
            ) from error
        if not isinstance(value, dict):
            raise PostPromotionVerificationError(
                "compatibility projection must be a JSON object: {}".format(store_name)
            )
        stores.append(store_name)

    seed = connection.execute(
        "SELECT value_json FROM app_settings WHERE key=?", (SEED_MANIFEST_SETTING,)
    ).fetchone()
    if seed is None:
        raise PostPromotionVerificationError(
            "compatibility projection manifest-hash setting is missing"
        )
    try:
        seeded_hash = json.loads(str(seed[0]))
    except json.JSONDecodeError as error:
        raise PostPromotionVerificationError(
            "compatibility projection manifest-hash setting is invalid JSON"
        ) from error
    if str(seeded_hash) != manifest_hash:
        raise PostPromotionVerificationError(
            "compatibility projection manifest hash differs from authority source manifest"
        )
    return tuple(sorted(stores))


def _current_source_hashes(manifest: Any) -> Dict[str, str]:
    return {
        str(item.canonical_path): str(item.source_hash)
        for item in tuple(manifest.sources)
        if str(item.status) == "valid_json"
    }


def _find_deferred_study_plan_topics(
    connection: sqlite3.Connection,
    manifest: Any,
) -> Tuple[DeferredStudyPlanReference, ...]:
    source_hashes = _current_source_hashes(manifest)
    plan_sources = (
        "data/weekly_study_plans.json",
        "data/multi_course_weekly_plans.json",
        "data/intelligent_study_plans.json",
    )
    review = []
    for source_path in plan_sources:
        source_hash = source_hashes.get(source_path)
        if not source_hash:
            continue
        rows = connection.execute(
            "SELECT legacy_key,target_id,details_json "
            "FROM migration_imports "
            "WHERE source_path=? AND source_hash=? "
            "AND target_table='study_plan_items' "
            "ORDER BY legacy_key,target_id",
            (source_path, source_hash),
        ).fetchall()
        for row in rows:
            try:
                details = json.loads(str(row[2] or "{}"))
            except json.JSONDecodeError:
                details = {}
            raw_topic = str(details.get("raw_topic") or "").strip()
            target_topic = str(details.get("target_topic_id") or "").strip()
            if raw_topic and not target_topic:
                review.append(
                    DeferredStudyPlanReference(
                        source_path=source_path,
                        legacy_key=str(row[0]),
                        target_id=str(row[1]),
                        reason="legacy study-plan topic remains unresolved; no topic foreign key was guessed",
                    )
                )
    unique = {
        (item.source_path, item.legacy_key, item.target_id, item.reason): item
        for item in review
    }
    return tuple(unique[key] for key in sorted(unique))


def _verify_router_reads(
    data_directory: Path,
    database_hash_before: str,
) -> int:
    loaded = 0
    for store_name in EXPECTED_STORES:
        path = data_directory / STORE_TO_FILENAME[store_name]
        value = maybe_load_sqlite_structured_store(store_name, path)
        if value is None:
            raise PostPromotionVerificationError(
                "structured router did not select SQLite authority for {}".format(
                    store_name
                )
            )
        if not isinstance(value, Mapping):
            raise PostPromotionVerificationError(
                "structured router returned a non-mapping for {}".format(store_name)
            )
        loaded += 1
    database_path = data_directory / DATABASE_FILENAME
    if _sha256_file(database_path) != database_hash_before:
        raise PostPromotionVerificationError(
            "router read smoke unexpectedly changed the authoritative SQLite file"
        )
    return loaded


def _verify_legacy_guard(control_path: Path) -> bool:
    try:
        assert_legacy_write_allowed(control_path)
    except LegacyWriteBlockedError:
        return True
    raise PostPromotionVerificationError(
        "legacy structured writer guard did not block after SQLite promotion"
    )


def _safe_artifact_path(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    if candidate == resolved_root or resolved_root not in candidate.parents:
        raise PostPromotionVerificationError(
            "backup manifest artifact escapes backup directory: {}".format(relative)
        )
    return candidate


def verify_promotion_backup(
    backup_directory: PathLike,
    *,
    expected_cutover_id: str,
    expected_source_manifest_hash: str,
    expected_sqlite_sha256: str,
) -> BackupVerification:
    backup = Path(backup_directory).resolve(strict=False)
    if not backup.exists() or not backup.is_dir() or backup.is_symlink():
        raise PostPromotionVerificationError(
            "final promotion backup must be an existing non-symlink directory: {}".format(
                backup
            )
        )
    manifest_path = backup / "cutover_backup_manifest.json"
    evidence_path = backup / "final_promotion_evidence.json"
    if not manifest_path.is_file():
        raise PostPromotionVerificationError("cutover backup manifest is missing")
    manifest_raw = manifest_path.read_bytes()
    manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
    try:
        manifest = json.loads(manifest_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PostPromotionVerificationError(
            "cutover backup manifest is not valid UTF-8 JSON"
        ) from error
    if str(manifest.get("source_manifest_hash") or "") != expected_source_manifest_hash:
        raise PostPromotionVerificationError(
            "backup manifest source hash differs from promoted authority state"
        )

    artifacts = manifest.get("artifacts", [])
    if not isinstance(artifacts, list) or not artifacts:
        raise PostPromotionVerificationError("backup manifest contains no artifacts")
    sqlite_backup = None
    for item in artifacts:
        if not isinstance(item, Mapping):
            raise PostPromotionVerificationError("backup artifact entry is not an object")
        relative = str(item.get("relative_path") or "")
        path = _safe_artifact_path(backup, relative)
        if not path.is_file() or path.is_symlink():
            raise PostPromotionVerificationError(
                "backup artifact is missing/not a regular file: {}".format(relative)
            )
        actual_sha = _sha256_file(path)
        if actual_sha != str(item.get("sha256") or ""):
            raise PostPromotionVerificationError(
                "backup artifact hash mismatch: {}".format(relative)
            )
        if str(item.get("kind") or "") == "sqlite_online_backup":
            sqlite_backup = path

    if sqlite_backup is None:
        raise PostPromotionVerificationError("backup contains no SQLite online backup")
    backup_connection = _open_read_only(sqlite_backup)
    try:
        integrity = tuple(
            str(row[0])
            for row in backup_connection.execute("PRAGMA integrity_check").fetchall()
        )
        foreign_keys = tuple(
            tuple(row)
            for row in backup_connection.execute("PRAGMA foreign_key_check").fetchall()
        )
    finally:
        backup_connection.close()
    if integrity != ("ok",) or foreign_keys:
        raise PostPromotionVerificationError(
            "backup SQLite integrity/foreign-key validation failed"
        )

    if not evidence_path.is_file():
        raise PostPromotionVerificationError("final promotion evidence file is missing")
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PostPromotionVerificationError(
            "final promotion evidence is not valid UTF-8 JSON"
        ) from error
    for key, expected in (
        ("cutover_id", expected_cutover_id),
        ("source_manifest_hash", expected_source_manifest_hash),
    ):
        if str(evidence.get(key) or "") != expected:
            raise PostPromotionVerificationError(
                "promotion evidence {} differs from authority state".format(key)
            )

    # The final locked promotion records the database boundary hash as
    # ``initial_sqlite_authority_sha256``.  Older closure code incorrectly
    # required a non-existent top-level ``sqlite_sha256`` evidence field.
    evidence_sqlite_sha = str(
        evidence.get("initial_sqlite_authority_sha256")
        or evidence.get("sqlite_sha256")
        or ""
    )
    if evidence_sqlite_sha != expected_sqlite_sha256:
        raise PostPromotionVerificationError(
            "promotion evidence initial SQLite authority SHA-256 differs from authority state"
        )

    new_authority_state = evidence.get("new_authority_state")
    if isinstance(new_authority_state, Mapping):
        if str(new_authority_state.get("sqlite_sha256") or "") != expected_sqlite_sha256:
            raise PostPromotionVerificationError(
                "promotion evidence new_authority_state.sqlite_sha256 differs from authority state"
            )
        if str(new_authority_state.get("cutover_id") or "") != expected_cutover_id:
            raise PostPromotionVerificationError(
                "promotion evidence new_authority_state.cutover_id differs from authority state"
            )

    evidence_manifest_sha = str(evidence.get("backup_manifest_sha256") or "")
    if evidence_manifest_sha and evidence_manifest_sha != manifest_sha:
        raise PostPromotionVerificationError(
            "promotion evidence backup manifest hash differs from backup bytes"
        )

    return BackupVerification(
        directory=str(backup),
        manifest_sha256=manifest_sha,
        artifact_count=len(artifacts),
        sqlite_integrity=integrity,
        sqlite_foreign_key_violation_count=len(foreign_keys),
        evidence_present=True,
    )


def verify_post_promotion_closure(
    *,
    project_root: PathLike,
    backup_directory: Optional[PathLike] = None,
    require_promoted_database_hash: bool = True,
) -> PostPromotionClosureReport:
    root = Path(project_root).resolve(strict=False)
    data = root / "data"
    control_path = root / CONTROL_FILENAME
    database = data / DATABASE_FILENAME
    lock = root / LOCK_FILENAME
    work = root / WORK_DIRECTORY_NAME

    if not root.is_dir():
        raise PostPromotionVerificationError(
            "project root does not exist: {}".format(root)
        )
    if not data.is_dir() or data.is_symlink():
        raise PostPromotionVerificationError(
            "data directory must be a regular non-symlink directory"
        )
    if not control_path.is_file() or control_path.is_symlink():
        raise PostPromotionVerificationError(
            "post-promotion authority-control file is missing/not regular"
        )

    state = read_authority_control(control_path)
    if state.storage_backend != BACKEND_SQLITE or not state.legacy_writes_blocked:
        raise PostPromotionVerificationError(
            "Phase 4 closure requires storage_backend=sqlite and legacy_writes_blocked=true"
        )

    lock_absent = not lock.exists() and not lock.is_symlink()
    work_absent = not work.exists() and not work.is_symlink()
    if not lock_absent:
        raise PostPromotionVerificationError(
            "cutover lock remains after promotion; operator review is required"
        )
    if not work_absent:
        raise PostPromotionVerificationError(
            "cutover work directory remains after promotion; operator review is required"
        )

    manifest = scan_structured_sources(data)
    validate_structured_manifest(manifest)
    if str(manifest.manifest_hash) != state.source_manifest_hash:
        raise PostPromotionVerificationError(
            "legacy structured source manifest changed after promotion"
        )

    optional_missing = tuple(
        sorted(
            Path(str(item.canonical_path)).name
            for item in tuple(manifest.sources)
            if not item.required and str(item.status) == "missing"
        )
    )

    database_hash_before = _sha256_file(database)
    hash_matches = database_hash_before == state.sqlite_sha256
    if require_promoted_database_hash and not hash_matches:
        raise PostPromotionVerificationError(
            "authoritative SQLite bytes changed since the promotion evidence was recorded"
        )

    connection = _open_read_only(database)
    try:
        before_changes = connection.total_changes
        readiness = validate_sqlite_readiness(connection)
        migration_versions = _validate_exact_migrations(connection)
        stores = _projection_stores(connection, state.source_manifest_hash)
        deferred = _find_deferred_study_plan_topics(connection, manifest)
        after_changes = connection.total_changes
        if before_changes != after_changes:
            raise PostPromotionVerificationError(
                "post-promotion read-only verification mutated SQLite"
            )
    finally:
        connection.close()

    routed_count = _verify_router_reads(data, database_hash_before)
    guard_blocked = _verify_legacy_guard(control_path)

    manifest_after = scan_structured_sources(data)
    if str(manifest_after.manifest_hash) != state.source_manifest_hash:
        raise PostPromotionVerificationError(
            "legacy structured source bytes changed during closure verification"
        )
    if _sha256_file(database) != database_hash_before:
        raise PostPromotionVerificationError(
            "authoritative SQLite bytes changed during closure verification"
        )

    backup = None
    if backup_directory is not None:
        backup = verify_promotion_backup(
            backup_directory,
            expected_cutover_id=state.cutover_id,
            expected_source_manifest_hash=state.source_manifest_hash,
            expected_sqlite_sha256=state.sqlite_sha256,
        )

    status = "pass_with_review" if deferred else "pass"
    return PostPromotionClosureReport(
        status=status,
        cutover_id=state.cutover_id,
        promoted_at=state.promoted_at,
        source_manifest_hash=state.source_manifest_hash,
        sqlite_sha256=state.sqlite_sha256,
        source_count=len(tuple(manifest.sources)),
        optional_sources_missing=optional_missing,
        migration_versions=migration_versions,
        integrity_check=readiness.integrity_check,
        foreign_key_violation_count=len(readiness.foreign_key_check),
        compatibility_stores=stores,
        routed_store_count=routed_count,
        legacy_write_guard_blocked=guard_blocked,
        source_manifest_unchanged=True,
        database_hash_matches_promotion=hash_matches,
        lock_absent=lock_absent,
        work_directory_absent=work_absent,
        deferred_study_plan_references=deferred,
        backup=backup,
        reads_only=True,
    )


__all__ = (
    "BackupVerification",
    "DeferredStudyPlanReference",
    "PostPromotionClosureReport",
    "PostPromotionVerificationError",
    "verify_post_promotion_closure",
    "verify_promotion_backup",
)
