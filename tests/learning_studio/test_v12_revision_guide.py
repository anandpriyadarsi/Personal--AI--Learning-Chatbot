from personal_learning_assistant.learning_studio.revision import guided_revision

def test_weak_recall_is_prioritized_with_honest_history_and_source_links():
    module={'sections':[{'id':'s1','title':'Comparison','pages':[1],'blocks':[{'kind':'table','pages':[1],'headers':['A','B'],'rows':[['x','y']]}]}], 'revision':[{'kind':'recall','pages':[1],'text':'First','answer':'One'},{'kind':'recall','pages':[2],'text':'Second','answer':'Two'}]}
    result=guided_revision(module,[{'pages':[2],'status':'recovered_needs_recheck','incorrect_count':2}],'5')
    assert result['cards'][0]['text']=='Second'
    assert result['weak_pages']==[2] and 'recorded misses' in result['selection_reason']
    assert result['comparisons'][0]['section_id']=='s1'
    assert result['checklist'] and result['is_subset']
    assert module['revision'][0]['text']=='First'

def test_empty_history_does_not_claim_weakness_and_full_preserves_order():
    module={'sections':[], 'revision':[{'kind':'recall','pages':[1],'text':'First','answer':'One'}]}
    result=guided_revision(module,[],'full')
    assert not result['weak_pages'] and 'No recorded misses' in result['selection_reason']
    assert not result['is_subset'] and result['cards']==module['revision']
