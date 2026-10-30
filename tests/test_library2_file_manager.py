import hashlib
from io import BytesIO
from pathlib import Path
import sqlite3
import tempfile
import unittest
from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary, LibraryError

COURSES=[{'id':'real-math-id','code':'MA103N','name':'Linear Algebra'},
         {'id':'real-chem-id','code':'CY100N','name':'Engineering Chemistry'}]

class AcademicFilesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.lib=NativeDocumentLibrary(Path(self.temp.name)/'data/native_library',autostart=False)
        self.addCleanup(self.lib.close)

    def roots(self):
        return self.lib.bootstrap_academics(COURSES,namespace='routed-course')

    def test_hierarchy_is_idempotent_and_uses_authoritative_course_identity(self):
        roots=self.roots();again=self.roots()
        self.assertEqual(roots,again)
        self.assertEqual(len(roots['subjects']),2)
        self.assertEqual({r['course_id'] for r in roots['subjects']},{'real-math-id','real-chem-id'})
        self.assertEqual(self.lib.children(roots['semester']['folder_id'])['total'],2)
        with self.assertRaises(LibraryError): self.lib.delete_folder(roots['subjects'][0]['folder_id'])

    def test_folder_move_inherits_scope_and_rejects_unconfirmed_cross_subject(self):
        roots=self.roots();math,chem=roots['subjects']
        folder=self.lib.create_folder('Lectures',math['folder_id'])
        child=self.lib.create_folder('Week 1',folder['id'])
        doc=self.lib.upload(BytesIO(b'An eigenvalue is 47.'),'lecture.txt',folder_id=child['id'])
        self.assertEqual(doc['subject_id'],'real-math-id')
        with self.assertRaises(LibraryError): self.lib.update_folder(folder['id'],'Lectures',chem['folder_id'])
        self.lib.update_folder(folder['id'],'Lectures',chem['folder_id'],confirm_scope=True)
        self.assertEqual(self.lib.get(doc['id'])['subject_id'],'real-chem-id')
        self.assertEqual(self.lib.original(doc['id']).read_bytes(),b'An eigenvalue is 47.')

    def test_duplicate_requires_decision_and_copy_honors_destination(self):
        roots=self.roots();math,chem=roots['subjects']
        raw=b'exact original'
        first=self.lib.upload(BytesIO(raw),'same.txt',folder_id=math['folder_id'])
        with self.assertRaises(LibraryError) as error:
            self.lib.upload(BytesIO(raw),'same.txt',folder_id=chem['folder_id'])
        self.assertEqual(error.exception.status,409)
        copied=self.lib.upload(BytesIO(raw),'same.txt',folder_id=chem['folder_id'],duplicate='copy')
        self.assertNotEqual(copied['id'],first['id'])
        self.assertEqual(copied['folder_id'],chem['folder_id'])
        self.assertEqual(len(list((self.lib.root/'blobs').iterdir())),1)
        another=self.lib.upload(BytesIO(b'different'),'same.txt',folder_id=chem['folder_id'])
        self.assertEqual(another['display_name'],'same (2).txt')

    def test_trash_restore_and_pin_aware_permanent_delete(self):
        doc=self.lib.upload(BytesIO(b'unique fact'),'fact.txt')
        self.lib.run_pending()
        self.lib.trash(doc['id'])
        self.assertFalse(self.lib.search('fact'))
        self.assertEqual(self.lib.list_documents()['total'],0)
        self.assertTrue(self.lib.original(doc['id']).exists())
        self.lib.restore(doc['id'])
        self.assertEqual(self.lib.list_documents()['total'],1)
        self.lib.pin_source(doc['id'],'studio','lesson-id')
        self.lib.trash(doc['id'])
        with self.assertRaises(LibraryError): self.lib.delete(doc['id'])
        self.assertTrue(self.lib.original(doc['id']).exists())

    def test_templates_respect_rename_delete_and_reapplication(self):
        root=self.roots()['subjects'][0]['folder_id']
        result=self.lib.apply_template(root,'MA103N',confirm=True)
        self.assertEqual(len(result['added']),4)
        folder=result['added'][0]
        self.lib.update_folder(folder['id'],'My custom lectures',root)
        self.lib.delete_folder(result['added'][1]['id'])
        again=self.lib.apply_template(root,'MA103N',confirm=True)
        self.assertEqual(again['added'],[])
        self.assertIn('My custom lectures',{f['name'] for f in self.lib.children(root)['items']})

    def test_metadata_substring_unicode_and_reopen(self):
        doc=self.lib.upload(BytesIO('सममिति matrix'.encode()),'रैखिक बीजगणित.txt')
        self.assertEqual(self.lib.metadata_search('बीज')[0]['id'],doc['id'])
        self.lib.update(doc['id'],display_name='Eigenvalues')
        self.assertEqual(self.lib.metadata_search('eigen')[0]['id'],doc['id'])
        reopened=NativeDocumentLibrary(self.lib.root,autostart=False)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.get(doc['id'])['sha256'],hashlib.sha256('सममिति matrix'.encode()).hexdigest())

if __name__=='__main__': unittest.main()


class OriginalRepairTests(unittest.TestCase):
    setUp=AcademicFilesTests.setUp
    def test_repair_requires_identical_bytes_and_keeps_identity_and_opt_out(self):
        raw=b'Saved code example, never executed.'
        doc=self.lib.upload(BytesIO(raw),'lab.py',indexing=False)
        self.lib.original(doc['id']).unlink()
        with self.assertRaises(LibraryError):self.lib.repair_original(doc['id'],BytesIO(b'different'))
        repaired=self.lib.repair_original(doc['id'],BytesIO(raw))
        self.assertEqual(repaired['id'],doc['id'])
        self.assertEqual(repaired['indexing_enabled'],0)
        self.assertEqual(self.lib.original(doc['id']).read_bytes(),raw)


class NativeRecentTests(unittest.TestCase):
    setUp=AcademicFilesTests.setUp
    def test_successful_native_open_records_recent_without_mutating_original(self):
        from personal_learning_assistant.services.native_document_library import resolve_android_document,record_android_open
        raw=b'Native original text'
        doc=self.lib.upload(BytesIO(raw),'fact.txt',indexing=False)
        app_root=self.lib.root.parent.parent
        resolved=resolve_android_document(app_root,doc['id'])
        self.assertEqual(resolved[1:],["text/plain","fact.txt"])
        record_android_open(app_root,doc['id'])
        self.assertEqual(self.lib.collection('recent')['items'][0]['id'],doc['id'])
        self.assertEqual(self.lib.original(doc['id']).read_bytes(),raw)
