"""Academic hierarchy and placement lifecycle on the existing native store."""
import json
import shutil
import uuid
from .native_document_extraction import normalize

TEMPLATES = {
 'CY100N': ['Lecture Notes',"Professor's PPTs",'PDFs','Assignments','Lab Materials','Previous Year Questions'],
 'UC100N': ['Lecture Materials','Lab Programs','Datasets','Assignments','Practice'],
 'MA103N': ['Lecture Notes','Practice Problems','Tutorials','Previous Year Questions'],
 'DE100N': ['Lecture Materials','Project Work','Assignments','References'],
 'UC103N': ['Lecture Notes','Readings','Assignments','Practice'],
}


class AcademicFiles:
    def bootstrap_academics(self, courses, *, namespace='routed-course', number=1):
        from .native_document_library import label, LibraryError
        if not isinstance(number,int) or not 1<=number<=8: raise LibraryError('Choose semester 1–8.')
        namespace=label(namespace,maximum=150)
        semester_id=uuid.uuid5(uuid.NAMESPACE_URL,'anvaya:semester:'+str(number)).hex
        with self.connection(write=True) as con:
            term=con.execute('SELECT * FROM semesters WHERE id=?',(semester_id,)).fetchone()
            if term is None:
                root=uuid.uuid4().hex
                con.execute("INSERT INTO folders(id,name,parent_id,node_kind) VALUES(?,?,NULL,'semester')",(root,'Semester '+str(number)))
                con.execute('INSERT INTO semesters(id,number,label,folder_id,sort_order) VALUES(?,?,?,?,?)',
                            (semester_id,number,'Semester '+str(number),root,number))
                term=con.execute('SELECT * FROM semesters WHERE id=?',(semester_id,)).fetchone()
            for index,course in enumerate(courses):
                identity=label(str(course['id']),maximum=150)
                if con.execute('SELECT 1 FROM subject_bindings WHERE semester_id=? AND authority=? AND course_id=?',
                               (semester_id,namespace,identity)).fetchone(): continue
                binding_id=uuid.uuid4().hex; folder_id=uuid.uuid4().hex
                con.execute("INSERT INTO folders(id,name,parent_id,binding_id,node_kind,sort_order) VALUES(?,?,?,?,'subject',?)",
                            (folder_id,label(course['code']+' — '+course['name']),term['folder_id'],binding_id,index))
                con.execute('INSERT INTO subject_bindings VALUES(?,?,?,?,?,?)',
                            (binding_id,semester_id,namespace,identity,course['code'],folder_id))
            subjects=[dict(r) for r in con.execute('SELECT b.*,f.name FROM subject_bindings b JOIN folders f ON f.id=b.folder_id WHERE semester_id=? ORDER BY f.sort_order,f.id',(semester_id,))]
            return {'semester':dict(term),'subjects':subjects}

    def semesters(self):
        with self.connection() as con: return [dict(r) for r in con.execute('SELECT * FROM semesters ORDER BY sort_order,id')]

    def _binding(self, con, folder_id):
        self._folder(con,folder_id)
        if folder_id is None: return None
        row=con.execute('''WITH RECURSIVE ancestors(id,parent_id,binding_id,depth) AS (
            SELECT id,parent_id,binding_id,0 FROM folders WHERE id=? UNION ALL
            SELECT f.id,f.parent_id,f.binding_id,a.depth+1 FROM folders f JOIN ancestors a ON f.id=a.parent_id WHERE a.depth<100)
            SELECT b.* FROM ancestors a JOIN subject_bindings b ON b.id=a.binding_id ORDER BY a.depth LIMIT 1''',(folder_id,)).fetchone()
        return dict(row) if row else None

    def children(self, parent_id=None, *, offset=0, limit=100):
        from .native_document_library import LibraryError
        limit,offset=int(limit),int(offset)
        if not 1<=limit<=100 or not 0<=offset<=100000: raise LibraryError('Invalid folder page.')
        with self.connection() as con:
            self._folder(con,parent_id)
            total=con.execute('SELECT count(*) FROM folders WHERE parent_id IS ?',(parent_id,)).fetchone()[0]
            items=[dict(r) for r in con.execute('SELECT * FROM folders WHERE parent_id IS ? ORDER BY sort_order,name,id LIMIT ? OFFSET ?',
                                               (parent_id,limit,offset))]
            return {'items':items,'total':total}

    def breadcrumbs(self, folder_id):
        from .native_document_library import LibraryError
        with self.connection() as con:
            result=[]
            while folder_id:
                row=con.execute('SELECT * FROM folders WHERE id=?',(folder_id,)).fetchone()
                if row is None or len(result)>100: raise LibraryError('Folder unavailable.',404)
                result.insert(0,dict(row));folder_id=row['parent_id']
            return result

    def _name_available(self,con,name,parent_id,excluding=None):
        from .native_document_library import LibraryError
        for row in con.execute('SELECT id,name FROM folders WHERE parent_id IS ?',(parent_id,)):
            if row['id']!=excluding and normalize(row['name'])==normalize(name):
                raise LibraryError('A folder with this name already exists here.',409)

    def metadata_search(self, query, *, folder_id=None, subject_id=None, kind=None, offset=0,limit=50):
        from .native_document_library import LibraryError
        if len(query)>500: raise LibraryError('Search is limited to 500 characters.')
        query=normalize(query)
        if not query: return []
        with self.connection() as con:
            scope,args=self._scope(con,folder_id,subject_id)
            if kind: scope+=' AND d.kind=?';args.append(kind)
            rows=con.execute('''SELECT d.* FROM documents d LEFT JOIN folders f ON f.id=d.folder_id
                 LEFT JOIN subject_bindings b ON b.id=f.binding_id WHERE d.trashed_at IS NULL
                 AND instr(library_normalize(d.display_name||' '||d.original_name||' '||d.kind||' '||d.topic||' '||d.tags||' '||coalesce(f.name,'')||' '||coalesce(b.code,'')),?)>0'''+scope+
                 ' ORDER BY d.updated_at DESC,d.id LIMIT ? OFFSET ?',
                 (query,*args,min(100,max(1,int(limit))),max(0,int(offset))))
            return [dict(self._doc(r),position=None,snippet='File name or metadata',match_kind='metadata') for r in rows]

    def trash(self,document_id):
        from .native_document_library import now
        with self.connection(write=True) as con:
            self._doc(con.execute('SELECT * FROM documents WHERE id=?',(document_id,)).fetchone())
            self._cancel_job(document_id);self._remove_index(con,document_id,purge=True)
            con.execute("UPDATE documents SET trashed_at=?,generation=generation+1,status='disabled',tutor_state='disabled',metadata_revision=metadata_revision+1 WHERE id=?",(now(),document_id))
            con.execute("UPDATE processing_jobs SET state='cancelled' WHERE document_id=?",(document_id,))
            self._enqueue_publication(con,document_id)
        self._wake.set()

    def restore(self,document_id):
        with self.connection(write=True) as con:
            self._doc(con.execute('SELECT * FROM documents WHERE id=?',(document_id,)).fetchone())
            con.execute("UPDATE documents SET trashed_at=NULL,generation=generation+1,status=CASE WHEN indexing_enabled THEN 'stored' ELSE 'disabled' END,metadata_revision=metadata_revision+1 WHERE id=?",(document_id,))
            self._enqueue_publication(con,document_id)
        self._wake.set()
        return self.get(document_id)

    def pin_source(self,document_id,owner,reference_id):
        from .native_document_library import label
        with self.connection(write=True) as con:
            self._doc(con.execute('SELECT * FROM documents WHERE id=?',(document_id,)).fetchone())
            con.execute('INSERT OR IGNORE INTO source_pins VALUES(?,?,?)',(document_id,label(owner),label(reference_id)))

    def _enqueue_publication(self,con,document_id):
        row=con.execute('SELECT * FROM documents WHERE id=?',(document_id,)).fetchone()
        if row is None: return
        con.execute("UPDATE processing_jobs SET state='cancelled' WHERE document_id=? AND generation<>? AND state IN ('pending','running')",(document_id,row['generation']))
        con.execute('''INSERT OR IGNORE INTO processing_jobs(id,document_id,content_hash,generation,extraction_version)
            VALUES(?,?,?,?,?)''',(uuid.uuid4().hex,document_id,row['sha256'],row['generation'],'native-v2'))

    def favorite(self,document_id,enabled):
        from .native_document_library import LibraryError
        if type(enabled) is not bool: raise LibraryError('Favorite must be a boolean.')
        with self.connection(write=True) as con:
            self._doc(con.execute('SELECT * FROM documents WHERE id=?',(document_id,)).fetchone())
            con.execute('UPDATE documents SET favorite=? WHERE id=?',(int(enabled),document_id))

    def mark_opened(self,document_id):
        from .native_document_library import now
        with self.connection(write=True) as con:
            con.execute('UPDATE documents SET opened_at=? WHERE id=? AND trashed_at IS NULL',(now(),document_id))

    def collection(self, view, *, limit=100, offset=0):
        from .native_document_library import LibraryError
        scope={'trash':'trashed_at IS NOT NULL','favorites':'trashed_at IS NULL AND favorite=1',
               'recent':'trashed_at IS NULL AND opened_at IS NOT NULL',
               'unsorted':"trashed_at IS NULL AND (subject_id IS NULL OR availability<>'available')"}.get(view)
        if scope is None: raise LibraryError('Choose a valid Library view.')
        with self.connection() as con:
            total=con.execute('SELECT count(*) FROM documents WHERE '+scope).fetchone()[0]
            rows=con.execute('SELECT * FROM documents WHERE '+scope+' ORDER BY coalesce(opened_at,updated_at) DESC,id LIMIT ? OFFSET ?',
                             (min(100,max(1,int(limit))),max(0,int(offset))))
            return {'items':[self._doc(r) for r in rows],'total':total,'page':1,'page_size':limit}

    def storage_usage(self):
        with self.connection() as con:
            unique=con.execute('SELECT coalesce(sum(size),0) FROM (SELECT sha256,max(size) size FROM documents GROUP BY sha256)').fetchone()[0]
            trash=con.execute('SELECT coalesce(sum(size),0) FROM (SELECT sha256,max(size) size FROM documents GROUP BY sha256 HAVING sum(trashed_at IS NULL)=0)').fetchone()[0]
            count=con.execute('SELECT count(*) FROM documents').fetchone()[0]
            unsorted=con.execute("SELECT count(*) FROM documents WHERE trashed_at IS NULL AND (subject_id IS NULL OR availability<>'available')").fetchone()[0]
        return {'unique_bytes':unique,'trash_bytes':trash,'placements':count,'unsorted':unsorted,
                'free_bytes':shutil.disk_usage(self.root).free,
                'metadata_index_bytes':self.database.stat().st_size}

    def apply_template(self,folder_id,key,*,confirm=False):
        from .native_document_library import LibraryError
        names=TEMPLATES.get(key)
        if names is None: raise LibraryError('Template unavailable.')
        added=[]
        with self.connection(write=True) as con:
            self._folder(con,folder_id)
            binding=self._binding(con,folder_id)
            if not binding: raise LibraryError('Choose a subject folder first.')
            for index,name in enumerate(names):
                origin=key+':'+str(index)
                if con.execute('SELECT 1 FROM template_applications WHERE folder_id=? AND template_key=? AND origin_key=?',(folder_id,key,origin)).fetchone(): continue
                existing=con.execute('SELECT id FROM folders WHERE parent_id=? AND name=?',(folder_id,name)).fetchone()
                identity=existing['id'] if existing else uuid.uuid4().hex
                if confirm:
                    if not existing:
                        con.execute('INSERT INTO folders(id,name,parent_id,binding_id,sort_order,template_origin) VALUES(?,?,?,?,?,?)',
                                    (identity,name,folder_id,binding['id'],index,origin))
                    con.execute('INSERT INTO template_applications VALUES(?,?,?,?,1)',(folder_id,key,origin,identity))
                added.append({'id':identity,'name':name,'parent_id':folder_id})
        return {'added':added,'applied':bool(confirm),'version':1}

    def repair_original(self,document_id,stream):
        from .native_document_library import LibraryError,MAX_UPLOAD,_safe
        from .native_document_formats import validate
        import hashlib,os,tempfile
        from pathlib import Path
        doc=self.get(document_id);digest=hashlib.sha256();size=0;prefix=b''
        fd,temporary=tempfile.mkstemp(dir=_safe(self.root/'tmp'));temporary=Path(temporary)
        try:
            with os.fdopen(fd,'wb') as output:
                for chunk in iter(lambda:stream.read(256*1024),b''):
                    size+=len(chunk)
                    if size>MAX_UPLOAD:raise LibraryError('Original exceeds 100 MiB.',413)
                    digest.update(chunk);output.write(chunk)
                    if len(prefix)<1024:prefix+=chunk[:1024-len(prefix)]
                output.flush();os.fsync(output.fileno())
            if digest.hexdigest()!=doc['sha256'] or size!=doc['size']:
                raise LibraryError('Choose the identical original file. Its expected hash must match.',409)
            try:validate(temporary,doc['kind'],prefix)
            except ValueError as error:raise LibraryError('Original format is invalid.') from error
            with self.connection(write=True) as con:
                os.replace(temporary,self._blob(doc['sha256']))
                if os.name!='nt':
                    handle=os.open(self.root/'blobs',os.O_RDONLY)
                    try:os.fsync(handle)
                    finally:os.close(handle)
                for row in con.execute('SELECT id FROM documents WHERE sha256=? AND size=?',(doc['sha256'],size)).fetchall():
                    con.execute("UPDATE documents SET managed_original=NULL,availability='available',generation=generation+1,status=CASE WHEN indexing_enabled THEN 'stored' ELSE 'disabled' END,tutor_state=CASE WHEN indexing_enabled THEN 'preparing' ELSE 'disabled' END WHERE id=?",(row['id'],))
                    self._enqueue_publication(con,row['id'])
            self._wake.set();return self.get(document_id)
        finally:temporary.unlink(missing_ok=True)


    def _restore_availability(self):
        from .native_document_library import _safe
        recovery=_safe(self.root.parent/'library-recovery.json')
        if not recovery.exists():return
        if recovery.stat().st_size>8*1024*1024:raise ValueError('Recovery inventory exceeds limits')
        records=json.loads(recovery.read_text(encoding='utf-8'))
        if not isinstance(records,list):raise ValueError('Invalid recovery inventory')
        import hashlib
        operation='restore-recovery:'+hashlib.sha256(recovery.read_bytes()).hexdigest()
        with self.connection(write=True) as con:
            if con.execute('SELECT 1 FROM migration_ledger WHERE operation_id=?',(operation,)).fetchone():return
            for record in records:
                con.execute("UPDATE documents SET availability='missing',tutor_state='attention',status='unavailable',generation=generation+1 WHERE id=? AND sha256=? AND size=? AND availability<>'missing'",(record['document_id'],record['sha256'],record['size']))
            con.execute("INSERT INTO migration_ledger VALUES(?,'complete',datetime('now'),'{}')",(operation,))


    def _release_unreferenced_sources(self,con,doc):
        from contextlib import closing
        from .native_document_library import LibraryError,_safe
        import sqlite3
        links=con.execute("SELECT * FROM source_links WHERE document_id=?",(doc['id'],)).fetchall()
        if not links:return
        if any(link['namespace']!='canonical' for link in links):raise LibraryError('Resolve linked sources before permanent deletion.',409)
        database=_safe(getattr(self,'_tutor_database',self.root.parent/'learning_assistant.db'))
        if not database.is_file():raise LibraryError('Linked source inventory is unavailable; file retained.',409)
        studio=_safe(self.root.parent/'learning_studio.sqlite3')
        sources={r['source_id'] for r in links}
        if studio.is_file():
            try:
                with closing(sqlite3.connect(str(studio),timeout=15)) as stored:
                    stored.execute('PRAGMA query_only=ON')
                    for (raw,) in stored.execute('SELECT package_json FROM modules'):
                        package=json.loads(raw)
                        if package.get('source',{}).get('source_id') in sources:
                            raise LibraryError('A Learning Studio lesson still uses this original. Keep the source or resolve that lesson first.',409)
            except (sqlite3.Error,ValueError) as error:
                if isinstance(error,LibraryError):raise
                raise LibraryError('Lesson references cannot be verified; file retained.',409) from error
        with closing(sqlite3.connect(str(database),timeout=15,isolation_level=None)) as academic:
            academic.execute('PRAGMA foreign_keys=ON')
            academic.execute('BEGIN IMMEDIATE')
            try:
                for source in sources:
                    for table,column,extra in [('resource_documents','document_id',''),('question_sources','document_id',''),
                         ('study_item_reading_sessions','item_identity'," AND item_kind='knowledge_document'"),
                         ('study_item_companion_entries','item_identity'," AND item_kind='knowledge_document'")]:
                        exists=academic.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
                        if exists and academic.execute('SELECT 1 FROM '+table+' WHERE '+column+'=?'+extra+' LIMIT 1',(source,)).fetchone():
                            raise LibraryError('Saved study history or resource references still use this source. Resolve them before deleting.',409)
                    if con.execute('SELECT 1 FROM source_links WHERE source_id=? AND document_id<>?',(source,doc['id'])).fetchone():
                        raise LibraryError('Another original placement still uses this source identity.',409)
                    academic.execute("UPDATE knowledge_documents SET extraction_status='unavailable',extraction_error='Original permanently deleted by owner' WHERE id=?",(source,))
                    academic.execute('DELETE FROM knowledge_chunks WHERE document_id=?',(source,))
                academic.commit()
            except BaseException:academic.rollback();raise


    def document_for_source(self,source_id,content_hash):
        with self.connection() as con:
            row=con.execute("SELECT d.* FROM documents d JOIN source_links l ON l.document_id=d.id WHERE l.namespace='canonical' AND l.source_id=? AND l.content_hash=? ORDER BY d.trashed_at IS NOT NULL,d.created_at LIMIT 1",(source_id,content_hash)).fetchone()
            return self._doc(row) if row else None
