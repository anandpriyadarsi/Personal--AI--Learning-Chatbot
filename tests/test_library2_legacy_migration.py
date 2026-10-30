from contextlib import closing
from io import BytesIO
from pathlib import Path
import hashlib
import sqlite3
import tempfile
import unittest
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
from personal_learning_assistant.repositories.sqlite.knowledge_registry_repository import SQLiteKnowledgeRegistryRepository
from personal_learning_assistant.services.knowledge_registry_service import KnowledgeRegistryService
from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary

class LegacyOriginalMigrationTests(unittest.TestCase):
    def test_existing_canonical_identity_and_managed_bytes_survive_without_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); data=root/'data';data.mkdir()
            db=data/'learning_assistant.db';apply_migrations(db)
            # Signature-only PDF is sufficient here: this test migrates storage,
            # not extraction. Real PDF extraction is covered by existing tests.
            raw=b'%PDF-1.4 original legacy bytes';digest=hashlib.sha256(raw).hexdigest()
            directory=data/'documents';directory.mkdir();original=directory/(digest+'.pdf');original.write_bytes(raw)
            with closing(sqlite3.connect(db,isolation_level=None)) as con:
                registry=KnowledgeRegistryService(SQLiteKnowledgeRegistryRepository(con))
                registry.register_document(kind='document',path_key='documents/'+original.name,
                                           content_hash=digest,mime_type='application/pdf',size_bytes=len(raw))
                canonical=con.execute('SELECT id FROM knowledge_documents').fetchone()[0]
            lib=NativeDocumentLibrary(data/'native_library',autostart=False)
            try:
                first=lib.migrate_legacy_sources(db);second=lib.migrate_legacy_sources(db)
                self.assertEqual(first['imported'],1);self.assertEqual(second['imported'],0)
                docs=lib.collection('unsorted')['items'];self.assertEqual(len(docs),1)
                self.assertEqual(lib.original(docs[0]['id']),original)
                self.assertEqual(lib.original(docs[0]['id']).read_bytes(),raw)
                self.assertFalse(list((lib.root/'blobs').iterdir()))
                with lib.connection() as con:
                    self.assertEqual(con.execute('SELECT source_id FROM source_links').fetchone()[0],canonical)
                with closing(sqlite3.connect(db)) as con:
                    self.assertEqual(con.execute('SELECT id FROM knowledge_documents').fetchone()[0],canonical)
            finally:lib.close()

if __name__=='__main__':unittest.main()


class RecoveryEligibilityTests(unittest.TestCase):
    def test_declared_unavailable_subject_original_restores_to_unsorted(self):
        from personal_learning_assistant.android_backup import export_backup,stage_restore,apply_pending_restore
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'source';lib=NativeDocumentLibrary(source/'data/native_library',autostart=False)
            doc=lib.upload(BytesIO(b'Unique fact'),'fact.txt',subject_id='chem')
            lib.original(doc['id']).unlink()
            raw=export_backup(source);lib.close()
            target=root/'target';stage_restore(target,raw);apply_pending_restore(target)
            restored=NativeDocumentLibrary(target/'data/native_library',autostart=False)
            try:
                self.assertEqual(restored.get(doc['id'])['availability'],'missing')
                self.assertEqual(restored.collection('unsorted')['total'],1)
                self.assertNotEqual(restored.get(doc['id'])['tutor_state'],'ready')
                restored.repair_original(doc['id'],BytesIO(b'Unique fact'))
                reopened=NativeDocumentLibrary(restored.root,autostart=False)
                try:self.assertEqual(reopened.get(doc['id'])['availability'],'available')
                finally:reopened.close()
            finally:restored.close()


class StudioNativeSourceTests(unittest.TestCase):
    def test_native_pdf_resolves_for_studio_without_copy_or_relaxed_limits(self):
        from pypdf import PdfWriter
        from personal_learning_assistant.learning_studio.sources import RegisteredSources
        writer=PdfWriter();writer.add_blank_page(width=100,height=100);out=BytesIO();writer.write(out);raw=out.getvalue()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);data=root/'data';data.mkdir();(data/'documents').mkdir()
            db=data/'learning_assistant.db';apply_migrations(db)
            lib=NativeDocumentLibrary(data/'native_library',autostart=False)
            try:
                lib.configure_tutor(db,data/'tutor_retrieval')
                doc=lib.upload(BytesIO(raw),'Original.pdf');lib.run_pending()
                with lib.connection() as con:source=con.execute('SELECT source_id FROM source_links WHERE document_id=?',(doc['id'],)).fetchone()[0]
                self.assertEqual(RegisteredSources(db,{'documents':data/'documents'})(source),raw)
                self.assertFalse(list((data/'documents').iterdir()))
            finally:lib.close()


class LegacyCourseScopeTests(unittest.TestCase):
    def test_existing_course_scope_survives_until_explicit_placement_change(self):
        from personal_learning_assistant.repositories.sqlite.retrieval_source_repository import SQLiteRetrievalSourceRepository
        import fitz
        pdf=fitz.open();page=pdf.new_page();page.insert_text((30,60),'Zirconium47 academic source');raw=pdf.tobytes();pdf.close()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);data=root/'data';data.mkdir();(data/'documents').mkdir()
            digest=hashlib.sha256(raw).hexdigest();(data/'documents'/(digest+'.pdf')).write_bytes(raw)
            db=data/'learning_assistant.db';apply_migrations(db)
            with closing(sqlite3.connect(db,isolation_level=None)) as con:
                owner=KnowledgeRegistryService(SQLiteKnowledgeRegistryRepository(con))
                owner.register_document(kind='document',path_key='documents/'+digest+'.pdf',content_hash=digest,mime_type='application/pdf',size_bytes=len(raw))
                source=con.execute('SELECT id FROM knowledge_documents').fetchone()[0]
                con.execute("INSERT INTO courses(id,code,name,created_at,updated_at) VALUES('chem','CY100N','Chemistry','t','t')")
                con.execute("INSERT INTO resources(id,resource_type,title,created_at,updated_at) VALUES('r','document','Original lecture','t','t')")
                con.execute("INSERT INTO resource_courses(resource_id,course_id) VALUES('r','chem')")
                con.execute("INSERT INTO resource_documents(resource_id,document_id) VALUES('r',?)",(source,))
            lib=NativeDocumentLibrary(data/'native_library',autostart=False)
            try:
                lib.migrate_legacy_sources(db);lib.configure_tutor(db,data/'tutor_retrieval');lib.run_pending()
                with closing(sqlite3.connect(db)) as con:
                    records=SQLiteRetrievalSourceRepository(con).active_records()
                    self.assertEqual(records[0]['course_ids'],('chem',))
                native=lib.collection('unsorted')['items'][0]
                lib.update(native['id'],folder_id=None);lib.run_pending()
                with closing(sqlite3.connect(db)) as con:
                    self.assertEqual(SQLiteRetrievalSourceRepository(con).active_records()[0]['course_ids'],())
            finally:lib.close()
