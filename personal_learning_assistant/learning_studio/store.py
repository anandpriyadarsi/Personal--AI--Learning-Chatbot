"""Dedicated transactional artifact/evidence store, never a shared academic migration."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from urllib.parse import quote
from .validation import PackageError, require

APPLICATION_ID = 0x414C5331
DDL = '''
CREATE TABLE modules(
 module_id TEXT NOT NULL, revision INTEGER NOT NULL, digest TEXT NOT NULL,
 title TEXT NOT NULL, unit TEXT NOT NULL, course_id TEXT, topic_name TEXT,
 package_json TEXT NOT NULL, source_blob BLOB NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(module_id,revision));
CREATE TABLE assets(
 module_id TEXT NOT NULL, revision INTEGER NOT NULL, name TEXT NOT NULL, bytes BLOB NOT NULL,
 PRIMARY KEY(module_id,revision,name),
 FOREIGN KEY(module_id,revision) REFERENCES modules(module_id,revision));
CREATE TABLE publications(
 module_id TEXT NOT NULL, revision INTEGER NOT NULL, published_at TEXT NOT NULL,
 PRIMARY KEY(module_id,revision),
 FOREIGN KEY(module_id,revision) REFERENCES modules(module_id,revision));
CREATE TABLE active_modules(
 module_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
 FOREIGN KEY(module_id,revision) REFERENCES publications(module_id,revision));
CREATE TABLE attempts(
 seq INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, owner TEXT NOT NULL,
 module_id TEXT NOT NULL, revision INTEGER NOT NULL, source_hash TEXT NOT NULL,
 question_id TEXT NOT NULL, question_revision INTEGER NOT NULL,
 selection INTEGER NOT NULL, correct INTEGER NOT NULL CHECK(correct IN (0,1)),
 attempt_number INTEGER NOT NULL, timestamp TEXT NOT NULL,
 FOREIGN KEY(module_id,revision) REFERENCES publications(module_id,revision),
 UNIQUE(owner,module_id,revision,question_id,question_revision,attempt_number));
CREATE INDEX module_course ON modules(course_id,title);
CREATE INDEX attempt_question ON attempts(owner,module_id,revision,question_id,seq);
'''
for _table in ('modules', 'assets', 'publications', 'attempts'):
    for _operation in ('UPDATE', 'DELETE'):
        DDL += f"CREATE TRIGGER immutable_{_table}_{_operation.lower()} BEFORE {_operation} ON {_table} BEGIN SELECT RAISE(ABORT,'immutable history'); END;\n"


class StudioStore:
    def __init__(self, path):
        self.path = Path(path).absolute()

    def _safe(self):
        require(self.path.name == 'learning_studio.sqlite3', 'Learning Studio must use its dedicated learning_studio.sqlite3 file.')
        require(not any(p.is_symlink() for p in (self.path, *self.path.parents)), 'Symlink storage is not allowed.')
        if self.path.exists(): require(self.path.is_file(), 'Invalid storage file.')

    @contextmanager
    def connection(self, *, write=False):
        self._safe()
        if not self.path.exists() and not write:
            yield None
            return
        if write:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        mode = 'rwc' if write else 'ro'
        con = sqlite3.connect('file:' + quote(self.path.as_posix(), safe='/:') + '?mode=' + mode,
                              uri=True, timeout=10, isolation_level=None)
        con.row_factory = sqlite3.Row
        try:
            con.execute('PRAGMA foreign_keys=ON')
            app_id = con.execute('PRAGMA application_id').fetchone()[0]
            if app_id == 0 and write:
                tables = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                require(not tables, 'Existing database is not a Learning Studio store.')
                # One explicit migration, atomic and separate from the academic DB.
                con.executescript('BEGIN IMMEDIATE;\n' + DDL +
                                  f'PRAGMA application_id={APPLICATION_ID}; PRAGMA user_version=1; COMMIT;')
            require(con.execute('PRAGMA application_id').fetchone()[0] == APPLICATION_ID and
                    con.execute('PRAGMA user_version').fetchone()[0] == 1,
                    'Unsupported or foreign Learning Studio database.')
            if write: con.execute('BEGIN IMMEDIATE')
            yield con
            if write: con.commit()
        except BaseException:
            if con.in_transaction: con.rollback()
            raise
        finally:
            con.close()
