"""Synthetic request-ledger recovery; never opens a configured personal store."""
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import subprocess
import sys

import pytest

from personal_learning_assistant.services.multimodal_schema import NATIVE_SQL
from personal_learning_assistant.services.provider_permission_service import PermissionGuard


@pytest.fixture
def ledger(tmp_path):
    database = tmp_path / 'requests.db'
    with sqlite3.connect(database) as con:
        con.executescript(NATIVE_SQL)
    guard = PermissionGuard(database, monthly_limit_micros=100)
    scope = {'document_id': 'synthetic', 'generation': 1}
    receipt = guard.grant(scope, 'fake', 'extract', max_cost_micros=30)
    guard.reserve(receipt, scope, 'fake', 'extract', 'lost-reply', 30)
    return guard, scope, receipt


def row(guard, operation='lost-reply'):
    with sqlite3.connect(guard.database) as con:
        return con.execute('SELECT * FROM mm_provider_requests WHERE id=?', (operation,)).fetchone()


def test_recovery_retains_accounting_and_replay_fence(ledger):
    guard, scope, receipt = ledger
    before = row(guard)
    assert guard.mark_unknown('lost-reply') == {'operation': 'lost-reply', 'status': 'outcome_unknown', 'changed': True}
    assert row(guard)[:-1] == before[:-1]
    assert row(guard)[-1] == 'outcome_unknown'
    assert guard.mark_unknown('lost-reply')['changed'] is False
    with pytest.raises(ValueError, match='already dispatched'):
        guard.reserve(receipt, scope, 'fake', 'extract', 'lost-reply', 30)
    guard.reserve(receipt, scope, 'fake', 'extract', 'new-operation', 30)
    guard.finish('new-operation', 'complete')
    guard.reserve(receipt, scope, 'fake', 'extract', 'another-operation', 30)
    guard.finish('another-operation', 'complete')
    with pytest.raises(ValueError, match='Monthly budget'):
        guard.reserve(receipt, scope, 'fake', 'extract', 'over-budget', 30)


def test_recovery_preserves_actual_and_rejects_terminal_missing_and_invalid(ledger):
    guard, _, _ = ledger
    with guard.connection() as con:
        con.execute("UPDATE mm_provider_requests SET actual=7 WHERE id='lost-reply'")
    guard.mark_unknown('lost-reply')
    assert row(guard)[4] == 7
    for operation in ('missing', '', None, 7):
        with pytest.raises(ValueError):
            guard.mark_unknown(operation)
    with guard.connection() as con:
        con.execute("UPDATE mm_provider_requests SET status='complete' WHERE id='lost-reply'")
    before = row(guard)
    with pytest.raises(ValueError, match='not sending'):
        guard.mark_unknown('lost-reply')
    assert row(guard) == before


def test_concurrent_recovery_only_one_transition_and_finish_cannot_overwrite(ledger):
    guard, _, _ = ledger
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: guard.mark_unknown('lost-reply'), range(2)))
    assert sorted(r['changed'] for r in results) == [False, True]
    with pytest.raises(ValueError, match='not sending'):
        guard.finish('lost-reply', 'complete', actual=0)
    assert row(guard)[3:] == (30, None, 'outcome_unknown')


def cli(database, *args):
    return subprocess.run([sys.executable, '-m', 'scripts.multimodal_requests', '--database', str(database), *args], capture_output=True, text=True, timeout=10)


def test_cli_defaults_read_only_and_mutation_requires_writers_stopped(ledger):
    guard, _, _ = ledger
    before = guard.database.read_bytes()
    result = cli(guard.database)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['dry_run'] is True and report['requests'][0]['status'] == 'sending'
    assert 'scope' not in result.stdout and 'permission_id' not in result.stdout
    for args in (('--operation', 'lost-reply', '--mark-unknown'), ('--writers-stopped', '--mark-unknown'), ('--operation', 'lost-reply', '--mark-unknown', '--writers-stopped', '--dry-run')):
        result = cli(guard.database, *args)
        assert result.returncode != 0
        assert guard.database.read_bytes() == before
    result = cli(guard.database, '--operation', 'lost-reply', '--mark-unknown', '--writers-stopped')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['changed'] is True
    result = cli(guard.database, '--operation', 'lost-reply', '--mark-unknown', '--writers-stopped')
    assert json.loads(result.stdout)['changed'] is False


def test_cli_never_creates_missing_database_or_schema(tmp_path):
    missing = tmp_path / 'missing.db'
    assert cli(missing).returncode != 0
    assert not missing.exists()
    empty = tmp_path / 'empty.db'
    with sqlite3.connect(empty):
        pass
    before = empty.read_bytes()
    assert cli(empty, '--list').returncode != 0
    assert empty.read_bytes() == before


# These probes exercise existing production publication fences as well as the
# operator recovery path. Provider answers are local synthetic data only.
from io import BytesIO
from test_multimodal_jobs import owners, image_bytes, records


@pytest.mark.parametrize('action', ['revoke', 'cancel'])
def test_inflight_revocation_or_cancel_retains_reservation_without_publication(owners, monkeypatch, action):
    from personal_learning_assistant.services.multimodal_evidence_service import MultimodalEvidenceService
    from personal_learning_assistant.tutor.vision_provider import VisionProvider
    lib, academic = owners
    for key, value in [('KEY', 'synthetic'), ('MODEL', 'fake'), ('MAX_MICROS', '20')]:
        monkeypatch.setenv('ANVAYA_MM_VISION_' + key, value)
    monkeypatch.setenv('ANVAYA_MM_MONTHLY_MICROS', '100')
    service = MultimodalEvidenceService(lib)
    document = lib.upload(BytesIO(image_bytes()), 'fenced.png')
    called = []
    def analyze(self, image):
        called.append(image)
        if action == 'cancel':
            service.cancel(document['id'])
        else:
            with lib.connection() as con:
                receipt = con.execute('SELECT permission_id FROM mm_selections WHERE document_id=?', (document['id'],)).fetchone()[0]
            PermissionGuard(lib.database).revoke(receipt)
        return {'text': 'Matrix [[1,0],[0,2]]', 'uncertain': []}
    monkeypatch.setattr(VisionProvider, 'analyze', analyze)
    preview = service.preview(document['id'], {'kind': 'image'}, method='vision')
    service.enqueue(document['id'], preview['token'])
    lib.run_pending()
    assert len(called) == 1 and not records(academic)
    with lib.connection() as con:
        request = dict(con.execute('SELECT * FROM mm_provider_requests').fetchone())
        assert con.execute('SELECT count(*) FROM mm_artifacts').fetchone()[0] == 0
    assert (request['reserved'], request['actual'], request['status']) == (20, None, 'outcome_unknown')
    assert PermissionGuard(lib.database).mark_unknown(request['id'])['changed'] is False
    lib.run_pending()
    assert len(called) == 1


def test_response_before_artifact_crash_keeps_complete_replay_fence(owners, monkeypatch):
    from personal_learning_assistant.services.multimodal_evidence_service import MultimodalEvidenceService, extract_selected
    from personal_learning_assistant.tutor.vision_provider import VisionProvider
    lib, academic = owners
    monkeypatch.setenv('ANVAYA_MM_VISION_KEY', 'synthetic')
    monkeypatch.setenv('ANVAYA_MM_VISION_MODEL', 'fake')
    monkeypatch.setenv('ANVAYA_MM_VISION_MAX_MICROS', '20')
    monkeypatch.setenv('ANVAYA_MM_MONTHLY_MICROS', '100')
    service = MultimodalEvidenceService(lib)
    document = lib.upload(BytesIO(image_bytes()), 'crash.png')
    called = []
    def analyze(self, image):
        called.append(image)
        return {'text': 'Matrix [[1,0],[0,2]]', 'uncertain': []}
    monkeypatch.setattr(VisionProvider, 'analyze', analyze)
    preview = service.preview(document['id'], {'kind': 'image'}, method='vision')
    service.enqueue(document['id'], preview['token'])
    finish = PermissionGuard.finish
    def crash_after_response(self, operation, status, actual=None):
        finish(self, operation, status, actual)
        raise SystemExit('synthetic crash after response, before artifact')
    monkeypatch.setattr(PermissionGuard, 'finish', crash_after_response)
    with pytest.raises(SystemExit, match='synthetic crash'):
        extract_selected(lib, lib.get(document['id']), lambda: False)
    assert not records(academic)
    with lib.connection() as con:
        request = dict(con.execute('SELECT * FROM mm_provider_requests').fetchone())
        assert con.execute('SELECT count(*) FROM mm_artifacts').fetchone()[0] == 0
    assert (request['reserved'], request['actual'], request['status']) == (20, None, 'complete')
    with pytest.raises(ValueError, match='not sending'):
        PermissionGuard(lib.database).mark_unknown(request['id'])
    monkeypatch.setattr(PermissionGuard, 'finish', finish)
    with pytest.raises(ValueError, match='already dispatched'):
        extract_selected(lib, lib.get(document['id']), lambda: False)
    assert len(called) == 1


def test_recovery_racing_finish_keeps_one_terminal_outcome(ledger):
    guard, _, _ = ledger
    def transition(action):
        other = PermissionGuard(guard.database, monthly_limit_micros=100)
        try:
            if action == 'recover':
                other.mark_unknown('lost-reply')
            else:
                other.finish('lost-reply', 'complete', actual=7)
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        succeeded = list(pool.map(transition, ('recover', 'finish')))
    assert sorted(succeeded) == [False, True]
    assert row(guard)[3:] in ((30, None, 'outcome_unknown'), (30, 7, 'complete'))


def test_concurrent_guards_keep_global_sending_exclusion_after_recovery(ledger):
    guard, scope, receipt = ledger
    guard.mark_unknown('lost-reply')
    def reserve(operation):
        other = PermissionGuard(guard.database, monthly_limit_micros=100)
        try:
            other.reserve(receipt, scope, 'fake', 'extract', operation, 30)
            return True
        except ValueError as error:
            assert 'already in progress' in str(error)
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        succeeded = list(pool.map(reserve, ('next-one', 'next-two')))
    assert sorted(succeeded) == [False, True]
    with sqlite3.connect(guard.database) as con:
        assert con.execute("SELECT count(*) FROM mm_provider_requests WHERE status='sending'").fetchone()[0] == 1
        assert con.execute('SELECT sum(reserved) FROM mm_provider_requests').fetchone()[0] == 60


def test_guard_recovery_never_creates_missing_owner(tmp_path):
    database = tmp_path / 'absent.db'
    with pytest.raises(ValueError, match='Existing request database required'):
        PermissionGuard(database).mark_unknown('lost-reply')
    assert not database.exists()
