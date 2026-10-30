"""Explicit, unencrypted, bounded-memory backup with staged, recoverable restore.

Production callers pass streams/paths. The bytes/dict helpers remain for v1
callers and small fixtures; they are deliberately not the HTTP transport.
"""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import tempfile
import uuid
import zipfile

MAX_BYTES = 4 * 1024 * 1024 * 1024
MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_FILES = 20000
MAX_MANIFEST = 8 * 1024 * 1024
BLOCK = 256 * 1024
FORMAT = 'anvaya.android-backup.v2'
LEGACY_FORMAT = 'anvaya.android-backup.v1'


def _safe(path):
    path = Path(path).absolute()
    if any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)() for p in (path, *path.parents)):
        raise ValueError('Symlinks cannot be exported or restored')
    return path


def _sync_directory(path):
    if os.name != 'nt':
        fd = os.open(path, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)


def _json_publish(path, value):
    path=_safe(path)
    temporary = _safe(path.with_suffix('.tmp'))
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path); _sync_directory(path.parent)


def _digest(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(BLOCK), b''): digest.update(chunk)
    return digest.hexdigest()


def _copy(source, destination, *, limit=MAX_FILE_BYTES):
    total = 0; digest = hashlib.sha256()
    for block in iter(lambda: source.read(BLOCK), b''):
        total += len(block)
        if total > limit: raise ValueError('Backup exceeds configured limits')
        digest.update(block); destination.write(block)
    return total, digest.hexdigest()


def _manifest(archive):
    infos = archive.infolist()
    if len(infos) > MAX_FILES + 1 or sum(i.file_size for i in infos) > MAX_BYTES:
        raise ValueError('Expanded backup exceeds limits')
    names = [i.filename for i in infos]
    if len(names) != len(set(names)) or 'manifest.json' not in names:
        raise ValueError('Duplicate entries or missing manifest')
    info = archive.getinfo('manifest.json')
    if info.file_size > MAX_MANIFEST: raise ValueError('Manifest exceeds limits')
    manifest = json.loads(archive.read(info))
    if manifest.get('format') not in (FORMAT, LEGACY_FORMAT) or not isinstance(manifest.get('files'), dict):
        raise ValueError('Unsupported backup format')
    if set(names) - {'manifest.json'} != set(manifest['files']):
        raise ValueError('Backup manifest mismatch')
    for info in infos:
        name = info.filename
        if name == 'manifest.json': continue
        path = PurePosixPath(name)
        if (not name.startswith('data/') or '\\' in name or '\x00' in name or ':' in name
            or '..' in path.parts or path.is_absolute() or len(path.parts) < 2
            or str(path) != name or info.is_dir() or info.file_size > MAX_FILE_BYTES
            or stat.S_ISLNK(info.external_attr >> 16)
            or name.endswith(('-wal', '-shm', '-journal'))):
            raise ValueError('Unsafe backup path')
        item = manifest['files'][name]
        digest = item if isinstance(item, str) else item.get('sha256')
        if not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
            raise ValueError('Invalid payload hash')
        if isinstance(item, dict) and item.get('size') != info.file_size:
            raise ValueError('Payload size mismatch')
    tombstones = manifest.get('unavailable_originals', [])
    if not isinstance(tombstones, list) or len(tombstones) > MAX_FILES:
        raise ValueError('Invalid recovery manifest')
    for item in tombstones:
        if (not isinstance(item, dict) or not re.fullmatch('[a-f0-9]{64}', str(item.get('sha256', '')))
            or not isinstance(item.get('document_id'), str)
            or not isinstance(item.get('size'), int) or item['size'] < 0
            or item.get('reason') not in ('missing', 'hash_mismatch')):
            raise ValueError('Invalid unavailable-original declaration')
    return manifest


def _unpack(source, directory):
    if isinstance(source, (bytes, bytearray)): source = io.BytesIO(source)
    try:
        with zipfile.ZipFile(source) as archive:
            manifest = _manifest(archive)
            paths = {}
            for name, expected in manifest['files'].items():
                path = directory/name; path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as incoming, path.open('wb') as outgoing:
                    size, digest = _copy(incoming, outgoing)
                    outgoing.flush(); os.fsync(outgoing.fileno())
                if digest != (expected if isinstance(expected, str) else expected['sha256']):
                    raise ValueError('Backup integrity check failed')
                paths[name] = path
            return manifest, paths
    except (zipfile.BadZipFile, KeyError, TypeError, json.JSONDecodeError, AttributeError) as error:
        raise ValueError('Invalid backup archive') from error


def _checked(raw):
    """Compatibility reader for small legacy callers, not used in production."""
    with tempfile.TemporaryDirectory() as temporary:
        _, paths = _unpack(raw, Path(temporary))
        return {name: path.read_bytes() for name, path in paths.items()}


def _snapshot(source, target):
    with closing(sqlite3.connect(source.absolute().as_uri()+'?mode=ro', uri=True)) as con:
        with closing(sqlite3.connect(target)) as destination:
            con.backup(destination)
            if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Database integrity check failed')


def export_backup_file(root, *, include_media=True, destination=None):
    from personal_learning_assistant.services.native_document_library import storage_lock
    from personal_learning_assistant.repositories.json.anvaya_notes_repository import notes_storage_lock
    root = _safe(root)
    output_dir = _safe(root/'backups'); output_dir.mkdir(parents=True, exist_ok=True)
    destination = _safe(destination or output_dir/('ANVAYA-'+uuid.uuid4().hex+'.zip'))
    # Never include the archive itself in its own inventory.
    if destination.is_relative_to(root/'data'): raise ValueError('Backup destination must be outside data')
    temporary = destination.with_name(destination.name+'.tmp')
    with notes_storage_lock(root/'data/anvaya_notes.json'), storage_lock(root/'data/native_library'):
        try:
            with tempfile.TemporaryDirectory(dir=root) as snapshot_dir:
                snapshot_dir = Path(snapshot_dir)
                paths = {}; total = 0; versions = {}
                for path in sorted((root/'data').rglob('*')):
                    _safe(path)
                    name = path.relative_to(root).as_posix()
                    if not path.is_file() or path.name.endswith(('-wal', '-shm', '-journal')): continue
                    if name.startswith(('data/native_library/tmp/', 'data/tutor_retrieval/')): continue
                    if not include_media and name.startswith('data/anvaya_notes_assets/') and '/media/' in name: continue
                    size = path.stat().st_size
                    if size > MAX_FILE_BYTES: raise ValueError('Backup file too large')
                    if path.suffix in ('.db', '.sqlite3'):
                        copied = snapshot_dir/name; copied.parent.mkdir(parents=True, exist_ok=True)
                        _snapshot(path, copied); path = copied
                        with closing(sqlite3.connect(path)) as con:
                            versions[name] = con.execute('PRAGMA user_version').fetchone()[0]
                    elif name == 'data/anvaya_notes.json':
                        notes = json.loads(path.read_bytes())
                        if not isinstance(notes, list): raise ValueError('Invalid notes store')
                        if not include_media:
                            for note in notes:
                                if isinstance(note, dict): note['media'] = []
                        copied = snapshot_dir/name; copied.parent.mkdir(parents=True, exist_ok=True)
                        copied.write_text(json.dumps(notes, ensure_ascii=False), encoding='utf-8'); path = copied
                    paths[name] = path; total += path.stat().st_size
                    if len(paths) > MAX_FILES or total > MAX_BYTES - MAX_MANIFEST: raise ValueError('Backup exceeds limits')
                unavailable = []
                native = paths.get('data/native_library/library.sqlite3')
                if native:
                    with closing(sqlite3.connect(native)) as con:
                        columns={r[1] for r in con.execute('PRAGMA table_info(documents)')}
                        locator_sql='managed_original' if 'managed_original' in columns else 'NULL'
                        for identity, digest, size, locator in con.execute('SELECT id,sha256,size,'+locator_sql+' FROM documents'):
                            name = 'data/'+locator if locator and re.fullmatch(r'documents/[0-9a-f]{64}\.pdf',locator) else 'data/native_library/blobs/'+digest
                            blob = paths.get(name)
                            reason = 'missing' if blob is None else ('hash_mismatch' if blob.stat().st_size != size or _digest(blob) != digest else None)
                            if reason:
                                unavailable.append({'document_id':identity,'sha256':digest,'size':size,'reason':reason})
                                paths.pop(name, None)
                manifest = {'format':FORMAT,'files':{},'schema_versions':versions,'unavailable_originals':unavailable,
                            'created_at':datetime.now(timezone.utc).isoformat(),'encrypted':False}
                if not include_media: manifest['media_excluded'] = True
                with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,allowZip64=True) as archive:
                    for name, path in paths.items():
                        with path.open('rb') as source, archive.open(name,'w',force_zip64=True) as target:
                            size, digest = _copy(source,target)
                        manifest['files'][name] = {'size':size,'sha256':digest}
                    archive.writestr('manifest.json',json.dumps(manifest,sort_keys=True))
                with temporary.open('rb') as stream: os.fsync(stream.fileno())
                # Verify the produced bytes before offering a backup.
                with tempfile.TemporaryDirectory(dir=root) as verify:
                    _unpack(temporary, Path(verify))
                os.replace(temporary,destination); _sync_directory(destination.parent)
                _json_publish(output_dir/'last-verified.json',{'verified_at':datetime.now(timezone.utc).isoformat(),'archive_size':destination.stat().st_size,'encrypted':False})
                return destination
        finally: temporary.unlink(missing_ok=True)


def export_backup(root, *, include_media=True):
    path = export_backup_file(root, include_media=include_media)
    try: return path.read_bytes()
    finally: path.unlink(missing_ok=True)


def _validate_databases(root, files, tombstones=()):
    declared = {(t['document_id'],t['sha256'],t['size']) for t in tombstones}
    with tempfile.TemporaryDirectory(dir=root) as temporary:
        directory = Path(temporary)
        for name, payload in files.items():
            if not name.endswith(('.db','.sqlite3')): continue
            path = directory/name; path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(payload, Path): shutil.copyfile(payload,path)
            else: path.write_bytes(payload)
            try:
                with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as con:
                    if (con.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or
                        con.execute('PRAGMA foreign_key_check').fetchone() is not None):
                        raise ValueError('Restored database is corrupt')
                if name=='data/learning_assistant.db':
                    from personal_learning_assistant.services.assessment_activation import activate_assessment_extension
                    activate_assessment_extension(database_path=path,backup_path=directory/'backups')
                elif name=='data/native_library/library.sqlite3':
                    with closing(sqlite3.connect(path)) as con:
                        from personal_learning_assistant.services.native_library_migrations import validate_schema
                        validate_schema(con)
                        columns={r[1] for r in con.execute('PRAGMA table_info(documents)')}
                        locator_sql='managed_original' if 'managed_original' in columns else 'NULL'
                        for identity,digest,size,locator in con.execute('SELECT id,sha256,size,'+locator_sql+' FROM documents'):
                            if locator and not re.fullmatch(r'documents/[0-9a-f]{64}\.pdf',locator):raise ValueError('Unsafe original locator')
                            blob=files.get('data/'+locator if locator else 'data/native_library/blobs/'+digest)
                            valid = (blob is not None and (blob.stat().st_size==size and _digest(blob)==digest if isinstance(blob,Path)
                                     else len(blob)==size and hashlib.sha256(blob).hexdigest()==digest))
                            if not valid and (identity,digest,size) not in declared:
                                raise ValueError('Library original is missing or changed')
                    if isinstance(payload,Path):
                        with closing(sqlite3.connect(payload)) as staged_con:
                            legacy=staged_con.execute('PRAGMA user_version').fetchone()[0]==1
                        if legacy:
                            from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary
                            staged=NativeDocumentLibrary(payload.parent,autostart=False)
                            staged.close()
                            with closing(sqlite3.connect(payload)) as staged_con:validate_schema(staged_con)
                elif name=='data/learning_studio.sqlite3':
                    from personal_learning_assistant.learning_studio.store import StudioStore
                    with StudioStore(path).connection(): pass
            except Exception as error:
                raise ValueError('Backup is incompatible with this app version') from error


def stage_restore(root, raw):
    root = _safe(root); root.mkdir(parents=True,exist_ok=True)
    temporary = _safe(root/'restore-pending.tmp')
    try:
        source = io.BytesIO(raw) if isinstance(raw,(bytes,bytearray)) else raw
        with temporary.open('wb') as output:
            _copy(source, output, limit=MAX_BYTES); output.flush(); os.fsync(output.fileno())
        with tempfile.TemporaryDirectory(dir=root) as checked:
            manifest, paths = _unpack(temporary,Path(checked))
            _validate_databases(root,paths,manifest.get('unavailable_originals',()))
        os.replace(temporary,root/'restore-pending.zip'); _sync_directory(root)
    finally: temporary.unlink(missing_ok=True)


def _recover_swap(root):
    journal = root/'restore-journal.json'
    if not journal.exists(): return
    state = json.loads(_safe(journal).read_text())
    previous, stage = state['previous'], state['stage']
    if (not re.fullmatch('data-before-restore-[A-Za-z0-9T-]+',previous)
        or not re.fullmatch(r'\.restore-[A-Za-z0-9-]+',stage)):
        raise ValueError('Invalid restore journal')
    data = _safe(root/'data'); previous = _safe(root/previous); stage = _safe(root/stage)
    if not data.exists() and previous.exists(): os.replace(previous,data)
    if data.exists():
        if state.get('phase')=='published': (root/'restore-pending.zip').unlink(missing_ok=True)
        shutil.rmtree(stage,ignore_errors=True); journal.unlink(); _sync_directory(root)


def apply_pending_restore(root):
    root = _safe(root); _recover_swap(root)
    pending = _safe(root/'restore-pending.zip')
    if not pending.exists(): return False
    stage = root/('.restore-'+uuid.uuid4().hex); stage.mkdir(mode=0o700)
    previous = root/('data-before-restore-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8])
    state = {'previous':previous.name,'stage':stage.name,'phase':'validated'}
    journal = root/'restore-journal.json'
    try:
        manifest, paths = _unpack(pending,stage)
        _validate_databases(root,paths,manifest.get('unavailable_originals',()))
        (stage/'data').mkdir(exist_ok=True)
        if manifest.get('unavailable_originals'):
            _json_publish(stage/'data/library-recovery.json',manifest['unavailable_originals'])
            native=stage/'data/native_library/library.sqlite3'
            if native.is_file():
                from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary
                restored=NativeDocumentLibrary(native.parent,autostart=False);restored.close()
        _json_publish(journal,state)
        if (root/'data').exists(): os.replace(root/'data',previous)
        state['phase']='old_moved'; _json_publish(journal,state)
        os.replace(stage/'data',root/'data'); _sync_directory(root)
        state['phase']='published'; _json_publish(journal,state)
        pending.unlink(); journal.unlink(); _sync_directory(root)
        return True
    except BaseException:
        _recover_swap(root)
        raise
    finally: shutil.rmtree(stage,ignore_errors=True)
