"""B3 manifest fixtures are disposable, never installed-authority evidence."""
from contextlib import closing
from dataclasses import FrozenInstanceError, asdict
import importlib
import json
import re
from pathlib import Path
import sqlite3

import pytest
from tests.test_topic_evidence_repository import _database, update, inventory

ROOT = Path(__file__).resolve().parents[1]


def api():
    name = 'personal_learning_assistant.repositories.sqlite.b3_authority_repository'
    assert (ROOT / (name.replace('.', '/') + '.py')).exists(), 'B3 authority inspector missing'
    return importlib.import_module(name)


def inspect(path, backend='sqlite', control_status='PASS'):
    module = api()
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as connection:
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')
        return module.inspect_authority(connection, expected_ledger=module.source_migration_ledger(ROOT),
                                        backend=backend, control_status=control_status)


def seed(path, store='courses', payload=None, stamp='2026-10-13T00:00:00Z'):
    if payload is None:
        payload = {'version': 1, 'courses': [{'id': 'course-ma', 'topics': [
            {'id': 'topic-lu'}, {'id': 'topic-rank'}]}]}
    update(path, 'INSERT OR REPLACE INTO app_settings(key,value_json,updated_at) VALUES(?,?,?)',
           ('phase4.compatibility_projection.' + store, json.dumps(payload), stamp))


def projection(result, name='courses'):
    return next(p for p in result.projections if p.store == name)


def test_manifest_reports_real_ledger_counts_and_unknown_historical_snapshots(tmp_path):
    path = _database(tmp_path)
    before = inventory(tmp_path)
    with closing(sqlite3.connect(path)) as c:
        sql_before = tuple(c.iterdump())
    first = inspect(path)
    assert first.ledger_status == first.schema_status == 'PASS'
    assert first.integrity_ok and first.foreign_key_violations == 0
    assert dict(first.relationship_counts)['assessment_response_evaluations'] == 5
    assert first.mapping_snapshot_status == first.independence_snapshot_status == 'UNVERIFIABLE'
    assert len(first.ledger) == 14 and len(first.projections) == 9
    assert inspect(path) == first
    after = inventory(tmp_path)
    assert all(after[key] == digest for key, digest in before.items())
    assert set(after) - set(before) <= {path.name + '-wal', path.name + '-shm'}
    with closing(sqlite3.connect(path)) as c:
        assert tuple(c.iterdump()) == sql_before
    assert 'course-ma' not in json.dumps(asdict(first))
    with pytest.raises(FrozenInstanceError):
        first.backend = 'legacy'


def test_requires_query_only_transaction_and_never_enables_writes(tmp_path):
    path = _database(tmp_path)
    module = api()
    with closing(sqlite3.connect(path)) as connection:
        with pytest.raises(ValueError, match='query-only'):
            module.inspect_authority(connection, expected_ledger=module.source_migration_ledger(ROOT), backend='sqlite', control_status='PASS')
        connection.execute('PRAGMA query_only=ON')
        with pytest.raises(ValueError, match='transaction'):
            module.inspect_authority(connection, expected_ledger=module.source_migration_ledger(ROOT), backend='sqlite', control_status='PASS')
        connection.execute('BEGIN')
        result = module.inspect_authority(connection, expected_ledger=module.source_migration_ledger(ROOT), backend='sqlite', control_status='PASS')
        assert result.total_changes == 0
        with pytest.raises(sqlite3.OperationalError):
            connection.execute('DELETE FROM topics')


@pytest.mark.parametrize('backend,control', [('legacy','PASS'), ('dual_read','PASS'), ('legacy','UNVERIFIABLE'), ('unknown','INVALID')])
def test_backend_selection_is_separate_from_normalized_schema(tmp_path, backend, control):
    result = inspect(_database(tmp_path), backend, control)
    assert result.backend == backend and result.control_status == control
    assert result.production_authority == 'BLOCKED'
    assert result.ledger_status == 'PASS'


@pytest.mark.parametrize('payload,status', [(None,'BLOCKED'), ({},'INVALID'), ({'version':1,'courses':'bad'},'INVALID'),
    ({'version':True,'courses':[]},'INVALID'), ({'version':999,'courses':[]},'UNVERIFIABLE')])
def test_missing_partial_and_unknown_version_projections(tmp_path, payload, status):
    path = _database(tmp_path)
    if payload is not None:
        seed(path, payload=payload)
    result = projection(inspect(path))
    assert result.structure_status == status
    assert result.freshness_status != 'PASS'


def test_corrupt_projection_is_invalid_not_empty_success(tmp_path):
    path = _database(tmp_path)
    seed(path)
    update(path, "UPDATE app_settings SET value_json='not JSON'")
    assert projection(inspect(path)).structure_status == 'INVALID'


def test_exact_identity_parity_is_not_a_freshness_watermark(tmp_path):
    path = _database(tmp_path)
    seed(path)
    result = projection(inspect(path))
    assert result.identity_status == 'PASS' and result.identity_mismatches == 0
    assert result.freshness_status == 'UNVERIFIABLE'
    assert result.watermark_available is False


@pytest.mark.parametrize('topic', ['TOPIC-LU', 'LU Factorization', 'missing', 'topic-rank'])
def test_conflicting_or_duplicate_canonical_ids_cannot_rebind_by_name(tmp_path, topic):
    path = _database(tmp_path)
    seed(path, payload={'version':1,'courses':[{'id':'course-ma','topics':[{'id':topic},{'id':'topic-rank'}]}]})
    result = projection(inspect(path))
    assert result.identity_status == 'INVALID' and result.identity_mismatches > 0


def test_source_revision_newer_than_projection_proves_stale(tmp_path):
    path = _database(tmp_path)
    seed(path, stamp='2026-09-01T00:00:00Z')
    assert projection(inspect(path)).freshness_status == 'INVALID'
    assert 'projection_stale' in projection(inspect(path)).reason_codes


def test_unknown_timestamp_cannot_prove_freshness(tmp_path):
    path = _database(tmp_path)
    seed(path, stamp='2026-10-13T00:00:00')
    assert projection(inspect(path)).freshness_status == 'UNVERIFIABLE'


def test_explicit_import_id_lineage_can_resolve_legacy_ids(tmp_path):
    path = _database(tmp_path)
    seed(path, payload={'version':1,'courses':[{'id':'public-course','topics':[{'id':'public-lu'},{'id':'public-rank'}]}]})
    for ordinal, table, key, target in [(1,'courses','course:id:public-course','course-ma'),
        (2,'topics','course:id:public-course/topic:id:public-lu','topic-lu'),
        (3,'topics','course:id:public-course/topic:id:public-rank','topic-rank')]:
        update(path, "INSERT INTO migration_imports(id,source_path,source_hash,source_type,legacy_key,target_table,target_id,imported_at) VALUES(?, 'data/courses.json', ?, 'legacy_json',?,?,?,?)",
               (str(ordinal),'a'*64,key,table,target,'2026-09-01T00:00:00Z'))
    assert projection(inspect(path)).identity_status == 'PASS'
    update(path, "INSERT INTO migration_imports(id,source_path,source_hash,source_type,legacy_key,target_table,target_id,imported_at) VALUES('conflict','data/courses.json',?,'legacy_json','course:id:public-course','courses','other',?)", ('b'*64,'2026-09-02T00:00:00Z'))
    assert projection(inspect(path)).identity_status == 'INVALID'


def test_cross_course_mapping_is_counted_as_identity_anomaly(tmp_path):
    path = _database(tmp_path)
    update(path, "INSERT INTO courses(id,code,name,status,created_at,updated_at) VALUES('other','OT','Other','active',?,?)", ('2026-09-01','2026-09-01'))
    update(path, "UPDATE topics SET course_id='other' WHERE id='topic-lu'")
    result = inspect(path)
    assert dict(result.identity_anomalies)['session_topic_course_conflicts'] > 0
    assert result.identity_status == 'INVALID'


@pytest.mark.parametrize('sql', ["UPDATE schema_migrations SET checksum='0'||substr(checksum,2) WHERE version=14", 'DROP TABLE topic_aliases'])
def test_bad_ledger_or_missing_table_cannot_pass(tmp_path, sql):
    path = _database(tmp_path)
    update(path, sql)
    result = inspect(path)
    assert result.ledger_status != 'PASS' or result.schema_status != 'PASS'
    assert result.production_authority == 'BLOCKED'


@pytest.mark.parametrize('table,parent', [('questions','assessments'), ('assessment_test_sessions','assessments'),
    ('assessment_test_responses','assessment_test_session_questions'), ('assessment_import_questions','questions'),
    ('question_sources','knowledge_documents'), ('question_topic_mappings','questions'),
    ('assessment_response_evaluations','question_attempts'), ('daily_agenda_items','daily_agendas'),
    ('study_plan_items','study_plans'), ('planner_tasks','month_plan_imports')])
def test_removed_declared_relationship_cannot_pass_schema_or_identity(tmp_path, table, parent):
    path = _database(tmp_path)
    with closing(sqlite3.connect(path)) as c, c:
        c.execute('PRAGMA writable_schema=ON')
        ddl = c.execute('SELECT sql FROM sqlite_master WHERE name=?',(table,)).fetchone()[0]
        changed = re.sub(r'REFERENCES\s+' + parent + r'\(id\)\s+ON DELETE (?:RESTRICT|CASCADE|SET NULL)', '', ddl)
        assert changed != ddl
        c.execute('UPDATE sqlite_master SET sql=? WHERE name=?',(changed,table))
        c.execute('PRAGMA writable_schema=OFF')
    result = inspect(path)
    assert result.ledger_status == 'PASS'
    assert result.schema_status == 'INVALID'
    assert result.identity_status != 'PASS'


def test_orphan_question_is_detected_even_when_fk_has_been_removed(tmp_path):
    path = _database(tmp_path)
    with closing(sqlite3.connect(path)) as c, c:
        c.execute('PRAGMA writable_schema=ON')
        c.execute("UPDATE sqlite_master SET sql=replace(sql,'REFERENCES assessments(id) ON DELETE RESTRICT','') WHERE name='questions'")
        c.execute('PRAGMA writable_schema=OFF')
    update(path, "INSERT INTO questions(id,assessment_id,ordinal,question_text,created_at,updated_at) VALUES('orphan','absent',1,'private','2026-01-01','2026-01-01')")
    result = inspect(path)
    assert result.schema_status == result.identity_status == 'INVALID'
    assert dict(result.identity_anomalies)['orphaned_relationships'] > 0


def test_temp_ledger_cannot_shadow_corrupt_main_authority(tmp_path):
    path = _database(tmp_path)
    update(path, "UPDATE schema_migrations SET checksum=? WHERE version=14", ('0'*64,))
    module = api()
    with closing(sqlite3.connect(path)) as c:
        c.execute('CREATE TEMP TABLE schema_migrations(version INTEGER,name TEXT,checksum TEXT)')
        c.executemany('INSERT INTO temp.schema_migrations VALUES(?,?,?)', module.source_migration_ledger(ROOT))
        c.commit()
        c.execute('PRAGMA query_only=ON')
        c.execute('BEGIN')
        with pytest.raises(ValueError, match='temporary'):
            module.inspect_authority(c, expected_ledger=module.source_migration_ledger(ROOT), backend='sqlite',control_status='PASS')


@pytest.mark.parametrize('reference,conflicts', [
    ('ev-sq1', 0),
    ('assessment_response_evaluation:ev-sq1', 0),
    ('assessment_response_evaluation:ev-sq3', 1),
    ('other_evaluation:ev-sq1', 1),
    (None, 1),
])
def test_attempt_bridge_accepts_only_exact_bare_or_writer_namespaced_identity(tmp_path, reference, conflicts):
    """Existing evaluation writer uses namespaced references, while old fixtures
    can have bare IDs. Both prove the same exact identity without trusting suffixes.
    """
    path = _database(tmp_path)
    update(path,
           "INSERT INTO question_attempts "
           "(id,question_id,attempt_number,outcome,earned_marks_milli,max_marks_milli,"
           "occurred_at,signed_score_milli,evaluation_ref) "
           "VALUES ('attempt','q1',1,'partially_correct',1000,2000,?,1000,?)",
           ('2026-09-20T10:30:00Z', reference))
    update(path, "UPDATE assessment_response_evaluations SET question_attempt_id='attempt' "
                 "WHERE id='ev-sq1'")
    before = inventory(tmp_path)
    report = inspect(path)
    assert dict(report.identity_anomalies)['attempt_bridge_conflicts'] == conflicts
    assert report.production_authority == 'BLOCKED'
    assert report.total_changes == 0
    after = inventory(tmp_path)
    assert all(after[name] == original for name, original in before.items())


def test_attempt_bridge_still_rejects_wrong_question_for_exact_eval_reference(tmp_path):
    path = _database(tmp_path)
    update(path,
           "INSERT INTO question_attempts "
           "(id,question_id,attempt_number,outcome,earned_marks_milli,max_marks_milli,"
           "occurred_at,signed_score_milli,evaluation_ref) "
           "VALUES ('attempt','q3',1,'partially_correct',1000,2000,?,1000,"
           "'assessment_response_evaluation:ev-sq1')",
           ('2026-09-20T10:30:00Z',))
    update(path, "UPDATE assessment_response_evaluations SET question_attempt_id='attempt' "
                 "WHERE id='ev-sq1'")
    assert dict(inspect(path).identity_anomalies)['attempt_bridge_conflicts'] == 1
