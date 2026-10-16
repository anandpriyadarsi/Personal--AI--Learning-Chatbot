"""B1 uses only closed, migrated synthetic snapshots; no runtime integration."""
from contextlib import closing
from dataclasses import FrozenInstanceError, asdict
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3

import pytest

from tests.test_assessment_studio_phase_e import _database, NOW

AS_OF = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


def api():
    assert (ROOT / 'personal_learning_assistant/repositories/sqlite/topic_intelligence_repository.py').exists(), 'B1 adapter missing'
    from personal_learning_assistant.repositories.sqlite import topic_intelligence_repository
    return topic_intelligence_repository


def read(path, topic='topic-lu', **kwargs):
    return api().SQLiteTopicIntelligenceRepository(path, closed_snapshot=True).read_topic_bundle(
        'course-ma', topic, as_of=kwargs.pop('as_of', AS_OF), **kwargs)


def update(path, sql, args=()):
    with closing(sqlite3.connect(path)) as c, c:
        c.execute(sql, args)


def inventory(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def test_mapping_and_grading_are_separate_and_exam_independence_is_unknown(tmp_path):
    bundle = read(_database(tmp_path))
    assert bundle.topic.course_id == 'course-ma'
    assert bundle.topic.topic_id == 'topic-lu'
    assert len(bundle.evidence) == 3
    first = bundle.evidence[0]
    assert first.evidence_id == 'ev-sq1'
    assert first.grading_confidence == 1.0
    assert first.mapping.confidence is None and first.mapping.state == 'unknown'
    assert first.independence.status == 'unknown' and first.mode == 'exam'
    assert all(not e.automatic_eligible for e in bundle.evidence)
    assert all({'mapping_snapshot_unknown', 'independence_unknown'} <= set(e.exclusion_reasons) for e in bundle.evidence)
    assert [e.awarded_marks_milli for e in bundle.evidence] == [1000, -500, 1500]
    assert 'evaluation_not_confirmed' in bundle.evidence[-1].exclusion_reasons
    assert first.occurred_at_utc == datetime(2026, 9, 20, 10, 30, tzinfo=timezone.utc)
    assert first.local_date.isoformat() == '2026-09-20'


def test_current_mapping_and_package_author_confidence_cannot_backfill_trust(tmp_path):
    path = _database(tmp_path)
    before = read(path)
    update(path, "INSERT INTO question_topic_mappings (id,question_id,topic_id,score,rank,method,state,created_at,reviewed_at) VALUES ('m','q1','topic-lu',1,1,'human','confirmed',?,?)", (NOW, NOW))
    update(path, "UPDATE assessment_import_batches SET package_json=?", ('{"authoring_confidence":1,"topic_mapping_confidence":1}',))
    after = read(path)
    assert before.evidence == after.evidence
    assert before.evidence_fingerprint == after.evidence_fingerprint
    assert before.snapshot_sha256 != after.snapshot_sha256


def test_nested_records_are_immutable_and_manual_mastered_is_not_assessed_mastery(tmp_path):
    path = _database(tmp_path)
    update(path, "UPDATE topics SET status='mastered', confidence=5 WHERE id='topic-lu'")
    b = read(path)
    assert b.topic.stored_status == 'mastered' and b.topic.self_reported_confidence == 5
    assert isinstance(b.evidence, tuple) and isinstance(b.evidence[0].source_refs, tuple)
    with pytest.raises(FrozenInstanceError):
        b.topic.stored_status = 'weak'
    with pytest.raises(FrozenInstanceError):
        b.evidence[0].mapping.confidence = 1.0
    assert not any(e.automatic_eligible for e in b.evidence)
    rendered = repr(asdict(b))
    assert 'answer_key' not in rendered and 'solution_text' not in rendered and str(path) not in rendered


def test_bridge_and_mistake_references_never_multiply_observations(tmp_path):
    path = _database(tmp_path)
    update(path, "INSERT INTO question_attempts (id,question_id,attempt_number,outcome,earned_marks_milli,max_marks_milli,occurred_at,signed_score_milli,evaluation_ref) VALUES ('attempt','q1',1,'partially_correct',1000,2000,?,1000,'ev-sq1')", (NOW,))
    update(path, "UPDATE assessment_response_evaluations SET question_attempt_id='attempt' WHERE id='ev-sq1'")
    update(path, "INSERT INTO mistake_events (id,attempt_id,category,created_at) VALUES ('mistake','attempt','concept_gap',?)", (NOW,))
    update(path, "UPDATE assessment_evaluation_mistakes SET mistake_event_id='mistake' WHERE id='m1'")
    update(path, "INSERT INTO assessment_evaluation_mistakes (id,response_evaluation_id,category,source_type,status,created_at) VALUES ('m3','ev-sq1','careless','user','confirmed',?)", (NOW,))
    b = read(path)
    assert len(b.evidence) == 3
    e = b.evidence[0]
    refs = {(r.kind, r.identifier) for r in e.source_refs}
    assert {('question_attempt','attempt'), ('mistake_event','mistake'), ('evaluation_mistake','m1'), ('evaluation_mistake','m3')} <= refs
    assert e.mistake_categories == ('careless', 'concept_gap')
    assert 'inconsistent_bridge_reference' not in e.exclusion_reasons


@pytest.mark.parametrize('reference,valid', [
    ('ev-sq1', True),
    ('assessment_response_evaluation:ev-sq1', True),
    ('assessment_response_evaluation:ev-sq3', False),
    ('other_prefix:ev-sq1', False),
    (None, False),
])
def test_observation_bridge_uses_exact_evaluation_reference_contract(tmp_path, reference, valid):
    path = _database(tmp_path)
    update(path,
           "INSERT INTO question_attempts (id,question_id,attempt_number,outcome,earned_marks_milli,max_marks_milli,occurred_at,signed_score_milli,evaluation_ref) "
           "VALUES ('attempt','q1',1,'partially_correct',1000,2000,?,1000,?)",
           (NOW, reference))
    update(path, "UPDATE assessment_response_evaluations SET question_attempt_id='attempt' WHERE id='ev-sq1'")
    evidence = read(path).evidence[0]
    assert ('inconsistent_bridge_reference' not in evidence.exclusion_reasons) is valid
    assert ('question_attempt', 'attempt') in {(r.kind, r.identifier) for r in evidence.source_refs}
    assert evidence.automatic_eligible is False


def test_content_duplicate_identity_is_shared_without_erasing_source_ids(tmp_path):
    path = _database(tmp_path)
    update(path, "UPDATE assessment_test_session_questions SET question_text=? WHERE id='sq1'", ('Café   rank',))
    update(path, "UPDATE assessment_test_session_questions SET question_text=? WHERE id='sq3'", ('Cafe\u0301\nrank',))
    b = read(path)
    assert b.evidence[0].question_id != b.evidence[1].question_id
    assert b.evidence[0].question_identity == b.evidence[1].question_identity
    assert b.evidence[0].question_identity.startswith('snapshot-sha256:')


def test_repeated_reads_preserve_all_files_sql_and_migration_history(tmp_path):
    path = _database(tmp_path)
    with closing(sqlite3.connect(path)) as c:
        before_sql = tuple(c.iterdump())
    before = inventory(tmp_path)
    first, second = read(path), read(path)
    assert first == second and inventory(tmp_path) == before
    with closing(sqlite3.connect(path)) as c:
        assert tuple(c.iterdump()) == before_sql
        assert c.execute('PRAGMA foreign_key_check').fetchall() == []
        assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert tuple(r[0] for r in c.execute('SELECT version FROM schema_migrations ORDER BY version')) == tuple(range(1,15))


def test_explicit_closed_snapshot_and_existing_file_are_required(tmp_path):
    cls = api().SQLiteTopicIntelligenceRepository
    path = tmp_path / 'absent' / 'missing.db'
    with pytest.raises((TypeError, ValueError)):
        cls(path)
    with pytest.raises(ValueError):
        cls(path, closed_snapshot=False)
    with pytest.raises(FileNotFoundError):
        cls(path, closed_snapshot=True).read_topic_bundle('course-ma','topic-lu',as_of=AS_OF)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('suffix', ['-wal', '-shm', '-journal'])
def test_sidecars_are_refused_without_reading_incomplete_snapshot(tmp_path, suffix):
    path = _database(tmp_path)
    Path(str(path) + suffix).write_bytes(b'synthetic active sidecar')
    before = inventory(tmp_path)
    with pytest.raises(api().TopicSnapshotError, match='sidecar'):
        read(path)
    assert inventory(tmp_path) == before


def test_real_open_wal_snapshot_is_refused(tmp_path):
    path = _database(tmp_path)
    with closing(sqlite3.connect(path)) as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.execute("UPDATE topics SET confidence=2 WHERE id='topic-lu'")
        c.commit()
        assert Path(str(path)+'-wal').exists()
        with pytest.raises(api().TopicSnapshotError, match='sidecar'):
            read(path)


def test_missing_schema_is_not_migrated(tmp_path):
    path = tmp_path / 'empty.db'
    with closing(sqlite3.connect(path)) as c:
        c.execute('CREATE TABLE unrelated (id TEXT)')
    before = inventory(tmp_path)
    with pytest.raises(api().TopicSchemaError):
        read(path)
    assert inventory(tmp_path) == before


@pytest.mark.parametrize('change', ["UPDATE topics SET deleted_at='2026-01-01' WHERE id='topic-lu'", "UPDATE courses SET deleted_at='2026-01-01' WHERE id='course-ma'"])
def test_deleted_identity_is_not_rebound_by_name(tmp_path, change):
    path = _database(tmp_path)
    update(path, change)
    with pytest.raises(api().TopicIdentityError):
        read(path)


def test_exact_course_topic_identity_required(tmp_path):
    path = _database(tmp_path)
    with pytest.raises(api().TopicIdentityError):
        api().SQLiteTopicIntelligenceRepository(path, closed_snapshot=True).read_topic_bundle('another-course','topic-lu',as_of=AS_OF)
    with pytest.raises(api().TopicIdentityError):
        read(path, 'LU Factorization')


@pytest.mark.parametrize('as_of', [datetime(2026,10,11), '2026-10-11', None])
def test_naive_or_missing_clock_rejected(tmp_path, as_of):
    with pytest.raises((TypeError, ValueError)):
        read(_database(tmp_path), as_of=as_of)


def test_invalid_timezone_rejected(tmp_path):
    with pytest.raises(ValueError):
        read(_database(tmp_path), timezone='not/a/timezone')


@pytest.mark.parametrize('stamp,reason', [('2026-09-20T10:30:00','occurrence_timezone_unknown'), ('invalid','occurrence_invalid'), ('2026-10-12T00:00:00Z','occurrence_after_as_of')])
def test_untrusted_occurrence_is_visible_but_excluded(tmp_path, stamp, reason):
    path = _database(tmp_path)
    update(path, "UPDATE assessment_test_sessions SET submitted_at=? WHERE id='s1'", (stamp,))
    e = next(e for e in read(path).evidence if e.evidence_id=='ev-sq1')
    assert e.occurred_at_raw == stamp and reason in e.exclusion_reasons
    assert not e.automatic_eligible


def test_self_entered_and_unanswered_rows_never_become_independent_evidence(tmp_path):
    path = _database(tmp_path)
    update(path, "UPDATE assessment_response_evaluations SET evaluator_type='user', outcome='unanswered', confidence=NULL WHERE id='ev-sq1'")
    e = read(path).evidence[0]
    assert e.grading_confidence is None
    assert {'self_reported_outcome','unanswered'} <= set(e.exclusion_reasons)
    assert not e.automatic_eligible


def test_unrelated_topic_does_not_change_evidence_fingerprint(tmp_path):
    path = _database(tmp_path)
    before = read(path)
    update(path, "UPDATE topics SET confidence=4 WHERE id='topic-rank'")
    after = read(path)
    assert before.evidence_fingerprint == after.evidence_fingerprint
    assert before.snapshot_sha256 != after.snapshot_sha256


def test_empty_topic_has_unknown_coverage_without_fabricated_zero_performance(tmp_path):
    path = _database(tmp_path)
    update(path, "INSERT INTO topics (id,course_id,name,normalized_name,status,created_at,updated_at) VALUES ('empty','course-ma','Empty','empty','not_started',?,?)", (NOW,NOW))
    b = read(path,'empty')
    assert b.evidence == ()
    assert b.supporting_sources_status == 'not_read_in_b1'
    assert not hasattr(b,'mastery_score')


def test_snapshot_connection_is_read_only_and_cannot_create_sidecars(tmp_path):
    path = _database(tmp_path)
    repo = api().SQLiteTopicIntelligenceRepository(path, closed_snapshot=True)
    before = inventory(tmp_path)
    with repo._snapshot() as (connection, digest):
        assert connection.execute('PRAGMA query_only').fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            connection.execute("UPDATE topics SET confidence=5")
        assert digest == before[path.name]
    assert inventory(tmp_path) == before


def test_changed_snapshot_is_rejected_before_return(tmp_path, monkeypatch):
    path = _database(tmp_path)
    cls = api().SQLiteTopicIntelligenceRepository
    original = cls._read
    def changed(self, *args):
        result = original(self, *args)
        update(path, "UPDATE topics SET confidence=3 WHERE id='topic-lu'")
        return result
    monkeypatch.setattr(cls, '_read', changed)
    with pytest.raises(api().TopicSnapshotError, match='changed'):
        read(path)


def test_symlink_snapshot_is_rejected(tmp_path):
    path = _database(tmp_path)
    link = tmp_path / 'alias.db'
    link.symlink_to(path)
    with pytest.raises(api().TopicSnapshotError, match='symlink'):
        read(link)


def test_cross_course_snapshot_is_disclosed_without_rebinding(tmp_path):
    path = _database(tmp_path)
    update(path, "INSERT INTO courses (id,code,name,status,created_at,updated_at) VALUES ('other','OTHER','Other course','active',?,?)", (NOW,NOW))
    update(path, "UPDATE assessments SET course_id='other' WHERE id='a1'")
    e = read(path).evidence[0]
    assert e.course_id == 'other' and 'cross_course_source' in e.exclusion_reasons
    assert not e.automatic_eligible


@pytest.mark.parametrize('sql', [
    "UPDATE assessment_response_evaluations SET question_id='q2' WHERE id='ev-sq1'",
    "UPDATE assessment_response_evaluations SET session_evaluation_id='se-s2' WHERE id='ev-sq1'",
    "UPDATE questions SET assessment_id='a2', ordinal=99 WHERE id='q1'",
])
def test_inconsistent_source_reference_is_not_trusted(tmp_path, sql):
    path = _database(tmp_path)
    update(path, sql)
    e = read(path).evidence[0]
    assert 'inconsistent_source_reference' in e.exclusion_reasons
    assert e.question_id == 'q1' and not e.automatic_eligible


def test_local_date_uses_configured_zone_without_reinterpreting_naive_time(tmp_path):
    path = _database(tmp_path)
    update(path, "UPDATE assessment_test_sessions SET submitted_at='2026-09-20T20:00:00Z' WHERE id='s1'")
    assert read(path).evidence[0].local_date.isoformat() == '2026-09-21'
    assert read(path, timezone='UTC').evidence[0].local_date.isoformat() == '2026-09-20'


def test_malformed_options_are_unknown_equivalence_not_new_independent_identity(tmp_path):
    path = _database(tmp_path)
    update(path, "UPDATE assessment_test_session_questions SET options_json='not json' WHERE id='sq1'")
    e = read(path).evidence[0]
    assert e.question_identity is None and 'question_identity_unknown' in e.exclusion_reasons


@pytest.mark.parametrize('sql', [
    "UPDATE assessment_test_sessions SET assessment_id='missing' WHERE id='s1'",
    "UPDATE assessment_test_session_questions SET session_id='missing' WHERE id='sq1'",
])
def test_orphaned_parents_reject_snapshot_instead_of_erasing_observations(tmp_path, sql):
    path = _database(tmp_path)
    update(path, sql)
    with pytest.raises(api().TopicSchemaError, match='parent'):
        read(path)


@pytest.mark.parametrize('evaluation_ref', ['ev-sq3', None])
def test_attempt_bridge_must_reference_exact_evaluation(tmp_path, evaluation_ref):
    path = _database(tmp_path)
    update(path, "INSERT INTO question_attempts (id,question_id,attempt_number,outcome,earned_marks_milli,max_marks_milli,occurred_at,evaluation_ref) VALUES ('attempt','q1',1,'partially_correct',1000,2000,?,?)", (NOW,evaluation_ref))
    update(path, "UPDATE assessment_response_evaluations SET question_attempt_id='attempt' WHERE id='ev-sq1'")
    e = read(path).evidence[0]
    assert 'inconsistent_bridge_reference' in e.exclusion_reasons
    assert ('question_attempt','attempt') in {(r.kind,r.identifier) for r in e.source_refs}


@pytest.mark.parametrize('event_attempt', [None, 'other-attempt'])
def test_mistake_bridge_must_exist_and_belong_to_evaluation_attempt(tmp_path, event_attempt):
    path = _database(tmp_path)
    if event_attempt:
        update(path, "INSERT INTO mistake_events (id,attempt_id,category,created_at) VALUES ('bad-event',?,'concept_gap',?)", (event_attempt,NOW))
    update(path, "UPDATE assessment_evaluation_mistakes SET mistake_event_id='bad-event' WHERE id='m1'")
    e = read(path).evidence[0]
    assert 'inconsistent_bridge_reference' in e.exclusion_reasons
    assert ('mistake_event','bad-event') in {(r.kind,r.identifier) for r in e.source_refs}


@pytest.mark.parametrize('table,column,value', [
    ('assessment_response_evaluations','awarded_marks_milli',1000.5),
    ('assessment_response_evaluations','max_marks_milli','bad'),
    ('assessment_test_session_questions','max_marks_milli',2000.5),
])
def test_noninteger_scores_reject_snapshot_with_typed_error(tmp_path, table, column, value):
    path = _database(tmp_path)
    identifier = 'sq1' if table.endswith('questions') else 'ev-sq1'
    update(path, f'UPDATE {table} SET {column}=? WHERE id=?', (value,identifier))
    with pytest.raises(api().TopicSchemaError, match='integer'):
        read(path)


@pytest.mark.parametrize('stamp', ['9999-12-31T23:59:59Z', '0001-01-01T00:00:00+01:00'])
def test_occurrence_conversion_overflow_is_retained_as_invalid(tmp_path, stamp):
    path = _database(tmp_path)
    update(path, "UPDATE assessment_test_sessions SET submitted_at=? WHERE id='s1'", (stamp,))
    e = next(e for e in read(path).evidence if e.evidence_id == 'ev-sq1')
    assert e.occurred_at_raw == stamp
    assert e.occurred_at_utc is None and e.local_date is None
    assert 'occurrence_invalid' in e.exclusion_reasons
