"""Explicit metadata-only Tutor receipts use a disposable canonical owner."""
from contextlib import closing, contextmanager
from datetime import timedelta
import json
import re
import shutil
import sqlite3

import pytest

from tests.test_academic_evidence_v23 import owners, NOW, event, inventory, service
from personal_learning_assistant.services.learning_tutor_session_v24 import (
    METADATA_FIELDS, PREFIX, project_session_metadata_snapshot, validate_owner_connection,
)
from personal_learning_assistant.learning_studio.validation import PackageError
from personal_learning_assistant.services.tutor_session_service import TutorSessionService
from personal_learning_assistant.repositories.sqlite.tutor_repository import SQLiteTutorRepository

BASE = '/academic-evidence/learning/synthetic/1/tutor-session'
QUERY = '?event_id=learning_attempt%3Apractice-1&question_id=q1&level=hint'


def app(owners, **extra):
    from personal_learning_assistant.ui.web import create_app
    from personal_learning_assistant.ui.web.learning_tutor_v24 import register_learning_tutor_v24
    @contextmanager
    def tutor_owner():
        with closing(sqlite3.connect(owners[0], isolation_level=None)) as connection:
            yield TutorSessionService(SQLiteTutorRepository(connection), now=lambda: NOW.isoformat())
    result = create_app({'TESTING': True, 'ACADEMIC_EVIDENCE_SERVICE_FACTORY': lambda: service(owners),
        'LEARNING_STUDIO_SERVICE_FACTORY': lambda: owners[1],
        'LEARNING_TUTOR_V24_OWNER_FACTORY': tutor_owner, **extra})
    if 'learning_tutor_v24' not in result.blueprints:
        register_learning_tutor_v24(result)
    return result


def token(response):
    assert response.status_code == 200, response.get_data(as_text=True)
    found = re.search(r'name="receipt_token" value="([^"]+)"', response.get_data(as_text=True))
    assert found is not None, response.get_data(as_text=True)
    return found[1]


def save(client, value, **kwargs):
    return client.post(BASE, data={'receipt_token': value, 'confirm_save': 'yes'}, **kwargs)


def counts(owners):
    with closing(sqlite3.connect(owners[0])) as connection:
        return [connection.execute('SELECT count(*) FROM '+table).fetchone()[0]
                for table in ('tutor_sessions', 'tutor_turns', 'tutor_evidence_links', 'tutor_feedback', 'planner_tasks')]


def test_review_get_never_creates_owner_and_explicit_retry_is_one_minimal_receipt(owners, tmp_path):
    event(owners)
    client = app(owners).test_client()
    view = service(owners).learning('synthetic', 1)
    before = inventory(tmp_path)
    reviewed = client.get(BASE+QUERY)
    value = token(reviewed)
    assert inventory(tmp_path) == before
    assert reviewed.headers['Cache-Control'] == 'no-store'
    assert save(client, value).status_code == save(client, value).status_code == 303
    assert counts(owners) == [1, 0, 0, 0, 0]
    with closing(sqlite3.connect(owners[0])) as connection:
        metadata = json.loads(connection.execute('SELECT metadata_json FROM tutor_sessions').fetchone()[0])
    assert set(metadata) == METADATA_FIELDS and metadata['event_id'] == 'learning_attempt:practice-1'
    assert not any(key in str(metadata) for key in ('answer', 'transcript', 'provider'))
    current = service(owners).learning('synthetic', 1)
    assert current.fingerprint == view.fingerprint
    history = project_session_metadata_snapshot(service(owners), current)
    assert history['available'] and len(history['sessions']) == 1 and history['scan_limit'] == 50
    assert history['sessions'][0]['assistance_level'] == 'hint'
    assert all(r.assistance == 'unknown' for r in current.records)


def test_get_never_constructs_configured_writer(owners, tmp_path):
    event(owners)
    def forbidden():
        raise AssertionError('GET opened a writer')
    client = app(owners, LEARNING_TUTOR_V24_OWNER_FACTORY=forbidden).test_client()
    before = inventory(tmp_path)
    assert token(client.get(BASE+QUERY))
    assert inventory(tmp_path) == before


def test_browser_form_submits_to_canonical_post_without_review_query(owners):
    event(owners)
    client = app(owners).test_client()
    review = client.get(BASE+QUERY)
    action = re.search(r'<form method="post" action="([^"]+)"', review.get_data(as_text=True))
    assert action is not None and action[1] == BASE
    response = client.post(action[1], data={'receipt_token': token(review), 'confirm_save': 'yes'})
    assert response.status_code == 303 and counts(owners) == [1, 0, 0, 0, 0]


@pytest.mark.parametrize('query', ['', QUERY+'&level=hint', QUERY+'&extra=1', QUERY.replace('q1', 'wrong'),
    QUERY.replace('practice-1', 'missing'), QUERY.replace('hint', 'answer')])
def test_review_requires_exact_eligible_mistake(owners, query):
    event(owners)
    assert app(owners).test_client().get(BASE+query).status_code in (400, 409)
    assert counts(owners) == [0, 0, 0, 0, 0]


def test_correct_attempt_is_not_an_eligible_mistake(owners):
    event(owners, selection=1)
    assert app(owners).test_client().get(BASE+QUERY).status_code == 409


def test_csrf_checkbox_origin_restart_and_expiry(owners, monkeypatch):
    event(owners)
    client = app(owners).test_client()
    value = token(client.get(BASE+QUERY))
    assert client.post(BASE, data={'receipt_token': value}).status_code == 400
    assert save(client, value+'forged').status_code == 400
    assert save(client, value, headers={'Origin': 'https://foreign.invalid'}).status_code == 403
    assert save(client, value, headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403
    assert save(app(owners).test_client(), value).status_code == 400
    from itsdangerous.timed import TimestampSigner
    original = TimestampSigner.get_timestamp
    monkeypatch.setattr(TimestampSigner, 'get_timestamp', lambda self: original(self)+901)
    assert save(client, value).status_code == 400
    assert counts(owners) == [0, 0, 0, 0, 0]


def test_new_attempt_invalidates_approved_context(owners):
    event(owners)
    client = app(owners).test_client()
    value = token(client.get(BASE+QUERY))
    event(owners, 'practice-2')
    assert save(client, value).status_code == 409
    assert counts(owners)[0] == 0


@pytest.mark.parametrize('flag', ['ACADEMIC_EVIDENCE_ENABLED', 'LEARNING_TUTOR_V24_ENABLED'])
def test_disabled_feature_does_not_read_owner(owners, flag):
    def forbidden():
        raise AssertionError('Disabled feature read storage')
    client = app(owners, **{flag: False, 'ACADEMIC_EVIDENCE_SERVICE_FACTORY': forbidden}).test_client()
    assert client.get(BASE+QUERY).status_code == 404
    assert save(client, 'irrelevant').status_code == 404


def test_configured_owner_with_colliding_course_ids_in_foreign_database_is_rejected(owners, tmp_path):
    event(owners)
    foreign = tmp_path/'foreign.db'
    shutil.copyfile(owners[0], foreign)
    @contextmanager
    def other_owner():
        with closing(sqlite3.connect(foreign, isolation_level=None)) as connection:
            yield TutorSessionService(SQLiteTutorRepository(connection), now=lambda: NOW.isoformat())
    client = app(owners, LEARNING_TUTOR_V24_OWNER_FACTORY=other_owner).test_client()
    value = token(client.get(BASE+QUERY))
    assert save(client, value).status_code == 503
    with closing(sqlite3.connect(foreign)) as connection:
        assert connection.execute('SELECT count(*) FROM tutor_sessions').fetchone()[0] == 0
    assert counts(owners)[0] == 0


def test_owner_connection_rejects_memory_attached_and_symlink(owners, tmp_path):
    with closing(sqlite3.connect(':memory:')) as connection:
        with pytest.raises(PackageError):
            validate_owner_connection(connection, owners[0])
    with closing(sqlite3.connect(owners[0])) as connection:
        connection.execute("ATTACH DATABASE ':memory:' AS other")
        with pytest.raises(PackageError):
            validate_owner_connection(connection, owners[0])
    linked = tmp_path/'linked.db'
    linked.symlink_to(owners[0])
    with closing(sqlite3.connect(owners[0])) as connection:
        with pytest.raises(PackageError):
            validate_owner_connection(connection, linked)


def test_mapping_is_validated_again_inside_owner_transaction(owners):
    event(owners)
    @contextmanager
    def changed_owner():
        with closing(sqlite3.connect(owners[0], isolation_level=None)) as connection:
            connection.execute("UPDATE topics SET name='Changed during owner acquisition' WHERE id='topic-lu'")
            yield TutorSessionService(SQLiteTutorRepository(connection), now=lambda: NOW.isoformat())
    client = app(owners, LEARNING_TUTOR_V24_OWNER_FACTORY=changed_owner).test_client()
    value = token(client.get(BASE+QUERY))
    assert save(client, value).status_code in (400, 409)
    assert counts(owners)[0] == 0


def test_default_path_mismatch_and_missing_tutor_schema_disable_review_save(owners):
    event(owners)
    client = app(owners, LEARNING_TUTOR_V24_OWNER_FACTORY=None).test_client()
    reviewed = client.get(BASE+QUERY)
    assert reviewed.status_code == 200 and b'name="receipt_token"' not in reviewed.data
    with closing(sqlite3.connect(owners[0])) as connection, connection:
        connection.execute('DROP TABLE tutor_feedback')
    assert not project_session_metadata_snapshot(service(owners), service(owners).learning('synthetic', 1))['available']
    assert b'name="receipt_token"' not in client.get(BASE+QUERY).data


def test_history_bounds_metadata_bytes_before_json_parse(owners, monkeypatch):
    event(owners)
    client = app(owners).test_client()
    value = token(client.get(BASE+QUERY))
    assert save(client, value).status_code == 303
    with closing(sqlite3.connect(owners[0])) as connection, connection:
        connection.execute('UPDATE tutor_sessions SET metadata_json=?', ('['*9000,))
    view = service(owners).learning('synthetic', 1)
    from personal_learning_assistant.services import learning_tutor_session_v24 as module
    def forbidden(*args, **kwargs):
        raise AssertionError('Oversized metadata reached JSON parser')
    monkeypatch.setattr(module.json, 'loads', forbidden)
    history = project_session_metadata_snapshot(service(owners), view)
    assert not history['available'] and history['sessions'] == []


@pytest.mark.parametrize('field,value', [('event_id', 'learning_attempt:nonexistent'),
    ('question_id', 'foreign-question'), ('question_revision', 2),
    ('reviewed_at', '2026-10-21T09:59:59+00:00')])
def test_recomputed_receipt_hash_does_not_authorize_fabricated_practice_context(owners, field, value):
    from personal_learning_assistant.services.learning_tutor_session_v24 import receipt_id
    event(owners)
    client = app(owners).test_client()
    assert save(client, token(client.get(BASE+QUERY))).status_code == 303
    with closing(sqlite3.connect(owners[0])) as connection, connection:
        metadata = json.loads(connection.execute('SELECT metadata_json FROM tutor_sessions').fetchone()[0])
        metadata[field] = value
        connection.execute('UPDATE tutor_sessions SET id=?,metadata_json=?',
            (receipt_id(metadata), json.dumps(metadata, sort_keys=True, separators=(',', ':'))))
    history = project_session_metadata_snapshot(service(owners), service(owners).learning('synthetic', 1))
    assert not history['available'] and history['sessions'] == []


def test_receipt_scan_limit_is_enforced_before_parsing(owners, monkeypatch):
    event(owners)
    client = app(owners).test_client()
    assert save(client, token(client.get(BASE+QUERY))).status_code == 303
    with closing(sqlite3.connect(owners[0])) as connection, connection:
        for index in range(50):
            connection.execute("INSERT INTO tutor_sessions SELECT ?,course_id,topic_id,assessment_id,resource_id,mode,source_policy,status,title,metadata_json,created_at,updated_at,completed_at FROM tutor_sessions LIMIT 1", (PREFIX+str(index),))
    view = service(owners).learning('synthetic', 1)
    from personal_learning_assistant.services import learning_tutor_session_v24 as module
    def forbidden(*args, **kwargs):
        raise AssertionError('Over-limit receipt inventory reached JSON parser')
    monkeypatch.setattr(module.json, 'loads', forbidden)
    history = project_session_metadata_snapshot(service(owners), view)
    assert not history['available'] and history['sessions'] == []


def test_retry_conflicting_existing_primary_key_does_not_overwrite_owner_data(owners):
    event(owners)
    client = app(owners).test_client()
    value = token(client.get(BASE+QUERY))
    assert save(client, value).status_code == 303
    with closing(sqlite3.connect(owners[0])) as connection, connection:
        connection.execute("UPDATE tutor_sessions SET title='Another existing session'")
    assert save(client, value).status_code == 409
    with closing(sqlite3.connect(owners[0])) as connection:
        assert connection.execute('SELECT title FROM tutor_sessions').fetchone()[0] == 'Another existing session'
    assert counts(owners) == [1, 0, 0, 0, 0]


def test_default_owner_retains_subsecond_utc_ordering(owners, monkeypatch):
    from personal_learning_assistant.services.academic_agent_web_service import AcademicAgentWebService
    from personal_learning_assistant.services import learning_tutor_session_v24 as module
    event(owners)
    stamp = NOW + timedelta(microseconds=123456)
    evidence = service(owners)
    evidence.now = lambda: stamp
    monkeypatch.setattr(module, 'precise_utc_now', lambda: (stamp+timedelta(microseconds=1)).isoformat())
    client = app(owners, LEARNING_TUTOR_V24_OWNER_FACTORY=None,
        ACADEMIC_EVIDENCE_SERVICE_FACTORY=lambda: evidence,
        ACADEMIC_AGENT_WEB_SERVICE_FACTORY=lambda: AcademicAgentWebService(database_path=owners[0])).test_client()
    value = token(client.get(BASE+QUERY))
    assert save(client, value).status_code == 303
    with closing(sqlite3.connect(owners[0])) as connection:
        saved = connection.execute('SELECT created_at FROM tutor_sessions').fetchone()[0]
    assert saved.endswith('123457+00:00')
