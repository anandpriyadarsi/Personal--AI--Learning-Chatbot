from contextlib import closing
from io import BytesIO
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
from personal_learning_assistant.repositories.sqlite.retrieval_source_repository import SQLiteRetrievalSourceRepository
from personal_learning_assistant.services.unified_search_runtime import UnifiedSearchRuntime

class TutorBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'data').mkdir()
        apply_migrations(self.root/'data/learning_assistant.db')
        self.lib=NativeDocumentLibrary(self.root/'data/native_library',autostart=False)
        self.addCleanup(self.lib.close)
        self.lib.configure_tutor(self.root/'data/learning_assistant.db',self.root/'data/tutor_retrieval')

    def records(self):
        with closing(sqlite3.connect(self.root/'data/learning_assistant.db')) as con:
            return SQLiteRetrievalSourceRepository(con).active_records()

    def test_upload_automatically_publishes_exact_hash_line_and_scoped_retrieval(self):
        doc=self.lib.upload(BytesIO(b'The synthetic catalyst is Zirconium47.'),'chemistry.txt',subject_id='chem')
        self.lib.run_pending()
        self.assertEqual(self.lib.get(doc['id'])['tutor_state'],'ready')
        records=self.records();self.assertEqual(len(records),1)
        self.assertEqual(records[0]['content_hash'],doc['sha256'])
        self.assertEqual(records[0]['locator']['line'],1)
        self.assertEqual(records[0]['course_ids'],('chem',))
        runtime=UnifiedSearchRuntime(database_path=self.root/'data/learning_assistant.db',index_root=self.root/'data/tutor_retrieval')
        self.addCleanup(runtime.close)
        hits=runtime.search('Zirconium47',course_ids=('chem',))
        self.assertTrue(hits)
        self.assertFalse(runtime.search('Zirconium47',course_ids=('math',)))
        self.lib.run_pending()
        self.assertEqual(len(self.records()),1)

    def test_trash_and_disable_immediately_remove_native_evidence(self):
        doc=self.lib.upload(BytesIO(b'Unique evidence Zirconium47.'),'fact.txt')
        self.lib.run_pending();self.assertEqual(len(self.records()),1)
        self.lib.trash(doc['id'])
        self.assertFalse(self.records())
        self.lib.run_pending();self.assertFalse(self.records())
        self.lib.restore(doc['id']);self.lib.run_pending();self.assertEqual(len(self.records()),1)
        self.lib.set_indexing(doc['id'],False)
        self.assertFalse(self.records())

    def test_two_owners_do_not_extract_same_job_and_cancel_cannot_publish(self):
        doc=self.lib.upload(BytesIO(b'evidence'),'fact.txt')
        second=NativeDocumentLibrary(self.lib.root,autostart=False);self.addCleanup(second.close)
        entered=threading.Event();release=threading.Event();count=[]
        extract=self.lib._extract
        def held(d):
            count.append(d['id']);entered.set();self.assertTrue(release.wait(5));return extract(d)
        self.lib._extract=held
        worker=threading.Thread(target=self.lib.run_pending);worker.start()
        self.assertTrue(entered.wait(5))
        second.run_pending()
        self.lib.set_indexing(doc['id'],False);release.set();worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(count,[doc['id']]);self.assertFalse(self.records())

if __name__=='__main__': unittest.main()
