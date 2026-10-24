"""Streamed local media owned by existing handwritten notes; no decoding/player."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from uuid import uuid4

from personal_learning_assistant.repositories.json.anvaya_notes_repository import (
    AnvayaNotesRepository, AnvayaNotesRepositoryError, AnvayaNotesNotFoundError,
    _safe_id, _serialized_write, _newer_version,
)
from personal_learning_assistant.services.anvaya_notes_service import (
    AnvayaNotesValidationError, AnvayaNotesUnavailableError, _utc_now,
)

MAX_MEDIA_BYTES = 512 * 1024 * 1024
MAX_MEDIA_BATCH = 20
MAX_MEDIA_REQUEST_BYTES = 1024 * 1024 * 1024
CHUNK = 65536
MIMES = {'.mp3':'audio/mpeg', '.wav':'audio/wav', '.m4a':'audio/mp4',
         '.aac':'audio/aac', '.mp4':'video/mp4', '.mkv':'video/x-matroska',
         '.mov':'video/quicktime', '.webm':'video/webm'}


def media_mime(filename, header):
    """Recognize the container only; the external player determines codec support."""
    suffix = Path(filename).suffix.lower()
    valid = {
        '.mp3': header.startswith(b'ID3') or (len(header)>1 and header[0]==255 and header[1]&224==224),
        '.wav': header[:4]==b'RIFF' and header[8:12]==b'WAVE',
        '.aac': len(header)>1 and header[0]==255 and header[1]&246==240,
        '.m4a': header[4:8]==b'ftyp',
        '.mp4': header[4:8]==b'ftyp',
        '.mov': header[4:8] in (b'ftyp',b'moov',b'mdat',b'wide'),
        '.mkv': header.startswith(b'\x1aE\xdf\xa3') and b'matroska' in header,
        '.webm': header.startswith(b'\x1aE\xdf\xa3') and b'webm' in header,
    }.get(suffix, False)
    if not valid or len(header)<12:
        raise AnvayaNotesValidationError('Choose a valid MP3, WAV, M4A, AAC, MP4, MKV, MOV or WebM file.')
    return MIMES[suffix]


def _name(value, suffix=None):
    name = str(value or '').strip()
    if not name or len(name)>200 or name.startswith('.') or any(c in name for c in '/\\') or any(ord(c)<32 or ord(c)==127 for c in name):
        raise AnvayaNotesValidationError('Enter a file name without folders or special control characters (up to 200 characters).')
    extension = Path(name).suffix.lower()
    if suffix:
        if extension and extension != suffix:
            raise AnvayaNotesValidationError('Keep the original file extension when renaming.')
        if not extension:
            name += suffix
    elif extension not in MIMES:
        raise AnvayaNotesValidationError('This media format is not supported.')
    return name


def _public(note_id, item):
    base = f'/notes/media/{note_id}/{item["id"]}'
    return {key:item[key] for key in ('id','filename','mimetype','size')} | {
        'url':base+'/file', 'open_url':base+'/open', 'share_url':base+'/share'}


class NotesMediaStore:
    def __init__(self, repository):
        self.repository = repository
        # The existing repository decorator keys its shared lock by this path.
        self.notes_path = repository.notes_path

    def _note(self, note_id):
        try:
            note = self.repository.get_note(note_id)
        except AnvayaNotesNotFoundError:
            raise
        except AnvayaNotesRepositoryError as error:
            raise AnvayaNotesUnavailableError('The note could not be read.') from error
        if note.get('note_kind') != 'handwritten':
            raise AnvayaNotesValidationError('Attach media to a handwritten note.')
        return note

    def _directory(self, note_id, *, create=False):
        path = self.repository.assets_root.absolute() / _safe_id(note_id) / 'media'
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise AnvayaNotesNotFoundError('Attachment storage is unavailable.')
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def list(self, note_id):
        return [_public(note_id, item) for item in self._note(note_id).get('media', [])]

    def _save(self, note, items):
        rows = self.repository.list_notes()
        note['media'] = items
        note['updated_at'] = _newer_version(_utc_now(), note.get('updated_at'))
        rows = [note if row.get('id')==note['id'] else row for row in rows]
        self.repository._save(rows)

    @_serialized_write
    def add(self, note_id, uploads):
        note = self._note(note_id)
        uploads = list(uploads)
        if not uploads or len(uploads)>MAX_MEDIA_BATCH:
            raise AnvayaNotesValidationError('Choose between 1 and 20 media files.')
        items = list(note.get('media', []))
        created = []
        result = []
        request_bytes = 0
        try:
            directory = self._directory(note_id, create=True)
            for filename, stream in uploads:
                filename = _name(filename)
                suffix = Path(filename).suffix.lower()
                asset_id = uuid4().hex
                path = directory / (asset_id+suffix)
                created.append(path)
                digest = hashlib.sha256()
                size = 0
                header = b''
                # Exclusive creation and a shared note-store lock avoid collision
                # or stale-note overwrite even on repeated/concurrent submissions.
                with path.open('xb') as output:
                    while True:
                        chunk = stream.read(CHUNK)
                        if not chunk:
                            break
                        size += len(chunk)
                        request_bytes += len(chunk)
                        if size>MAX_MEDIA_BYTES or request_bytes>MAX_MEDIA_REQUEST_BYTES:
                            raise AnvayaNotesValidationError('Each file must be 512 MB or smaller; one upload must be under 1 GB.')
                        if len(header)<4096:
                            header = (header+chunk)[:4096]
                        digest.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                mime = media_mime(filename, header)
                sha = digest.hexdigest()
                duplicate = next((item for item in items if item.get('sha256')==sha and item.get('mimetype')==mime and item.get('size')==size), None)
                if duplicate:
                    # Only deduplicate a still-present, intact original.
                    self.resolve(note_id, duplicate['id']) if duplicate in note.get('media', []) else None
                    path.unlink()
                    result.append(_public(note_id, duplicate))
                    continue
                item = {'id':asset_id,'filename':filename,'stored_name':path.name,
                        'mimetype':mime,'size':size,'sha256':sha}
                items.append(item)
                result.append(_public(note_id,item))
            self._save(note, items)
            return result
        except (OSError, AnvayaNotesRepositoryError) as error:
            if isinstance(error, AnvayaNotesNotFoundError):
                raise
            raise AnvayaNotesUnavailableError('Media could not be saved. Check available storage and try again.') from error
        finally:
            # After a successful JSON commit keep referenced files. On failure
            # remove every newly written file, preserving older note metadata.
            try:
                committed = {item['stored_name'] for item in self.repository.get_note(note_id).get('media', [])}
            except AnvayaNotesRepositoryError:
                committed = {p.name for p in created}  # uncertain disk state: do not destroy data
            for path in created:
                if path.name not in committed:
                    try: path.unlink(missing_ok=True)
                    except OSError: pass

    def _find(self, note_id, asset_id):
        note = self._note(note_id)
        asset_id = _safe_id(asset_id)
        item = next((x for x in note.get('media', []) if x.get('id')==asset_id), None)
        if item is None:
            raise AnvayaNotesNotFoundError('Attachment not found. Refresh the note.')
        return note, item

    def _path(self, note_id, item):
        suffix = Path(item.get('stored_name','')).suffix.lower()
        expected = _safe_id(item['id']) + suffix
        if suffix not in MIMES or item.get('stored_name') != expected or item.get('mimetype') != MIMES[suffix]:
            raise AnvayaNotesNotFoundError('Attachment not found.')
        path = self._directory(note_id) / expected
        if path.is_symlink():
            raise AnvayaNotesNotFoundError('Attachment not found.')
        return path

    def resolve(self, note_id, asset_id):
        _, item = self._find(note_id, asset_id)
        path = self._path(note_id, item)
        try:
            if not path.is_file():
                raise AnvayaNotesNotFoundError('Attachment is missing. Attach the original file again.')
            digest = hashlib.sha256()
            with path.open('rb') as source:
                for chunk in iter(lambda:source.read(CHUNK),b''):
                    digest.update(chunk)
            if path.stat().st_size!=item['size'] or digest.hexdigest()!=item['sha256']:
                raise AnvayaNotesUnavailableError('This attachment is damaged. Attach the original file again.')
        except OSError as error:
            raise AnvayaNotesUnavailableError('The attachment could not be read. Check storage access.') from error
        return dict(item, path=path)

    @_serialized_write
    def rename(self, note_id, asset_id, filename):
        note, item = self._find(note_id,asset_id)
        item['filename'] = _name(filename,Path(item['stored_name']).suffix.lower())
        try:
            self._save(note,note['media'])
        except (OSError, AnvayaNotesRepositoryError) as error:
            raise AnvayaNotesUnavailableError('The attachment could not be renamed.') from error
        return _public(note_id,item)

    @_serialized_write
    def delete(self, note_id, asset_id):
        note, item = self._find(note_id,asset_id)
        path = self._path(note_id,item)
        staged = path.with_name(path.name+'.delete-'+uuid4().hex)
        moved = False
        try:
            if path.exists():
                path.rename(staged)
                moved = True
            self._save(note,[x for x in note['media'] if x['id']!=asset_id])
        except (OSError, AnvayaNotesRepositoryError) as error:
            if moved:
                staged.rename(path)
            raise AnvayaNotesUnavailableError('The attachment could not be removed.') from error
        try: staged.unlink(missing_ok=True)
        except OSError: pass  # unreferenced tombstone; never restore after commit


def resolve_android_media(root_path, note_id, asset_id):
    """Native-only: never include the private path in browser JSON or an intent."""
    root = Path(root_path).absolute()
    repo = AnvayaNotesRepository(notes_path=root/'data/anvaya_notes.json',
                                assets_root=root/'data/anvaya_notes_assets')
    item = NotesMediaStore(repo).resolve(note_id,asset_id)
    return [str(item['path']), item['mimetype'], item['filename']]
