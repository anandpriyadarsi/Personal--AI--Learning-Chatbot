"""Phase 7.2 Recovery Bundle + Two Verified Backups.

The recovery builder is intentionally conservative:

* production/source state is read only;
* SQLite is copied with the online backup API;
* two bundles are created independently from the same stable source snapshot;
* every copied payload is SHA-256 verified;
* SQLite integrity/FK/logical fingerprints are verified independently;
* registered vault/source paths are represented even when external bytes are
  unavailable;
* secret-sensitive generic source paths are never copied;
* rebuildable retrieval indexes, caches, virtual environments and credentials
  are never included;
* no restore is performed here.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlparse

from personal_learning_assistant.migration.authority_promotion import (
    BACKEND_SQLITE,
    read_authority_control,
)
from personal_learning_assistant.phase7.runtime_inventory import build_inventory


class RecoveryBundleError(RuntimeError):
    pass


class RecoveryOutputError(RecoveryBundleError):
    pass


class RecoveryVerificationError(RecoveryBundleError):
    pass


CONFIRMATION_PHRASE = "CREATE_PHASE7_TWO_VERIFIED_BACKUPS"

SAFE_LEGACY_JSON = (
    "courses.json",
    "assessments.json",
    "assessment_workspace.json",
    "learning_memory.json",
    "course_progress_history.json",
    "weekly_study_plans.json",
    "multi_course_weekly_plans.json",
    "intelligent_study_plans.json",
    "semester_grade_config.json",
    "notes.json",
    "resources.json",
    "obsidian_config.json",
)

FORBIDDEN_PAYLOAD_PARTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".phase5_retrieval",
    "node_modules",
}
FORBIDDEN_FILE_NAMES = {
    ".env",
    "credentials",
    "credentials.json",
    "credential.json",
    "secrets.json",
    "secret.json",
    "id_rsa",
    "id_ed25519",
}
FORBIDDEN_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
}
SENSITIVE_NAME_MARKERS = (
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "private_key",
    "client_secret",
)


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(value) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _sqlite_uri(path: Path, mode: str = "ro") -> str:
    text = str(path.resolve(strict=False)).replace("\\", "/")
    from urllib.parse import quote

    return "file:{}?mode={}".format(quote(text, safe="/:"), mode)


def _open_ro(path: Path) -> sqlite3.Connection:
    if not path.is_file() or path.is_symlink():
        raise RecoveryBundleError(
            "SQLite database is missing or not a regular file: {}".format(path)
        )
    connection = sqlite3.connect(
        _sqlite_uri(path, "ro"),
        uri=True,
        isolation_level=None,
        timeout=5.0,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def _normalize_sqlite_value(value):
    if isinstance(value, bytes):
        return {"__bytes_hex__": value.hex()}
    if isinstance(value, float):
        # JSON's repr is deterministic for a fixed Python runtime/value.
        return {"__float__": repr(value)}
    return value


def logical_sqlite_fingerprint(connection: sqlite3.Connection) -> str:
    """Hash logical schema + sorted table rows, independent of DB file layout."""
    digest = hashlib.sha256()
    table_rows = connection.execute(
        "SELECT name,sql FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()

    for table_row in table_rows:
        name = str(table_row["name"])
        sql = str(table_row["sql"] or "")
        digest.update(
            _canonical_json_bytes(
                {"table": name, "schema_sql": sql}
            )
        )
        digest.update(b"\n")

        quoted = '"' + name.replace('"', '""') + '"'
        columns = connection.execute(
            "PRAGMA table_info({})".format(quoted)
        ).fetchall()
        column_names = tuple(str(row["name"]) for row in columns)
        digest.update(
            _canonical_json_bytes(
                {"columns": column_names}
            )
        )
        digest.update(b"\n")

        rows = []
        for row in connection.execute(
            "SELECT * FROM {}".format(quoted)
        ).fetchall():
            values = [
                _normalize_sqlite_value(row[column])
                for column in column_names
            ]
            rows.append(_canonical_json_bytes(values))
        for encoded in sorted(rows):
            digest.update(encoded)
            digest.update(b"\n")
    return digest.hexdigest()


def _sqlite_health(connection: sqlite3.Connection) -> dict:
    integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
    foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    if integrity != "ok":
        raise RecoveryVerificationError(
            "SQLite integrity_check returned {!r}".format(integrity)
        )
    if foreign_keys:
        raise RecoveryVerificationError(
            "SQLite foreign_key_check returned {} row(s)".format(
                len(foreign_keys)
            )
        )
    versions = tuple(
        int(row[0])
        for row in connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
    )
    if len(versions) < 4 or versions[:4] != (1, 2, 3, 4):
        raise RecoveryVerificationError(
            "recovery requires intact migration prefix (1,2,3,4); found {}".format(
                versions
            )
        )
    return {
        "integrity_check": integrity,
        "foreign_key_violation_count": 0,
        "migration_versions": versions,
        "logical_sha256": logical_sqlite_fingerprint(connection),
    }


def _safe_public_uri(value) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme.lower() in {"http", "https"}:
        # Preserve public provenance without query/fragment material that may
        # contain temporary access tokens or tracking secrets.
        return parsed._replace(params="", query="", fragment="").geturl()
    return None


def _portable_parts(relative: str) -> Tuple[str, ...]:
    path = Path(str(relative).replace("\\", "/"))
    if path.is_absolute():
        raise RecoveryBundleError("absolute registered path is not portable")
    parts = tuple(part for part in path.parts if part not in ("", "."))
    if any(part == ".." for part in parts):
        raise RecoveryBundleError("registered path attempts parent traversal")
    return parts


def _is_sensitive_generic_path(parts: Sequence[str]) -> bool:
    lowered = [str(part).casefold() for part in parts]
    for part in lowered:
        if part in FORBIDDEN_PAYLOAD_PARTS:
            return True
        if part in FORBIDDEN_FILE_NAMES:
            return True
        if part.startswith(".env."):
            return True
        if any(marker in part for marker in SENSITIVE_NAME_MARKERS):
            return True
    if lowered:
        suffix = Path(lowered[-1]).suffix.casefold()
        if suffix in FORBIDDEN_SUFFIXES:
            return True
    return False


def _assert_no_symlink_traversal(root: Path, relative_parts: Sequence[str]) -> Path:
    if root.is_symlink():
        raise RecoveryBundleError(
            "registered root must not be a symlink: {}".format(root)
        )
    candidate = root
    for part in relative_parts:
        candidate = candidate / part
        if candidate.exists() and candidate.is_symlink():
            raise RecoveryBundleError(
                "registered path traverses a symlink"
            )
    root_abs = Path(os.path.abspath(os.fspath(root)))
    candidate_abs = Path(os.path.abspath(os.fspath(candidate)))
    try:
        common = Path(os.path.commonpath((str(root_abs), str(candidate_abs))))
    except ValueError as error:
        raise RecoveryBundleError("registered path escaped its root") from error
    if common != root_abs:
        raise RecoveryBundleError("registered path escaped its root")
    return candidate_abs


def _parse_path_key(path_key: str):
    text = str(path_key or "").replace("\\", "/").strip("/")
    if not text or "/" not in text:
        return None, ()
    root_key, relative = text.split("/", 1)
    if not root_key:
        return None, ()
    return root_key, _portable_parts(relative)


def _copy_verified(
    source: Path,
    destination: Path,
    *,
    expected_sha256: Optional[str] = None,
) -> dict:
    if source.is_symlink() or not source.is_file():
        raise RecoveryBundleError(
            "copy source is missing/not regular: {}".format(source)
        )
    before = _sha256_file(source)
    if expected_sha256 is not None and before != expected_sha256:
        raise RecoveryVerificationError(
            "source hash changed before copy: {}".format(source.name)
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    copied = _sha256_file(destination)
    after = _sha256_file(source)
    if before != copied or before != after:
        raise RecoveryVerificationError(
            "source/copy hash mismatch for {}".format(source.name)
        )
    return {
        "sha256": copied,
        "size_bytes": int(destination.stat().st_size),
    }


def _migration_manifest(project_root: Path, connection: sqlite3.Connection) -> dict:
    applied = [
        {
            "version": int(row["version"]),
            "name": str(row["name"]),
            "checksum": str(row["checksum"]),
            "applied_at": str(row["applied_at"]),
        }
        for row in connection.execute(
            "SELECT version,name,checksum,applied_at "
            "FROM schema_migrations ORDER BY version"
        ).fetchall()
    ]
    files = []
    migration_dir = (
        project_root
        / "personal_learning_assistant"
        / "repositories"
        / "sqlite"
        / "migrations"
    )
    if migration_dir.is_dir():
        for path in sorted(migration_dir.glob("[0-9][0-9][0-9][0-9]_*.sql")):
            files.append(
                {
                    "name": path.name,
                    "sha256": _sha256_file(path),
                    "size_bytes": int(path.stat().st_size),
                }
            )
    return {
        "applied": applied,
        "migration_files": files,
    }


def _legacy_snapshot(project_root: Path) -> Tuple[dict, ...]:
    data_dir = project_root / "data"
    result = []
    for name in SAFE_LEGACY_JSON:
        path = data_dir / name
        if path.is_symlink():
            raise RecoveryBundleError(
                "legacy evidence must not be a symlink: {}".format(name)
            )
        if path.is_file():
            result.append(
                {
                    "name": name,
                    "sha256": _sha256_file(path),
                    "size_bytes": int(path.stat().st_size),
                }
            )
    return tuple(result)


def _vault_snapshot(connection: sqlite3.Connection) -> Tuple[dict, ...]:
    rows = connection.execute(
        "SELECT n.id,n.vault_id,n.relative_path,n.path_key,n.title,"
        "n.source_hash,n.file_mtime_ns,n.archived_at,n.trashed_at,"
        "v.name AS vault_name,v.path_key AS vault_path_key,v.root_path,v.enabled "
        "FROM note_metadata n "
        "JOIN vaults v ON v.id=n.vault_id "
        "ORDER BY v.id,n.path_key,n.id"
    ).fetchall()
    result = []
    for row in rows:
        relative_parts = _portable_parts(str(row["relative_path"]))
        root = Path(str(row["root_path"]))
        status = "external_unavailable"
        actual_hash = None
        size_bytes = None
        source_path = None
        try:
            if root.is_dir() and not root.is_symlink():
                candidate = _assert_no_symlink_traversal(root, relative_parts)
                if candidate.is_file() and not candidate.is_symlink():
                    source_path = candidate
                    actual_hash = _sha256_file(candidate)
                    size_bytes = int(candidate.stat().st_size)
                    status = "available"
                else:
                    status = "missing_registered_file"
            else:
                status = "vault_root_unavailable"
        except (OSError, RecoveryBundleError):
            status = "unsafe_or_unavailable"

        active = row["archived_at"] is None and row["trashed_at"] is None
        result.append(
            {
                "note_id": str(row["id"]),
                "vault_id": str(row["vault_id"]),
                "vault_name": str(row["vault_name"]),
                "vault_path_key": str(row["vault_path_key"]),
                "vault_enabled": bool(row["enabled"]),
                "relative_path": "/".join(relative_parts),
                "path_key": str(row["path_key"]),
                "title": str(row["title"]),
                "active": active,
                "registered_source_hash": str(row["source_hash"]),
                "actual_sha256": actual_hash,
                "registry_hash_match": (
                    None if actual_hash is None else actual_hash == str(row["source_hash"])
                ),
                "size_bytes": size_bytes,
                "status": status,
                "_source_path": source_path,
            }
        )
    return tuple(result)


def _source_snapshot(
    connection: sqlite3.Connection,
    source_roots: Mapping[str, Path],
) -> Tuple[dict, ...]:
    rows = connection.execute(
        "SELECT id,kind,canonical_uri,path_key,mime_type,content_hash,"
        "size_bytes,source_timestamp,extraction_status,extraction_version "
        "FROM knowledge_documents ORDER BY id"
    ).fetchall()
    result = []
    for row in rows:
        path_key = str(row["path_key"] or "")
        root_key, relative_parts = _parse_path_key(path_key)
        source_path = None
        actual_hash = None
        actual_size = None
        status = "external_reference"
        excluded_reason = None

        if root_key and relative_parts:
            if _is_sensitive_generic_path((root_key,) + relative_parts):
                status = "secret_sensitive_excluded"
                excluded_reason = "path matches secret-sensitive exclusion policy"
            elif root_key in source_roots:
                root = Path(source_roots[root_key])
                try:
                    if root.is_dir() and not root.is_symlink():
                        candidate = _assert_no_symlink_traversal(root, relative_parts)
                        if candidate.is_file() and not candidate.is_symlink():
                            actual_hash = _sha256_file(candidate)
                            actual_size = int(candidate.stat().st_size)
                            if actual_hash != str(row["content_hash"]):
                                raise RecoveryVerificationError(
                                    "registered source hash mismatch for {}".format(
                                        path_key
                                    )
                                )
                            source_path = candidate
                            status = "available"
                        else:
                            status = "missing_in_provided_root"
                    else:
                        status = "provided_root_unavailable"
                except OSError:
                    status = "provided_root_unavailable"
            else:
                status = "root_not_provided"

        result.append(
            {
                "document_id": str(row["id"]),
                "kind": str(row["kind"]),
                "mime_type": str(row["mime_type"]),
                "path_key": path_key,
                "root_key": root_key,
                "relative_path": (
                    None if not relative_parts else "/".join(relative_parts)
                ),
                "public_canonical_uri": _safe_public_uri(row["canonical_uri"]),
                "has_canonical_uri": bool(str(row["canonical_uri"] or "").strip()),
                "registered_content_hash": str(row["content_hash"]),
                "registered_size_bytes": (
                    None if row["size_bytes"] is None else int(row["size_bytes"])
                ),
                "source_timestamp": row["source_timestamp"],
                "extraction_status": str(row["extraction_status"]),
                "extraction_version": str(row["extraction_version"]),
                "actual_sha256": actual_hash,
                "actual_size_bytes": actual_size,
                "status": status,
                "excluded_reason": excluded_reason,
                "_source_path": source_path,
            }
        )
    return tuple(result)


def _strip_internal(rows: Iterable[dict]) -> Tuple[dict, ...]:
    return tuple(
        {
            key: value
            for key, value in row.items()
            if not key.startswith("_")
        }
        for row in rows
    )


def _snapshot_identity(
    *,
    sqlite_logical_sha256: str,
    authority_sha256: str,
    migration_manifest: dict,
    legacy_rows: Sequence[dict],
    vault_rows: Sequence[dict],
    source_rows: Sequence[dict],
    runtime_inventory: dict,
    git_identity: Mapping[str, str],
) -> str:
    identity = {
        "sqlite_logical_sha256": sqlite_logical_sha256,
        "authority_sha256": authority_sha256,
        "migrations": migration_manifest,
        "legacy": tuple(
            (row["name"], row["sha256"], row["size_bytes"])
            for row in legacy_rows
        ),
        "vaults": tuple(
            (
                row["note_id"],
                row["vault_id"],
                row["relative_path"],
                row["registered_source_hash"],
                row["actual_sha256"],
                row["status"],
            )
            for row in vault_rows
        ),
        "sources": tuple(
            (
                row["document_id"],
                row["path_key"],
                row["registered_content_hash"],
                row["actual_sha256"],
                row["status"],
                row["public_canonical_uri"],
            )
            for row in source_rows
        ),
        "runtime_inventory_sha256": runtime_inventory["inventory_sha256"],
        "git": dict(git_identity),
    }
    return _sha256_bytes(_canonical_json_bytes(identity))


def _capture_snapshot(
    *,
    project_root: Path,
    database_path: Path,
    authority_path: Path,
    source_roots: Mapping[str, Path],
    git_identity: Mapping[str, str],
) -> dict:
    authority_state = read_authority_control(authority_path)
    if (
        authority_state.storage_backend != BACKEND_SQLITE
        or not authority_state.legacy_writes_blocked
    ):
        raise RecoveryBundleError(
            "Phase 7 recovery requires locked SQLite authority"
        )
    authority_sha = _sha256_file(authority_path)

    connection = _open_ro(database_path)
    try:
        health = _sqlite_health(connection)
        migrations = _migration_manifest(project_root, connection)
        vault_rows = _vault_snapshot(connection)
        source_rows = _source_snapshot(connection, source_roots)
    finally:
        connection.close()

    legacy_rows = _legacy_snapshot(project_root)
    runtime_inventory = build_inventory(project_root)
    identity = _snapshot_identity(
        sqlite_logical_sha256=health["logical_sha256"],
        authority_sha256=authority_sha,
        migration_manifest=migrations,
        legacy_rows=legacy_rows,
        vault_rows=_strip_internal(vault_rows),
        source_rows=_strip_internal(source_rows),
        runtime_inventory=runtime_inventory,
        git_identity=git_identity,
    )
    return {
        "sqlite_health": health,
        "authority_sha256": authority_sha,
        "authority_state": {
            "storage_backend": authority_state.storage_backend,
            "legacy_writes_blocked": bool(authority_state.legacy_writes_blocked),
            "cutover_id": str(authority_state.cutover_id),
            "promoted_at": str(authority_state.promoted_at),
        },
        "migrations": migrations,
        "legacy": legacy_rows,
        "vaults": vault_rows,
        "sources": source_rows,
        "runtime_inventory": runtime_inventory,
        "git": dict(git_identity),
        "source_snapshot_identity_sha256": identity,
    }


def preview_recovery(
    *,
    project_root,
    database_path,
    authority_path,
    source_roots: Optional[Mapping[str, Path]] = None,
    git_identity: Optional[Mapping[str, str]] = None,
) -> dict:
    project_root = Path(project_root).resolve()
    source_roots = {
        str(key).strip().lower(): Path(value)
        for key, value in dict(source_roots or {}).items()
    }
    snapshot = _capture_snapshot(
        project_root=project_root,
        database_path=Path(database_path),
        authority_path=Path(authority_path),
        source_roots=source_roots,
        git_identity=dict(git_identity or {}),
    )

    source_rows = snapshot["sources"]
    required_keys = sorted(
        {
            row["root_key"]
            for row in source_rows
            if row["root_key"]
        }
    )
    return {
        "mode": "preview",
        "source_snapshot_identity_sha256": snapshot[
            "source_snapshot_identity_sha256"
        ],
        "sqlite_logical_sha256": snapshot["sqlite_health"]["logical_sha256"],
        "migration_versions": snapshot["sqlite_health"]["migration_versions"],
        "authority": snapshot["authority_state"],
        "legacy_json_file_count": len(snapshot["legacy"]),
        "registered_note_count": len(snapshot["vaults"]),
        "available_note_body_count": sum(
            1 for row in snapshot["vaults"] if row["status"] == "available"
        ),
        "unavailable_note_body_count": sum(
            1 for row in snapshot["vaults"] if row["status"] != "available"
        ),
        "registered_source_document_count": len(source_rows),
        "available_source_byte_count": sum(
            1 for row in source_rows if row["status"] == "available"
        ),
        "external_or_unavailable_source_count": sum(
            1 for row in source_rows if row["status"] != "available"
        ),
        "secret_sensitive_source_exclusion_count": sum(
            1
            for row in source_rows
            if row["status"] == "secret_sensitive_excluded"
        ),
        "required_source_root_keys": required_keys,
        "provided_source_root_keys": sorted(source_roots),
        "runtime_inventory_sha256": snapshot["runtime_inventory"][
            "inventory_sha256"
        ],
        "writes_performed": False,
        "restore_performed": False,
    }


def _payload_record(bundle_root: Path, path: Path, role: str) -> dict:
    return {
        "path": path.relative_to(bundle_root).as_posix(),
        "role": role,
        "sha256": _sha256_file(path),
        "size_bytes": int(path.stat().st_size),
    }


def _backup_sqlite(source_path: Path, destination: Path) -> dict:
    source = _open_ro(source_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    target = sqlite3.connect(str(destination), isolation_level=None)
    target.row_factory = sqlite3.Row
    try:
        source.backup(target)
        target.execute("PRAGMA foreign_keys=ON")
        health = _sqlite_health(target)
    finally:
        target.close()
        source.close()
    return health


def _create_one_bundle(
    *,
    label: str,
    bundle_root: Path,
    project_root: Path,
    database_path: Path,
    authority_path: Path,
    snapshot: dict,
) -> dict:
    if bundle_root.exists():
        raise RecoveryOutputError(
            "backup directory already exists: {}".format(bundle_root.name)
        )
    bundle_root.mkdir(parents=True)
    payload = []

    db_out = bundle_root / "sqlite" / "learning_assistant.db"
    db_health = _backup_sqlite(database_path, db_out)
    if db_health["logical_sha256"] != snapshot["sqlite_health"]["logical_sha256"]:
        raise RecoveryVerificationError(
            "online SQLite backup logical fingerprint differs from source"
        )
    payload.append(_payload_record(bundle_root, db_out, "sqlite_authority"))

    authority_out = bundle_root / "control" / "phase4_authority.json"
    _copy_verified(
        authority_path,
        authority_out,
        expected_sha256=snapshot["authority_sha256"],
    )
    payload.append(
        _payload_record(bundle_root, authority_out, "authority_control")
    )

    for row in snapshot["legacy"]:
        src = project_root / "data" / row["name"]
        out = bundle_root / "legacy_json" / row["name"]
        _copy_verified(src, out, expected_sha256=row["sha256"])
        payload.append(_payload_record(bundle_root, out, "legacy_json_evidence"))

    vault_manifest = []
    for row in snapshot["vaults"]:
        public = {
            key: value
            for key, value in row.items()
            if not key.startswith("_")
        }
        source_path = row.get("_source_path")
        if row["status"] == "available" and source_path is not None:
            out = (
                bundle_root
                / "vaults"
                / row["vault_path_key"]
                / Path(row["relative_path"])
            )
            copied = _copy_verified(
                Path(source_path),
                out,
                expected_sha256=row["actual_sha256"],
            )
            public["backup_path"] = out.relative_to(bundle_root).as_posix()
            public["backup_sha256"] = copied["sha256"]
            payload.append(
                _payload_record(bundle_root, out, "registered_note_body")
            )
        else:
            public["backup_path"] = None
            public["backup_sha256"] = None
        vault_manifest.append(public)

    source_manifest = []
    for row in snapshot["sources"]:
        public = {
            key: value
            for key, value in row.items()
            if not key.startswith("_")
        }
        source_path = row.get("_source_path")
        if row["status"] == "available" and source_path is not None:
            relative = Path(row["relative_path"])
            out = (
                bundle_root
                / "sources"
                / str(row["root_key"])
                / relative
            )
            copied = _copy_verified(
                Path(source_path),
                out,
                expected_sha256=row["actual_sha256"],
            )
            public["backup_path"] = out.relative_to(bundle_root).as_posix()
            public["backup_sha256"] = copied["sha256"]
            payload.append(
                _payload_record(bundle_root, out, "registered_source_file")
            )
        else:
            public["backup_path"] = None
            public["backup_sha256"] = None
        source_manifest.append(public)

    manifests = {
        "migrations.json": snapshot["migrations"],
        "vaults.json": {
            "registered_note_count": len(vault_manifest),
            "copied_note_body_count": sum(
                1 for row in vault_manifest if row["backup_path"]
            ),
            "notes": vault_manifest,
        },
        "sources.json": {
            "registered_document_count": len(source_manifest),
            "copied_source_byte_count": sum(
                1 for row in source_manifest if row["backup_path"]
            ),
            "external_or_unavailable_count": sum(
                1 for row in source_manifest if not row["backup_path"]
            ),
            "documents": source_manifest,
        },
        "runtime_inventory.json": snapshot["runtime_inventory"],
        "git_identity.json": snapshot["git"],
        "exclusions.json": {
            "rebuildable_or_runtime_excluded": sorted(FORBIDDEN_PAYLOAD_PARTS),
            "secret_sensitive_names_excluded": sorted(FORBIDDEN_FILE_NAMES),
            "secret_sensitive_suffixes_excluded": sorted(FORBIDDEN_SUFFIXES),
            "retrieval_policy": (
                ".phase5_retrieval is derived/rebuildable and is never copied"
            ),
            "credential_policy": (
                ".env/credential/token/private-key generic source paths are never copied"
            ),
        },
        "recovery_contract.json": {
            "schema_version": 1,
            "restore_performed": False,
            "phase7_3_required_for_restore_rehearsal": True,
            "structured_authority": "sqlite/learning_assistant.db",
            "authority_control": "control/phase4_authority.json",
            "note_body_policy": (
                "registered note bytes are copied when their registered vault root is available"
            ),
            "source_policy": (
                "registered local source bytes are copied only from explicit source-root mappings; "
                "otherwise provenance/hash references remain in sources.json"
            ),
            "retrieval_policy": (
                "retrieval indexes are omitted and must be rebuilt from authoritative sources/chunks"
            ),
        },
    }
    for name, value in manifests.items():
        path = bundle_root / "manifests" / name
        _write_json(path, value)
        payload.append(
            _payload_record(bundle_root, path, "recovery_metadata")
        )

    payload.sort(key=lambda item: item["path"])
    manifest = {
        "schema_version": 1,
        "backup_label": label,
        "created_at": _utc_now(),
        "source_snapshot_identity_sha256": snapshot[
            "source_snapshot_identity_sha256"
        ],
        "sqlite": {
            "raw_sha256": _sha256_file(db_out),
            "logical_sha256": db_health["logical_sha256"],
            "integrity_check": db_health["integrity_check"],
            "foreign_key_violation_count": db_health[
                "foreign_key_violation_count"
            ],
            "migration_versions": db_health["migration_versions"],
        },
        "authority_sha256": snapshot["authority_sha256"],
        "payload_files": payload,
        "payload_file_count": len(payload),
        "copied_note_body_count": sum(
            1 for row in vault_manifest if row["backup_path"]
        ),
        "unavailable_note_body_count": sum(
            1 for row in vault_manifest if not row["backup_path"]
        ),
        "copied_source_byte_count": sum(
            1 for row in source_manifest if row["backup_path"]
        ),
        "external_or_unavailable_source_count": sum(
            1 for row in source_manifest if not row["backup_path"]
        ),
        "restore_performed": False,
        "verified": False,
    }
    manifest_path = bundle_root / "recovery_manifest.json"
    _write_json(manifest_path, manifest)

    verified = verify_recovery_bundle(bundle_root)
    manifest["verified"] = True
    manifest["verification"] = verified
    _write_json(manifest_path, manifest)

    # Re-read after final manifest rewrite and independently verify again.
    final = verify_recovery_bundle(bundle_root)
    return {
        "label": label,
        "manifest_sha256": _sha256_file(manifest_path),
        "source_snapshot_identity_sha256": snapshot[
            "source_snapshot_identity_sha256"
        ],
        "sqlite_logical_sha256": db_health["logical_sha256"],
        "payload_file_count": len(payload),
        "copied_note_body_count": sum(
            1 for row in vault_manifest if row["backup_path"]
        ),
        "copied_source_byte_count": sum(
            1 for row in source_manifest if row["backup_path"]
        ),
        "external_or_unavailable_source_count": sum(
            1 for row in source_manifest if not row["backup_path"]
        ),
        "verification": final,
    }


def _payload_path_forbidden(rel: str) -> bool:
    parts = Path(rel).parts
    lowered = tuple(str(part).casefold() for part in parts)
    if any(part in FORBIDDEN_PAYLOAD_PARTS for part in lowered):
        return True
    # Secret-name filtering applies to generic registered source bytes.  Vault
    # Markdown is user-authored authoritative content and is intentionally
    # preserved even if a note title happens to contain a sensitive word.
    if lowered and lowered[0] == "sources":
        return _is_sensitive_generic_path(parts[1:])
    return False


def _manifest_payload_map(bundle_root: Path, manifest: dict) -> Dict[str, dict]:
    result = {}
    for entry in manifest.get("payload_files", ()):
        rel = str(entry.get("path", "")).replace("\\", "/")
        if not rel or rel.startswith("/") or ".." in Path(rel).parts:
            raise RecoveryVerificationError(
                "invalid recovery payload path {!r}".format(rel)
            )
        if _payload_path_forbidden(rel):
            raise RecoveryVerificationError(
                "forbidden/sensitive payload path present: {}".format(rel)
            )
        if rel in result:
            raise RecoveryVerificationError(
                "duplicate recovery payload path: {}".format(rel)
            )
        result[rel] = entry
    return result


def verify_recovery_bundle(bundle_root) -> dict:
    bundle_root = Path(bundle_root)
    manifest_path = bundle_root / "recovery_manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise RecoveryVerificationError("recovery_manifest.json is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload_map = _manifest_payload_map(bundle_root, manifest)

    for rel, expected in payload_map.items():
        path = bundle_root / Path(rel)
        if not path.is_file() or path.is_symlink():
            raise RecoveryVerificationError(
                "payload file missing/not regular: {}".format(rel)
            )
        actual = _sha256_file(path)
        if actual != str(expected.get("sha256", "")):
            raise RecoveryVerificationError(
                "payload hash mismatch: {}".format(rel)
            )
        if int(path.stat().st_size) != int(expected.get("size_bytes", -1)):
            raise RecoveryVerificationError(
                "payload size mismatch: {}".format(rel)
            )

    db = bundle_root / "sqlite" / "learning_assistant.db"
    connection = sqlite3.connect(str(db), isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        health = _sqlite_health(connection)
    finally:
        connection.close()

    expected_sqlite = manifest.get("sqlite", {})
    if health["logical_sha256"] != expected_sqlite.get("logical_sha256"):
        raise RecoveryVerificationError(
            "backup SQLite logical fingerprint differs from manifest"
        )
    if _sha256_file(db) != expected_sqlite.get("raw_sha256"):
        raise RecoveryVerificationError(
            "backup SQLite raw hash differs from manifest"
        )

    authority = bundle_root / "control" / "phase4_authority.json"
    if _sha256_file(authority) != manifest.get("authority_sha256"):
        raise RecoveryVerificationError(
            "authority-control backup hash differs from manifest"
        )

    if manifest.get("restore_performed") is not False:
        raise RecoveryVerificationError(
            "Phase 7.2 manifest must state restore_performed=false"
        )

    return {
        "status": "pass",
        "payload_file_count": len(payload_map),
        "sqlite_logical_sha256": health["logical_sha256"],
        "integrity_check": health["integrity_check"],
        "foreign_key_violation_count": 0,
        "migration_versions": health["migration_versions"],
        "restore_performed": False,
    }


def verify_recovery_pair(output_root) -> dict:
    output_root = Path(output_root)
    pair_path = output_root / "pair_manifest.json"
    if not pair_path.is_file() or pair_path.is_symlink():
        raise RecoveryVerificationError("pair_manifest.json is missing")
    pair = json.loads(pair_path.read_text(encoding="utf-8"))

    a_root = output_root / "backup-A"
    b_root = output_root / "backup-B"
    a = verify_recovery_bundle(a_root)
    b = verify_recovery_bundle(b_root)

    a_manifest = json.loads(
        (a_root / "recovery_manifest.json").read_text(encoding="utf-8")
    )
    b_manifest = json.loads(
        (b_root / "recovery_manifest.json").read_text(encoding="utf-8")
    )

    identity_a = a_manifest["source_snapshot_identity_sha256"]
    identity_b = b_manifest["source_snapshot_identity_sha256"]
    if identity_a != identity_b:
        raise RecoveryVerificationError(
            "backup A and B represent different source snapshots"
        )
    if a["sqlite_logical_sha256"] != b["sqlite_logical_sha256"]:
        raise RecoveryVerificationError(
            "backup A and B SQLite logical fingerprints differ"
        )
    if pair.get("source_snapshot_identity_sha256") != identity_a:
        raise RecoveryVerificationError(
            "pair manifest source identity differs from bundle identity"
        )

    for label, root in (("A", a_root), ("B", b_root)):
        expected_hash = pair.get("backups", {}).get(label, {}).get(
            "manifest_sha256"
        )
        actual_hash = _sha256_file(root / "recovery_manifest.json")
        if expected_hash != actual_hash:
            raise RecoveryVerificationError(
                "pair manifest hash mismatch for backup {}".format(label)
            )

    return {
        "status": "pass",
        "backup_a_verified": True,
        "backup_b_verified": True,
        "source_snapshot_identity_sha256": identity_a,
        "sqlite_logical_sha256": a["sqlite_logical_sha256"],
        "restore_performed": False,
    }


def _validate_output_root(
    output_root: Path,
    *,
    project_root: Path,
    external_roots: Sequence[Path],
) -> None:
    if output_root.exists():
        raise RecoveryOutputError(
            "output directory already exists: {}".format(output_root)
        )
    name = output_root.name.casefold()
    if "phase7" not in name or not (
        "recovery" in name or "backup" in name
    ):
        raise RecoveryOutputError(
            "output directory name must clearly identify Phase 7 recovery/backup"
        )

    output_abs = Path(os.path.abspath(os.fspath(output_root)))
    project_abs = Path(os.path.abspath(os.fspath(project_root)))

    try:
        common = Path(os.path.commonpath((str(output_abs), str(project_abs))))
    except ValueError:
        common = None
    if common == project_abs:
        raise RecoveryOutputError(
            "Phase 7 recovery output must be outside the project root"
        )

    current = output_abs.parent
    while True:
        if current.exists() and current.is_symlink():
            raise RecoveryOutputError(
                "recovery output path traverses a symlink"
            )
        if current.parent == current:
            break
        current = current.parent

    for root in external_roots:
        root_abs = Path(os.path.abspath(os.fspath(root)))
        try:
            common = Path(
                os.path.commonpath((str(output_abs), str(root_abs)))
            )
        except ValueError:
            continue
        if common in (output_abs, root_abs):
            raise RecoveryOutputError(
                "recovery output must not overlap a registered source/vault root"
            )


def create_two_verified_backups(
    *,
    project_root,
    database_path,
    authority_path,
    output_root,
    source_roots: Optional[Mapping[str, Path]] = None,
    git_identity: Optional[Mapping[str, str]] = None,
    confirmation: str,
) -> dict:
    if confirmation != CONFIRMATION_PHRASE:
        raise RecoveryBundleError(
            "creation requires exact confirmation {}".format(
                CONFIRMATION_PHRASE
            )
        )

    project_root = Path(project_root).resolve()
    database_path = Path(database_path)
    authority_path = Path(authority_path)
    output_root = Path(output_root)
    source_roots = {
        str(key).strip().lower(): Path(value)
        for key, value in dict(source_roots or {}).items()
    }
    git_identity = dict(git_identity or {})

    # Capture vault roots only for overlap safety.  Absolute roots are never
    # written into recovery manifests.
    connection = _open_ro(database_path)
    try:
        vault_roots = tuple(
            Path(str(row[0]))
            for row in connection.execute(
                "SELECT root_path FROM vaults WHERE enabled=1 ORDER BY id"
            ).fetchall()
        )
    finally:
        connection.close()

    _validate_output_root(
        output_root,
        project_root=project_root,
        external_roots=tuple(source_roots.values()) + vault_roots,
    )

    parent = output_root.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = parent / (
        ".phase7-recovery-stage-{}".format(uuid.uuid4().hex)
    )
    if staging.exists():
        raise RecoveryOutputError("unexpected staging collision")
    staging.mkdir()

    try:
        first = _capture_snapshot(
            project_root=project_root,
            database_path=database_path,
            authority_path=authority_path,
            source_roots=source_roots,
            git_identity=git_identity,
        )
        a = _create_one_bundle(
            label="A",
            bundle_root=staging / "backup-A",
            project_root=project_root,
            database_path=database_path,
            authority_path=authority_path,
            snapshot=first,
        )

        second = _capture_snapshot(
            project_root=project_root,
            database_path=database_path,
            authority_path=authority_path,
            source_roots=source_roots,
            git_identity=git_identity,
        )
        if (
            second["source_snapshot_identity_sha256"]
            != first["source_snapshot_identity_sha256"]
        ):
            raise RecoveryVerificationError(
                "authoritative/source state changed between backup A and backup B"
            )

        b = _create_one_bundle(
            label="B",
            bundle_root=staging / "backup-B",
            project_root=project_root,
            database_path=database_path,
            authority_path=authority_path,
            snapshot=second,
        )

        third = _capture_snapshot(
            project_root=project_root,
            database_path=database_path,
            authority_path=authority_path,
            source_roots=source_roots,
            git_identity=git_identity,
        )
        if (
            third["source_snapshot_identity_sha256"]
            != first["source_snapshot_identity_sha256"]
        ):
            raise RecoveryVerificationError(
                "authoritative/source state changed while creating recovery pair"
            )

        pair_manifest = {
            "schema_version": 1,
            "created_at": _utc_now(),
            "source_snapshot_identity_sha256": first[
                "source_snapshot_identity_sha256"
            ],
            "backups": {
                "A": {
                    "directory": "backup-A",
                    "manifest_sha256": a["manifest_sha256"],
                    "verified": True,
                },
                "B": {
                    "directory": "backup-B",
                    "manifest_sha256": b["manifest_sha256"],
                    "verified": True,
                },
            },
            "independently_created": True,
            "restore_performed": False,
            "phase7_3_restore_rehearsal_required": True,
        }
        _write_json(staging / "pair_manifest.json", pair_manifest)

        verification = verify_recovery_pair(staging)
        pair_manifest["verification"] = verification
        _write_json(staging / "pair_manifest.json", pair_manifest)
        verify_recovery_pair(staging)

        os.replace(str(staging), str(output_root))
        final_verification = verify_recovery_pair(output_root)
        return {
            "status": "pass",
            "output_name": output_root.name,
            "backup_a_verified": True,
            "backup_b_verified": True,
            "source_snapshot_identity_sha256": first[
                "source_snapshot_identity_sha256"
            ],
            "sqlite_logical_sha256": first["sqlite_health"][
                "logical_sha256"
            ],
            "copied_note_body_count": a["copied_note_body_count"],
            "copied_source_byte_count": a["copied_source_byte_count"],
            "external_or_unavailable_source_count": (
                a["external_or_unavailable_source_count"]
            ),
            "restore_performed": False,
            "verification": final_verification,
        }
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
