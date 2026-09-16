"""Phase 6.4 explicit lecture start/pause/resume/finish orchestration."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from personal_learning_assistant.domain.lecture_learning_models import (
    LectureLearningActionResult,
    LectureLearningSnapshot,
    LectureStudySegment,
)
from personal_learning_assistant.domain.tutor_models import TutorSessionSpec
from personal_learning_assistant.repositories.sqlite.lecture_learning_repository import (
    LectureLearningConflictError,
)


class LectureLearningError(RuntimeError):
    pass


def _utc_now():
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _new_id(prefix):
    return "{}-{}".format(prefix, uuid.uuid4())


def _parse_utc(value: str):
    text = str(value or "").strip()
    if not text:
        raise LectureLearningError("timestamp is required")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        result = datetime.fromisoformat(text)
    except ValueError as error:
        raise LectureLearningError("invalid ISO timestamp: {}".format(value)) from error
    if result.tzinfo is None:
        raise LectureLearningError("lecture timestamps must include timezone information")
    return result.astimezone(timezone.utc)


def _elapsed_minutes(started_at: str, ended_at: str) -> int:
    start = _parse_utc(started_at)
    end = _parse_utc(ended_at)
    seconds = (end - start).total_seconds()
    if seconds < 0:
        raise LectureLearningError("lecture end time is earlier than start time")
    return int(seconds // 60)


class LectureLearningService:
    """Explicit event-driven lecture learning.

    Time is measured only between explicit start/resume and pause/finish calls.
    Playback activity is never guessed.
    """

    def __init__(self, repository, *, now=_utc_now, id_factory=_new_id):
        self.repository = repository
        self._now = now
        self._id_factory = id_factory

    def _resolved_scope(self, resource_id, *, course_id=None, topic_id=None):
        self.repository.resource(resource_id)
        courses = self.repository.course_ids(resource_id)
        topics = self.repository.topic_ids(resource_id)

        if course_id is not None:
            course_id = str(course_id)
            if course_id not in courses:
                raise LectureLearningError(
                    "selected course is not linked to this lecture resource"
                )
        elif len(courses) == 1:
            course_id = courses[0]
        elif len(courses) == 0:
            course_id = None
        else:
            raise LectureLearningError(
                "lecture is linked to multiple courses; choose course explicitly"
            )

        if topic_id is not None:
            topic_id = str(topic_id)
            if topic_id not in topics:
                raise LectureLearningError(
                    "selected topic is not linked to this lecture resource"
                )
            if course_id and not self.repository.topic_belongs_to_course(
                topic_id, course_id
            ):
                raise LectureLearningError(
                    "selected topic does not belong to selected course"
                )
        elif len(topics) == 1:
            candidate = topics[0]
            if course_id is None or self.repository.topic_belongs_to_course(
                candidate, course_id
            ):
                topic_id = candidate
            else:
                topic_id = None
        else:
            # Multiple reviewed topic links are common for lectures. Do not guess
            # which one the student is studying in this segment.
            topic_id = None

        return course_id, topic_id

    @staticmethod
    def _validate_progress(value, max_value, unit):
        value = None if value is None else float(value)
        max_value = None if max_value is None else float(max_value)
        if max_value is not None and max_value < 0:
            raise LectureLearningError("max_value must be non-negative")
        if value is not None and value < 0:
            raise LectureLearningError("progress value must be non-negative")
        if value is not None and max_value is not None and value > max_value:
            raise LectureLearningError("progress value cannot exceed max_value")
        return value, max_value, str(unit or "")

    def _progress_fields(
        self,
        resource_id,
        *,
        position=None,
        value=None,
        max_value=None,
        unit=None,
    ):
        latest = self.repository.latest_progress(resource_id)
        if latest is None:
            latest_position = ""
            latest_value = None
            latest_max = None
            latest_unit = ""
        else:
            latest_position = str(latest["position"] or "")
            latest_value = (
                None if latest["value"] is None else float(latest["value"])
            )
            latest_max = (
                None if latest["max_value"] is None else float(latest["max_value"])
            )
            latest_unit = str(latest["unit"] or "")

        resolved_position = (
            latest_position if position is None else str(position or "")
        )
        resolved_value = latest_value if value is None else value
        resolved_max = latest_max if max_value is None else max_value
        resolved_unit = latest_unit if unit is None else str(unit or "")
        resolved_value, resolved_max, resolved_unit = self._validate_progress(
            resolved_value, resolved_max, resolved_unit
        )
        return resolved_position, resolved_value, resolved_max, resolved_unit

    def snapshot(self, resource_id: str):
        resource = self.repository.resource(resource_id)
        courses = self.repository.course_ids(resource_id)
        topics = self.repository.topic_ids(resource_id)
        latest = self.repository.latest_progress(resource_id)
        active = self.repository.open_segment(resource_id)
        segments = self.repository.segments(resource_id)

        position = "" if latest is None else str(latest["position"] or "")
        value = (
            None
            if latest is None or latest["value"] is None
            else float(latest["value"])
        )
        max_value = (
            None
            if latest is None or latest["max_value"] is None
            else float(latest["max_value"])
        )
        unit = "" if latest is None else str(latest["unit"] or "")

        status = str(resource["status"])
        if active is not None:
            next_action = "pause_or_checkpoint"
        elif status == "paused":
            next_action = "resume"
        elif status == "completed":
            next_action = "completed"
        else:
            next_action = "start"

        return LectureLearningSnapshot(
            resource_id=str(resource["id"]),
            title=str(resource["title"]),
            resource_type=str(resource["resource_type"]),
            provider=str(resource["provider"] or ""),
            canonical_uri=(
                None
                if resource["canonical_uri"] is None
                else str(resource["canonical_uri"])
            ),
            external_id=(
                None if resource["external_id"] is None else str(resource["external_id"])
            ),
            status=status,
            course_ids=courses,
            topic_ids=topics,
            current_position=position,
            progress_value=value,
            progress_max_value=max_value,
            progress_unit=unit,
            total_study_minutes=self.repository.total_study_minutes(resource_id),
            segment_count=len(segments),
            active_session_id=(
                None if active is None else str(active["id"])
            ),
            active_started_at=(
                None if active is None else str(active["started_at"])
            ),
            current_chunk_count=self.repository.current_chunk_count(resource_id),
            next_action=next_action,
        )

    def start(
        self,
        resource_id: str,
        *,
        course_id=None,
        topic_id=None,
        position=None,
        value=None,
        max_value=None,
        unit=None,
        note="",
    ):
        current = self.snapshot(resource_id)
        if current.active_session_id is not None:
            raise LectureLearningError("lecture already has an active study session")
        if current.status == "completed":
            raise LectureLearningError(
                "completed lecture cannot be restarted through normal learning mode"
            )

        course_id, topic_id = self._resolved_scope(
            resource_id, course_id=course_id, topic_id=topic_id
        )
        position, value, max_value, unit = self._progress_fields(
            resource_id,
            position=position,
            value=value,
            max_value=max_value,
            unit=unit,
        )
        now = self._now()
        segment_id = self._id_factory("lecture-session")
        self.repository.start_segment(
            segment_id=segment_id,
            resource_id=resource_id,
            started_at=now,
            course_id=course_id,
            topic_id=topic_id,
            note=str(note or ""),
            progress_event_id=self._id_factory("resource-progress"),
            position=position,
            value=value,
            max_value=max_value,
            unit=unit,
            outbox_event_id=self._id_factory("outbox"),
        )
        return LectureLearningActionResult(
            action="start",
            segment_id=segment_id,
            recorded_minutes=0,
            snapshot=self.snapshot(resource_id),
        )

    def checkpoint(
        self,
        resource_id: str,
        *,
        position=None,
        value=None,
        max_value=None,
        unit=None,
        note="",
    ):
        if self.repository.open_segment(resource_id) is None:
            raise LectureLearningError(
                "checkpoint requires an active lecture study session"
            )
        position, value, max_value, unit = self._progress_fields(
            resource_id,
            position=position,
            value=value,
            max_value=max_value,
            unit=unit,
        )
        self.repository.checkpoint(
            resource_id=resource_id,
            occurred_at=self._now(),
            progress_event_id=self._id_factory("resource-progress"),
            position=position,
            value=value,
            max_value=max_value,
            unit=unit,
            note=str(note or ""),
            outbox_event_id=self._id_factory("outbox"),
        )
        return LectureLearningActionResult(
            action="checkpoint",
            segment_id=str(self.repository.open_segment(resource_id)["id"]),
            recorded_minutes=0,
            snapshot=self.snapshot(resource_id),
        )

    def pause(
        self,
        resource_id: str,
        *,
        position=None,
        value=None,
        max_value=None,
        unit=None,
        note="",
    ):
        active = self.repository.open_segment(resource_id)
        if active is None:
            raise LectureLearningError("pause requires an active lecture study session")
        ended_at = self._now()
        duration = _elapsed_minutes(str(active["started_at"]), ended_at)
        position, value, max_value, unit = self._progress_fields(
            resource_id,
            position=position,
            value=value,
            max_value=max_value,
            unit=unit,
        )
        segment_id = self.repository.close_segment(
            resource_id=resource_id,
            ended_at=ended_at,
            duration_minutes=duration,
            final_status="paused",
            outcome="paused",
            confidence=None,
            session_note=str(note or ""),
            progress_event_id=self._id_factory("resource-progress"),
            position=position,
            value=value,
            max_value=max_value,
            unit=unit,
            progress_note=str(note or ""),
            outbox_event_id=self._id_factory("outbox"),
        )
        return LectureLearningActionResult(
            action="pause",
            segment_id=segment_id,
            recorded_minutes=duration,
            snapshot=self.snapshot(resource_id),
        )

    def resume(
        self,
        resource_id: str,
        *,
        course_id=None,
        topic_id=None,
        position=None,
        value=None,
        max_value=None,
        unit=None,
        note="",
    ):
        current = self.snapshot(resource_id)
        if current.active_session_id is not None:
            raise LectureLearningError("lecture already has an active study session")
        if current.status != "paused":
            raise LectureLearningError(
                "resume requires the latest lecture status to be paused"
            )
        result = self.start(
            resource_id,
            course_id=course_id,
            topic_id=topic_id,
            position=position,
            value=value,
            max_value=max_value,
            unit=unit,
            note=note,
        )
        return LectureLearningActionResult(
            action="resume",
            segment_id=result.segment_id,
            recorded_minutes=0,
            snapshot=result.snapshot,
        )

    def finish(
        self,
        resource_id: str,
        *,
        position=None,
        value=None,
        max_value=None,
        unit=None,
        confidence=None,
        note="",
    ):
        current = self.snapshot(resource_id)
        if current.status == "completed" and current.active_session_id is None:
            return LectureLearningActionResult(
                action="finish",
                segment_id=None,
                recorded_minutes=0,
                snapshot=current,
            )

        if confidence is not None:
            confidence = int(confidence)
            if confidence < 0 or confidence > 5:
                raise LectureLearningError("confidence must be between 0 and 5")

        position, value, max_value, unit = self._progress_fields(
            resource_id,
            position=position,
            value=value,
            max_value=max_value,
            unit=unit,
        )
        active = self.repository.open_segment(resource_id)
        if active is not None:
            ended_at = self._now()
            duration = _elapsed_minutes(str(active["started_at"]), ended_at)
            segment_id = self.repository.close_segment(
                resource_id=resource_id,
                ended_at=ended_at,
                duration_minutes=duration,
                final_status="completed",
                outcome="completed",
                confidence=confidence,
                session_note=str(note or ""),
                progress_event_id=self._id_factory("resource-progress"),
                position=position,
                value=value,
                max_value=max_value,
                unit=unit,
                progress_note=str(note or ""),
                outbox_event_id=self._id_factory("outbox"),
            )
        else:
            if current.status != "paused":
                raise LectureLearningError(
                    "finish requires an active or paused lecture session"
                )
            ended_at = self._now()
            duration = 0
            segment_id = None
            self.repository.complete_without_open_segment(
                resource_id=resource_id,
                occurred_at=ended_at,
                progress_event_id=self._id_factory("resource-progress"),
                position=position,
                value=value,
                max_value=max_value,
                unit=unit,
                note=str(note or ""),
                outbox_event_id=self._id_factory("outbox"),
            )

        return LectureLearningActionResult(
            action="finish",
            segment_id=segment_id,
            recorded_minutes=duration,
            snapshot=self.snapshot(resource_id),
        )

    def lecture_tutor_session(
        self,
        resource_id: str,
        tutor_session_service,
        *,
        source_policy="source_only",
    ):
        snapshot = self.snapshot(resource_id)
        course_id = snapshot.course_ids[0] if len(snapshot.course_ids) == 1 else None
        topic_id = snapshot.topic_ids[0] if len(snapshot.topic_ids) == 1 else None
        return tutor_session_service.create_session(
            TutorSessionSpec(
                mode="lecture",
                source_policy=source_policy,
                course_id=course_id,
                topic_id=topic_id,
                resource_id=resource_id,
                title="Lecture: {}".format(snapshot.title),
                metadata={
                    "origin": "phase6.4_lecture_learning",
                    "lecture_resource_id": resource_id,
                    "resume_position": snapshot.current_position,
                },
            )
        )
