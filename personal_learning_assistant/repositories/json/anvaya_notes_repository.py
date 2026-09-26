"""Independent JSON + asset repository for ANVAYA personal Notes.

This store is intentionally separate from the Obsidian vault. Reads never scan
or mutate the vault. Explicit writes atomically replace the JSON index and keep
uploaded source files under an app-managed asset root.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from threading import Lock, RLock
from typing import Iterable
from uuid import uuid4


DEFAULT_NOTES_PATH = Path("data/anvaya_notes.json")
DEFAULT_ASSETS_ROOT = Path("data/anvaya_notes_assets")
_LOCKS_GUARD = Lock()
_STORE_LOCKS = {}


def _serialized_write(method):
    """Keep a JSON store's compare-and-replace atomic across app threads."""
    @wraps(method)
    def write(self, *args, **kwargs):
        path = str(self.notes_path.resolve(strict=False))
        with _LOCKS_GUARD:
            lock = _STORE_LOCKS.setdefault(path, RLock())
        with lock:
            return method(self, *args, **kwargs)
    return write


def _newer_version(proposed, previous):
    """Prevent same-clock edits from reusing a prior optimistic version."""
    def parse(value):
        try:
            result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
        except ValueError:
            return None

    before, after = parse(previous), parse(proposed)
    if after is not None and (before is None or after > before):
        return str(proposed)
    if before is not None:
        return (before + timedelta(microseconds=1)).isoformat(timespec="microseconds").replace("+00:00", "Z")
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


class AnvayaNotesRepositoryError(RuntimeError):
    pass


class AnvayaNotesNotFoundError(AnvayaNotesRepositoryError):
    pass


class AnvayaNotesConflictError(AnvayaNotesRepositoryError):
    pass


def _safe_id(value: str) -> str:
    text = str(value or "").strip()
    if not text or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in text):
        raise AnvayaNotesNotFoundError("Note or asset was not found.")
    return text


class AnvayaNotesRepository:
    def __init__(self, *, notes_path=DEFAULT_NOTES_PATH, assets_root=DEFAULT_ASSETS_ROOT):
        self.notes_path = Path(notes_path)
        self.assets_root = Path(assets_root)

    def list_notes(self):
        if not self.notes_path.exists():
            return []
        try:
            raw = self.notes_path.read_text(encoding="utf-8")
        except OSError as error:
            raise AnvayaNotesRepositoryError("Notes store could not be read.") from error
        if not raw.strip():
            return []
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            raise AnvayaNotesRepositoryError("Notes store is invalid.") from error
        if not isinstance(payload, list):
            raise AnvayaNotesRepositoryError("Notes store is invalid.")
        return [deepcopy(row) for row in payload if isinstance(row, dict)]

    def get_note(self, note_id):
        note_id = _safe_id(note_id)
        for row in self.list_notes():
            if str(row.get("id") or "") == note_id:
                return row
        raise AnvayaNotesNotFoundError("Note was not found.")

    def _save(self, rows):
        payload = [deepcopy(dict(row)) for row in rows]
        self.notes_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.notes_path.with_name(
            self.notes_path.name + ".tmp-" + uuid4().hex
        )
        try:
            temporary.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            os.replace(temporary, self.notes_path)
        except OSError as error:
            raise AnvayaNotesRepositoryError("Notes store could not be saved.") from error
        finally:
            if temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    pass
        return payload

    def _write_assets(self, note_id, uploads: Iterable[dict]):
        uploads = tuple(uploads or ())
        if not uploads:
            return []
        note_id = _safe_id(note_id)
        target_dir = self.assets_root / note_id
        if target_dir.exists() and target_dir.is_symlink():
            raise AnvayaNotesRepositoryError("Notes asset directory is unsafe.")
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise AnvayaNotesRepositoryError("Notes asset directory could not be created.") from error
        stored = []
        created_paths = []
        try:
            for item in uploads:
                asset_id = _safe_id(item.get("id") or uuid4().hex)
                suffix = str(item["suffix"]).casefold()
                stored_name = asset_id + suffix
                target = target_dir / stored_name
                payload = bytes(item["bytes"])
                try:
                    target.write_bytes(payload)
                except OSError as error:
                    raise AnvayaNotesRepositoryError("Note asset could not be saved.") from error
                created_paths.append(target)
                stored.append(
                    {
                        "id": asset_id,
                        "filename": str(item["filename"]),
                        "stored_name": stored_name,
                        "mimetype": str(item["mimetype"]),
                        "size": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                )
            return stored
        except Exception:
            for path in created_paths:
                try:
                    path.unlink()
                except OSError:
                    pass
            raise

    @_serialized_write
    def create_note(self, record, uploads=()):
        rows = self.list_notes()
        note = deepcopy(dict(record))
        note_id = _safe_id(note.get("id"))
        if any(str(row.get("id") or "") == note_id for row in rows):
            raise AnvayaNotesConflictError("Note id already exists.")
        assets = []
        try:
            assets = self._write_assets(note_id, uploads)
            note["assets"] = assets
            rows.append(note)
            self._save(rows)
            return deepcopy(note)
        except Exception:
            if assets:
                note_dir = self.assets_root / note_id
                try:
                    shutil.rmtree(note_dir)
                except OSError:
                    pass
            raise

    @_serialized_write
    def update_note(
        self,
        note_id,
        *,
        expected_updated_at,
        changes,
        uploads=(),
        remove_asset_ids=(),
    ):
        note_id = _safe_id(note_id)
        rows = self.list_notes()
        index = next(
            (idx for idx, row in enumerate(rows) if str(row.get("id") or "") == note_id),
            None,
        )
        if index is None:
            raise AnvayaNotesNotFoundError("Note was not found.")

        current = deepcopy(rows[index])
        if str(current.get("updated_at") or "") != str(expected_updated_at or ""):
            raise AnvayaNotesConflictError("Note changed since it was opened.")

        remove_ids = {_safe_id(value) for value in tuple(remove_asset_ids or ())}
        current_assets = list(current.get("assets") or [])
        known_ids = {str(asset.get("id") or "") for asset in current_assets}
        unknown = sorted(remove_ids - known_ids)
        if unknown:
            raise AnvayaNotesNotFoundError("One or more note files were not found.")

        note_dir = self.assets_root / note_id
        staged_removals = []
        new_assets = []
        try:
            new_assets = self._write_assets(note_id, uploads)

            for asset in current_assets:
                asset_id = str(asset.get("id") or "")
                if asset_id not in remove_ids:
                    continue
                stored_name = Path(str(asset.get("stored_name") or "")).name
                source = note_dir / stored_name
                if source.exists():
                    if note_dir.is_symlink() or source.is_symlink():
                        raise AnvayaNotesRepositoryError(
                            "Notes asset directory is unsafe."
                        )
                    temporary = note_dir / (
                        stored_name + ".delete-" + uuid4().hex
                    )
                    try:
                        os.replace(source, temporary)
                    except OSError as error:
                        raise AnvayaNotesRepositoryError(
                            "Note file could not be staged for deletion."
                        ) from error
                    staged_removals.append((temporary, source))

            updated = deepcopy(current)
            updated.update(deepcopy(dict(changes)))
            updated["updated_at"] = _newer_version(updated.get("updated_at"), current.get("updated_at"))
            updated["id"] = note_id
            updated["created_at"] = current.get("created_at", "")
            updated["assets"] = [
                asset
                for asset in current_assets
                if str(asset.get("id") or "") not in remove_ids
            ] + new_assets
            rows[index] = updated

            self._save(rows)
        except Exception:
            for asset in new_assets:
                try:
                    (note_dir / asset["stored_name"]).unlink()
                except OSError:
                    pass
            for temporary, source in reversed(staged_removals):
                try:
                    if temporary.exists():
                        os.replace(temporary, source)
                except OSError:
                    pass
            raise

        for temporary, _source in staged_removals:
            try:
                temporary.unlink()
            except OSError:
                # Metadata is already committed and no longer references this
                # staged file. Leaving a hidden orphan is safer than restoring
                # a deleted asset into active storage without metadata.
                pass

        return deepcopy(updated)

    def read_asset(self, note_id, asset_id):
        note = self.get_note(note_id)
        asset_id = _safe_id(asset_id)
        asset = next(
            (
                deepcopy(item)
                for item in list(note.get("assets") or [])
                if str(item.get("id") or "") == asset_id
            ),
            None,
        )
        if asset is None:
            raise AnvayaNotesNotFoundError("Asset was not found.")
        stored_name = Path(str(asset.get("stored_name") or "")).name
        note_dir = self.assets_root / _safe_id(note_id)
        path = note_dir / stored_name
        try:
            if note_dir.is_symlink() or path.is_symlink():
                raise AnvayaNotesNotFoundError("Asset was not found.")
            resolved_root = note_dir.resolve(strict=False)
            resolved = path.resolve(strict=True)
            if resolved.parent != resolved_root or not resolved.is_file():
                raise AnvayaNotesNotFoundError("Asset was not found.")
            payload = resolved.read_bytes()
        except (OSError, RuntimeError) as error:
            raise AnvayaNotesNotFoundError("Asset was not found.") from error
        if hashlib.sha256(payload).hexdigest() != str(asset.get("sha256") or ""):
            raise AnvayaNotesRepositoryError("Asset integrity check failed.")
        asset["bytes"] = payload
        return asset
