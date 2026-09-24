"""Atomic Markdown file operations for Notes Studio.

This module never opens SQLite. It provides expected-hash conflict protection
and atomic replace/move primitives for a configured Obsidian vault.
"""
from __future__ import annotations
import hashlib, os, re, unicodedata
from pathlib import Path
from typing import Optional, Tuple, Union

PathLike = Union[str, os.PathLike]
_RESERVED = {"CON","PRN","AUX","NUL",*(f"COM{i}" for i in range(1,10)),*(f"LPT{i}" for i in range(1,10))}
_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

class MarkdownStoreError(RuntimeError): pass
class MarkdownConflictError(MarkdownStoreError): pass
class MarkdownPathError(MarkdownStoreError): pass


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def safe_filename(title: str) -> str:
    value = unicodedata.normalize("NFC", str(title or "").strip())
    value = _INVALID.sub("-", value).rstrip(" .")
    value = re.sub(r"\s+", " ", value).strip()
    if not value: value = "Untitled"
    stem = value.split(".",1)[0].upper()
    if stem in _RESERVED: value = value + "-note"
    value = value[:120].rstrip(" .") or "Untitled"
    return value + ".md"


def safe_attachment_filename(filename: str) -> str:
    raw = str(filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    raw = unicodedata.normalize("NFC", raw.strip())
    suffix = Path(raw).suffix.casefold()
    if suffix not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        raise MarkdownPathError("unsupported attachment type")
    stem = Path(raw).stem
    stem = _INVALID.sub("-", stem).rstrip(" .")
    stem = re.sub(r"[\[\]()]", "-", stem)
    stem = re.sub(r"\s+", " ", stem).strip() or "image"
    if stem.upper() in _RESERVED:
        stem += "-image"
    stem = stem[:100].rstrip(" .") or "image"
    return stem + suffix

class AtomicMarkdownNoteStore:
    def __init__(self, vault_root: PathLike):
        self.root = Path(vault_root).resolve(strict=False)
        if not self.root.is_dir() or self.root.is_symlink():
            raise MarkdownPathError("vault root must be an existing non-symlink directory")

    def _resolve(self, relative_path: str) -> Path:
        rel = Path(str(relative_path).replace("\\","/"))
        if rel.is_absolute() or ".." in rel.parts:
            raise MarkdownPathError("note path must remain inside the vault")
        target = (self.root / rel).resolve(strict=False)
        if target == self.root or self.root not in target.parents:
            raise MarkdownPathError("note path escapes the vault")
        return target

    def read(self, relative_path: str) -> Tuple[bytes,str]:
        path=self._resolve(relative_path)
        raw=path.read_bytes()
        return raw, sha256_bytes(raw)

    def choose_create_path(self, inbox: str, title: str) -> str:
        folder = Path(str(inbox).replace("\\","/"))
        base = safe_filename(title)
        stem, suffix = Path(base).stem, Path(base).suffix
        candidate = folder / base
        number=2
        while self._resolve(candidate.as_posix()).exists():
            candidate = folder / f"{stem} ({number}){suffix}"
            number += 1
        return candidate.as_posix()

    def atomic_write(self, relative_path: str, payload: bytes, *, expected_hash: Optional[str]=None) -> str:
        path=self._resolve(relative_path)
        if path.exists():
            if path.is_symlink() or not path.is_file(): raise MarkdownPathError("target is not a regular note file")
            current=sha256_bytes(path.read_bytes())
            if expected_hash is not None and current != expected_hash:
                raise MarkdownConflictError("note changed on disk; expected hash does not match")
        elif expected_hash is not None:
            raise MarkdownConflictError("note disappeared before write")
        path.parent.mkdir(parents=True, exist_ok=True)
        temp=path.with_name(path.name+".notes-studio.tmp")
        try:
            with temp.open("wb") as handle:
                handle.write(payload); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp,path)
        finally:
            if temp.exists():
                try: temp.unlink()
                except OSError: pass
        return sha256_bytes(payload)

    def choose_attachment_path(self, note_relative: str, note_id: str, filename: str) -> str:
        note_path = Path(str(note_relative).replace("\\", "/"))
        namespace = re.sub(r"[^A-Za-z0-9_-]", "-", str(note_id or "").strip())
        if not namespace:
            raise MarkdownPathError("note identity is required for attachment path")
        base = safe_attachment_filename(filename)
        folder = note_path.parent / "_attachments" / namespace
        candidate = folder / base
        stem, suffix = Path(base).stem, Path(base).suffix
        number = 2
        while self._resolve(candidate.as_posix()).exists():
            candidate = folder / f"{stem} ({number}){suffix}"
            number += 1
        return candidate.as_posix()

    def atomic_write_attachment(
        self,
        note_relative: str,
        note_id: str,
        filename: str,
        payload: bytes,
        *,
        expected_note_hash: str,
    ):
        _raw, current_hash = self.read(note_relative)
        if current_hash != str(expected_note_hash or ""):
            raise MarkdownConflictError(
                "note changed on disk; refresh before attaching files"
            )
        relative_path = self.choose_attachment_path(
            note_relative,
            note_id,
            filename,
        )
        asset_hash = self.atomic_write(relative_path, bytes(payload))
        return relative_path, asset_hash

    def move(self, source_relative: str, target_relative: str, *, expected_hash: str) -> str:
        source=self._resolve(source_relative); target=self._resolve(target_relative)
        if not source.is_file() or source.is_symlink(): raise MarkdownConflictError("source note is missing/not regular")
        current=sha256_bytes(source.read_bytes())
        if current != expected_hash: raise MarkdownConflictError("note changed on disk before move")
        if target.exists(): raise MarkdownConflictError("target path already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source,target)
        return current
