"""The read-only academic invariant must not inspect asynchronous reader files."""
import hashlib
from pathlib import Path

from tests.test_architecture_manual_academic_journey_browser import academic_inventory


def test_academic_inventory_ignores_disappearing_unrelated_journal(tmp_path, monkeypatch):
    academic = tmp_path / "academic.sqlite3"
    academic.write_bytes(b"canonical academic data")
    journal = tmp_path / "learning_studio.sqlite3-journal"
    journal.write_bytes(b"temporary reader transaction")
    original_read = Path.read_bytes

    def read_with_disappearing_journal(path):
        if path == journal:
            journal.unlink()
            raise FileNotFoundError(path)
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", read_with_disappearing_journal)
    before = academic_inventory(academic)
    assert before == {academic.name: hashlib.sha256(b"canonical academic data").hexdigest()}
    academic.write_bytes(b"unexpected academic mutation")
    assert academic_inventory(academic) != before


def test_academic_inventory_keeps_canonical_wal_and_shm(tmp_path):
    academic = tmp_path / "academic.sqlite3"
    for suffix in ("", "-wal", "-shm"):
        academic.with_name(academic.name + suffix).write_bytes(suffix.encode())
    before = academic_inventory(academic)
    assert set(before) == {academic.name, academic.name + "-wal", academic.name + "-shm"}
    academic.with_name(academic.name + "-wal").write_bytes(b"changed")
    assert academic_inventory(academic) != before
