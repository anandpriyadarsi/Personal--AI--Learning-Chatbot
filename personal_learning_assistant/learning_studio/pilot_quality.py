"""Explicit V1.2 normalization of the private pilot; never modifies V1 artifacts.

Added activities and graphs are teaching support, never grading or factual
certification. Original questions, source extracts, flags and assets are retained.
"""
from .archive import decode_json, read_zip
from .pilot import convert_pilot
from .content_blocks import V2, validate_extension
from .validation import require, locators, text


def normalize_pilot(raw, *, source_id='pilot-source', module_revision=2):
    require(type(module_revision) is int and module_revision >= 2, 'V1.2 requires a new module revision >= 2.')
    package, source, assets = convert_pilot(raw, source_id=source_id, module_revision=module_revision)
    proposed = decode_json(read_zip(raw, pilot=True)['ANVAYA_Learning_Module_Proposed_v1.json'])
    package['schema'] = V2
    # Ordered slide summaries are notes, not a claim of graph topology.
    for section in package['sections']:
        for index,block in enumerate(section['blocks']):
            if block['kind']=='mindmap':
                section['blocks'][index]={'kind':'teaching','pages':block['pages'],'text':'### Authored summary\n\n'+'\n'.join('- '+node for node in block['nodes'])}
    # Targeted derived-note correction retains the source's qualifying word.
    for block in package['sections'][3]['blocks']:
        if block['kind']=='teaching':
            block['text']=block['text'].replace("The slide calls it the world's oldest continuously practised religion.", "The slide says it is often called the world's oldest continuously practised religion; this is the source's qualified description, not an independently verified ranking.")
    package['sections'][10]['blocks'].append({'kind':'teaching','pages':[11],'text':'**Authoring provenance:** The warning about missing primary quotation citations and the rationale for question q-017 are added source-literacy guidance by the pilot author. The original slide lists attributions; it does not itself state this evaluation rule. Original question wording and answer key remain unchanged.'})
    cards = proposed['revision'].get('cards')
    require(isinstance(cards, list) and len(cards) == 12, 'Pilot must retain all twelve authored recall cards.')
    ids=set()
    for card in cards:
        require(isinstance(card,dict) and set(card)=={'id','page','prompt','answer'}, 'Malformed pilot recall card.')
        require(card['id'] not in ids, 'Duplicate pilot recall card.'); ids.add(card['id'])
        locators([card['page']],20); text(card['prompt']); text(card['answer'])
        package['revision'].append({'kind':'recall','text':card['prompt'],'answer':card['answer'],'pages':[card['page']]})
    additions = [
        (6, {'kind':'activity','pages':[6,7], 'widget':'compare_reveal',
             'prompt':'Choose a perspective, explain the permanent-self distinction in your own words, then compare with the authored account.',
             'choices':[{'id':'buddhism','label':'Buddhism: anatta','detail':'No permanent self; avoid treating the changing process as an eternal soul.'},
                        {'id':'jainism','label':'Jainism: jiva','detail':'An eternal individual jiva; compare this with anatta.'},
                        {'id':'vedanta','label':'Vedanta diversity','detail':'The deck distinguishes Advaita identity, Vishishtadvaita qualified relationship, and Dvaita distinction. Page 6 is broad shorthand; page 7 qualifies it.'}],
             'feedback':'Use pages 6 and 7 together. This comparison is ungraded reflection, not proof of mastery.'}),
        (11, {'kind':'activity','pages':[11], 'widget':'predict_check',
              'prompt':'Predict whether a quotation appearing on this slide establishes the scientific truth of a philosophical claim. Explain what evidence would still be needed.',
              'choices':[{'id':'slide','label':'Slide attribution is enough','detail':'The slide records an attribution, but does not itself supply independently checked primary quotation evidence.'},
                         {'id':'verify','label':'Further verification is needed','detail':'Check the original publication, exact words, context and attribution before relying on the quotation.'}],
              'feedback':'Separate what the source attributes from independently verified fact. These quotations remain flagged for external verification; this is an ungraded source-literacy activity.'}),
        (7, {'kind':'graph','pages':[7],'graph_type':'concept_map',
             'nodes':[{'id':'vedanta','label':'Vedanta: views of Atman and Brahman'}, {'id':'advaita','label':'Advaita'}, {'id':'vishishtadvaita','label':'Vishishtadvaita'}, {'id':'dvaita','label':'Dvaita'}],
             'edges':[{'from':'vedanta','to':'advaita','label':'identity'}, {'from':'vedanta','to':'vishishtadvaita','label':'qualified relationship'}, {'from':'vedanta','to':'dvaita','label':'enduring distinction'}],
             'alt':'The deck contrasts three Vedanta accounts of Atman and Brahman: Advaita identity, Vishishtadvaita qualified relationship, and Dvaita enduring distinction. This is a conceptual comparison, not historical genealogy.'}),
        (13, {'kind':'graph','pages':[13], 'graph_type':'process',
              'nodes':[{'id':'dukkha','label':'Dukkha: suffering'}, {'id':'samudaya','label':'Samudaya: origin'}, {'id':'nirodha','label':'Nirodha: cessation'}, {'id':'magga','label':'Magga: path'}],
              'edges':[{'from':'dukkha','to':'samudaya','label':'investigate origin'}, {'from':'samudaya','to':'nirodha','label':'consider cessation'}, {'from':'nirodha','to':'magga','label':'identify the path'}],
              'alt':'Study sequence for the Four Noble Truths: suffering, origin, cessation, path. Arrows organize inquiry; they do not claim that suffering mechanically causes cessation.'}),
    ]
    for page, block in additions:
        validate_extension(block)
        package['sections'][page-1]['blocks'].append(block)
    return package, source, assets
