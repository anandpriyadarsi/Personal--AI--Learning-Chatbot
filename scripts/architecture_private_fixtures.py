"""Pinned private IKS test inputs. No extraction, imports, credentials or transport.

Trusted runners provision the unchanged originals outside every checkout and
artifact directory. Only an explicit validator flag enables their path variables.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import stat
import sys
import tempfile


class FixtureError(ValueError):
    """A deliberately path/payload-free fixture-policy error."""


FIXTURES = {
    'recovered': {
        'environment': 'ANVAYA_TEST_RECOVERED_PILOT_ZIP', 'size': 2880076,
        'sha256': 'e26d03de4a300dda0186ee005745d98afa41f0a23d12d6612965079e995f6923',
        'pdf_sha256': '75cd41956da56018967fea70ae5829803a9b54effa827e25883ac184bffcf411',
        'claimed_sha256': '75cd41956da56018967fea70ae5829803a9b54effa827e25883ac184bffcf411',
    },
    'bad_v3': {
        'environment': 'ANVAYA_TEST_BAD_V3_ZIP', 'size': 2891010,
        'sha256': 'a49c7fcd16f129ccf62a3260fd0a914be3b278b32ee460cf8833bbdf531e9cdd',
        'pdf_sha256': 'f812fb27240fc5cd5265a1608f80ac480f241b56f9b27d4826bb6453b319735b',
        'claimed_sha256': '75cd41956da56018967fea70ae5829803a9b54effa827e25883ac184bffcf411',
    },
}


def check_path_syntax(value: str, *, windows: bool | None = None):
    windows = os.name == 'nt' if windows is None else windows
    if not isinstance(value, str) or not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise FixtureError('Private fixture path has invalid characters')
    path = PureWindowsPath(value) if windows else PurePosixPath(value)
    if not path.is_absolute() or '..' in path.parts:
        raise FixtureError('Private fixture requires an absolute local path')
    if windows:
        if len(path.drive) != 2 or path.drive[1] != ':' or ':' in str(path)[2:]:
            raise FixtureError('Private fixture network/device paths are forbidden')
    elif '\\' in value or ':' in value:
        raise FixtureError('Private fixture path uses a foreign path syntax')
    return path


def _read_private(value: str, *, repo: Path, output: Path, label: str, spec: dict) -> tuple[Path, bytes]:
    check_path_syntax(value)
    path = Path(value)
    try:
        # Reject parents too: resolve() alone would silently accept an alias.
        for item in (path, *path.parents):
            if item.is_symlink() or getattr(item, 'is_junction', lambda: False)():
                raise FixtureError(label + ': symlink/junction fixture paths are forbidden')
        canonical = path.resolve(strict=True)
        for root in (repo.resolve(), output.resolve()):
            if canonical == root or canonical.is_relative_to(root):
                raise FixtureError(label + ': fixtures must be outside source and artifacts')
        if any((parent / '.git').is_file() or (parent / '.git/HEAD').is_file() for parent in canonical.parents):
            raise FixtureError(label + ': fixtures must be outside Git checkouts')
        info = canonical.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != spec['size']:
            raise FixtureError(label + ': fixture type/size/link policy failed')
        flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
        with os.fdopen(os.open(canonical, flags), 'rb') as stream:
            opened = os.fstat(stream.fileno())
            if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                    or (opened.st_dev, opened.st_ino, opened.st_size) != (info.st_dev, info.st_ino, info.st_size)):
                raise FixtureError(label + ': fixture changed during validation')
            raw = stream.read(spec['size'] + 1)
            after = os.fstat(stream.fileno())
            if (after.st_nlink != 1 or after.st_size != opened.st_size
                    or after.st_mtime_ns != opened.st_mtime_ns):
                raise FixtureError(label + ': fixture changed during validation')
        if len(raw) != spec['size'] or hashlib.sha256(raw).hexdigest() != spec['sha256']:
            raise FixtureError(label + ': fixture checksum mismatch')
        return canonical, raw
    except FixtureError:
        raise
    except (OSError, ValueError):
        raise FixtureError(label + ': private fixture unavailable') from None


def _check_manifest(raw: bytes, label: str, spec: dict) -> None:
    from personal_learning_assistant.learning_studio.archive import decode_json, read_zip
    from personal_learning_assistant.learning_studio.pilot import convert_pilot
    from personal_learning_assistant.learning_studio.validation import PackageError

    def require(condition):
        if not condition:
            raise ValueError('Invalid manifest')

    try:
        files = read_zip(raw, pilot=True)  # bounded member sizes, CRC, paths and compression
        proposed = decode_json(files['ANVAYA_Learning_Module_Proposed_v1.json'])
        report = decode_json(files['Source_Fidelity_Coverage_Report.json'])
        require(hashlib.sha256(files['ORIGINAL_20_Page_Presentation.pdf']).hexdigest() == spec['pdf_sha256'])
        require(proposed['schema'] == 'anvaya.learning-module.v1')
        require(proposed['source_sha256'] == report['original_source_sha256'] == spec['claimed_sha256'])
        require(proposed['source_page_count'] == 20 and len(proposed['lessons']) == 20)
        require({lesson['page'] for lesson in proposed['lessons']} == set(range(1, 21)))
        require(len({lesson['image_file'] for lesson in proposed['lessons']}) == 20)
        require(len(proposed['questions']) == 31)
        for lesson in proposed['lessons']:
            require(hashlib.sha256(files[lesson['image_file']]).hexdigest() == lesson['image_sha256'])
            require(hashlib.sha256(lesson['source_text'].encode()).hexdigest() == lesson['source_text_sha256'])
        if label == 'recovered':
            package, _, assets = convert_pilot(raw)
            require(package['mapping'] is None and len(assets) == 20 and len(package['questions']) == 31)
        else:
            require(spec['pdf_sha256'] != spec['claimed_sha256'])
            try:
                convert_pilot(raw)
            except PackageError as error:
                require(str(error) == 'Pilot source hash mismatch.')
            else:
                raise AssertionError('Historic invalid archive was accepted')
    except (AssertionError, KeyError, TypeError, ValueError, PackageError):
        raise FixtureError(label + ': fixture manifest validation failed') from None


def validate_pair(environment: dict, *, repo: Path, output: Path) -> dict:
    """Return validated native paths and a separate public checksum manifest.

    Both roles are mandatory. Neither filename nor a user-supplied hash grants
    authority; only the two pinned unchanged originals pass production policy.
    """
    if sys.version_info < (3, 12):
        raise FixtureError('Private fixture validation requires Python 3.12 or later')
    result = {}
    for label, spec in FIXTURES.items():
        value = environment.get(spec['environment'])
        if not value:
            raise FixtureError(label + ': required private fixture is missing')
        path, raw = _read_private(value, repo=repo, output=output, label=label, spec=spec)
        _check_manifest(raw, label, spec)
        result[label] = {'path': str(path), 'environment': spec['environment'],
            'present': True, 'sha256': spec['sha256'], 'pdf_sha256': spec['pdf_sha256'],
            'manifest_verified': True, 'expected_source_rejection': label == 'bad_v3'}
    return result


def public_manifest(validated: dict) -> dict:
    return {label: {key: value for key, value in row.items() if key not in {'path', 'environment'}}
            for label, row in validated.items()}


def private_temporary_directory(*, prefix: str, repo: Path, output: Path):
    """Refuse unsafe inherited TEMP/TMPDIR before writing any private byte."""
    base = Path(tempfile.gettempdir())
    try:
        check_path_syntax(str(base))
        for item in (base, *base.parents):
            if item.is_symlink() or getattr(item, 'is_junction', lambda: False)():
                raise FixtureError('Private temporary root cannot use symlinks/junctions')
        canonical = base.resolve(strict=True)
        if not canonical.is_dir():
            raise FixtureError('Private temporary root must be a directory')
        for root in (repo.resolve(), output.resolve()):
            if canonical == root or canonical.is_relative_to(root):
                raise FixtureError('Private temporary root must be outside source and artifacts')
        if any((parent / '.git').is_file() or (parent / '.git/HEAD').is_file()
               for parent in (canonical, *canonical.parents)):
            raise FixtureError('Private temporary root must be outside Git checkouts')
        return tempfile.TemporaryDirectory(prefix=prefix, dir=canonical)
    except FixtureError:
        raise
    except (OSError, ValueError):
        raise FixtureError('Private temporary root unavailable') from None


class PrivateFixtureStage:
    """Ephemeral owner-only, read-only snapshots outside source and artifacts.

    Never expose an original's mutable path to later pytest processes. Snapshot
    bytes are independently checked against the fixed original pins after copy.
    """
    def __init__(self, environment: dict, *, repo: Path, output: Path):
        self.directory = None
        try:
            originals = validate_pair(environment, repo=repo, output=output)
            self.directory = private_temporary_directory(prefix='anvaya-private-fixtures-', repo=repo, output=output)
            self.environment = {}
            for label, row in originals.items():
                _, raw = _read_private(row['path'], repo=repo, output=output, label=label, spec=FIXTURES[label])
                destination = Path(self.directory.name) / (label + '.zip')
                destination.write_bytes(raw)
                destination.chmod(stat.S_IRUSR)
                self.environment[row['environment']] = str(destination)
            self.manifest = public_manifest(validate_pair(self.environment, repo=repo, output=output))
        except BaseException as error:
            self.close()
            if isinstance(error, OSError):
                raise FixtureError('Private fixture staging is unavailable') from None
            raise

    def close(self):
        if self.directory is not None:
            # Windows cannot remove read-only files; restore owner write only
            # inside this instance's private directory before deterministic cleanup.
            try:
                for path in Path(self.directory.name).glob('*.zip'):
                    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
                self.directory.cleanup()
            except OSError:
                raise FixtureError('Private fixture cleanup is unavailable; owner intervention required') from None
            self.directory = None


def redact(text: str, environment: dict) -> str:
    """Remove native and escaped private paths from persisted diagnostics."""
    import json
    for label, spec in FIXTURES.items():
        value = environment.get(spec['environment'])
        if value:
            variants = {value, value.replace('\\', '/'), json.dumps(value)[1:-1],
                value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')}
            for variant in sorted(variants, key=len, reverse=True):
                text = text.replace(variant, '<private-fixture:' + label + '>')
    return text
