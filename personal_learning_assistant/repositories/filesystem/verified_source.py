"""Shared bounded descriptor reads for external sources and ingestion."""
import os
import stat
from pathlib import Path


class UnsafeSourceError(OSError):
    pass


def reject_symlink_components(path):
    path = Path(path).absolute()
    for candidate in (*reversed(path.parents), path):
        if candidate.is_symlink():
            raise UnsafeSourceError('Source paths must not contain symlinks.')
    return path


def read_verified_bytes(path, *, max_bytes):
    path = reject_symlink_components(path)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(descriptor, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
            raise UnsafeSourceError('Source exceeds the safe read limit or is not a regular file.')
        raw = stream.read(max_bytes + 1)
        after = os.fstat(stream.fileno())
    reject_symlink_components(path)
    current = path.stat()
    keys = ('st_dev','st_ino','st_size','st_mtime_ns')
    if len(raw) > max_bytes or any(getattr(before,k) != getattr(after,k) or getattr(after,k) != getattr(current,k) for k in keys):
        raise UnsafeSourceError('Source changed during the read or exceeds the safe read limit.')
    return raw
