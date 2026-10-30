"""Real disk round trips; runnable with unittest when optional test deps are absent."""
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile
from personal_learning_assistant import android_backup as backup


class StreamingBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'data').mkdir()

    def test_over_100_mib_round_trip_without_whole_file_reads(self):
        path = self.root/'data/large.bin'
        block = b'lecture data\n' * 8192
        with path.open('wb') as stream:
            for _ in range(1100): stream.write(block)
        self.assertGreater(path.stat().st_size, 100*1024*1024)
        archive = backup.export_backup_file(self.root)
        dest = self.root/'destination'
        with archive.open('rb') as source: backup.stage_restore(dest, source)
        self.assertTrue(backup.apply_pending_restore(dest))
        def digest(p):
            with p.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()
        self.assertEqual(digest(path), digest(dest/'data/large.bin'))

    def test_missing_promised_payload_rejected_without_replacing_data(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('manifest.json', json.dumps({'format':'anvaya.android-backup.v2', 'files':{
                'data/lost.pdf':{'sha256':'a'*64,'size':12}}}))
        with self.assertRaises(ValueError): backup.stage_restore(self.root, archive.getvalue())
        self.assertFalse((self.root/'restore-pending.zip').exists())

    def test_v1_import_and_previous_data_retained(self):
        (self.root/'data/old.txt').write_text('keep')
        payload=b'v1 notes'; archive=io.BytesIO()
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('data/notes.txt',payload)
            z.writestr('manifest.json',json.dumps({'format':'anvaya.android-backup.v1','files':{
                'data/notes.txt':hashlib.sha256(payload).hexdigest()}}))
        backup.stage_restore(self.root, archive.getvalue())
        backup.apply_pending_restore(self.root)
        self.assertEqual((self.root/'data/notes.txt').read_bytes(),payload)
        self.assertTrue(list(self.root.glob('data-before-restore-*/old.txt')))

    def test_missing_native_original_is_declared_not_fabricated(self):
        native=self.root/'data/native_library'; native.mkdir()
        with sqlite3.connect(native/'library.sqlite3') as con:
            con.execute('CREATE TABLE documents(id TEXT,sha256 TEXT,size INTEGER)')
            con.execute('PRAGMA user_version=1')
            con.execute('INSERT INTO documents VALUES(?,?,?)',('d','a'*64,10))
        archive=backup.export_backup_file(self.root)
        with zipfile.ZipFile(archive) as z:
            manifest=json.loads(z.read('manifest.json'))
        self.assertEqual(manifest['unavailable_originals'][0]['sha256'],'a'*64)
        dest=self.root/'dest'
        with archive.open('rb') as stream: backup.stage_restore(dest,stream)
        backup.apply_pending_restore(dest)
        self.assertFalse((dest/'data/native_library/blobs'/('a'*64)).exists())
        self.assertTrue((dest/'data/library-recovery.json').exists())

    def test_interrupted_swap_recovered_before_reading_pending_archive(self):
        previous=self.root/'data-before-restore-test'
        (self.root/'data').rename(previous)
        journal={'previous':previous.name,'stage':'.restore-test','phase':'old_moved'}
        (self.root/'restore-journal.json').write_text(json.dumps(journal))
        self.assertFalse(backup.apply_pending_restore(self.root))
        self.assertTrue((self.root/'data').exists())


if __name__ == '__main__': unittest.main()
