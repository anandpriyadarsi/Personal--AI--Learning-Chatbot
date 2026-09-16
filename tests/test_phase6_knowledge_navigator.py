from __future__ import annotations

import sqlite3
from datetime import date

from personal_learning_assistant.repositories.sqlite.knowledge_navigator_repository import (
    SQLiteKnowledgeNavigatorRepository,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
from personal_learning_assistant.services.knowledge_navigator_service import (
    KnowledgeNavigatorService,
)


NOW = "2026-09-16T12:00:00Z"


def _env(tmp_path):
    db = tmp_path / "db.sqlite"
    apply_migrations(db)
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
        ("t-inverse", "Inverse", "inverse", 3, "not_started", None),
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
    c.execute(
        "INSERT INTO topic_aliases(id,topic_id,course_id,alias,normalized_alias,source,created_at) "
        "VALUES ('a1','t-lu','c1','LU','lu','manual',?)",
        (NOW,),
    )

    c.execute(
        "INSERT INTO assessments(id,course_id,assessment_type,title,due_on,due_time,status,"
        "weight_bps,max_points_milli,earned_points_milli,description,created_at,updated_at,deleted_at) "
        "VALUES ('ass1','c1','quiz','Quiz 1','2026-09-18',NULL,'pending',1000,10000,NULL,'',?,?,NULL)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO assessment_topics(id,assessment_id,topic_id,raw_label,source,confidence,created_at) "
        "VALUES ('at1','ass1','t-lu','','manual',1.0,?)",
        (NOW,),
    )

    c.execute(
        "INSERT INTO questions(id,assessment_id,ordinal,question_text,max_marks_milli,status,"
        "user_notes,import_batch_id,created_at,updated_at,deleted_at) "
        "VALUES ('q1','ass1',1,'Find LU',5000,'attempted','',NULL,?,?,NULL)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO question_topic_mappings(id,question_id,topic_id,score,rank,method,state,"
        "reason,created_at,reviewed_at) "
        "VALUES ('m1','q1','t-lu',1.0,1,'manual','accepted','',?,?)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO question_attempts(id,question_id,attempt_number,outcome,earned_marks_milli,"
        "max_marks_milli,response_ref,feedback_ref,occurred_at) "
        "VALUES ('qa1','q1',1,'incorrect',1000,5000,NULL,NULL,?)",
        (NOW,),
    )
    c.execute(
        "INSERT INTO mistake_events(id,attempt_id,category,mistake_text,created_at,resolved_at) "
        "VALUES ('mist1','qa1','procedure','wrong elimination multiplier',?,NULL)",
        (NOW,),
    )
    c.execute(
        "INSERT INTO learning_memory_entries(id,scope_type,scope_id,kind,topic_id,raw_topic,"
        "memory_text,source_entity_type,source_entity_id,created_at,updated_at,archived_at) "
        "VALUES ('mem1','topic','t-lu','confusion','t-lu','','pivot confusion',NULL,NULL,?,?,NULL)",
        (NOW, NOW),
    )

    # Direct topic resource with current retrievable chunks.
    c.execute(
        "INSERT INTO resources(id,resource_type,title,canonical_uri,provider,external_id,status,"
        "rating,quality_note,created_at,updated_at,completed_at,archived_at,deleted_at) "
        "VALUES ('r-mit','external_lecture','MIT Lecture 04','https://ocw.mit.edu/l4','mit_ocw',"
        "'mit-l4','in_progress',5,'',?,?,NULL,NULL,NULL)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO resource_courses(resource_id,course_id,role) VALUES ('r-mit','c1','supporting')"
    )
    c.execute(
        "INSERT INTO resource_topics(resource_id,topic_id,relation_source,confidence) "
        "VALUES ('r-mit','t-lu','reviewed_crosswalk',1.0)"
    )
    c.execute(
        "INSERT INTO resource_progress_events(id,resource_id,occurred_at,status,value,max_value,"
        "unit,position,note) VALUES ('rp1','r-mit',?,'in_progress',20,60,'minutes','','')",
        (NOW,),
    )
    c.execute(
        "INSERT INTO knowledge_documents(id,kind,canonical_uri,path_key,mime_type,content_hash,"
        "size_bytes,source_timestamp,extraction_status,extraction_version,extraction_error,"
        "created_at,updated_at) VALUES "
        "('d1','external_course_chunks',NULL,'mit/chunks.jsonl','application/x-ndjson','h1',"
        "100,NULL,'completed','v1',NULL,?,?)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO resource_documents(resource_id,document_id,role) VALUES ('r-mit','d1','source')"
    )
    c.execute(
        "INSERT INTO knowledge_chunks(id,document_id,ordinal,page_number,char_start,char_end,"
        "chunk_type,text_hash,extraction_version,chunk_text) VALUES "
        "('k1','d1',0,NULL,0,10,'text','th1','v1','LU evidence')"
    )

    # Course-only completed resource should rank below the direct unfinished one.
    c.execute(
        "INSERT INTO resources(id,resource_type,title,canonical_uri,provider,external_id,status,"
        "rating,quality_note,created_at,updated_at,completed_at,archived_at,deleted_at) "
        "VALUES ('r-old','book','Finished Book',NULL,'','book-1','completed',3,'',?,?,?,NULL,NULL)",
        (NOW, NOW, NOW),
    )
    c.execute(
        "INSERT INTO resource_courses(resource_id,course_id,role) VALUES ('r-old','c1','supporting')"
    )

    c.execute(
        "INSERT INTO vaults(id,name,root_path,path_key,enabled,last_scanned_at,created_at,updated_at) "
        "VALUES ('v1','Vault','X:/vault','vault',1,NULL,?,?)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO note_metadata(id,vault_id,relative_path,path_key,title,note_type,confidence,"
        "revision_status,pinned_at,archived_at,trashed_at,source_hash,file_mtime_ns,"
        "frontmatter_extra_json,created_at,updated_at) VALUES "
        "('n1','v1','LU.md','lu.md','My LU Note','note',4,'reviewed',?,NULL,NULL,'nh',1,'{}',?,?)",
        (NOW, NOW, NOW),
    )
    c.execute(
        "INSERT INTO note_topics(note_id,topic_id,relation_source,confidence) "
        "VALUES ('n1','t-lu','manual',1.0)"
    )

    c.execute(
        "INSERT INTO study_plans(id,kind,horizon,starts_on,ends_on,requested_minutes,"
        "allocated_minutes,status,engine_name,engine_version,rationale,created_at,updated_at) "
        "VALUES ('sp1','weekly','week','2026-09-16','2026-09-22',60,60,'active',"
        "'test','1','',?,?)",
        (NOW, NOW),
    )
    c.execute(
        "INSERT INTO study_plan_items(id,plan_id,plan_date,ordinal,course_id,topic_id,"
        "assessment_id,resource_id,note_id,minutes,action,reason,score,status) "
        "VALUES ('spi1','sp1','2026-09-17',1,'c1','t-lu',NULL,NULL,NULL,30,'review','',1.0,'planned')"
    )
    c.execute(
        "INSERT INTO study_sessions(id,started_at,ended_at,duration_minutes,course_id,topic_id,"
        "resource_id,assessment_id,note_id,plan_item_id,outcome,confidence,note,created_at) "
        "VALUES ('ss1',?, ?,25,'c1','t-lu','r-mit',NULL,NULL,NULL,'',2,'',?)",
        (NOW, NOW, NOW),
    )

    repo = SQLiteKnowledgeNavigatorRepository(c)
    service = KnowledgeNavigatorService(repo)
    return c, service


def test_navigation_is_read_only(tmp_path):
    c, service = _env(tmp_path)
    before = c.total_changes
    result = service.navigate("MA103N", as_of=date(2026, 9, 16))
    assert c.total_changes == before
    assert result.writes_performed is False
    c.close()


def test_weak_urgent_topic_ranks_above_mastered_topic(tmp_path):
    c, service = _env(tmp_path)
    result = service.navigate("MA103N", as_of=date(2026, 9, 16))
    assert result.topics[0].topic_id == "t-lu"
    rank = next(item for item in result.topics if item.topic_id == "t-rank")
    assert result.topics[0].priority_score > rank.priority_score
    assert result.topics[0].nearest_due_on == "2026-09-18"
    assert result.topics[0].unresolved_mistake_count == 1
    c.close()


def test_topic_reasons_expose_evidence_not_opaque_score(tmp_path):
    c, service = _env(tmp_path)
    topic = service.navigate(
        "MA103N", topic_name="LU", as_of=date(2026, 9, 16)
    ).topics[0]
    joined = " | ".join(topic.reasons)
    assert "confidence is 2/5" in joined
    assert "due in 2 day(s)" in joined
    assert "unresolved mistake" in joined
    assert "learning-memory" in joined
    assert "study-plan" in joined
    c.close()


def test_direct_in_progress_retrievable_resource_ranks_high(tmp_path):
    c, service = _env(tmp_path)
    topic = service.navigate(
        "MA103N", topic_name="LU", as_of=date(2026, 9, 16)
    ).topics[0]
    assert topic.sources[0].source_id == "r-mit"
    assert topic.sources[0].current_chunk_count == 1
    assert topic.sources[0].progress_status == "in_progress"
    assert topic.sources[0].study_minutes == 25
    c.close()


def test_completed_course_only_resource_is_deprioritized(tmp_path):
    c, service = _env(tmp_path)
    topic = service.navigate(
        "MA103N", topic_name="LU", as_of=date(2026, 9, 16)
    ).topics[0]
    resources = {
        item.source_id: item
        for item in topic.sources
        if item.source_kind == "resource"
    }
    assert resources["r-mit"].score > resources["r-old"].score
    c.close()


def test_pinned_reviewed_topic_note_is_a_candidate(tmp_path):
    c, service = _env(tmp_path)
    topic = service.navigate(
        "MA103N", topic_name="LU", as_of=date(2026, 9, 16)
    ).topics[0]
    note = next(item for item in topic.sources if item.source_id == "n1")
    assert note.source_kind == "note"
    assert "directly linked" in " ".join(note.reasons)
    assert "pinned" in " ".join(note.reasons)
    c.close()


def test_expired_assessment_does_not_add_urgency(tmp_path):
    c, service = _env(tmp_path)
    c.execute("UPDATE assessments SET due_on='2026-09-10' WHERE id='ass1'")
    topic = service.navigate(
        "MA103N", topic_name="LU", as_of=date(2026, 9, 16)
    ).topics[0]
    assert topic.nearest_due_on is None
    assert topic.upcoming_assessment_count == 0
    c.close()


def test_unknown_topic_fails_explicitly(tmp_path):
    c, service = _env(tmp_path)
    import pytest

    with pytest.raises(Exception, match="topic not found"):
        service.navigate(
            "MA103N", topic_name="Eigenvalues", as_of=date(2026, 9, 16)
        )
    c.close()


def test_repeated_navigation_is_deterministic(tmp_path):
    c, service = _env(tmp_path)
    first = service.navigate("MA103N", as_of=date(2026, 9, 16))
    second = service.navigate("MA103N", as_of=date(2026, 9, 16))
    assert first == second
    c.close()
