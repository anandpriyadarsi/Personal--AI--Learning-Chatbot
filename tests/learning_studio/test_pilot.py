import hashlib
import io
import os
from pathlib import Path
import stat
import zipfile
import pytest
from .helpers import catalogue
from personal_learning_assistant.learning_studio.archive import decode_json, read_zip
from personal_learning_assistant.learning_studio.validation import PackageError
from personal_learning_assistant.learning_studio.pilot import convert_pilot
from personal_learning_assistant.learning_studio.service import LearningStudioService


def archive(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in entries:
            info = zipfile.ZipInfo(name)
            # Preserve malicious raw names even when the host is Windows.
            info.filename = name; info.orig_filename = name
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    return output.getvalue()


@pytest.mark.parametrize('name', ['../escape', '/absolute', 'assets/../other.webp', 'C:drive', 'assets\\x.png', 'evil.html'])
def test_archive_path_and_types_rejected(name):
    with pytest.raises(PackageError): read_zip(archive([(name, b'unsafe')]))


def test_bomb_duplicate_symlink_and_duplicate_json_rejected():
    with pytest.raises(PackageError): read_zip(archive([('module.json', b'0' * 1_000_000)]))
    with pytest.warns(UserWarning): raw = archive([('module.json', b'{}'), ('module.json', b'{}')])
    with pytest.raises(PackageError): read_zip(raw)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as z:
        info = zipfile.ZipInfo('assets/link.png'); info.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(info, '../foreign')
    with pytest.raises(PackageError): read_zip(output.getvalue())
    with pytest.raises(PackageError): decode_json(b'{"schema":"one","schema":"two"}')


def test_external_bad_v3_source_is_rejected(tmp_path):
    path = os.environ.get('ANVAYA_TEST_BAD_V3_ZIP')
    if not path: pytest.skip('External bad V3 fixture missing; no real-source rejection is claimed.')
    with pytest.raises(PackageError, match='Pilot source hash mismatch'):
        convert_pilot(Path(path).read_bytes())
    # Verify the discrepancy independently of the converter.
    import json
    files = read_zip(Path(path).read_bytes(), pilot=True)
    claimed = json.loads(files['ANVAYA_Learning_Module_Proposed_v1.json'])['source_sha256']
    actual = hashlib.sha256(files['ORIGINAL_20_Page_Presentation.pdf']).hexdigest()
    assert actual != claimed
    assert not (tmp_path / 'learning_studio.sqlite3').exists()


def test_consistent_synthetic_twenty_page_reader(tmp_path):
    from personal_learning_assistant.learning_studio.demo import synthetic_pdf, synthetic_package
    source = synthetic_pdf()
    package, assets = synthetic_package(source)
    service = LearningStudioService(tmp_path / 'learning_studio.sqlite3', source_loader=lambda _: source,
                                   catalogue_loader=catalogue)
    service.stage(package, assets); service.publish(package['module_id'], 1)
    assert service.source(package['module_id'], 1) == source
    assert len(service.module(package['module_id'], 1)['pages']) == 20
    for page in package['pages']:
        assert service.asset(package['module_id'], 1, page['preview']) == assets[page['preview']]
    assert any(b['kind'] == 'mindmap' for s in package['sections'] for b in s['blocks'])
    assert any(b['kind'] == 'flowchart' for s in package['sections'] for b in s['blocks'])


def test_lying_deflate_size_is_rejected_with_bounded_expansion():
    import struct, zlib
    raw = bytearray(archive([('module.json', b'{}' + b'0' * 8_000_000)]))
    central = raw.index(b'PK\x01\x02')
    crc = zlib.crc32(b'{}')
    struct.pack_into('<I', raw, 14, crc); struct.pack_into('<I', raw, 22, 2)
    struct.pack_into('<I', raw, central + 16, crc); struct.pack_into('<I', raw, central + 24, 2)
    with pytest.raises(PackageError): read_zip(bytes(raw))


def test_corrupt_deflate_is_a_clean_validation_error():
    import struct
    raw = bytearray(archive([('module.json', b'{"schema":"test"}')]))
    name_len, extra_len = struct.unpack_from('<HH', raw, 26)
    raw[30+name_len+extra_len] = 0xff
    with pytest.raises(PackageError): read_zip(bytes(raw))


def test_original_archive_name_checked_before_platform_normalisation(monkeypatch):
    raw = archive([('assets\\x.png', b'unsafe')])
    original = zipfile.ZipInfo
    class NormalizingZipInfo(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.filename = self.filename.replace('\\', '/')
    monkeypatch.setattr(zipfile, 'ZipInfo', NormalizingZipInfo)
    with pytest.raises(PackageError): read_zip(raw)
