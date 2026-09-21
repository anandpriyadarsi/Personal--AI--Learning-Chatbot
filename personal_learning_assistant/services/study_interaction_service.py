"""Generic active-reading and Study Companion orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from personal_learning_assistant.domain.study_item_models import StudyItemIdentity


class StudyInteractionValidationError(ValueError):
    pass


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class StudyInteractionService:
    def __init__(self, repository, *, now=_utc_now, id_factory=None):
        self.repository = repository
        self._now = now
        self._id_factory = id_factory or (lambda prefix: "{}-{}".format(prefix, uuid.uuid4()))

    def history(self, identity: StudyItemIdentity):
        return self.repository.reading_history(identity)

    def companion(self, identity: StudyItemIdentity):
        entries = self.repository.list_entries(identity)
        return {
            "key_points": tuple(x for x in entries if x["entry_type"] == "key_point"),
            "doubts": tuple(x for x in entries if x["entry_type"] == "doubt"),
            "personal_notes": tuple(
                x for x in entries if x["entry_type"] == "personal_note"
            ),
        }

    def start_reading(self, *, identity, locator=None):
        return self.repository.create_session(
            session_id=self._id_factory("study-reading"),
            identity=identity,
            locator=dict(locator or {}),
            now=self._now(),
        )

    def heartbeat(self, *, identity, session_id, sequence, delta_seconds, scroll_bps):
        return self.repository.heartbeat(
            session_id=session_id,
            identity=identity,
            sequence=int(sequence),
            delta_seconds=int(delta_seconds),
            scroll_bps=int(scroll_bps),
            now=self._now(),
        )

    def end_reading(
        self, *, identity, session_id, sequence, delta_seconds, scroll_bps,
        replayed_delta_seconds=0
    ):
        return self.repository.end_session(
            session_id=session_id,
            identity=identity,
            sequence=int(sequence),
            delta_seconds=int(delta_seconds),
            scroll_bps=int(scroll_bps),
            replayed_delta_seconds=int(replayed_delta_seconds or 0),
            now=self._now(),
        )

    def add_entry(self, *, identity, entry_type, entry_text, locator=None):
        return self.repository.add_entry(
            entry_id=self._id_factory("study-entry"),
            identity=identity,
            entry_type=str(entry_type or "").strip(),
            entry_text=str(entry_text or "").strip(),
            locator=dict(locator or {}),
            now=self._now(),
        )

    def archive_entry(self, *, identity, entry_id):
        return self.repository.archive_entry(
            entry_id=str(entry_id or "").strip(),
            identity=identity,
            now=self._now(),
        )
