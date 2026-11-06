"""Deterministic in-memory notebook export. Student code remains inert text."""
import json
from personal_learning_assistant.domain.coding_models import CodingError
from personal_learning_assistant.services.coding_templates import TEMPLATES


def export_notebook(task, *, template_id='', include_student_code=False):
    if type(include_student_code) is not bool:
        raise CodingError('invalid_field','Choose whether to include saved student code.')
    if template_id and template_id not in TEMPLATES:
        raise CodingError('invalid_template','Choose a reviewed practice template.')
    # Arbitrary snippets must never inherit assertions from an unrelated template.
    if template_id != (task.get('template_id') or ''):
        raise CodingError('template_mismatch','Export uses this task’s saved template. Start a new task for another template.',409)
    cells = []
    def add(kind, source):
        cell = {'id':f'cell-{len(cells)+1:02d}', 'cell_type':kind, 'metadata':{}, 'source':source}
        if kind=='code':
            cell.update(execution_count=None,outputs=[])
        cells.append(cell)
    spec = TEMPLATES.get(template_id)
    objective = task['snapshot']['objective'] or (spec['objective'] if spec else 'Explore your student-defined task.')
    add('markdown', '# ANVAYA practice\n\n' + objective + '\n\nProvenance: not_executed. This notebook is editable practice, not an assessment or verified execution receipt.')
    add('markdown', '## Before running\n\nDownload, then choose File → Upload notebook in Colab, or open in Jupyter. Run cells manually in order. ANVAYA cannot see this notebook or runtime. Paste reviewed code/output/error into Tutor for feedback. Outputs you paste are unverified.\n\nPrerequisites: ' + (spec['prerequisites'] if spec else 'Python basics') + '\n\nUse a Python 3 environment with NumPy, Pandas and Matplotlib when required. Standard Colab environments normally include these; check the versions below. No installation or Drive access is performed by this notebook.')
    add('code',spec['imports'] if spec else 'import sys\nprint("Python", sys.version.split()[0])')
    if spec:
        add('code',spec['data'])
        add('markdown','## Predict before running\n\n' + spec['task'])
    else:
        add('markdown','## Student-defined expected behavior\n\nWrite a prediction and define what success means before running. No assertions have been invented for your code.')
    code = task['snapshot'].get('code','') if include_student_code else ''
    add('code', code if code else (spec['starter'] if spec else '# Write your attempt here.'))
    if spec:
        add('markdown','## Public self-check\n\nThese visible checks concern synthetic data. A failed check is an invitation to inspect your attempt, not a grade.')
        add('code',spec['check'])
    add('markdown','## Reflect / viva\n\n' + (spec['reflection'] if spec else 'Explain your inputs, output and one assumption. What would make the result misleading?'))
    add('markdown','## Fresh variant\n\n' + (spec['variant'] if spec else 'Change one input and predict how your result changes. Rebuild the essential operation from blank.'))
    notebook = {'nbformat':4,'nbformat_minor':5,'metadata':{
        'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
        'language_info':{'name':'python','version':'3'},
        'anvaya':{'schema':'anvaya.practice-notebook.v1','template_id':template_id or None,
                  'template_version':1 if spec else None,'task_id':task['id'],'task_revision':task['revision'],
                  'provenance':'not_executed'}},'cells':cells}
    encoded = json.dumps(notebook,ensure_ascii=False,allow_nan=False,indent=2).encode('utf-8')
    if len(cells)>40 or len(encoded)>512*1024:
        raise CodingError('too_large','Notebook exceeds the export size limit.',413)
    return encoded
