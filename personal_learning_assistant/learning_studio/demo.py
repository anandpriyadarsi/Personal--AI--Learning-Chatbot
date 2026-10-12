"""Explicit disposable demo; never initializes the user's academic registry.

python -m personal_learning_assistant.learning_studio.demo --directory PATH
Optional --pilot-zip PATH runs the strict converter; inconsistent pilots fail
before any filesystem writes. Defaults to clearly labelled synthetic content.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import sqlite3
from .validation import PackageError, require
from .service import LearningStudioService
from .sources import RegisteredSources


def synthetic_catalogue():
    return {'available': True, 'courses': [
        {'id': f'demo-c{i}', 'code': f'DEMO{i}', 'name': f'Synthetic course {i+1}',
         'semester': 'Semester 1 (demo)', 'academic_year': 'Synthetic year',
         'topics': [{'id': f'demo-t{i}', 'name': 'Synthetic comparisons'}]} for i in range(6)]}


def synthetic_pdf(count=20):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    font_ref = writer._add_object(font)
    for i in range(1, count+1):
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font_ref})})
        stream = DecodedStreamObject()
        stream.set_data(f'BT /F1 18 Tf 50 720 Td (Synthetic source page {i}) Tj 0 -35 Td /F1 12 Tf (Demonstration only. No academic evidence.) Tj ET'.encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
    out = io.BytesIO(); writer.write(out); return out.getvalue()


def synthetic_package(raw):
    from PIL import Image, ImageDraw
    count = 20
    p = {'schema': 'anvaya.learning-module.v1', 'module_id': 'synthetic-reader', 'module_revision': 1,
         'title': 'Synthetic Learning Studio demonstration: compare, understand and recall',
         'unit': 'Reader demonstration', 'source': {'source_id': 'demo-source', 'sha256': hashlib.sha256(raw).hexdigest(),
         'filename': 'synthetic-source.pdf', 'media_type': 'application/pdf', 'page_count': count},
         'mapping': None, 'pages': [], 'sections': [], 'revision': [], 'questions': []}
    assets = {}
    for i in range(1, count+1):
        name = f'assets/page-{i:02}.png'
        image = Image.new('RGB', (612, 792), 'white'); draw = ImageDraw.Draw(image)
        draw.text((50, 60), f'Synthetic page {i}: demonstration only', fill='black')
        draw.text((50, 90), 'Textual alternative, table, formula and concept blocks', fill='black')
        out = io.BytesIO(); image.save(out, 'PNG'); assets[name] = out.getvalue()
        p['pages'].append({'page': i, 'status': 'needs_review', 'text': f'Synthetic source page {i}. Demonstration only. No academic evidence.',
                           'preview': name, 'review_flags': ['Synthetic preview is illustrative, not an exact PDF rendering.']})
        blocks = [
            {'kind': 'source', 'text': p['pages'][-1]['text'], 'pages': [i]},
            {'kind': 'teaching', 'text': '**Try it:** compare two cases, explain the difference, then recall from memory.', 'pages': [i]},
            {'kind': 'mindmap', 'nodes': ['Understand', 'Source', 'Comparison', 'Recall'], 'alt': 'Understanding connects source, comparison and recall.', 'pages': [i]},
            {'kind': 'flowchart', 'nodes': ['Observe', 'Compare', 'Recall', 'Check'], 'alt': 'Observe, compare, recall, then check.', 'pages': [i]},
            {'kind': 'table', 'headers': ['Case', 'Distinction'], 'rows': [['A', 'First case'], ['B', 'Second case']], 'pages': [i]},
            {'kind': 'example', 'text': 'Formula example: z = (x − μ) / σ. The formula is teaching content in a synthetic fixture.', 'pages': [i]},
        ]
        p['sections'].append({'id': f'section-{i}', 'title': f'Concept {i}: source-grounded synthetic lesson', 'pages': [i], 'blocks': blocks})
        p['questions'].append({'id': f'q-{i}', 'revision': 1, 'kind': 'mcq', 'prompt': f'Synthetic recall {i}: what comes after compare?',
                              'options': ['Guess', 'Recall'], 'correct_index': 1, 'explanation': 'The teaching workflow says compare, then recall.',
                              'pages': [i], 'difficulty': 'easy', 'low_stakes': True})
    p['revision'] = [
        {'kind': 'teaching', 'text': '## Revision checklist\n- Compare cases.\n- Recall without looking.\n- Recheck missed questions.\n\n**Memory trap:** a corrected retry does not erase an earlier mistake.', 'pages': [1, 20]},
        {'kind': 'recall', 'text': 'What happens to an earlier wrong answer after retrying correctly?', 'answer': 'It remains in server history and appears as recovered, needing recheck.', 'pages': [1]},
    ]
    return p, assets


def make_demo(directory, *, pilot_zip=None):
    # Strict pilot validation happens first. Inconsistent attached data is never
    # silently rebound to a new source hash, even in a disposable demo.
    if pilot_zip:
        from .pilot import convert_pilot
        p, raw, assets = convert_pilot(Path(pilot_zip).read_bytes(), source_id='demo-source')
    else:
        raw = synthetic_pdf(); p, assets = synthetic_package(raw)
    root = Path(directory).absolute()
    require(not any(x.is_symlink() for x in (root, *root.parents)), 'Demo directory cannot be a symlink.')
    marker = root / '.anvaya-learning-demo'
    if root.exists():
        require(root.is_dir() and marker.is_file() and not marker.is_symlink() and marker.read_text() == 'synthetic-learning-studio-v1\n',
                'Choose a new empty demo path; existing user directories are never reused.')
    else:
        root.mkdir(parents=True)
        marker.write_text('synthetic-learning-studio-v1\n')
    source_path = root / 'source.pdf'
    registry_path = root / 'source-registry.sqlite3'
    if not source_path.exists(): source_path.write_bytes(raw)
    require(not source_path.is_symlink() and source_path.read_bytes() == raw, 'Demo source changed; choose a new directory.')
    if not registry_path.exists():
        with sqlite3.connect(registry_path) as con:
            con.execute('CREATE TABLE knowledge_documents(id TEXT PRIMARY KEY,path_key TEXT,content_hash TEXT,mime_type TEXT)')
            con.execute('INSERT INTO knowledge_documents VALUES(?,?,?,?)', ('demo-source', 'demo/source.pdf', hashlib.sha256(raw).hexdigest(), 'application/pdf'))
    sources = RegisteredSources(registry_path, {'demo': root})
    s = LearningStudioService(root / 'learning_studio.sqlite3', source_loader=sources, catalogue_loader=synthetic_catalogue)
    s.stage(p, assets); s.publish(p['module_id'], p['module_revision'])
    import copy
    for i in range(6):
        for j in range(12):
            fixture = copy.deepcopy(p)
            fixture.update(module_id=f'demo-{i}-{j}', title=f'Synthetic presentation {j+1}', unit=f'Unit {j//4+1}')
            fixture['mapping'] = {'course_id': f'demo-c{i}', 'topic_id': f'demo-t{i}', 'topic_name': 'Synthetic comparisons', 'reviewed': True, 'confidence': 1}
            s.stage(fixture, assets); s.publish(fixture['module_id'], 1)
    return s


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True)
    parser.add_argument('--pilot-zip')
    parser.add_argument('--port', type=int, default=5091)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    try:
        s = make_demo(args.directory, pilot_zip=args.pilot_zip)
    except (PackageError, OSError) as error:
        parser.exit(1, f'Demo blocked: {error}\n')
    print(f'Disposable demo prepared: {s.store.path}\nURL: http://127.0.0.1:{args.port}/learning')
    if not args.prepare_only:
        from personal_learning_assistant.ui.web import create_app
        app = create_app({'LEARNING_STUDIO_SERVICE_FACTORY': lambda: s})
        app.run(host='127.0.0.1', port=args.port, debug=False, use_reloader=False)


if __name__ == '__main__': main()
