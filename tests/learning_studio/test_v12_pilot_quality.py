import json
from pathlib import Path
import zipfile
import pytest
from personal_learning_assistant.learning_studio.pilot import convert_pilot
from personal_learning_assistant.learning_studio.pilot_quality import normalize_pilot
from personal_learning_assistant.learning_studio.rendering import trusted_graph, trusted_activity

CANDIDATE = Path(__file__).resolve().parents[3] / 'v12-input/04_UNCHANGED_RECONCILED_PILOT_CANDIDATE.zip'

def test_builtin_trusted_rendering_escapes_and_requires_valid_contract():
    graph={'kind':'graph','pages':[1],'graph_type':'process','nodes':[{'id':'a','label':'Read & compare'},{'id':'b','label':'Revisit'}], 'edges':[{'from':'a','to':'b','label':'then'}], 'alt':'Read then revisit'}
    assert 'Read &amp; compare' in str(trusted_graph(graph))
    assert 'then' in str(trusted_graph(graph))
    graph['edges'][0]['to']='missing'
    with pytest.raises(ValueError): trusted_graph(graph)
    widget={'kind':'activity','pages':[1],'widget':'predict_check','prompt':'Predict first','choices':[{'id':'a','label':'Agree','detail':'Different accounts'},{'id':'b','label':'Differ','detail':'Compare evidence'}],'feedback':'Not a graded answer'}
    result=str(trusted_activity(widget, 'check-1'))
    assert 'required' in result and '<details' in result and 'Not a graded answer' in result

def assert_real_pilot_normalization_restores_exact_cards_preserves_every_original():
    raw=CANDIDATE.read_bytes(); old,source,assets=convert_pilot(raw)
    new,new_source,new_assets=normalize_pilot(raw)
    with zipfile.ZipFile(CANDIDATE) as z: proposed=json.loads(z.read('ANVAYA_Learning_Module_Proposed_v1.json'))
    assert new['schema']=='anvaya.learning-module.v2' and new['module_revision']==2
    assert new['questions']==old['questions'] and len(new['questions'])==31
    assert new['pages']==old['pages'] and len(new['sections'])==20
    assert source==new_source and assets==new_assets
    cards=[b for b in new['revision'] if b['kind']=='recall']
    assert cards==[{'kind':'recall','text':c['prompt'],'answer':c['answer'],'pages':[c['page']]} for c in proposed['revision']['cards']]
    blocks=[b for s in new['sections'] for b in s['blocks']]
    assert {b['graph_type'] for b in blocks if b['kind']=='graph'}=={'concept_map','process'}
    assert {b['widget'] for b in blocks if b['kind']=='activity'}=={'compare_reveal','predict_check'}
    assert new['mapping'] is None and all(p['status']=='needs_review' for p in new['pages'])


def test_normalization_contract_builtin(monkeypatch):
    # Always-executed public fixture, with private bytes additionally checked locally.
    import copy
    import personal_learning_assistant.learning_studio.pilot_quality as quality
    from .helpers import package
    original=package()
    original['sections']=[{'id':f'lesson-{i:02}', 'title':f'Lesson {i}', 'pages':[i], 'blocks':[{'kind':'teaching','pages':[i],'text':'Synthetic notes'}]} for i in range(1,21)]
    cards=[{'id':f'r{i}','page':i,'prompt':f'Synthetic prompt {i}','answer':f'Synthetic answer {i}'} for i in range(1,13)]
    monkeypatch.setattr(quality,'convert_pilot',lambda *args,**kwargs:(copy.deepcopy(original),b'PDF',{}))
    monkeypatch.setattr(quality,'read_zip',lambda *args,**kwargs:{'ANVAYA_Learning_Module_Proposed_v1.json':json.dumps({'revision':{'cards':cards}}).encode()})
    new,source,assets=quality.normalize_pilot(b'fixture')
    assert new['questions']==original['questions']
    assert len([b for b in new['revision'] if b['kind']=='recall'])==12
    assert len([b for section in new['sections'] for b in section['blocks'] if b['kind']=='activity'])==2
    monkeypatch.undo()
    if CANDIDATE.exists():
        assert_real_pilot_normalization_restores_exact_cards_preserves_every_original()


def test_graph_branches_labels_and_injection_rejected():
    graph={'kind':'graph','pages':[1],'graph_type':'concept_map','nodes':[{'id':'root','label':'Root'},{'id':'a','label':'Alpha'},{'id':'b','label':'Beta'}],'edges':[{'from':'root','to':'a','label':'first branch'},{'from':'root','to':'b','label':'second branch'}],'alt':'Two branches'}
    rendered=str(trusted_graph(graph))
    assert rendered.count('<path')==2 and 'first branch' in rendered and 'second branch' in rendered
    assert '<svg' in rendered and 'Represented relationships' in rendered
    graph['nodes'][0]['label']='<script>alert(1)</script>'
    with pytest.raises(ValueError): trusted_graph(graph)


def test_graph_direction_has_visible_generated_arrow_geometry():
    graph={'kind':'graph','pages':[1],'graph_type':'process','nodes':[{'id':'a','label':'Read'},{'id':'b','label':'Compare'}],'edges':[{'from':'a','to':'b','label':'then'}],'alt':'Read then compare'}
    rendered=str(trusted_graph(graph))
    assert '<polygon points="350,180 360,175 360,185"' in rendered
    assert 'url(#ls-direction)' not in rendered
