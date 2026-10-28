"""Original-file Library, independent of academic/lesson ownership.

The additive sidecar is disposable only for its page index, NEVER its document
metadata. Original blobs are immutable and shared by explicitly copied records.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Lock, RLock, Thread
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import uuid
from .native_document_extraction import extract_pages, normalize

MAX_UPLOAD = 100 * 1024 * 1024
MIMES = {'pdf': 'application/pdf', 'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation', 'ppt': 'application/vnd.ms-powerpoint'}
_root_locks = {}
_root_locks_guard = Lock()


def storage_lock(root):
    with _root_locks_guard:
        return _root_locks.setdefault(str(Path(root).absolute()), RLock())


FTS_SQL = 'CREATE VIRTUAL TABLE IF NOT EXISTS page_fts USING fts5(document_id UNINDEXED, position UNINDEXED, text, tokenize="unicode61 remove_diacritics 0")'


class LibraryError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def label(value, *, maximum=255, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()) or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise LibraryError('Supply a valid name or label.')
    return value.strip()


def _safe(path):
    if any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)() for p in (path, *path.parents)):
        raise LibraryError('Library storage must use regular, private paths.', 409)
    return path


def document_filename(doc):
    """Current user name, with the immutable original's actual format suffix."""
    name = re.sub(r'[/\\\x00-\x1f]', '_', doc['display_name']).strip().strip('.') or 'Document'
    extension = '.' + doc['kind']
    if name.lower().endswith(extension): return name
    if name.rsplit('.', 1)[-1].lower() in MIMES: name = name.rsplit('.', 1)[0]
    return name[:255-len(extension)] + extension


def _verified_original(root, doc):
    digest = doc['sha256']
    if not re.fullmatch('[0-9a-f]{64}', digest): raise LibraryError('Invalid storage identity.', 409)
    path = _safe(root/'blobs'/digest)
    try:
        if not path.is_file() or path.stat().st_size != doc['size']:
            raise LibraryError('Original file is missing or changed. Restore a backup.', 409)
        actual = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024*1024), b''): actual.update(chunk)
        if actual.hexdigest() != digest:
            raise LibraryError('Original integrity check failed. Restore a backup.', 409)
    except OSError as error:
        raise LibraryError('Original file is unavailable.', 409) from error
    return path


def resolve_android_document(root_path, document_id):
    """Native-only read: resolve one stable ID without indexing or copying bytes.

    The caller runs this off the UI thread. Private paths never cross into the
    WebView or the viewer intent. A read-only connection avoids starting workers,
    initializing schema, or resetting an in-progress index during a view action.
    """
    if not isinstance(document_id, str) or not re.fullmatch('[0-9a-f]{32}', document_id):
        raise LibraryError('Invalid document identity.', 404)
    root = _safe(Path(root_path).absolute()/'data/native_library')
    database = _safe(root/'library.sqlite3')
    with storage_lock(root):
        try:
            # The Android embedded SQLite driver cannot reliably open the
            # URI-mode read-only connection used by desktop Python. Check
            # existence before opening so an unavailable Library is never
            # silently initialized. query_only keeps this view non-mutating.
            if not database.is_file():
                raise LibraryError('Original file is unavailable.', 409)
            con = sqlite3.connect(str(database), timeout=15)
            con.row_factory = sqlite3.Row
            try:
                con.execute('PRAGMA query_only=ON')
                doc = NativeDocumentLibrary._doc(con.execute('SELECT * FROM documents WHERE id=?', (document_id,)).fetchone())
                return [str(_verified_original(root, doc)), doc['mime'], document_filename(doc)]
            finally: con.close()
        except (sqlite3.Error, OSError) as error:
            raise LibraryError('Original file is unavailable.', 409) from error


class NativeDocumentLibrary:
    def __init__(self, root, *, autostart=True):
        self.root = _safe(Path(root).absolute())
        self.database = self.root/'library.sqlite3'
        self._lock, self._worker_lock = storage_lock(self.root), Lock()
        self._wake, self._stop = Event(), Event()
        self._thread = None
        self._job_cancel = {}
        for directory in (self.root, self.root/'blobs', self.root/'tmp'):
            _safe(directory).mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connection(write=True) as con:
            version = con.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0,1):
                raise LibraryError('This Library needs a newer ANVAYA version.',409)
            con.executescript('''
                CREATE TABLE IF NOT EXISTS folders(id TEXT PRIMARY KEY, name TEXT NOT NULL, parent_id TEXT REFERENCES folders(id));
                CREATE TABLE IF NOT EXISTS documents(
                    id TEXT PRIMARY KEY, original_name TEXT NOT NULL, display_name TEXT NOT NULL,
                    kind TEXT NOT NULL, sha256 TEXT NOT NULL, size INTEGER NOT NULL,
                    folder_id TEXT REFERENCES folders(id), subject_id TEXT, topic TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '[]', indexing_enabled INTEGER NOT NULL DEFAULT 1,
                    ocr INTEGER NOT NULL DEFAULT 0, generation INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'stored', status_detail TEXT NOT NULL DEFAULT '',
                    position_count INTEGER NOT NULL DEFAULT 0, indexed_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS documents_scope ON documents(folder_id,subject_id);
                CREATE INDEX IF NOT EXISTS documents_jobs ON documents(status);
                CREATE TABLE IF NOT EXISTS pages(id INTEGER PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL, text TEXT NOT NULL, UNIQUE(document_id,position));
                PRAGMA user_version=1;
            ''')
            self._ensure_index(con)
            con.execute("UPDATE documents SET status='stored' WHERE status='indexing'")
        try: os.chmod(self.database, 0o600)
        except OSError: pass
        if autostart:
            self._thread = Thread(target=self._work, name='anvaya-file-index', daemon=True)
            self._thread.start()
            self._wake.set()

    def _ensure_index(self, con):
        existing = con.execute("SELECT sql FROM sqlite_master WHERE name='page_fts'").fetchone()
        if existing is None:
            try: con.execute(FTS_SQL)
            except sqlite3.OperationalError as error:
                if 'no such module' not in str(error): raise
                con.execute('CREATE TABLE page_fts(rowid INTEGER PRIMARY KEY,document_id TEXT,position INTEGER,text TEXT)')
        schema = con.execute("SELECT sql FROM sqlite_master WHERE name='page_fts'").fetchone()[0]
        self.fts_enabled = 'VIRTUAL TABLE' in schema.upper()

    @contextmanager
    def connection(self, *, write=False):
        _safe(self.database)
        with self._lock:
            con = sqlite3.connect(self.database, timeout=15)
            con.row_factory = sqlite3.Row
            con.create_function('library_normalize', 1, normalize)
            con.execute('PRAGMA secure_delete=ON')
            con.execute('PRAGMA foreign_keys=ON')
            try:
                if write: con.execute('BEGIN IMMEDIATE')
                yield con
                if write: con.commit()
            except BaseException:
                if write: con.rollback()
                raise
            finally:
                con.close()

    def close(self):
        self._stop.set(); self._wake.set()
        if self._thread: self._thread.join(timeout=2)

    def _work(self):
        while not self._stop.is_set():
            self._wake.wait(10); self._wake.clear()
            if self._stop.is_set(): return
            try: self.run_pending()
            except (sqlite3.Error, OSError, LibraryError):
                # Keep the worker alive; content or local paths never enter logs.
                continue

    def _folder(self, con, folder_id):
        if folder_id is not None and not con.execute('SELECT 1 FROM folders WHERE id=?', (folder_id,)).fetchone():
            raise LibraryError('Folder not found.', 404)

    @staticmethod
    def _doc(row):
        if row is None: raise LibraryError('Document not found.', 404)
        doc = dict(row); doc['tags'] = json.loads(doc['tags']); doc['mime'] = MIMES[doc['kind']]
        return doc

    def get(self, document_id):
        with self.connection() as con:
            return self._doc(con.execute('SELECT * FROM documents WHERE id=?', (document_id,)).fetchone())

    def _blob(self, digest):
        if not re.fullmatch('[0-9a-f]{64}', digest): raise LibraryError('Invalid storage identity.', 409)
        return _safe(self.root/'blobs'/digest)

    def original(self, document_id):
        return _verified_original(self.root, self.get(document_id))

    def upload(self, stream, filename, *, folder_id=None, subject_id=None, indexing=True):
        filename = label(filename)
        if '/' in filename or '\\' in filename or filename in ('.','..'):
            raise LibraryError('Choose a filename without directory separators.')
        kind = filename.rsplit('.', 1)[-1].lower()
        if kind not in MIMES: raise LibraryError('Choose a PDF, PPTX or PPT file.')
        digest, size, prefix = hashlib.sha256(), 0, b''
        handle, temporary = tempfile.mkstemp(dir=_safe(self.root/'tmp'))
        temporary = Path(temporary)
        try:
            with os.fdopen(handle, 'wb') as output:
                while True:
                    chunk = stream.read(256*1024)
                    if not chunk: break
                    size += len(chunk)
                    if size > MAX_UPLOAD: raise LibraryError('File exceeds 100 MiB.', 413)
                    if len(prefix) < 1024: prefix += chunk[:1024-len(prefix)]
                    digest.update(chunk); output.write(chunk)
                output.flush(); os.fsync(output.fileno())
            valid = (kind == 'pdf' and b'%PDF-' in prefix[:1024]) or (kind == 'pptx' and prefix.startswith(b'PK\x03\x04')) or (kind == 'ppt' and prefix.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'))
            if not valid: raise LibraryError('The file does not match its document format.')
            sha = digest.hexdigest(); document_id = uuid.uuid4().hex
            with self.connection(write=True) as con:
                self._folder(con, folder_id)
                duplicate = con.execute('SELECT * FROM documents WHERE sha256=? AND original_name=?', (sha, filename)).fetchone()
                blob = self._blob(sha)
                try: _verified_original(self.root, {'sha256':sha, 'size':size})
                except LibraryError:
                    # The incoming stream is fully hashed and synced. Re-import
                    # can repair a missing/damaged shared blob without losing IDs.
                    os.replace(temporary, blob)
                    if os.name != 'nt':
                        directory_fd = os.open(blob.parent, os.O_RDONLY)
                        try: os.fsync(directory_fd)
                        finally: os.close(directory_fd)
                if duplicate: return self._doc(duplicate)
                con.execute('''INSERT INTO documents(id,original_name,display_name,kind,sha256,size,folder_id,subject_id,indexing_enabled,status,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''', (document_id, filename, filename, kind, sha, size, folder_id, subject_id,
                    int(indexing), 'stored' if indexing else 'disabled', now(), now()))
            self._wake.set()
            return self.get(document_id)
        finally:
            temporary.unlink(missing_ok=True)

    def folders(self):
        with self.connection() as con:
            return [dict(row) for row in con.execute('SELECT * FROM folders ORDER BY name COLLATE NOCASE')]

    def create_folder(self, name, parent_id=None):
        name = label(name); identity = uuid.uuid4().hex
        with self.connection(write=True) as con:
            self._folder(con, parent_id)
            con.execute('INSERT INTO folders VALUES(?,?,?)', (identity, name, parent_id))
        return {'id':identity, 'name':name, 'parent_id':parent_id}

    def update_folder(self, folder_id, name, parent_id):
        name = label(name)
        with self.connection(write=True) as con:
            self._folder(con, folder_id); self._folder(con, parent_id)
            current = parent_id
            for _ in range(100):
                if current is None: break
                if current == folder_id: raise LibraryError('A folder cannot be moved inside itself.')
                current = con.execute('SELECT parent_id FROM folders WHERE id=?', (current,)).fetchone()[0]
            else: raise LibraryError('Folder nesting is limited to 100 levels.')
            con.execute('UPDATE folders SET name=?,parent_id=? WHERE id=?', (name, parent_id, folder_id))

    def delete_folder(self, folder_id):
        with self.connection(write=True) as con:
            self._folder(con, folder_id)
            if con.execute('SELECT 1 FROM folders WHERE parent_id=? UNION ALL SELECT 1 FROM documents WHERE folder_id=? LIMIT 1', (folder_id, folder_id)).fetchone():
                raise LibraryError('Move files and subfolders out before deleting this folder.', 409)
            con.execute('DELETE FROM folders WHERE id=?', (folder_id,))

    def update(self, document_id, **fields):
        allowed = {'display_name','folder_id','subject_id','topic','tags'}
        if not fields or set(fields) - allowed: raise LibraryError('Invalid document fields.')
        if 'display_name' in fields:
            fields['display_name'] = label(fields['display_name'])
            if '/' in fields['display_name'] or '\\' in fields['display_name'] or fields['display_name'] in ('.', '..'):
                raise LibraryError('Choose a filename without directory separators.')
        if 'topic' in fields: fields['topic'] = label(fields['topic'], empty=True)
        if 'subject_id' in fields and fields['subject_id'] is not None: fields['subject_id'] = label(fields['subject_id'], maximum=150)
        if 'tags' in fields:
            tags = fields['tags']
            if not isinstance(tags,list) or len(tags)>30: raise LibraryError('Use at most 30 tags.')
            fields['tags'] = json.dumps([label(t, maximum=80) for t in tags])
        with self.connection(write=True) as con:
            self._doc(con.execute('SELECT * FROM documents WHERE id=?',(document_id,)).fetchone())
            if 'folder_id' in fields: self._folder(con, fields['folder_id'])
            fields['updated_at'] = now()
            con.execute('UPDATE documents SET '+','.join(k+'=?' for k in fields)+' WHERE id=?', (*fields.values(),document_id))
        return self.get(document_id)

    def copy(self, document_id):
        with self.connection(write=True) as con:
            doc = self._doc(con.execute('SELECT * FROM documents WHERE id=?',(document_id,)).fetchone())
            doc.pop('mime'); doc['tags'] = json.dumps(doc['tags']); doc['id'] = uuid.uuid4().hex
            doc['display_name'] = doc['display_name'][:240] + ' (copy)'
            doc['created_at'] = doc['updated_at'] = now()
            doc['status'] = 'stored' if doc['indexing_enabled'] else 'disabled'
            doc['position_count'] = doc['indexed_count'] = 0
            con.execute('INSERT INTO documents('+','.join(doc)+') VALUES('+','.join('?' for _ in doc)+')', tuple(doc.values()))
        self._wake.set()
        return self.get(doc['id'])

    def _cancel_job(self, document_id=None):
        for identity, event in self._job_cancel.items():
            if document_id is None or identity == document_id: event.set()

    def _remove_index(self, con, document_id, *, purge=False):
        con.execute('DELETE FROM page_fts WHERE document_id=?', (document_id,))
        con.execute('DELETE FROM pages WHERE document_id=?', (document_id,))
        if purge and self.fts_enabled:
            # FTS5 inverted segments may retain deleted terms. Rebuild from its
            # surviving content under secure_delete on explicit privacy actions.
            con.execute("INSERT INTO page_fts(page_fts) VALUES('rebuild')")

    def delete(self, document_id):
        with self.connection(write=True) as con:
            doc = self._doc(con.execute('SELECT * FROM documents WHERE id=?',(document_id,)).fetchone())
            self._cancel_job(document_id)
            self._remove_index(con, document_id, purge=True)
            con.execute('DELETE FROM documents WHERE id=?', (document_id,))
            if not con.execute('SELECT 1 FROM documents WHERE sha256=?', (doc['sha256'],)).fetchone():
                # Commit metadata first: a crash can orphan a blob, never a live reference.
                con.commit()
                # Retain write transaction while checking again against concurrent upload.
                con.execute('BEGIN IMMEDIATE')
                if not con.execute('SELECT 1 FROM documents WHERE sha256=?',(doc['sha256'],)).fetchone():
                    self._blob(doc['sha256']).unlink(missing_ok=True)

    def set_indexing(self, document_id, enabled):
        if type(enabled) is not bool: raise LibraryError('Indexing flag must be a boolean.')
        with self.connection(write=True) as con:
            self._doc(con.execute('SELECT * FROM documents WHERE id=?',(document_id,)).fetchone())
            self._cancel_job(document_id)
            self._remove_index(con, document_id, purge=True)
            con.execute("UPDATE documents SET indexing_enabled=?,generation=generation+1,status=?,position_count=0,indexed_count=0,status_detail='' WHERE id=?",
                        (int(enabled), 'stored' if enabled else 'disabled', document_id))
        self._wake.set()

    def rebuild(self, document_id=None, *, ocr=False):
        with self.connection(write=True) as con:
            if document_id: self._doc(con.execute('SELECT * FROM documents WHERE id=?',(document_id,)).fetchone())
            self._cancel_job(document_id)
            if document_id is None:
                con.execute('DROP TABLE IF EXISTS page_fts'); self._ensure_index(con); con.execute('DELETE FROM pages')
            else: self._remove_index(con, document_id)
            con.execute("UPDATE documents SET generation=generation+1,status=CASE WHEN indexing_enabled=1 THEN 'stored' ELSE 'disabled' END,ocr=?,position_count=0,indexed_count=0,status_detail=''"+
                        (' WHERE id=?' if document_id else ''), (int(ocr), document_id) if document_id else (int(ocr),))
        self._wake.set()

    def _extract(self, doc):
        return extract_pages(self.original(doc['id']), doc['kind'], ocr=bool(doc['ocr']),
                             cancelled=self._job_cancel[doc['id']].is_set)

    def run_pending(self):
        if not self._worker_lock.acquire(blocking=False): return
        try:
            while not self._stop.is_set():
                with self.connection(write=True) as con:
                    row = con.execute("SELECT * FROM documents WHERE status='stored' AND indexing_enabled=1 ORDER BY created_at LIMIT 1").fetchone()
                    if row is None: return
                    doc = self._doc(row)
                    self._job_cancel[doc['id']] = Event()
                    con.execute("UPDATE documents SET status='indexing' WHERE id=?", (doc['id'],))
                try:
                    pages, status, detail = self._extract(doc)
                except Exception:
                    pages, status, detail = [], 'failed', 'Indexing failed or exceeded local resource limits. Original preserved; retry or use an external viewer.'
                with self.connection(write=True) as con:
                    self._job_cancel.pop(doc['id'],None)
                    current = con.execute('SELECT generation,indexing_enabled FROM documents WHERE id=?',(doc['id'],)).fetchone()
                    if current is None or current['generation'] != doc['generation'] or not current['indexing_enabled']: continue
                    self._remove_index(con, doc['id'])
                    indexed = 0
                    for position, text in pages:
                        normalized = normalize(text)
                        if not normalized: continue
                        indexed += 1
                        cursor = con.execute('INSERT INTO pages(document_id,position,text) VALUES(?,?,?)',(doc['id'], position, text))
                        con.execute('INSERT INTO page_fts(rowid,document_id,position,text) VALUES(?,?,?,?)',(cursor.lastrowid, doc['id'], position, normalized))
                    con.execute('UPDATE documents SET status=?,status_detail=?,position_count=?,indexed_count=? WHERE id=?',
                                (status, detail, len(pages), indexed, doc['id']))
        finally: self._worker_lock.release()

    def _scope(self, con, folder_id=None, subject_id=None, document_id=None):
        clauses, args = [], []
        if folder_id:
            self._folder(con, folder_id)
            clauses.append('d.folder_id IN (WITH RECURSIVE tree(id) AS (SELECT ? UNION SELECT f.id FROM folders f JOIN tree t ON f.parent_id=t.id) SELECT id FROM tree)')
            args.append(folder_id)
        if subject_id: clauses.append('d.subject_id=?'); args.append(subject_id)
        if document_id: clauses.append('d.id=?'); args.append(document_id)
        return (' AND '+' AND '.join(clauses) if clauses else ''), args

    def search(self, query, *, folder_id=None, subject_id=None, document_id=None, offset=0, limit=50):
        if len(query)>500: raise LibraryError('Search is limited to 500 characters.')
        normalized = normalize(query)
        if not normalized: return []
        limit, offset = min(100,max(1,int(limit))), max(0,int(offset))
        with self.connection() as con:
            scope, args = self._scope(con, folder_id, subject_id, document_id)
            phrase = '"'+normalized+'"'
            rank_sql = 'bm25(page_fts)' if self.fts_enabled else '0.0'
            match_sql = 'page_fts MATCH ?' if self.fts_enabled else "instr(' ' || page_fts.text || ' ', ?) > 0"
            # One ranked union keeps pagination stable when a file also matches
            # by metadata. Both name and content hits count toward the page.
            try:
                rows = con.execute("""SELECT * FROM (
                    SELECT d.*, NULL AS position, '' AS passage, -1000000.0 AS rank
                    FROM documents d WHERE ?=1 AND instr(' ' || library_normalize(d.display_name || ' ' || d.original_name || ' ' || d.topic || ' ' || d.tags) || ' ', ?) > 0"""+scope+"""
                    UNION ALL
                    SELECT d.*,p.position,p.text AS passage,"""+rank_sql+""" AS rank FROM page_fts
                    JOIN pages p ON p.id=page_fts.rowid JOIN documents d ON d.id=p.document_id
                    WHERE """+match_sql+""" AND d.indexing_enabled=1"""+scope+
                    ' ) ORDER BY rank,updated_at DESC,position LIMIT ? OFFSET ?',
                    (int(not bool(document_id)),' '+normalized+' ',*args,phrase if self.fts_enabled else ' '+normalized+' ',*args,limit,offset)).fetchall()
            except sqlite3.DatabaseError as error:
                raise LibraryError('Search index unavailable. Use Rebuild Search Index; originals are preserved.',409) from error
            hits = []
            for row in rows:
                doc = self._doc(row); passage = doc.pop('passage')
                if doc['position'] is None:
                    doc.update(snippet='Document name, topic or tags',match_kind='metadata')
                else:
                    at = passage.casefold().find(normalized.split()[0])
                    start = max(0, at-65)
                    doc['snippet'] = ('…' if start else '') + passage[start:start+240] + ('…' if len(passage)>start+240 else '')
                    doc['match_kind'] = 'content'
                hits.append(doc)
            return hits

    def list_documents(self, *, folder_id=None, subject_id=None, kind=None, sort='newest', page=1, page_size=30):
        order = {'newest':'d.created_at DESC','name':'d.display_name COLLATE NOCASE','size':'d.size DESC'}.get(sort)
        if not order: raise LibraryError('Choose a valid sort order.')
        if kind and kind not in MIMES: raise LibraryError('Choose a valid file type.')
        page, page_size = int(page), int(page_size)
        if not 1<=page<=100000 or not 1<=page_size<=100: raise LibraryError('Choose a valid page.')
        with self.connection() as con:
            # Browse a folder's direct children; search includes descendants.
            scope, args = self._scope(con, subject_id=subject_id)
            if folder_id:
                self._folder(con,folder_id); scope+=' AND d.folder_id=?';args.append(folder_id)
            else: scope+=' AND d.folder_id IS NULL'
            if kind: scope+=' AND d.kind=?';args.append(kind)
            total = con.execute('SELECT count(*) FROM documents d WHERE 1=1'+scope,args).fetchone()[0]
            rows = con.execute('SELECT d.* FROM documents d WHERE 1=1'+scope+' ORDER BY '+order+' LIMIT ? OFFSET ?',(*args,page_size,(page-1)*page_size)).fetchall()
            return {'items':[self._doc(r) for r in rows], 'total':total,'page':page,'page_size':page_size}
