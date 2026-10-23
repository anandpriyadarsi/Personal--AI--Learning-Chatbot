"""Mode navigation and closed-book practice against disposable production SQLite."""
import re
import sqlite3
from uuid import uuid4

import pytest

from test_assessment_production_integration import _production


def start(client, aid, mode):
    return client.post(f"/assessments/tests/{aid}/start", data={
        "confirmed": "1", "assessment_mode": mode,
        "self_review_acknowledged": "1",
    })


def command(service, sid, action, **payload):
    return service.command(sid, action, {
        "request_id": uuid4().hex,
        "expected_revision": service.state(sid)["revision"], **payload,
    })


def test_home_two_primary_mode_cards_precede_secondary_actions(tmp_path):
    app, _, _, _, _ = _production(tmp_path)
    html = app.test_client().get('/assessments').text
    assert html.count('class="assessment-mode-card"') == 2
    assert 'CBT Based Test' in html and 'Handwritten Test' in html
    assert 'assessment_mode=cbt' in html and 'assessment_mode=handwritten' in html
    assert html.index('Open Handwritten Tests') < html.index('Recent Tests')
    assert 'Pause/Resume and handwritten' not in html
    assert 'Continue Paused Tests' not in html


@pytest.mark.parametrize('mode', ['cbt', 'handwritten'])
def test_mode_navigation_is_read_only_and_preflight_has_one_start(tmp_path, mode):
    app, path, aid, _, _ = _production(tmp_path, paper=True)
    client = app.test_client()
    library = client.get('/assessments/tests?assessment_mode='+mode)
    assert library.status_code == 200
    assert f'assessment_mode={mode}' in library.text
    page = client.get(f'/assessments/tests/{aid}?assessment_mode={mode}')
    assert page.status_code == 200
    assert page.text.count('action="/assessments/tests/'+aid+'/start"') == 1
    assert ('Start CBT Test' if mode == 'cbt' else 'Start Handwritten Test') in page.text
    assert 'Start with Pause/Resume' not in page.text
    assert 'value="'+mode+'"' in page.text
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM assessment_test_sessions').fetchone()[0] == 0


@pytest.mark.parametrize('mode', ['invalid', 'paper_subjective', '//evil.example'])
def test_invalid_mode_rejected_without_creating_attempt(tmp_path, mode):
    app, path, aid, _, _ = _production(tmp_path)
    client = app.test_client()
    assert client.get('/assessments/tests',query_string={'assessment_mode':mode}).status_code == 400
    assert client.get(f'/assessments/tests/{aid}',query_string={'assessment_mode':mode}).status_code == 400
    assert start(client, aid, mode).status_code == 400
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM assessment_test_sessions').fetchone()[0] == 0


def test_unsuitable_paper_explained_and_rejected_before_session_created(tmp_path):
    app, path, aid, _, _ = _production(tmp_path)
    client = app.test_client()
    library = client.get('/assessments/tests?assessment_mode=handwritten')
    assert 'authored subjective solutions and marking rubrics' in library.text
    page = client.get(f'/assessments/tests/{aid}?assessment_mode=handwritten')
    assert 'Start Handwritten Test' not in page.text
    assert 'authored subjective solutions and marking rubrics' in page.text
    assert start(client, aid, 'handwritten').status_code in (400,422)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM assessment_test_sessions').fetchone()[0] == 0


def test_personal_cbt_defaults_to_pausable_but_exam_retains_fixed_clock(tmp_path):
    app, path, aid, ext, _ = _production(tmp_path)
    client = app.test_client()
    result = start(client, aid, 'cbt')
    assert result.status_code == 303
    sid = result.location.rsplit('/',1)[1]
    assert ext().state(sid)['pause_allowed'] is True
    with sqlite3.connect(path) as db:
        db.execute("UPDATE assessment_runtime_specs SET mode='exam'")
        db.execute("UPDATE assessment_test_sessions SET status='submitted' WHERE id=?",(sid,))
    page = client.get(f'/assessments/tests/{aid}?assessment_mode=cbt')
    assert 'cannot be paused' in page.text
    exam = start(client,aid,'cbt')
    assert exam.status_code == 303
    exam_id = exam.location.rsplit('/',1)[1]
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM assessment_extended_execution WHERE session_id=?',(exam_id,)).fetchone()[0] == 0
    assert start(client,aid,'handwritten').status_code in (400,422)


def test_active_handwritten_reveal_denied_even_after_attempt_and_old_reveal_hidden(tmp_path):
    app, path, aid, ext, _ = _production(tmp_path,paper=True)
    result = start(app.test_client(),aid,'handwritten')
    sid = result.location.rsplit('/',1)[1]
    service = ext()
    q = service.state(sid)['questions'][0]
    command(service,sid,'attempt',question_id=q['session_question_id'],attempted=True)
    with pytest.raises(ValueError,match='Finish solving'):
        command(service,sid,'reveal',question_id=q['session_question_id'])
    assert service.authorized_guides(sid) == {}
    html = app.test_client().get('/assessments/extended/sessions/'+sid).text
    assert 'Reveal solution and marking guide' not in html
    command(service,sid,'finish_solving')
    assert command(service,sid,'reveal',question_id=q['session_question_id'])['guide']['solution']
    assert 'synthetic fixture review only' not in app.test_client().get('/assessments/extended/sessions/'+sid).text


def test_paper_navigation_pause_restart_restores_question_and_progress(tmp_path):
    app, path, aid, ext, clock = _production(tmp_path,paper=True)
    client = app.test_client()
    result = start(client,aid,'handwritten');sid = result.location.rsplit('/',1)[1]
    service = ext()
    command(service,sid,'navigate',ordinal=2)
    q = service.state(sid)['questions'][1]
    command(service,sid,'attempt',question_id=q['session_question_id'],attempted=True)
    command(service,sid,'pause')
    frozen = service.state(sid)['remaining_ms'];clock.advance(86400)
    rebuilt = ext()
    assert rebuilt.state(sid)['remaining_ms'] == frozen
    assert rebuilt.state(sid)['current_ordinal'] == 2
    assert rebuilt.state(sid)['questions'][1]['attempted'] is True
    home = client.get('/assessments').text
    assert 'Continue Paused Tests' in home and 'Handwritten Test' in home
    assert 'Paused at question 2' in home
    assert 'Resume Test' in home
    command(rebuilt,sid,'resume')
    assert rebuilt.state(sid)['current_ordinal'] == 2


def test_cbt_submit_saves_visible_response_and_reuses_private_scoring(tmp_path):
    app, path, aid, ext, _ = _production(tmp_path)
    client = app.test_client()
    sid = start(client,aid,'cbt').location.rsplit('/',1)[1]
    service = ext();state = service.state(sid);q=state['questions'][0]
    assert service.practice_results(sid) is None
    page = client.get('/assessments/extended/sessions/'+sid).text
    token = re.search('name="mutation_token" value="([^"]+)"',page).group(1)
    response = client.post('/assessments/extended/sessions/'+sid+'/save',headers={'Origin':'http://localhost'},data={
        'mutation_token':token,'request_id':uuid4().hex,'expected_revision':state['revision'],
        'question_id':q['session_question_id'],'expected_response_revision':q['response_revision'],
        'option_ids':'B','command':'submit',
    })
    assert response.status_code==303
    results = service.practice_results(sid)
    assert results['items'][0]['awarded_marks_milli']==q['max_marks_milli']
    assert results['items'][0]['outcome']=='correct'
    assert 'CBT Practice Result' in client.get(response.location).text
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM assessment_session_evaluations').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM question_attempts').fetchone()[0]==0


def test_paused_recent_test_never_uses_legacy_wall_clock_label(tmp_path):
    app, _, aid, ext, clock = _production(tmp_path)
    sid = start(app.test_client(),aid,'cbt').location.rsplit('/',1)[1]
    command(ext(),sid,'pause');clock.advance(86400)
    home = app.test_client().get('/assessments').text
    assert 'Time ended' not in home
    assert 'Test Paused' in home


def test_extended_fill_fields_save_pause_and_reload_without_key_leak(tmp_path):
    from test_assessment_runner_math_fill_ux import _make_structured_fill_question
    app,path,aid,ext,_ = _production(tmp_path)
    _make_structured_fill_question(path)
    client=app.test_client();sid=start(client,aid,'cbt').location.rsplit('/',1)[1]
    service=ext();q=service.state(sid)['questions'][0]
    command(service,sid,'navigate',ordinal=3,question_id=q['session_question_id'],
        expected_response_revision=q['response_revision'],response={},marked=False)
    url='/assessments/extended/sessions/'+sid
    page=client.get(url).text
    assert 'name="blank_1"' in page and 'name="blank_3"' in page
    assert '2,(3,-2)' not in page
    token=re.search('name="mutation_token" value="([^"]+)"',page).group(1)
    state=service.state(sid);q=state['questions'][2]
    result=client.post(url+'/save',headers={'Origin':'http://localhost'},data={
        'mutation_token':token,'request_id':uuid4().hex,'expected_revision':state['revision'],
        'question_id':q['session_question_id'],'expected_response_revision':q['response_revision'],
        'command':'pause','blank_1':'2','blank_2':'3','blank_3':'-2',
    })
    assert result.status_code==303
    assert service.state(sid)['status']=='paused'
    assert service.state(sid)['questions'][2]['response']['parts']==['2','3','-2']
    assert 'name="blank_3" value="-2"' in client.get(url).text
    stale=client.post(url+'/save',headers={'Origin':'http://localhost'},data={
        'mutation_token':token,'request_id':uuid4().hex,'expected_revision':state['revision'],
        'question_id':q['session_question_id'],'expected_response_revision':q['response_revision'],
        'command':'save','blank_1':'7','blank_2':'8','blank_3':'-5',
    })
    assert stale.status_code==409
    assert 'name="blank_1" value="7"' in stale.text
    assert 'name="blank_3" value="-5"' in stale.text
    assert service.state(sid)['questions'][2]['response']['parts']==['2','3','-2']


def test_native_save_next_replays_same_receipt_after_lost_acknowledgement(tmp_path):
    app,_,aid,ext,_=_production(tmp_path)
    client=app.test_client();sid=start(client,aid,'cbt').location.rsplit('/',1)[1]
    url='/assessments/extended/sessions/'+sid
    page=client.get(url).text;state=ext().state(sid);q=state['questions'][0]
    payload={'mutation_token':re.search('name="mutation_token" value="([^"]+)"',page).group(1),
        'request_id':uuid4().hex,'expected_revision':state['revision'],
        'question_id':q['session_question_id'],'expected_response_revision':q['response_revision'],
        'option_ids':'B','command':'next','ordinal':'1'}
    first=client.post(url+'/save',data=payload,headers={'Origin':'http://localhost'})
    assert first.status_code==303
    revision=ext().state(sid)['revision']
    replay=client.post(url+'/save',data=payload,headers={'Origin':'http://localhost'})
    assert replay.status_code==303
    assert ext().state(sid)['current_ordinal']==2
    assert ext().state(sid)['revision']==revision


def test_extended_cbt_preserves_uc100n_tools_with_active_context_policy(tmp_path):
    from types import SimpleNamespace
    app,path,aid,ext,_=_production(tmp_path)
    with sqlite3.connect(path) as db:db.execute("UPDATE courses SET code='UC100N'")
    calls=[]
    class Provider:
        def complete(self,request):
            calls.append(request)
            return SimpleNamespace(content='Use a Boolean mask, then try it yourself.')
    app.config['CODING_HELPER_PROVIDER_FACTORY']=Provider
    client=app.test_client();sid=start(client,aid,'cbt').location.rsplit('/',1)[1]
    html=client.get('/assessments/extended/sessions/'+sid).text
    assert 'Coding Helper' in html and 'Open Google Colab' in html
    q=ext().state(sid)['questions'][0]
    url=f'/assessments/sessions/{sid}/questions/{q["session_question_id"]}/coding-helper'
    assert client.post(url,json={'action':'concept','topic':'Pandas'}).status_code==200
    assert len(calls)==1 and 'SECRET' not in str(calls[0])
    command(ext(),sid,'pause')
    assert client.post(url,json={'action':'concept','topic':'Pandas'}).status_code in (400,409)
    assert len(calls)==1

