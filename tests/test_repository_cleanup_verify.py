"""Cleanup audits retain historical bytes while excluding accepted upstream work."""
import subprocess

import pytest

from scripts import repository_cleanup_verify as audit


def test_cleanup_delta_uses_recorded_integration_base(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(tmp_path), *args], text=True).strip()
    git('init')
    git('config', 'user.name', 'Synthetic Test')
    git('config', 'user.email', 'synthetic@example.invalid')
    (tmp_path / 'runtime.py').write_text('accepted = 1\n')
    git('add', '.')
    git('commit', '-m', 'historical baseline')
    historical = git('rev-parse', 'HEAD')
    (tmp_path / 'runtime.py').write_text('accepted = 2\n')
    git('add', '.')
    git('commit', '-m', 'accepted upstream runtime')
    integration = git('rev-parse', 'HEAD')
    (tmp_path / 'report.md').write_text('Archived report\n')
    git('add', '.')
    git('commit', '-m', 'cleanup only')
    monkeypatch.setattr(audit, 'ROOT', tmp_path)
    monkeypatch.setattr(audit, 'BASE_SHA', historical)
    assert audit.integration_changes({'integration_base_sha': integration}) == ['report.md']


def test_forwarding_document_preserves_exact_archive_destination():
    record = {'original': 'ANVAYA_HISTORY.md',
              'archive': 'docs/archive/learning/ANVAYA_HISTORY.md'}
    valid = '# Archived document\n\n[Read the preserved original](docs/archive/learning/ANVAYA_HISTORY.md).\n'
    audit.verify_forwarding_document(record, valid)
    with pytest.raises(AssertionError):
        audit.verify_forwarding_document(record, valid.replace('learning/', 'other/'))
    with pytest.raises(AssertionError):
        audit.verify_forwarding_document(record, '')
