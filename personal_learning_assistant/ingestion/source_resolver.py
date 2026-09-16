"""Explicit logical-root resolution for registered local knowledge sources."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
from typing import Mapping, Optional, Tuple

class SourceResolutionError(RuntimeError): pass
class SourceMissingError(SourceResolutionError): pass
class SourceUnsafePathError(SourceResolutionError): pass

class SourceRootResolver:
    def __init__(self, roots: Mapping[str, os.PathLike]):
        prepared = {}
        for key, raw_path in roots.items():
            logical = str(key or "").strip().casefold()
            if not logical or "/" in logical or "\\" in logical: raise ValueError("source root keys must be simple logical names")
            path = Path(raw_path).resolve(strict=False)
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
        path = (root / relative_path).resolve(strict=False)
        if path == root or root not in path.parents: raise SourceUnsafePathError("registered source path escapes logical root")
        if not path.exists(): raise SourceMissingError("registered source file is missing")
        if path.is_symlink() or not path.is_file(): raise SourceUnsafePathError("registered source is not a regular non-symlink file")
        return path
    @staticmethod
    def snapshot(path: Path) -> Tuple[bytes, str]:
        before = path.stat(); raw = path.read_bytes(); after = path.stat()
        if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns: raise SourceResolutionError("source changed while ingestion snapshot was read")
        return raw, hashlib.sha256(raw).hexdigest()
