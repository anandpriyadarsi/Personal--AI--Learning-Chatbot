"""Existing-file, read-only projection over canonical academic tables."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3


class LibraryUnavailableError(RuntimeError):
    pass


class LibraryNotFoundError(LookupError):
    pass


def document_title(path_key):
    # A display basename only. Never reveal directories or URI query credentials.
    value = str(path_key or '').replace('\\', '/').rstrip('/')
    return value.rsplit('/', 1)[-1].split('?', 1)[0].split('#', 1)[0] or 'Registered document'


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
SELECT 'resource' AS kind, r.id, r.title, r.resource_type AS item_type,
       r.provider, r.status AS learning_status, r.updated_at, '' AS extraction_status
FROM resources r WHERE """ + _ACTIVE + """
UNION ALL
SELECT 'document', d.id, library_document_title(d.path_key), d.kind,
       '', NULL, d.updated_at, d.extraction_status
FROM knowledge_documents d
WHERE NOT EXISTS (SELECT 1 FROM resource_documents rd WHERE rd.document_id=d.id)
"""


class LearningLibraryRepository:
    def __init__(self, database_path):
        self.database_path = Path(database_path)

    @contextmanager
    def _read(self):
        con = None
        try:
            if not self.database_path.is_file() or self.database_path.is_symlink():
                raise LibraryUnavailableError('Library is temporarily unavailable')
            con = sqlite3.connect(self.database_path.resolve().as_uri() + '?mode=ro',
                                  uri=True, isolation_level=None, timeout=5)
            con.row_factory = sqlite3.Row
            con.create_function('library_document_title', 1, document_title, deterministic=True)
            con.execute('PRAGMA query_only=ON')
            con.execute('BEGIN')
            for table, columns in _COLUMNS.items():
                con.execute(f'SELECT {columns} FROM {table} LIMIT 0')
            yield con
        except (sqlite3.Error, OSError, ValueError) as exc:
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
            row = con.execute('SELECT r.id,r.title,r.resource_type,r.provider,r.status,r.updated_at,'
                              'r.canonical_uri FROM resources r WHERE r.id=? AND ' + _ACTIVE,
                              (resource_id,)).fetchone()
            if row is None:
                raise LibraryNotFoundError('Resource was not found')
            return dict(row), self._relations(con, [resource_id])[resource_id]
