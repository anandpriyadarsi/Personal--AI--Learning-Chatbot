import copy
import hashlib
import sqlite3
import threading
from pathlib import Path
import pytest
from .helpers import source_pdf, package, catalogue
from .test_service import publish, event
from personal_learning_assistant.learning_studio.service import LearningStudioService
from personal_learning_assistant.learning_studio.sources import RegisteredSources
from personal_learning_assistant.learning_studio.validation import PackageError


def test_source_registry_read_and_symlink_ownership(tmp_path):
    raw = source_pdf(); root = tmp_path / 'originals'; root.mkdir()
    original = root / 'lecture.pdf'; original.write_bytes(raw)
    registry = tmp_path / 'source-registry.db'
    with sqlite3.connect(registry) as con:
        con.execute('CREATE TABLE knowledge_documents(id,path_key,content_hash,mime_type)')
        con.execute('INSERT INTO knowledge_documents VALUES(?,?,?,?)', ('fixture-source', 'slides/lecture.pdf', hashlib.sha256(raw).hexdigest(), 'application/pdf'))
    before = registry.read_bytes()
    loader = RegisteredSources(registry, {'slides': root})
    assert loader('fixture-source') == raw
    assert registry.read_bytes() == before and original.read_bytes() == raw
    original.rename(root / 'actual.pdf'); original.symlink_to(root / 'actual.pdf')
    with pytest.raises(PackageError): loader('fixture-source')


def test_invalid_post_missing_database_does_not_create_state(tmp_path):
    studio = LearningStudioService(tmp_path / 'learning_studio.sqlite3', source_loader=lambda _: source_pdf(), catalogue_loader=catalogue)
    with pytest.raises(PackageError): studio.attempt('missing', event(package()))
    assert not studio.store.path.exists()
    with pytest.raises(PackageError): studio.publish('missing', 1)
    assert not studio.store.path.exists()


def test_mapping_removed_after_stage_prevents_publish(tmp_path):
    studio = LearningStudioService(tmp_path / 'learning_studio.sqlite3', source_loader=lambda _: source_pdf(), catalogue_loader=catalogue)
    studio.stage(package(mapped=True))
    studio.catalogue_loader = lambda: {'available': True, 'courses': []}
    with pytest.raises(PackageError): studio.publish('synthetic', 1)
    assert studio.library()['modules'] == []


def test_concurrent_idempotent_events_single_append(tmp_path):
    studio = LearningStudioService(tmp_path / 'learning_studio.sqlite3', source_loader=lambda _: source_pdf(), catalogue_loader=catalogue)
    p = publish(studio)
    errors = []
    def submit():
        try: studio.attempt('synthetic', event(p))
        except Exception as error: errors.append(error)
    threads = [threading.Thread(target=submit) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert not errors and studio.evidence()['attempts'] == 1


def test_unsupported_critical_integrity_fields_and_bad_block_refs(tmp_path):
    studio = LearningStudioService(tmp_path / 'learning_studio.sqlite3', source_loader=lambda _: source_pdf(), catalogue_loader=catalogue)
    p = package(); p['source']['integrity_failure'] = True
    with pytest.raises(PackageError): studio.stage(p)
    p = package(); p['sections'][0]['blocks'][0]['pages'] = [99]
    with pytest.raises(PackageError): studio.stage(p)


def test_markdown_active_html_links_images_never_execute():
    from personal_learning_assistant.learning_studio.rendering import markdown
    html = str(markdown('<script>danger()</script> [link](javascript:alert(1)) ![remote](https://evil.test/x.png)'))
    assert '<script>' not in html and '<img' not in html and 'href=' not in html


def test_removed_question_cannot_reuse_historical_revision(tmp_path):
    studio = LearningStudioService(tmp_path / 'learning_studio.sqlite3', source_loader=lambda _: source_pdf(), catalogue_loader=catalogue)
    p = publish(studio)
    removed = copy.deepcopy(p); removed['module_revision'] = 2; removed['questions'] = []
    publish(studio, removed)
    reused = copy.deepcopy(p); reused['module_revision'] = 3; reused['questions'][0]['correct_index'] = 0
    with pytest.raises(PackageError): studio.stage(reused)


@pytest.mark.parametrize('change', ['pages-object', 'options-object', 'kind-object'])
def test_malformed_json_types_are_validation_errors(tmp_path, change):
    studio = LearningStudioService(tmp_path / 'learning_studio.sqlite3', source_loader=lambda _: source_pdf(), catalogue_loader=catalogue)
    p = package()
    if change == 'pages-object': p['sections'][0]['pages'] = [{}]
    if change == 'options-object': p['questions'][0]['options'] = [{}, 'Correct']
    if change == 'kind-object': p['sections'][0]['blocks'][0]['kind'] = {}
    with pytest.raises(PackageError): studio.stage(p)
    assert not studio.store.path.exists()


def test_source_missing_between_preview_and_publish_safe_error(tmp_path):
    studio = LearningStudioService(tmp_path / 'learning_studio.sqlite3', source_loader=lambda _: source_pdf(), catalogue_loader=catalogue)
    studio.stage(package())
    def unavailable(_): raise RuntimeError('private path/provider details')
    studio.source_loader = unavailable
    with pytest.raises(PackageError, match='unavailable') as exc: studio.publish('synthetic', 1)
    assert exc.value.status == 503
    assert studio.library()['unmapped_count'] == 0


@pytest.mark.parametrize('field', ['status', 'preview', 'difficulty'])
def test_unhashable_fidelity_fields_are_rejected(tmp_path, field):
    studio = LearningStudioService(tmp_path / 'learning_studio.sqlite3', source_loader=lambda _: source_pdf(), catalogue_loader=catalogue)
    p = package()
    if field == 'difficulty': p['questions'][0][field] = {}
    else: p['pages'][0][field] = {}
    with pytest.raises(PackageError): studio.stage(p)
    assert not studio.store.path.exists()
