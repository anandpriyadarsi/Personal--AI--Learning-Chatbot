"""Deterministic proposed V3 pilot adapter; no HTML execution or canonical mapping."""
import hashlib
from .archive import decode_json, read_zip
from .validation import identity, integer, require


def convert_pilot(raw, *, source_id='pilot-source', module_revision=1):
    identity(source_id); integer(module_revision, 1, 1000000)
    files = read_zip(raw, pilot=True)
    required = {'ANVAYA_Learning_Module_Proposed_v1.json', 'ORIGINAL_20_Page_Presentation.pdf', 'Source_Fidelity_Coverage_Report.json'}
    require(required <= files.keys(), 'Pilot archive is missing the proposed JSON, original PDF or fidelity report.')
    proposed = decode_json(files['ANVAYA_Learning_Module_Proposed_v1.json'])
    report = decode_json(files['Source_Fidelity_Coverage_Report.json'])
    source = files['ORIGINAL_20_Page_Presentation.pdf']
    digest = hashlib.sha256(source).hexdigest()
    require(proposed.get('schema') == 'anvaya.learning-module.v1' and proposed.get('source_sha256') == digest and
            report.get('original_source_sha256') == digest, 'Pilot source hash mismatch.')
    require(proposed.get('source_page_count') == 20 and len(proposed.get('lessons', [])) == 20,
            'This adapter expects the attached 20-page V3 pilot.')
    flags = {p['page']: p.get('review_flags', []) for p in report.get('slide_details', [])}
    p = {'schema': 'anvaya.learning-module.v1', 'module_id': 'three-paths-ancient-india',
         'module_revision': module_revision, 'title': proposed['title'], 'unit': 'Comparative Indian Traditions',
         'source': {'source_id': source_id, 'sha256': digest, 'filename': proposed['source_original_filename'],
                    'media_type': 'application/pdf', 'page_count': 20},
         'mapping': None, 'pages': [], 'sections': [], 'revision': [], 'questions': []}
    assets = {}
    for lesson in proposed['lessons']:
        page = lesson['page']
        name = lesson['image_file']
        image = files.get(name)
        require(image is not None and hashlib.sha256(image).hexdigest() == lesson['image_sha256'], 'Pilot image hash mismatch.')
        require(hashlib.sha256(lesson['source_text'].encode()).hexdigest() == lesson['source_text_sha256'], 'Pilot text hash mismatch.')
        assets[name] = image
        p['pages'].append({'page': page, 'status': 'needs_review', 'text': lesson['source_text'],
                          'preview': name, 'review_flags': ['Semantic interpretation has not been independently verified.', *flags.get(page, [])]})
        p['sections'].append({'id': f'lesson-{page:02}', 'title': lesson['title'], 'pages': [page], 'blocks': [
            {'kind': 'source', 'text': lesson['source_text'], 'pages': [page]},
            {'kind': 'teaching', 'text': lesson.get('notes_text', lesson['notes']), 'pages': [page]},
            {'kind': 'mindmap', 'nodes': [lesson['title'], *lesson['points']],
             'alt': 'Teaching summary: ' + '; '.join([lesson['title'], *lesson['points']]), 'pages': [page]},
            {'kind': 'objectives', 'text': lesson['activity'], 'pages': [page]},
        ]})
    p['sections'][0]['blocks'].append({'kind': 'flowchart', 'nodes': ['Read the source', 'Compare the traditions', 'Recall without looking', 'Check and revisit'],
        'alt': 'Suggested learning workflow: read, compare, recall, then check. This is an authored learning strategy.', 'pages': [1, 2, 20]})
    p['revision'].append({'kind': 'teaching', 'text': proposed['revision']['markdown'], 'pages': proposed['revision']['source_pages']})
    for q in proposed['questions']:
        require(q['source_ref']['document_sha256'] == digest and q['source_ref']['page'] == q['page'], 'Pilot question source reference mismatch.')
        p['questions'].append({'id': f'q-{q["id"]:03}', 'revision': 1, 'kind': 'mcq', 'prompt': q['question'],
            'options': q['options'], 'correct_index': q['answer'], 'explanation': q['explanation'],
            'pages': [q['page']], 'difficulty': 'normal', 'low_stakes': True})
    return p, source, assets
