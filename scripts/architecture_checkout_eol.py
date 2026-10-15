"""Prepare a pristine CI checkout with two historical CRLF Git blobs.

Only exact EOL-equivalent backup.py/dashboard.py may be restored to HEAD bytes.
No substantive/staged/unrelated changes are accepted. No academic paths read.
Local Git attributes preserve the historical blobs; tracked source is unchanged.
"""
import argparse
import json
from pathlib import Path
import subprocess


HISTORICAL = ('backup.py', 'dashboard.py')
ATTRIBUTES = 'backup.py -text\ndashboard.py -text\n'


def _git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def prepare_clean_checkout(repo: Path) -> dict:
    requested = repo.absolute()
    if any(p.is_symlink() for p in (requested, *requested.parents)):
        raise ValueError('Unsafe checkout path')
    repo = requested.resolve()
    if Path(_git(repo, 'rev-parse', '--show-toplevel').decode().strip()).resolve() != repo:
        raise ValueError('Exact Git checkout root required')
    status = _git(repo, 'status', '--porcelain=v1', '-uall').decode().splitlines()
    if any(line[:2] != ' M' or line[3:] not in HISTORICAL for line in status):
        raise ValueError('Refusing staged or unrelated dirty work')
    contents = {}
    for name in HISTORICAL:
        path = repo / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Historical source file absent or unsafe')
        expected = _git(repo, 'show', 'HEAD:' + name)
        actual = path.read_bytes()
        if actual.replace(b'\r\n', b'\n') != expected.replace(b'\r\n', b'\n'):
            raise ValueError('Refusing substantive historical source change')
        contents[name] = expected
    attributes = Path(_git(repo, 'rev-parse', '--git-path', 'info/attributes').decode().strip())
    if not attributes.is_absolute():
        attributes = repo / attributes
    if any(p.is_symlink() for p in (attributes, *attributes.parents)) or (attributes.exists() and not attributes.is_file()):
        raise ValueError('Unsafe Git attributes path')
    previous = attributes.read_text(encoding='utf-8') if attributes.exists() else ''
    # All source/status/path checks finish before any write. Preserve other
    # attributes, append only the two exact overrides, and retain idempotency.
    if not previous.endswith(ATTRIBUTES):
        attributes.parent.mkdir(parents=True, exist_ok=True)
        attributes.write_text(previous.rstrip('\n') + '\n' + ATTRIBUTES, encoding='utf-8')
    for name, expected in contents.items():
        path = repo / name
        if path.read_bytes() != expected:
            path.write_bytes(expected)
    if _git(repo, 'status', '--porcelain=v1', '-uall').strip():
        raise ValueError('Checkout is not clean after checked EOL preparation')
    return {'working_tree_clean': True, 'preserved_head': _git(repo, 'rev-parse', 'HEAD').decode().strip(),
            'allowed_historical_files': list(HISTORICAL), 'no_substantive_source_change': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare_clean_checkout(args.repo), indent=2))
