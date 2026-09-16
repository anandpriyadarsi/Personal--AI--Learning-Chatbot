"""Application service for Phase 5.5 Resources 2 Core."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Optional, Sequence, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from personal_learning_assistant.domain.resources2_models import (
    CANONICAL_RESOURCE_STATUSES,
    CreateResource2Command,
    DuplicateCandidate,
    ResourceDetails,
    ResourceProgressCommand,
    ResourceProgressEvent,
    UpdateResource2Command,
)
from personal_learning_assistant.repositories.sqlite.resources2_repository import (
    Resources2ConflictError,
    SQLiteResources2Repository,
)


_ALLOWED_COURSE_ROLES = {
    "primary", "supporting", "external_course", "prerequisite",
}
_ALLOWED_TOPIC_SOURCES = {"explicit", "imported", "suggested"}
_ALLOWED_NOTE_ROLES = {
    "related", "summary", "annotation", "revision", "source", "solution",
    "worked_example", "mistake_log",
}
_ALLOWED_ASSESSMENT_ROLES = {
    "related", "source", "required_reading", "question_sheet", "preparation",
    "solution", "submission",
}
_ALLOWED_DOCUMENT_ROLES = {
    "source", "primary", "primary_file", "transcript", "supplement", "solution",
    "metadata_package",
}
_TRACKING_PARAMS = {
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src", "si",
}
_YOUTUBE_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be",
}


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _normal_title(value: str) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _youtube_video_id(uri: str) -> Optional[str]:
    try:
        parts = urlsplit(uri)
    except ValueError:
        return None
    host = (parts.hostname or "").casefold()
    if host not in _YOUTUBE_HOSTS:
        return None
    if host == "youtu.be":
        value = parts.path.strip("/").split("/", 1)[0]
        return value or None
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if query.get("v"):
        return query["v"]
    path = parts.path.strip("/").split("/")
    if len(path) >= 2 and path[0] in {"shorts", "embed", "live"}:
        return path[1] or None
    return None


def normalize_canonical_uri(value: Optional[str]) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parts = urlsplit(text)
    except ValueError:
        return text.replace("\\", "/")
    if parts.scheme.casefold() not in {"http", "https"}:
        return text.replace("\\", "/")

    video_id = _youtube_video_id(text)
    if video_id:
        return "https://www.youtube.com/watch?v={}".format(video_id)

    scheme = parts.scheme.casefold()
    host = (parts.hostname or "").casefold()
    port = parts.port
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = "{}:{}".format(host, port)
    path = parts.path or "/"
    pairs = []
    for key, val in parse_qsl(parts.query, keep_blank_values=True):
        lower = key.casefold()
        if lower.startswith("utm_") or lower in _TRACKING_PARAMS:
            continue
        pairs.append((key, val))
    pairs.sort(key=lambda item: (item[0].casefold(), item[1]))
    return urlunsplit((scheme, netloc, path, urlencode(pairs, doseq=True), ""))


class Resources2Service:
    def __init__(self, repository: SQLiteResources2Repository, *, now=_utc_now):
        self.repository = repository
        self._now = now

    @staticmethod
    def _validate_status(status: str) -> str:
        value = str(status or "").strip().casefold()
        if value not in CANONICAL_RESOURCE_STATUSES:
            raise ValueError(
                "status must be one of {}".format(
                    ", ".join(CANONICAL_RESOURCE_STATUSES)
                )
            )
        return value

    @staticmethod
    def _validate_rating(rating):
        if rating is None:
            return None
        value = int(rating)
        if value < 1 or value > 5:
            raise ValueError("rating must be 1-5 or null")
        return value

    @staticmethod
    def _validate_links(command: CreateResource2Command) -> None:
        for item in command.course_links:
            if item.role not in _ALLOWED_COURSE_ROLES:
                raise ValueError("unsupported resource-course role")
        for item in command.topic_links:
            if item.relation_source not in _ALLOWED_TOPIC_SOURCES:
                raise ValueError("unsupported resource-topic relation source")
            if item.confidence is not None and not 0 <= float(item.confidence) <= 1:
                raise ValueError("topic-link confidence must be between 0 and 1")
        for item in command.note_links:
            if item.role not in _ALLOWED_NOTE_ROLES:
                raise ValueError("unsupported resource-note role")
        for item in command.assessment_links:
            if item.role not in _ALLOWED_ASSESSMENT_ROLES:
                raise ValueError("unsupported resource-assessment role")
        for item in command.document_links:
            if item.role not in _ALLOWED_DOCUMENT_ROLES:
                raise ValueError("unsupported resource-document role")

    @staticmethod
    def _identity(
        *,
        resource_type: str,
        canonical_uri: Optional[str],
        provider: str,
        external_id: Optional[str],
        document_count: int,
        note_count: int,
    ):
        rtype = str(resource_type or "").strip()
        if not rtype:
            raise ValueError("resource_type is required")
        provider = str(provider or "").strip().casefold()
        external_id = str(external_id or "").strip() or None
        canonical_uri = normalize_canonical_uri(canonical_uri)

        video_id = _youtube_video_id(canonical_uri or "")
        if video_id:
            if not provider:
                provider = "youtube"
            if external_id is None:
                external_id = video_id

        if not canonical_uri and not (provider and external_id) and not document_count and not note_count:
            raise ValueError(
                "resource requires canonical_uri, provider+external_id, linked document, or linked note"
            )
        return rtype, canonical_uri, provider, external_id

    def get_duplicate_candidates(
        self,
        *,
        title: str,
        canonical_uri: Optional[str],
        provider: str,
        external_id: Optional[str],
        document_ids: Sequence[str] = (),
    ) -> Tuple[DuplicateCandidate, ...]:
        return self.repository.duplicate_candidates(
            canonical_uri=normalize_canonical_uri(canonical_uri),
            provider=str(provider or "").strip().casefold(),
            external_id=str(external_id or "").strip() or None,
            document_ids=tuple(document_ids),
            normalized_title=_normal_title(title),
        )

    def create_resource(self, command: CreateResource2Command) -> ResourceDetails:
        title = str(command.title or "").strip()
        if not title:
            raise ValueError("title is required")
        self._validate_links(command)
        status = self._validate_status(command.status)
        rating = self._validate_rating(command.rating)
        rtype, canonical_uri, provider, external_id = self._identity(
            resource_type=command.resource_type,
            canonical_uri=command.canonical_uri,
            provider=command.provider,
            external_id=command.external_id,
            document_count=len(command.document_links),
            note_count=len(command.note_links),
        )
        document_ids = tuple(item.document_id for item in command.document_links)
        duplicates = self.get_duplicate_candidates(
            title=title,
            canonical_uri=canonical_uri,
            provider=provider,
            external_id=external_id,
            document_ids=document_ids,
        )
        if duplicates and not command.allow_duplicate:
            raise Resources2ConflictError(
                "potential duplicate resource(s) require explicit review: {}".format(
                    ", ".join(item.resource_id for item in duplicates)
                )
            )

        resource_id = str(uuid.uuid4())
        now = self._now()
        event = {
            "id": str(uuid.uuid4()),
            "event_type": "resource.created",
            "entity_type": "resource",
            "entity_id": resource_id,
            "payload": {
                "resource_type": rtype,
                "status": status,
            },
            "created_at": now,
        }
        try:
            resource = self.repository.create_resource(
                resource_id=resource_id,
                resource_type=rtype,
                title=title,
                canonical_uri=canonical_uri,
                provider=provider,
                external_id=external_id,
                status=status,
                rating=rating,
                quality_note=str(command.quality_note or ""),
                now=now,
                course_links=command.course_links,
                topic_links=command.topic_links,
                note_links=command.note_links,
                assessment_links=command.assessment_links,
                document_links=command.document_links,
                outbox_event=event,
            )
        except Exception as error:
            # Exact provider/external identity is protected by the existing
            # partial UNIQUE index. Surface it as a domain conflict.
            if "UNIQUE constraint failed: resources.provider, resources.external_id" in str(error):
                raise Resources2ConflictError(
                    "provider + external_id already belongs to another resource"
                ) from error
            raise

        return ResourceDetails(
            resource=resource,
            relations=self.repository.get_relations(resource_id),
            history=self.repository.get_history(resource_id),
        )

    def update_resource(self, command: UpdateResource2Command) -> ResourceDetails:
        current = self.repository.get_resource(command.resource_id)
        title = current.title if command.title is None else str(command.title).strip()
        if not title:
            raise ValueError("title is required")
        rtype = current.resource_type if command.resource_type is None else str(command.resource_type).strip()
        provider = current.provider if command.provider is None else str(command.provider).strip().casefold()
        external_id = current.external_id if command.external_id is None else (str(command.external_id).strip() or None)
        canonical_uri = current.canonical_uri if command.canonical_uri is None else normalize_canonical_uri(command.canonical_uri)
        rating = current.rating if command.rating is None else self._validate_rating(command.rating)
        quality_note = current.quality_note if command.quality_note is None else str(command.quality_note)

        duplicates = tuple(
            item
            for item in self.get_duplicate_candidates(
                title=title,
                canonical_uri=canonical_uri,
                provider=provider,
                external_id=external_id,
            )
            if item.resource_id != current.id
        )
        if duplicates:
            raise Resources2ConflictError(
                "updated identity conflicts with another resource candidate"
            )

        now = self._now()
        event = {
            "id": str(uuid.uuid4()),
            "event_type": "resource.updated",
            "entity_type": "resource",
            "entity_id": current.id,
            "payload": {},
            "created_at": now,
        }
        resource = self.repository.update_resource(
            resource_id=current.id,
            resource_type=rtype,
            title=title,
            canonical_uri=canonical_uri,
            provider=provider,
            external_id=external_id,
            rating=rating,
            quality_note=quality_note,
            now=now,
            outbox_event=event,
        )
        return ResourceDetails(
            resource=resource,
            relations=self.repository.get_relations(current.id),
            history=self.repository.get_history(current.id),
        )

    def replace_relationships(self, resource_id: str, command: CreateResource2Command):
        self._validate_links(command)
        now = self._now()
        event = {
            "id": str(uuid.uuid4()),
            "event_type": "resource.relationships_changed",
            "entity_type": "resource",
            "entity_id": resource_id,
            "payload": {},
            "created_at": now,
        }
        return self.repository.set_relationships(
            resource_id=resource_id,
            course_links=command.course_links,
            topic_links=command.topic_links,
            note_links=command.note_links,
            assessment_links=command.assessment_links,
            document_links=command.document_links,
            now=now,
            outbox_event=event,
        )

    def record_progress(self, command: ResourceProgressCommand) -> ResourceDetails:
        status = self._validate_status(command.status)
        value = None if command.value is None else float(command.value)
        max_value = None if command.max_value is None else float(command.max_value)
        if max_value is not None and max_value < 0:
            raise ValueError("max_value must be non-negative")
        if value is not None and max_value is not None and value > max_value:
            raise ValueError("progress value cannot exceed max_value")
        event = ResourceProgressEvent(
            id=str(uuid.uuid4()),
            resource_id=command.resource_id,
            occurred_at=str(command.occurred_at),
            status=status,
            value=value,
            max_value=max_value,
            unit=str(command.unit or ""),
            position=str(command.position or ""),
            note=str(command.note or ""),
        )
        now = self._now()
        outbox = {
            "id": str(uuid.uuid4()),
            "event_type": "resource.progress_recorded",
            "entity_type": "resource",
            "entity_id": command.resource_id,
            "payload": {"status": status},
            "created_at": now,
        }
        resource = self.repository.append_progress(
            event=event,
            now=now,
            outbox_event=outbox,
        )
        return ResourceDetails(
            resource=resource,
            relations=self.repository.get_relations(command.resource_id),
            history=self.repository.get_history(command.resource_id),
        )

    def complete_resource(
        self,
        resource_id: str,
        *,
        occurred_at: str,
        value: Optional[float] = None,
        max_value: Optional[float] = None,
        unit: str = "",
        position: str = "",
        note: str = "",
    ) -> ResourceDetails:
        return self.record_progress(
            ResourceProgressCommand(
                resource_id=resource_id,
                status="completed",
                occurred_at=occurred_at,
                value=value,
                max_value=max_value,
                unit=unit,
                position=position,
                note=note,
            )
        )

    def reopen_resource(self, resource_id: str, *, occurred_at: str, note: str = ""):
        return self.record_progress(
            ResourceProgressCommand(
                resource_id=resource_id,
                status="in_progress",
                occurred_at=occurred_at,
                note=note,
            )
        )

    def set_rating(self, resource_id: str, rating: Optional[int], quality_note: str = ""):
        current = self.repository.get_resource(resource_id)
        return self.update_resource(
            UpdateResource2Command(
                resource_id=resource_id,
                rating=rating,
                quality_note=quality_note if quality_note else current.quality_note,
            )
        )

    def archive_resource(self, resource_id: str):
        now = self._now()
        return self.repository.set_lifecycle(
            resource_id,
            status="archived",
            archived_at=now,
            deleted_at=None,
            now=now,
            outbox_event={
                "id": str(uuid.uuid4()),
                "event_type": "resource.archived",
                "entity_type": "resource",
                "entity_id": resource_id,
                "payload": {},
                "created_at": now,
            },
        )

    def trash_resource(self, resource_id: str):
        now = self._now()
        current = self.repository.get_resource(resource_id)
        return self.repository.set_lifecycle(
            resource_id,
            status=current.status,
            archived_at=current.archived_at,
            deleted_at=now,
            now=now,
            outbox_event={
                "id": str(uuid.uuid4()),
                "event_type": "resource.trashed",
                "entity_type": "resource",
                "entity_id": resource_id,
                "payload": {},
                "created_at": now,
            },
        )

    def restore_resource(self, resource_id: str):
        now = self._now()
        current = self.repository.get_resource(resource_id)
        status = "saved" if current.status == "archived" else current.status
        return self.repository.set_lifecycle(
            resource_id,
            status=status,
            archived_at=None,
            deleted_at=None,
            now=now,
            outbox_event={
                "id": str(uuid.uuid4()),
                "event_type": "resource.restored",
                "entity_type": "resource",
                "entity_id": resource_id,
                "payload": {},
                "created_at": now,
            },
        )

    def get_resource(self, resource_id: str) -> ResourceDetails:
        return ResourceDetails(
            resource=self.repository.get_resource(resource_id),
            relations=self.repository.get_relations(resource_id),
            history=self.repository.get_history(resource_id),
        )

    def list_resources(self, **kwargs):
        return self.repository.list_resources(**kwargs)

    def search_resources(self, text: str):
        return self.repository.search_resources(text)

    def get_continue_learning(self):
        rows = []
        for status in ("in_progress", "paused", "needs_review"):
            rows.extend(self.repository.list_resources(status=status))
        return tuple(
            sorted(
                rows,
                key=lambda item: (item.updated_at, item.title.casefold(), item.id),
                reverse=True,
            )
        )
