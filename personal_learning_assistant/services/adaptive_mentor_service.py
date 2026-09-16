"""Phase 6.7 explainable Adaptive Mentor orchestration."""

from __future__ import annotations

from datetime import date

from personal_learning_assistant.domain.adaptive_mentor_models import (
    AdaptiveMentorReport,
    MentorAction,
    MentorTopicState,
)


class AdaptiveMentorError(RuntimeError):
    pass


_LOW_CONFIDENCE_STATUSES = {
    "weak",
    "not_started",
    "learning",
    "in_progress",
    "revision",
    "review",
}
_ACTIVE_RESOURCE_STATUSES = {
    "in_progress",
    "learning",
    "started",
    "active",
    "paused",
}


def _token(value):
    return str(value or "").strip().casefold()


def _combine_reasons(*groups, limit=10):
    result = []
    seen = set()
    for group in groups:
        for raw in group:
            value = str(raw).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)
            if len(result) >= limit:
                return tuple(result)
    return tuple(result)


class AdaptiveMentorService:
    """Compose Phase 6 evidence streams into advisory next actions.

    This service is deterministic and read-only. It never calls an LLM and never
    mutates mastery, memory, progress, plans, resources, practice, or assessments.
    """

    def __init__(
        self,
        *,
        navigator_service,
        exam_intelligence_service,
        evidence_repository,
    ):
        self.navigator_service = navigator_service
        self.exam_intelligence_service = exam_intelligence_service
        self.evidence_repository = evidence_repository

    def advise(
        self,
        course_code: str,
        *,
        as_of=None,
        target_assessment_id=None,
        limit_topics=5,
        max_actions=10,
    ):
        as_of = as_of or date.today()
        if int(limit_topics) <= 0 or int(max_actions) <= 0:
            raise AdaptiveMentorError("mentor limits must be positive")

        navigator = self.navigator_service.navigate(
            course_code,
            as_of=as_of,
            limit_topics=max(int(limit_topics), 1),
            limit_sources=5,
        )
        exam = self.exam_intelligence_service.analyze(
            course_code,
            as_of=as_of,
            target_assessment_id=target_assessment_id,
            limit_topics=100,
            limit_questions=200,
        )

        if navigator.course_id != exam.course_id:
            raise AdaptiveMentorError(
                "navigator and exam intelligence resolved different courses"
            )

        exam_topics = {item.topic_id: item for item in exam.topics}
        practice_available = self.evidence_repository.practice_history_available()

        topic_states = []
        candidates = []
        for topic in navigator.topics:
            exam_topic = exam_topics.get(topic.topic_id)
            exam_score = (
                0.0
                if exam_topic is None
                else float(exam_topic.preparation_priority_score)
            )
            combined = round(float(topic.priority_score) + 0.55 * exam_score, 3)
            practice = self.evidence_repository.practice_summary(
                navigator.course_id,
                topic.topic_id,
            )
            target_scope = bool(
                exam_topic is not None and exam_topic.target_assessment_in_scope
            )

            state_reasons = _combine_reasons(
                topic.reasons,
                () if exam_topic is None else exam_topic.reasons,
                self._practice_reasons(practice),
            )
            state = MentorTopicState(
                topic_id=topic.topic_id,
                topic_name=topic.topic_name,
                status=topic.status,
                confidence=topic.confidence,
                navigator_priority_score=float(topic.priority_score),
                exam_priority_score=exam_score,
                combined_priority_score=combined,
                unresolved_mistake_count=topic.unresolved_mistake_count,
                active_memory_count=topic.active_memory_count,
                upcoming_assessment_count=topic.upcoming_assessment_count,
                target_assessment_in_scope=target_scope,
                practice=practice,
                reasons=state_reasons,
            )
            topic_states.append(state)

            topic_actions = self._topic_actions(
                topic,
                state,
                exam_topic,
                exam.questions,
            )
            candidates.extend(topic_actions)

        # Higher-priority topics remain grouped; within a topic the action stage
        # creates a sensible review -> tutor -> recall -> formal-practice flow.
        candidates.sort(
            key=lambda row: (
                -row["topic_priority"],
                row["stage"],
                -row["action_score"],
                row["title"].casefold(),
                row["action_type"],
            )
        )

        actions = []
        for sequence, row in enumerate(candidates[: int(max_actions)], 1):
            actions.append(
                MentorAction(
                    sequence=sequence,
                    action_type=row["action_type"],
                    topic_id=row["topic_id"],
                    topic_name=row["topic_name"],
                    title=row["title"],
                    priority_score=round(row["action_score"], 3),
                    reasons=tuple(row["reasons"]),
                    resource_id=row.get("resource_id"),
                    question_id=row.get("question_id"),
                    assessment_id=row.get("assessment_id"),
                    source_labels=tuple(row.get("source_labels", ())),
                    advisory=True,
                )
            )

        return AdaptiveMentorReport(
            course_id=navigator.course_id,
            course_code=navigator.course_code,
            course_name=navigator.course_name,
            as_of=as_of.isoformat(),
            target_assessment_id=exam.target_assessment_id,
            target_assessment_title=exam.target_assessment_title,
            practice_history_available=practice_available,
            topics=tuple(topic_states),
            actions=tuple(actions),
            llm_called=False,
            writes_performed=False,
            authoritative_state_changes=False,
        )

    @staticmethod
    def _practice_reasons(practice):
        if not practice.available:
            return ("persisted Phase 6.5 practice history is not available",)
        reasons = []
        if practice.deterministic_attempt_count == 0:
            reasons.append("no deterministic active-recall attempt is recorded")
        else:
            accuracy = practice.deterministic_accuracy
            reasons.append(
                "deterministic active-recall accuracy is {:.0f}% across {} attempt(s)".format(
                    accuracy * 100.0,
                    practice.deterministic_attempt_count,
                )
            )
        if practice.advisory_attempt_count:
            reasons.append(
                "{} free-response/advisory attempt(s) are recorded but not "
                "treated as correctness evidence".format(
                    practice.advisory_attempt_count
                )
            )
        return tuple(reasons)

    def _topic_actions(self, topic, state, exam_topic, exam_questions):
        result = []
        low_confidence = (
            topic.confidence is None
            or topic.confidence <= 2
            or _token(topic.status) in _LOW_CONFIDENCE_STATUSES
        )

        # Stage 1: continue an explicit unfinished lecture, otherwise use the
        # strongest registered note/resource when concept review is warranted.
        active_lecture = next(
            (
                source
                for source in topic.sources
                if source.source_kind == "resource"
                and source.resource_type == "external_lecture"
                and (
                    _token(source.status) in _ACTIVE_RESOURCE_STATUSES
                    or _token(source.progress_status) in _ACTIVE_RESOURCE_STATUSES
                )
            ),
            None,
        )
        if active_lecture is not None:
            reasons = [
                "this lecture is already in progress/paused",
                "continuing an existing learning thread avoids restarting from zero",
            ]
            if active_lecture.progress_value is not None:
                if active_lecture.progress_max_value not in (None, 0):
                    reasons.append(
                        "recorded progress is {} of {} {}".format(
                            active_lecture.progress_value,
                            active_lecture.progress_max_value,
                            active_lecture.progress_unit,
                        ).strip()
                    )
                else:
                    reasons.append(
                        "recorded progress value is {} {}".format(
                            active_lecture.progress_value,
                            active_lecture.progress_unit,
                        ).strip()
                    )
            result.append(
                self._candidate(
                    state,
                    stage=1,
                    action_type="continue_lecture",
                    title="Continue {}".format(active_lecture.title),
                    bonus=24.0,
                    reasons=reasons,
                    resource_id=active_lecture.source_id,
                )
            )
        elif low_confidence and topic.sources:
            source = topic.sources[0]
            if source.source_kind == "note":
                action_type = "review_note"
                title = "Review {}".format(source.title)
            else:
                action_type = "study_resource"
                title = "Study {}".format(source.title)
            result.append(
                self._candidate(
                    state,
                    stage=1,
                    action_type=action_type,
                    title=title,
                    bonus=18.0,
                    reasons=(
                        "concept review is appropriate before harder recall/practice",
                    )
                    + tuple(source.reasons[:3]),
                    resource_id=(
                        source.source_id
                        if source.source_kind == "resource"
                        else None
                    ),
                )
            )

        # Stage 2: use the grounded tutor when structured evidence says the topic
        # still has confusion/weakness signals. Memory text is never interpreted.
        if (
            low_confidence
            or topic.unresolved_mistake_count > 0
            or topic.active_memory_count > 0
        ):
            reasons = []
            if low_confidence:
                reasons.append(
                    "topic status/confidence indicates concept review is still useful"
                )
            if topic.unresolved_mistake_count:
                reasons.append(
                    "{} unresolved formal mistake event(s) are recorded".format(
                        topic.unresolved_mistake_count
                    )
                )
            if topic.active_memory_count:
                reasons.append(
                    "{} active learning-memory entr{} linked to the topic; "
                    "their text is not interpreted by the mentor".format(
                        topic.active_memory_count,
                        "y is" if topic.active_memory_count == 1 else "ies are",
                    )
                )
            result.append(
                self._candidate(
                    state,
                    stage=2,
                    action_type="grounded_tutor",
                    title="Use the grounded tutor for {}".format(topic.topic_name),
                    bonus=20.0,
                    reasons=reasons,
                )
            )

        # Stage 3: active recall adapts to deterministic practice history only.
        practice = state.practice
        if not practice.available:
            recall_bonus = 12.0
            recall_reasons = (
                "no persisted practice history is available, so no mastery claim is made",
                "a source-grounded recall check can collect explicit evidence",
            )
            include_recall = True
        elif practice.deterministic_attempt_count == 0:
            recall_bonus = 18.0
            recall_reasons = (
                "no deterministic recall attempt is recorded for this topic",
                "a fast quiz can test recall without changing mastery automatically",
            )
            include_recall = True
        else:
            accuracy = practice.deterministic_accuracy
            if accuracy < 0.70:
                recall_bonus = 28.0
                recall_reasons = (
                    "deterministic practice accuracy is {:.0f}% across {} attempt(s)".format(
                        accuracy * 100.0,
                        practice.deterministic_attempt_count,
                    ),
                    "incorrect deterministic attempts justify another recall cycle",
                )
                include_recall = True
            elif state.target_assessment_in_scope:
                recall_bonus = 10.0
                recall_reasons = (
                    "deterministic practice accuracy is {:.0f}%".format(
                        accuracy * 100.0
                    ),
                    "the topic is explicitly in the selected assessment scope",
                )
                include_recall = True
            else:
                include_recall = False
                recall_bonus = 0.0
                recall_reasons = ()

        if include_recall:
            result.append(
                self._candidate(
                    state,
                    stage=3,
                    action_type="active_recall",
                    title="Run source-grounded active recall on {}".format(
                        topic.topic_name
                    ),
                    bonus=recall_bonus,
                    reasons=recall_reasons,
                )
            )

        # Stage 4: formal question/PYQ evidence stays separate from generated
        # practice. Prefer explicit PYQ and source-backed formal questions.
        question = self._formal_question_for_topic(
            topic.topic_id,
            exam_questions,
        )
        if question is not None:
            if question.explicit_pyq:
                action_type = "solve_pyq"
                title = "Solve PYQ: {}".format(question.assessment_title)
                bonus = 24.0
                reasons = [
                    "this is explicitly labelled PYQ/past-paper evidence",
                ]
            else:
                action_type = "solve_formal_question"
                title = "Solve formal question: {}".format(
                    question.assessment_title
                )
                bonus = 14.0
                reasons = [
                    "this is an existing formal assessment question, not generated practice",
                ]
            if question.max_marks_milli is not None:
                reasons.append(
                    "recorded question marks: {}".format(
                        question.max_marks_milli / 1000.0
                    )
                )
            if question.unresolved_mistake_count:
                reasons.append(
                    "{} unresolved mistake event(s) are attached to this question".format(
                        question.unresolved_mistake_count
                    )
                )
                bonus += 10.0
            if question.source_count:
                reasons.append(
                    "{} source record(s) preserve question provenance".format(
                        question.source_count
                    )
                )
            if state.target_assessment_in_scope:
                reasons.append(
                    "topic is explicitly in the selected target-assessment scope"
                )
                bonus += 8.0
            result.append(
                self._candidate(
                    state,
                    stage=4,
                    action_type=action_type,
                    title=title,
                    bonus=bonus,
                    reasons=reasons,
                    question_id=question.question_id,
                    assessment_id=question.assessment_id,
                    source_labels=question.source_labels,
                )
            )

        return result

    @staticmethod
    def _formal_question_for_topic(topic_id, questions):
        candidates = [
            item
            for item in questions
            if topic_id in item.accepted_topic_ids
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: (
                0 if item.explicit_pyq else 1,
                0 if item.source_count > 0 else 1,
                0 if item.attempt_count == 0 else 1,
                -item.unresolved_mistake_count,
                item.assessment_title.casefold(),
                item.ordinal,
                item.question_id,
            )
        )
        return candidates[0]

    @staticmethod
    def _candidate(
        state,
        *,
        stage,
        action_type,
        title,
        bonus,
        reasons,
        resource_id=None,
        question_id=None,
        assessment_id=None,
        source_labels=(),
    ):
        return {
            "stage": int(stage),
            "action_type": action_type,
            "topic_id": state.topic_id,
            "topic_name": state.topic_name,
            "title": title,
            "topic_priority": state.combined_priority_score,
            "action_score": state.combined_priority_score + float(bonus),
            "reasons": _combine_reasons(reasons, state.reasons, limit=8),
            "resource_id": resource_id,
            "question_id": question_id,
            "assessment_id": assessment_id,
            "source_labels": tuple(source_labels),
        }
