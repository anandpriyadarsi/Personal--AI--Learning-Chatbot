"""Aggregate-only inspection of an explicit query-only read transaction.

No default DB, migration, copy, fallback, live consumer or authority creation.
The caller owns the stable artifact/copy boundary and closes the connection.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from personal_learning_assistant.domain.b3_authority import (
    AuthorityStatus as S, B3AuthorityManifest, ProjectionInspection,
)


REQUIRED_COLUMNS = {
    'schema_migrations': ('version', 'name', 'checksum'),
    'app_settings': ('key', 'value_json', 'updated_at'),
    'migration_imports': ('source_path', 'source_type', 'legacy_key', 'target_table', 'target_id', 'source_hash', 'source_version'),
    'courses': ('id', 'updated_at', 'deleted_at'),
    'topics': ('id', 'course_id', 'updated_at', 'deleted_at'),
    'topic_aliases': ('topic_id', 'course_id'),
    'assessments': ('id', 'course_id', 'updated_at', 'deleted_at'),
    'questions': ('id', 'assessment_id', 'updated_at', 'deleted_at'),
    'question_sources': ('id', 'question_id'),
    'question_topic_mappings': ('id', 'question_id', 'topic_id', 'score', 'method', 'state'),
    'assessment_import_batches': ('id', 'course_id', 'assessment_id', 'status', 'source_sha256'),
    'assessment_import_questions': ('id', 'batch_id', 'canonical_question_id', 'selected_topic_id', 'mapping_confidence', 'review_required'),
    'assessment_test_sessions': ('id', 'assessment_id', 'status'),
    'assessment_test_session_questions': ('id', 'session_id', 'question_id', 'topic_id'),
    'assessment_test_responses': ('id', 'session_question_id'),
    'assessment_session_evaluations': ('id', 'session_id'),
    'assessment_response_evaluations': ('id', 'session_evaluation_id', 'session_question_id', 'question_id', 'response_id', 'question_attempt_id'),
    'assessment_evaluation_mistakes': ('id', 'response_evaluation_id', 'mistake_event_id'),
    'question_attempts': ('id', 'question_id', 'evaluation_ref'),
    'mistake_events': ('id', 'attempt_id'),
    'planner_tasks': ('id',), 'daily_agendas': ('id',), 'daily_agenda_items': ('id',),
    'study_plans': ('id', 'updated_at'), 'study_plan_items': ('id',),
    'study_sessions': ('id',), 'assessment_recovery_recommendations': ('id',),
}

PROJECTION_SHAPES = {
    'courses': (1, 'courses', list), 'assessments': (2, 'assessments', list),
    'assessment_workspace': (1, 'workspaces', dict), 'learning_memory': (2, 'course_memory', dict),
    'course_progress_history': (1, 'courses', dict), 'weekly_study_plans': (1, 'plans', list),
    'multi_course_weekly_plans': (1, 'plans', list), 'intelligent_study_plans': (1, 'plans', list),
    'semester_grade_config': (1, 'courses', list),
}

# Declared FK ownership/actions in the immutable 0001-0014 source schema.
# This is a versioned adapter contract, never a second data authority.
EXPECTED_RELATIONSHIPS = (
    ('assessment_evaluation_mistakes', 'mistake_event_id', 'mistake_events', 'RESTRICT'),
    ('assessment_evaluation_mistakes', 'response_evaluation_id', 'assessment_response_evaluations', 'CASCADE'),
    ('assessment_import_batches', 'assessment_id', 'assessments', 'RESTRICT'),
    ('assessment_import_batches', 'course_id', 'courses', 'RESTRICT'),
    ('assessment_import_questions', 'batch_id', 'assessment_import_batches', 'CASCADE'),
    ('assessment_import_questions', 'canonical_question_id', 'questions', 'RESTRICT'),
    ('assessment_import_questions', 'selected_topic_id', 'topics', 'RESTRICT'),
    ('assessment_recovery_recommendations', 'course_id', 'courses', 'RESTRICT'),
    ('assessment_recovery_recommendations', 'planner_task_id', 'planner_tasks', 'RESTRICT'),
    ('assessment_recovery_recommendations', 'topic_id', 'topics', 'RESTRICT'),
    ('assessment_response_evaluations', 'question_attempt_id', 'question_attempts', 'RESTRICT'),
    ('assessment_response_evaluations', 'question_id', 'questions', 'RESTRICT'),
    ('assessment_response_evaluations', 'response_id', 'assessment_test_responses', 'RESTRICT'),
    ('assessment_response_evaluations', 'session_evaluation_id', 'assessment_session_evaluations', 'CASCADE'),
    ('assessment_response_evaluations', 'session_question_id', 'assessment_test_session_questions', 'CASCADE'),
    ('assessment_session_evaluations', 'session_id', 'assessment_test_sessions', 'CASCADE'),
    ('assessment_test_responses', 'session_question_id', 'assessment_test_session_questions', 'CASCADE'),
    ('assessment_test_session_questions', 'question_id', 'questions', 'RESTRICT'),
    ('assessment_test_session_questions', 'session_id', 'assessment_test_sessions', 'CASCADE'),
    ('assessment_test_session_questions', 'topic_id', 'topics', 'RESTRICT'),
    ('assessment_test_sessions', 'assessment_id', 'assessments', 'RESTRICT'),
    ('assessments', 'course_id', 'courses', 'RESTRICT'),
    ('daily_agenda_items', 'agenda_id', 'daily_agendas', 'CASCADE'),
    ('mistake_events', 'attempt_id', 'question_attempts', 'RESTRICT'),
    ('planner_tasks', 'assessment_id', 'assessments', 'RESTRICT'),
    ('planner_tasks', 'course_id', 'courses', 'RESTRICT'),
    ('planner_tasks', 'source_import_id', 'month_plan_imports', 'SET NULL'),
    ('planner_tasks', 'topic_id', 'topics', 'RESTRICT'),
    ('question_attempts', 'question_id', 'questions', 'RESTRICT'),
    ('question_sources', 'document_id', 'knowledge_documents', 'RESTRICT'),
    ('question_sources', 'note_id', 'note_metadata', 'RESTRICT'),
    ('question_sources', 'question_id', 'questions', 'RESTRICT'),
    ('question_sources', 'resource_id', 'resources', 'RESTRICT'),
    ('question_topic_mappings', 'question_id', 'questions', 'RESTRICT'),
    ('question_topic_mappings', 'topic_id', 'topics', 'RESTRICT'),
    ('questions', 'assessment_id', 'assessments', 'RESTRICT'),
    ('study_plan_items', 'assessment_id', 'assessments', 'RESTRICT'),
    ('study_plan_items', 'course_id', 'courses', 'RESTRICT'),
    ('study_plan_items', 'note_id', 'note_metadata', 'RESTRICT'),
    ('study_plan_items', 'plan_id', 'study_plans', 'RESTRICT'),
    ('study_plan_items', 'resource_id', 'resources', 'RESTRICT'),
    ('study_plan_items', 'topic_id', 'topics', 'RESTRICT'),
    ('study_sessions', 'assessment_id', 'assessments', 'RESTRICT'),
    ('study_sessions', 'course_id', 'courses', 'RESTRICT'),
    ('study_sessions', 'note_id', 'note_metadata', 'RESTRICT'),
    ('study_sessions', 'plan_item_id', 'study_plan_items', 'RESTRICT'),
    ('study_sessions', 'resource_id', 'resources', 'RESTRICT'),
    ('study_sessions', 'topic_id', 'topics', 'RESTRICT'),
    ('topic_aliases', 'course_id', 'courses', 'RESTRICT'),
    ('topic_aliases', 'topic_id', 'topics', 'RESTRICT'),
    ('topics', 'course_id', 'courses', 'RESTRICT'),
)

ANOMALY_QUERIES = {
    'alias_course_conflicts': 'SELECT count(*) FROM main.topic_aliases x JOIN main.topics t ON t.id=x.topic_id WHERE x.course_id<>t.course_id',
    'mapping_course_conflicts': 'SELECT count(*) FROM main.question_topic_mappings x JOIN main.questions q ON q.id=x.question_id JOIN main.assessments a ON a.id=q.assessment_id JOIN main.topics t ON t.id=x.topic_id WHERE a.course_id<>t.course_id',
    'session_topic_course_conflicts': 'SELECT count(*) FROM main.assessment_test_session_questions x JOIN main.assessment_test_sessions s ON s.id=x.session_id JOIN main.assessments a ON a.id=s.assessment_id JOIN main.topics t ON t.id=x.topic_id WHERE a.course_id<>t.course_id',
    'session_question_assessment_conflicts': 'SELECT count(*) FROM main.assessment_test_session_questions x JOIN main.assessment_test_sessions s ON s.id=x.session_id JOIN main.questions q ON q.id=x.question_id WHERE s.assessment_id<>q.assessment_id',
    'evaluation_reference_conflicts': 'SELECT count(*) FROM main.assessment_response_evaluations e JOIN main.assessment_test_session_questions q ON q.id=e.session_question_id JOIN main.assessment_session_evaluations s ON s.id=e.session_evaluation_id JOIN main.assessment_test_responses r ON r.id=e.response_id WHERE e.question_id<>q.question_id OR s.session_id<>q.session_id OR r.session_question_id<>q.id',
    'attempt_bridge_conflicts': 'SELECT count(*) FROM main.assessment_response_evaluations e LEFT JOIN main.question_attempts a ON a.id=e.question_attempt_id WHERE e.question_attempt_id IS NOT NULL AND (a.id IS NULL OR a.question_id<>e.question_id OR a.evaluation_ref IS NULL OR a.evaluation_ref<>e.id)',
    'mistake_bridge_conflicts': 'SELECT count(*) FROM main.assessment_evaluation_mistakes m JOIN main.assessment_response_evaluations e ON e.id=m.response_evaluation_id LEFT JOIN main.mistake_events x ON x.id=m.mistake_event_id WHERE m.mistake_event_id IS NOT NULL AND (x.id IS NULL OR x.attempt_id IS NULL OR e.question_attempt_id IS NULL OR x.attempt_id<>e.question_attempt_id)',
    'import_topic_course_conflicts': 'SELECT count(*) FROM main.assessment_import_questions q JOIN main.assessment_import_batches b ON b.id=q.batch_id JOIN main.topics t ON t.id=q.selected_topic_id WHERE t.course_id<>b.course_id',
}


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def source_migration_ledger(repo: Path) -> tuple[tuple[int, str, str], ...]:
    root = Path(repo).absolute() / 'personal_learning_assistant/repositories/sqlite/migrations'
    if any(p.is_symlink() for p in (root, *root.parents)) or not root.is_dir():
        raise ValueError('Source migration inventory unavailable')
    result = []
    for path in sorted(root.glob('*.sql')):
        match = re.fullmatch(r'(\d{4})_(.+)\.sql', path.name)
        if match is None or path.is_symlink() or not path.is_file():
            raise ValueError('Source migration inventory invalid')
        result.append((int(match[1]), match[2], hashlib.sha256(path.read_bytes()).hexdigest()))
    if not result or [x[0] for x in result] != list(range(1, len(result) + 1)):
        raise ValueError('Source migration ledger must be contiguous')
    return tuple(result)


def _stamp(raw):
    try:
        value = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if value.tzinfo is None or value.utcoffset() is None:
            return None
        return value.astimezone(timezone.utc)
    except (TypeError, AttributeError, ValueError, OverflowError):
        return None


def _course_identity(connection, payload):
    courses = {r[0] for r in connection.execute('SELECT id FROM main.courses WHERE deleted_at IS NULL')}
    topics = {(r[0], r[1]) for r in connection.execute('SELECT course_id,id FROM main.topics WHERE deleted_at IS NULL')}
    links = {}
    for table, key, target in connection.execute("SELECT target_table,legacy_key,target_id FROM main.migration_imports WHERE source_path='data/courses.json' AND source_type='legacy_json' AND target_table IN ('courses','topics')"):
        links.setdefault((table, key), set()).add(target)
    invalid = 0
    unknown = False
    seen_courses, seen_topics = set(), set()
    def resolve(table, value, key, active):
        nonlocal invalid
        linked = links.get((table, key), set())
        candidates = linked | ({value} if value in active else set())
        if len(candidates) != 1 or not candidates <= active:
            invalid += 1
            return None
        return next(iter(candidates))
    for course in payload['courses']:
        if not isinstance(course, dict) or not isinstance(course.get('topics'), list):
            return S.INVALID, 1
        cid = course.get('id')
        if not isinstance(cid, str) or not cid:
            unknown = True
            continue
        key = 'course:id:' + cid
        canonical = resolve('courses', cid, key, courses)
        if canonical in seen_courses:
            invalid += 1
        if canonical is not None:
            seen_courses.add(canonical)
        for topic in course['topics']:
            if not isinstance(topic, dict) or not isinstance(topic.get('id'), str) or not topic['id']:
                unknown = True
                continue
            tid = resolve('topics', topic['id'], key + '/topic:id:' + topic['id'], {x[1] for x in topics})
            pair = (canonical, tid)
            if tid is not None and canonical is not None:
                if pair not in topics or pair in seen_topics:
                    invalid += 1
                seen_topics.add(pair)
    if unknown:
        return (S.INVALID, invalid) if invalid else (S.UNVERIFIABLE, None)
    invalid += len(courses ^ seen_courses) + len(topics ^ seen_topics)
    return (S.INVALID if invalid else S.PASS), invalid


def _projection(connection, store):
    row = connection.execute('SELECT value_json,updated_at FROM main.app_settings WHERE key=?', ('phase4.compatibility_projection.' + store,)).fetchone()
    if row is None:
        return ProjectionInspection(store, None, S.BLOCKED, S.UNVERIFIABLE, S.UNVERIFIABLE, reason_codes=('projection_missing',))
    try:
        payload = json.loads(row[0], parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
        version, key, shape = PROJECTION_SHAPES[store]
        if not isinstance(payload, dict) or type(payload.get('version')) is not int or not isinstance(payload.get(key), shape):
            raise ValueError('Invalid projection shape')
    except (TypeError, ValueError):
        return ProjectionInspection(store, None, S.INVALID, S.UNVERIFIABLE, S.UNVERIFIABLE, reason_codes=('projection_invalid',))
    if payload['version'] != version:
        return ProjectionInspection(store, payload['version'], S.UNVERIFIABLE, S.UNVERIFIABLE, S.UNVERIFIABLE, reason_codes=('projection_version_unsupported',))
    identity, mismatches = _course_identity(connection, payload) if store == 'courses' else (S.UNVERIFIABLE, None)
    freshness, reasons = S.UNVERIFIABLE, ['projection_watermark_unavailable']
    tables = {'courses': ('courses','topics'), 'assessments': ('assessments',), 'assessment_workspace': ('questions',),
              'weekly_study_plans': ('study_plans',), 'multi_course_weekly_plans': ('study_plans',), 'intelligent_study_plans': ('study_plans',)}.get(store, ())
    projection_time = _stamp(row[1])
    if projection_time is not None:
        for table in tables:
            stamps = [_stamp(r[0]) for r in connection.execute('SELECT updated_at FROM main.' + table)]
            if any(stamp is not None and stamp > projection_time for stamp in stamps):
                freshness = S.INVALID
                reasons.append('projection_stale')
                break
    return ProjectionInspection(store, payload['version'], S.PASS, identity, freshness, mismatches, reason_codes=tuple(reasons))


def inspect_authority(connection: sqlite3.Connection, *, expected_ledger: tuple,
                      backend: str, control_status: str) -> B3AuthorityManifest:
    if connection.execute('PRAGMA query_only').fetchone()[0] != 1:
        raise ValueError('An explicit query-only connection is required')
    if not connection.in_transaction:
        raise ValueError('An explicit read transaction is required')
    if connection.execute('SELECT count(*) FROM temp.sqlite_master').fetchone()[0]:
        raise ValueError('Connections with temporary schema objects are unsupported')
    if backend not in ('legacy', 'dual_read', 'sqlite', 'unknown'):
        raise ValueError('Unknown backend contract')
    status = S(control_status)
    before = connection.total_changes
    tables = {r[0]: r[1] for r in connection.execute("SELECT name,sql FROM main.sqlite_master WHERE type='table'")}
    missing = tuple(sorted(set(REQUIRED_COLUMNS) - tables.keys()))
    schema_ok = not missing
    counts, fks = [], []
    for table, columns in REQUIRED_COLUMNS.items():
        if table in tables:
            present = {r[1] for r in connection.execute('PRAGMA main.table_info(' + table + ')')}
            ownership_columns = {column for child,column,_,_ in EXPECTED_RELATIONSHIPS if child == table}
            schema_ok &= (set(columns) | ownership_columns) <= present
            counts.append((table, connection.execute('SELECT count(*) FROM main.' + table).fetchone()[0]))
            fks.extend((table, *r) for r in connection.execute('PRAGMA main.foreign_key_list(' + table + ')'))
    edges = {(r[0], r[4], r[3], r[7]) for r in fks if r[5] == 'id' and r[6] == 'NO ACTION'}
    schema_ok &= set(EXPECTED_RELATIONSHIPS) <= edges
    actual = tuple(tuple(r) for r in connection.execute('SELECT version,name,checksum FROM main.schema_migrations ORDER BY version')) if 'schema_migrations' in tables else ()
    ledger_status = S.PASS if actual == expected_ledger and bool(expected_ledger) else S.INVALID
    # Never export unexpected ledger names or arbitrary checksum text.
    known_names = {x[1] for x in expected_ledger}
    ledger = tuple((r[0] if type(r[0]) is int else -1, r[1] if r[1] in known_names else 'unrecognized_migration',
                    r[2] if isinstance(r[2], str) and re.fullmatch('[0-9a-f]{64}', r[2]) else _digest(r[2])) for r in actual)
    integrity = [tuple(r) for r in connection.execute('PRAGMA main.integrity_check')] == [('ok',)]
    fk_count = len(connection.execute('PRAGMA main.foreign_key_check').fetchall())
    anomalies = []
    orphan_count = 0
    for child, column, parent, _ in EXPECTED_RELATIONSHIPS:
        try:
            count = connection.execute('SELECT count(*) FROM main.' + child + ' c LEFT JOIN main.' + parent +
                ' p ON p.id=c.' + column + ' WHERE c.' + column + ' IS NOT NULL AND p.id IS NULL').fetchone()[0]
            if orphan_count is not None:
                orphan_count += count
        except sqlite3.DatabaseError:
            orphan_count = None
    anomalies.append(('orphaned_relationships', orphan_count))
    for name, query in ANOMALY_QUERIES.items():
        try:
            count = connection.execute(query).fetchone()[0]
        except sqlite3.DatabaseError:
            count = None
        anomalies.append((name, count))
    identity = S.INVALID if fk_count or any(v for _, v in anomalies) else (S.UNVERIFIABLE if not schema_ok or any(v is None for _, v in anomalies) else S.PASS)
    projections = []
    for store in sorted(PROJECTION_SHAPES):
        try:
            projections.append(_projection(connection, store))
        except sqlite3.DatabaseError:
            projections.append(ProjectionInspection(store, None, S.BLOCKED, S.UNVERIFIABLE, S.UNVERIFIABLE, reason_codes=('projection_schema_unavailable',)))
    if connection.total_changes != before:
        raise RuntimeError('Inspection mutated SQL state')
    return B3AuthorityManifest(backend, status, ledger_status, ledger, S.PASS if schema_ok else S.INVALID,
        _digest(sorted((k,v) for k,v in tables.items() if k in REQUIRED_COLUMNS)), _digest(fks), missing,
        integrity, fk_count, identity, tuple(sorted(anomalies)), tuple(sorted(counts)), tuple(projections), 0)
