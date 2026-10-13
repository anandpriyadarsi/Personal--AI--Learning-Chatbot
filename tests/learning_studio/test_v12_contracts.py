import copy
import pytest
from .helpers import package, source_pdf, catalogue
from personal_learning_assistant.learning_studio.validation import validate_package, PackageError


def graph():
    return {'kind':'graph','pages':[1],'graph_type':'concept_map',
            'nodes':[{'id':'a','label':'Case A'},{'id':'b','label':'Case B'}],
            'edges':[{'from':'a','to':'b','label':'contrasts with'}],
            'alt':'Case A contrasts with Case B.'}


def activity():
    return {'kind':'activity','pages':[1],'widget':'compare_reveal','prompt':'Compare the two cases.',
            'choices':[{'id':'a','label':'A','detail':'First case'},{'id':'b','label':'B','detail':'Second case'}],
            'feedback':'Compare the source evidence; this is ungraded reflection.'}


def v2():
    p=package();p['schema']='anvaya.learning-module.v2'
    p['sections'][0]['blocks'] += [graph(),activity()]
    return p


def test_v2_graph_and_widgets_are_data_and_v1_history_still_valid():
    validate_package(package(),catalogue(),source_pdf())
    p=v2();assert validate_package(p,catalogue(),source_pdf())==p


@pytest.mark.parametrize('change',[
    lambda b:b['edges'][0].update(to='missing'),
    lambda b:b['nodes'][1].update(id='a'),
    lambda b:b['nodes'][0].update(label='<script>alert(1)</script>'),
    lambda b:b.update(url='https://remote.invalid/graph.svg'),
    lambda b:b.update(nodes=b['nodes']*30),
    lambda b:b['edges'][0].update(label='javascript:alert(1)'),
])
def test_malformed_graph_relationships_or_code_rejected(change):
    p=v2();change(p['sections'][0]['blocks'][-2])
    with pytest.raises(PackageError):validate_package(p,catalogue(),source_pdf())


def test_legacy_ordered_lists_do_not_accept_invented_graph_edges():
    p=package();p['sections'][0]['blocks'].append(graph())
    with pytest.raises(PackageError):validate_package(p,catalogue(),source_pdf())


def test_widget_registry_rejects_callbacks_unknown_types_duplicate_choices():
    for change in (lambda b:b.update(widget='run_python'),lambda b:b.update(callback='eval'),
                   lambda b:b['choices'][1].update(id='a')):
        p=v2();change(p['sections'][0]['blocks'][-1])
        with pytest.raises(PackageError):validate_package(p,catalogue(),source_pdf())


@pytest.mark.parametrize('path',[('schema',),('graph_type',),('edge_from',),('widget',)])
def test_malformed_extension_tags_are_bounded_validation_errors(path):
    p=v2()
    if path[0]=='schema':p['schema']={}
    elif path[0]=='graph_type':p['sections'][0]['blocks'][-2]['graph_type']={}
    elif path[0]=='edge_from':p['sections'][0]['blocks'][-2]['edges'][0]['from']={}
    else:p['sections'][0]['blocks'][-1]['widget']={}
    with pytest.raises(PackageError):validate_package(p,catalogue(),source_pdf())
