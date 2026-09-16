"""Phase 6.3 explainable, read-only study navigation."""

from __future__ import annotations

from datetime import date
from typing import Optional

from personal_learning_assistant.domain.knowledge_navigator_models import (
    KnowledgeNavigatorResult,
    StudySourceRecommendation,
    StudyTopicRecommendation,
)


class KnowledgeNavigatorError(RuntimeError):
    pass


_INACTIVE_ASSESSMENT = {"completed", "done", "cancelled", "canceled", "archived"}
_COMPLETED_RESOURCE = {"completed", "done"}
_IN_PROGRESS_RESOURCE = {"in_progress", "learning", "started", "active"}


def _parse_date(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _days_until(value, as_of):
    parsed = _parse_date(value)
    if parsed is None:
        return None
    return (parsed - as_of).days


def _topic_base(status, confidence):
    status_key = str(status or "").strip().casefold()
    status_points = {
        "learning": 35.0,
        "in_progress": 35.0,
        "not_started": 30.0,
        "revision": 25.0,
        "review": 25.0,
        "weak": 40.0,
        "mastered": 5.0,
        "completed": 5.0,
    }.get(status_key, 20.0)
    if confidence is None:
        confidence_points = 15.0
    else:
        confidence_points = max(0.0, min(40.0, (5 - int(confidence)) * 8.0))
    return status_points + confidence_points


def _assessment_urgency(days):
    if days is None or days < 0:
        return 0.0
    if days <= 3:
        return 35.0
    if days <= 7:
        return 25.0
    if days <= 14:
        return 15.0
    if days <= 30:
        return 5.0
    return 0.0


class KnowledgeNavigatorService:
    """Produce deterministic recommendations without writing academic state."""

    def __init__(self, repository):
        self.repository = repository

    def navigate(
        self,
        course_code: str,
        *,
        topic_name: Optional[str] = None,
        as_of: Optional[date] = None,
        limit_topics: int = 5,
        limit_sources: int = 5,
    ) -> KnowledgeNavigatorResult:
        as_of = as_of or date.today()
        if limit_topics <= 0 or limit_sources <= 0:
            raise KnowledgeNavigatorError("limits must be positive")

        course = self.repository.course_by_code(course_code)
        if course is None:
            raise KnowledgeNavigatorError(
                "course code not found: {}".format(course_code)
            )
        course_id = str(course["id"])

        focused = None
        if topic_name:
            focused = self.repository.topic_by_name(course_id, topic_name)
            if focused is None:
                raise KnowledgeNavigatorError(
                    "topic not found in {}: {}".format(course_code, topic_name)
                )
            topic_rows = (focused,)
        else:
            topic_rows = self.repository.topics_for_course(course_id)

        recommendations = [
            self._topic_recommendation(
                course_id,
                row,
                as_of=as_of,
                limit_sources=limit_sources,
            )
            for row in topic_rows
        ]
        recommendations.sort(
            key=lambda item: (
                -item.priority_score,
                item.position,
                item.topic_name.casefold(),
                item.topic_id,
            )
        )
        recommendations = recommendations[: int(limit_topics)]

        return KnowledgeNavigatorResult(
            course_id=course_id,
            course_code=str(course["code"]),
            course_name=str(course["name"]),
            as_of=as_of.isoformat(),
            focused_topic_id=None if focused is None else str(focused["id"]),
            topic_count=len(recommendations),
            topics=tuple(recommendations),
            writes_performed=False,
        )

    def _topic_recommendation(self, course_id, row, *, as_of, limit_sources):
        topic_id = str(row["id"])
        status = str(row["status"])
        confidence = None if row["confidence"] is None else int(row["confidence"])

        score = _topic_base(status, confidence)
        reasons = [
            "topic status is {}".format(status or "unknown"),
            (
                "confidence is not recorded"
                if confidence is None
                else "confidence is {}/5".format(confidence)
            ),
        ]

        assessments = []
        for item in self.repository.assessments_for_topic(course_id, topic_id):
            if str(item["status"] or "").strip().casefold() in _INACTIVE_ASSESSMENT:
                continue
            days = _days_until(item["due_on"], as_of)
            assessments.append((item, days))
        future = [(item, days) for item, days in assessments if days is None or days >= 0]
        dated_future = [(item, days) for item, days in future if days is not None]
        nearest_due = None
        if dated_future:
            item, days = min(dated_future, key=lambda pair: (pair[1], str(pair[0]["id"])))
            nearest_due = str(item["due_on"])
            urgency = _assessment_urgency(days)
            score += urgency
            if urgency:
                reasons.append(
                    "assessment '{}' is due in {} day(s)".format(
                        item["title"], days
                    )
                )
        if future and not dated_future:
            reasons.append("linked active assessment has no recorded due date")

        mistakes = self.repository.unresolved_mistake_count(topic_id)
        if mistakes:
            score += min(25.0, mistakes * 7.0)
            reasons.append(
                "{} unresolved mistake event(s) are linked to this topic".format(
                    mistakes
                )
            )

        memory_count = self.repository.active_memory_count(topic_id)
        if memory_count:
            reasons.append(
                "{} active learning-memory entr{} linked to this topic".format(
                    memory_count, "y is" if memory_count == 1 else "ies are"
                )
            )

        planned = self.repository.planned_item_count(topic_id, as_of.isoformat())
        if planned:
            reasons.append(
                "{} upcoming study-plan item(s) already cover this topic".format(
                    planned
                )
            )

        study_minutes = self.repository.topic_study_minutes(topic_id)
        if study_minutes:
            reasons.append(
                "{} recorded study minute(s) exist for this topic".format(
                    study_minutes
                )
            )

        sources = self._sources(
            course_id,
            topic_id,
            as_of=as_of,
            limit_sources=limit_sources,
        )
        if not sources:
            reasons.append("no linked note/resource candidate is currently registered")

        return StudyTopicRecommendation(
            topic_id=topic_id,
            topic_name=str(row["name"]),
            position=int(row["position"]),
            status=status,
            confidence=confidence,
            priority_score=round(score, 3),
            reasons=tuple(reasons),
            nearest_due_on=nearest_due,
            upcoming_assessment_count=len(future),
            unresolved_mistake_count=mistakes,
            active_memory_count=memory_count,
            planned_item_count=planned,
            study_minutes=study_minutes,
            sources=tuple(sources),
        )

    def _sources(self, course_id, topic_id, *, as_of, limit_sources):
        candidates = []

        for row in self.repository.resource_candidates(course_id, topic_id):
            score = 0.0
            reasons = []
            if int(row["direct_topic"]):
                score += 45.0
                reasons.append("directly linked to this topic")
            elif int(row["direct_course"]):
                score += 15.0
                reasons.append("linked to the course")

            status = str(row["status"] or "")
            status_key = status.strip().casefold()
            if status_key in _IN_PROGRESS_RESOURCE:
                score += 20.0
                reasons.append("resource is already in progress")
            elif status_key in _COMPLETED_RESOURCE:
                score -= 20.0
                reasons.append("resource is already completed")
            else:
                score += 10.0
                reasons.append("resource is available to start")

            progress = self.repository.latest_resource_progress(str(row["id"]))
            progress_status = ""
            progress_value = None
            progress_max = None
            progress_unit = ""
            if progress is not None:
                progress_status = str(progress["status"] or "")
                progress_value = (
                    None if progress["value"] is None else float(progress["value"])
                )
                progress_max = (
                    None
                    if progress["max_value"] is None
                    else float(progress["max_value"])
                )
                progress_unit = str(progress["unit"] or "")
                if progress_status.strip().casefold() in _IN_PROGRESS_RESOURCE:
                    score += 8.0
                    reasons.append("latest progress event is in progress")
                if (
                    progress_value is not None
                    and progress_max not in (None, 0.0)
                    and progress_value < progress_max
                ):
                    score += 5.0
                    reasons.append("resource has unfinished recorded progress")

            chunks = self.repository.resource_current_chunk_count(str(row["id"]))
            if chunks:
                score += 20.0
                reasons.append(
                    "{} current knowledge chunk(s) are retrievable".format(chunks)
                )

            for assessment in self.repository.resource_upcoming_assessments(
                str(row["id"]), course_id
            ):
                if str(assessment["status"] or "").strip().casefold() in _INACTIVE_ASSESSMENT:
                    continue
                days = _days_until(assessment["due_on"], as_of)
                if days is not None and 0 <= days <= 14:
                    score += 12.0
                    reasons.append(
                        "linked to assessment '{}' due in {} day(s)".format(
                            assessment["title"], days
                        )
                    )
                    break

            rating = None if row["rating"] is None else int(row["rating"])
            if rating is not None:
                score += rating * 2.0
                reasons.append("resource rating is {}/5".format(rating))

            study_minutes = self.repository.resource_study_minutes(str(row["id"]))
            candidates.append(
                StudySourceRecommendation(
                    source_kind="resource",
                    source_id=str(row["id"]),
                    title=str(row["title"]),
                    score=round(score, 3),
                    reasons=tuple(reasons),
                    status=status,
                    provider=str(row["provider"] or ""),
                    resource_type=str(row["resource_type"] or ""),
                    progress_status=progress_status,
                    progress_value=progress_value,
                    progress_max_value=progress_max,
                    progress_unit=progress_unit,
                    current_chunk_count=chunks,
                    study_minutes=study_minutes,
                )
            )

        for row in self.repository.note_candidates(course_id, topic_id):
            score = 0.0
            reasons = []
            if int(row["direct_topic"]):
                score += 45.0
                reasons.append("note is directly linked to this topic")
            elif int(row["direct_course"]):
                score += 15.0
                reasons.append("note is linked to the course")
            if row["pinned_at"] is not None:
                score += 10.0
                reasons.append("note is pinned")
            revision_status = str(row["revision_status"] or "")
            if revision_status.strip().casefold() in {"reviewed", "complete", "completed"}:
                score += 5.0
                reasons.append("note metadata says it has been reviewed")
            candidates.append(
                StudySourceRecommendation(
                    source_kind="note",
                    source_id=str(row["id"]),
                    title=str(row["title"]),
                    score=round(score, 3),
                    reasons=tuple(reasons),
                    status=revision_status,
                )
            )

        candidates.sort(
            key=lambda item: (
                -item.score,
                0 if item.source_kind == "note" else 1,
                item.title.casefold(),
                item.source_id,
            )
        )
        return candidates[: int(limit_sources)]
