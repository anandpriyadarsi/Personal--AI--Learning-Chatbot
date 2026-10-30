"""Idempotent adapter for existing local canonical PDFs; no source ID rewrite."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid


class LegacySources:
    def migrate_legacy_sources(self,database):
        from .native_document_library import now, _verified_original, LibraryError
        from personal_learning_assistant.android_backup import export_backup_file
        database=Path(database).absolute()
        if not database.is_file(): return {'imported':0}
        with self.connection() as con:
            if con.execute("SELECT 1 FROM migration_ledger WHERE operation_id='canonical-local-v2'").fetchone():
                return {'imported':0}
        with closing(sqlite3.connect(str(database))) as academic:
            academic.row_factory=sqlite3.Row
            rows=[dict(r) for r in academic.execute("SELECT * FROM knowledge_documents WHERE path_key LIKE 'documents/%' AND mime_type='application/pdf'")]
        if rows: export_backup_file(self.root.parent.parent)
        imported=0
        for source in rows:
            if not re.fullmatch('documents/[0-9a-f]{64}\\.pdf',source['path_key']): continue
            identity=uuid.uuid5(uuid.NAMESPACE_URL,'anvaya:canonical:'+source['id']+':'+source['content_hash']).hex
            digest=source['content_hash']
            if not re.fullmatch('[0-9a-f]{64}',digest): continue
            locator=source['path_key'];path=self.root.parent/locator
            size=source['size_bytes']
            if size is None:
                try:size=path.stat().st_size
                except OSError:size=0
            available=True
            try:_verified_original(self.root,{'sha256':digest,'size':size,'managed_original':locator})
            except LibraryError:available=False
            # Display overrides belong to their existing sidecar owner. Read a
            # title if available, without changing either registry database.
            name='Imported PDF '+source['id'][:8]+'.pdf'
            display=database.with_name(database.name+'.display.sqlite3')
            if display.is_file():
                try:
                    with closing(sqlite3.connect(display.as_uri()+'?mode=ro',uri=True)) as con:
                        columns={r[1] for r in con.execute('PRAGMA table_info(display_titles)')}
                        if {'kind','item_id','title'}<=columns:
                            title=con.execute("SELECT title FROM display_titles WHERE kind='document' AND item_id=?",(source['id'],)).fetchone()
                            if title:name=title[0]
                except sqlite3.Error:pass
            with self.connection(write=True) as con:
                if con.execute('SELECT 1 FROM source_links WHERE namespace=? AND source_id=? AND content_hash=?',('canonical',source['id'],digest)).fetchone():continue
                con.execute('''INSERT OR IGNORE INTO documents(id,original_name,display_name,kind,sha256,size,indexing_enabled,status,
                     created_at,updated_at,managed_original,availability,tutor_state) VALUES(?,?,?,?,?,?,1,?,?,?,?,?,?)''',
                     (identity,name,name,'pdf',digest,size,'stored' if available else 'unavailable',now(),now(),locator,
                      'available' if available else 'missing','preparing' if available else 'attention'))
                con.execute('INSERT OR IGNORE INTO source_links VALUES(?,?,?,?,?,?)',(identity,'canonical',source['id'],digest,'migrated','legacy:'+identity))
                self._enqueue_publication(con,identity)
                con.execute('INSERT OR REPLACE INTO migration_ledger VALUES(?,?,?,?)',('legacy:'+identity,'complete',now(),json.dumps({'source_id':source['id'],'sha256':digest})))
            imported+=1
        with self.connection(write=True) as con:
            con.execute("INSERT OR REPLACE INTO migration_ledger VALUES('canonical-local-v2','complete',?,'{}')",(now(),))
        self._wake.set()
        return {'imported':imported}
