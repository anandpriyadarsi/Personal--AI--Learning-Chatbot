"""V1.6: every authored question is navigable without inventing mastery evidence."""
from copy import deepcopy
import pytest

from .helpers import package
from .test_v12_progress import service
from .test_service import publish, event
from personal_learning_assistant.learning_studio.quality import quality_report
from personal_learning_assistant.learning_studio.validation import PackageError
from personal_learning_assistant.ui.web import create_app


def populated(tmp_path):
    studio=service(tmp_path)
    authored=package()
    original=authored['questions'][0]
    authored['questions']=[original]+[
        dict(deepcopy(original),id=f'q{i:03}',pages=[1 if i%2 else 2])
        for i in range(2,127)]
    publish(studio,authored)
    return studio,authored


def test_full_bank_pagination_has_no_unreachable_questions(tmp_path):
    studio,authored=populated(tmp_path)
    seen=[]
    for offset in (0,50,100):
        view=quality_report(studio,'synthetic',1,offset=offset,limit=50)
        seen += [q['question_id'] for q in view['questions']]
        assert view['summary']['total_questions']==126
        assert view['summary']['unanswered']==126
        assert view['questions_total']==126
        assert view['pagination']['shown']==min(50,126-offset)
        assert view['pagination']['has_next']==(offset<100)
        assert not view['independent_recheck_confirmed']
        assert all(q['independent_recheck']=='unverified / insufficient evidence' for q in view['questions'])
    assert len(seen)==126 and set(seen)=={q['id'] for q in authored['questions']}


def test_status_and_source_page_filters_keep_unfiltered_denominators(tmp_path):
    studio,authored=populated(tmp_path)
    studio.attempt('synthetic',event(authored))
    all_view=quality_report(studio,'synthetic',1)
    assert all_view['summary']['total_questions']==126
    status=quality_report(studio,'synthetic',1,question_ids=['q1'])['questions'][0]['status']
    assert status in {'needs_review','checked_correct'}
    narrowed=quality_report(studio,'synthetic',1,status=status,page=1,limit=20)
    assert narrowed['questions_total']==1
    assert [q['question_id'] for q in narrowed['questions']]==[authored['questions'][0]['id']]
    assert narrowed['summary']==all_view['summary']
    unread=quality_report(studio,'synthetic',1,status='never_practised',page=2,limit=50)
    assert unread['questions_total']==63
    assert all(2 in q['pages'] and q['status']=='never_practised' for q in unread['questions'])
    assert unread['pagination']['has_next'] and unread['pagination']['next_offset']==50
    assert not {'correct_index','explanation','selection'}&set(narrowed['questions'][0])


@pytest.mark.parametrize('arguments',[
    {'status':'mastered'},{'page':0},{'page':501},{'offset':-1},{'offset':1000001},{'limit':0},{'limit':101}
])
def test_queue_domain_rejects_invalid_filters(tmp_path,arguments):
    studio,_=populated(tmp_path)
    with pytest.raises(PackageError):
        quality_report(studio,'synthetic',1,**arguments)


def test_read_only_web_filters_and_navigation_are_no_js_accessible(tmp_path):
    studio,authored=populated(tmp_path)
    before=studio.store.path.read_bytes()
    app=create_app({'TESTING':True,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:studio})
    client=app.test_client()
    base='/learning/modules/synthetic/1/quality'
    first=client.get(base+'?format=html&limit=20')
    assert first.status_code==200
    assert first.headers['Cache-Control']=='no-store'
    assert 'Showing 1–20 of 126 matching questions' in first.text
    assert 'Next questions' in first.text and 'Previous questions' not in first.text
    assert first.text.count('class="ls-notice ls-quality-item"')==20
    end=client.get(base+'?format=html&limit=20&offset=120')
    assert end.status_code==200 and 'Showing 121–126 of 126' in end.text
    assert 'Next questions' not in end.text and 'Previous questions' in end.text
    assert 'name="status"' in end.text and 'name="page"' in end.text
    json_view=client.get(base+'?limit=20&status=never_practised&page=2').json
    assert json_view['filters']=={'status':'never_practised','page':2}
    assert json_view['summary']['total_questions']==126
    assert json_view['pagination']['total']==63
    assert not json_view['independent_recheck_confirmed']
    assert authored['questions'][0]['explanation'] not in str(json_view)
    assert studio.store.path.read_bytes()==before


@pytest.mark.parametrize('suffix',[
    '?at=2099','?offset=-1','?offset=99999999','?offset=x','?limit=101',
    '?page=3','?status=mastered','?format=csv','?status=all&status=needs_review',
    '?source_hash=abc','?offset=%2B2',
])
def test_invalid_web_parameters_fail_closed(tmp_path,suffix):
    studio,_=populated(tmp_path)
    client=create_app({'TESTING':True,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:studio}).test_client()
    assert client.get('/learning/modules/synthetic/1/quality'+suffix).status_code==400
