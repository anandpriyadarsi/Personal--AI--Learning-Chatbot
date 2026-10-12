import copy
import sqlite3
import pytest
from .helpers import source_pdf, package, catalogue
from personal_learning_assistant.learning_studio.service import LearningStudioService
from personal_learning_assistant.learning_studio.validation import PackageError


@pytest.fixture
def studio(tmp_path):
    raw = source_pdf()
    return LearningStudioService(tmp_path / 'learning_studio.sqlite3',
        source_loader=lambda identity: raw if identity == 'fixture-source' else None,
        catalogue_loader=catalogue)


def publish(studio, p=None):
    p = p or package()
    studio.stage(p)
    studio.publish(p['module_id'], p['module_revision'])
    return p


def event(p, event_id='event-1', selection=0):
    return dict(event_id=event_id, module_revision=p['module_revision'],
                source_sha256=p['source']['sha256'], question_id='q1',
                question_revision=1, selection=selection, is_correct=True)


def test_empty_reads_are_pure(studio):
    assert studio.library()['modules'] == []
    assert studio.evidence()['attempts'] == 0
    assert not studio.store.path.exists()


def test_stage_publish_source_and_public_keys(studio):
    p = package()
    studio.stage(p)
    assert studio.library()['modules'] == []
    assert studio.module('synthetic', 1, staged=True)['title'] == p['title']
    studio.publish('synthetic', 1)
    public = studio.module('synthetic', 1)
    assert 'correct_index' not in public['questions'][0]
    assert 'explanation' not in public['questions'][0]
    assert studio.source('synthetic', 1) == source_pdf()


def test_wrong_correct_reopen_and_idempotency(studio):
    p = publish(studio)
    assert studio.attempt('synthetic', event(p))['correct'] is False
    assert studio.attempt('synthetic', event(p))['attempt_number'] == 1
    with pytest.raises(PackageError):
        studio.attempt('synthetic', event(p, selection=1))
    result = studio.attempt('synthetic', event(p, 'event-2', 1))
    assert result['correct'] and result['attempt_number'] == 2
    reopened = LearningStudioService(studio.store.path, source_loader=studio.source_loader,
                                    catalogue_loader=catalogue)
    weak = reopened.weak('synthetic', 1)
    assert len(weak) == 1 and weak[0]['status'] == 'recovered_needs_recheck'
    assert weak[0]['incorrect_count'] == 1
    assert reopened.evidence()['ever_missed'] == 1
    with studio.store.connection(write=True) as con:
        assert con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not con.execute('PRAGMA foreign_key_check').fetchall()
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('DELETE FROM attempts')


@pytest.mark.parametrize('change', ['schema', 'hash', 'page', 'duplicate', 'key', 'mapping', 'raw_html', 'extra'])
def test_invalid_packages_no_partial_writes(studio, change):
    p = package()
    if change == 'schema': p['schema'] = 'bad'
    if change == 'hash': p['source']['sha256'] = '0' * 64
    if change == 'page': p['sections'][0]['pages'] = [99]
    if change == 'duplicate': p['questions'].append(copy.deepcopy(p['questions'][0]))
    if change == 'key': p['questions'][0]['correct_index'] = 99
    if change == 'mapping': p['mapping'] = {'course_id': 'invented', 'topic_name': 'Fake', 'reviewed': True, 'confidence': 1}
    if change == 'raw_html': p['sections'][0]['blocks'][0]['text'] = '<script>alert(1)</script>'
    if change == 'extra': p['questions'][0]['script'] = 'unsafe'
    with pytest.raises(PackageError): studio.stage(p)
    assert not studio.store.path.exists()


@pytest.mark.parametrize('change', ['revision', 'hash', 'question', 'question_revision', 'selection', 'owner'])
def test_attempt_context_fails_closed(studio, change):
    p = publish(studio)
    e = event(p)
    if change == 'revision': e['module_revision'] = 99
    if change == 'hash': e['source_sha256'] = 'f' * 64
    if change == 'question': e['question_id'] = 'foreign'
    if change == 'question_revision': e['question_revision'] = 9
    if change == 'selection': e['selection'] = True
    if change == 'owner': e['learner_id'] = 'foreign'
    with pytest.raises(PackageError): studio.attempt('synthetic', e)
    assert studio.evidence()['attempts'] == 0


def test_revisions_immutable_and_historical_grading(studio):
    p = publish(studio)
    changed = copy.deepcopy(p); changed['title'] = 'Changed'
    with pytest.raises(PackageError): studio.stage(changed)
    new = copy.deepcopy(p); new['module_revision'] = 2
    new['questions'][0]['revision'] = 2; new['questions'][0]['correct_index'] = 0
    publish(studio, new)
    assert studio.module('synthetic', 1)['title'] == p['title']
    assert studio.attempt('synthetic', event(p, selection=1))['correct']
    assert studio.library(course_id='unmapped')['modules'][0]['revision'] == 2


def test_source_change_between_stage_and_publish(studio):
    studio.stage(package())
    studio.source_loader = lambda identity: source_pdf(3)
    with pytest.raises(PackageError): studio.publish('synthetic', 1)
    assert studio.library()['modules'] == []


def test_seventy_two_modules_group_and_paginate(studio):
    for c in range(6):
        for j in range(12):
            p = package(module_id=f'm{c}-{j}', mapped=True)
            p['mapping'].update(course_id=f'c{c}', topic_id=f't{c}')
            publish(studio, p)
    landing = studio.library()
    assert len(landing['courses']) == 6
    assert all(c['module_count'] == 12 for c in landing['courses'])
    assert landing['modules'] == []
    course = studio.library(course_id='c2', limit=5)
    assert len(course['modules']) == 5 and course['total'] == 12
    assert studio.library(course_id='c2', search='nonexistent')['total'] == 0


def test_wrong_database_and_symlink_fail_without_changes(tmp_path):
    protected = tmp_path / 'learning_assistant.db'
    con = sqlite3.connect(protected); con.execute('CREATE TABLE academic(x)'); con.close()
    before = protected.read_bytes()
    service = LearningStudioService(protected, source_loader=lambda _: source_pdf(), catalogue_loader=catalogue)
    with pytest.raises(PackageError): service.stage(package())
    assert protected.read_bytes() == before
    link = tmp_path / 'learning_studio.sqlite3'
    link.symlink_to(protected)
    service = LearningStudioService(link, source_loader=lambda _: source_pdf(), catalogue_loader=catalogue)
    with pytest.raises(PackageError): service.stage(package())
