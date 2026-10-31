"""Regression coverage for the local-only self-contained Learning Studio import."""
import hashlib
import io
import json
import zipfile

import pytest
from pypdf import PdfWriter

from personal_learning_assistant.learning_studio.archive import read_zip
from personal_learning_assistant.learning_studio.portable_bundle import decode_self_contained_bundle
from personal_learning_assistant.learning_studio.service import LearningStudioService
from personal_learning_assistant.learning_studio.validation import PackageError


def _pdf():
    stream = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(stream)
    return stream.getvalue()


def _module(source):
    return {
        'schema': 'anvaya.learning-module.v2',
        'module_id': 'uc100n.test.portable',
        'module_revision': 1,
        'title': 'Portable UC100N test',
        'unit': 'UC100N',
        'source': {
            'source_id': 'NEEDS_PORTABLE_BINDING',
            'sha256': hashlib.sha256(source).hexdigest(),
            'filename': 'original.pdf',
            'media_type': 'application/pdf',
            'page_count': 1,
        },
        'mapping': None,
        'pages': [{'page': 1, 'status': 'verified', 'text': 'Blank page', 'review_flags': []}],
        'sections': [{
            'id': 'intro', 'title': 'Intro', 'pages': [1],
            'blocks': [{'kind': 'teaching', 'pages': [1], 'text': 'Encoding makes categories numeric.'}],
        }],
        'revision': [{'kind': 'recall', 'pages': [1], 'text': 'What is encoding?',
                      'answer': 'Converting categories to numerical representation.'}],
        'questions': [{
            'id': 'q1', 'revision': 1, 'kind': 'mcq',
            'prompt': 'What is one-hot encoding?',
            'options': ['One binary indicator per category', 'Deleting categories'],
            'correct_index': 0, 'explanation': 'One-hot indicators encode categories.',
            'pages': [1], 'difficulty': 'easy', 'low_stakes': True,
        }],
    }


def _archive(source=None, extra=None):
    source = source or _pdf()
    entries = {
        'bundle.json': json.dumps({
            'schema': 'anvaya.learning-bundle.v1',
            'modules': ['theory'],
        }).encode(),
        'modules/theory/module.json': json.dumps(_module(source)).encode(),
        'modules/theory/source.pdf': source,
        'extras/Google_Colab/Lab.ipynb': b'{"cells":[]}',
    }
    if extra:
        entries.update(extra)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return stream.getvalue()


def _decode(raw):
    return decode_self_contained_bundle(read_zip(raw, pilot=True))


def test_portable_zip_binds_exact_original_pdf_and_preserves_inert_extra():
    data = _decode(_archive())
    assert len(data) == 1
    module, assets, coverage, source = data[0]
    assert module['source']['source_id'] == 'portable.' + hashlib.sha256(source).hexdigest()
    assert assets == {} and coverage is None
    assert module['source']['page_count'] == 1


def test_portable_zip_rejects_pdf_tamper_and_executable_extra():
    raw = _archive()
    members = read_zip(raw, pilot=True)
    members['modules/theory/source.pdf'] = b'%PDF-mismatched'
    with pytest.raises(PackageError, match='checksum'):
        decode_self_contained_bundle(members)
    members = read_zip(raw, pilot=True)
    members['extras/run.py'] = b'print("not executed")'
    with pytest.raises(PackageError, match='Extras'):
        decode_self_contained_bundle(members)


def test_portable_zip_rejects_extra_module_and_traversal():
    raw = _archive()
    members = read_zip(raw, pilot=True)
    members['modules/unlisted/module.json'] = members['modules/theory/module.json']
    with pytest.raises(PackageError, match='unrecognized'):
        decode_self_contained_bundle(members)
    malicious = _archive(extra={'../escape.txt': b'untrusted'})
    with pytest.raises(PackageError, match='Unsafe archive path'):
        _decode(malicious)


def test_portable_stage_publish_reads_immutable_snapshot_not_external_registry(tmp_path):
    module, assets, coverage, source = _decode(_archive())
    calls = []
    def unavailable_loader(source_id):
        calls.append(source_id)
        raise AssertionError('Portable package must not use external source registry')
    studio = LearningStudioService(
        tmp_path / 'learning_studio.sqlite3',
        source_loader=unavailable_loader,
        catalogue_loader=lambda: {'available': False, 'courses': []},
    )
    staged = studio.stage(module, assets, coverage, source_bytes=source)
    assert staged['state'] == 'staged'
    assert studio.source(module['module_id'], 1, staged=True) == source
    assert studio.publish(module['module_id'], 1)['state'] == 'published'
    assert studio.source(module['module_id'], 1) == source
    assert studio.module(module['module_id'], 1)['title'] == module['title']
    assert calls == []


def test_portable_stage_rejects_forged_source_id(tmp_path):
    module, assets, coverage, source = _decode(_archive())
    module['source']['source_id'] = 'portable.' + '0' * 64
    studio = LearningStudioService(
        tmp_path / 'learning_studio.sqlite3',
        source_loader=lambda source_id: None,
        catalogue_loader=lambda: {'available': False, 'courses': []},
    )
    with pytest.raises(PackageError, match='identity'):
        studio.stage(module, assets, coverage, source_bytes=source)


def test_portable_bundle_atomic_rollback_when_second_member_conflicts(tmp_path):
    module, assets, coverage, source = _decode(_archive())
    studio = LearningStudioService(
        tmp_path / 'learning_studio.sqlite3',
        source_loader=lambda source_id: None,
        catalogue_loader=lambda: {'available': False, 'courses': []},
    )
    second = dict(module, module_id='uc100n.test.existing')
    studio.stage(second, assets, coverage, source_bytes=source)
    conflicting = dict(second, title='Conflicting immutable revision')
    with pytest.raises(PackageError, match='immutable'):
        studio.stage_many_portable([
            (module, assets, coverage, source),
            (conflicting, assets, coverage, source),
        ])
    # The first module was not left partially staged after the second failed.
    with studio.store.connection() as con:
        assert con.execute('SELECT count(*) FROM modules WHERE module_id=?',
                           (module['module_id'],)).fetchone()[0] == 0
        assert con.execute('SELECT count(*) FROM modules WHERE module_id=?',
                           (second['module_id'],)).fetchone()[0] == 1
