"""Explicit unencrypted native backup; never uploaded or synced automatically."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import tempfile
import uuid
import zipfile

MAX_BYTES = 100 * 1024 * 1024
MAX_FILES = 1000
FORMAT = 'anvaya.android-backup.v1'


def _checked(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError('Backup exceeds 100 MB')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_FILES or sum(i.file_size for i in infos) > MAX_BYTES:
                raise ValueError('Expanded backup exceeds limits')
            names = [i.filename for i in infos]
            if len(names) != len(set(names)) or 'manifest.json' not in names:
                raise ValueError('Duplicate entries or missing manifest')
            manifest = json.loads(archive.read('manifest.json'))
            if manifest.get('format') != FORMAT or not isinstance(manifest.get('files'), dict):
                raise ValueError('Unsupported backup format')
            files = {}
            for info in infos:
                name = info.filename
                if name == 'manifest.json': continue
                path = PurePosixPath(name)
                if (not name.startswith('data/') or '\\' in name or '\x00' in name
                    or '..' in path.parts or path.is_absolute() or len(path.parts) < 2
                    or info.is_dir() or stat.S_ISLNK(info.external_attr >> 16)
                    or name.endswith(('-wal', '-shm', '-journal'))):
                    raise ValueError('Unsafe backup path')
                payload = archive.read(info)
                if hashlib.sha256(payload).hexdigest() != manifest['files'].get(name):
                    raise ValueError('Backup integrity check failed')
                files[name] = payload
            if set(files) != set(manifest['files']):
                raise ValueError('Backup manifest mismatch')
            return files
    except (zipfile.BadZipFile, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError('Invalid backup archive') from error


def export_backup(root, *, include_media=True):
    # Blob enumeration and metadata snapshot must agree while indexing/uploads
    # run independently of the phone's academic request lock.
    from personal_learning_assistant.services.native_document_library import storage_lock
    from personal_learning_assistant.repositories.json.anvaya_notes_repository import notes_storage_lock
    with notes_storage_lock(Path(root)/'data/anvaya_notes.json'), storage_lock(Path(root)/'data/native_library'):
        return _export_backup(root, include_media=include_media)


def _export_backup(root, *, include_media=True):
    root = Path(root)
    files = {}
    for path in sorted((root/'data').rglob('*')):
        relative = path.relative_to(root).as_posix()
        if not include_media and relative.startswith('data/anvaya_notes_assets/') and '/media/' in relative:
            continue
        if path.is_symlink(): raise ValueError('Symlinks cannot be exported')
        if not path.is_file() or path.name.endswith(('-wal','-shm','-journal')): continue
        if path.stat().st_size > MAX_BYTES: raise ValueError('Backup file too large')
        name = path.relative_to(root).as_posix()
        if name.startswith('data/native_library/tmp/'): continue
        if path.suffix in ('.db','.sqlite3'):
            with tempfile.TemporaryDirectory() as temporary:
                destination = Path(temporary)/'snapshot.db'
                with closing(sqlite3.connect(path.absolute().as_uri()+'?mode=ro', uri=True)) as source:
                    with closing(sqlite3.connect(destination)) as target:
                        source.backup(target)
                        if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                            raise ValueError('Database integrity check failed')
                files[name] = destination.read_bytes()
        else:
            payload = path.read_bytes()
            if not include_media and name=='data/anvaya_notes.json':
                notes = json.loads(payload)
                if not isinstance(notes,list): raise ValueError('Invalid notes store')
                for note in notes:
                    if isinstance(note,dict): note['media'] = []
                payload = json.dumps(notes,ensure_ascii=False).encode('utf-8')
            files[name] = payload
        if len(files) >= MAX_FILES or sum(map(len, files.values())) > MAX_BYTES:
            raise ValueError('Backup exceeds limits')
    manifest = {'format':FORMAT,'files':{k:hashlib.sha256(v).hexdigest() for k,v in files.items()}}
    if not include_media: manifest['media_excluded'] = True
    out = io.BytesIO()
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in files.items(): archive.writestr(name,payload)
        archive.writestr('manifest.json',json.dumps(manifest,sort_keys=True))
    raw = out.getvalue(); _checked(raw)
    return raw


def _validate_databases(root, files):
    # Integrity alone does not prove that production owners can reopen a DB.
    # Validate copies with the same migrations before scheduling any replacement.
    with tempfile.TemporaryDirectory(dir=root) as temporary:
        directory=Path(temporary)
        for name,payload in files.items():
            if not name.endswith(('.db','.sqlite3')): continue
            path=directory/Path(name).name; path.write_bytes(payload)
            try:
                with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as con:
                    if (con.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or
                        con.execute('PRAGMA foreign_key_check').fetchone() is not None):
                        raise ValueError('Restored database is corrupt')
                if name=='data/learning_assistant.db':
                    from personal_learning_assistant.services.assessment_activation import activate_assessment_extension
                    activate_assessment_extension(database_path=path,backup_path=directory/'backups')
                elif name=='data/native_library/library.sqlite3':
                    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as con:
                        if con.execute('PRAGMA user_version').fetchone()[0]!=1: raise ValueError('Unknown Library version')
                        for digest,size in con.execute('SELECT sha256,size FROM documents'):
                            blob=files.get('data/native_library/blobs/'+digest)
                            if blob is None or len(blob)!=size or hashlib.sha256(blob).hexdigest()!=digest:
                                raise ValueError('Library original is missing or changed')
                elif name=='data/learning_studio.sqlite3':
                    from personal_learning_assistant.learning_studio.store import StudioStore
                    with StudioStore(path).connection(): pass
            except Exception as error:
                raise ValueError('Backup is incompatible with this app version') from error


def stage_restore(root, raw):
    files = _checked(raw)
    root = Path(root); root.mkdir(parents=True,exist_ok=True)
    _validate_databases(root,files)
    pending = root/'restore-pending.zip'
    temporary = root/'restore-pending.tmp'
    temporary.write_bytes(raw); os.replace(temporary,pending)


def apply_pending_restore(root):
    root = Path(root); pending=root/'restore-pending.zip'
    if not pending.exists(): return False
    if pending.is_symlink(): raise ValueError('Unsafe restore archive')
    files = _checked(pending.read_bytes())
    _validate_databases(root,files)
    stage = root/('.restore-'+uuid.uuid4().hex); stage.mkdir(mode=0o700)
    data = root/'data'
    previous = root/('data-before-restore-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8])
    try:
        (stage/'data').mkdir()
        for name,payload in files.items():
            path=stage/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(payload)
        if data.exists(): os.replace(data,previous)
        try: os.replace(stage/'data',data)
        except OSError:
            if previous.exists(): os.replace(previous,data)
            raise
        pending.unlink()
        return True
    finally: shutil.rmtree(stage,ignore_errors=True)
