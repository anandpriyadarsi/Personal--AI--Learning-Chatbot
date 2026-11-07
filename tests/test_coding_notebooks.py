"""Only reviewed synthetic template/reference snippets run in isolated tests."""
import json
import pytest
import nbformat
from personal_learning_assistant.services.coding_notebooks import export_notebook, TEMPLATES
from personal_learning_assistant.domain.coding_models import CodingError


def task(template_id,code=''):
    return {'id':'00000000-0000-4000-a000-000000000001','revision':1,'title':'Synthetic',
            'template_id':template_id,'snapshot':{'objective':'','code':code}}


@pytest.mark.parametrize('template_id',TEMPLATES)
def test_curated_structure_and_public_checks(template_id):
    data=export_notebook(task(template_id),template_id=template_id)
    assert data==export_notebook(task(template_id),template_id=template_id)
    notebook=nbformat.reads(data.decode('utf-8'),as_version=4);nbformat.validate(notebook)
    assert len(notebook.cells)<=40 and len(data)<512*1024
    assert len({c.id for c in notebook.cells})==len(notebook.cells)
    for cell in notebook.cells:
        if cell.cell_type=='code':assert cell.execution_count is None and cell.outputs==[]
    assert notebook.metadata.anvaya.provenance=='not_executed'
    spec=TEMPLATES[template_id]
    # Authored solutions live ONLY in this trusted test, never exported/embedded.
    references={
        'python-collections':'passing = {name: score for name, score in scores if score >= 50}',
        'numpy-shapes':'matrix = values.reshape(2,3)\nrow_totals = matrix.sum(axis=1)',
        'pandas-indexing':'labelled = df.loc[103]\npositional = df.iloc[2]\nmeans = df.groupby("group")["score"].mean()',
        'missing-values':'missing = df.isna().sum()\ndropped = df.dropna()\nfilled = df.fillna(df.median())',
        'histogram':'fig, ax = plt.subplots()\ncounts, edges, patches = ax.hist(values,bins=bins)\nax.set_xlabel("Measurement")\nax.set_ylabel("Frequency")'}
    import matplotlib
    matplotlib.use('Agg')
    namespace={}
    for source in (spec['imports'],spec['data'],references[template_id],spec['check']):exec(compile(source,'<trusted synthetic template>','exec'),namespace)
    # A meaningful deliberate defect must fail its public self-check.
    bad={
      'python-collections':'passing = {}', 'numpy-shapes':'row_totals = matrix.sum(axis=0)',
      'pandas-indexing':'labelled = df.iloc[0]', 'missing-values':'filled = df.copy()',
      'histogram':'counts = counts * 0'}
    exec(compile(bad[template_id],'<trusted deliberate defect>','exec'),namespace)
    with pytest.raises(AssertionError):exec(compile(spec['check'],'<trusted synthetic check>','exec'),namespace)
    import matplotlib.pyplot as plt
    plt.close('all')


def test_arbitrary_code_is_json_only_without_invented_assertions(tmp_path):
    sentinel=tmp_path/'forbidden'
    snippet=f'import pathlib\npathlib.Path({str(sentinel)!r}).touch()\n<script>alert(1)</script>'
    data=export_notebook(task('',snippet),include_student_code=True)
    notebook=json.loads(data)
    assert any(c['source']==snippet for c in notebook['cells'])
    assert not any('assert ' in c['source'] for c in notebook['cells'])
    assert not sentinel.exists()
    assert 'Student-defined expected behavior' in data.decode()
    with pytest.raises(CodingError): export_notebook(task(''),template_id='numpy-shapes')
