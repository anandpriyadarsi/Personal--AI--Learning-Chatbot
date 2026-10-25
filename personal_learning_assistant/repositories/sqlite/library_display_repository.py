"""Optional local display names; never modify canonical academic/source records."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import unicodedata
from urllib.parse import quote

APPLICATION_ID = 0x414C4431


def validate_title(value):
    if not isinstance(value, str):
        raise ValueError('Enter a document name.')
    title = unicodedata.normalize('NFC', value.strip())
    if not 1 <= len(title) <= 160:
        raise ValueError('Use a name between 1 and 160 characters.')
    if any(unicodedata.category(c).startswith('C') or c in '<>/\\' for c in title):
        raise ValueError('Names cannot contain control characters, angle brackets or path separators.')
    return title


class LibraryDisplayRepository:
    def __init__(self, database_path):
        self.source = Path(database_path).absolute()
        self.path = self.source.with_name(self.source.name + '.display.sqlite3')

    def _safe(self):
        from .learning_library_repository import LibraryUnavailableError
        for path in (self.source, self.path):
            if any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)()
                   for p in (path, *path.parents)):
                raise LibraryUnavailableError('Library names are temporarily unavailable')
            if path.exists() and (not path.is_file() or path.stat().st_nlink != 1):
                raise LibraryUnavailableError('Library names are temporarily unavailable')
        if any(Path(str(self.path)+suffix).exists() or Path(str(self.path)+suffix).is_symlink()
               for suffix in ('-wal','-shm','-journal')):
            raise LibraryUnavailableError('Library names are temporarily unavailable')

    @contextmanager
    def connection(self, *, write=False):
        from .learning_library_repository import LibraryUnavailableError
        self._safe()
        if not self.path.exists() and not write:
            yield None
            return
        if write and not self.source.is_file():
            raise LibraryUnavailableError('Library is temporarily unavailable')
        con = None
        try:
            if write:
                if self.path.exists():
                    with self.path.open('rb') as stream:
                        header=stream.read(20)
                    if len(header)!=20 or header[18:20]!=bytes((1,1)):
                        raise LibraryUnavailableError('Library names are temporarily unavailable')
                con = sqlite3.connect('file:'+quote(self.path.as_posix(),safe='/:')+'?mode=rwc',
                                     uri=True,timeout=5,isolation_level=None)
            else:
                from .learning_library_repository import LearningLibraryRepository
                payload=LearningLibraryRepository(self.path)._capture_delete_source(self.path)
                con=sqlite3.connect(':memory:',isolation_level=None)
                con.deserialize(payload)
            if write:
                con.execute('BEGIN IMMEDIATE')
            app_id = con.execute('PRAGMA application_id').fetchone()[0]
            if app_id == 0 and write:
                if con.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():
                    raise LibraryUnavailableError('Library names are temporarily unavailable')
                con.execute('CREATE TABLE display_titles(kind TEXT NOT NULL, item_id TEXT NOT NULL, '
                            'title TEXT NOT NULL, PRIMARY KEY(kind,item_id))')
                con.execute(f'PRAGMA application_id={APPLICATION_ID}')
                con.execute('PRAGMA user_version=1')
            if (con.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID or
                    con.execute('PRAGMA user_version').fetchone()[0] != 1):
                raise LibraryUnavailableError('Library names are temporarily unavailable')
            if not write:
                con.execute('PRAGMA query_only=ON')
            yield con
            if write:
                con.commit()
        except (sqlite3.Error, OSError) as error:
            raise LibraryUnavailableError('Library names are temporarily unavailable') from error
        finally:
            if con is not None:
                con.close()

    def titles(self):
        with self.connection() as con:
            return {} if con is None else {(kind, ident): title for kind, ident, title in
                con.execute('SELECT kind,item_id,title FROM display_titles')}

    def rename(self, kind, item_id, title, *, expected_title, original_title):
        title = validate_title(title)
        with self.connection(write=True) as con:
            row = con.execute('SELECT title FROM display_titles WHERE kind=? AND item_id=?',
                              (kind,item_id)).fetchone()
            current = row[0] if row else original_title
            if current != expected_title:
                raise ValueError('This name changed. Reload the Library and try again.')
            duplicate = any(other.casefold() == title.casefold() for (other,) in con.execute(
                'SELECT title FROM display_titles WHERE NOT (kind=? AND item_id=?)',(kind,item_id)))
            con.execute('INSERT INTO display_titles VALUES(?,?,?) ON CONFLICT(kind,item_id) '
                        'DO UPDATE SET title=excluded.title',(kind,item_id,title))
        return {'title':title,'duplicate':duplicate}


def connection_titles(connection):
    """Resolve the same local overlay for existing Knowledge metadata readers."""
    rows = connection.execute('PRAGMA database_list').fetchall()
    source = next((r[2] for r in rows if r[1] == 'main'), '')
    return LibraryDisplayRepository(source).titles() if source else {}
