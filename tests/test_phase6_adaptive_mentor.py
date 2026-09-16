from __future__ import annotations

import sqlite3
from datetime import date

from personal_learning_assistant.domain.exam_intelligence_models import (
    ExamIntelligenceReport,
    ExamQuestionEvidence,
    ExamTopicIntelligence,
)
from personal_learning_assistant.domain.knowledge_navigator_models import (
    KnowledgeNavigatorResult,
    StudySourceRecommendation,
    StudyTopicRecommendation,
)
from personal_learning_assistant.repositories.sqlite.adaptive_mentor_repository import (
    SQLiteAdaptiveMentorRepository,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import (
    apply_migrations,
)
from personal_learning_assistant.services.adaptive_mentor_service import (
    AdaptiveMentorService,
)


NOW = "2026-09-16T20:00:00Z"


class FakeNavigator:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def navigate(self, course_code, **kwargs):
        self.calls.append((course_code, kwargs))
        return self.result


class FakeExam:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def analyze(self, course_code, **kwargs):
        self.calls.append((course_code, kwargs))
        return self.result


class FakeEvidence:
    def __init__(self, summaries=None, available=True):
        self.summaries = summaries or {}
        self.available = available

    def practice_history_available(self):
        return self.available

    def practice_summary(self, course_id, topic_id):
        from personal_learning_assistant.domain.adaptive_mentor_models import (
            MentorPracticeSummary,
        )

        return self.summaries.get(
            topic_id,
            MentorPracticeSummary(
                available=self.available,
                session_count=0,
                completed_session_count=0,
                deterministic_attempt_count=0,
                correct_attempt_count=0,
                incorrect_attempt_count=0,
                advisory_attempt_count=0,
                latest_attempt_at=None,
            ),
        )


def _navigator():
    lu_sources = (
        StudySourceRecommendation(
            source_kind="resource",
            source_id="r-l4",
            title="MIT Lecture 04",
            score=93.0,
            reasons=(
                "directly linked to this topic",
                "resource is already in progress",
                "current retrievable chunks exist",
            ),
            status="in_progress",
            provider="mit_ocw",
            resource_type="external_lecture",
            progress_status="in_progress",
            progress_value=20.0,
            progress_max_value=60.0,
            progress_unit="minutes",
            current_chunk_count=12,
            study_minutes=25,
        ),
    )
    return KnowledgeNavigatorResult(
        course_id="c1",
        course_code="MA103N",
        course_name="Linear Algebra",
        as_of="2026-09-16",
        focused_topic_id=None,
        topic_count=2,
        topics=(
            StudyTopicRecommendation(
                topic_id="t-lu",
                topic_name="LU Factorization",
                position=1,
                status="learning",
                confidence=2,
                priority_score=90.0,
                reasons=(
                    "topic status is learning",
                    "confidence is 2/5",
                    "assessment 'Mid Semester' is due in 4 day(s)",
                ),
                nearest_due_on="2026-09-20",
                upcoming_assessment_count=1,
                unresolved_mistake_count=1,
                active_memory_count=1,
                planned_item_count=0,
                study_minutes=25,
                sources=lu_sources,
            ),
            StudyTopicRecommendation(
                topic_id="t-rank",
                topic_name="Rank",
                position=2,
                status="mastered",
                confidence=5,
                priority_score=15.0,
                reasons=("topic status is mastered", "confidence is 5/5"),
                nearest_due_on=None,
                upcoming_assessment_count=0,
                unresolved_mistake_count=0,
                active_memory_count=0,
                planned_item_count=0,
                study_minutes=50,
                sources=(),
            ),
        ),
        writes_performed=False,
    )


def _exam():
    lu = ExamTopicIntelligence(
        topic_id="t-lu",
        topic_name="LU Factorization",
        position=1,
        status="learning",
        confidence=2,
        historical_question_count=2,
        historical_assessment_count=1,
        explicit_pyq_question_count=1,
        total_marks_milli=8000,
        missing_marks_question_count=0,
        source_backed_question_count=1,
        attempted_question_count=1,
        unresolved_mistake_count=1,
        target_assessment_in_scope=True,
        preparation_priority_score=82.0,
        reasons=(
            "2 formal question(s) map here",
            "1 question(s) come from explicitly labelled PYQ/past-paper assessments",
            "topic is explicitly in the selected target-assessment scope",
        ),
    )
    rank = ExamTopicIntelligence(
        topic_id="t-rank",
        topic_name="Rank",
        position=2,
        status="mastered",
        confidence=5,
        historical_question_count=1,
        historical_assessment_count=1,
        explicit_pyq_question_count=0,
        total_marks_milli=3000,
        missing_marks_question_count=0,
        source_backed_question_count=0,
        attempted_question_count=1,
        unresolved_mistake_count=0,
        target_assessment_in_scope=False,
        preparation_priority_score=12.0,
        reasons=("1 formal question(s) map here",),
    )
    q = ExamQuestionEvidence(
        question_id="q-lu",
        assessment_id="a-pyq",
        assessment_title="Previous Year Paper 2025",
        assessment_type="pyq",
        explicit_pyq=True,
        ordinal=1,
        question_text="Factor A into LU.",
        max_marks_milli=5000,
        accepted_topic_ids=("t-lu",),
        mapping_state="accepted",
        source_count=1,
        source_labels=("Official PYQ PDF page 2 [Q1]",),
        attempt_count=1,
        unresolved_mistake_count=1,
    )
    return ExamIntelligenceReport(
        course_id="c1",
        course_code="MA103N",
        course_name="Linear Algebra",
        as_of="2026-09-16",
        formal_assessment_count=2,
        formal_question_count=2,
        explicit_pyq_assessment_count=1,
        explicit_pyq_question_count=1,
        accepted_mapped_question_count=2,
        proposed_only_question_count=0,
        unmapped_question_count=0,
        source_backed_question_count=1,
        upcoming_assessment_count=1,
        target_assessment_id="a-mid",
        target_assessment_title="Mid Semester",
        topics=(lu, rank),
        questions=(q,),
        prediction_performed=False,
        writes_performed=False,
    )


def _service(evidence=None):
    return AdaptiveMentorService(
        navigator_service=FakeNavigator(_navigator()),
        exam_intelligence_service=FakeExam(_exam()),
        evidence_repository=evidence or FakeEvidence(),
    )


def test_mentor_is_advisory_read_only_and_no_llm():
    report = _service().advise(
        "MA103N",
        as_of=date(2026, 9, 16),
        target_assessment_id="a-mid",
    )
    assert report.writes_performed is False
    assert report.authoritative_state_changes is False
    assert report.llm_called is False
    assert all(action.advisory for action in report.actions)


def test_unfinished_lecture_is_recommended_before_restarting_resource():
    report = _service().advise("MA103N", as_of=date(2026, 9, 16))
    lu_actions = [a for a in report.actions if a.topic_id == "t-lu"]
    assert lu_actions[0].action_type == "continue_lecture"
    assert lu_actions[0].resource_id == "r-l4"
    assert "MIT Lecture 04" in lu_actions[0].title


def test_low_confidence_mistake_memory_signals_grounded_tutor_without_reading_memory_text():
    report = _service().advise("MA103N", as_of=date(2026, 9, 16))
    tutor = next(a for a in report.actions if a.action_type == "grounded_tutor")
    joined = " | ".join(tutor.reasons)
    assert "unresolved" in joined
    assert "learning-memory" in joined
    assert "text is not interpreted" in joined


def test_no_deterministic_practice_produces_active_recall_action():
    report = _service().advise("MA103N", as_of=date(2026, 9, 16))
    recall = next(a for a in report.actions if a.action_type == "active_recall")
    assert recall.topic_id == "t-lu"
    assert any("no deterministic" in reason for reason in recall.reasons)


def test_weak_deterministic_practice_increases_recall_reasoning():
    from personal_learning_assistant.domain.adaptive_mentor_models import (
        MentorPracticeSummary,
    )

    evidence = FakeEvidence(
        summaries={
            "t-lu": MentorPracticeSummary(
                available=True,
                session_count=2,
                completed_session_count=2,
                deterministic_attempt_count=4,
                correct_attempt_count=1,
                incorrect_attempt_count=3,
                advisory_attempt_count=1,
                latest_attempt_at=NOW,
            )
        }
    )
    report = _service(evidence).advise("MA103N", as_of=date(2026, 9, 16))
    recall = next(a for a in report.actions if a.action_type == "active_recall")
    assert any("25%" in reason for reason in recall.reasons)


def test_advisory_free_response_never_counts_as_correctness():
    from personal_learning_assistant.domain.adaptive_mentor_models import (
        MentorPracticeSummary,
    )

    evidence = FakeEvidence(
        summaries={
            "t-lu": MentorPracticeSummary(
                available=True,
                session_count=1,
                completed_session_count=1,
                deterministic_attempt_count=0,
                correct_attempt_count=0,
                incorrect_attempt_count=0,
                advisory_attempt_count=3,
                latest_attempt_at=NOW,
            )
        }
    )
    report = _service(evidence).advise("MA103N", as_of=date(2026, 9, 16))
    state = next(t for t in report.topics if t.topic_id == "t-lu")
    assert state.practice.deterministic_accuracy is None
    assert any("not treated as correctness" in r for r in state.reasons)


def test_explicit_pyq_action_preserves_question_and_source_provenance():
    report = _service().advise("MA103N", as_of=date(2026, 9, 16))
    pyq = next(a for a in report.actions if a.action_type == "solve_pyq")
    assert pyq.question_id == "q-lu"
    assert pyq.assessment_id == "a-pyq"
    assert pyq.source_labels == ("Official PYQ PDF page 2 [Q1]",)


def test_target_scope_influences_priority_but_not_prediction():
    report = _service().advise(
        "MA103N",
        as_of=date(2026, 9, 16),
        target_assessment_id="a-mid",
    )
    lu = next(t for t in report.topics if t.topic_id == "t-lu")
    assert lu.target_assessment_in_scope is True
    assert report.authoritative_state_changes is False
    assert report.llm_called is False


def test_strong_practice_can_skip_redundant_recall_when_not_targeted():
    from personal_learning_assistant.domain.adaptive_mentor_models import (
        MentorPracticeSummary,
    )

    exam = _exam()
    untargeted = ExamIntelligenceReport(
        **{
            **exam.__dict__,
            "target_assessment_id": None,
            "target_assessment_title": None,
            "topics": tuple(
                ExamTopicIntelligence(
                    **{
                        **topic.__dict__,
                        "target_assessment_in_scope": False,
                    }
                )
                for topic in exam.topics
            ),
        }
    )
    evidence = FakeEvidence(
        summaries={
            "t-lu": MentorPracticeSummary(
                available=True,
                session_count=2,
                completed_session_count=2,
                deterministic_attempt_count=4,
                correct_attempt_count=4,
                incorrect_attempt_count=0,
                advisory_attempt_count=0,
                latest_attempt_at=NOW,
            )
        }
    )
    service = AdaptiveMentorService(
        navigator_service=FakeNavigator(_navigator()),
        exam_intelligence_service=FakeExam(untargeted),
        evidence_repository=evidence,
    )
    report = service.advise("MA103N", as_of=date(2026, 9, 16))
    assert not any(
        a.action_type == "active_recall" and a.topic_id == "t-lu"
        for a in report.actions
    )


def test_repository_practice_summary_uses_only_deterministic_correctness(tmp_path):
    db = tmp_path / "db.sqlite"
    applied = apply_migrations(db)
    assert applied[:4] == (1, 2, 3, 4)
    c = sqlite3.connect(str(db), isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute(
        "INSERT INTO courses(id,code,name,status,description,created_at,updated_at,deleted_at) "
        "VALUES ('c1','MA103N','Linear Algebra','active','',?,?,NULL)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO topics(id,course_id,name,normalized_name,position,status,"
        "confidence,raw_import_status,created_at,updated_at,deleted_at) "
        "VALUES ('t1','c1','LU','lu',1,'learning',2,NULL,?,?,NULL)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO practice_sessions(id,tutor_session_id,course_id,topic_id,resource_id,"
        "mode,difficulty,status,source_query,source_policy,requested_item_count,"
        "generation_provider,generation_model,provider_request_id,created_at,completed_at) "
        "VALUES ('ps1',NULL,'c1','t1',NULL,'fast_quiz','medium','completed','LU',"
        "'source_only',2,'fake','fake','req',?,?)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO practice_items(id,session_id,ordinal,item_type,prompt,options_json,"
        "answer_key_json,explanation,created_at) "
        "VALUES ('pi1','ps1',1,'single_choice','Q1','[]','{}','E',?)",
        (NOW,),
    )
    c.execute(
        "INSERT INTO practice_items(id,session_id,ordinal,item_type,prompt,options_json,"
        "answer_key_json,explanation,created_at) "
        "VALUES ('pi2','ps1',2,'free_response','Q2','[]','{}','E',?)",
        (NOW,),
    )
    c.execute(
        "INSERT INTO practice_attempts(id,item_id,attempt_number,response_text,outcome,"
        "score_bps,grading_mode,self_confidence,feedback,occurred_at) "
        "VALUES ('pa1','pi1',1,'A','incorrect',0,'deterministic',2,'',?)",
        (NOW,),
    )
    c.execute(
        "INSERT INTO practice_attempts(id,item_id,attempt_number,response_text,outcome,"
        "score_bps,grading_mode,self_confidence,feedback,occurred_at) "
        "VALUES ('pa2','pi2',1,'explain','advisory_ungraded',NULL,'advisory',4,'',?)",
        (NOW,),
    )
    repo = SQLiteAdaptiveMentorRepository(c)
    summary = repo.practice_summary("c1", "t1")
    assert summary.available is True
    assert summary.session_count == 1
    assert summary.completed_session_count == 1
    assert summary.deterministic_attempt_count == 1
    assert summary.correct_attempt_count == 0
    assert summary.incorrect_attempt_count == 1
    assert summary.advisory_attempt_count == 1
    assert summary.deterministic_accuracy == 0.0
    c.close()


def test_repository_gracefully_handles_pre_0004_database():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    repo = SQLiteAdaptiveMentorRepository(c)
    assert repo.practice_history_available() is False
    summary = repo.practice_summary("c1", "t1")
    assert summary.available is False
    assert summary.deterministic_accuracy is None
    c.close()
