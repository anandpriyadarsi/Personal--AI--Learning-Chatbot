"""Reviewed conversion parent constraints run in the existing owner transaction."""
from copy import deepcopy
import hashlib
import pytest
from tests.academic_evidence_v23_fixtures import uc_owners
from personal_learning_assistant.learning_studio.service import canonical
from personal_learning_assistant.learning_studio.validation import PackageError

def staged(owners):
 s=owners[1];p=deepcopy(owners[2]);p['module_revision']=2
 assets={'assets/cases.png':s.asset('uc100n-demo',1,'assets/cases.png')}
 binding={'revision':1,'digest':hashlib.sha256(canonical(owners[2]).encode()).hexdigest()}
 return s,p,assets,binding

def test_expected_parent_preserves_original_and_exact_receipt(uc_owners):
 s,p,assets,binding=staged(uc_owners)
 assert s.stage(p,assets,expected_parent=binding)['revision']==2
 assert s.stage(p,assets,expected_parent=binding)['revision']==2
 assert s.source('uc100n-demo',1)==s.source('uc100n-demo',2,staged=True)
 s.publish('uc100n-demo',2)
 assert s.stage(p,assets,expected_parent=binding)['revision']==2
 p['title']='Conflicting edited notes'
 with pytest.raises(PackageError):s.stage(p,assets,expected_parent=binding)

@pytest.mark.parametrize('binding',[{'revision':True,'digest':'a'*64},{'revision':1,'digest':'oops'},{'revision':1,'digest':'a'*64,'extra':1}])
def test_bad_parent_shape_never_changes_store(uc_owners,binding):
 s,p,assets,_=staged(uc_owners);before=s.store.path.read_bytes()
 with pytest.raises(PackageError):s.stage(p,assets,expected_parent=binding)
 assert s.store.path.read_bytes()==before

def test_changed_parent_and_target_conflict_are_rejected(uc_owners):
 s,p,assets,binding=staged(uc_owners)
 s.stage(p,assets);s.publish('uc100n-demo',2)
 p['title']='Another edit'
 before=s.store.path.read_bytes()
 with pytest.raises(PackageError):s.stage(p,assets,expected_parent=binding)
 assert s.store.path.read_bytes()==before
