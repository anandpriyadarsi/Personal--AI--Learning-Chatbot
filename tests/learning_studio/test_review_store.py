import copy
import sqlite3
import pytest
from .helpers import package, source_pdf, catalogue
from personal_learning_assistant.learning_studio.service import LearningStudioService
from personal_learning_assistant.learning_studio.coverage import build_coverage, digest
from personal_learning_assistant.learning_studio.review_store import ReviewStoreMixin, COVERAGE_DDL
from personal_learning_assistant.learning_studio.mapping_review import MappingReviewMixin
from personal_learning_assistant.learning_studio.store import execute_ddl
from personal_learning_assistant.learning_studio.validation import PackageError

Service = LearningStudioService

@pytest.fixture
def studio(tmp_path):
    return Service(tmp_path/'learning_studio.sqlite3',source_loader=lambda _:source_pdf(),catalogue_loader=catalogue)

def ledger(p):
    r=build_coverage(p,source_pdf(),reviewer='Fixture reviewer',method='Synthetic fixture')
    r['inventory']=[{'id':'visual-1','page':1,'kind':'unsupported_visual','text':'Uninterpreted visual','locator':{'rect':[0,0,10,10]}}]
    r['coverage']=[{'element_id':'visual-1','state':'unresolved','reason':'Needs interpretation','mappings':[]}]
    r['review']['inventory_digest']=digest(r['inventory'])
    return r

def prepare(studio):
    p=package();studio.stage(p)
    return p

def test_coverage_durable_idempotent_append_only(studio):
    p=prepare(studio);r=ledger(p)
    assert studio.stage_coverage('synthetic',1,r)['digest']==digest(r)
    assert studio.stage_coverage('synthetic',1,r)['digest']==digest(r)
    assert studio.coverage_report('synthetic',1)==r
    changed=copy.deepcopy(r);changed['coverage'][0]['reason']='Agent cannot interpret this visual'
    studio.stage_coverage('synthetic',1,changed)
    assert studio.coverage_report('synthetic',1)==changed
    with studio.store.connection(write=True) as con:
        assert con.execute('SELECT count(*) FROM coverage_reports').fetchone()[0]==2
        with pytest.raises(sqlite3.IntegrityError):con.execute('DELETE FROM coverage_reports')

def test_coverage_rejects_stale_and_unknown_without_write(studio):
    p=prepare(studio);r=ledger(p);r['package_digest']='0'*64
    with pytest.raises(PackageError):studio.stage_coverage('synthetic',1,r)
    assert studio.coverage_report('synthetic',1) is None
    with pytest.raises(PackageError):studio.stage_coverage('synthetic',99,ledger(p))

def test_mapping_confirmation_new_revision_preserves_history(studio):
    p=prepare(studio);studio.publish('synthetic',1)
    candidates=studio.mapping_candidates('synthetic',1)
    assert candidates['candidates'][0]['topic_id']=='t0'
    result=studio.confirm_mapping('synthetic',1,{'module_revision':2,'course_id':'c0','topic_id':'t0','topic_name':'Topic','confidence':.95,'confirmed':True})
    assert result['revision']==2 and result['state']=='staged'
    assert studio.module('synthetic',1)['mapping'] is None
    assert studio.module('synthetic',2,staged=True)['mapping']['reviewed'] is True
    assert studio.module('synthetic',1)['history']==[1]

@pytest.mark.parametrize('field,value',[('confirmed',False),('confidence',.89),('topic_id','invented'),('topic_name','Renamed'),('module_revision',1),('course_id','fake')])
def test_mapping_confirmation_fails_closed(studio,field,value):
    prepare(studio)
    payload={'module_revision':2,'course_id':'c0','topic_id':'t0','topic_name':'Topic','confidence':.95,'confirmed':True};payload[field]=value
    with pytest.raises(PackageError):studio.confirm_mapping('synthetic',1,payload)
    with studio.store.connection() as con:assert con.execute('SELECT count(*) FROM modules').fetchone()[0]==1

def test_candidates_missing_catalogue_are_readonly(studio):
    prepare(studio);studio.catalogue_loader=lambda:{'available':False,'courses':[]}
    assert studio.mapping_candidates('synthetic',1)['candidates']==[]

def test_mapping_live_catalogue_changed_does_not_write(studio):
    prepare(studio)
    old=studio.mapping_candidates('synthetic',1)
    assert old['available']
    studio.catalogue_loader=lambda:{'available':True,'courses':[{'id':'c0','topics':[{'id':'t0','name':'Renamed'}]}]}
    with pytest.raises(PackageError):studio.confirm_mapping('synthetic',1,{'module_revision':2,'course_id':'c0','topic_id':'t0','topic_name':'Topic','confidence':1,'confirmed':True})
    with studio.store.connection() as con:assert con.execute('SELECT count(*) FROM modules').fetchone()[0]==1

def test_coverage_read_detects_record_integrity(studio):
    p=prepare(studio);studio.stage_coverage('synthetic',1,ledger(p))
    with studio.store.connection(write=True) as con:
        con.execute('DROP TRIGGER immutable_coverage_reports_update')
        con.execute("UPDATE coverage_reports SET digest=?",('0'*64,))
    with pytest.raises(PackageError,match='integrity'):studio.coverage_report('synthetic',1)

def test_mapping_candidates_exclude_keys_and_ignore_caller_extra(studio):
    prepare(studio)
    result=studio.mapping_candidates('synthetic',1)
    assert 'questions' not in result and 'correct_index' not in str(result)
    with pytest.raises(PackageError):studio.confirm_mapping('synthetic',1,{'module_revision':2,'course_id':'c0','topic_id':'t0','topic_name':'Topic','confidence':1,'confirmed':True,'reviewed':True})

def test_mapping_new_revision_retains_exact_questions_source_and_old_attempts(studio):
    p=prepare(studio);studio.publish('synthetic',1)
    from .test_service import event
    studio.attempt('synthetic',event(p))
    studio.confirm_mapping('synthetic',1,{'module_revision':2,'course_id':'c0','topic_id':'t0','topic_name':'Topic','confidence':1,'confirmed':True})
    derived=studio.module('synthetic',2,staged=True,public=False)
    assert derived['questions']==p['questions']
    assert derived['pages']==p['pages'] and derived['source']==p['source']
    assert studio.weak('synthetic',1)[0]['incorrect_count']==1
    assert studio.coverage_report('synthetic',2) is None
