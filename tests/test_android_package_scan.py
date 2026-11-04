"""Exercise the delivery gate against actual ZIP entries, including public CAs."""
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

GATE = (Path(__file__).parents[1] / 'scripts/android_emulator_acceptance.sh').read_text().split("<<'PACKAGE_CHECK'\n", 1)[1].split('\nPACKAGE_CHECK', 1)[0]
PUBLIC_CERT = b'-----BEGIN CERTIFICATE-----\nMAA=\n-----END CERTIFICATE-----\n'


def scan(tmp_path, entries):
    evidence = tmp_path / 'android-evidence'
    evidence.mkdir()
    (evidence / 'apk-badging.txt').write_text("name='in.anvaya.privateapp' versionCode='19' versionName='1.4.0-unified-debug' sdkVersion:'24' targetSdkVersion:'35' armeabi-v7a arm64-v8a x86_64")
    with zipfile.ZipFile(evidence / 'ANVAYA-Unified-Android-test.apk', 'w') as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    return subprocess.run([sys.executable, '-c', GATE], cwd=tmp_path, capture_output=True, text=True)


def test_chaquopy_public_ca_bundle_is_not_a_private_key(tmp_path):
    result = scan(tmp_path, {'assets/chaquopy/cacert.pem': b'# Public CA bundle\n' + PUBLIC_CERT})
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('name', ['assets/private.pem', 'assets/key.jks', 'assets/main.db', 'assets/main.sqlite', 'assets/main.sqlite3', 'assets/owner.keystore', 'assets/workspace.zip', 'assets/androidTest/fixture.json'])
def test_private_or_test_payload_remains_forbidden(tmp_path, name):
    assert scan(tmp_path, {name: PUBLIC_CERT}).returncode != 0


@pytest.mark.parametrize('data', [b'-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----', PUBLIC_CERT + b'-----BEGIN RSA PRIVATE KEY-----\nsecret', b'', b'# No actual certificate', PUBLIC_CERT + b'garbage', PUBLIC_CERT + b'# -----BEGIN PRIVATE KEY-----'])
def test_ca_allowance_cannot_hide_keys_or_arbitrary_payload(tmp_path, data):
    assert scan(tmp_path, {'assets/chaquopy/cacert.pem': data}).returncode != 0
