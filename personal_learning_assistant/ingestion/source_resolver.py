"""Explicit logical-root resolution for registered local knowledge sources."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
from typing import Mapping, Optional, Tuple
from personal_learning_assistant.repositories.filesystem.verified_source import reject_symlink_components, read_verified_bytes

class SourceResolutionError(RuntimeError): pass
class SourceMissingError(SourceResolutionError): pass
class SourceUnsafePathError(SourceResolutionError): pass

class SourceRootResolver:
    def __init__(self, roots: Mapping[str, os.PathLike]):
        prepared = {}
        for key, raw_path in roots.items():
            logical = str(key or "").strip().casefold()
            if not logical or "/" in logical or "\\" in logical: raise ValueError("source root keys must be simple logical names")
            try:
                path = reject_symlink_components(raw_path).resolve(strict=False)
            except OSError as error:
                raise SourceUnsafePathError('Source root must not contain symlinks.') from error
            if not path.is_dir() or path.is_symlink(): raise SourceUnsafePathError("source root must be an existing non-symlink directory: {}".format(path))
            prepared[logical] = path
        self.roots = prepared
    def resolve(self, path_key: Optional[str]) -> Optional[Path]:
        text = str(path_key or "").strip().replace("\\", "/")
        if not text: return None
        if "/" not in text: raise SourceResolutionError("registered path_key has no logical root prefix")
        root_key, relative = text.split("/", 1); root = self.roots.get(root_key.casefold())
        if root is None: raise SourceResolutionError("no local source root mapping for {}".format(root_key))
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts: raise SourceUnsafePathError("registered source path escapes logical root")
        try:
            path = reject_symlink_components(root / relative_path).resolve(strict=False)
        except OSError as error:
            raise SourceUnsafePathError('Registered source must not contain symlinks.') from error
        if path == root or root not in path.parents: raise SourceUnsafePathError("registered source path escapes logical root")
        if not path.exists(): raise SourceMissingError("registered source file is missing")
        if path.is_symlink() or not path.is_file(): raise SourceUnsafePathError("registered source is not a regular non-symlink file")
        return path
    @staticmethod
    def snapshot(path: Path) -> Tuple[bytes, str]:
        try:
            raw = read_verified_bytes(path, max_bytes=100 * 1024 * 1024)
        except OSError as error:
            raise SourceResolutionError('Source is unsafe, changed, or exceeds the 100 MB ingestion limit.') from error
        return raw, hashlib.sha256(raw).hexdigest()
