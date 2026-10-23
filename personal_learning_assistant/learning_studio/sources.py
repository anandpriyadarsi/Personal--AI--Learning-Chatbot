"""Read-only adapters to ANVAYA's existing registered sources and course catalogue."""
import json
from contextlib import closing
from pathlib import Path, PurePosixPath
import sqlite3
from urllib.parse import quote
from .validation import PackageError, MAX_SOURCE, require


def safe_regular(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)) and path.is_file(), 'Registered file must be a non-symlink regular file.')
    return path


class RegisteredSources:
    def __init__(self, database_path, roots):
        self.database_path = Path(database_path)
        self.roots = roots

    def __call__(self, source_id):
        from personal_learning_assistant.ingestion.source_resolver import SourceRootResolver
        db = safe_regular(self.database_path)
        with closing(sqlite3.connect('file:' + quote(db.as_posix(), safe='/:') + '?mode=ro', uri=True)) as con:
            row = con.execute('SELECT path_key,content_hash,mime_type FROM knowledge_documents WHERE id=?', (source_id,)).fetchone()
        require(row is not None and row[2] == 'application/pdf', 'Source ID must reference an existing registered PDF.')
        require(isinstance(row[0], str) and '/' in row[0] and '\\' not in row[0], 'Registered source has an invalid logical path.')
        logical, relative = row[0].split('/', 1)
        root = next((Path(v).absolute() for k, v in self.roots.items() if str(k).casefold() == logical.casefold()), None)
        require(root is not None and not PurePosixPath(relative).is_absolute() and '..' not in PurePosixPath(relative).parts, 'Registered source path escapes its configured root.')
        # Check the unresolved path BEFORE the existing resolver canonicalises it.
        # Resolving first hides intermediate symlinks, including links inside a root.
        safe_regular(root / relative)
        resolver = SourceRootResolver(self.roots)
        path = safe_regular(resolver.resolve(row[0]))
        require(path.stat().st_size <= MAX_SOURCE, 'Registered source exceeds 20 MB.', 413)
        raw, digest = resolver.snapshot(path)
        require(digest == row[1], 'Registered source changed. Existing ingestion must reconcile it first.', 409)
        return raw


def catalogue():
    from personal_learning_assistant.services.course_dashboard_service import load_course_catalogue, unavailable_course_catalogue
    try:
        return load_course_catalogue()
    except Exception:
        return unavailable_course_catalogue()
