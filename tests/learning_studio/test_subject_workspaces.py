"""Read-only subject workspaces and CY100N Chemistry section regression tests."""
import copy

import pytest

from .helpers import catalogue, package, source_pdf
from .test_service import publish
from personal_learning_assistant.learning_studio.course_views import subject_template
from personal_learning_assistant.learning_studio.service import LearningStudioService
from personal_learning_assistant.learning_studio.validation import PackageError
from personal_learning_assistant.ui.web import create_app


@pytest.fixture
def chemistry(tmp_path):
    course_catalogue = catalogue()
    course_catalogue['courses'][0].update(code='CY100N',name='Green Chemistry')
    course_catalogue['courses'][1].update(code='MA103N',name='Linear Algebra')
    raw=source_pdf()
    service=LearningStudioService(tmp_path/'learning_studio.sqlite3',
        source_loader=lambda _:raw,catalogue_loader=lambda:course_catalogue)
    app=create_app({'TESTING':True,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:service})
    return service,app.test_client(),course_catalogue


def test_subject_titles_are_display_only_and_zero_module_templates_exist(chemistry):
    s,c,cat=chemistry
    assert cat['courses'][0]['name']=='Green Chemistry'
    assert subject_template(cat['courses'][0])['title']=='Chemistry'
    html=c.get('/learning').text
    assert '<h4>Chemistry</h4>' in html
    assert 'Linear Algebra' in html and 'Data Science' not in html
    page=c.get('/learning/courses/c0')
    assert page.status_code==200
    assert '<h1>Chemistry</h1>' in page.text
    assert 'Green Chemistry' in page.text and 'Spectroscopy' in page.text and '>Lab<' in page.text
    assert 'This learning template is ready' in page.text
    assert not s.store.path.exists(), 'GET on an empty library must not create academic state'


def test_chemistry_sections_are_nested_filterable_and_preserve_unknown_modules(chemistry):
    s,c,cat=chemistry
    documents=[
        ('green','Green Chemistry: the 12 principles','Green Chemistry','green-chemistry'),
        ('spectro','AAS Spectroscopy and infrared methods','Spectroscopy','spectroscopy'),
        ('lab','Spectroscopy lab experiment and precautions','Spectroscopy Lab','lab'),
        ('other','Chemical bonding lecture','Chemistry review','other'),
    ]
    for module_id,title,unit,area in documents:
        p=package(module_id=module_id,mapped=True)
        p['title']=title
        p['unit']=unit
        publish(s,p)
    source_mapping=s.module('green',1)['mapping']
    baseline=s.store.path.read_bytes()
    index=c.get('/learning/courses/c0')
    assert index.status_code==200 and '4</strong>' in index.text
    assert 'No modules match these filters' not in index.text
    for module_id,title,unit,area in documents:
        path='/learning/courses/c0?section='+area
        res=c.get(path)
        assert res.status_code==200
        assert title in res.text
        assert res.text.count('class="ls-card ls-learning-module"')==1
        assert '1 module in this view' in res.text
        data=s.library(course_id='c0',section=area)
        assert data['total']==1 and data['modules'][0]['module_id']==module_id
        assert data['chemistry_counts'][area]==1
    assert c.get('/learning/courses/c0?section=spectroscopy').text.find('Spectroscopy lab experiment and precautions')==-1
    assert c.get('/learning/courses/c0?section=other').status_code==200
    assert s.library(course_id='c0')['total']==4
    assert c.get('/learning/courses/c1').status_code==200
    assert s.module('green',1)['mapping']==source_mapping
    assert s.store.path.read_bytes()==baseline


def test_course_section_pagination_and_query_combination(chemistry):
    s,c,_=chemistry
    for i in range(16):
        p=package(module_id=f'green-{i}',mapped=True)
        p['title']=f'Green Chemistry topic {i:02}'
        publish(s,p)
    a=s.library(course_id='c0',section='green-chemistry',offset=0,limit=12)
    b=s.library(course_id='c0',section='green-chemistry',offset=12,limit=12)
    assert a['total']==b['total']==16 and len(a['modules'])==12 and len(b['modules'])==4
    assert a['chemistry_counts']['green-chemistry']==16
    assert c.get('/learning/courses/c0?section=green-chemistry').status_code==200
    assert 'Next' in c.get('/learning/courses/c0?section=green-chemistry').text
    assert 'Previous' in c.get('/learning/courses/c0?section=green-chemistry&offset=12').text
    assert s.library(course_id='c0',section='green-chemistry',search='topic 15')['total']==1


@pytest.mark.parametrize('course_id,section',[
    ('c0','unknown'),('c0','lab/../../wrong'),('c1','lab'),('unmapped','lab'),
])
def test_invalid_section_rejected_without_mutation(chemistry,course_id,section):
    s,c,_=chemistry
    assert c.get('/learning/courses/'+course_id+'?section='+section).status_code==400
    assert not s.store.path.exists()


def test_nonchemistry_course_uses_source_practice_revision_template(chemistry):
    _,c,_=chemistry
    res=c.get('/learning/courses/c1')
    assert res.status_code==200
    assert 'Linear Algebra' in res.text
    assert 'Worked problems' in res.text
    assert 'Mistakes &amp; exam revision' in res.text
    assert 'Notes' in res.text and 'Assessments' in res.text


def test_unknown_academic_year_is_presentation_only_first_year_semester_one(chemistry):
    service,client,source=chemistry
    for course in source['courses']:
        course.pop('academic_year',None)
        course['semester']=''
    assert 'academic_year' not in source['courses'][0]
    page=client.get('/learning')
    assert page.status_code==200
    assert 'First Year' in page.text
    assert 'Semester 1' in page.text
    assert 'Academic year unspecified' not in page.text
    assert 'Semester unspecified' not in page.text
    assert 'ls-subject-summary' in page.text
    assert 'ls-subject-tags' not in page.text
    assert page.text.count('class="ls-card ls-subject-card') == len(source['courses'])
    assert source['courses'][0]['name']=='Green Chemistry'
    assert 'academic_year' not in source['courses'][0]
    assert not service.store.path.exists()


def test_real_academic_year_and_other_semesters_are_not_relabelled(chemistry):
    _,client,source=chemistry
    source['courses'][0]['academic_year']='2027-28'
    source['courses'][0]['semester']='Semester 3'
    page=client.get('/learning')
    assert page.status_code==200
    assert '2027-28' in page.text
    assert 'Semester 3' in page.text
    assert 'First Year' not in page.text
