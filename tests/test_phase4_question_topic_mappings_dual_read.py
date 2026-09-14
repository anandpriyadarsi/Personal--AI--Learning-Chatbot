import hashlib
import json
import sqlite3

import pytest

from personal_learning_assistant.repositories.json.question_repository import LegacyJsonQuestionRepository
from personal_learning_assistant.repositories.question_topic_mapping_backend import (
    QuestionTopicMappingBackendConfig,
    build_question_topic_mapping_repository,
)
from personal_learning_assistant.repositories.sqlite.question_topic_mapping_repository import (
    SQLiteQuestionTopicMappingReadOnlyError,
    SQLiteQuestionTopicMappingRepository,
)


def _fixture(tmp_path):
    raw = {
        "version": 1,
        "workspaces": {
            "quiz-1": {
                "assessment_id": "quiz-1",
                "questions": [{
                    "id": "q1",
                    "text": "Find matrix rank",
                    "topic": "Rank",
                    "topic_mapping": {
                        "method": "automatic",
                        "suggested_topic": "Rank",
                        "score": 0.9,
                        "confidence": "high",
                        "alternatives": [{"topic": "Rank", "score": 0.9}],
                        "accepted": True,
                        "mapped_at": "2026-09-14T00:00:00",
                    },
                }],
            }
        },
    }
    path = tmp_path / "assessment_workspace.json"
    payload = json.dumps(raw, ensure_ascii=False, indent=2).encode("utf-8")
    path.write_bytes(payload)
    return path, raw, hashlib.sha256(payload).hexdigest()


def _connection(source_hash):
    c = sqlite3.connect(":memory:")
    c.executescript("""
    CREATE TABLE migration_imports(source_path TEXT, source_hash TEXT, source_type TEXT, source_version TEXT, legacy_key TEXT, target_table TEXT, target_id TEXT, imported_at TEXT, details_json TEXT);
    CREATE TABLE questions(id TEXT PRIMARY KEY);
    CREATE TABLE topics(id TEXT PRIMARY KEY, course_id TEXT, name TEXT, normalized_name TEXT);
    CREATE TABLE question_topic_mappings(id TEXT PRIMARY KEY, question_id TEXT, topic_id TEXT, score REAL, rank INTEGER, method TEXT, state TEXT, reason TEXT, created_at TEXT, reviewed_at TEXT);
    """)
    c.execute("INSERT INTO questions VALUES ('question-1')")
    c.execute("INSERT INTO topics VALUES ('topic-rank','course-1','Rank','rank')")
    c.execute("INSERT INTO question_topic_mappings VALUES (?,?,?,?,?,?,?,?,?,?)", ('mapping-1','question-1','topic-rank',0.9,1,'automatic','accepted','legacy suggested + accepted_topic; confidence=high','2026-09-14T00:00:00','2026-09-14T00:00:00'))
    observation = {
        "kind": "question_topic_mapping_observation",
        "question_legacy_key": "assessment:id:quiz-1/question:id:q1",
        "course_target_id": "course-1",
        "raw_topic": "Rank",
        "raw_topic_mapping": {"method":"automatic","suggested_topic":"Rank","score":0.9,"confidence":"high","alternatives":[{"topic":"Rank","score":0.9}],"accepted":True,"mapped_at":"2026-09-14T00:00:00"},
        "candidate_resolutions": [{"legacy_key":"assessment:id:quiz-1/question:id:q1/topic:label:rank","raw_label":"Rank","normalized_label":"rank","state":"accepted","resolution":"resolved","target_ids":["topic-rank"]}],
    }
    mapping = {
        "kind":"question_topic_mapping","question_legacy_key":"assessment:id:quiz-1/question:id:q1","question_target_id":"question-1","course_target_id":"course-1","topic_target_id":"topic-rank","raw_label":"Rank","normalized_label":"rank","origins":["suggested","alternative","accepted_topic"],"raw_candidate":{"topic":"Rank","score":0.9},"raw_topic":"Rank","raw_topic_mapping":observation["raw_topic_mapping"],"resolution":"exact_course_topic_name"
    }
    c.execute("INSERT INTO migration_imports VALUES (?,?,?,?,?,?,?,?,?)", ('data/assessment_workspace.json',source_hash,'legacy_json','1','assessment:id:quiz-1/question:id:q1/topic_mapping:observation','questions','question-1','2026-09-14T00:00:00',json.dumps(observation)))
    c.execute("INSERT INTO migration_imports VALUES (?,?,?,?,?,?,?,?,?)", ('data/assessment_workspace.json',source_hash,'legacy_json','1','assessment:id:quiz-1/question:id:q1/topic:label:rank','question_topic_mappings','mapping-1','2026-09-14T00:00:00',json.dumps(mapping)))
    c.commit()
    return c


def test_dual_read_returns_legacy_and_reports_mapping_parity(tmp_path):
    path, raw, digest = _fixture(tmp_path)
    connection = _connection(digest)
    legacy = LegacyJsonQuestionRepository(path=path)
    repo = build_question_topic_mapping_repository(
        "dual_read", legacy_repository=legacy, sqlite_connection=connection
    )
    before = path.read_bytes()
    changes_before = connection.total_changes
    state = repo.load_state()
    assert state == raw
    assert path.read_bytes() == before
    assert repo.last_report.status == "pass"
    assert repo.last_report.mismatch_count == 0
    assert connection.total_changes == changes_before


def test_dual_read_never_promotes_sqlite_to_authority(tmp_path):
    path, _, digest = _fixture(tmp_path)
    connection = _connection(digest)
    sqlite_repo = SQLiteQuestionTopicMappingRepository(connection)
    with pytest.raises(SQLiteQuestionTopicMappingReadOnlyError):
        sqlite_repo.save_state({})
    repo = build_question_topic_mapping_repository("dual_read", legacy_path=path, sqlite_repository=sqlite_repo)
    changed = repo.load_state()
    changed["workspaces"]["quiz-1"]["questions"][0]["topic"] = "Different"
    repo.save_state(changed)
    assert json.loads(path.read_text(encoding="utf-8"))["workspaces"]["quiz-1"]["questions"][0]["topic"] == "Different"


def test_unresolved_candidate_is_review_required_not_guessed(tmp_path):
    path, _, digest = _fixture(tmp_path)
    connection = _connection(digest)
    observation = json.loads(connection.execute("SELECT details_json FROM migration_imports WHERE target_table='questions'").fetchone()[0])
    observation["candidate_resolutions"][0]["resolution"] = "unresolved"
    observation["candidate_resolutions"][0]["target_ids"] = []
    connection.execute("UPDATE migration_imports SET details_json=? WHERE target_table='questions'", (json.dumps(observation),))
    connection.commit()
    repo = build_question_topic_mapping_repository("dual_read", legacy_path=path, sqlite_connection=connection)
    repo.load_state()
    assert repo.last_report.status == "pass_with_review"
    review = [d for d in repo.last_report.diagnostics if d.domain == "unresolved_or_ambiguous_topic_candidates"][0]
    assert review.status == "review_required"


def test_invalid_backend_mode_rejects_sqlite_authority():
    with pytest.raises(ValueError):
        QuestionTopicMappingBackendConfig("sqlite")
