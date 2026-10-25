"""Explicit, optional vault snapshots and independent Markdown copies.

Snapshots are app-owned read-only inputs to the existing vault reader. Nothing
here writes back to Obsidian or represents a synchronization relationship.
"""
from __future__ import annotations

import io
import re
import shutil
import stat
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .obsidian_workspace_service import ObsidianWorkspaceValidationError

MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_EXPANDED_BYTES = 100 * 1024 * 1024
MAX_ENTRIES = 2000
MAX_NOTE_BYTES = 500_000
MAX_COPY_NOTES = 20
_EXCLUDED = {".obsidian", ".trash", ".git", "node_modules", "__MACOSX"}


class ObsidianConnectionValidationError(ObsidianWorkspaceValidationError, ValueError):
    pass


def _invalid(message):
    raise ObsidianConnectionValidationError(message)


def _safe_zip_path(name):
    if (not name or "\\" in name or "\x00" in name or name.startswith("/")
            or re.match(r"^[A-Za-z]:", name)):
        _invalid("The ZIP contains an unsafe path. Choose a fresh vault export.")
    parts = PurePosixPath(name).parts
    if any(part in {"..", "."} or ":" in part for part in parts):
        _invalid("The ZIP contains an unsafe path. Choose a fresh vault export.")
    return parts


class ObsidianConnectionService:
    def __init__(self, config_api, workspace, notes, snapshots_root):
        self.config_api = config_api
        self.workspace = workspace
        self.notes = notes
        self.snapshots_root = Path(snapshots_root)

    def status(self):
        config = self.config_api.load_config()
        path = str(config.get("vault_path") or "")
        valid = bool(path and self.config_api.validate_vault_path(path)[0])
        snapshot = config.get("connection_mode") == "snapshot"
        return {
            "configured": bool(path), "connected": bool(config.get("enabled") and valid),
            "mode": "snapshot" if snapshot else "folder",
            "name": str(config.get("snapshot_name") or Path(path).name) if snapshot else Path(path).name,
            "imported_at": str(config.get("snapshot_imported_at") or "") if snapshot else "",
            "state": "Connected" if config.get("enabled") and valid else ("Unavailable" if path else "Not connected"),
        }

    def import_snapshot(self, raw):
        if not raw or len(raw) > MAX_ARCHIVE_BYTES:
            _invalid("Choose a vault ZIP snapshot of 25 MB or smaller.")
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries = archive.infolist()
                if len(entries) > MAX_ENTRIES or sum(item.file_size for item in entries) > MAX_EXPANDED_BYTES:
                    _invalid("The ZIP exceeds 2,000 entries or 100 MB expanded. Export a smaller vault.")
                paths = []
                markers = set()
                seen = set()
                for item in entries:
                    parts = _safe_zip_path(item.filename)
                    if not parts:
                        _invalid("The ZIP contains an empty path.")
                    mode = (item.external_attr >> 16) & 0o170000
                    if mode not in (0, stat.S_IFREG, stat.S_IFDIR) or item.flag_bits & 1:
                        _invalid("Encrypted ZIP entries and links are not supported.")
                    key = "/".join(parts).casefold()
                    if key in seen:
                        _invalid("The ZIP contains duplicate paths.")
                    seen.add(key)
                    if ".obsidian" in parts:
                        marker = parts.index(".obsidian")
                        if marker == len(parts) - 1 and not item.is_dir():
                            _invalid("The .obsidian marker must be a folder.")
                        markers.add(parts[:marker])
                    paths.append((item, parts))
                if len(markers) != 1:
                    _invalid("Include one vault and its hidden .obsidian folder in the ZIP.")
                prefix = next(iter(markers))
                markdown = []
                total = 0
                for item, parts in paths:
                    if parts[:len(prefix)] != prefix:
                        _invalid("The ZIP must contain a single Obsidian vault.")
                    relative = parts[len(prefix):]
                    if not relative or item.is_dir() or any(part in _EXCLUDED for part in relative):
                        continue
                    if not relative[-1].lower().endswith(".md"):
                        continue
                    if item.file_size > MAX_NOTE_BYTES:
                        _invalid("Each Markdown note must be 500 KB or smaller.")
                    with archive.open(item) as stream:
                        content = stream.read(MAX_NOTE_BYTES + 1)
                    total += len(content)
                    if len(content) > MAX_NOTE_BYTES or total > MAX_EXPANDED_BYTES:
                        _invalid("The expanded Markdown exceeds the snapshot limit.")
                    content.decode("utf-8-sig")
                    markdown.append((relative, content))
                if not markdown:
                    _invalid("No UTF-8 Markdown notes were found in this vault ZIP.")
        except (zipfile.BadZipFile, zipfile.LargeZipFile, UnicodeError, RuntimeError, NotImplementedError) as error:
            if isinstance(error, ObsidianConnectionValidationError):
                raise
            raise ObsidianConnectionValidationError("Choose a readable ZIP containing UTF-8 Markdown and a .obsidian folder.") from error

        if self.snapshots_root.is_symlink():
            _invalid("The snapshot storage folder is unavailable.")
        self.snapshots_root.mkdir(parents=True, exist_ok=True)
        folder = Path(tempfile.mkdtemp(prefix="vault-", dir=self.snapshots_root))
        try:
            (folder / ".obsidian").mkdir()
            # Native backups preserve files, not empty directories. This inert
            # marker keeps a restored snapshot valid for the existing reader.
            (folder / ".obsidian" / "app.json").write_text("{}", encoding="utf-8")
            for relative, content in markdown:
                destination = folder.joinpath(*relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
            config = dict(self.config_api.load_config())
            config.update(vault_path=str(folder), enabled=True, connection_mode="snapshot",
                          snapshot_id=folder.name,
                          snapshot_name=prefix[-1] if prefix else "Vault snapshot",
                          snapshot_imported_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
            self.config_api.save_config(config)
        except Exception:
            shutil.rmtree(folder)
            raise
        return {"markdown_files": len(markdown)}

    def connect_folder(self, path):
        return self.workspace.connect_vault(path)

    def disconnect(self):
        config = dict(self.config_api.load_config())
        for key in ("connection_mode", "snapshot_id", "snapshot_name", "snapshot_imported_at"):
            config.pop(key, None)
        config.update(vault_path="", enabled=False)
        self.config_api.save_config(config)

    def copy_notes(self, paths):
        selected = list(dict.fromkeys(paths))
        if not selected or len(selected) > MAX_COPY_NOTES:
            _invalid("Select between 1 and 20 Markdown notes to copy.")
        # Validate every selected source before creating any independent copies.
        sources = []
        for path in selected:
            try:
                source = self.workspace.note_preview(path)
            except ObsidianWorkspaceValidationError as error:
                raise ObsidianConnectionValidationError(str(error)) from error
            if len(source["text"]) > MAX_NOTE_BYTES:
                _invalid("Each note must contain 500,000 characters or fewer to copy.")
            sources.append(source)
        return self.notes.create_typed_notes([
            {"title": source["title"], "body": source["text"]} for source in sources
        ])


def build_obsidian_connection_service(workspace=None, notes=None):
    import obsidian_integration as config_api
    from .obsidian_workspace_service import build_obsidian_workspace_service
    from .anvaya_notes_service import build_anvaya_notes_service
    return ObsidianConnectionService(config_api, workspace or build_obsidian_workspace_service(),
                                     notes or build_anvaya_notes_service(),
                                     Path(config_api.DATA_DIR) / "obsidian_snapshots")
