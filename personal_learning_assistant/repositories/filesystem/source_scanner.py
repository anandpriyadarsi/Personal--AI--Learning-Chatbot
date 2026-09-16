"""Deterministic read-only filesystem scanner for Phase 5.2.

The scanner hashes source bytes and records metadata only. It never creates,
renames, moves, rewrites or deletes source files/directories.
"""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Tuple, Union

from personal_learning_assistant.domain.source_scanner_models import (
    SourceFingerprint,
    SourceScanIssue,
    SourceScanResult,
    SourceScanRoot,
)


PathLike = Union[str, os.PathLike]
_ROOT_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

# Registration support only. Extraction support is intentionally later.
SOURCE_TYPES: Mapping[str, Tuple[str, str]] = {
    ".md": ("markdown", "text/markdown"),
    ".txt": ("text", "text/plain"),
    ".pdf": ("pdf", "application/pdf"),
    ".pptx": (
        "powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ),
    ".ppt": ("powerpoint", "application/vnd.ms-powerpoint"),
    ".docx": (
        "document",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    ".doc": ("document", "application/msword"),
    ".json": ("json", "application/json"),
    ".jsonl": ("jsonl", "application/x-ndjson"),
    ".srt": ("transcript", "application/x-subrip"),
    ".vtt": ("transcript", "text/vtt"),
    ".csv": ("tabular", "text/csv"),
    ".html": ("html", "text/html"),
    ".htm": ("html", "text/html"),
}


class SourceScannerError(RuntimeError):
    """Base scanner failure."""


class SourceRootError(SourceScannerError):
    """Invalid or unsafe configured root."""


def _hash_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp(mtime_ns: int) -> str:
    seconds = mtime_ns / 1_000_000_000
    return (
        datetime.fromtimestamp(seconds, timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _manifest_hash(sources: Iterable[SourceFingerprint]) -> str:
    digest = hashlib.sha256()
    for source in sorted(sources, key=lambda item: item.path_key):
        row = "\0".join(
            (
                source.path_key,
                source.kind,
                source.mime_type,
                source.content_hash,
                str(source.size_bytes),
                source.source_timestamp,
            )
        )
        digest.update(row.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


class FileSystemSourceScanner:
    """Fingerprint supported files below one explicit non-symlink root."""

    def __init__(
        self,
        root_key: str,
        root_path: PathLike,
        *,
        source_types: Mapping[str, Tuple[str, str]] = SOURCE_TYPES,
    ):
        key = str(root_key or "").strip().lower()
        if not _ROOT_KEY.fullmatch(key):
            raise ValueError(
                "root_key must match [a-z0-9][a-z0-9._-]*"
            )
        self.root_key = key
        # ``absolute`` normalizes the operator-supplied path without resolving
        # symlinks. Resolving here would hide a symlink root before safety
        # validation.
        self.root_path = Path(
            os.path.abspath(
                os.fspath(root_path)
            )
        )
        self.source_types = {
            str(extension).lower(): (str(values[0]), str(values[1]))
            for extension, values in source_types.items()
        }

    def _validate_root(self) -> None:
        if not self.root_path.exists():
            raise SourceRootError(
                "source root does not exist: {}".format(self.root_path)
            )
        if self.root_path.is_symlink():
            raise SourceRootError(
                "source root must not be a symlink: {}".format(self.root_path)
            )
        if not self.root_path.is_dir():
            raise SourceRootError(
                "source root is not a directory: {}".format(self.root_path)
            )

    def _path_key(self, path: Path) -> str:
        try:
            relative = path.relative_to(self.root_path)
        except ValueError as error:
            raise SourceScannerError(
                "scanner path escaped configured root"
            ) from error
        relative_text = relative.as_posix()
        if relative_text.startswith("../") or relative_text == "..":
            raise SourceScannerError("scanner path escaped configured root")
        return "{}/{}".format(self.root_key, relative_text)

    def scan(self) -> SourceScanResult:
        self._validate_root()
        sources = []
        issues = []
        unsupported = 0
        ignored_symlinks = 0

        for current_root, dir_names, file_names in os.walk(
            str(self.root_path), topdown=True, followlinks=False
        ):
            current = Path(current_root)
            kept_dirs = []
            for name in sorted(dir_names):
                candidate = current / name
                if candidate.is_symlink():
                    ignored_symlinks += 1
                    continue
                kept_dirs.append(name)
            dir_names[:] = kept_dirs

            for file_name in sorted(file_names):
                path = current / file_name
                try:
                    if path.is_symlink():
                        ignored_symlinks += 1
                        continue
                    extension = path.suffix.lower()
                    source_type = self.source_types.get(extension)
                    if source_type is None:
                        unsupported += 1
                        continue
                    before = path.stat()
                    if not path.is_file():
                        continue
                    content_hash = _hash_file(path)
                    after = path.stat()
                    path_key = self._path_key(path)
                    if (
                        before.st_size != after.st_size
                        or before.st_mtime_ns != after.st_mtime_ns
                    ):
                        issues.append(
                            SourceScanIssue(
                                category="unstable_file",
                                path_key=path_key,
                                message=(
                                    "source changed while it was being "
                                    "fingerprinted"
                                ),
                            )
                        )
                        continue
                    kind, mime_type = source_type
                    sources.append(
                        SourceFingerprint(
                            root_key=self.root_key,
                            path_key=path_key,
                            absolute_path=str(
                                Path(
                                    os.path.abspath(
                                        os.fspath(path)
                                    )
                                )
                            ),
                            kind=kind,
                            mime_type=mime_type,
                            content_hash=content_hash,
                            size_bytes=int(after.st_size),
                            source_timestamp=_timestamp(
                                int(after.st_mtime_ns)
                            ),
                        )
                    )
                except OSError as error:
                    try:
                        issue_key = self._path_key(path)
                    except Exception:
                        issue_key = "{}/<unavailable>".format(
                            self.root_key
                        )
                    issues.append(
                        SourceScanIssue(
                            category="unreadable_file",
                            path_key=issue_key,
                            message=type(error).__name__,
                        )
                    )

        ordered = tuple(
            sorted(sources, key=lambda item: item.path_key)
        )
        ordered_issues = tuple(
            sorted(
                issues,
                key=lambda item: (item.path_key, item.category),
            )
        )
        return SourceScanResult(
            root=SourceScanRoot(
                key=self.root_key,
                path=str(self.root_path),
            ),
            sources=ordered,
            issues=ordered_issues,
            ignored_unsupported=unsupported,
            ignored_symlinks=ignored_symlinks,
            manifest_hash=_manifest_hash(ordered),
        )
