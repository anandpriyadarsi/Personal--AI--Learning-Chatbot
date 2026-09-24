"""Lifecycle and bounded study actions for Notes Studio Phase 7.5.15.8.

Lifecycle metadata remains owned by the existing SQLite note_metadata rows. File
moves and study-status writes delegate to the established Phase 5.4 Notes
Studio command service. Read helpers use SQLite read-only mode and never mutate
the vault, registry, retrieval state, or Tutor state.
"""
from __future__ import annotations

import sqlite3
from importlib import import_module
from pathlib import Path
from typing import Iterable

from personal_learning_assistant.services.notes_studio_editor_service import (
    configured_notes_studio_mutation_context,
)


_TRASH_PREFIX = ".trash/Personal AI Learning Assistant/"
_STUDY_ACTIONS = {
    "needs_practice": "needs_practice",
    "review_due": "review_due",
    "revised": "revised",
    "mastered": "mastered",
}
_METADATA_ACTIONS = {"pin", "unpin", "archive", "unarchive"}
_ALL_ACTIONS = _METADATA_ACTIONS | set(_STUDY_ACTIONS) | {"trash"}


class NotesStudioLifecycleError(RuntimeError):
    pass


class NotesStudioLifecycleValidationError(NotesStudioLifecycleError):
    pass


class NotesStudioLifecycleNotFoundError(NotesStudioLifecycleError):
    pass


class NotesStudioLifecycleConflictError(NotesStudioLifecycleError):
    pass


class NotesStudioLifecycleUnavailableError(NotesStudioLifecycleError):
    pass


def _clean(value, *, limit=500) -> str:
    return " ".join(str(value or "").replace("\x00", "").split())[:limit]


def _readonly_connection(database_path):
    path = Path(database_path)
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(str(path))
    uri = path.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def read_lifecycle_snapshot(database_path, note_ids: Iterable[str]):
    """Return lifecycle timestamps for existing managed-note ids, read-only."""
    ids = tuple(
        dict.fromkeys(
            _clean(item, limit=100)
            for item in note_ids or ()
            if _clean(item, limit=100)
        )
    )
    if not ids:
        return {}
    try:
        connection = _readonly_connection(database_path)
    except (OSError, sqlite3.Error):
        return {}
    try:
        placeholders = ",".join("?" for _ in ids)
        rows = connection.execute(
            "SELECT id,pinned_at,archived_at,trashed_at "
            "FROM note_metadata WHERE id IN ({})".format(placeholders),
            ids,
        ).fetchall()
        return {
            str(row["id"]): {
                "pinned_at": "" if row["pinned_at"] is None else str(row["pinned_at"]),
                "archived_at": "" if row["archived_at"] is None else str(row["archived_at"]),
                "trashed_at": "" if row["trashed_at"] is None else str(row["trashed_at"]),
            }
            for row in rows
        }
    except sqlite3.Error:
        return {}
    finally:
        connection.close()


def derive_restore_target(relative_path: str) -> str:
    path = str(relative_path or "").replace("\\", "/")
    if not path.startswith(_TRASH_PREFIX):
        return ""
    target = path[len(_TRASH_PREFIX) :].lstrip("/")
    if not target or target.startswith(".trash/"):
        return ""
    return target


def _configured_trash_rows(database_path="data/learning_assistant.db"):
    """Read trashed managed-note metadata for the currently configured vault."""
    config_api = import_module("obsidian_integration")
    config = config_api.load_config()
    config = dict(config) if isinstance(config, dict) else {}
    root = str(config.get("vault_path") or "").strip()
    if not root or not bool(config.get("enabled", False)):
        return ()

    try:
        root_resolved = Path(root).resolve(strict=False)
        connection = _readonly_connection(database_path)
    except (OSError, sqlite3.Error):
        return ()

    try:
        vault_rows = connection.execute(
            "SELECT id,root_path FROM vaults WHERE enabled=1 ORDER BY id"
        ).fetchall()
        vault_id = ""
        for row in vault_rows:
            try:
                candidate = Path(str(row["root_path"])).resolve(strict=False)
            except OSError:
                continue
            if candidate == root_resolved:
                vault_id = str(row["id"])
                break
        if not vault_id:
            return ()

        rows = connection.execute(
            "SELECT id,title,relative_path,source_hash,trashed_at "
            "FROM note_metadata "
            "WHERE vault_id=? AND trashed_at IS NOT NULL "
            "ORDER BY trashed_at DESC,title COLLATE NOCASE,id",
            (vault_id,),
        ).fetchall()
        return tuple(
            {
                "id": str(row["id"]),
                "title": str(row["title"]),
                "relative_path": str(row["relative_path"]),
                "source_hash": str(row["source_hash"]),
                "trashed_at": str(row["trashed_at"]),
            }
            for row in rows
        )
    except sqlite3.Error:
        return ()
    finally:
        connection.close()


def _translate_error(error):
    store_module = import_module(
        "personal_learning_assistant.repositories.filesystem.markdown_note_store"
    )
    repo_module = import_module(
        "personal_learning_assistant.repositories.sqlite.notes_studio_repository"
    )
    if isinstance(error, store_module.MarkdownConflictError):
        return NotesStudioLifecycleConflictError(
            "The note changed since you opened it. Refresh before continuing."
        )
    if isinstance(error, repo_module.NotesStudioNotFoundError):
        return NotesStudioLifecycleNotFoundError(
            "That managed note no longer exists."
        )
    if isinstance(error, (ValueError, store_module.MarkdownPathError)):
        return NotesStudioLifecycleValidationError(
            "The lifecycle action or restore destination is invalid."
        )
    if isinstance(error, NotesStudioLifecycleError):
        return error
    return NotesStudioLifecycleUnavailableError(
        "Notes Studio lifecycle actions are temporarily unavailable."
    )


class NotesStudioLifecycleService:
    """Expose lifecycle and bounded study actions through Phase 5.4 commands."""

    def __init__(
        self,
        *,
        mutation_context_factory=configured_notes_studio_mutation_context,
        trash_reader=_configured_trash_rows,
    ):
        self.mutation_context_factory = mutation_context_factory
        self.trash_reader = trash_reader

    def apply_action(self, *, note_id, action, expected_hash=""):
        note_id = _clean(note_id, limit=100)
        action = _clean(action, limit=40).casefold()
        expected_hash = _clean(expected_hash, limit=128).casefold()
        if not note_id or action not in _ALL_ACTIONS:
            raise NotesStudioLifecycleValidationError(
                "Choose a supported lifecycle or study action."
            )
        if action in _STUDY_ACTIONS or action == "trash":
            if len(expected_hash) != 64:
                raise NotesStudioLifecycleValidationError(
                    "Refresh the note before changing its study or trash state."
                )

        try:
            with self.mutation_context_factory() as service:
                if action == "pin":
                    view = service.pin(note_id, True)
                elif action == "unpin":
                    view = service.pin(note_id, False)
                elif action == "archive":
                    view = service.archive(note_id, True)
                elif action == "unarchive":
                    view = service.archive(note_id, False)
                elif action == "trash":
                    view = service.trash(
                        note_id,
                        expected_hash=expected_hash,
                    )
                else:
                    view = service.set_study_status(
                        note_id,
                        expected_hash,
                        _STUDY_ACTIONS[action],
                    )
        except Exception as error:
            raise _translate_error(error) from error

        return {
            "id": str(view.id),
            "relative_path": str(view.relative_path),
            "source_hash": str(view.source_hash),
            "pinned": bool(view.pinned_at),
            "archived": bool(view.archived_at),
            "trashed": bool(view.trashed_at),
            "revision_status": str(view.revision_status),
        }

    def trash_workspace(self):
        try:
            raw_rows = tuple(self.trash_reader() or ())
        except Exception as error:
            raise NotesStudioLifecycleUnavailableError(
                "Notes Studio Trash is temporarily unavailable."
            ) from error

        notes = []
        for raw in raw_rows:
            row = dict(raw)
            restore_target = derive_restore_target(row.get("relative_path", ""))
            if not restore_target:
                continue
            notes.append(
                {
                    "id": _clean(row.get("id"), limit=100),
                    "title": _clean(row.get("title"), limit=300) or "Untitled",
                    "relative_path": str(row.get("relative_path") or ""),
                    "restore_target": restore_target,
                    "source_hash": _clean(row.get("source_hash"), limit=128),
                    "trashed_at": _clean(row.get("trashed_at"), limit=80),
                }
            )
        return {"notes": notes, "count": len(notes)}

    def restore_note(self, *, note_id, expected_hash, relative_path):
        note_id = _clean(note_id, limit=100)
        expected_hash = _clean(expected_hash, limit=128).casefold()
        target = str(relative_path or "").strip().replace("\\", "/")
        if not note_id or len(expected_hash) != 64 or not target:
            raise NotesStudioLifecycleValidationError(
                "Choose an explicit restore destination and refresh Trash."
            )
        if target.startswith("/") or target.startswith(".trash/") or ".." in Path(target).parts:
            raise NotesStudioLifecycleValidationError(
                "Choose a safe vault-relative restore destination."
            )
        try:
            with self.mutation_context_factory() as service:
                view = service.restore(
                    note_id,
                    target,
                    expected_hash=expected_hash,
                )
        except Exception as error:
            raise _translate_error(error) from error
        return {
            "id": str(view.id),
            "relative_path": str(view.relative_path),
            "source_hash": str(view.source_hash),
            "trashed": bool(view.trashed_at),
        }


def build_notes_studio_lifecycle_service() -> NotesStudioLifecycleService:
    return NotesStudioLifecycleService()
