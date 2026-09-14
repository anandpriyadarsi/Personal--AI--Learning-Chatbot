"""Idempotent access to the Phase 3 ``migration_imports`` ledger."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Mapping, Optional, Tuple

from .legacy_source_scanner import LegacySourceSnapshot, STATUS_VALID_JSON


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LEDGER_NAMESPACE = uuid.UUID("6dbe0fd3-4b72-4cee-9f76-b727f9cb2141")


class MigrationImportLedgerError(RuntimeError):
    """Base class for import-ledger failures."""


class MigrationImportValidationError(MigrationImportLedgerError, ValueError):
    """Raised when a ledger identity is malformed or unsafe."""


class MigrationImportConflictError(MigrationImportLedgerError):
    """Raised when one source identity is mapped to two target records."""


@dataclass(frozen=True)
class MigrationImportIdentity:
    source_path: str
    source_hash: str
    source_type: str
    source_version: str
    legacy_key: str
    target_table: str


@dataclass(frozen=True)
class MigrationImportRecord:
    id: str
    identity: MigrationImportIdentity
    target_id: str
    imported_at: str
    details_json: str

    @property
    def details(self) -> Any:
        return json.loads(self.details_json)


@dataclass(frozen=True)
class LedgerWriteResult:
    record: MigrationImportRecord
    created: bool


def _utc_now_text() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _normalize_source_path(value: str) -> str:
    raw = str(value).strip().replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]

    path = PurePosixPath(raw)
    windows_absolute = bool(re.match(r"^[A-Za-z]:/", raw))
    unc_absolute = raw.startswith("//")
    if (
        not raw
        or path.is_absolute()
        or windows_absolute
        or unc_absolute
        or ".." in path.parts
    ):
        raise MigrationImportValidationError(
            "source_path must be a non-empty project-relative path"
        )
    return path.as_posix()


def _validate_hash(value: str) -> str:
    digest = str(value).strip().lower()
    if not _SHA256_RE.fullmatch(digest):
        raise MigrationImportValidationError(
            "source_hash must be a 64-character SHA-256 hex digest"
        )
    return digest


def _nonempty(value: str, field: str) -> str:
    text = str(value).strip()
    if not text:
        raise MigrationImportValidationError("{} must not be empty".format(field))
    return text


def _target_table(value: str) -> str:
    table = _nonempty(value, "target_table")
    if not _SQL_IDENTIFIER_RE.fullmatch(table):
        raise MigrationImportValidationError(
            "target_table must be a simple SQL identifier"
        )
    return table


def _details_json(details: Optional[Mapping[str, Any]]) -> str:
    if details is None:
        return "{}"
    try:
        return json.dumps(
            dict(details),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise MigrationImportValidationError(
            "details must be JSON serializable"
        ) from exc


def build_import_identity(
    *,
    source_path: str,
    source_hash: str,
    source_type: str,
    source_version: str = "",
    legacy_key: str = "",
    target_table: str,
) -> MigrationImportIdentity:
    return MigrationImportIdentity(
        source_path=_normalize_source_path(source_path),
        source_hash=_validate_hash(source_hash),
        source_type=_nonempty(source_type, "source_type"),
        source_version=str(source_version).strip(),
        legacy_key=str(legacy_key),
        target_table=_target_table(target_table),
    )


def _validated_identity(identity: MigrationImportIdentity) -> MigrationImportIdentity:
    return build_import_identity(
        source_path=identity.source_path,
        source_hash=identity.source_hash,
        source_type=identity.source_type,
        source_version=identity.source_version,
        legacy_key=identity.legacy_key,
        target_table=identity.target_table,
    )


def _record_id(identity: MigrationImportIdentity) -> str:
    material = "\x1f".join(
        (
            identity.source_path,
            identity.source_hash,
            identity.source_type,
            identity.source_version,
            identity.legacy_key,
            identity.target_table,
        )
    )
    return str(uuid.uuid5(_LEDGER_NAMESPACE, material))


def _row_to_record(row: sqlite3.Row) -> MigrationImportRecord:
    identity = MigrationImportIdentity(
        source_path=str(row[1]),
        source_hash=str(row[2]),
        source_type=str(row[3]),
        source_version=str(row[4]),
        legacy_key=str(row[5]),
        target_table=str(row[6]),
    )
    return MigrationImportRecord(
        id=str(row[0]),
        identity=identity,
        target_id=str(row[7]),
        imported_at=str(row[8]),
        details_json=str(row[9]),
    )


class MigrationImportLedger:
    """Small transaction-friendly adapter over ``migration_imports``.

    Methods never call ``commit`` or ``rollback``. Importers can therefore place
    target-row creation and ledger recording inside the same explicit SQLite
    transaction. With an autocommit connection, a standalone ledger insert is
    committed by SQLite immediately.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._assert_table_exists()

    def _assert_table_exists(self) -> None:
        row = self._connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'migration_imports'"
        ).fetchone()
        if row is None:
            raise MigrationImportLedgerError(
                "migration_imports does not exist; apply migration 0001 first"
            )

    def find(
        self,
        identity: MigrationImportIdentity,
    ) -> Optional[MigrationImportRecord]:
        identity = _validated_identity(identity)
        row = self._connection.execute(
            "SELECT id, source_path, source_hash, source_type, source_version, "
            "legacy_key, target_table, target_id, imported_at, details_json "
            "FROM migration_imports "
            "WHERE source_path = ? AND source_hash = ? AND source_type = ? "
            "AND source_version = ? AND legacy_key = ? AND target_table = ?",
            (
                identity.source_path,
                identity.source_hash,
                identity.source_type,
                identity.source_version,
                identity.legacy_key,
                identity.target_table,
            ),
        ).fetchone()
        return None if row is None else _row_to_record(row)

    def record_import(
        self,
        identity: MigrationImportIdentity,
        *,
        target_id: str,
        details: Optional[Mapping[str, Any]] = None,
        imported_at: Optional[str] = None,
    ) -> LedgerWriteResult:
        identity = _validated_identity(identity)
        target = _nonempty(target_id, "target_id")
        existing = self.find(identity)

        if existing is not None:
            if existing.target_id != target:
                raise MigrationImportConflictError(
                    "source identity is already mapped to target_id {}"
                    .format(existing.target_id)
                )
            return LedgerWriteResult(record=existing, created=False)

        record = MigrationImportRecord(
            id=_record_id(identity),
            identity=identity,
            target_id=target,
            imported_at=imported_at or _utc_now_text(),
            details_json=_details_json(details),
        )

        try:
            self._connection.execute(
                "INSERT INTO migration_imports "
                "(id, source_path, source_hash, source_type, source_version, "
                "legacy_key, target_table, target_id, imported_at, details_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.id,
                    identity.source_path,
                    identity.source_hash,
                    identity.source_type,
                    identity.source_version,
                    identity.legacy_key,
                    identity.target_table,
                    record.target_id,
                    record.imported_at,
                    record.details_json,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raced = self.find(identity)
            if raced is not None and raced.target_id == target:
                return LedgerWriteResult(record=raced, created=False)
            if raced is not None:
                raise MigrationImportConflictError(
                    "source identity was concurrently mapped to target_id {}"
                    .format(raced.target_id)
                ) from exc
            raise

        return LedgerWriteResult(record=record, created=True)

    def record_snapshot_import(
        self,
        snapshot: LegacySourceSnapshot,
        *,
        legacy_key: str,
        target_table: str,
        target_id: str,
        details: Optional[Mapping[str, Any]] = None,
        imported_at: Optional[str] = None,
    ) -> LedgerWriteResult:
        if snapshot.status != STATUS_VALID_JSON:
            raise MigrationImportValidationError(
                "only valid_json source snapshots can create import mappings"
            )

        identity = build_import_identity(
            source_path=snapshot.canonical_path,
            source_hash=snapshot.source_hash,
            source_type=snapshot.source_type,
            source_version=snapshot.source_version,
            legacy_key=legacy_key,
            target_table=target_table,
        )
        return self.record_import(
            identity,
            target_id=target_id,
            details=details,
            imported_at=imported_at,
        )

    def list_for_source(
        self,
        source_path: str,
        *,
        source_hash: Optional[str] = None,
    ) -> Tuple[MigrationImportRecord, ...]:
        normalized_path = _normalize_source_path(source_path)
        parameters = [normalized_path]
        sql = (
            "SELECT id, source_path, source_hash, source_type, source_version, "
            "legacy_key, target_table, target_id, imported_at, details_json "
            "FROM migration_imports WHERE source_path = ?"
        )
        if source_hash is not None:
            sql += " AND source_hash = ?"
            parameters.append(_validate_hash(source_hash))
        sql += " ORDER BY legacy_key, target_table, target_id"

        rows = self._connection.execute(sql, tuple(parameters)).fetchall()
        return tuple(_row_to_record(row) for row in rows)
