"""Optional, minimal offline-help receipts in the existing Tutor owner.

Reading history uses only AcademicEvidenceService's captured RAM connection.
Writing still passes through TutorSessionService and SQLiteTutorRepository; no
transcript, provider request, migration, or second persistence store is involved.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import re
import sqlite3

from personal_learning_assistant.domain.tutor_models import TutorSessionSpec
from personal_learning_assistant.learning_studio.validation import PackageError, require, validate_mapping
from personal_learning_assistant.learning_studio.grounded_help import LEVELS, consume
from personal_learning_assistant.repositories.sqlite.connection import transaction
from personal_learning_assistant.repositories.sqlite.tutor_repository import SQLiteTutorRepository, TutorRepositoryError
from personal_learning_assistant.services.tutor_session_service import TutorSessionService

SCHEMA = 'anvaya.learning-tutor-session.v1'
PREFIX = 'learning-tutor-v24-'
SCAN_LIMIT = 50
MAX_METADATA_BYTES = 8192
MAX_HISTORY_BYTES = 65536
METADATA_FIELDS = frozenset(('schema', 'module_id', 'module_revision', 'source_id',
    'source_sha256', 'question_id', 'question_revision', 'event_id', 'course_id',
    'topic_id', 'assistance_level', 'evidence_fingerprint', 'reviewed_at'))


def precise_utc_now():
    return datetime.now(timezone.utc).isoformat()


def _clock(value):
    require(isinstance(value, str) and len(value) <= 64, 'Invalid receipt clock.', 409)
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        require(stamp.tzinfo is not None and stamp.utcoffset() is not None,
                'Aware receipt clock required.', 409)
        return stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError) as error:
        raise PackageError('Invalid receipt clock.', 409) from error


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def validate_metadata(value):
    require(isinstance(value, dict) and set(value) == METADATA_FIELDS and value.get('schema') == SCHEMA,
            'Unsupported learning receipt metadata.', 409)
    require(len(_json(value).encode()) <= MAX_METADATA_BYTES, 'Receipt metadata exceeds its bound.', 413)
    for key in ('module_id', 'source_id', 'question_id', 'event_id', 'course_id', 'topic_id'):
        require(isinstance(value[key], str) and 0 < len(value[key]) <= 256 and
                not any(ord(c) < 32 for c in value[key]), 'Invalid exact receipt identity.', 409)
    for key in ('module_revision', 'question_revision'):
        require(type(value[key]) is int and 1 <= value[key] <= 1_000_000,
                'Invalid receipt revision.', 409)
    for key in ('source_sha256', 'evidence_fingerprint'):
        require(isinstance(value[key], str) and re.fullmatch('[0-9a-f]{64}', value[key]) is not None,
                'Invalid receipt fingerprint.', 409)
    require(value['assistance_level'] in LEVELS, 'Invalid assistance level.', 409)
    _clock(value['reviewed_at'])
    return value


def metadata_for_help(view, help_view, reviewed_at):
    require(help_view['evidence_fingerprint'] == view.fingerprint and
            help_view['source_sha256'] == view.source_sha256, 'Help context changed.', 409)
    return validate_metadata({'schema': SCHEMA, 'module_id': view.module_id,
        'module_revision': view.module_revision, 'source_id': view.source_id,
        'source_sha256': view.source_sha256, 'question_id': help_view['question']['id'],
        'question_revision': help_view['question']['revision'], 'event_id': help_view['event_id'],
        'course_id': view.course_id, 'topic_id': view.topic_id,
        'assistance_level': help_view['assistance_level'], 'evidence_fingerprint': view.fingerprint,
        'reviewed_at': reviewed_at})


def receipt_id(metadata):
    return PREFIX + sha256(_json(validate_metadata(metadata)).encode()).hexdigest()


def _safe_path(path):
    path = Path(path).absolute()
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)),
            'Canonical Tutor storage is unavailable.', 503)
    return path


def validate_owner_connection(connection, evidence_path):
    """Names and matching IDs never establish ownership of a different file."""
    require(isinstance(connection, sqlite3.Connection), 'Explicit canonical Tutor connection required.', 503)
    expected = _safe_path(evidence_path)
    databases = connection.execute('PRAGMA database_list').fetchall()
    require(len(databases) == 1 and databases[0][1] == 'main' and databases[0][2],
            'Only the canonical main Tutor database is permitted.', 503)
    actual = _safe_path(databases[0][2])
    require(actual == expected and actual.samefile(expected), 'Tutor and evidence owners differ.', 503)


class _ReceiptRepository(SQLiteTutorRepository):
    """Existing owner insert with exact-primary-key retry and policy in its transaction."""
    def __init__(self, connection, evidence_path, mapping):
        validate_owner_connection(connection, evidence_path)
        super().__init__(connection)
        self.evidence_path = evidence_path
        self.mapping = mapping

    def create_session(self, **values):
        from .academic_evidence_service import AcademicEvidenceService
        with transaction(self.connection, immediate=True):
            validate_owner_connection(self.connection, self.evidence_path)
            validate_mapping(self.mapping, AcademicEvidenceService._catalogue(self.connection))
            metadata = validate_metadata(json.loads(values['metadata_json']))
            require(metadata['course_id'] == values['course_id'] == self.mapping['course_id'] and
                    metadata['topic_id'] == values['topic_id'] == self.mapping['topic_id'] and
                    values['session_id'] == receipt_id(metadata), 'Receipt owner context changed.', 409)
            require(_clock(values['created_at']) >= _clock(metadata['reviewed_at']),
                    'Receipt cannot precede the reviewed help.', 409)
            old = self.connection.execute('SELECT course_id,topic_id,assessment_id,resource_id,mode,source_policy,status,title,metadata_json,created_at,updated_at,completed_at FROM tutor_sessions WHERE id=?',
                    (values['session_id'],)).fetchone()
            if old is not None:
                expected = (values['course_id'], values['topic_id'], None, None,
                    values['mode'], values['source_policy'], 'active', values['title'], values['metadata_json'])
                require(tuple(old[:9]) == expected and old[9] == old[10] and old[11] is None and
                        _clock(old[9]) >= _clock(metadata['reviewed_at']),
                        'Receipt identity conflicts with existing Tutor data.', 409)
            else:
                self.connection.execute("INSERT INTO tutor_sessions(id,course_id,topic_id,assessment_id,resource_id,mode,source_policy,status,title,metadata_json,created_at,updated_at,completed_at) VALUES (?,?,?,?,?,?,?,'active',?,?,?,?,NULL)",
                    (values['session_id'], values['course_id'], values['topic_id'], None, None,
                     values['mode'], values['source_policy'], values['title'], values['metadata_json'],
                     values['created_at'], values['created_at']))
        return self.get_session(values['session_id'])


def save_session_metadata(owner, academic, view, preview, help_view, *, reviewed_at):
    require(isinstance(owner, TutorSessionService) and isinstance(owner.repository, SQLiteTutorRepository),
            'Canonical TutorSessionService owner required.', 503)
    # Revalidate the stateless consumer even for a non-HTTP caller.
    help_view = consume(preview, view, event_id=help_view['event_id'],
        question_id=help_view['question']['id'], level=help_view['assistance_level'], explicit_action=True)
    metadata = metadata_for_help(view, help_view, reviewed_at)
    record = next((r for r in view.records if r.identifier == metadata['event_id']), None)
    require(record is not None and record.occurred_at is not None and
            _clock(view.as_of) >= _clock(metadata['reviewed_at']) >= _clock(record.occurred_at),
            'Help review cannot precede the exact practice event.', 409)
    repository = _ReceiptRepository(owner.repository.connection, academic.path, preview['mapping'])
    sessions = TutorSessionService(repository, now=owner._now, id_factory=lambda _: receipt_id(metadata))
    return sessions.create_session(TutorSessionSpec(mode='guidance', source_policy='source_only',
        course_id=view.course_id, topic_id=view.topic_id, title='Reviewed offline learning help', metadata=metadata))


@contextmanager
def default_owner(academic, web_owner):
    from .academic_agent_web_service import _open_database
    expected = _safe_path(academic.path)
    require(_safe_path(web_owner.database_path) == expected, 'Tutor and evidence owners differ.', 503)
    connection = _open_database(web_owner.database_path, writable=True)
    try:
        validate_owner_connection(connection, expected)
        yield TutorSessionService(SQLiteTutorRepository(connection), now=precise_utc_now)
    finally:
        connection.close()


def project_session_metadata_snapshot(academic, view):
    """A bounded sidecar: never changes evidence fingerprint or attempt attribution."""
    result = {'schema': SCHEMA, 'available': False, 'sessions': [], 'scan_limit': SCAN_LIMIT,
              'assistance': 'unknown', 'mastery': 'unknown', 'status': 'unavailable'}
    try:
        with academic._connection() as connection:
            SQLiteTutorRepository(connection).validate_schema()
            rows = connection.execute('SELECT id,length(CAST(metadata_json AS BLOB)) FROM tutor_sessions WHERE id GLOB ? ORDER BY created_at DESC,id LIMIT ?',
                    (PREFIX+'*', SCAN_LIMIT+1)).fetchall()
            require(len(rows) <= SCAN_LIMIT and all(type(r[1]) is int and r[1] <= MAX_METADATA_BYTES for r in rows)
                    and sum(r[1] for r in rows) <= MAX_HISTORY_BYTES, 'Tutor receipt inventory exceeds its bound.', 503)
            sessions = []
            for identity, _ in rows:
                row = connection.execute('SELECT metadata_json,course_id,topic_id,mode,source_policy,status,assessment_id,resource_id,created_at,updated_at,completed_at FROM tutor_sessions WHERE id=?', (identity,)).fetchone()
                metadata = validate_metadata(json.loads(row[0]))
                require(identity == receipt_id(metadata) and tuple(row[1:8]) ==
                    (metadata['course_id'], metadata['topic_id'], 'guidance', 'source_only', 'active', None, None)
                    and row[8] == row[9] and row[10] is None and
                    _clock(metadata['reviewed_at']) <= _clock(row[8]) <= _clock(view.as_of),
                    'Unverified Tutor receipt.', 409)
                if any(metadata[k] != value for k, value in (
                    ('module_id', view.module_id), ('module_revision', view.module_revision),
                    ('course_id', view.course_id), ('topic_id', view.topic_id),
                    ('source_id', view.source_id), ('source_sha256', view.source_sha256))):
                    continue
                record = next((r for r in view.records if r.identifier == metadata['event_id'] and
                               r.kind == 'learning_practice'), None)
                require(record is not None and record.qualification == 'study_signal' and
                    record.outcome == 'incorrect' and record.question_id == metadata['question_id'] and
                    record.question_revision == metadata['question_revision'] and
                    record.module_revision == metadata['module_revision'] and
                    record.course_id == metadata['course_id'] and record.topic_id == metadata['topic_id'] and
                    record.occurred_at is not None and _clock(record.occurred_at) <= _clock(metadata['reviewed_at']),
                    'Saved help no longer has an exact eligible practice event.', 409)
                sources = [r for r in record.source_refs if r.kind == 'learning_source']
                questions = [r for r in record.source_refs if r.kind == 'learning_question']
                events = [r for r in record.source_refs if r.kind == 'learning_event']
                require(sources and all(r.identifier == metadata['source_id'] and
                    r.sha256 == metadata['source_sha256'] and r.revision == metadata['module_revision'] and
                    type(r.page) is int and r.page > 0 for r in sources) and
                    len({r.page for r in sources}) == len(sources) and
                    len(questions) == 1 and questions[0].identifier == metadata['question_id'] and
                    questions[0].revision == metadata['question_revision'] and
                    len(events) == 1 and 'learning_attempt:'+events[0].identifier == metadata['event_id'],
                    'Saved help source, page or question association changed.', 409)
                sessions.append({'session_id': identity, **metadata, 'saved_at': row[8],
                    'status': 'current' if metadata['evidence_fingerprint'] == view.fingerprint else 'stale',
                    'attempt_assistance': 'unknown', 'independence': 'unknown', 'mastery': 'unknown'})
        return {**result, 'available': True, 'sessions': sessions, 'status': 'available'}
    except (PackageError, TutorRepositoryError, sqlite3.Error, OSError, ValueError, TypeError, RecursionError):
        return result
