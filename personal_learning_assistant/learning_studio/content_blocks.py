"""V2 adds bounded non-executable graph and ungraded activity data."""
from .validation import identity, integer, items, require, shape, text

V2 = 'anvaya.learning-module.v2'


def validate_extension(block):
    kind = block.get('kind')
    if kind == 'graph':
        shape(block, {'kind','pages','graph_type','nodes','edges','alt'})
        require(isinstance(block['graph_type'], str) and block['graph_type'] in {'concept_map','process'}, 'Unsupported graph type.')
        text(block['alt'],5000)
        nodes=items(block['nodes'],24,nonempty=True);ids=set()
        for node in nodes:
            shape(node,{'id','label'});identity(node['id']);text(node['label'],180)
            require(node['id'] not in ids,'Duplicate graph node ID.');ids.add(node['id'])
        edges=items(block['edges'],60,nonempty=True);seen=set();adj={n:[] for n in ids}
        for edge in edges:
            shape(edge,{'from','to','label'});identity(edge['from']);identity(edge['to']);text(edge['label'],180)
            require(edge['from'] in ids and edge['to'] in ids and edge['from']!=edge['to'], 'Graph edge references unknown or identical nodes.')
            pair=(edge['from'],edge['to'],edge['label']);require(pair not in seen,'Duplicate graph edge.');seen.add(pair)
            adj[edge['from']].append(edge['to'])
        require(ids == {e[k] for e in edges for k in ('from','to')}, 'Every graph node needs a represented relationship.')
        if block['graph_type']=='process':
            visiting=set();done=set()
            def visit(n):
                require(n not in visiting,'Process graph cannot contain a cycle.')
                if n in done:return
                visiting.add(n)
                for child in adj[n]:visit(child)
                visiting.remove(n);done.add(n)
            for n in ids:visit(n)
    elif kind == 'activity':
        shape(block,{'kind','pages','widget','prompt','choices','feedback'})
        require(isinstance(block['widget'], str) and block['widget'] in {'compare_reveal','predict_check'},'Unsupported trusted widget.')
        text(block['prompt'],3000);text(block['feedback'],6000)
        choices=items(block['choices'],12,nonempty=True);require(len(choices)>=2,'Activity needs two perspectives.')
        ids=set()
        for choice in choices:
            shape(choice,{'id','label','detail'});identity(choice['id']);text(choice['label'],300);text(choice['detail'],4000)
            require(choice['id'] not in ids,'Duplicate activity choice ID.');ids.add(choice['id'])
    else:require(False,'Unsupported extension block.')
