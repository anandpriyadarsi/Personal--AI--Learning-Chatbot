"""Leased local queue, native pages -> canonical owner -> lexical generation.

No cloud calls, model downloads, second extractor or duplicated originals.
Jobs resume on app open; this implementation does not claim closed-app work.
"""
from contextlib import closing
from pathlib import Path
from threading import Event, Thread
import sqlite3
import time
import uuid
from personal_learning_assistant.domain.ingestion_models import ExtractedUnit
from personal_learning_assistant.ingestion.chunking import prepare_chunks


class NativeTutorBridge:
    def configure_tutor(self,database_path,index_root,*,refresh=None):
        self._tutor_database=Path(database_path)
        self._tutor_index=Path(index_root)
        self._tutor_refresh=refresh
        self._wake.set()

    def _claim(self):
        token=uuid.uuid4().hex
        with self.connection(write=True) as con:
            row=con.execute('''SELECT j.id job_id,d.* FROM processing_jobs j JOIN documents d ON d.id=j.document_id
                 WHERE (j.state='pending' OR (j.state='running' AND j.lease_until<?))
                 AND j.generation=d.generation ORDER BY d.created_at,j.id LIMIT 1''',(time.time(),)).fetchone()
            if row is None: return None
            doc=self._doc(row);job=doc.pop('job_id')
            con.execute("UPDATE processing_jobs SET state='running',lease_owner=?,lease_until=?,attempts=attempts+1 WHERE id=?",(token,time.time()+90,job))
            if doc['indexing_enabled'] and not doc['trashed_at'] and doc['status']=='stored':
                con.execute("UPDATE documents SET status='indexing' WHERE id=?",(doc['id'],))
            return doc,job,token

    def _heartbeat(self,job,token,stop):
        while not stop.wait(20):
            with self.connection(write=True) as con:
                con.execute("UPDATE processing_jobs SET lease_until=? WHERE id=? AND lease_owner=? AND state='running'",(time.time()+90,job,token))

    def _publish_native(self,doc,pages):
        from .knowledge_registry_service import KnowledgeRegistryService
        from personal_learning_assistant.repositories.sqlite.knowledge_registry_repository import SQLiteKnowledgeRegistryRepository
        from personal_learning_assistant.repositories.sqlite.ingestion_repository import SQLiteIngestionRepository
        if not getattr(self,'_tutor_database',None): return None
        # One canonical identity per meaningful placement prevents cross-subject
        # broadening through hash-shared copies. Original bytes remain shared.
        with closing(sqlite3.connect(str(self._tutor_database),isolation_level=None,timeout=15)) as con:
            con.row_factory=sqlite3.Row;con.execute('PRAGMA foreign_keys=ON')
            registry=KnowledgeRegistryService(SQLiteKnowledgeRegistryRepository(con))
            path_key='native_library/'+doc['id']
            with self.connection() as native:
                linked=native.execute("SELECT source_id FROM source_links WHERE document_id=? AND namespace='canonical' AND content_hash=?",(doc['id'],doc['sha256'])).fetchone()
            existing=con.execute('SELECT id FROM knowledge_documents WHERE id=?',(linked['source_id'],)).fetchone() if linked else con.execute('SELECT id FROM knowledge_documents WHERE path_key=?',(path_key,)).fetchone()
            if existing is None:
                registry.register_document(kind='document',path_key=path_key,content_hash=doc['sha256'],mime_type=doc['mime'],size_bytes=doc['size'])
            source=existing['id'] if existing else con.execute('SELECT id FROM knowledge_documents WHERE path_key=?',(path_key,)).fetchone()[0]
            if not doc['indexing_enabled'] or doc['trashed_at'] or not pages:
                con.execute("UPDATE knowledge_documents SET extraction_status='unavailable' WHERE id=?",(source,))
                con.execute('DELETE FROM knowledge_chunks WHERE document_id=?',(source,))
                return source
            units=[]
            for position,text in pages:
                if not text.strip(): continue
                locator={'native_document_id':doc['id'],'content_hash':doc['sha256'],
                         'native_generation':doc['generation'],'metadata_revision':doc['metadata_revision'],
                         'course_id':doc['subject_id'],'filename':doc['display_name'],
                         'source_url':'/library/files/'+doc['id']+'/original?native_action=view'}
                if doc['kind']=='pdf': locator['page']=position
                elif doc['kind']=='pptx': locator['slide']=position
                elif doc['kind']=='docx': locator['paragraph']=position
                else: locator['line']=position
                units.append(ExtractedUnit(text=text,kind=doc['kind'],
                    page_number=position if doc['kind']=='pdf' else None,
                    slide_number=position if doc['kind']=='pptx' else None,locator=locator))
            chunks=prepare_chunks(units)
            if chunks:
                version='native-v2:'+doc['sha256']+':'+str(doc['generation'])
                repo=SQLiteIngestionRepository(con)
                repo.commit_extraction(document_id=source,content_hash=doc['sha256'],extraction_version=version,
                                       chunks=chunks,now=doc['updated_at'],handoff_index_version='native-v2')
            return source

    def _refresh_retrieval(self):
        if not getattr(self,'_tutor_database',None): return
        from personal_learning_assistant.repositories.sqlite.retrieval_source_repository import SQLiteRetrievalSourceRepository
        from personal_learning_assistant.retrieval.index_builder import RetrievalIndexBuilder
        with closing(sqlite3.connect(str(self._tutor_database),timeout=15)) as con:
            repo=SQLiteRetrievalSourceRepository(con)
            records=repo.active_records()
            if records:
                built=RetrievalIndexBuilder(repo,self._tutor_index).build(embedding_provider=None,acknowledge=False)
                if repo.source_fingerprint()!=built.source_fingerprint: return
                ready={(r['locator'].get('native_document_id'),r['locator'].get('native_generation')) for r in records}
                with self.connection(write=True) as native:
                    for identity,generation in ready:
                        native.execute("UPDATE documents SET tutor_state='ready' WHERE id=? AND generation=? AND trashed_at IS NULL AND indexing_enabled=1",(identity,generation))
        if self._tutor_refresh: self._tutor_refresh()

    def run_pending(self):
        if not self._worker_lock.acquire(blocking=False): return
        changed=False
        try:
            while not self._stop.is_set():
                claimed=self._claim()
                if claimed is None: break
                doc,job,token=claimed;stopped=Event()
                pulse=Thread(target=self._heartbeat,args=(job,token,stopped),daemon=True);pulse.start()
                try:
                    active=doc['indexing_enabled'] and not doc['trashed_at']
                    self._job_cancel[doc['id']]=Event()
                    if not active:
                        pages,status,detail=[],'disabled',''
                    elif doc['status'] in ('ready','partial','ocr_required','conversion_required','unavailable'):
                        with self.connection() as con:
                            pages=[(r['position'],r['text']) for r in con.execute('SELECT * FROM pages WHERE document_id=? ORDER BY position',(doc['id'],))]
                        status,detail=doc['status'],doc['status_detail']
                    else:
                        pages,status,detail=self._extract(doc)
                    with self.connection(write=True) as con:
                        current=con.execute('SELECT * FROM documents WHERE id=?',(doc['id'],)).fetchone()
                        lease=con.execute('SELECT * FROM processing_jobs WHERE id=?',(job,)).fetchone()
                        if (current is None or current['generation']!=doc['generation'] or lease['lease_owner']!=token or lease['state']!='running'):
                            con.execute("UPDATE processing_jobs SET state='cancelled' WHERE id=? AND lease_owner=?",(job,token));continue
                        self._remove_index(con,doc['id'])
                        indexed=0
                        for position,text in pages:
                            from .native_document_extraction import normalize
                            normalized=normalize(text)
                            if not normalized: continue
                            indexed+=1
                            cursor=con.execute('INSERT INTO pages(document_id,position,text) VALUES(?,?,?)',(doc['id'],position,text))
                            con.execute('INSERT INTO page_fts(rowid,document_id,position,text) VALUES(?,?,?,?)',(cursor.lastrowid,doc['id'],position,normalized))
                        # Publish only a still-current generation. The lock is
                        # held for owner transactions, never extraction or build.
                        source=self._publish_native(doc,pages if active else [])
                        tutor='preparing' if source and indexed and active else ('stored_only' if active else 'disabled')
                        con.execute('UPDATE documents SET status=?,status_detail=?,position_count=?,indexed_count=?,tutor_state=? WHERE id=?',
                                    (status,detail,len(pages),indexed,tutor,doc['id']))
                        if source:
                            con.execute('''INSERT OR REPLACE INTO source_links VALUES(?,?,?,?,?,?)''',
                                        (doc['id'],'canonical',source,doc['sha256'],'published',job))
                        con.execute("UPDATE processing_jobs SET state='complete',checkpoint='published',error_code='',lease_until=NULL WHERE id=? AND lease_owner=?",(job,token))
                    changed=True
                except Exception:
                    with self.connection(write=True) as con:
                        con.execute("UPDATE processing_jobs SET state='failed',error_code='local_processing_failed',lease_until=NULL WHERE id=? AND lease_owner=?",(job,token))
                        con.execute("UPDATE documents SET status='failed',tutor_state='attention',status_detail='Local processing failed or exceeded local resource limits. Original preserved; retry from Details.' WHERE id=? AND generation=?",(doc['id'],doc['generation']))
                finally:
                    self._job_cancel.pop(doc['id'],None);stopped.set();pulse.join(1)
            if changed:
                try: self._refresh_retrieval()
                except (sqlite3.Error,OSError,RuntimeError,ValueError):
                    # A durable published checkpoint retries the derived build
                    # on the next wake. Never report ready for a failed build.
                    self._wake.set()
            elif getattr(self,'_tutor_database',None):
                with self.connection() as con:
                    retry=con.execute("SELECT 1 FROM documents WHERE tutor_state='preparing' LIMIT 1").fetchone()
                if retry: self._refresh_retrieval()
        finally: self._worker_lock.release()
