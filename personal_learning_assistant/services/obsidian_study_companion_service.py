"""Obsidian Reader identity, history, and Companion coordination."""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode

from markupsafe import Markup, escape

from personal_learning_assistant.repositories.sqlite.obsidian_study_repository import (
    ObsidianStudyRepositoryConflictError,
    ObsidianStudyRepositoryError,
    ObsidianStudyRepositoryNotFoundError,
    SQLiteObsidianStudyRepository,
)
from personal_learning_assistant.repositories.sqlite.obsidian_study_repository_v2 import (
    SQLiteObsidianStudyRepositoryV2,
    supports_unified_study_schema,
)
from personal_learning_assistant.services.obsidian_markdown_renderer import (
    render_markdown,
)
from personal_learning_assistant.services.obsidian_workspace_service import (
    ObsidianWorkspaceNotFoundError,
    ObsidianWorkspaceUnavailableError,
    ObsidianWorkspaceValidationError,
    build_obsidian_workspace_service,
)


MAX_COMPANION_TEXT_CHARS = 2000
_HASH = re.compile(r"^[0-9a-f]{64}$")


class ObsidianStudyError(RuntimeError):
    """Base safe web-facing Reader/Companion error."""


class ObsidianStudyValidationError(ObsidianStudyError):
    """A tracking or Companion request is malformed."""


class ObsidianStudyNotFoundError(ObsidianStudyError):
    """A scoped session or Companion entry was not found."""


class ObsidianStudyConflictError(ObsidianStudyError):
    """The note or session changed before a write completed."""


class ObsidianStudyUnavailableError(ObsidianStudyError):
    """Study persistence is temporarily unavailable."""


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _empty_history():
    return {
        "times_opened": 0,
        "last_read_at": None,
        "total_active_seconds": 0,
        "last_session_active_seconds": 0,
        "max_scroll_bps": 0,
        "recent_sessions": (),
    }


def _normalized_path_key(relative_path: str) -> str:
    return unicodedata.normalize(
        "NFC",
        str(relative_path or "").replace("\\", "/").strip(),
    ).casefold()


def _escaped_fallback(source: str) -> Markup:
    return Markup('<pre class="obsidian-render-fallback">{}</pre>').format(
        escape(source)
    )


class ObsidianStudyCompanionService:
    def __init__(
        self,
        workspace_service,
        repository,
        *,
        renderer=render_markdown,
        now=_utc_now,
        id_factory=uuid.uuid4,
    ):
        self.workspace_service = workspace_service
        self.repository = repository
        self._renderer = renderer
        self._now = now
        self._id_factory = id_factory

    @staticmethod
    def _identity(note):
        vault_identity = str(note.get("vault_identity") or "").strip()
        relative_path = str(note.get("relative_path") or "").strip()
        source_hash = str(note.get("source_hash") or "").strip().lower()
        if not vault_identity.startswith("vault:") or not _HASH.fullmatch(
            vault_identity[6:]
        ):
            raise ObsidianStudyUnavailableError(
                "The current Obsidian note identity is unavailable."
            )
        if not relative_path or not _HASH.fullmatch(source_hash):
            raise ObsidianStudyUnavailableError(
                "The current Obsidian note identity is unavailable."
            )

        assistant_id = note.get("assistant_id")
        if assistant_id:
            try:
                note_identity = "assistant:" + str(uuid.UUID(str(assistant_id)))
            except (ValueError, AttributeError, TypeError):
                assistant_id = None
        if not assistant_id:
            material = vault_identity + "\0" + _normalized_path_key(relative_path)
            note_identity = "path:" + hashlib.sha256(
                material.encode("utf-8")
            ).hexdigest()
        return vault_identity, note_identity, relative_path, source_hash

    @staticmethod
    def _submitted_hash(value) -> str:
        text = str(value or "").strip()
        if text != text.lower() or not _HASH.fullmatch(text):
            raise ObsidianStudyValidationError(
                "A valid current note hash is required."
            )
        return text

    @staticmethod
    def _uuid(value, *, label: str) -> str:
        try:
            return str(uuid.UUID(str(value or "")))
        except (ValueError, AttributeError, TypeError) as error:
            raise ObsidianStudyValidationError(
                "A valid {} identifier is required.".format(label)
            ) from error

    @staticmethod
    def _integer(value, *, label: str, minimum: int, maximum: int) -> int:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not minimum <= value <= maximum
        ):
            raise ObsidianStudyValidationError(
                "{} is outside the accepted range.".format(label)
            )
        return value

    def _current_note(self, relative_path, source_hash):
        submitted_hash = self._submitted_hash(source_hash)
        try:
            note = dict(self.workspace_service.note_preview(relative_path))
        except ObsidianWorkspaceValidationError as error:
            raise ObsidianStudyValidationError(
                "Choose a valid Markdown note inside the configured vault."
            ) from error
        except ObsidianWorkspaceNotFoundError as error:
            raise ObsidianStudyNotFoundError(
                "That Markdown note is no longer available."
            ) from error
        except ObsidianWorkspaceUnavailableError as error:
            raise ObsidianStudyUnavailableError(
                "The current Markdown note could not be validated safely."
            ) from error
        except Exception as error:
            raise ObsidianStudyUnavailableError(
                "The current Markdown note could not be validated safely."
            ) from error

        identity = self._identity(note)
        if identity[3] != submitted_hash:
            raise ObsidianStudyConflictError(
                "The Markdown note changed. Refresh the Reader and try again."
            )
        return note, identity

    @staticmethod
    def _session_result(row):
        return {
            "session_id": str(row["id"]),
            "active_seconds": int(row["active_seconds"]),
            "max_scroll_bps": int(row["max_scroll_bps"]),
            "accepted": bool(row["accepted"]),
            "ended_at": (
                None if row.get("ended_at") is None else str(row["ended_at"])
            ),
        }

    @staticmethod
    def _translate_repository_error(error):
        if isinstance(error, ObsidianStudyRepositoryNotFoundError):
            return ObsidianStudyNotFoundError(
                "The reading session or Companion entry was not found."
            )
        if isinstance(error, ObsidianStudyRepositoryConflictError):
            return ObsidianStudyConflictError(
                "The reading session or Companion entry changed."
            )
        return ObsidianStudyUnavailableError(
            "Study history and Companion are temporarily unavailable."
        )

    def start_reading(self, *, relative_path, source_hash):
        _note, identity = self._current_note(relative_path, source_hash)
        try:
            session_id = str(uuid.UUID(str(self._id_factory())))
        except (ValueError, AttributeError, TypeError) as error:
            raise ObsidianStudyUnavailableError(
                "A reading session could not be started."
            ) from error
        try:
            row = self.repository.create_session(
                session_id=session_id,
                vault_identity=identity[0],
                note_identity=identity[1],
                relative_path=identity[2],
                source_hash=identity[3],
                now=self._now(),
            )
        except ObsidianStudyRepositoryError as error:
            raise self._translate_repository_error(error) from error
        return self._session_result(row)

    def heartbeat(
        self,
        *,
        relative_path,
        source_hash,
        session_id,
        sequence,
        delta_seconds,
        scroll_bps,
    ):
        canonical_session_id = self._uuid(session_id, label="reading session")
        bounded_sequence = self._integer(
            sequence,
            label="event sequence",
            minimum=1,
            maximum=2_147_483_647,
        )
        bounded_delta = self._integer(
            delta_seconds,
            label="active-time delta",
            minimum=1,
            maximum=60,
        )
        bounded_scroll = self._integer(
            scroll_bps,
            label="scroll progress",
            minimum=0,
            maximum=10000,
        )
        _note, identity = self._current_note(relative_path, source_hash)
        try:
            row = self.repository.heartbeat(
                session_id=canonical_session_id,
                vault_identity=identity[0],
                note_identity=identity[1],
                source_hash=identity[3],
                sequence=bounded_sequence,
                delta_seconds=bounded_delta,
                scroll_bps=bounded_scroll,
                now=self._now(),
            )
        except ObsidianStudyRepositoryError as error:
            raise self._translate_repository_error(error) from error
        return self._session_result(row)

    def end_reading(
        self,
        *,
        relative_path,
        source_hash,
        session_id,
        sequence,
        delta_seconds,
        scroll_bps,
        replayed_delta_seconds=None,
    ):
        canonical_session_id = self._uuid(session_id, label="reading session")
        bounded_sequence = self._integer(
            sequence,
            label="event sequence",
            minimum=1,
            maximum=2_147_483_647,
        )
        bounded_delta = self._integer(
            delta_seconds,
            label="active-time delta",
            minimum=0,
            maximum=60,
        )
        bounded_scroll = self._integer(
            scroll_bps,
            label="scroll progress",
            minimum=0,
            maximum=10000,
        )
        bounded_replayed_delta = (
            bounded_delta
            if replayed_delta_seconds is None
            else self._integer(
                replayed_delta_seconds,
                label="replayed active-time delta",
                minimum=0,
                maximum=bounded_delta,
            )
        )
        _note, identity = self._current_note(relative_path, source_hash)
        try:
            row = self.repository.end_session(
                session_id=canonical_session_id,
                vault_identity=identity[0],
                note_identity=identity[1],
                source_hash=identity[3],
                sequence=bounded_sequence,
                delta_seconds=bounded_delta,
                scroll_bps=bounded_scroll,
                now=self._now(),
                replayed_delta_seconds=bounded_replayed_delta,
            )
        except ObsidianStudyRepositoryError as error:
            raise self._translate_repository_error(error) from error
        return self._session_result(row)

    def add_companion_entry(
        self,
        *,
        relative_path,
        source_hash,
        entry_type,
        entry_text,
    ):
        normalized_type = str(entry_type or "").strip()
        if normalized_type not in ("key_point", "doubt"):
            raise ObsidianStudyValidationError(
                "Choose key point or doubt as the Companion entry type."
            )
        normalized_text = (
            str(entry_text or "")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .strip()
        )
        if not normalized_text or len(normalized_text) > MAX_COMPANION_TEXT_CHARS:
            raise ObsidianStudyValidationError(
                "Companion text must contain 1 to 2000 characters."
            )
        _note, identity = self._current_note(relative_path, source_hash)
        try:
            entry_id = str(uuid.UUID(str(self._id_factory())))
        except (ValueError, AttributeError, TypeError) as error:
            raise ObsidianStudyUnavailableError(
                "The Companion entry could not be saved."
            ) from error
        try:
            return self.repository.add_entry(
                entry_id=entry_id,
                vault_identity=identity[0],
                note_identity=identity[1],
                relative_path=identity[2],
                entry_type=normalized_type,
                entry_text=normalized_text,
                now=self._now(),
                source_hash=identity[3],
            )
        except ObsidianStudyRepositoryError as error:
            raise self._translate_repository_error(error) from error

    def archive_companion_entry(
        self,
        *,
        relative_path,
        source_hash,
        entry_id,
    ):
        canonical_entry_id = self._uuid(entry_id, label="Companion entry")
        _note, identity = self._current_note(relative_path, source_hash)
        try:
            return self.repository.archive_entry(
                entry_id=canonical_entry_id,
                vault_identity=identity[0],
                note_identity=identity[1],
                now=self._now(),
            )
        except ObsidianStudyRepositoryError as error:
            raise self._translate_repository_error(error) from error

    def reader_view(self, relative_path):
        note = dict(self.workspace_service.note_preview(relative_path))
        vault_identity, note_identity, path, _source_hash = self._identity(note)
        source = str(note.get("text") or "")
        try:
            rendered = self._renderer(source)
            if not isinstance(rendered, Markup):
                rendered = Markup(escape(str(rendered)))
        except Exception:
            rendered = _escaped_fallback(source)

        history = _empty_history()
        companion = {
            "available": True,
            "message": "",
            "key_points": (),
            "doubts": (),
        }
        try:
            history = self.repository.reading_history(
                vault_identity=vault_identity,
                note_identity=note_identity,
            )
            entries = self.repository.list_entries(
                vault_identity=vault_identity,
                note_identity=note_identity,
            )
            companion["key_points"] = tuple(
                item for item in entries if item["entry_type"] == "key_point"
            )
            companion["doubts"] = tuple(
                item for item in entries if item["entry_type"] == "doubt"
            )
        except ObsidianStudyRepositoryError:
            history = _empty_history()
            companion = {
                "available": False,
                "message": (
                    "Study history and Companion are temporarily unavailable."
                ),
                "key_points": (),
                "doubts": (),
            }

        vault_name = str(note.get("vault_name") or "").strip()
        deep_link = ""
        if vault_name:
            deep_link = "obsidian://open?" + urlencode(
                {"vault": vault_name, "file": path},
                quote_via=quote,
            )
        note.update(
            {
                "vault_identity": vault_identity,
                "note_identity": note_identity,
                "rendered_html": rendered,
                "open_in_obsidian_url": deep_link,
                "history": history,
                "companion": companion,
            }
        )
        return note


def build_obsidian_study_companion_service(
    *,
    workspace_service=None,
    database_path="data/learning_assistant.db",
):
    workspace = workspace_service or build_obsidian_workspace_service()
    database = Path(database_path)
    if supports_unified_study_schema(database):
        repository = SQLiteObsidianStudyRepositoryV2(database)
    else:
        repository = SQLiteObsidianStudyRepository(database)
    return ObsidianStudyCompanionService(workspace, repository)
