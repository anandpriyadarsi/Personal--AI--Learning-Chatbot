import copy
import importlib.util
import json
from datetime import datetime,timezone
from html import unescape
import re
from .helpers import package
from .test_v12_progress import service
from .test_service import publish,event
from personal_learning_assistant.ui.web import create_app

def report(s,at=None):
    name='personal_learning_assistant.learning_studio.quality'
    assert importlib.util.find_spec(name), 'Bounded timestamped quality contract missing'
    from personal_learning_assistant.learning_studio.quality import quality_report
    return quality_report(s,'synthetic',1,at=at)

def test_exact_denominators_fresh_question_and_key_free_contract(tmp_path):
    s=service(tmp_path);p=package();p['questions'] += [dict(copy.deepcopy(p['questions'][0]),id='q2'),dict(copy.deepcopy(p['questions'][0]),id='other',pages=[2])]
    publish(s,p);s.attempt('synthetic',event(p));s.attempt('synthetic',event(p,'right',1));before=s.store.path.read_bytes();r=report(s)
    assert r['schema']=='anvaya.learning-quality.v1'
    assert r['summary']==dict(total_questions=3,unanswered=2,wrong=0,correct=0,retry_correct=1,distinct_attempted=1,attempt_events=2)
    q=r['questions'][0];assert q['status']=='recovered_needs_recheck' and q['fresh_question_id']=='q2'
    assert q['independent_recheck']=='unverified / insufficient evidence'
    assert r['source']['sha256']==p['source']['sha256'] and r['owner_scope']=='local-owner'
    assert not {'correct_index','explanation','selection'}&q.keys() and p['questions'][0]['explanation'] not in json.dumps(r)
    assert s.store.path.read_bytes()==before

def test_time_and_duplicate_correct_answers_never_confirm_independence(tmp_path,monkeypatch):
    from personal_learning_assistant.learning_studio import service as domain
    monkeypatch.setattr(domain,'now',lambda:'2026-10-01T10:00:00+00:00')
    s=service(tmp_path);p=publish(s);s.attempt('synthetic',event(p));s.attempt('synthetic',event(p,'retry',1));s.attempt('synthetic',event(p,'again',1))
    q=report(s,datetime(2026,10,1,11,tzinfo=timezone.utc))['questions'][0]
    assert q['suggestion']=='later' and q['suggested_after']=='2026-10-02T10:00:00+00:00'
    r=report(s,datetime(2026,10,3,tzinfo=timezone.utc));assert r['questions'][0]['suggestion']=='due'
    assert not r['independent_recheck_confirmed'] and r['summary']['distinct_attempted']==1

def test_self_report_and_new_revision_do_not_clear_misses(tmp_path):
    s=service(tmp_path);p=publish(s);s.attempt('synthetic',event(p))
    s.record_engagement('synthetic',1,dict(event_id='reflect',section_id='lesson-1',block_index=1,action='reflection',response='I understand.'))
    p=copy.deepcopy(p);p['module_revision']=2;publish(s,p);r=report(s)
    assert r['summary']['wrong']==1 and r['self_reports']['reflection_events']==1
    from personal_learning_assistant.learning_studio.quality import quality_report
    assert quality_report(s,'synthetic',2)['summary']['distinct_attempted']==0

def test_bounded_projection_keeps_complete_denominator(tmp_path):
    s=service(tmp_path);p=package();p['questions']=[dict(copy.deepcopy(p['questions'][0]),id=f'q{i}') for i in range(125)];publish(s,p);r=report(s)
    assert len(r['questions'])==100 and r['questions_truncated'] and r['summary']['unanswered']==125

def test_quality_routes_and_neutral_practice_hint(tmp_path):
    s=service(tmp_path);p=package();p['questions'].append(dict(copy.deepcopy(p['questions'][0]),id='q2'));publish(s,p);s.attempt('synthetic',event(p))
    app=create_app({'TESTING':True,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:s});c=app.test_client()
    assert c.get('/learning/modules/synthetic/1/quality').status_code==200
    assert c.get('/learning/modules/synthetic/1/quality?at=2099').status_code==400
    text=c.get('/learning/modules/synthetic/1?view=practice&question=q1').text
    assert 'Think before choosing' in text and 'unverified / insufficient evidence' in text and 'Try an unattempted related question' in text
    assert 'correct_index' not in text and p['questions'][0]['explanation'] not in text
    assert '1 of 2' in c.get('/learning/modules/synthetic/1/quality?format=html').text

def test_equal_blocks_have_exact_outline_targets(tmp_path):
    s=service(tmp_path);p=package();p['sections'][0]['blocks'].append(copy.deepcopy(p['sections'][0]['blocks'][1]));publish(s,p)
    c=create_app({'TESTING':True,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:s}).test_client()
    text=c.get('/learning/modules/synthetic/1?view=learn').text
    outline=re.search(r'<ul class="ls-subsections">(.*?)</ul>',text,re.S)[1]
    assert '#ls-block-lesson-1-3' in unescape(outline)

def test_full_revision_prints_exact_pending_review_flags(tmp_path):
    s=service(tmp_path);p=package();p['pages'][1]['review_flags']=['Unresolved equation interpretation'];publish(s,p)
    c=create_app({'TESTING':True,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:s}).test_client()
    text=c.get('/learning/modules/synthetic/1?view=revision').text
    assert 'Unresolved equation interpretation' in text and 'Pages awaiting source review' in text
