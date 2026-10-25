"""Existing-file, read-only projection over canonical academic tables."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
import sqlite3
import os
import stat
from urllib.parse import urlsplit
from personal_learning_assistant.services.academic_wal_snapshot import AcademicSnapshotUnavailable
from personal_learning_assistant.services.academic_wal_snapshot import MAX_SNAPSHOT_BYTES, SQLITE_HEADER


class LibraryUnavailableError(RuntimeError):
    pass


class LibraryNotFoundError(LookupError):
    pass


def document_title(path_key):
    # A display basename only. Never reveal directories or URI query credentials.
    value = str(path_key or '').split('?', 1)[0].split('#', 1)[0].replace('\\', '/')
    if '://' in value or value.startswith('//'):
        try:
            value = urlsplit(value).path
        except ValueError:
            return 'Registered document'
    value = value.rstrip('/')
    return value.rsplit('/', 1)[-1] or 'Registered document'


# Validate the complete read contract even for an empty database/result.
_COLUMNS = {
    'resources': 'id,resource_type,title,canonical_uri,provider,status,updated_at,archived_at,deleted_at',
    'knowledge_documents': 'id,kind,path_key,mime_type,content_hash,extraction_status,updated_at',
    'resource_documents': 'resource_id,document_id',
    'resource_courses': 'resource_id,course_id',
    'resource_topics': 'resource_id,topic_id',
    'resource_notes': 'resource_id,note_id',
    'courses': 'id,code,name,deleted_at',
    'topics': 'id,name,deleted_at',
    'note_metadata': 'id,title,archived_at,trashed_at',
}
_ACTIVE = 'r.archived_at IS NULL AND r.deleted_at IS NULL'
_ITEMS = """
SELECT 'resource' AS kind, r.id, library_display_title('resource',r.id,r.title) AS title, r.resource_type AS item_type,
       r.provider, r.status AS learning_status, r.updated_at, '' AS extraction_status
FROM resources r WHERE """ + _ACTIVE + """
UNION ALL
SELECT 'document', d.id, library_display_title('document',d.id,library_document_title(d.path_key)), d.kind,
       '', NULL, d.updated_at, d.extraction_status
FROM knowledge_documents d
WHERE NOT EXISTS (SELECT 1 FROM resource_documents rd WHERE rd.document_id=d.id)
"""


class LearningLibraryRepository:
    def __init__(self, database_path, *, wal_snapshot_provider=None):
        self.database_path = Path(database_path)
        self.wal_snapshot_provider = wal_snapshot_provider

    @staticmethod
    def _file_stamp(info):
        # CPython 3.12 Windows path stat uses creation time for st_ctime,
        # while fstat uses the actual change time. Compare their shared birth
        # time when exposed; retain the handle's change-time check separately.
        identity_time = getattr(info, 'st_birthtime_ns', info.st_ctime_ns)
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, identity_time)

    @staticmethod
    def _source_stamp(source):
        if any(path.is_symlink() or getattr(path, 'is_junction', lambda: False)()
               for path in (source, *source.parents)):
            raise LibraryUnavailableError('Library is temporarily unavailable')
        info = source.stat()
        if not stat.S_ISREG(info.st_mode):
            raise LibraryUnavailableError('Library is temporarily unavailable')
        return LearningLibraryRepository._file_stamp(info)

    @staticmethod
    def _refuse_sidecars(source):
        if any(Path(str(source) + suffix).exists() or Path(str(source) + suffix).is_symlink()
               for suffix in ('-wal', '-shm', '-journal')):
            raise LibraryUnavailableError('Library is temporarily unavailable')

    def _capture_delete_source(self, source):
        # SQLite sees only a stable, bounded RAM image. A DELETE->WAL race can
        # never attach this read route to a live file or modify its SHM index.
        self._refuse_sidecars(source)
        before = self._source_stamp(source)
        if not 100 <= before[2] <= MAX_SNAPSHOT_BYTES:
            raise LibraryUnavailableError('Library source exceeds the safe snapshot bounds')
        with source.open('rb') as stream:
            info = os.fstat(stream.fileno())
            opened = self._file_stamp(info)
            opened_change_time = info.st_ctime_ns
            if not stat.S_ISREG(info.st_mode) or opened != before:
                raise LibraryUnavailableError('Library source changed; retry')
            payload = stream.read(MAX_SNAPSHOT_BYTES + 1)
            info = os.fstat(stream.fileno())
            after = self._file_stamp(info)
            handle_changed = info.st_ctime_ns != opened_change_time
        self._refuse_sidecars(source)
        if (handle_changed or before != after or before != self._source_stamp(source)
                or len(payload) != before[2] or not payload.startswith(SQLITE_HEADER)
                or payload[18:20] != bytes((1, 1))):
            raise LibraryUnavailableError('Library source changed or requires an owner snapshot')
        return payload

    @contextmanager
    def _read(self):
        con = None
        try:
            source = self.database_path.absolute()
            # Reject aliases to private or changing SQLite files before opening.
            # Junction rejection is necessary on Windows as well as POSIX symlinks.
            if (not source.is_file() or any(
                    path.is_symlink() or getattr(path, 'is_junction', lambda: False)()
                    for path in (source, *source.parents))):
                raise LibraryUnavailableError('Library is temporarily unavailable')
            # A DELETE-header database can still have sidecars from interrupted
            # operations. Never let a Library GET create or reconcile those files.
            if self.wal_snapshot_provider is None and any(
                    Path(str(source) + suffix).exists() or
                    Path(str(source) + suffix).is_symlink()
                    for suffix in ('-wal', '-shm', '-journal')):
                raise LibraryUnavailableError('Library is temporarily unavailable')
            # Live WAL query-only SQLite still touches the shared-memory index.
            # Reuse the validated Planning/Analysis owner snapshot instead.
            if self.wal_snapshot_provider is not None:
                from personal_learning_assistant.services.academic_overview_service import AcademicOverviewService
                owner_reader = AcademicOverviewService(
                    self.database_path, wal_snapshot_provider=self.wal_snapshot_provider)
                con = owner_reader._open_authorized_wal_snapshot(
                    {'limits': []}, datetime.now(timezone.utc))
            else:
                payload = self._capture_delete_source(source)
                con = sqlite3.connect(':memory:', isolation_level=None)
                con.deserialize(payload)
            con.row_factory = sqlite3.Row
            con.create_function('library_document_title', 1, document_title, deterministic=True)
            from .library_display_repository import LibraryDisplayRepository
            titles = LibraryDisplayRepository(self.database_path).titles()
            con.create_function('library_display_title', 3,
                lambda kind, ident, fallback: titles.get((kind,ident),fallback), deterministic=True)
            con.create_function('library_casefold', 1, lambda value: str(value or '').casefold(), deterministic=True)
            con.execute('PRAGMA query_only=ON')
            if not con.in_transaction:
                con.execute('BEGIN')
            for table, columns in _COLUMNS.items():
                con.execute(f'SELECT {columns} FROM {table} LIMIT 0')
            yield con
        except (sqlite3.Error, OSError, ValueError, AcademicSnapshotUnavailable) as exc:
            raise LibraryUnavailableError('Library is temporarily unavailable') from exc
        finally:
            if con is not None:
                con.close()

    @staticmethod
    def _relations(con, ids):
        result = {rid: {'courses': [], 'topics': [], 'documents': [], 'notes': []} for rid in ids}
        if not ids:
            return result
        placeholders = ','.join('?' for _ in ids)
        queries = {
            'courses': "SELECT DISTINCT x.resource_id, c.id, c.code || ' · ' || c.name AS label "
                       'FROM resource_courses x JOIN courses c ON c.id=x.course_id '
                       f'WHERE x.resource_id IN ({placeholders}) AND c.deleted_at IS NULL '
                       'ORDER BY label COLLATE NOCASE, c.id',
            'topics': 'SELECT DISTINCT x.resource_id, t.id, t.name AS label '
                      'FROM resource_topics x JOIN topics t ON t.id=x.topic_id '
                      f'WHERE x.resource_id IN ({placeholders}) AND t.deleted_at IS NULL '
                      'ORDER BY label COLLATE NOCASE, t.id',
            'notes': 'SELECT DISTINCT x.resource_id, n.id, n.title AS label '
                     'FROM resource_notes x JOIN note_metadata n ON n.id=x.note_id '
                     f'WHERE x.resource_id IN ({placeholders}) '
                     'AND n.archived_at IS NULL AND n.trashed_at IS NULL '
                     'ORDER BY label COLLATE NOCASE, n.id',
            'documents': 'SELECT DISTINCT x.resource_id, d.id, d.kind, d.path_key, d.mime_type, '
                         'd.content_hash, d.extraction_status '
                         'FROM resource_documents x JOIN knowledge_documents d ON d.id=x.document_id '
                         f'WHERE x.resource_id IN ({placeholders}) '
                         'ORDER BY library_document_title(d.path_key) COLLATE NOCASE, d.id',
        }
        for name, sql in queries.items():
            for row in con.execute(sql, ids):
                result[row['resource_id']][name].append(dict(row))
        return result

    def list_items(self, query):
        with self._read() as con:
            where, params = [], []
            if query.item_kind != 'all':
                where.append('i.kind=?')
                params.append(query.item_kind)
            if query.course_id:
                where.append("i.kind='resource' AND EXISTS (SELECT 1 FROM resource_courses rc "
                             'JOIN courses c ON c.id=rc.course_id WHERE rc.resource_id=i.id '
                             'AND c.id=? AND c.deleted_at IS NULL)')
                params.append(query.course_id)
            if query.search.strip():
                where.append('(instr(library_casefold(i.title), ?) > 0 OR '
                             'instr(library_casefold(i.provider), ?) > 0 OR '
                             'instr(library_casefold(i.item_type), ?) > 0 OR '
                             "(i.kind='resource' AND EXISTS (SELECT 1 FROM resource_documents rd "
                             'JOIN knowledge_documents d ON d.id=rd.document_id WHERE rd.resource_id=i.id AND '
                             "instr(library_casefold(library_display_title('document',d.id,'')),?)>0)))")
                params.extend([query.search.strip().casefold()] * 4)
            filtered = 'SELECT * FROM (' + _ITEMS + ') i' + (' WHERE ' + ' AND '.join(where) if where else '')
            total_all = con.execute('SELECT COUNT(*) FROM (' + _ITEMS + ')').fetchone()[0]
            total = con.execute('SELECT COUNT(*) FROM (' + filtered + ')', params).fetchone()[0]
            rows = [dict(row) for row in con.execute(
                filtered + ' ORDER BY updated_at DESC, title COLLATE NOCASE, kind, id LIMIT ? OFFSET ?',
                params + [query.page_size, (query.page - 1) * query.page_size])]
            relations = self._relations(con, [r['id'] for r in rows if r['kind'] == 'resource'])
            courses = [dict(r) for r in con.execute(
                "SELECT DISTINCT c.id, c.code || ' · ' || c.name AS label FROM courses c "
                'JOIN resource_courses rc ON c.id=rc.course_id JOIN resources r ON r.id=rc.resource_id '
                'WHERE c.deleted_at IS NULL AND ' + _ACTIVE + ' ORDER BY label COLLATE NOCASE,c.id')]
            return rows, relations, courses, total, total_all

    def resource_detail(self, resource_id):
        with self._read() as con:
            row = con.execute("SELECT r.id,library_display_title('resource',r.id,r.title) AS title,r.resource_type,r.provider,r.status,r.updated_at,"
                              'r.canonical_uri FROM resources r WHERE r.id=? AND ' + _ACTIVE,
                              (resource_id,)).fetchone()
            if row is None:
                raise LibraryNotFoundError('Resource was not found')
            relations = self._relations(con, [resource_id])[resource_id]
            for document in relations['documents']:
                document['display_title'] = con.execute(
                    "SELECT library_display_title('document',?,?)",
                    (document['id'],document_title(document['path_key']))).fetchone()[0]
            return dict(row), relations

    def original_title(self, kind, item_id):
        with self._read() as con:
            if kind == 'document':
                row = con.execute('SELECT path_key FROM knowledge_documents WHERE id=?',(item_id,)).fetchone()
                if row is not None:
                    return document_title(row[0])
            elif kind == 'resource':
                row = con.execute('SELECT r.title FROM resources r WHERE r.id=? AND '+_ACTIVE,(item_id,)).fetchone()
                if row is not None:
                    return row[0]
            raise LibraryNotFoundError('Material was not found')

    def title_exists(self, title, *, kind, item_id):
        with self._read() as con:
            return con.execute(
                "SELECT 1 FROM knowledge_documents d WHERE d.id<>? AND library_casefold("
                "library_display_title('document',d.id,library_document_title(d.path_key)))=? "
                "UNION ALL SELECT 1 FROM resources r WHERE r.id<>? AND "+_ACTIVE+
                " AND library_casefold(library_display_title('resource',r.id,r.title))=? LIMIT 1",
                (item_id if kind=='document' else '',title.casefold(),
                 item_id if kind=='resource' else '',title.casefold())).fetchone() is not None
