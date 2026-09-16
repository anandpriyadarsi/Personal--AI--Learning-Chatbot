"""Phase 6.6 explainable PYQ + Exam Intelligence."""

from __future__ import annotations

import re
from datetime import date

from personal_learning_assistant.domain.exam_intelligence_models import (
    ExamIntelligenceReport,
    ExamQuestionEvidence,
    ExamTopicIntelligence,
)


class ExamIntelligenceError(RuntimeError):
    pass


_EXPLICIT_PYQ_TYPES = {
    "pyq",
    "past_paper",
    "past_exam_paper",
    "previous_year_question",
    "previous_year_questions",
    "previous_year_paper",
}
_INACTIVE_ASSESSMENT = {"cancelled", "canceled", "archived"}


def _token(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().casefold()).strip("_")


def _explicit_pyq(assessment_type, title, description):
    kind = _token(assessment_type)
    if kind in _EXPLICIT_PYQ_TYPES:
        return True
    text = " ".join(
        (
            str(title or "").strip().casefold(),
            str(description or "").strip().casefold(),
        )
    )
    return (
        " pyq " in " {} ".format(text)
        or "previous year" in text
        or "past paper" in text
        or "past exam paper" in text
    )


def _source_label(row):
    raw = str(row["raw_source_label"] or "").strip()
    locator = str(row["locator"] or "").strip()
    page = row["page_number"]
    if raw:
        label = raw
    elif row["document_id"] is not None:
        label = "document:{}".format(row["document_id"])
    elif row["resource_id"] is not None:
        label = "resource:{}".format(row["resource_id"])
    elif row["note_id"] is not None:
        label = "note:{}".format(row["note_id"])
    else:
        label = "source"
    if page is not None:
        label += " page {}".format(int(page))
    if locator:
        label += " [{}]".format(locator)
    return label


def _parse_due(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _topic_status_points(status):
    return {
        "weak": 12.0,
        "not_started": 10.0,
        "learning": 8.0,
        "in_progress": 8.0,
        "revision": 6.0,
        "review": 6.0,
        "mastered": 0.0,
        "completed": 0.0,
    }.get(_token(status), 3.0)


class ExamIntelligenceService:
    """Analyze formal question evidence without predicting future questions."""

    def __init__(self, repository):
        self.repository = repository

    def analyze(
        self,
        course_code: str,
        *,
        as_of=None,
        target_assessment_id=None,
        limit_topics=12,
        limit_questions=25,
    ):
        as_of = as_of or date.today()
        if int(limit_topics) <= 0 or int(limit_questions) <= 0:
            raise ExamIntelligenceError("report limits must be positive")

        course = self.repository.course_by_code(course_code)
        course_id = str(course["id"])
        assessments = self.repository.assessments_for_course(course_id)
        assessment_map = {str(row["id"]): row for row in assessments}

        target = None
        target_topic_ids = set()
        if target_assessment_id:
            target = self.repository.assessment(course_id, target_assessment_id)
            target_topic_ids = set(
                self.repository.target_topic_ids(str(target["id"]))
            )

        explicit_pyq_assessment_ids = {
            str(row["id"])
            for row in assessments
            if _explicit_pyq(
                row["assessment_type"], row["title"], row["description"]
            )
        }

        question_records = []
        accepted_mapped_count = 0
        proposed_only_count = 0
        unmapped_count = 0
        source_backed_count = 0

        for row in self.repository.questions_for_course(course_id):
            question_id = str(row["id"])
            mappings = self.repository.mappings_for_question(question_id)
            accepted_topic_ids = tuple(
                sorted(
                    {
                        str(item["topic_id"])
                        for item in mappings
                        if str(item["state"]).strip().casefold() == "accepted"
                    }
                )
            )
            if accepted_topic_ids:
                mapping_state = "accepted"
                accepted_mapped_count += 1
            elif mappings:
                mapping_state = "proposed_only"
                proposed_only_count += 1
            else:
                mapping_state = "unmapped"
                unmapped_count += 1

            sources = self.repository.sources_for_question(question_id)
            if sources:
                source_backed_count += 1
            source_labels = tuple(_source_label(item) for item in sources)
            attempts = self.repository.attempts_for_question(question_id)
            unresolved = self.repository.unresolved_mistake_count(question_id)
            assessment_id = str(row["assessment_id"])
            question_records.append(
                ExamQuestionEvidence(
                    question_id=question_id,
                    assessment_id=assessment_id,
                    assessment_title=str(row["assessment_title"]),
                    assessment_type=str(row["assessment_type"]),
                    explicit_pyq=assessment_id in explicit_pyq_assessment_ids,
                    ordinal=int(row["ordinal"]),
                    question_text=str(row["question_text"]),
                    max_marks_milli=(
                        None
                        if row["max_marks_milli"] is None
                        else int(row["max_marks_milli"])
                    ),
                    accepted_topic_ids=accepted_topic_ids,
                    mapping_state=mapping_state,
                    source_count=len(sources),
                    source_labels=source_labels,
                    attempt_count=len(attempts),
                    unresolved_mistake_count=unresolved,
                )
            )

        topic_rows = self.repository.topics_for_course(course_id)
        by_topic = {str(row["id"]): [] for row in topic_rows}
        for question in question_records:
            for topic_id in question.accepted_topic_ids:
                if topic_id in by_topic:
                    by_topic[topic_id].append(question)

        mapped_marks_total = sum(
            question.max_marks_milli or 0
            for question in question_records
            if question.accepted_topic_ids
        )

        topic_intelligence = []
        for topic in topic_rows:
            topic_id = str(topic["id"])
            questions = by_topic[topic_id]
            assessment_ids = {item.assessment_id for item in questions}
            total_marks = sum(item.max_marks_milli or 0 for item in questions)
            missing_marks = sum(
                1 for item in questions if item.max_marks_milli is None
            )
            explicit_pyq_count = sum(1 for item in questions if item.explicit_pyq)
            source_backed = sum(1 for item in questions if item.source_count > 0)
            attempted = sum(1 for item in questions if item.attempt_count > 0)
            mistakes = sum(item.unresolved_mistake_count for item in questions)
            target_scope = topic_id in target_topic_ids

            score = min(25.0, len(questions) * 5.0)
            reasons = []
            if questions:
                reasons.append(
                    "{} formal question(s) map here across {} assessment(s)".format(
                        len(questions), len(assessment_ids)
                    )
                )
            else:
                reasons.append("no accepted formal-question mapping currently exists")

            if mapped_marks_total > 0 and total_marks > 0:
                marks_share = total_marks / mapped_marks_total
                score += 25.0 * marks_share
                reasons.append(
                    "mapped historical marks total {} ({:.1f}% of mapped marks corpus)".format(
                        total_marks / 1000.0,
                        marks_share * 100.0,
                    )
                )
            elif total_marks > 0:
                reasons.append(
                    "mapped historical marks total {}".format(total_marks / 1000.0)
                )
            if missing_marks:
                reasons.append(
                    "{} mapped question(s) have no recorded marks".format(missing_marks)
                )

            if explicit_pyq_count:
                score += min(15.0, explicit_pyq_count * 5.0)
                reasons.append(
                    "{} question(s) come from explicitly labelled PYQ/past-paper assessments".format(
                        explicit_pyq_count
                    )
                )

            if mistakes:
                score += min(18.0, mistakes * 6.0)
                reasons.append(
                    "{} unresolved mistake event(s) exist on mapped formal questions".format(
                        mistakes
                    )
                )

            if target_scope:
                score += 25.0
                reasons.append(
                    "topic is explicitly in the selected target-assessment scope"
                )

            confidence = (
                None
                if topic["confidence"] is None
                else int(topic["confidence"])
            )
            if confidence is not None:
                confidence_points = max(0.0, (5 - confidence) * 3.0)
                score += confidence_points
                reasons.append("current topic confidence is {}/5".format(confidence))
            else:
                reasons.append("current topic confidence is not recorded")

            status = str(topic["status"])
            status_points = _topic_status_points(status)
            score += status_points
            reasons.append("current topic status is {}".format(status))

            topic_intelligence.append(
                ExamTopicIntelligence(
                    topic_id=topic_id,
                    topic_name=str(topic["name"]),
                    position=int(topic["position"]),
                    status=status,
                    confidence=confidence,
                    historical_question_count=len(questions),
                    historical_assessment_count=len(assessment_ids),
                    explicit_pyq_question_count=explicit_pyq_count,
                    total_marks_milli=total_marks,
                    missing_marks_question_count=missing_marks,
                    source_backed_question_count=source_backed,
                    attempted_question_count=attempted,
                    unresolved_mistake_count=mistakes,
                    target_assessment_in_scope=target_scope,
                    preparation_priority_score=round(score, 3),
                    reasons=tuple(reasons),
                )
            )

        topic_intelligence.sort(
            key=lambda item: (
                -item.preparation_priority_score,
                item.position,
                item.topic_name.casefold(),
                item.topic_id,
            )
        )

        question_records.sort(
            key=lambda item: (
                0 if item.explicit_pyq else 1,
                item.assessment_title.casefold(),
                item.ordinal,
                item.question_id,
            )
        )

        upcoming = 0
        for assessment in assessments:
            status = _token(assessment["status"])
            if status in _INACTIVE_ASSESSMENT:
                continue
            due = _parse_due(assessment["due_on"])
            if due is not None and due >= as_of:
                upcoming += 1

        explicit_pyq_question_count = sum(
            1 for item in question_records if item.explicit_pyq
        )

        return ExamIntelligenceReport(
            course_id=course_id,
            course_code=str(course["code"]),
            course_name=str(course["name"]),
            as_of=as_of.isoformat(),
            formal_assessment_count=len(assessments),
            formal_question_count=len(question_records),
            explicit_pyq_assessment_count=len(explicit_pyq_assessment_ids),
            explicit_pyq_question_count=explicit_pyq_question_count,
            accepted_mapped_question_count=accepted_mapped_count,
            proposed_only_question_count=proposed_only_count,
            unmapped_question_count=unmapped_count,
            source_backed_question_count=source_backed_count,
            upcoming_assessment_count=upcoming,
            target_assessment_id=(
                None if target is None else str(target["id"])
            ),
            target_assessment_title=(
                None if target is None else str(target["title"])
            ),
            topics=tuple(topic_intelligence[: int(limit_topics)]),
            questions=tuple(question_records[: int(limit_questions)]),
            prediction_performed=False,
            writes_performed=False,
        )
