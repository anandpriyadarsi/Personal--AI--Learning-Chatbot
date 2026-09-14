"""Shared safety helpers for Phase 3 legacy JSON importers.

These helpers keep migration reads deterministic and auditable.  They never
modify a legacy source and they deliberately require an already-scanned source
snapshot so import code cannot silently read an unverified file.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Iterable, Optional, Tuple

from .legacy_source_scanner import LegacySourceSnapshot, STATUS_VALID_JSON


_TARGET_NAMESPACE = uuid.UUID("d4de4c23-d086-4b3f-9d7b-768252b82a71")
_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class LegacyImportError(RuntimeError):
    """Base class for Phase 3 legacy import failures."""


class LegacySourceChangedError(LegacyImportError):
    """Raised when source bytes no longer match the approved scan snapshot."""


class LegacyImportDataError(LegacyImportError, ValueError):
    """Raised when a source shape cannot be imported losslessly/safely."""


@dataclass(frozen=True)
class ImportIssue:
    severity: str
    code: str
    message: str
    legacy_key: str = ""


@dataclass(frozen=True)
class ImportTally:
    created: int = 0
    updated: int = 0
    matched: int = 0

    @property
    def total(self) -> int:
        return self.created + self.updated + self.matched


def _portable_source_path(value: str) -> str:
    raw = str(value).strip().replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]

    path = PurePosixPath(raw)
    if (
        not raw
        or path.is_absolute()
        or re.match(r"^[A-Za-z]:/", raw)
        or raw.startswith("//")
        or ".." in path.parts
    ):
        raise LegacyImportDataError(
            "source path must be a non-empty project-relative path"
        )
    return path.as_posix()


def stable_target_id(
    source_path: str,
    entity_type: str,
    legacy_key: str,
) -> str:
    """Return a stable UUID5 target ID independent of source content hash.

    A changed source hash therefore creates a new ledger observation while the
    same logical legacy entity can update the same SQLite target row.
    """
    portable = _portable_source_path(source_path)
    entity = str(entity_type).strip()
    key = str(legacy_key)
    if not entity or not key:
        raise LegacyImportDataError(
            "entity_type and legacy_key must be non-empty"
        )

    material = "\x1f".join((portable, entity, key))
    return str(uuid.uuid5(_TARGET_NAMESPACE, material))


def source_sha256(snapshot: LegacySourceSnapshot) -> str:
    """Re-read and verify a source without changing it."""
    if snapshot.status != STATUS_VALID_JSON:
        raise LegacyImportDataError(
            "only valid_json snapshots can be imported"
        )

    try:
        raw = snapshot.physical_path.read_bytes()
    except OSError as exc:
        raise LegacySourceChangedError(
            "legacy source can no longer be read: {}".format(
                snapshot.canonical_path
            )
        ) from exc

    digest = hashlib.sha256(raw).hexdigest()
    if digest != snapshot.source_hash or len(raw) != snapshot.byte_count:
        raise LegacySourceChangedError(
            "legacy source changed after scan: {}".format(
                snapshot.canonical_path
            )
        )
    return digest


def load_verified_json(
    snapshot: LegacySourceSnapshot,
    *,
    expected_kind: Optional[str] = None,
) -> Any:
    """Load JSON only after raw bytes still match the scan snapshot."""
    source_sha256(snapshot)
    raw = snapshot.physical_path.read_bytes()

    try:
        value = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LegacySourceChangedError(
            "legacy source no longer decodes as the scanned JSON"
        ) from exc

    if expected_kind == "object" and not isinstance(value, dict):
        raise LegacyImportDataError(
            "{} must contain a top-level JSON object".format(
                snapshot.canonical_path
            )
        )
    if expected_kind == "array" and not isinstance(value, list):
        raise LegacyImportDataError(
            "{} must contain a top-level JSON array".format(
                snapshot.canonical_path
            )
        )
    return value


def ensure_tables(
    connection: sqlite3.Connection,
    table_names: Iterable[str],
) -> None:
    """Fail before import when the expected Phase 3 schema is not applied."""
    missing = []
    for raw_name in table_names:
        name = str(raw_name)
        if not _SQL_IDENTIFIER_RE.fullmatch(name):
            raise LegacyImportDataError(
                "invalid required table name: {}".format(name)
            )
        row = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = ?",
            (name,),
        ).fetchone()
        if row is None:
            missing.append(name)

    if missing:
        raise LegacyImportError(
            "required SQLite tables are missing: {}".format(
                ", ".join(sorted(missing))
            )
        )


def freeze_tally(counter: dict[str, int]) -> ImportTally:
    return ImportTally(
        created=int(counter.get("created", 0)),
        updated=int(counter.get("updated", 0)),
        matched=int(counter.get("matched", 0)),
    )


def add_tally(counter: dict[str, int], disposition: str) -> None:
    if disposition not in {"created", "updated", "matched"}:
        raise LegacyImportDataError(
            "unknown import disposition: {}".format(disposition)
        )
    counter[disposition] = int(counter.get(disposition, 0)) + 1


__all__: Tuple[str, ...] = (
    "ImportIssue",
    "ImportTally",
    "LegacyImportDataError",
    "LegacyImportError",
    "LegacySourceChangedError",
    "add_tally",
    "ensure_tables",
    "freeze_tally",
    "load_verified_json",
    "source_sha256",
    "stable_target_id",
)
