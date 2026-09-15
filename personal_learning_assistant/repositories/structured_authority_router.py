"""Phase 4.11 runtime routing for structured legacy compatibility stores.

The router is intentionally small and side-effect controlled:

* missing/legacy/dual_read authority keeps the existing JSON code path;
* sqlite authority opens only an already-existing database in read/write mode;
* no database or authority-control file is created by a read;
* exact legacy-shaped compatibility projections live inside SQLite app_settings;
* the Phase-5 ``courses.json.document_links`` sub-domain remains legacy-owned.

Top-level V8-V13 compatibility modules call ``maybe_load_*`` / ``maybe_save_*``
so their public signatures remain unchanged.  Returning ``None`` / ``False``
means "continue with the existing legacy implementation".
"""

from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Optional, Union
from urllib.parse import quote

from personal_learning_assistant.migration.authority_promotion import (
    BACKEND_SQLITE,
    LegacyWriteBlockedError,
    read_authority_control,
)
from personal_learning_assistant.repositories.authority_guard import (
    infer_authority_control_path,
)


PathLike = Union[str, Path]
DATABASE_FILENAME = "learning_assistant.db"

STORE_COURSES = "courses"
STORE_ASSESSMENTS = "assessments"
STORE_ASSESSMENT_WORKSPACE = "assessment_workspace"
STORE_LEARNING_MEMORY = "learning_memory"
STORE_PROGRESS_HISTORY = "course_progress_history"
STORE_WEEKLY_PLANS = "weekly_study_plans"
STORE_MULTI_COURSE_PLANS = "multi_course_weekly_plans"
STORE_INTELLIGENT_PLANS = "intelligent_study_plans"
STORE_GRADE_CONFIG = "semester_grade_config"

STRUCTURED_STORE_NAMES = {
    STORE_COURSES,
    STORE_ASSESSMENTS,
    STORE_ASSESSMENT_WORKSPACE,
    STORE_LEARNING_MEMORY,
    STORE_PROGRESS_HISTORY,
    STORE_WEEKLY_PLANS,
    STORE_MULTI_COURSE_PLANS,
    STORE_INTELLIGENT_PLANS,
    STORE_GRADE_CONFIG,
}


class StructuredAuthorityRoutingError(RuntimeError):
    """Base error for Phase 4.11 runtime structured routing."""


class StructuredDatabaseUnavailableError(StructuredAuthorityRoutingError):
    """Raised when SQLite authority is active but its database is unavailable."""


class DeferredStructuredDomainWriteError(StructuredAuthorityRoutingError):
    """Raised when a Phase-5-deferred field would be changed after cutover."""


def _store_path(path: PathLike) -> Path:
    return Path(path)


def _project_root_for_store(path: Path) -> Path:
    parent = path.parent
    if parent.name.casefold() == "data":
        return parent.parent
    return parent


def database_path_for_store(path: PathLike) -> Path:
    store = _store_path(path)
    return _project_root_for_store(store) / "data" / DATABASE_FILENAME


def current_structured_backend(path: PathLike) -> str:
    control = infer_authority_control_path(_store_path(path))
    return read_authority_control(control).storage_backend


def _open_existing_database(path: Path) -> sqlite3.Connection:
    if not path.exists() or not path.is_file() or path.is_symlink():
        raise StructuredDatabaseUnavailableError(
            "SQLite authority is active but the structured database does not exist as a regular file: {}"
            .format(path)
        )
    # mode=rw prevents sqlite3.connect from silently creating a replacement DB.
    uri = "file:{}?mode=rw".format(quote(str(path.resolve()).replace("\\", "/"), safe="/:"))
    try:
        connection = sqlite3.connect(uri, uri=True, isolation_level=None)
    except sqlite3.Error as error:
        raise StructuredDatabaseUnavailableError(
            "unable to open the authoritative SQLite database in rw mode: {}".format(error)
        ) from error
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _legacy_document_links(path: Path) -> Mapping[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, Mapping):
        return {}
    links = raw.get("document_links", {})
    return deepcopy(dict(links)) if isinstance(links, Mapping) else {}


def _prepare_course_payload_for_sqlite(path: Path, payload: Mapping[str, Any]) -> dict:
    result = deepcopy(dict(payload))
    requested_links = result.get("document_links", {})
    if not isinstance(requested_links, Mapping):
        requested_links = {}
    legacy_links = _legacy_document_links(path)
    if dict(requested_links) != dict(legacy_links):
        raise DeferredStructuredDomainWriteError(
            "Course document_links remain a Phase 5 legacy-owned sub-domain. "
            "Phase 4.11 can update courses/topics after SQLite promotion only when document_links are unchanged."
        )
    # Do not copy the Phase-5-deferred authority into SQLite compatibility state.
    result["document_links"] = {}
    return result


def maybe_load_sqlite_structured_store(
    store_name: str,
    store_path: PathLike,
) -> Optional[Any]:
    """Return an SQLite compatibility projection only after authority promotion.

    ``None`` means the caller must continue through its pre-existing legacy path.
    """
    if store_name not in STRUCTURED_STORE_NAMES:
        raise ValueError("unknown structured store: {}".format(store_name))
    path = _store_path(store_path)
    control = infer_authority_control_path(path)
    state = read_authority_control(control)
    if state.storage_backend != BACKEND_SQLITE:
        return None

    from personal_learning_assistant.repositories.sqlite.compatibility_repository import (
        SQLiteCompatibilityProjectionRepository,
    )

    connection = _open_existing_database(database_path_for_store(path))
    try:
        repository = SQLiteCompatibilityProjectionRepository(
            connection,
            authority_control_path=control,
        )
        payload = repository.load_projection(store_name)
    finally:
        connection.close()

    if store_name == STORE_COURSES:
        payload = deepcopy(payload)
        payload["document_links"] = deepcopy(_legacy_document_links(path))
    return payload


def maybe_save_sqlite_structured_store(
    store_name: str,
    store_path: PathLike,
    payload: Mapping[str, Any],
) -> bool:
    """Persist through SQLite when promoted; otherwise leave legacy code untouched."""
    if store_name not in STRUCTURED_STORE_NAMES:
        raise ValueError("unknown structured store: {}".format(store_name))
    if not isinstance(payload, Mapping):
        raise TypeError("structured store payload must be a mapping")

    path = _store_path(store_path)
    control = infer_authority_control_path(path)
    state = read_authority_control(control)
    if state.storage_backend != BACKEND_SQLITE:
        return False

    from personal_learning_assistant.repositories.sqlite.compatibility_repository import (
        SQLiteCompatibilityProjectionRepository,
    )

    prepared = (
        _prepare_course_payload_for_sqlite(path, payload)
        if store_name == STORE_COURSES
        else deepcopy(dict(payload))
    )
    try:
        connection = _open_existing_database(database_path_for_store(path))
    except StructuredDatabaseUnavailableError as error:
        # Phase 4.10 established the compatibility-writer contract that once
        # SQLite authority is active, old JSON writers fail with
        # LegacyWriteBlockedError *before* they can create or modify legacy
        # data. Phase 4.11 routing must preserve that contract even when the
        # authoritative database itself is missing/unopenable. Reads still
        # surface StructuredDatabaseUnavailableError directly; writes fail
        # closed as a blocked legacy write and retain the database error as
        # the chained cause for diagnosis.
        raise LegacyWriteBlockedError(
            "Legacy structured JSON writes remain blocked because SQLite is "
            "authoritative, but the authoritative SQLite database is unavailable."
        ) from error
    try:
        repository = SQLiteCompatibilityProjectionRepository(
            connection,
            authority_control_path=control,
        )
        repository.save_projection(store_name, prepared)
    finally:
        connection.close()
    return True


__all__ = (
    "DATABASE_FILENAME",
    "DeferredStructuredDomainWriteError",
    "STORE_ASSESSMENTS",
    "STORE_ASSESSMENT_WORKSPACE",
    "STORE_COURSES",
    "STORE_GRADE_CONFIG",
    "STORE_INTELLIGENT_PLANS",
    "STORE_LEARNING_MEMORY",
    "STORE_MULTI_COURSE_PLANS",
    "STORE_PROGRESS_HISTORY",
    "STORE_WEEKLY_PLANS",
    "STRUCTURED_STORE_NAMES",
    "StructuredAuthorityRoutingError",
    "StructuredDatabaseUnavailableError",
    "current_structured_backend",
    "database_path_for_store",
    "maybe_load_sqlite_structured_store",
    "maybe_save_sqlite_structured_store",
)
