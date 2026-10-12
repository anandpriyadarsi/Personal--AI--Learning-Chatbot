import copy
import pytest
from .helpers import package, source_pdf, catalogue
from .test_service import publish,event
from personal_learning_assistant.learning_studio.service import LearningStudioService
from personal_learning_assistant.ui.web import create_app


def service(tmp_path):
    return LearningStudioService(tmp_path/'learning_studio.sqlite3',source_loader=lambda _:source_pdf(),catalogue_loader=catalogue)


def test_removed_course_module_is_discoverable_without_remapping(tmp_path):
    s=service(tmp_path); p=publish(s,package(mapped=True))
    before=s.module('synthetic',1)['mapping']
    s.catalogue_loader=lambda:{'available':True,'courses':[]}
    assert s.library()['unavailable_count']==1
    view=s.library(course_id='unavailable')
    assert view['total']==1 and view['modules'][0]['module_id']=='synthetic'
    app=create_app({'TESTING':True,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:s})
    c=app.test_client()
    assert b'Course unavailable / needs review' in c.get('/learning').data
    assert c.get('/learning/courses/unavailable').status_code==200
    assert s.module('synthetic',1)['mapping']==before


def test_weak_question_links_precise_historical_lesson_and_question(tmp_path):
    s=service(tmp_path);p=package()
    p['sections'].insert(0,{'id':'first','title':'First section','pages':[2],
        'blocks':[{'kind':'teaching','text':'Other concept','pages':[2]}]})
    publish(s,p);s.attempt('synthetic',event(p))
    new=copy.deepcopy(p);new['module_revision']=2;publish(s,new)
    app=create_app({'TESTING':True,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:s})
    html=app.test_client().get('/learning/modules/synthetic/1?view=weak').data
    assert b'/learning/modules/synthetic/1?view=learn' in html and b'#lesson-1' in html
    assert b'#question-q1' in html
    weak=s.weak('synthetic',1)[0]
    assert weak['lesson_section_id']=='lesson-1' and weak['source_page']==1




def test_authored_markdown_table_has_accessible_scroll_boundary():
    from personal_learning_assistant.learning_studio.rendering import markdown
    rendered=str(markdown('| A | B |\n|---|---|\n|one|two|'))
    assert 'ls-table-scroll' in rendered and 'tabindex="0"' in rendered and '<table>' in rendered


def test_removed_course_back_link_and_missing_optional_metadata(tmp_path):
    s=service(tmp_path);publish(s,package(mapped=True))
    s.catalogue_loader=lambda:{'available':True,'courses':[]}
    app=create_app({'TESTING':True,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:s})
    html=app.test_client().get('/learning/modules/synthetic/1').data
    assert b'/learning/courses/unavailable' in html
    sparse=catalogue();sparse['courses'][0].pop('semester');sparse['courses'][1]['semester']='S1'
    s.catalogue_loader=lambda:sparse
    assert app.test_client().get('/learning').status_code==200
