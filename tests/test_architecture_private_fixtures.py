"""Synthetic harness-policy tests; these never certify the two external originals."""
import hashlib
import io
import json
import os
from pathlib import Path, PureWindowsPath
import zipfile

import pytest

from scripts import architecture_validation as harness


def policy():
    from scripts import architecture_private_fixtures
    return architecture_private_fixtures


def synthetic_pair(tmp_path, monkeypatch):
    module = policy()
    pdf = b'%PDF synthetic harness unit source'
    digest = hashlib.sha256(pdf).hexdigest()
    image = b'synthetic preview'
    text = 'Synthetic source'
    proposed = {'schema': 'anvaya.learning-module.v1', 'source_sha256': digest,
        'source_page_count': 20, 'title': 'Synthetic harness unit',
        'source_original_filename': 'synthetic.pdf',
        'revision': {'markdown': 'Synthetic recall', 'source_pages': [1]},
        'lessons': [{'page': p, 'title': f'Page {p}', 'image_file': f'assets/p{p}.webp',
            'image_sha256': hashlib.sha256(image).hexdigest(), 'source_text': text,
            'source_text_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'notes': 'Synthetic notes', 'points': ['Synthetic point'], 'activity': 'Recall'}
            for p in range(1, 21)],
        'questions': [{'id': n, 'question': 'Synthetic?', 'page': 1,
            'source_ref': {'document_sha256': digest, 'page': 1},
            'options': ['A', 'B'], 'answer': 0, 'explanation': 'Synthetic'} for n in range(1, 32)]}
    specs, paths = {}, {}
    for name, original in module.FIXTURES.items():
        buf = io.BytesIO()
        actual_pdf = pdf if name == 'recovered' else b'%PDF intentionally mismatched unit source'
        with zipfile.ZipFile(buf, 'w') as archive:
            archive.writestr('ORIGINAL_20_Page_Presentation.pdf', actual_pdf)
            archive.writestr('ANVAYA_Learning_Module_Proposed_v1.json', json.dumps(proposed))
            archive.writestr('Source_Fidelity_Coverage_Report.json', json.dumps({'original_source_sha256': digest}))
            for lesson in proposed['lessons']:
                archive.writestr(lesson['image_file'], image)
        raw = buf.getvalue()
        path = tmp_path / (name + '.zip')
        path.write_bytes(raw)
        specs[name] = {**original, 'sha256': hashlib.sha256(raw).hexdigest(),
            'pdf_sha256': hashlib.sha256(actual_pdf).hexdigest(), 'claimed_sha256': digest, 'size': len(raw)}
        paths[original['environment']] = str(path)
    monkeypatch.setattr(module, 'FIXTURES', specs)
    return module, paths


def test_explicit_authorized_pair_survives_environment_without_credentials(tmp_path, monkeypatch):
    module, paths = synthetic_pair(tmp_path, monkeypatch)
    for name, path in paths.items(): monkeypatch.setenv(name, path)
    monkeypatch.setenv('OPENAI_API_KEY', 'never-copy-this')
    monkeypatch.setenv('ANVAYA_OTHER_SECRET', 'never-copy-this')
    env = harness.clean_environment(tmp_path / 'artifacts', harness.ROOT, allow_private_fixtures=True)
    assert all(env[name] == str(Path(path).resolve()) for name, path in paths.items())
    assert 'OPENAI_API_KEY' not in env and 'ANVAYA_OTHER_SECRET' not in env
    default = harness.clean_environment(tmp_path / 'artifacts', harness.ROOT)
    assert all(name not in default for name in paths)
    assert module.validate_pair(paths, repo=harness.ROOT, output=tmp_path / 'artifacts')['recovered']['present']


@pytest.mark.parametrize('problem', ['missing', 'swapped', 'wrong_hash', 'directory', 'inside_repo', 'inside_output', 'hardlink'])
def test_unsafe_fixture_pair_fails_closed_without_disclosing_paths(tmp_path, monkeypatch, problem):
    module, paths = synthetic_pair(tmp_path, monkeypatch)
    good, bad = [spec['environment'] for spec in module.FIXTURES.values()]
    repo = tmp_path / 'repo'; repo.mkdir()
    output = tmp_path / 'output'; output.mkdir()
    if problem == 'missing': paths.pop(bad)
    elif problem == 'swapped': paths[good], paths[bad] = paths[bad], paths[good]
    elif problem == 'wrong_hash': Path(paths[good]).write_bytes(b'wrong')
    elif problem == 'directory': paths[good] = str(tmp_path)
    elif problem in {'inside_repo', 'inside_output'}:
        path = (repo if problem == 'inside_repo' else output) / 'private.zip'
        path.write_bytes(Path(paths[good]).read_bytes()); paths[good] = str(path)
    else:
        alias = tmp_path / 'alias.zip'; os.link(paths[good], alias)
    with pytest.raises(module.FixtureError) as caught:
        module.validate_pair(paths, repo=repo, output=output)
    assert str(tmp_path) not in str(caught.value)


def test_symlink_and_parent_symlink_are_refused(tmp_path, monkeypatch):
    module, paths = synthetic_pair(tmp_path, monkeypatch)
    key = next(iter(paths)); original = paths[key]
    link = tmp_path / 'link.zip'
    try: link.symlink_to(original)
    except OSError:
        pytest.skip('Host lacks symlink privilege; this boundary was not exercised.')
    paths[key] = str(link)
    with pytest.raises(module.FixtureError): module.validate_pair(paths, repo=harness.ROOT, output=tmp_path / 'out')
    directory = tmp_path / 'alias'
    directory.symlink_to(tmp_path, target_is_directory=True)
    paths[key] = str(directory / Path(original).name)
    with pytest.raises(module.FixtureError): module.validate_pair(paths, repo=harness.ROOT, output=tmp_path / 'out')


@pytest.mark.parametrize('value', ['C:relative.zip', r'\\server\private\source.zip', r'\\?\C:\private\source.zip', 'relative.zip', 'C:\\private\\bad\nname.zip'])
def test_windows_path_lexical_policy_rejects_ambiguous_or_network_paths(value):
    with pytest.raises(policy().FixtureError): policy().check_path_syntax(value, windows=True)


def test_windows_absolute_drive_path_does_not_use_posix_parsing():
    value = r'C:\private folder\source.zip'
    assert policy().check_path_syntax(value, windows=True) == PureWindowsPath(value)


def test_private_fixture_paths_and_shell_payloads_are_redacted_from_logs_xml_and_commands(tmp_path, monkeypatch):
    module, paths = synthetic_pair(tmp_path, monkeypatch)
    for name, path in paths.items(): monkeypatch.setenv(name, path)
    env = harness.clean_environment(tmp_path / 'artifacts', harness.ROOT, allow_private_fixtures=True)
    import sys
    result = harness.run_command('private', [sys.executable, '-c',
        'import os; print(os.environ["ANVAYA_TEST_RECOVERED_PILOT_ZIP"])'],
        tmp_path, tmp_path, env)
    log = (tmp_path / 'private.log').read_text()
    assert 'stdout withheld' in log and paths[next(iter(paths))] not in log
    assert str(tmp_path / 'recovered.zip') not in json.dumps(result)


def test_manifest_is_checked_even_for_a_pinned_zip(tmp_path, monkeypatch):
    module, paths = synthetic_pair(tmp_path, monkeypatch)
    spec = module.FIXTURES['recovered']; path = Path(paths[spec['environment']])
    # Pin a malformed synthetic fixture to prove manifest validation is independent
    # of the checksum test. This does not change production's pinned originals.
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, 'w') as archive:
        archive.writestr('ORIGINAL_20_Page_Presentation.pdf', b'%PDF synthetic harness unit source')
    path.write_bytes(raw.getvalue())
    spec.update(sha256=hashlib.sha256(raw.getvalue()).hexdigest(), size=len(raw.getvalue()))
    with pytest.raises(module.FixtureError, match='manifest'):
        module.validate_pair(paths, repo=harness.ROOT, output=tmp_path / 'out')


def test_private_mode_never_exports_learning_source_screenshots(tmp_path, monkeypatch):
    _, paths = synthetic_pair(tmp_path, monkeypatch)
    for name, path in paths.items(): monkeypatch.setenv(name, path)
    env = harness.clean_environment(tmp_path / 'out', harness.ROOT, allow_private_fixtures=True)
    assert 'ANVAYA_BROWSER_ARTIFACTS' not in env
    assert 'ANVAYA_VALIDATION_ARTIFACTS' in env  # separate synthetic architecture journeys


def test_private_failure_junit_retains_outcome_but_omits_payload(tmp_path, monkeypatch):
    _, paths = synthetic_pair(tmp_path, monkeypatch)
    for name, path in paths.items(): monkeypatch.setenv(name, path)
    env = harness.clean_environment(tmp_path / 'out', harness.ROOT, allow_private_fixtures=True)
    import sys
    xml = tmp_path / 'private.xml'
    code = ('from pathlib import Path; import sys; '
        'Path(sys.argv[1]).write_text(\'<testsuites><testsuite><testcase name="private-test" classname="fixture">'
        '<failure message="PRIVATE ANSWER">PRIVATE SOURCE</failure>'
        '<system-out>PRIVATE SLIDE</system-out></testcase></testsuite></testsuites>\'); '
        'print("PRIVATE PAYLOAD"); sys.exit(1)')
    result = harness.run_command('private-failure', [sys.executable, '-c', code, str(xml)], tmp_path, tmp_path, env, xml=xml)
    assert result['status'] == 'FAIL'
    assert result['failures'][0]['id'] == 'private_validation::case-000001'
    assert 'PRIVATE' not in xml.read_text() and 'PRIVATE' not in (tmp_path / 'private-failure.log').read_text()
    # Reproduction argv can contain source supplied by a caller. The validator
    # only uses fixed synthetic argv; a private run must publish no raw argv.
    assert 'PRIVATE ANSWER' not in json.dumps(result)


def test_malformed_private_xml_never_leaves_raw_public_diagnostics(tmp_path, monkeypatch):
    _, paths = synthetic_pair(tmp_path, monkeypatch)
    for name, path in paths.items(): monkeypatch.setenv(name, path)
    env = harness.clean_environment(tmp_path / 'out', harness.ROOT, allow_private_fixtures=True)
    import sys
    xml = tmp_path / 'broken.xml'
    code = 'from pathlib import Path; import sys; Path(sys.argv[1]).write_bytes(b"PRIVATE SOURCE <invalid"); print("PRIVATE PAYLOAD")'
    try:
        result = harness.run_command('broken', [sys.executable, '-c', code, str(xml)], tmp_path, tmp_path, env, xml=xml)
    except Exception:
        result = {'status': 'FAIL'}
    assert result['status'] == 'FAIL'
    assert all(b'PRIVATE' not in path.read_bytes() for path in tmp_path.glob('*.log'))
    assert not xml.exists() or b'PRIVATE' not in xml.read_bytes()


def test_private_staging_copies_verified_bytes_outside_artifacts_and_cleans_up(tmp_path, monkeypatch):
    module, paths = synthetic_pair(tmp_path, monkeypatch)
    staged = module.PrivateFixtureStage(paths, repo=harness.ROOT, output=tmp_path / 'out')
    private_root = Path(staged.directory.name)
    try:
        assert not private_root.is_relative_to(tmp_path / 'out')
        for key, path in staged.environment.items():
            assert Path(path).read_bytes() == Path(paths[key]).read_bytes()
            assert Path(path).resolve() != Path(paths[key]).resolve()
        assert all('path' not in item for item in staged.manifest.values())
    finally:
        staged.close()
    assert not private_root.exists()


def test_unsafe_default_temp_directory_is_rejected_before_private_bytes_written(tmp_path, monkeypatch):
    module, paths = synthetic_pair(tmp_path, monkeypatch)
    import tempfile
    output = tmp_path / 'artifacts'; output.mkdir()
    monkeypatch.setattr(tempfile, 'tempdir', str(output))
    writes = []
    write_bytes = Path.write_bytes
    def tracked_write(path, raw):
        if path.is_relative_to(output): writes.append(path)
        return write_bytes(path, raw)
    monkeypatch.setattr(Path, 'write_bytes', tracked_write)
    with pytest.raises(module.FixtureError):
        module.PrivateFixtureStage(paths, repo=harness.ROOT, output=output)
    assert not list(output.rglob('*.zip'))
    assert not writes


def test_unknown_junit_identity_cannot_disclose_source_payload(tmp_path, monkeypatch):
    _, paths = synthetic_pair(tmp_path, monkeypatch)
    for name, path in paths.items(): monkeypatch.setenv(name, path)
    env = harness.clean_environment(tmp_path / 'out', harness.ROOT, allow_private_fixtures=True)
    import sys
    xml = tmp_path / 'safe.xml'
    code = 'from pathlib import Path; import sys; Path(sys.argv[1]).write_text(\'<testsuites><testsuite><testcase name="PRIVATE PAYLOAD" classname="PRIVATE SOURCE"/></testsuite></testsuites>\')'
    result = harness.run_command('unknown', [sys.executable, '-c', code, str(xml)], tmp_path, tmp_path, env, xml=xml)
    assert result['status'] == 'PASS'
    assert 'PRIVATE' not in xml.read_text() and 'PRIVATE' not in json.dumps(result)


def test_hardlink_added_between_stat_and_open_is_refused(tmp_path, monkeypatch):
    module, paths = synthetic_pair(tmp_path, monkeypatch)
    path = Path(paths[module.FIXTURES['recovered']['environment']])
    original = os.open
    def changed_open(name, flags, *args, **kwargs):
        if Path(name) == path: os.link(path, tmp_path / 'racing-alias.zip')
        return original(name, flags, *args, **kwargs)
    monkeypatch.setattr(os, 'open', changed_open)
    with pytest.raises(module.FixtureError, match='changed'):
        module.validate_pair(paths, repo=harness.ROOT, output=tmp_path / 'out')


def test_four_original_outcomes_are_individual_and_cannot_be_replaced_by_other_passes(tmp_path):
    import xml.etree.ElementTree as ET
    root = ET.Element('testsuites'); suite = ET.SubElement(root, 'testsuite')
    for classname, name in harness.EXTERNAL_TEST_IDS:
        ET.SubElement(suite, 'testcase', classname=classname, name=name)
    xml = tmp_path / 'outcomes.xml'
    ET.ElementTree(root).write(xml)
    result = harness.external_pilot_acceptance(xml)
    assert result['status'] == 'PASS' and len(result['outcomes']) == 4
    suite.remove(list(suite)[0])
    ET.SubElement(suite, 'testcase', classname='synthetic', name='replacement')
    ET.ElementTree(root).write(xml)
    result = harness.external_pilot_acceptance(xml)
    assert result['status'] == 'BLOCKED' and 'NOT_RUN' in result['outcomes'].values()


def test_staging_os_failure_never_exposes_private_path(tmp_path, monkeypatch):
    module, paths = synthetic_pair(tmp_path, monkeypatch)
    def failed_write(path, raw):
        raise OSError(28, 'Synthetic disk full', 'SENSITIVE_PRIVATE_PATH')
    monkeypatch.setattr(Path, 'write_bytes', failed_write)
    with pytest.raises(module.FixtureError) as caught:
        module.PrivateFixtureStage(paths, repo=harness.ROOT, output=tmp_path / 'out')
    assert 'SENSITIVE_PRIVATE_PATH' not in str(caught.value)
