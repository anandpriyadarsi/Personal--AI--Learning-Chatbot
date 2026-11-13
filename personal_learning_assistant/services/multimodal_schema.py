"""Explicit optional activation. Never called by imports, GETs or app startup."""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil
import sqlite3
import uuid
from .native_document_library import _safe

NATIVE_SQL='''
CREATE TABLE IF NOT EXISTS mm_schema_ledger(version INTEGER PRIMARY KEY, checksum TEXT NOT NULL, backup_ref TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mm_selections(document_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE, source_json TEXT NOT NULL, locator_json TEXT NOT NULL, method TEXT NOT NULL, review_text TEXT NOT NULL, permission_id TEXT, state TEXT NOT NULL, error TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS mm_artifacts(id TEXT PRIMARY KEY, document_id TEXT NOT NULL, source_json TEXT NOT NULL, locator_json TEXT NOT NULL, recipe TEXT NOT NULL, content_hash TEXT NOT NULL, text TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL, uncertain_json TEXT NOT NULL, UNIQUE(document_id,source_json,locator_json,recipe));
CREATE TABLE IF NOT EXISTS mm_reviews(id TEXT PRIMARY KEY, artifact_id TEXT NOT NULL, artifact_hash TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mm_permissions(id TEXT PRIMARY KEY, scope_json TEXT NOT NULL, provider TEXT NOT NULL, purpose TEXT NOT NULL, max_cost INTEGER NOT NULL, expires REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS mm_provider_requests(id TEXT PRIMARY KEY, permission_id TEXT NOT NULL, month TEXT NOT NULL, reserved INTEGER NOT NULL, actual INTEGER, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mm_lecture_manifests(id TEXT PRIMARY KEY, transcript_id TEXT NOT NULL, source_json TEXT NOT NULL, frames_json TEXT NOT NULL, reference TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1);
'''
CANONICAL_SQL=(Path(__file__).resolve().parents[1]/'repositories/sqlite/optional_migrations/0020_multimodal_evidence.sql').read_text(encoding='utf-8')
CHECKSUM=hashlib.sha256((NATIVE_SQL+CANONICAL_SQL).encode()).hexdigest()


def available(con):
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE name='mm_schema_ledger'").fetchone())


def _backup(src,dst):
    with closing(sqlite3.connect(str(src))) as read,closing(sqlite3.connect(str(dst))) as write:
        read.backup(write)
        if write.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Backup verification failed')


def activate(database,library_root,*,apply=False):
    database=_safe(Path(database).absolute());root=_safe(Path(library_root).absolute());native=_safe(root/'library.sqlite3')
    if not database.is_file() or not native.is_file():raise ValueError('Existing academic and Library owners are required; no empty owner will be created')
    # Never follow an asset symlink into another owner's data during backup.
    for path in database.parent.rglob('*'):
        if 'backups' in path.relative_to(database.parent).parts:continue
        _safe(path)
    for path in root.rglob('*'):_safe(path)
    pending=[]
    for path in (native,database):
        # Read-only SQLite can still create WAL/SHM sidecars. Immutable preview
        # avoids writes; refuse an uncheckpointed owner rather than ignore WAL.
        wal=Path(str(path)+'-wal')
        if not apply and wal.is_file() and wal.stat().st_size:
            raise ValueError('Stop writers and checkpoint existing owners before read-only preview')
        connection=sqlite3.connect(str(path)) if apply else sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True)
        with closing(connection) as con:
            if available(con):
                row=con.execute('SELECT checksum FROM mm_schema_ledger WHERE version=1').fetchone()
                if not row or row[0]!=CHECKSUM:raise ValueError('Multimodal schema checksum mismatch')
            else:pending.append(path)
    if not apply or not pending:return dict(pending=bool(pending),checksum=CHECKSUM)
    # Run with stopped app/writers. Backup ALL authoritative owner files under
    # the data root (including notes/assets/config), not disposable indexes.
    backup=database.parent/'backups'/('multimodal-'+uuid.uuid4().hex)
    backup.mkdir(parents=True,mode=0o700)
    try:
        _backup(database,backup/'academic.sqlite3');_backup(native,backup/'library.sqlite3')
        shutil.copytree(root,backup/'native',ignore=shutil.ignore_patterns('tmp','library.sqlite3*'))
        for path in database.parent.iterdir():
            if path in (database,root,backup.parent) or path.name.endswith(('-wal','-shm')):continue
            if path.is_symlink():raise ValueError('Symlink in owner backup')
            if path.is_file():
                if path.suffix in ('.db','.sqlite3'):_backup(path,backup/path.name)
                else:shutil.copy2(path,backup/path.name)
            elif path.is_dir() and path.name not in ('tutor_retrieval','retrieval_index'):
                shutil.copytree(path,backup/path.name,symlinks=False)
        hashes={str(p.relative_to(backup)):hashlib.sha256(p.read_bytes()).hexdigest() for p in backup.rglob('*') if p.is_file()}
        (backup/'checksums.json').write_text(json.dumps(hashes,sort_keys=True))
        for path,sql in ((native,NATIVE_SQL),(database,CANONICAL_SQL)):
            with closing(sqlite3.connect(str(path),isolation_level=None)) as con:
                con.executescript('BEGIN IMMEDIATE;'+sql)
                con.execute('INSERT OR REPLACE INTO mm_schema_ledger VALUES(1,?,?)',(CHECKSUM,str(backup)))
                con.commit()
    except Exception:
        # Activation is explicit and requires stopped writers. Restore only this
        # failed activation, never use backups as routine behavior rollback.
        if (backup/'academic.sqlite3').is_file():_backup(backup/'academic.sqlite3',database)
        if (backup/'library.sqlite3').is_file():_backup(backup/'library.sqlite3',native)
        raise
    return dict(pending=False,checksum=CHECKSUM,backup=backup)
