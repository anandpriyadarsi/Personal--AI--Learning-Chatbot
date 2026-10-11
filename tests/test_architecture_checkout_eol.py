import importlib.util
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def module():
    path = ROOT / 'scripts/architecture_checkout_eol.py'
    assert path.exists(), 'Checked historical EOL preparation is missing'
    spec = importlib.util.spec_from_file_location('checkout_eol', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def source(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    git(repo, 'init')
    git(repo, 'config', 'core.autocrlf', 'false')
    for name in ('backup.py', 'dashboard.py'):
        (repo / name).write_bytes(b'VALUE = 1\r\n')
    git(repo, 'add', 'backup.py', 'dashboard.py')
    git(repo, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'Historical CRLF blobs')
    (repo / '.gitattributes').write_text('*.py text eol=lf\n', encoding='utf-8')
    git(repo, 'add', '.gitattributes')
    git(repo, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'Later LF attribute')
    (repo / 'backup.py').write_bytes(b'VALUE = 1\n')
    assert git(repo, 'status', '--porcelain')
    return repo


def test_only_historical_eol_differences_are_restored_and_repeat_is_idempotent(tmp_path):
    repo = source(tmp_path)
    head = git(repo, 'rev-parse', 'HEAD')
    result = module().prepare_clean_checkout(repo)
    assert result['working_tree_clean']
    assert git(repo, 'status', '--porcelain', '-uall') == ''
    assert git(repo, 'rev-parse', 'HEAD') == head
    assert (repo / 'backup.py').read_bytes() == b'VALUE = 1\r\n'
    attributes = (repo / '.git/info/attributes').read_bytes()
    module().prepare_clean_checkout(repo)
    assert (repo / '.git/info/attributes').read_bytes() == attributes


def test_substantive_change_is_refused_before_any_eol_or_metadata_write(tmp_path):
    repo = source(tmp_path)
    (repo / 'dashboard.py').write_bytes(b'VALUE = 99\n')
    before = {n: (repo / n).read_bytes() for n in ('backup.py', 'dashboard.py')}
    with pytest.raises(ValueError, match='substantive'):
        module().prepare_clean_checkout(repo)
    assert {n: (repo / n).read_bytes() for n in before} == before
    assert not (repo / '.git/info/attributes').exists()


def test_unrelated_dirty_work_is_refused_and_preserved(tmp_path):
    repo = source(tmp_path)
    private = repo / 'unrelated.txt'
    private.write_text('preserve this work', encoding='utf-8')
    with pytest.raises(ValueError, match='unrelated'):
        module().prepare_clean_checkout(repo)
    assert private.read_text() == 'preserve this work'
    assert not (repo / '.git/info/attributes').exists()
