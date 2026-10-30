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
