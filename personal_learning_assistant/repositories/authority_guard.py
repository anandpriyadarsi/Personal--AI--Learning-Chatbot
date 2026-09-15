"""Shared Phase 4.10 guard for legacy structured JSON writers.

The authority-control file lives outside ``data/`` so the Phase 3 legacy source
scanner does not mistake it for another legacy JSON source.  Merely importing
this module never creates files or directories.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Union

from personal_learning_assistant.migration.authority_promotion import (
    AuthorityControlState,
    assert_legacy_write_allowed,
)


PathLike = Union[str, Path]
AUTHORITY_CONTROL_FILENAME = ".phase4_authority.json"


def _authority_root_for_store(path: Path) -> Path:
    parent = path.parent
    if parent.name.casefold() == "data":
        return parent.parent
    return parent


def infer_authority_control_path(*store_paths: PathLike) -> Path:
    """Infer one project-local control path from structured store paths.

    Normal production paths such as ``<project>/data/courses.json`` resolve to
    ``<project>/.phase4_authority.json``.  Temporary tests using another data
    directory therefore stay isolated automatically.
    """
    if not store_paths:
        raise ValueError("at least one structured store path is required")

    roots = tuple(_authority_root_for_store(Path(item)) for item in store_paths)
    first = roots[0]
    if any(root != first for root in roots[1:]):
        raise ValueError("structured store paths do not share one authority root")
    return first / AUTHORITY_CONTROL_FILENAME


def guard_legacy_structured_write(control_path: PathLike) -> AuthorityControlState:
    """Fail closed when SQLite has been atomically promoted to authority."""
    return assert_legacy_write_allowed(Path(control_path))


__all__ = (
    "AUTHORITY_CONTROL_FILENAME",
    "guard_legacy_structured_write",
    "infer_authority_control_path",
)
