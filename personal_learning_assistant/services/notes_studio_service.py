"""Notes Studio foundation: safe Markdown + SQLite coordinated commands."""
from __future__ import annotations

import hashlib
import posixpath
import uuid
from datetime import datetime, timezone
from pathlib import Path

from personal_learning_assistant.domain.notes_studio_models import (
    CreateNoteRequest,
    UpdateNoteRequest,
)
from personal_learning_assistant.repositories.filesystem.markdown_note_store import (
    AtomicMarkdownNoteStore,
    MarkdownConflictError,
)
from personal_learning_assistant.repositories.filesystem.obsidian_vault_scanner import (
    normalized_note_path_key,
)
from personal_learning_assistant.repositories.sqlite.knowledge_registry_repository import (
    SQLiteKnowledgeRegistryRepository,
)
from personal_learning_assistant.repositories.sqlite.notes_studio_repository import (
    SQLiteNotesStudioRepository,
)
from personal_learning_assistant.services.operation_coordination_service import (
    OperationCoordinationService,
)


_CANON = {
    "unreviewed",
    "learning",
    "needs_practice",
    "review_due",
    "revised",
    "mastered",
}
_MANAGED_FRONTMATTER = {
    "assistant_id",
    "title",
    "topic",
    "course",
    "note_type",
    "note_date",
    "date",
    "confidence",
    "revision_status",
    "card_summary",
    "tags",
}


def _now():
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _scalar(value) -> str:
    return " ".join(str(value or "").replace("\x00", "").split())


def _list_values(values):
    cleaned = []
    for value in values or ():
        text = _scalar(value).lstrip("#").strip()
        if text:
            cleaned.append(text)
    return tuple(cleaned)


def _frontmatter(
    note_id,
    title,
    note_type,
    confidence,
    status,
    tags,
    *,
    topic="",
    course="",
    note_date="",
    card_summary=(),
):
    lines = [
        "---",
        "assistant_id: {}".format(_scalar(note_id)),
        "title: {}".format(_scalar(title)),
    ]
    if _scalar(topic):
        lines.append("topic: {}".format(_scalar(topic)))
    if _scalar(course):
        lines.append("course: {}".format(_scalar(course)))
    lines.append("note_type: {}".format(_scalar(note_type)))
    if _scalar(note_date):
        lines.append("note_date: {}".format(_scalar(note_date)))
    lines.append("revision_status: {}".format(_scalar(status)))
    if confidence is not None:
        lines.append("confidence: {}".format(int(confidence)))
    summary = _list_values(card_summary)[:5]
    if summary:
        lines.append("card_summary:")
        lines.extend("  - " + item for item in summary)
    clean_tags = _list_values(tags)
    if clean_tags:
        lines.append("tags:")
        lines.extend("  - " + item for item in clean_tags)
    lines.append("---")
    return "\n".join(lines)


def _split_frontmatter(text: str):
    source = str(text or "")
    lines = source.splitlines()
    if not lines or lines[0].lstrip("\ufeff").strip() != "---":
        return (), source
    for index in range(1, len(lines)):
        if lines[index].strip() in ("---", "..."):
            return tuple(lines[1:index]), "\n".join(lines[index + 1 :]).lstrip("\n")
    return (), source


def _frontmatter_values(lines):
    values = {}
    current = None
    for raw in tuple(lines or ()):
        stripped = str(raw).strip()
        if not stripped or stripped.startswith("#"):
            continue
        if str(raw)[:1].isspace() and stripped.startswith("-") and current:
            item = stripped[1:].strip().strip("'\"")
            if item:
                existing = values.get(current)
                if not isinstance(existing, list):
                    existing = []
                existing.append(item)
                values[current] = existing
            continue
        if ":" not in str(raw):
            current = None
            continue
        key, value = str(raw).split(":", 1)
        current = key.strip().casefold() or None
        if not current:
            continue
        value = value.strip()
        if not value:
            values.setdefault(current, [])
        elif value.startswith("[") and value.endswith("]"):
            values[current] = [
                item.strip().strip("'\"")
                for item in value[1:-1].split(",")
                if item.strip().strip("'\"")
            ]
        else:
            values[current] = value.strip("'\"")
    return values


def _unknown_frontmatter(lines):
    blocks = []
    current = []
    current_key = None

    def flush():
        if not current:
            return
        if current_key is None or current_key not in _MANAGED_FRONTMATTER:
            blocks.extend(current)

    for raw in tuple(lines or ()):
        text = str(raw)
        stripped = text.strip()
        is_top_level_key = (
            bool(stripped)
            and not text[:1].isspace()
            and not stripped.startswith("#")
            and ":" in text
        )
        if is_top_level_key:
            flush()
            current.clear()
            current_key = text.split(":", 1)[0].strip().casefold()
        current.append(text)
    flush()
    return tuple(blocks)


def _merged_source(existing_source: str, generated: str, body: str) -> str:
    existing_lines, _existing_body = _split_frontmatter(existing_source)
    unknown = _unknown_frontmatter(existing_lines)
    generated_lines = generated.splitlines()
    canonical = generated_lines[1:-1]
    frontmatter_lines = ["---", *canonical]
    if unknown:
        frontmatter_lines.extend(unknown)
    frontmatter_lines.append("---")
    return "\n".join(frontmatter_lines) + "\n\n" + str(body or "").lstrip("\n")


def _value(values, key):
    value = values.get(key)
    if isinstance(value, list):
        return ""
    return str(value or "").strip()


def _summary_value(values):
    value = values.get("card_summary", ())
    if isinstance(value, str):
        value = (value,)
    elif not isinstance(value, list):
        value = ()
    return _list_values(value)[:5]


class NotesStudioService:
    def __init__(
        self,
        *,
        vault_id: str,
        store: AtomicMarkdownNoteStore,
        notes: SQLiteNotesStudioRepository,
        journal_repository: SQLiteKnowledgeRegistryRepository,
        inbox="01 INBOX",
        now=_now,
    ):
        self.vault_id = vault_id
        self.store = store
        self.notes = notes
        self.coordination = OperationCoordinationService(
            journal_repository,
            now=now,
        )
        self.inbox = inbox
        self._now = now

    def _validate(self, note_type, confidence, status):
        if confidence is not None and not 0 <= int(confidence) <= 5:
            raise ValueError("confidence must be 0-5 or null")
        if status not in _CANON:
            raise ValueError("unsupported revision_status")
        if not str(note_type).strip():
            raise ValueError("note_type is required")

    def create_note(self, request: CreateNoteRequest):
        self._validate(
            request.note_type,
            request.confidence,
            request.revision_status,
        )
        if not _scalar(request.title):
            raise ValueError("title is required")
        note_id = str(uuid.uuid4())
        rel = self.store.choose_create_path(self.inbox, request.title)
        meta = _frontmatter(
            note_id,
            request.title,
            request.note_type,
            request.confidence,
            request.revision_status,
            request.tags,
            topic=request.topic,
            course=request.course,
            note_date=request.note_date,
            card_summary=request.card_summary,
        )
        payload = (meta + "\n\n" + str(request.body or "").lstrip("\n")).encode(
            "utf-8"
        )
        op = self.coordination.begin_operation(
            kind="notes_studio_create",
            target_path=rel,
            before_hash=None,
        )
        try:
            new_hash = self.store.atomic_write(rel, payload)
            self.coordination.mark_file_applied(op.id, after_hash=new_hash)
            stat = (self.store.root / rel).stat()
            view = self.notes.insert_note(
                note_id=note_id,
                vault_id=self.vault_id,
                relative_path=rel,
                path_key=normalized_note_path_key(rel),
                title=_scalar(request.title),
                note_type=_scalar(request.note_type),
                confidence=request.confidence,
                revision_status=request.revision_status,
                source_hash=new_hash,
                file_mtime_ns=stat.st_mtime_ns,
                frontmatter_extra={"notes_studio": "phase5.4"},
                now=self._now(),
                tags=_list_values(request.tags),
            )
            self.coordination.mark_database_committed(op.id)
            self.coordination.enqueue_event(
                event_type="note.saved",
                entity_type="note",
                entity_id=note_id,
                payload={"source_hash": new_hash},
            )
            self.coordination.complete_operation(op.id)
            return view
        except Exception as exc:
            try:
                self.coordination.fail_operation(
                    op.id,
                    error=type(exc).__name__,
                )
            except Exception:
                pass
            raise

    def update_note(self, request: UpdateNoteRequest):
        current = self.notes.get(request.note_id)
        raw, current_hash = self.store.read(current.relative_path)
        if current_hash != request.expected_hash:
            raise MarkdownConflictError(
                "note changed on disk; refresh before saving"
            )

        existing_source = raw.decode("utf-8-sig")
        existing_frontmatter, existing_body = _split_frontmatter(existing_source)
        values = _frontmatter_values(existing_frontmatter)

        title = current.title if request.title is None else request.title
        typ = current.note_type if request.note_type is None else request.note_type
        confidence = (
            current.confidence
            if request.confidence is None
            else request.confidence
        )
        status = (
            current.revision_status
            if request.revision_status is None
            else request.revision_status
        )
        tags = current.tags if request.tags is None else request.tags
        topic = (
            _value(values, "topic")
            if request.topic is None
            else request.topic
        )
        course = (
            _value(values, "course")
            if request.course is None
            else request.course
        )
        note_date = (
            (_value(values, "note_date") or _value(values, "date"))
            if request.note_date is None
            else request.note_date
        )
        card_summary = (
            _summary_value(values)
            if request.card_summary is None
            else request.card_summary
        )
        body = existing_body if request.body is None else request.body

        self._validate(typ, confidence, status)
        if not _scalar(title):
            raise ValueError("title is required")
        generated = _frontmatter(
            current.id,
            title,
            typ,
            confidence,
            status,
            tags,
            topic=topic,
            course=course,
            note_date=note_date,
            card_summary=card_summary,
        )
        payload = _merged_source(
            existing_source,
            generated,
            str(body or ""),
        ).encode("utf-8")

        op = self.coordination.begin_operation(
            kind="notes_studio_update",
            target_path=current.relative_path,
            before_hash=current_hash,
        )
        try:
            new_hash = self.store.atomic_write(
                current.relative_path,
                payload,
                expected_hash=current_hash,
            )
            self.coordination.mark_file_applied(
                op.id,
                after_hash=new_hash,
            )
            stat = (self.store.root / current.relative_path).stat()
            view = self.notes.update_note(
                note_id=current.id,
                relative_path=current.relative_path,
                path_key=normalized_note_path_key(current.relative_path),
                title=_scalar(title),
                note_type=_scalar(typ),
                confidence=confidence,
                revision_status=status,
                source_hash=new_hash,
                file_mtime_ns=stat.st_mtime_ns,
                frontmatter_extra={"notes_studio": "phase5.4"},
                now=self._now(),
                tags=_list_values(tags),
            )
            self.coordination.mark_database_committed(op.id)
            self.coordination.enqueue_event(
                event_type="note.saved",
                entity_type="note",
                entity_id=current.id,
                payload={"source_hash": new_hash},
            )
            self.coordination.complete_operation(op.id)
            return view
        except Exception as exc:
            try:
                self.coordination.fail_operation(
                    op.id,
                    error=type(exc).__name__,
                )
            except Exception:
                pass
            raise

    def add_attachment(
        self,
        *,
        note_id: str,
        expected_hash: str,
        filename: str,
        payload: bytes,
    ):
        current = self.notes.get(note_id)
        _raw, current_hash = self.store.read(current.relative_path)
        if current_hash != str(expected_hash or ""):
            raise MarkdownConflictError(
                "note changed on disk; refresh before attaching files"
            )
        relative_path = self.store.choose_attachment_path(
            current.relative_path,
            current.id,
            filename,
        )
        op = self.coordination.begin_operation(
            kind="notes_studio_attachment_create",
            target_path=relative_path,
            before_hash=None,
        )
        try:
            written_path, asset_hash = self.store.atomic_write_attachment(
                current.relative_path,
                current.id,
                filename,
                payload,
                expected_note_hash=current_hash,
            )
            self.coordination.mark_file_applied(
                op.id,
                after_hash=asset_hash,
            )
            self.coordination.mark_database_committed(op.id)
            self.coordination.complete_operation(op.id)
            note_parent = Path(current.relative_path).parent.as_posix()
            start = "." if note_parent in ("", ".") else note_parent
            reference_path = posixpath.relpath(written_path, start=start)
            alt = Path(written_path).stem.replace("[", "").replace("]", "")
            return {
                "relative_path": written_path,
                "source_hash": asset_hash,
                "note_relative_path": current.relative_path,
                "markdown_reference": "![{}]({})".format(
                    alt or "image",
                    reference_path,
                ),
            }
        except Exception as exc:
            try:
                self.coordination.fail_operation(
                    op.id,
                    error=type(exc).__name__,
                )
            except Exception:
                pass
            raise

    def pin(self, note_id, pinned=True):
        return self.notes.set_lifecycle(
            note_id,
            pinned_at=self._now() if pinned else None,
            archived_at=None,
            trashed_at=None,
            now=self._now(),
            keep_existing=True,
        )

    def archive(self, note_id, archived=True):
        return self.notes.set_lifecycle(
            note_id,
            pinned_at=None,
            archived_at=self._now() if archived else None,
            trashed_at=None,
            now=self._now(),
            keep_existing=True,
        )

    def set_study_status(self, note_id, expected_hash, status):
        if status not in _CANON:
            raise ValueError("unsupported revision_status")
        return self.update_note(
            UpdateNoteRequest(
                note_id=note_id,
                expected_hash=str(expected_hash or ""),
                revision_status=status,
            )
        )

    def trash(self, note_id, expected_hash=None):
        current = self.notes.get(note_id)
        _raw, current_hash = self.store.read(current.relative_path)
        if expected_hash is not None and current_hash != str(expected_hash or ""):
            raise MarkdownConflictError(
                "note changed on disk; refresh before moving to trash"
            )
        target = (
            ".trash/Personal AI Learning Assistant/"
            + current.relative_path
        )
        op = self.coordination.begin_operation(
            kind="notes_studio_trash",
            target_path=current.relative_path,
            before_hash=current_hash,
        )
        try:
            self.store.move(
                current.relative_path,
                target,
                expected_hash=current_hash,
            )
            self.coordination.mark_file_applied(
                op.id,
                after_hash=current_hash,
            )
            view = self.notes.update_path_and_trash(
                note_id,
                relative_path=target,
                path_key=normalized_note_path_key(target),
                trashed_at=self._now(),
                now=self._now(),
            )
            self.coordination.mark_database_committed(op.id)
            self.coordination.complete_operation(op.id)
            return view
        except Exception as exc:
            try:
                self.coordination.fail_operation(
                    op.id,
                    error=type(exc).__name__,
                )
            except Exception:
                pass
            raise

    def restore(self, note_id, relative_path, expected_hash=None):
        current = self.notes.get(note_id)
        if current.trashed_at is None:
            raise ValueError("note is not trashed")
        target = str(relative_path or "").strip().replace("\\", "/")
        if not target or target.startswith(".trash/"):
            raise ValueError("explicit restore destination is required")
        _raw, current_hash = self.store.read(current.relative_path)
        if expected_hash is not None and current_hash != str(expected_hash or ""):
            raise MarkdownConflictError(
                "note changed on disk; refresh before restoring"
            )
        op = self.coordination.begin_operation(
            kind="notes_studio_restore",
            target_path=current.relative_path,
            before_hash=current_hash,
        )
        try:
            self.store.move(
                current.relative_path,
                target,
                expected_hash=current_hash,
            )
            self.coordination.mark_file_applied(
                op.id,
                after_hash=current_hash,
            )
            view = self.notes.update_path_and_trash(
                note_id,
                relative_path=target,
                path_key=normalized_note_path_key(target),
                trashed_at=None,
                now=self._now(),
            )
            self.coordination.mark_database_committed(op.id)
            self.coordination.complete_operation(op.id)
            return view
        except Exception as exc:
            try:
                self.coordination.fail_operation(
                    op.id,
                    error=type(exc).__name__,
                )
            except Exception:
                pass
            raise
