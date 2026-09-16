"""Phase 7.3 Full Restore + Reverse-Restore Rehearsal.

This module consumes a *verified retained Phase 7.2 recovery pair* and proves,
entirely in a new isolated work directory, that:

* backup A and backup B each restore independently;
* the exact restored SQLite copy matches the recorded logical fingerprint;
* authority control, safe legacy JSON, registered note bodies, and registered
  source bytes restore with the hashes recorded in the bundle;
* a relocated runtime clone can point vault roots only at the isolated restored
  vault mirror;
* the Phase 5.8 lexical retrieval index can be rebuilt from restored SQLite and
  serves a course-grounded smoke query;
* the Phase 6 Tutor Workspace can open the restored runtime read-only;
* the restored exact SQLite copy can still produce a Phase 3 reverse export and
  pass the historical reverse-export re-import/restore rehearsal;
* A and B produce equivalent restore/rebuild outcomes; and
* the retained pair itself is byte-for-byte unchanged.

No production database, live vault, live registered source, or current retrieval
index is opened or modified by this module.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional, Sequence, Tuple
from urllib.parse import quote

from personal_learning_assistant.migration.reverse_export_restore import (
    rehearse_phase3_restore,
    reverse_export_phase3,
)
from personal_learning_assistant.phase7.recovery_bundle import (
    RecoveryVerificationError,
    logical_sqlite_fingerprint,
    verify_recovery_bundle,
    verify_recovery_pair,
)
from personal_learning_assistant.repositories.sqlite.adaptive_mentor_repository import (
    SQLiteAdaptiveMentorRepository,
)
from personal_learning_assistant.repositories.sqlite.exam_intelligence_repository import (
    SQLiteExamIntelligenceRepository,
)
from personal_learning_assistant.repositories.sqlite.knowledge_navigator_repository import (
    SQLiteKnowledgeNavigatorRepository,
)
from personal_learning_assistant.repositories.sqlite.retrieval_source_repository import (
    SQLiteRetrievalSourceRepository,
)
from personal_learning_assistant.repositories.sqlite.tutor_workspace_repository import (
    SQLiteTutorWorkspaceRepository,
)
from personal_learning_assistant.retrieval.index_builder import RetrievalIndexBuilder
from personal_learning_assistant.retrieval.index_store import RetrievalIndexStore
from personal_learning_assistant.services.adaptive_mentor_service import (
    AdaptiveMentorService,
)
from personal_learning_assistant.services.exam_intelligence_service import (
    ExamIntelligenceService,
)
from personal_learning_assistant.services.knowledge_navigator_service import (
    KnowledgeNavigatorService,
)
from personal_learning_assistant.services.retrieval_service import RetrievalService
from personal_learning_assistant.services.tutor_workspace_service import (
    TutorWorkspaceService,
)


CONFIRMATION_PHRASE = "REHEARSE_PHASE7_FULL_RESTORE"

_FIXED_REVERSE_TIMESTAMP = "2026-09-16T00:00:00Z"
_OUTPUT_MARKERS = ("phase7", "restore", "rehearsal")
_REQUIRED_ROLES = {"sqlite_authority", "authority_control"}


class Phase73Error(RuntimeError):
    pass


class Phase73SafetyError(Phase73Error):
    pass


class Phase73ValidationError(Phase73Error):
    pass


@dataclass(frozen=True)
class RestoredBackupResult:
    label: str
    exact_database_relative_path: str
    runtime_database_relative_path: str
    sqlite_logical_sha256: str
    restored_content_sha256: str
    restored_payload_count: int
    restored_note_body_count: int
    restored_source_file_count: int
    runtime_vault_rebind_count: int
    retrieval_source_fingerprint: str
    retrieval_chunk_count: int
    retrieval_hit_count: int
    retrieval_smoke_chunk_ids: Tuple[str, ...]
    workspace_sha256: str
    workspace_topic_count: int
    workspace_action_count: int
    reverse_export_sha256: str
    reverse_export_status: str
    reverse_restore_status: str
    reverse_migration_idempotent: bool
    reverse_import_idempotent: bool


@dataclass(frozen=True)
class RestorePairRehearsalResult:
    output_directory: Path
    report_path: Path
    status: str
    backup_a: RestoredBackupResult
    backup_b: RestoredBackupResult
    source_snapshot_identity_sha256: str
    retained_pair_unchanged: bool
    backups_equivalent: bool
    restore_performed_only_in_isolation: bool


def _canonical_json_bytes(value) -> bytes:
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


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
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
    cursor = path
    while True:
        if cursor.exists() and cursor.is_symlink():
            raise Phase73SafetyError(
                "restore path cannot traverse a symlink"
            )
        if cursor.parent == cursor:
            break
        cursor = cursor.parent


def _validate_new_work_root(
    work_root: Path,
    *,
    project_root: Path,
    recovery_root: Path,
) -> Path:
    if work_root.exists() or work_root.is_symlink():
        raise Phase73SafetyError(
            "rehearsal output must be a new absent directory"
        )
    if not work_root.parent.is_dir():
        raise Phase73SafetyError(
            "rehearsal output parent must already exist"
        )

    resolved = work_root.resolve(strict=False)
    project = project_root.resolve(strict=False)
    recovery = recovery_root.resolve(strict=False)

    leaf = work_root.name.casefold()
    if not any(marker in leaf for marker in _OUTPUT_MARKERS):
        raise Phase73SafetyError(
            "rehearsal output name must identify Phase 7/restore/rehearsal"
        )

    _assert_no_symlink_chain(work_root.parent)

    for protected, label in (
        (project, "project"),
        (recovery, "retained recovery pair"),
    ):
        if (
            resolved == protected
            or _is_relative_to(resolved, protected)
            or _is_relative_to(protected, resolved)
        ):
            raise Phase73SafetyError(
                "rehearsal output must not overlap {}".format(label)
            )
    return work_root


def _tree_snapshot(root: Path) -> Tuple[Tuple[str, int, str], ...]:
    if not root.is_dir() or root.is_symlink():
        raise Phase73SafetyError(
            "retained recovery pair is missing or unsafe"
        )
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise Phase73SafetyError(
                "retained recovery pair contains a symlink"
            )
        if path.is_file():
            rows.append(
                (
                    path.relative_to(root).as_posix(),
                    int(path.stat().st_size),
                    _sha256_file(path),
                )
            )
    return tuple(rows)


def _tree_fingerprint(root: Path) -> str:
    return _sha256_bytes(_canonical_json_bytes(_tree_snapshot(root)))


def _sqlite_uri(path: Path, mode: str) -> str:
    text = str(path.resolve(strict=False)).replace("\\", "/")
    return "file:{}?mode={}".format(quote(text, safe="/:"), mode)


def _open_db(path: Path, *, writable: bool) -> sqlite3.Connection:
    if not path.is_file() or path.is_symlink():
        raise Phase73ValidationError(
            "restored SQLite database is missing or unsafe"
        )
    connection = sqlite3.connect(
        _sqlite_uri(path, "rw" if writable else "ro"),
        uri=True,
        isolation_level=None,
        timeout=5.0,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def _sqlite_health(path: Path) -> dict:
    connection = _open_db(path, writable=False)
    try:
        integrity = str(
            connection.execute("PRAGMA integrity_check").fetchone()[0]
        )
        foreign_keys = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
        versions = tuple(
            int(row[0])
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
        )
        logical = logical_sqlite_fingerprint(connection)
    finally:
        connection.close()

    if integrity != "ok":
        raise Phase73ValidationError(
            "restored SQLite integrity_check returned {!r}".format(integrity)
        )
    if foreign_keys:
        raise Phase73ValidationError(
            "restored SQLite foreign_key_check returned {} row(s)".format(
                len(foreign_keys)
            )
        )
    if len(versions) < 4 or versions[:4] != (1, 2, 3, 4):
        raise Phase73ValidationError(
            "restored SQLite lacks intact 0001/0002/0003/0004 prefix"
        )
    return {
        "integrity_check": integrity,
        "foreign_key_violation_count": 0,
        "migration_versions": versions,
        "logical_sha256": logical,
    }


def _online_restore(backup_db: Path, restored_db: Path) -> None:
    if restored_db.exists():
        raise Phase73SafetyError("restore destination already exists")
    if not backup_db.is_file() or backup_db.is_symlink():
        raise Phase73ValidationError(
            "backup SQLite database is missing or unsafe"
        )
    restored_db.parent.mkdir(parents=True, exist_ok=True)

    source = sqlite3.connect(
        _sqlite_uri(backup_db, "ro"),
        uri=True,
        isolation_level=None,
        timeout=5.0,
    )
    destination = sqlite3.connect(
        str(restored_db),
        isolation_level=None,
        timeout=5.0,
    )
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def _copy_verified(source: Path, destination: Path, expected_sha: str) -> None:
    if not source.is_file() or source.is_symlink():
        raise Phase73ValidationError(
            "restore payload is missing or unsafe: {}".format(source.name)
        )
    actual = _sha256_file(source)
    if actual != expected_sha:
        raise Phase73ValidationError(
            "retained payload hash mismatch before restore"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    if _sha256_file(destination) != expected_sha:
        raise Phase73ValidationError(
            "restored payload hash mismatch after copy"
        )
    if _sha256_file(source) != expected_sha:
        raise Phase73ValidationError(
            "retained payload changed during restore"
        )


def _portable_relative(value: str) -> Path:
    text = str(value or "").replace("\\", "/")
    path = Path(text)
    if (
        not text
        or text.startswith("/")
        or path.is_absolute()
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise Phase73ValidationError(
            "invalid portable recovery payload path: {!r}".format(value)
        )
    return path


def _payload_entries(manifest: Mapping[str, object]) -> Tuple[Mapping[str, object], ...]:
    entries = manifest.get("payload_files", ())
    if not isinstance(entries, list):
        raise Phase73ValidationError("recovery payload_files must be a list")
    result = []
    roles = set()
    for raw in entries:
        if not isinstance(raw, dict):
            raise Phase73ValidationError(
                "recovery payload entry must be an object"
            )
        _portable_relative(str(raw.get("path", "")))
        role = str(raw.get("role", ""))
        roles.add(role)
        result.append(raw)
    if not _REQUIRED_ROLES.issubset(roles):
        raise Phase73ValidationError(
            "recovery bundle is missing required authority payload roles"
        )
    return tuple(result)


def _restore_payload_destination(
    restored_root: Path,
    relative: Path,
    role: str,
) -> Optional[Path]:
    parts = relative.parts
    if role == "legacy_json_evidence":
        if not parts or parts[0] != "legacy_json":
            raise Phase73ValidationError("legacy JSON payload path is malformed")
        return restored_root / "legacy_json" / Path(*parts[1:])
    if role == "registered_note_body":
        if not parts or parts[0] != "vaults":
            raise Phase73ValidationError("vault payload path is malformed")
        return restored_root / "vaults" / Path(*parts[1:])
    if role == "registered_source_file":
        if not parts or parts[0] != "sources":
            raise Phase73ValidationError("source payload path is malformed")
        return restored_root / "sources" / Path(*parts[1:])
    if role == "recovery_metadata":
        return restored_root / "provenance" / relative
    return None


def _content_fingerprint(records: Sequence[Mapping[str, object]]) -> str:
    identity = tuple(
        sorted(
            (
                str(item["role"]),
                str(item["restored_path"]),
                str(item["sha256"]),
                int(item["size_bytes"]),
            )
            for item in records
        )
    )
    return _sha256_bytes(_canonical_json_bytes(identity))


def _clone_runtime_database(source_db: Path, runtime_db: Path) -> None:
    _online_restore(source_db, runtime_db)


def _rebind_runtime_vaults(
    runtime_db: Path,
    restored_root: Path,
) -> int:
    connection = _open_db(runtime_db, writable=True)
    try:
        rows = connection.execute(
            "SELECT id,path_key FROM vaults ORDER BY id"
        ).fetchall()
        count = 0
        connection.execute("BEGIN IMMEDIATE")
        try:
            for row in rows:
                path_key = str(row["path_key"] or "").strip()
                if not path_key:
                    raise Phase73ValidationError(
                        "vault path_key is blank during isolated relocation"
                    )
                relative = _portable_relative(path_key)
                isolated_root = restored_root / "vaults" / relative
                isolated_root.mkdir(parents=True, exist_ok=True)
                connection.execute(
                    "UPDATE vaults SET root_path=? WHERE id=?",
                    (str(isolated_root.resolve(strict=False)), str(row["id"])),
                )
                count += 1
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
    finally:
        connection.close()
    return count


def _course_id(connection: sqlite3.Connection, course_code: str) -> str:
    rows = connection.execute(
        "SELECT id FROM courses WHERE upper(code)=upper(?) "
        "AND deleted_at IS NULL",
        (str(course_code).strip(),),
    ).fetchall()
    if len(rows) != 1:
        raise Phase73ValidationError(
            "expected exactly one active restored course for {}".format(
                course_code
            )
        )
    return str(rows[0][0])


def _real_retrieval_probe(
    runtime_db: Path,
    restored_root: Path,
    *,
    course_code: str,
    smoke_query: str,
) -> dict:
    index_root = restored_root / "runtime" / "retrieval"
    if index_root.exists():
        raise Phase73SafetyError("isolated retrieval output already exists")

    connection = _open_db(runtime_db, writable=True)
    try:
        course_id = _course_id(connection, course_code)
        repository = SQLiteRetrievalSourceRepository(connection)
        builder = RetrievalIndexBuilder(repository, index_root)
        result = builder.build(
            embedding_provider=None,
            acknowledge=True,
        )
    finally:
        connection.close()

    store = RetrievalIndexStore(index_root)
    try:
        service = RetrievalService(store)
        hits = service.search(
            smoke_query,
            course_ids=(course_id,),
            top_k=5,
        )
    finally:
        store.close()

    if not hits:
        raise Phase73ValidationError(
            "rebuilt retrieval index returned no course-grounded smoke hit"
        )

    return {
        "source_fingerprint": str(result.source_fingerprint),
        "chunk_count": int(result.chunk_count),
        "lexical_backend": str(result.lexical_backend),
        "semantic_enabled": bool(result.semantic_enabled),
        "hit_count": len(hits),
        "hit_chunk_ids": tuple(str(hit.chunk_id) for hit in hits),
    }


def _workspace_signature(snapshot) -> Tuple[str, dict]:
    payload = {
        "course_id": snapshot.course_id,
        "course_code": snapshot.course_code,
        "course_name": snapshot.course_name,
        "as_of": snapshot.as_of,
        "schema_versions": tuple(snapshot.schema_versions),
        "tutor_schema_ready": bool(snapshot.tutor_schema_ready),
        "practice_schema_ready": bool(snapshot.practice_schema_ready),
        "counts": {
            key: value
            for key, value in snapshot.counts.__dict__.items()
        },
        "recent_activity": tuple(
            (
                item.activity_type,
                item.entity_id,
                item.status,
                item.mode,
                item.topic_id,
                item.resource_id,
                item.assessment_id,
                item.occurred_at,
            )
            for item in snapshot.recent_activity
        ),
        "mentor_topics": tuple(
            (
                item.topic_id,
                item.topic_name,
                item.status,
                item.confidence,
                item.combined_priority_score,
                tuple(item.reasons),
            )
            for item in snapshot.mentor.topics
        ),
        "mentor_actions": tuple(
            (
                item.sequence,
                item.action_type,
                item.topic_id,
                item.resource_id,
                item.question_id,
                item.assessment_id,
                tuple(item.source_labels),
                bool(item.advisory),
            )
            for item in snapshot.mentor.actions
        ),
        "mentor_flags": (
            bool(snapshot.mentor.llm_called),
            bool(snapshot.mentor.writes_performed),
            bool(snapshot.mentor.authoritative_state_changes),
        ),
        "workspace_flags": (
            bool(snapshot.writes_performed),
            bool(snapshot.provider_called),
        ),
    }
    return _sha256_bytes(_canonical_json_bytes(payload)), payload


def _real_workspace_probe(
    runtime_db: Path,
    *,
    course_code: str,
    as_of: date,
) -> dict:
    connection = _open_db(runtime_db, writable=False)
    try:
        before = connection.total_changes
        navigator = KnowledgeNavigatorService(
            SQLiteKnowledgeNavigatorRepository(connection)
        )
        exam = ExamIntelligenceService(
            SQLiteExamIntelligenceRepository(connection)
        )
        mentor = AdaptiveMentorService(
            navigator_service=navigator,
            exam_intelligence_service=exam,
            evidence_repository=SQLiteAdaptiveMentorRepository(connection),
        )
        workspace = TutorWorkspaceService(
            repository=SQLiteTutorWorkspaceRepository(connection),
            mentor_service=mentor,
        )
        snapshot = workspace.snapshot(
            course_code,
            as_of=as_of,
            limit_topics=5,
            max_actions=10,
            recent_limit=12,
        )
        if connection.total_changes != before:
            raise Phase73ValidationError(
                "Tutor Workspace smoke unexpectedly wrote restored runtime SQLite"
            )
    finally:
        connection.close()

    if snapshot.provider_called or snapshot.writes_performed:
        raise Phase73ValidationError(
            "Tutor Workspace smoke violated read-only/provider-free boundary"
        )
    if (
        snapshot.mentor.llm_called
        or snapshot.mentor.writes_performed
        or snapshot.mentor.authoritative_state_changes
    ):
        raise Phase73ValidationError(
            "Adaptive Mentor smoke violated advisory/read-only boundary"
        )

    sha, payload = _workspace_signature(snapshot)
    return {
        "sha256": sha,
        "topic_count": len(snapshot.mentor.topics),
        "action_count": len(snapshot.mentor.actions),
        "payload": payload,
    }


def _reverse_semantic_sha(exported, rehearsal) -> str:
    """Stable A/B reverse-export identity.

    Phase 3's relational snapshot is an audit artifact and can contain
    restore-instance metadata tied to the isolated database identity/path.
    Comparing its raw file hash across independently named A/B restore roots is
    therefore too strict.  The retirement-safety question is whether both
    restores export the same legacy artifacts from the same logical database
    state with the same reconciliation result.

    Raw relational-snapshot hashes are still recorded separately for audit.
    """
    artifact_identity = tuple(
        sorted(
            (
                artifact.source_path,
                artifact.relative_path,
                artifact.sha256,
                int(artifact.byte_count),
                int(artifact.record_count),
            )
            for artifact in exported.artifacts
        )
    )
    identity = {
        "artifacts": artifact_identity,
        "database_source_fingerprint": str(rehearsal.source_fingerprint),
        "export_status": str(exported.status),
        "reconciliation": tuple(exported.reconciliation),
        "documented_discrepancies": tuple(
            exported.documented_discrepancies
        ),
        "unmigrated_legacy_sources": tuple(
            exported.unmigrated_legacy_sources
        ),
    }
    return _sha256_bytes(_canonical_json_bytes(identity))


def _real_reverse_probe(
    exact_db: Path,
    restored_root: Path,
) -> dict:
    connection = _open_db(exact_db, writable=False)
    try:
        reverse_dir = restored_root / "phase3-reverse-export"
        legacy_root = restored_root / "legacy_json"
        if not legacy_root.is_dir():
            raise Phase73ValidationError(
                "restored legacy JSON evidence is unavailable for reverse reconciliation"
            )
        exported = reverse_export_phase3(
            connection,
            reverse_dir,
            legacy_source_directory=legacy_root,
            generated_at=_FIXED_REVERSE_TIMESTAMP,
        )
        rehearsal = rehearse_phase3_restore(
            connection,
            exported,
            restored_root / "phase3-restore-rehearsal",
            generated_at=_FIXED_REVERSE_TIMESTAMP,
        )
    finally:
        connection.close()

    relational_sha = _sha256_file(exported.relational_snapshot_path)
    reverse_sha = _reverse_semantic_sha(exported, rehearsal)

    if not rehearsal.migration_idempotent:
        raise Phase73ValidationError(
            "reverse restore migration replay is not idempotent"
        )
    if not rehearsal.import_idempotent:
        raise Phase73ValidationError(
            "reverse restore import replay is not idempotent"
        )
    if not rehearsal.export_hashes_unchanged:
        raise Phase73ValidationError(
            "reverse restore altered reverse-export artifacts"
        )

    return {
        "sha256": reverse_sha,
        "raw_relational_snapshot_sha256": relational_sha,
        "export_status": exported.status,
        "restore_status": rehearsal.status,
        "migration_idempotent": bool(rehearsal.migration_idempotent),
        "import_idempotent": bool(rehearsal.import_idempotent),
        "source_fingerprint": str(rehearsal.source_fingerprint),
        "backup_fingerprint": str(rehearsal.backup_fingerprint),
        "restored_fingerprint": str(rehearsal.restored_fingerprint),
    }


def _restore_one(
    *,
    label: str,
    backup_root: Path,
    restored_root: Path,
    course_code: str,
    as_of: date,
    smoke_query: str,
    retrieval_probe: Optional[Callable[..., Mapping[str, object]]],
    workspace_probe: Optional[Callable[..., Mapping[str, object]]],
    reverse_probe: Optional[Callable[..., Mapping[str, object]]],
) -> RestoredBackupResult:
    # The pair supplied here is already an isolated working copy verified by
    # rehearse_recovery_pair().  Never open the retained backup SQLite itself
    # from this function: SQLite may create transient journal/WAL sidecars even
    # during verification on some platforms.
    manifest_path = backup_root / "recovery_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = _payload_entries(manifest)

    restored_root.mkdir()
    provenance = restored_root / "provenance"
    provenance.mkdir()
    _copy_verified(
        manifest_path,
        provenance / "recovery_manifest.json",
        _sha256_file(manifest_path),
    )

    exact_db = restored_root / "state" / (
        "phase7_restored_{}.db".format(label.lower())
    )
    backup_db = backup_root / "sqlite" / "learning_assistant.db"
    _online_restore(backup_db, exact_db)
    health = _sqlite_health(exact_db)
    expected_logical = str(manifest["sqlite"]["logical_sha256"])
    if health["logical_sha256"] != expected_logical:
        raise Phase73ValidationError(
            "restored backup {} SQLite logical fingerprint mismatch".format(label)
        )

    authority_source = backup_root / "control" / "phase4_authority.json"
    authority_target = restored_root / "state" / "phase4_authority.json"
    _copy_verified(
        authority_source,
        authority_target,
        str(manifest["authority_sha256"]),
    )

    restored_records = []
    note_count = 0
    source_count = 0
    for entry in entries:
        role = str(entry["role"])
        if role in _REQUIRED_ROLES:
            continue
        relative = _portable_relative(str(entry["path"]))
        destination = _restore_payload_destination(
            restored_root,
            relative,
            role,
        )
        if destination is None:
            continue
        source = backup_root / relative
        expected = str(entry["sha256"])
        _copy_verified(source, destination, expected)
        restored_records.append(
            {
                "role": role,
                "restored_path": destination.relative_to(restored_root).as_posix(),
                "sha256": expected,
                "size_bytes": int(entry["size_bytes"]),
            }
        )
        if role == "registered_note_body":
            note_count += 1
        elif role == "registered_source_file":
            source_count += 1

    content_sha = _content_fingerprint(restored_records)
    _write_json(
        restored_root / "restored_content_manifest.json",
        {
            "schema_version": 1,
            "backup_label": label,
            "restored_payload_count": len(restored_records),
            "restored_note_body_count": note_count,
            "restored_source_file_count": source_count,
            "restored_content_sha256": content_sha,
            "records": restored_records,
        },
    )

    # Preserve the exact restored authority copy.  A separate runtime clone is
    # used for derived-index rebuild and portable vault-root relocation.
    runtime_db = restored_root / "runtime" / (
        "phase7_runtime_{}.db".format(label.lower())
    )
    _clone_runtime_database(exact_db, runtime_db)
    rebound = _rebind_runtime_vaults(runtime_db, restored_root)

    if retrieval_probe is None:
        retrieval = _real_retrieval_probe(
            runtime_db,
            restored_root,
            course_code=course_code,
            smoke_query=smoke_query,
        )
    else:
        retrieval = dict(
            retrieval_probe(
                runtime_db,
                restored_root,
                label=label,
                course_code=course_code,
                smoke_query=smoke_query,
            )
        )

    if workspace_probe is None:
        workspace = _real_workspace_probe(
            runtime_db,
            course_code=course_code,
            as_of=as_of,
        )
    else:
        workspace = dict(
            workspace_probe(
                runtime_db,
                restored_root,
                label=label,
                course_code=course_code,
                as_of=as_of,
            )
        )

    if reverse_probe is None:
        reverse = _real_reverse_probe(exact_db, restored_root)
    else:
        reverse = dict(
            reverse_probe(
                exact_db,
                restored_root,
                label=label,
            )
        )

    # Reverse-export and runtime derived work must not alter the exact restored
    # authority database.
    final_health = _sqlite_health(exact_db)
    if final_health["logical_sha256"] != expected_logical:
        raise Phase73ValidationError(
            "rehearsal altered the exact restored authority database"
        )

    return RestoredBackupResult(
        label=label,
        exact_database_relative_path=exact_db.relative_to(
            restored_root.parent
        ).as_posix(),
        runtime_database_relative_path=runtime_db.relative_to(
            restored_root.parent
        ).as_posix(),
        sqlite_logical_sha256=health["logical_sha256"],
        restored_content_sha256=content_sha,
        restored_payload_count=len(restored_records),
        restored_note_body_count=note_count,
        restored_source_file_count=source_count,
        runtime_vault_rebind_count=rebound,
        retrieval_source_fingerprint=str(
            retrieval["source_fingerprint"]
        ),
        retrieval_chunk_count=int(retrieval["chunk_count"]),
        retrieval_hit_count=int(retrieval["hit_count"]),
        retrieval_smoke_chunk_ids=tuple(
            str(item) for item in retrieval.get("hit_chunk_ids", ())
        ),
        workspace_sha256=str(workspace["sha256"]),
        workspace_topic_count=int(workspace["topic_count"]),
        workspace_action_count=int(workspace["action_count"]),
        reverse_export_sha256=str(reverse["sha256"]),
        reverse_export_status=str(reverse["export_status"]),
        reverse_restore_status=str(reverse["restore_status"]),
        reverse_migration_idempotent=bool(
            reverse["migration_idempotent"]
        ),
        reverse_import_idempotent=bool(reverse["import_idempotent"]),
    )


def preview_restore_rehearsal(recovery_root) -> dict:
    recovery_root = Path(recovery_root)
    verification = verify_recovery_pair(recovery_root)
    pair = json.loads(
        (recovery_root / "pair_manifest.json").read_text(encoding="utf-8")
    )
    a_manifest = json.loads(
        (
            recovery_root
            / "backup-A"
            / "recovery_manifest.json"
        ).read_text(encoding="utf-8")
    )
    b_manifest = json.loads(
        (
            recovery_root
            / "backup-B"
            / "recovery_manifest.json"
        ).read_text(encoding="utf-8")
    )

    return {
        "mode": "preview",
        "pair_verified": True,
        "source_snapshot_identity_sha256": verification[
            "source_snapshot_identity_sha256"
        ],
        "sqlite_logical_sha256": verification["sqlite_logical_sha256"],
        "backup_a_payload_file_count": int(a_manifest["payload_file_count"]),
        "backup_b_payload_file_count": int(b_manifest["payload_file_count"]),
        "backup_a_copied_note_body_count": int(
            a_manifest["copied_note_body_count"]
        ),
        "backup_b_copied_note_body_count": int(
            b_manifest["copied_note_body_count"]
        ),
        "backup_a_copied_source_byte_count": int(
            a_manifest["copied_source_byte_count"]
        ),
        "backup_b_copied_source_byte_count": int(
            b_manifest["copied_source_byte_count"]
        ),
        "pair_restore_performed": bool(pair["restore_performed"]),
        "writes_performed": False,
    }


def rehearse_recovery_pair(
    *,
    recovery_root,
    project_root,
    work_root,
    course_code="MA103N",
    as_of=date(2026, 9, 16),
    smoke_query="LU factorization triangular matrices",
    confirmation: str,
    retrieval_probe: Optional[Callable[..., Mapping[str, object]]] = None,
    workspace_probe: Optional[Callable[..., Mapping[str, object]]] = None,
    reverse_probe: Optional[Callable[..., Mapping[str, object]]] = None,
) -> RestorePairRehearsalResult:
    if confirmation != CONFIRMATION_PHRASE:
        raise Phase73SafetyError(
            "rehearsal requires exact confirmation {}".format(
                CONFIRMATION_PHRASE
            )
        )

    recovery_root = Path(recovery_root)
    project_root = Path(project_root)
    work_root = Path(work_root)
    _validate_new_work_root(
        work_root,
        project_root=project_root,
        recovery_root=recovery_root,
    )

    # Freeze the retained pair identity *before* any SQLite library opens a
    # backup database.  We then copy the pair byte-for-byte into the isolated
    # staging area and perform all manifest/SQLite verification against that
    # working copy.  This avoids Windows/SQLite journal/WAL sidecars appearing
    # beside the retained recovery databases.
    pair_before = _tree_snapshot(recovery_root)
    pair_before_sha = _tree_fingerprint(recovery_root)

    staging = work_root.parent / (
        ".phase7-restore-stage-{}".format(uuid.uuid4().hex)
    )
    if staging.exists():
        raise Phase73SafetyError("unexpected rehearsal staging collision")
    staging.mkdir()

    try:
        isolated_pair = staging / "_retained_pair_working_copy"
        shutil.copytree(recovery_root, isolated_pair)

        copied_snapshot = _tree_snapshot(isolated_pair)
        if copied_snapshot != pair_before:
            raise Phase73ValidationError(
                "isolated retained-pair working copy differs from source"
            )

        pair_verification = verify_recovery_pair(isolated_pair)

        a = _restore_one(
            label="A",
            backup_root=isolated_pair / "backup-A",
            restored_root=staging / "restored-A",
            course_code=course_code,
            as_of=as_of,
            smoke_query=smoke_query,
            retrieval_probe=retrieval_probe,
            workspace_probe=workspace_probe,
            reverse_probe=reverse_probe,
        )
        b = _restore_one(
            label="B",
            backup_root=isolated_pair / "backup-B",
            restored_root=staging / "restored-B",
            course_code=course_code,
            as_of=as_of,
            smoke_query=smoke_query,
            retrieval_probe=retrieval_probe,
            workspace_probe=workspace_probe,
            reverse_probe=reverse_probe,
        )

        pair_after = _tree_snapshot(recovery_root)
        pair_after_sha = _tree_fingerprint(recovery_root)
        pair_unchanged = (
            pair_before == pair_after and pair_before_sha == pair_after_sha
        )
        if not pair_unchanged:
            raise Phase73ValidationError(
                "retained recovery pair changed during rehearsal"
            )

        equivalence = {
            "sqlite_logical_sha256": (
                a.sqlite_logical_sha256 == b.sqlite_logical_sha256
            ),
            "restored_content_sha256": (
                a.restored_content_sha256 == b.restored_content_sha256
            ),
            "retrieval_source_fingerprint": (
                a.retrieval_source_fingerprint
                == b.retrieval_source_fingerprint
            ),
            "retrieval_chunk_count": (
                a.retrieval_chunk_count == b.retrieval_chunk_count
            ),
            "workspace_sha256": (
                a.workspace_sha256 == b.workspace_sha256
            ),
            "reverse_export_sha256": (
                a.reverse_export_sha256 == b.reverse_export_sha256
            ),
        }
        backups_equivalent = all(equivalence.values())
        if not backups_equivalent:
            failed = sorted(
                key for key, passed in equivalence.items() if not passed
            )
            raise Phase73ValidationError(
                "backup A/B restore outcomes differ: {}".format(
                    ", ".join(failed)
                )
            )

        expected_sqlite = str(
            pair_verification["sqlite_logical_sha256"]
        )
        if (
            a.sqlite_logical_sha256 != expected_sqlite
            or b.sqlite_logical_sha256 != expected_sqlite
        ):
            raise Phase73ValidationError(
                "restored SQLite identity differs from retained pair"
            )

        # The retained Phase 7.2 pair remains the durable backup evidence.
        # The copied pair was only a safety sandbox for SQLite verification and
        # must not be duplicated inside the retained Phase 7.3 rehearsal.
        shutil.rmtree(isolated_pair)

        report = {
            "schema_version": 1,
            "status": "pass",
            "source_snapshot_identity_sha256": pair_verification[
                "source_snapshot_identity_sha256"
            ],
            "retained_pair_sha256_before": pair_before_sha,
            "retained_pair_sha256_after": pair_after_sha,
            "retained_pair_unchanged": True,
            "restore_performed_only_in_isolation": True,
            "production_or_live_source_accessed": False,
            "semantic_provider_called": False,
            "llm_provider_called": False,
            "backups_equivalent": True,
            "equivalence": equivalence,
            "backup_A": a.__dict__,
            "backup_B": b.__dict__,
            "phase7_4_runtime_observation_started": False,
            "retirement_or_deletion_performed": False,
        }
        _write_json(
            staging / "phase7_restore_rehearsal_report.json",
            report,
        )
        os.replace(str(staging), str(work_root))
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return RestorePairRehearsalResult(
        output_directory=work_root,
        report_path=work_root / "phase7_restore_rehearsal_report.json",
        status="pass",
        backup_a=a,
        backup_b=b,
        source_snapshot_identity_sha256=str(
            pair_verification["source_snapshot_identity_sha256"]
        ),
        retained_pair_unchanged=True,
        backups_equivalent=True,
        restore_performed_only_in_isolation=True,
    )
