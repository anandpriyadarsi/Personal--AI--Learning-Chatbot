from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from personal_learning_assistant.repositories.sqlite.exam_intelligence_repository import (
    ExamIntelligenceNotFoundError,
    SQLiteExamIntelligenceRepository,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
from personal_learning_assistant.services.exam_intelligence_service import (
    ExamIntelligenceService,
)


NOW = "2026-09-16T20:00:00Z"


def _env(tmp_path):
    db = tmp_path / "db.sqlite"
    applied = apply_migrations(db)
    assert applied[:4] == (1, 2, 3, 4)
    assert apply_migrations(db) == ()
    c = sqlite3.connect(str(db), isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")

    c.execute(
        "INSERT INTO courses(id,code,name,status,description,created_at,updated_at,deleted_at) "
        "VALUES ('c1','MA103N','Linear Algebra','active','',?,?,NULL)",
        (NOW, NOW),
    )
    topics = (
        ("t-lu", "LU Factorization", "lu factorization", 1, "learning", 2),
        ("t-rank", "Rank", "rank", 2, "mastered", 5),
        ("t-inv", "Inverse", "inverse", 3, "not_started", None),
    )
    for topic_id, name, normalized, position, status, confidence in topics:
        c.execute(
            "INSERT INTO topics(id,course_id,name,normalized_name,position,status,"
            "confidence,raw_import_status,created_at,updated_at,deleted_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,NULL)",
            (
                topic_id,
                "c1",
                name,
                normalized,
                position,
                status,
                confidence,
                None,
                NOW,
                NOW,
            ),
        )

    assessments = (
        (
            "a-pyq",
            "pyq",
            "Previous Year Paper 2025",
            "2025-11-20",
            "completed",
            "Official previous year paper",
        ),
        (
            "a-mid",
            "mid_semester",
            "Mid Semester",
            "2026-09-20",
            "pending",
            "",
        ),
        (
            "a-quiz",
            "quiz",
            "Quiz 1",
            "2026-09-18",
            "pending",
            "",
        ),
    )
    for aid, kind, title, due, status, description in assessments:
        c.execute(
            "INSERT INTO assessments(id,course_id,assessment_type,title,due_on,due_time,"
            "status,weight_bps,max_points_milli,earned_points_milli,description,"
            "created_at,updated_at,deleted_at) "
            "VALUES (?,?,?,?,?,NULL,?,NULL,NULL,NULL,?,?,?,NULL)",
            (aid, "c1", kind, title, due, status, description, NOW, NOW),
        )

    c.execute(
        "INSERT INTO assessment_topics(id,assessment_id,topic_id,raw_label,source,confidence,created_at) "
        "VALUES ('at-lu','a-mid','t-lu','','planner',1.0,?)",
        (NOW,),
    )
    c.execute(
        "INSERT INTO assessment_topics(id,assessment_id,topic_id,raw_label,source,confidence,created_at) "
        "VALUES ('at-rank','a-mid','t-rank','','planner',1.0,?)",
        (NOW,),
    )

    questions = (
        ("q1", "a-pyq", 1, "Factor A into LU.", 5000),
        ("q2", "a-pyq", 2, "Find the rank of A.", 3000),
        ("q3", "a-quiz", 1, "Find A inverse.", 2000),
        ("q4", "a-quiz", 2, "State a matrix result.", None),
    )
    for qid, aid, ordinal, text, marks in questions:
        c.execute(
            "INSERT INTO questions(id,assessment_id,ordinal,question_text,max_marks_milli,"
            "status,user_notes,import_batch_id,created_at,updated_at,deleted_at) "
            "VALUES (?,?,?,?,?,'not_started','',NULL,?,?,NULL)",
            (qid, aid, ordinal, text, marks, NOW, NOW),
        )

    mappings = (
        ("m1", "q1", "t-lu", "accepted", 1),
        ("m2", "q2", "t-rank", "accepted", 1),
        ("m3", "q3", "t-inv", "proposed", 1),
    )
    for mid, qid, tid, state, rank in mappings:
        c.execute(
            "INSERT INTO question_topic_mappings(id,question_id,topic_id,score,rank,"
            "method,state,reason,created_at,reviewed_at) "
            "VALUES (?,?,?,1.0,?,'manual',?,'',?,?)",
            (mid, qid, tid, rank, state, NOW, NOW if state == "accepted" else None),
        )

    c.execute(
        "INSERT INTO knowledge_documents(id,kind,canonical_uri,path_key,mime_type,"
        "content_hash,size_bytes,source_timestamp,extraction_status,extraction_version,"
        "extraction_error,created_at,updated_at) "
        "VALUES ('d1','pdf',NULL,'pyq.pdf','application/pdf','h1',100,NULL,"
        "'completed','v1',NULL,?,?)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO question_sources(id,question_id,document_id,resource_id,note_id,"
        "page_number,locator,raw_source_label,created_at) "
        "VALUES ('s1','q1','d1',NULL,NULL,2,'Q1','Official PYQ PDF',?)",
        (NOW,),
    )

    c.execute(
        "INSERT INTO question_attempts(id,question_id,attempt_number,outcome,"
        "earned_marks_milli,max_marks_milli,response_ref,feedback_ref,occurred_at) "
        "VALUES ('qa1','q1',1,'incorrect',1000,5000,NULL,NULL,?)",
        (NOW,),
    )
    c.execute(
        "INSERT INTO mistake_events(id,attempt_id,category,mistake_text,created_at,resolved_at) "
        "VALUES ('me1','qa1','procedure','wrong multiplier',?,NULL)",
        (NOW,),
    )

    repo = SQLiteExamIntelligenceRepository(c)
    service = ExamIntelligenceService(repo)
    return c, service


def test_report_is_read_only(tmp_path):
    c, service = _env(tmp_path)
    before = c.total_changes
    report = service.analyze("MA103N", as_of=date(2026, 9, 16))
    assert c.total_changes == before
    assert report.writes_performed is False
    assert report.prediction_performed is False
    c.close()


def test_explicit_pyq_requires_explicit_source_metadata(tmp_path):
    c, service = _env(tmp_path)
    report = service.analyze("MA103N", as_of=date(2026, 9, 16))
    assert report.explicit_pyq_assessment_count == 1
    assert report.explicit_pyq_question_count == 2
    pyq = [item for item in report.questions if item.explicit_pyq]
    assert {item.assessment_id for item in pyq} == {"a-pyq"}
    assert not any(
        item.assessment_id == "a-mid" and item.explicit_pyq
        for item in report.questions
    )
    c.close()


def test_mapping_states_are_not_silently_promoted(tmp_path):
    c, service = _env(tmp_path)
    report = service.analyze("MA103N", as_of=date(2026, 9, 16))
    assert report.accepted_mapped_question_count == 2
    assert report.proposed_only_question_count == 1
    assert report.unmapped_question_count == 1
    q3 = next(item for item in report.questions if item.question_id == "q3")
    assert q3.mapping_state == "proposed_only"
    assert q3.accepted_topic_ids == ()
    c.close()


def test_question_source_provenance_is_preserved(tmp_path):
    c, service = _env(tmp_path)
    report = service.analyze("MA103N", as_of=date(2026, 9, 16))
    q1 = next(item for item in report.questions if item.question_id == "q1")
    assert q1.source_count == 1
    assert "Official PYQ PDF" in q1.source_labels[0]
    assert "page 2" in q1.source_labels[0]
    assert "[Q1]" in q1.source_labels[0]
    assert report.source_backed_question_count == 1
    c.close()


def test_topic_statistics_use_only_accepted_question_mappings(tmp_path):
    c, service = _env(tmp_path)
    report = service.analyze("MA103N", as_of=date(2026, 9, 16))
    topics = {item.topic_id: item for item in report.topics}
    assert topics["t-lu"].historical_question_count == 1
    assert topics["t-lu"].total_marks_milli == 5000
    assert topics["t-lu"].explicit_pyq_question_count == 1
    assert topics["t-inv"].historical_question_count == 0
    assert topics["t-inv"].total_marks_milli == 0
    c.close()


def test_unresolved_formal_mistakes_raise_explainable_preparation_priority(tmp_path):
    c, service = _env(tmp_path)
    report = service.analyze("MA103N", as_of=date(2026, 9, 16))
    lu = next(item for item in report.topics if item.topic_id == "t-lu")
    rank = next(item for item in report.topics if item.topic_id == "t-rank")
    assert lu.unresolved_mistake_count == 1
    assert lu.preparation_priority_score > rank.preparation_priority_score
    assert any("unresolved mistake" in reason for reason in lu.reasons)
    c.close()


def test_target_assessment_scope_is_explicit_and_not_a_prediction(tmp_path):
    c, service = _env(tmp_path)
    report = service.analyze(
        "MA103N",
        as_of=date(2026, 9, 16),
        target_assessment_id="a-mid",
    )
    topics = {item.topic_id: item for item in report.topics}
    assert topics["t-lu"].target_assessment_in_scope is True
    assert topics["t-rank"].target_assessment_in_scope is True
    assert topics["t-inv"].target_assessment_in_scope is False
    assert report.target_assessment_title == "Mid Semester"
    assert report.prediction_performed is False
    c.close()


def test_upcoming_assessment_count_uses_dates_not_title_guessing(tmp_path):
    c, service = _env(tmp_path)
    report = service.analyze("MA103N", as_of=date(2026, 9, 16))
    assert report.upcoming_assessment_count == 2
    c.close()


def test_repeat_report_is_deterministic(tmp_path):
    c, service = _env(tmp_path)
    first = service.analyze("MA103N", as_of=date(2026, 9, 16))
    second = service.analyze("MA103N", as_of=date(2026, 9, 16))
    assert first == second
    c.close()


def test_unknown_target_assessment_fails_explicitly(tmp_path):
    c, service = _env(tmp_path)
    with pytest.raises(ExamIntelligenceNotFoundError):
        service.analyze(
            "MA103N",
            as_of=date(2026, 9, 16),
            target_assessment_id="missing",
        )
    c.close()
