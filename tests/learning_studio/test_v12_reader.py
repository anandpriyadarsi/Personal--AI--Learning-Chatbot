import copy
from .test_routes import client,token
from .test_service import publish
from .helpers import package


def test_single_lesson_selected_all_and_invalid_section(client):
    c,s,app=client;p=package();other=copy.deepcopy(p['sections'][0]);other['id']='lesson-2';other['title']='Second lesson unique title';other['pages']=[2];p['sections'].append(other);publish(s,p)
    path='/learning/modules/synthetic/1'
    html=c.get(path+'?view=learn').data
    assert html.count(b'class="ls-lesson"')==1
    assert b'Compare with original' in html
    assert b'Lesson 1 of 2' in html
    assert b'Second lesson unique title</h2>' not in html
    assert b'Second lesson unique title</h2>' in c.get(path+'?view=learn&section=lesson-2').data
    assert c.get(path+'?view=learn&section=missing').status_code==404
    assert c.get(path+'?view=learn&all=1').data.count(b'class="ls-lesson"')==2


def test_progress_http_guard_pure_reads_and_restart(client):
    c,s,app=client;publish(s);path='/learning/modules/synthetic/1/progress';before=s.store.path.read_bytes()
    assert c.get(path).json['current'] is None
    assert before==s.store.path.read_bytes()
    payload={'event_id':'r1','section_id':'lesson-1','view':'learn'}
    assert c.post(path,json=payload).status_code==403
    assert c.post(path,json=payload,headers=token(app)).status_code==200
    assert c.get(path).json['current']['section_id']=='lesson-1'
    assert c.post(path,json=dict(payload,owner='other'),headers=token(app)).status_code==400


def test_source_and_practice_are_selected_not_walls(client):
    c,s,app=client;p=package();q=dict(p['questions'][0],id='q2',prompt='Second question unique');p['questions'].append(q);publish(s,p);path='/learning/modules/synthetic/1'
    assert c.get(path+'?view=source').data.count(b'class="ls-source-page"')==1
    assert b'id="source-page-2"' in c.get(path+'?view=source&page=2').data
    assert c.get(path+'?view=source&page=999').status_code==404
    assert c.get(path+'?view=practice').data.count(b'class="ls-question"')==1
    assert b'Second question unique' in c.get(path+'?view=practice&question=q2').data
    assert c.get(path+'?view=practice&question=missing').status_code==404
    assert c.get(path+'?view=practice&questions=all').data.count(b'class="ls-question"')==2


def test_staged_coverage_links_and_mapping_csrf(client):
    from .test_review_store import ledger
    c,s,app=client;p=package();record=ledger(p)
    record['unresolved']=[{'id':'review-1','pages':[1],'snippet':'Synthetic visual','issue':'Needs interpretation','next_action':'Inspect original page'}]
    s.stage(p,coverage=record)
    html=c.get('/learning/modules/synthetic/1/coverage').data
    assert b'/learning/staged/synthetic/1?view=source' in html
    assert c.get('/learning/staged/synthetic/1?view=source&page=1').status_code==200
    assert c.get('/learning/modules/synthetic/1/mapping').status_code==200
    assert c.post('/learning/modules/synthetic/1/mapping',json={}).status_code==403
    assert c.post('/learning/tutor-review',json={}).status_code==403
