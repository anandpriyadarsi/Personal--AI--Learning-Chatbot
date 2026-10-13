from .test_service import publish,event
from .test_v12_progress import service
from .helpers import package


def test_initialized_empty_is_no_evidence(tmp_path):
    s=service(tmp_path);publish(s)
    assert s.evidence()['evidence_label']=='No evidence'


def test_retries_are_one_distinct_observation_and_stale_mapping_is_historical(tmp_path):
    s=service(tmp_path);p=publish(s,package(mapped=True))
    for i in range(10):s.attempt('synthetic',event(p,f'retry-{i}',int(i==9)))
    e=s.evidence();g=e['groups'][0]
    assert e['unique_questions']==1 and g['unique_questions']==1
    assert g['evidence_label']=='Limited evidence'
    assert e['recovered_needs_recheck']==1 and e['currently_wrong']==0
    s.catalogue_loader=lambda:{'available':True,'courses':[]}
    e=s.evidence();assert e['reviewed_attempts']==0
    assert e['historically_mapped_attempts']==10 and e['groups'][0]['mapping_status']=='needs_review'
