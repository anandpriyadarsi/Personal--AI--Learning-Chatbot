"""SQLite repository for Phase 5.3 Obsidian vault metadata and link graph."""

from __future__ import annotations

import json
import sqlite3
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple

from personal_learning_assistant.domain.obsidian_vault_models import (
    NoteLinkRecord,
    NoteMetadataRecord,
    VaultRecord,
)
from personal_learning_assistant.repositories.sqlite.connection import transaction


class ObsidianVaultRepositoryError(RuntimeError):
    pass


class ObsidianVaultSchemaError(ObsidianVaultRepositoryError):
    pass


class ObsidianVaultConflictError(ObsidianVaultRepositoryError):
    pass


_REQUIRED_COLUMNS = {
    "vaults": {
        "id", "name", "root_path", "path_key", "enabled", "last_scanned_at",
        "created_at", "updated_at",
    },
    "note_metadata": {
        "id", "vault_id", "relative_path", "path_key", "title", "note_type",
        "confidence", "revision_status", "source_hash", "file_mtime_ns",
        "frontmatter_extra_json", "created_at", "updated_at",
    },
    "tags": {"id", "name", "normalized_name", "created_at"},
    "note_tags": {"note_id", "tag_id"},
    "note_links": {
        "id", "source_note_id", "target_note_id", "unresolved_target",
        "source_position", "heading", "block_id", "link_type", "created_at",
    },
}


def _vault(row: sqlite3.Row) -> VaultRecord:
    return VaultRecord(
        id=str(row["id"]),
        name=str(row["name"]),
        root_path=str(row["root_path"]),
        path_key=str(row["path_key"]),
        enabled=bool(row["enabled"]),
        last_scanned_at=None if row["last_scanned_at"] is None else str(row["last_scanned_at"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _note(row: sqlite3.Row) -> NoteMetadataRecord:
    return NoteMetadataRecord(
        id=str(row["id"]),
        vault_id=str(row["vault_id"]),
        relative_path=str(row["relative_path"]),
        path_key=str(row["path_key"]),
        title=str(row["title"]),
        note_type=str(row["note_type"]),
        confidence=None if row["confidence"] is None else int(row["confidence"]),
        revision_status=str(row["revision_status"]),
        source_hash=str(row["source_hash"]),
        file_mtime_ns=int(row["file_mtime_ns"]),
        frontmatter_extra_json=str(row["frontmatter_extra_json"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _link(row: sqlite3.Row) -> NoteLinkRecord:
    return NoteLinkRecord(
        id=str(row["id"]),
        source_note_id=str(row["source_note_id"]),
        target_note_id=None if row["target_note_id"] is None else str(row["target_note_id"]),
        unresolved_target=str(row["unresolved_target"]),
        source_position=str(row["source_position"]),
        heading=str(row["heading"]),
        block_id=str(row["block_id"]),
        link_type=str(row["link_type"]),
        created_at=str(row["created_at"]),
    )


class SQLiteObsidianVaultRepository:
    """Explicit-connection repository over existing Phase 3 note/vault tables."""

    def __init__(self, connection: sqlite3.Connection, *, validate_schema: bool = True):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("connection must be an explicit sqlite3.Connection")
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        if validate_schema:
            self.validate_schema()

    def validate_schema(self):
        tables = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        missing_tables = sorted(set(_REQUIRED_COLUMNS) - tables)
        if missing_tables:
            raise ObsidianVaultSchemaError(
                "Phase 5.3 required tables are missing: {}".format(
                    ", ".join(missing_tables)
                )
            )
        problems = []
        for table, required in _REQUIRED_COLUMNS.items():
            columns = {
                str(row[1])
                for row in self.connection.execute(
                    'PRAGMA table_info("{}")'.format(table)
                ).fetchall()
            }
            missing = sorted(required - columns)
            if missing:
                problems.append("{}:[{}]".format(table, ",".join(missing)))
        if problems:
            raise ObsidianVaultSchemaError(
                "Phase 5.3 schema columns are incomplete: {}".format(
                    "; ".join(problems)
                )
            )

    def get_vault_by_key(self, path_key: str) -> Optional[VaultRecord]:
        row = self.connection.execute(
            "SELECT * FROM vaults WHERE path_key=?", (str(path_key),)
        ).fetchone()
        return None if row is None else _vault(row)

    def get_vault(self, vault_id: str) -> Optional[VaultRecord]:
        row = self.connection.execute(
            "SELECT * FROM vaults WHERE id=?", (str(vault_id),)
        ).fetchone()
        return None if row is None else _vault(row)

    def list_notes(self, vault_id: str) -> Tuple[NoteMetadataRecord, ...]:
        rows = self.connection.execute(
            "SELECT * FROM note_metadata WHERE vault_id=? ORDER BY path_key,id",
            (str(vault_id),),
        ).fetchall()
        return tuple(_note(row) for row in rows)

    def get_note(self, note_id: str) -> Optional[NoteMetadataRecord]:
        row = self.connection.execute(
            "SELECT * FROM note_metadata WHERE id=?", (str(note_id),)
        ).fetchone()
        return None if row is None else _note(row)

    def list_links_for_note(self, note_id: str) -> Tuple[NoteLinkRecord, ...]:
        rows = self.connection.execute(
            "SELECT * FROM note_links WHERE source_note_id=? "
            "ORDER BY source_position,id",
            (str(note_id),),
        ).fetchall()
        return tuple(_link(row) for row in rows)

    def get_backlinks(self, note_id: str) -> Tuple[NoteLinkRecord, ...]:
        rows = self.connection.execute(
            "SELECT * FROM note_links WHERE target_note_id=? "
            "ORDER BY source_note_id,source_position,id",
            (str(note_id),),
        ).fetchall()
        return tuple(_link(row) for row in rows)

    def list_tags_for_note(self, note_id: str) -> Tuple[str, ...]:
        rows = self.connection.execute(
            "SELECT t.name FROM tags t "
            "JOIN note_tags nt ON nt.tag_id=t.id "
            "WHERE nt.note_id=? ORDER BY t.normalized_name,t.id",
            (str(note_id),),
        ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def apply_snapshot(
        self,
        *,
        vault: Mapping[str, object],
        notes: Sequence[Mapping[str, object]],
        links: Sequence[Mapping[str, object]],
        tags: Sequence[Mapping[str, str]],
        note_tags: Sequence[Tuple[str, str]],
        scanned_at: str,
    ) -> None:
        with transaction(self.connection, immediate=True):
            existing_vault = self.get_vault(str(vault["id"]))
            if existing_vault is None:
                self.connection.execute(
                    "INSERT INTO vaults "
                    "(id,name,root_path,path_key,enabled,last_scanned_at,created_at,updated_at) "
                    "VALUES (?,?,?,?,1,?,?,?)",
                    (
                        str(vault["id"]),
                        str(vault["name"]),
                        str(vault["root_path"]),
                        str(vault["path_key"]),
                        scanned_at,
                        str(vault["created_at"]),
                        scanned_at,
                    ),
                )
            else:
                self.connection.execute(
                    "UPDATE vaults SET name=?,root_path=?,path_key=?,enabled=1,"
                    "last_scanned_at=?,updated_at=? WHERE id=?",
                    (
                        str(vault["name"]),
                        str(vault["root_path"]),
                        str(vault["path_key"]),
                        scanned_at,
                        scanned_at,
                        str(vault["id"]),
                    ),
                )

            scanned_note_ids = []
            for item in notes:
                note_id = str(item["id"])
                scanned_note_ids.append(note_id)
                existing = self.get_note(note_id)
                extra_json = json.dumps(
                    dict(item["frontmatter_extra"]),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                if existing is None:
                    self.connection.execute(
                        "INSERT INTO note_metadata "
                        "(id,vault_id,relative_path,path_key,title,note_type,confidence,"
                        "revision_status,pinned_at,archived_at,trashed_at,source_hash,"
                        "file_mtime_ns,frontmatter_extra_json,created_at,updated_at) "
                        "VALUES (?,?,?,?,?,?,?,?,NULL,NULL,NULL,?,?,?,?,?)",
                        (
                            note_id,
                            str(vault["id"]),
                            str(item["relative_path"]),
                            str(item["path_key"]),
                            str(item["title"]),
                            str(item["note_type"]),
                            item["confidence"],
                            str(item["revision_status"]),
                            str(item["source_hash"]),
                            int(item["file_mtime_ns"]),
                            extra_json,
                            str(item["created_at"]),
                            scanned_at,
                        ),
                    )
                else:
                    if existing.vault_id != str(vault["id"]):
                        raise ObsidianVaultConflictError(
                            "note ID is already owned by another vault"
                        )
                    self.connection.execute(
                        "UPDATE note_metadata SET relative_path=?,path_key=?,title=?,"
                        "note_type=?,confidence=?,revision_status=?,source_hash=?,"
                        "file_mtime_ns=?,frontmatter_extra_json=?,updated_at=? WHERE id=?",
                        (
                            str(item["relative_path"]),
                            str(item["path_key"]),
                            str(item["title"]),
                            str(item["note_type"]),
                            item["confidence"],
                            str(item["revision_status"]),
                            str(item["source_hash"]),
                            int(item["file_mtime_ns"]),
                            extra_json,
                            scanned_at,
                            note_id,
                        ),
                    )

            for tag in tags:
                self.connection.execute(
                    "INSERT INTO tags (id,name,normalized_name,created_at) VALUES (?,?,?,?) "
                    "ON CONFLICT(normalized_name) DO NOTHING",
                    (
                        str(tag["id"]),
                        str(tag["name"]),
                        str(tag["normalized_name"]),
                        str(tag["created_at"]),
                    ),
                )

            for note_id in scanned_note_ids:
                self.connection.execute(
                    "DELETE FROM note_tags WHERE note_id=?", (note_id,)
                )
                self.connection.execute(
                    "DELETE FROM note_links WHERE source_note_id=?", (note_id,)
                )

            for note_id, tag_id in note_tags:
                self.connection.execute(
                    "INSERT OR IGNORE INTO note_tags (note_id,tag_id) VALUES (?,?)",
                    (str(note_id), str(tag_id)),
                )

            for item in links:
                self.connection.execute(
                    "INSERT INTO note_links "
                    "(id,source_note_id,target_note_id,unresolved_target,source_position,"
                    "heading,block_id,link_type,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        str(item["id"]),
                        str(item["source_note_id"]),
                        item["target_note_id"],
                        str(item["unresolved_target"]),
                        str(item["source_position"]),
                        str(item["heading"]),
                        str(item["block_id"]),
                        str(item["link_type"]),
                        str(item["created_at"]),
                    ),
                )
