"""Behaviour contracts for the UC100N guided companion; synthetic data only."""
import io
import json
import sqlite3
from contextlib import redirect_stdout
from dataclasses import replace

import pytest
from test_assessment_coding_helper import setup, endpoint, dump
from personal_learning_assistant.services.assessment_coding_helper import ACTIONS


@pytest.mark.parametrize('action,contract', [
    ('viva', 'parameter'), ('predict', 'prediction'), ('compare', 'difference'),
    ('check', 'attempt'), ('debug', 'broadcasting'), ('operation', 'COMMON MISTAKE'),
])
def test_specialized_teaching_contracts(tmp_path, action, contract):
    client, _, provider, _, _, sid, qid = setup(tmp_path)
    result = client.post(endpoint(sid,qid),json={'action':action,'topic':'reshape','code':'a = np.arange(6).reshape(2, 3)'})
    assert result.status_code == 200
    assert contract.lower() in provider.requests[-1].messages[0]['content'].lower()
    assert 'never claim to have run code' in provider.requests[-1].messages[0]['content'].lower()


@pytest.mark.parametrize('depth', ['overview','line_by_line','operations','data_flow'])
def test_explanation_depth_is_validated_and_passed(tmp_path, depth):
    client, _, provider, _, _, sid, qid = setup(tmp_path)
    assert client.post(endpoint(sid,qid),json={'action':'explain_code','code':'x = [1, 2]','explanation_depth':depth}).status_code == 200
    assert json.loads(provider.requests[-1].messages[-1]['content'])['explanation_depth'] == depth


@pytest.mark.parametrize('payload', [
    {'action':'hint'}, {'action':'hint','topic':'x','explanation_depth':'anything'},
    {'action':'memory','topic':'x','card_id':['invalid']},
    {'action':'concept','topic':'x','context_token':123},
    {'action':'concept','topic':'x','context_token':'x'*36001},
])
def test_invalid_new_fields_and_empty_request(tmp_path, payload):
    client, _, provider, _, _, sid, qid = setup(tmp_path)
    assert client.post(endpoint(sid,qid),json=payload).status_code == 400
    assert not provider.requests


def test_catalogue_grounding_uses_exact_selected_card(tmp_path):
    client, _, provider, _, _, sid, qid = setup(tmp_path)
    from personal_learning_assistant.services.coding_operations import OPERATION_CARDS
    card = next(c for c in OPERATION_CARDS if c['what']=='Groupby')
    assert client.post(endpoint(sid,qid),json={'action':'operation','card_id':card['id'],'topic':'groupby'}).status_code == 200
    data = json.loads(provider.requests[-1].messages[-1]['content'])
    assert data['reference_cards'][0] == card
    assert len(data['reference_cards']) <= 3


@pytest.mark.parametrize('level', [1,2,3])
def test_hints_are_progressive_and_never_enable_solution(tmp_path, level):
    client, _, provider, _, _, sid, qid = setup(tmp_path)
    assert client.post(endpoint(sid,qid),json={'action':'hint','topic':'loops','hint_level':level,'full_solution':True}).status_code == 200
    data = json.loads(provider.requests[-1].messages[-1]['content'])
    assert data['hint_level'] == level and data['full_solution'] is False
    assert 'Never reveal a final answer in hint mode' in provider.requests[-1].messages[0]['content']


def test_continuation_is_bounded_signed_and_resettable_without_writes(tmp_path):
    client, _, provider, path, _, sid, qid = setup(tmp_path)
    before = dump(path)
    token = ''
    for index in range(6):
        response = client.post(endpoint(sid,qid),json={'action':'concept','message':f'follow-up {index}', 'context_token':token})
        assert response.status_code == 200
        data = json.loads(provider.requests[-1].messages[-1]['content'])
        assert len(data['previous_exchanges']) == min(index,3)
        if index:
            assert f'follow-up {index-1}' in data['previous_exchanges'][-1]['student']
        token = response.json['context_token']
        assert isinstance(token,str) and 0 < len(token) <= 36000
    assert dump(path) == before
    assert client.post(endpoint(sid,qid),json={'action':'concept','message':'new topic','context_token':''}).status_code == 200
    assert json.loads(provider.requests[-1].messages[-1]['content'])['previous_exchanges'] == []
    count = len(provider.requests)
    assert client.post(endpoint(sid,qid),json={'action':'concept','message':'forged','context_token':token+'bad'}).status_code == 409
    assert len(provider.requests) == count


@pytest.mark.parametrize('change', ['question','course','mode','include_question','full_solution'])
def test_context_cannot_cross_boundary(tmp_path, change):
    client, service, provider, path, _, sid, qid = setup(tmp_path)
    data={'action':'debug','code':'x=1', 'include_question':True, 'full_solution':True}
    first=client.post(endpoint(sid,qid),json=data)
    assert first.status_code == 200
    data['context_token']=first.json['context_token']
    if change == 'question':
        qid=service.runner_view(sid,ordinal=2)['question']['session_question_id']
    elif change in {'include_question','full_solution'}:
        data[change]=False
    else:
        with sqlite3.connect(path) as db:
            if change == 'course': db.execute("UPDATE courses SET code='MA103N'")
            if change == 'mode': db.execute("UPDATE assessment_test_sessions SET mode='exam'")
    assert client.post(endpoint(sid,qid),json=data).status_code in {403,409}
    assert len(provider.requests)==1


def test_expired_context_rejected(tmp_path, monkeypatch):
    client, _, provider, _, _, sid, qid = setup(tmp_path)
    import itsdangerous.timed
    original=itsdangerous.timed.time.time
    token=client.post(endpoint(sid,qid),json={'action':'concept','topic':'loops'}).json['context_token']
    monkeypatch.setattr(itsdangerous.timed.time,'time',lambda:original()+901)
    response=client.post(endpoint(sid,qid),json={'action':'concept','topic':'loops','context_token':token})
    assert response.status_code==409
    assert response.json['reset_context'] is True
    assert len(provider.requests)==1


def test_exam_rejects_context_and_arbitrary_card_but_accepts_generic_card(tmp_path):
    client, _, provider, _, _, sid, qid=setup(tmp_path,mode='exam',ASSESSMENT_CODING_HELPER_EXAM_POLICY='concepts')
    for extra in ({'context_token':'forged'}, {'card_id':'forged'}, {'explanation_depth':'data_flow'}):
        assert client.post(endpoint(sid,qid),json={'action':'concept','topic':'loops',**extra}).status_code == 403
    response=client.post(endpoint(sid,qid),json={'action':'memory','topic':'numpy-4'})
    assert response.status_code == 200
    assert response.json['context_token']==''
    data=json.loads(provider.requests[-1].messages[-1]['content'])
    assert data['visible_context']=={} and data['previous_exchanges']==[]


@pytest.mark.parametrize('mode,setting', [('exam','bogus'),('exam','full'),('exam',None)])
def test_unknown_exam_policy_remains_closed(tmp_path,mode,setting):
    client,_,provider,_,_,sid,qid=setup(tmp_path,mode=mode,ASSESSMENT_CODING_HELPER_EXAM_POLICY=setting)
    assert client.post(endpoint(sid,qid),json={'action':'concept','topic':'loops'}).status_code==403
    assert not provider.requests


@pytest.mark.parametrize('failure', ['timeout','empty','type'])
def test_provider_failures_preserve_data_and_hide_details(tmp_path,failure):
    client,_,provider,path,_,sid,qid=setup(tmp_path)
    from personal_learning_assistant.domain.tutor_models import TutorProviderResponse
    def complete(_):
        if failure=='timeout': raise TimeoutError('SECRET URL KEY')
        return TutorProviderResponse('' if failure=='empty' else {}, 'fixture','fixture')
    provider.complete=complete
    before=dump(path)
    result=client.post(endpoint(sid,qid),json={'action':'debug','code':'print(x)'})
    assert result.status_code==503
    assert 'SECRET' not in result.get_data(as_text=True)
    assert 'context_token' not in result.json
    assert dump(path)==before


def test_all_card_examples_compile_and_run_with_synthetic_data():
    from personal_learning_assistant.services.coding_operations import OPERATION_CARDS
    import numpy as np
    import pandas as pd
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    assert 'EDA' in {c['category'] for c in OPERATION_CARDS}
    for card in OPERATION_CARDS:
        code=compile(card['example'],card['id'],'exec')
        with redirect_stdout(io.StringIO()) as output:
            exec(code, {'np':np,'pd':pd,'plt':plt})
        plt.close('all')
        if card.get('expected_stdout') is not None:
            assert output.getvalue().strip()==card['expected_stdout'], card['what']
    assert sum('expected_stdout' in c for c in OPERATION_CARDS) >= 65


@pytest.mark.parametrize('course', ['UC100N','MA103N','CY100N','UC103N','DE100N'])
@pytest.mark.parametrize('mode', ['practice','assignment','exam'])
def test_acceptance_fixture_course_and_mode(tmp_path,course,mode,monkeypatch):
    from scripts.assessment_live_acceptance import build_fixture
    monkeypatch.delenv('ANVAYA_CODING_HELPER_ENABLED',raising=False)
    monkeypatch.delenv('ANVAYA_CODING_HELPER_EXAM_POLICY',raising=False)
    app,sid,path=build_fixture(tmp_path,course=course,mode=mode)
    html=app.test_client().get(f'/assessments/sessions/{sid}').get_data(as_text=True)
    assert ('id="coding-helper-open"' in html)==(course=='UC100N' and mode!='exam')
    assert ('colab.research.google.com' in html)==(course=='UC100N')
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT assessment_type FROM assessments').fetchone()[0]==('assignment' if mode=='assignment' else 'quiz')


def test_request_limit_does_not_call_provider(tmp_path):
    client,_,provider,_,_,sid,qid=setup(tmp_path)
    response=client.post(endpoint(sid,qid),data='x'*100001,content_type='application/json')
    assert response.status_code==413 and not provider.requests


def test_expiry_during_provider_cannot_return_stale_help(tmp_path):
    client,_,provider,path,clock,sid,qid=setup(tmp_path)
    original=provider.complete
    def complete(request):
        clock.advance(61)
        return original(request)
    provider.complete=complete
    before=dump(path)
    response=client.post(endpoint(sid,qid),json={'action':'concept','topic':'loops'})
    assert response.status_code!=200
    assert 'reply' not in response.json
    assert dump(path)==before
