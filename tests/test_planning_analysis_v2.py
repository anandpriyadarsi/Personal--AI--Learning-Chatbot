from datetime import datetime, timezone
import hashlib
import sqlite3
import pytest
from tests.test_assessment_studio_phase_e import _database as _seed_database

NOW = datetime(2026, 9, 28, 10, tzinfo=timezone.utc)

def _database(tmp_path):
    path = _seed_database(tmp_path)
    con = sqlite3.connect(path)
    con.execute('PRAGMA journal_mode=DELETE')
    con.close()
    return path

def service(path):
    from personal_learning_assistant.services.academic_overview_service import AcademicOverviewService
    return AcademicOverviewService(path, now=lambda: NOW, local_timezone='Asia/Kolkata')

def inventory(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}

def test_missing_database_stays_missing_and_unknown(tmp_path):
    before = inventory(tmp_path)
    view = service(tmp_path/'missing.db').overview()
    assert not view['available']
    assert view['effort']['actual_minutes'] is None
    assert view['summary']['evaluated_sessions'] is None
    assert inventory(tmp_path) == before

def test_evaluated_denominators_and_unknown_independence(tmp_path):
    path = _database(tmp_path)
    before = inventory(tmp_path)
    view = service(path).overview()
    rows = {r['id']:r for r in view['assessments']}
    assert rows['s1']['earned'] == 3 and rows['s1']['max_marks'] == 4
    assert rows['s2']['earned'] == .5 and rows['s2']['max_marks'] == 4
    assert rows['s3']['category'] == 'pending'
    assert rows['s3']['earned'] is None
    assert all(r['independence'] == 'unknown' for r in rows.values())
    assert 'answer_key' not in str(view) and 'solution_text' not in str(view)
    assert inventory(tmp_path) == before

def test_self_reported_never_mixed_with_evaluated(tmp_path):
    path = _database(tmp_path)
    with sqlite3.connect(path) as c:
        c.execute("UPDATE assessment_response_evaluations SET evaluator_type='user' WHERE id='ev-sq1'")
    view = service(path).overview(evidence='self_reported')
    assert [r['id'] for r in view['assessments']] == ['s1']
    assert view['assessments'][0]['category'] == 'self_reported'

def test_future_evaluation_and_invalid_filters(tmp_path):
    path = _database(tmp_path)
    with sqlite3.connect(path) as c:
        c.execute("UPDATE assessment_session_evaluations SET updated_at='2027-01-01T00:00:00Z' WHERE session_id='s1'")
    assert 's1' not in [r['id'] for r in service(path).overview()['assessments']]
    for kwargs in ({'days':999},{'evidence':'mastered'},{'course':"' OR 1=1 --"}):
        with pytest.raises(ValueError): service(path).overview(**kwargs)

def test_actual_effort_not_recorded_is_not_zero_and_drafts_excluded(tmp_path):
    path = _database(tmp_path)
    with sqlite3.connect(path) as c:
        for aid, status in [('approved','approved'),('draft','draft')]:
            c.execute("INSERT INTO daily_agendas(id,agenda_date,status,generated_at,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                      (aid,'2026-09-27' if aid=='approved' else '2026-09-28',status,'x','x','x'))
            c.execute("INSERT INTO daily_agenda_items(id,agenda_id,ordinal,item_kind,title,planned_minutes,created_at,updated_at) VALUES(?,?,1,'manual','Read',30,'x','x')",(aid,aid))
    result = service(path).overview()['effort']
    assert result['planned_minutes'] == 30
    assert result['actual_minutes'] is None
    assert result['recorded_items'] == 0
    with sqlite3.connect(path) as c:
        c.execute("UPDATE daily_agenda_items SET actual_minutes=0 WHERE id='approved'")
    assert service(path).overview()['effort']['actual_minutes'] == 0

@pytest.mark.parametrize('route', ['/planning', '/analysis'])
def test_live_pages_read_only_and_validated_filters(tmp_path, monkeypatch, route):
    from personal_learning_assistant.ui.web import create_app
    from personal_learning_assistant.services.operational_planner_web_service import build_operational_planner_web_service
    path = _database(tmp_path)
    app = create_app({'TESTING':True,
        'ACADEMIC_OVERVIEW_SERVICE_FACTORY': lambda: service(path),
        'OPERATIONAL_PLANNER_WEB_SERVICE_FACTORY': lambda: build_operational_planner_web_service(path)})
    before = inventory(tmp_path)
    client = app.test_client()
    response = client.get(route+'?course=MA103N&days=7')
    assert response.status_code == 200
    assert b'MA103N' in response.data
    assert inventory(tmp_path) == before
    assert client.get(route+'?days=999').status_code == 400
    assert client.get(route+"?course=%27%20OR%201=1").status_code == 400


def test_missing_wal_sidecars_degrades_without_creating_them(tmp_path):
    path = _seed_database(tmp_path)
    before = inventory(tmp_path)
    result = service(path).overview()
    assert not result['available']
    assert inventory(tmp_path) == before


def test_topic_observations_never_claim_recovery_authority(tmp_path):
    path = _database(tmp_path)
    result = service(path).overview()
    assert result['topics']
    for row in result['topics']:
        assert row['mapping_status'] == 'unreviewed'
        assert row['question_count'] > 0
        assert 'manual review' in row['reason'].lower()
        assert row['url'].startswith('/assessments/sessions/')
    with sqlite3.connect(path) as c:
        c.execute("UPDATE topics SET deleted_at='2026-09-28T00:00:00Z'")
    assert all(row['mapping_status']=='unavailable' for row in service(path).overview()['topics'])


def test_partial_self_score_is_unknown(tmp_path):
    path = _database(tmp_path)
    with sqlite3.connect(path) as c:
        c.execute("UPDATE assessment_response_evaluations SET evaluator_type='user' WHERE id='ev-sq1'")
        c.execute("UPDATE assessment_response_evaluations SET awarded_marks_milli=NULL,status='awaiting_review' WHERE id='ev-sq2'")
    row = next(r for r in service(path).overview()['assessments'] if r['id']=='s1')
    assert row['category']=='self_reported'
    assert row['earned'] is None


def test_future_response_never_used_as_final_performance(tmp_path):
    path = _database(tmp_path)
    with sqlite3.connect(path) as c:
        c.execute("UPDATE assessment_response_evaluations SET updated_at='2027-01-01T00:00:00Z' WHERE id='ev-sq1'")
    row = next(r for r in service(path).overview()['assessments'] if r['id']=='s1')
    assert row['category']=='pending' and row['earned'] is None


def test_live_wal_inventory_remains_identical(tmp_path):
    path = _database(tmp_path)
    con = sqlite3.connect(path)
    try:
        con.execute('PRAGMA journal_mode=WAL')
        con.execute("UPDATE courses SET name='Live update'")
        con.commit()
        before = inventory(tmp_path)
        view = service(path).overview()
        assert inventory(tmp_path)==before
        assert not view['available']  # Strict physical read gate, not a stale immutable read.
    finally:
        con.close()


def _submitted_paper(tmp_path, *, delay_days=0):
    from tests.test_assessment_production_integration import _production
    from tests.test_assessment_pause_paper import command
    app, path, aid, factory, clock = _production(tmp_path, paper=True)
    response = app.test_client().post('/assessments/tests/'+aid+'/start', data={
        'confirmed':'1', 'extended_kind':'paper_subjective', 'self_review_acknowledged':'1'})
    sid = response.location.rsplit('/', 1)[1]
    studio = factory()
    command(studio, sid, 'finish_solving')
    clock.advance(delay_days*86400)
    for q in studio.state(sid)['questions']:
        command(studio, sid, 'reveal', question_id=q['session_question_id'])
        command(studio, sid, 'self_save', question_id=q['session_question_id'], marks='.5', reason='PRIVATE REASON')
    command(studio, sid, 'self_submit', confirmed=True)
    with sqlite3.connect(path) as con:
        con.execute('PRAGMA journal_mode=DELETE')
    return app, path, sid, studio, clock


def test_paper_projection_uses_submitted_marks_date_and_working_link(tmp_path):
    from personal_learning_assistant.services.academic_overview_service import AcademicOverviewService
    app, path, sid, studio, clock = _submitted_paper(tmp_path, delay_days=35)
    before = inventory(tmp_path)
    view = AcademicOverviewService(path, now=clock).overview(days=7)
    row = next(r for r in view['assessments'] if r['id']==sid)
    assert row['category']=='self_reported' and row['earned']==row['question_count']*.5
    assert row['review_revision']==1 and row['date'].startswith(clock().date().isoformat())
    assert row['source_refs'] == [sid, sid+':self-review:1']
    assert view['summary']['evaluated_sessions']==0 and view['topics']==[]
    assert 'PRIVATE REASON' not in str(view) and 'rubric_text' not in str(view)
    assert inventory(tmp_path)==before
    assert row['url']=='/assessments/sessions/'+sid
    response = app.test_client().get(row['url'])
    assert response.status_code==303
    assert response.location=='/assessments/extended/sessions/'+sid


def test_paper_projection_future_and_latest_draft(tmp_path):
    from datetime import timedelta
    from tests.test_assessment_pause_paper import command
    from personal_learning_assistant.services.academic_overview_service import AcademicOverviewService
    _, path, sid, studio, clock = _submitted_paper(tmp_path)
    future = AcademicOverviewService(path, now=lambda: clock()-timedelta(seconds=1)).overview()
    assert not any(r['category']=='self_reported' for r in future['assessments'])
    command(studio, sid, 'amend', reason='PRIVATE CORRECTION')
    with sqlite3.connect(path) as con:
        con.execute('PRAGMA journal_mode=DELETE')
    row = next(r for r in AcademicOverviewService(path, now=clock).overview()['assessments'] if r['id']==sid)
    assert row['review_revision']==1 and row['earned']==row['question_count']*.5


@pytest.mark.parametrize('mutation', ['malformed', 'oversized', 'foreign_question', 'missing_question', 'invalid_marks', 'wrong_denominator', 'wrong_package'])
def test_paper_projection_fails_closed_on_invalid_snapshot(tmp_path, mutation):
    import json
    from personal_learning_assistant.services.academic_overview_service import AcademicOverviewService
    _, path, sid, studio, clock = _submitted_paper(tmp_path)
    with sqlite3.connect(path) as con:
        # Corruption fixture only: real submitted snapshots remain immutable.
        con.execute('DROP TRIGGER assessment_extended_submitted_immutable')
        snapshot = json.loads(con.execute('SELECT snapshot_json FROM assessment_extended_self_reviews').fetchone()[0])
        if mutation=='wrong_package': snapshot['package_identity']['snapshot_sha256']='0'*64
        if mutation=='foreign_question':
            snapshot['items']['foreign'] = snapshot['items'].pop(next(iter(snapshot['items'])))
        if mutation=='missing_question': snapshot['items'].pop(next(iter(snapshot['items'])))
        if mutation=='invalid_marks': next(iter(snapshot['items'].values()))['awarded_marks_milli'] = True
        if mutation=='wrong_denominator': con.execute('UPDATE assessment_test_session_questions SET max_marks_milli=max_marks_milli+1 WHERE session_id=?',(sid,))
        raw = '{' if mutation=='malformed' else json.dumps(snapshot)
        if mutation=='oversized': raw = json.dumps(dict(snapshot, reflection='x'*262145))
        con.execute('UPDATE assessment_extended_self_reviews SET snapshot_json=?', (raw,))
    before = inventory(tmp_path)
    view = AcademicOverviewService(path, now=clock).overview()
    assert not any(r['id']==sid for r in view['assessments'])
    assert inventory(tmp_path)==before


def test_paper_projection_latest_submitted_revision_is_as_of_clock(tmp_path):
    from personal_learning_assistant.services.academic_overview_service import AcademicOverviewService
    from tests.test_assessment_pause_paper import command
    _, path, sid, studio, clock = _submitted_paper(tmp_path)
    first_time = clock()
    clock.advance(60)
    command(studio, sid, 'amend', reason='Correction')
    for q in studio.state(sid)['questions']:
        command(studio, sid, 'self_save', question_id=q['session_question_id'], marks='1')
    command(studio, sid, 'self_submit', confirmed=True)
    with sqlite3.connect(path) as con:
        con.execute('PRAGMA journal_mode=DELETE')
    old = AcademicOverviewService(path, now=lambda:first_time).overview()['assessments'][0]
    latest = AcademicOverviewService(path, now=clock).overview()['assessments'][0]
    assert old['review_revision']==1 and old['earned']==old['question_count']*.5
    assert latest['review_revision']==2 and latest['earned']==latest['question_count']
