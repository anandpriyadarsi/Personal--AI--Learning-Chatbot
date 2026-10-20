"""B1 reader for an explicitly supplied closed, checkpointed SQLite snapshot.

No default database, snapshot copying, migrations, JSON fallback or consumers.
Never supply a live database: immutable reads deliberately cannot see WAL data.
The caller must first acquire a consistent closed artifact; live authority is a
separate gate. Sidecar/stability checks reject observable violations, not prove
that arbitrary external writers are absent.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone as datetime_timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import unicodedata
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from personal_learning_assistant.domain.topic_intelligence import (
    EvidenceReference, IndependenceSnapshot, MappingSnapshot,
    TopicEvidence, TopicEvidenceBundle, TopicIdentity,
)


class TopicSnapshotError(ValueError):
    """Snapshot is not an explicit stable closed artifact."""


class TopicSchemaError(RuntimeError):
    """Required normalized schema or source integrity is unavailable."""


class TopicIdentityError(ValueError):
    """Exact active canonical course/topic identity is unavailable."""


def _aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('An explicit timezone-aware as_of datetime is required')
    return value.astimezone(datetime_timezone.utc)


def _occurrence(raw, as_of, zone, reasons):
    if not raw:
        reasons.add('occurrence_missing')
        return None, None
    try:
        parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            reasons.add('occurrence_timezone_unknown')
            return None, None
        parsed = parsed.astimezone(datetime_timezone.utc)
        local_date = parsed.astimezone(zone).date()
    except (ValueError, TypeError, AttributeError, OverflowError):
        reasons.add('occurrence_invalid')
        return None, None
    if parsed > as_of:
        reasons.add('occurrence_after_as_of')
    return parsed, local_date


def _normalize(value):
    if isinstance(value, str):
        return ' '.join(unicodedata.normalize('NFC', value).split())
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in sorted(value.items())}
    return value


def _question_identity(row, reasons):
    try:
        options = json.loads(row['options_json'])
        if not isinstance(options, list) or not row['question_text'].strip():
            raise ValueError('Question snapshot unavailable')
        value = _normalize([row['question_type'], row['question_text'], options])
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, AttributeError):
        reasons.add('question_identity_unknown')
        return None
    return 'snapshot-sha256:' + hashlib.sha256(encoded).hexdigest()


class SQLiteTopicIntelligenceRepository:
    def __init__(self, snapshot_path: str | Path, *, closed_snapshot: bool):
        if closed_snapshot is not True:
            raise TopicSnapshotError('Explicit closed_snapshot=True attestation required')
        self.snapshot_path = Path(snapshot_path).absolute()

    def _inventory(self):
        path = self.snapshot_path
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise TopicSnapshotError('Snapshot path must not contain symlinks')
        if not path.is_file():
            raise FileNotFoundError('Existing regular snapshot file required')
        if any(Path(str(path) + s).exists() or Path(str(path) + s).is_symlink()
               for s in ('-wal', '-shm', '-journal')):
            raise TopicSnapshotError('Closed snapshot must have no SQLite sidecars')
        stat = path.stat()
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, digest.hexdigest())

    @contextmanager
    def _snapshot(self):
        before = self._inventory()
        connection = sqlite3.connect(self.snapshot_path.as_uri() + '?mode=ro&immutable=1', uri=True)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute('PRAGMA query_only=ON')
            connection.execute('BEGIN')
            yield connection, before[-1]
        finally:
            connection.close()
        if self._inventory() != before:
            raise TopicSnapshotError('Snapshot changed during read; result discarded')

    def read_topic_bundle(self, course_id: str, topic_id: str, *, as_of: datetime,
                          timezone: str = 'Asia/Kolkata') -> TopicEvidenceBundle:
        as_of = _aware_utc(as_of)
        try:
            zone = ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, TypeError) as error:
            raise ValueError('Valid configured timezone required') from error
        if not isinstance(course_id, str) or not isinstance(topic_id, str) or not course_id or not topic_id:
            raise TopicIdentityError('Exact canonical identifiers required')
        try:
            with self._snapshot() as (connection, digest):
                topic, evidence = self._read(connection, course_id, topic_id, as_of, zone)
        except sqlite3.DatabaseError as error:
            raise TopicSchemaError('Normalized Topic Intelligence snapshot schema is unavailable') from error
        payload = {'topic': asdict(topic), 'evidence': [asdict(e) for e in evidence],
                   'as_of': as_of.isoformat(), 'timezone': timezone, 'contract': 'topic-evidence-b1-v1'}
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                                default=lambda x: x.isoformat(), allow_nan=False).encode()).hexdigest()
        return TopicEvidenceBundle(topic, evidence, as_of, timezone, digest, fingerprint)

    def _read(self, connection, course_id, topic_id, as_of, zone):
        identity = connection.execute(
            'SELECT c.id AS course_id,c.code,c.name AS course_name,t.id AS topic_id,'
            't.name AS topic_name,t.status,t.confidence FROM topics t JOIN courses c ON c.id=t.course_id '
            'WHERE c.id=? AND t.id=? AND c.deleted_at IS NULL AND t.deleted_at IS NULL',
            (course_id, topic_id)).fetchone()
        if identity is None:
            raise TopicIdentityError('Active canonical course/topic pair not found')
        topic = TopicIdentity(identity['course_id'], identity['code'], identity['course_name'],
                              identity['topic_id'], identity['topic_name'], identity['status'], identity['confidence'])
        rows = connection.execute('''
            SELECT ev.*, sq.session_id, sq.question_id AS snapshot_question_id, sq.ordinal,
                sq.topic_id, sq.question_type, sq.question_text, sq.options_json, sq.difficulty,
                sq.max_marks_milli AS snapshot_max_marks, s.assessment_id, s.mode, s.status AS session_status,
                s.id AS source_session_id,a.id AS source_assessment_id,
                s.submitted_at,s.expires_at,a.course_id,a.deleted_at AS assessment_deleted,
                q.assessment_id AS question_assessment_id,q.deleted_at AS question_deleted,
                se.session_id AS evaluation_session_id,se.status AS session_evaluation_status,
                tr.session_question_id AS response_question_id
            FROM assessment_response_evaluations ev
            JOIN assessment_test_session_questions sq ON sq.id=ev.session_question_id
            LEFT JOIN assessment_test_sessions s ON s.id=sq.session_id
            LEFT JOIN assessments a ON a.id=s.assessment_id
            LEFT JOIN questions q ON q.id=sq.question_id
            LEFT JOIN assessment_session_evaluations se ON se.id=ev.session_evaluation_id
            LEFT JOIN assessment_test_responses tr ON tr.id=ev.response_id
            WHERE sq.topic_id=? ORDER BY s.id,sq.ordinal,ev.id
        ''', (topic_id,)).fetchall()
        observations = []
        for row in rows:
            if row['source_session_id'] is None or row['source_assessment_id'] is None:
                raise TopicSchemaError('Evidence parent session or assessment is missing')
            for column in ('awarded_marks_milli', 'max_marks_milli', 'snapshot_max_marks'):
                if column == 'awarded_marks_milli' and row[column] is None:
                    continue
                if type(row[column]) is not int:
                    raise TopicSchemaError('Evidence scores must be signed integer milli-marks')
            reasons = {'mapping_snapshot_unknown', 'independence_unknown'}
            if row['course_id'] != course_id:
                reasons.add('cross_course_source')
            if (row['question_id'] != row['snapshot_question_id'] or
                    row['question_assessment_id'] != row['assessment_id'] or
                    row['evaluation_session_id'] != row['session_id'] or
                    row['response_question_id'] != row['session_question_id']):
                reasons.add('inconsistent_source_reference')
            if row['assessment_deleted'] or row['question_deleted']:
                reasons.add('deleted_source')
            if row['session_status'] not in ('submitted', 'expired'):
                reasons.add('session_not_terminal')
            if row['session_evaluation_status'] != 'confirmed' or row['status'] not in ('confirmed', 'auto_confirmed'):
                reasons.add('evaluation_not_confirmed')
            if row['evaluator_type'] == 'user':
                reasons.add('self_reported_outcome')
            if row['awarded_marks_milli'] is None:
                reasons.add('score_unavailable')
            if row['max_marks_milli'] != row['snapshot_max_marks']:
                reasons.add('score_snapshot_mismatch')
            if row['max_marks_milli'] <= 0:
                reasons.add('nonpositive_maximum')
            if row['outcome'] == 'unanswered':
                reasons.add('unanswered')
            raw = row['submitted_at'] or (row['expires_at'] if row['session_status'] == 'expired' else None)
            occurred, local_date = _occurrence(raw, as_of, zone, reasons)
            question_identity = _question_identity(row, reasons)
            refs = {('response_evaluation',row['id']), ('session_evaluation',row['session_evaluation_id']),
                    ('assessment',row['assessment_id']), ('session',row['session_id']),
                    ('session_question',row['session_question_id']), ('question',row['snapshot_question_id']),
                    ('response',row['response_id'])}
            if row['question_attempt_id']:
                refs.add(('question_attempt',row['question_attempt_id']))
                attempt = connection.execute('SELECT question_id,evaluation_ref FROM question_attempts WHERE id=?', (row['question_attempt_id'],)).fetchone()
                if (attempt is None or attempt['question_id'] != row['snapshot_question_id'] or
                        attempt['evaluation_ref'] not in (row['id'], 'assessment_response_evaluation:' + row['id'])):
                    reasons.add('inconsistent_bridge_reference')
            mistakes = connection.execute('SELECT id,category,mistake_event_id FROM assessment_evaluation_mistakes '
                                          "WHERE response_evaluation_id=? AND status='confirmed' ORDER BY category,id", (row['id'],)).fetchall()
            for mistake in mistakes:
                refs.add(('evaluation_mistake',mistake['id']))
                if mistake['mistake_event_id']:
                    refs.add(('mistake_event',mistake['mistake_event_id']))
                    event = connection.execute('SELECT attempt_id FROM mistake_events WHERE id=?',
                                               (mistake['mistake_event_id'],)).fetchone()
                    if event is None or event['attempt_id'] != row['question_attempt_id']:
                        reasons.add('inconsistent_bridge_reference')
            observations.append(TopicEvidence(
                evidence_id=row['id'], session_evaluation_id=row['session_evaluation_id'],
                session_question_id=row['session_question_id'], response_id=row['response_id'],
                question_id=row['snapshot_question_id'], question_identity=question_identity,
                session_id=row['session_id'], assessment_id=row['assessment_id'], course_id=row['course_id'],
                topic_id=row['topic_id'], ordinal=row['ordinal'], mode=row['mode'], session_status=row['session_status'],
                occurred_at_raw=raw, occurred_at_utc=occurred, local_date=local_date,
                awarded_marks_milli=row['awarded_marks_milli'], max_marks_milli=row['max_marks_milli'],
                outcome=row['outcome'], evaluation_status=row['status'],
                session_evaluation_status=row['session_evaluation_status'], evaluator_type=row['evaluator_type'],
                grading_confidence=row['confidence'], rubric_version=row['rubric_version'], difficulty=row['difficulty'],
                mapping=MappingSnapshot(), independence=IndependenceSnapshot(),
                mistake_categories=tuple(sorted({m['category'] for m in mistakes})),
                source_refs=tuple(EvidenceReference(*ref) for ref in sorted(refs)),
                exclusion_reasons=tuple(sorted(reasons))))
        observations.sort(key=lambda e: (e.occurred_at_utc is None,
                          e.occurred_at_utc or datetime.max.replace(tzinfo=datetime_timezone.utc),
                          e.session_id, e.ordinal, e.evidence_id))
        return topic, tuple(observations)
