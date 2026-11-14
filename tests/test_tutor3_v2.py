"""Synthetic Tutor V2 projection and progressive contract gates."""
from tests.test_tutor_ui_v3 import ui, _save_sample_user_turn
from tests.test_phase7_5_academic_agent_web import open_database, table_counts
from tests.test_tutor_coding import coding


def test_recent_context_is_bounded_read_only_and_excludes_empty(ui):
    app, service, course = ui
    empty = service.create_session(course_id=course['id'])
    for i in range(22):
        sid = service.create_session(course_id=course['id'], title=f'Study {i}')
        _save_sample_user_turn(service, sid)
    db = open_database(service.database_path)
    before = table_counts(db)
    context = service.ui_context()
    assert context['history_available']
    assert len(context['recent_sessions']) == 20
    assert empty not in [s['session_id'] for s in context['recent_sessions']]
    assert table_counts(db) == before
    db.close()


def test_session_and_error_supply_picker_scope_and_readiness(ui):
    app, service, course = ui
    sid = service.create_session(course_id=course['id'], title='My scoped session')
    _save_sample_user_turn(service, sid)
    c = app.test_client()
    for response in [c.get('/agent/sessions/'+sid), c.post('/agent/sessions/'+sid+'/ask',data={})]:
        assert 'id="tutor-sessions-panel"' in response.text
        assert 'Filter the 20 most recent conversations' in response.text
        assert 'Source Only' in response.text
        assert 'Provider status' not in response.text
        assert 'data-tutor-evidence' in response.text
    assert c.get('/agent/sessions/missing').status_code == 404


def test_history_failure_does_not_break_transcript(ui, monkeypatch):
    app, service, course = ui
    sid = service.create_session(course_id=course['id'])
    def broken():
        raise RuntimeError('private database detail')
    monkeypatch.setattr(service, 'ui_context', broken)
    response = app.test_client().get('/agent/sessions/'+sid)
    assert response.status_code == 200
    assert 'Recent conversations unavailable' in response.text
    assert 'private database detail' not in response.text


def test_saved_coding_is_fail_closed_before_javascript(coding):
    app, service, path, course, provider, retrieval, sid = coding
    html = app.test_client().get('/agent/sessions/'+sid).text
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    form = soup.select_one('#tutor-ask-form')
    assert form['data-workspace'] == 'coding'
    assert form.select_one('button[type=submit]').has_attr('disabled')
    fallback = soup.select_one('#coding-native-fallback form')
    assert fallback['action'].endswith('/workspace')
    assert fallback.select_one('[name=workspace]')['value'] == 'academic'


def test_source_only_insufficiency_and_hostile_evidence_are_honest(ui, monkeypatch):
    app, service, course = ui
    sid = service.create_session(course_id=course['id'], source_policy='source_only')
    service.ask(sid, 'Explain vector spaces from my source.')
    view = service.session_view(sid)
    assert view['turns'][-1]['support_level'] == 'insufficient'
    turn = view['turns'][-1]
    turn['evidence'] = [dict(citation_label='S1',document_id='not-real',chunk_id='test',
        source_title='<img src=x onerror=alert(1)>',source_label='Source',
        historical_exact=True,citation_url='javascript:alert(1)',locator_label='Page 1',
        relation_type='',retrieval_score=None)]
    turn['cited_labels'] = ['S1']
    monkeypatch.setattr(service, 'session_view', lambda _:view)
    html = app.test_client().get('/agent/sessions/'+sid).text
    assert 'href="javascript:' not in html
    assert '<img src=x onerror' not in html
    assert 'Source-grounded' not in html
    assert 'Support: Insufficient' in html


def test_feature_off_can_explicitly_leave_saved_coding(coding):
    app, service, path, course, provider, retrieval, sid = coding
    app.config['TUTOR_CODING_ENABLED'] = False
    c=app.test_client()
    assert 'disabled aria-label="Ask tutor"' in c.get('/agent/sessions/'+sid).text
    response=c.post('/agent/sessions/'+sid+'/workspace',data={
        'csrf_token':app.extensions['tutor_action_csrf'],'workspace':'academic'})
    assert response.status_code == 303
    assert service.session_view(sid)['metadata']['coding_workspace_v1']['workspace']=='academic'
    html=c.get(response.headers['Location']).text
    assert 'disabled aria-label="Ask tutor"' not in html
    assert not provider.requests


def test_inactive_coding_has_no_orphan_initializer(coding):
    app, service, path, course, provider, retrieval, sid = coding
    with open_database(path) as db:
        db.execute("UPDATE tutor_sessions SET status='completed' WHERE id=?",(sid,))
    html=app.test_client().get('/agent/sessions/'+sid).text
    assert 'id="coding-studio"' not in html
    assert 'id="tutor-ask-form"' not in html


def test_missing_coding_schema_can_explicitly_leave_saved_workspace(ui):
    import json
    app, service, course = ui
    # The projection's optional-schema path must never activate anything.
    app.config['ANDROID_LOCAL_RUNTIME']=False
    sid=service.create_session(course_id=course['id'])
    with open_database(service.database_path) as db:
        db.execute('UPDATE tutor_sessions SET metadata_json=? WHERE id=?',
            (json.dumps({'coding_workspace_v1':{'version':1,'workspace':'coding'}}),sid))
        before=table_counts(db)
    response=app.test_client().post('/agent/sessions/'+sid+'/workspace',data={
        'workspace':'academic','csrf_token':app.extensions['tutor_action_csrf']})
    assert response.status_code==303
    assert service.session_view(sid)['metadata']['coding_workspace_v1']['workspace']=='academic'
    with open_database(service.database_path) as db:
        assert table_counts(db)==before
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='tutor_coding_tasks'").fetchone()
