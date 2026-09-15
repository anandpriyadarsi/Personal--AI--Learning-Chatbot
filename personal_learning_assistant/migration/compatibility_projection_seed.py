"""Pre-promotion seeding for Phase 4.11 SQLite compatibility projections.

Run this only inside the final locked cutover *after* the last legacy delta has
been imported/reconciled and *before* ``storage_backend=sqlite`` is written.
It copies exact application-visible structured JSON shapes into SQLite
``app_settings``.  The normalized relational tables remain populated by the
Phase 3 importers; this seed does not rewrite migration ledger history.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple, Union

from personal_learning_assistant.migration.authority_promotion import (
    BACKEND_SQLITE,
    read_authority_control,
    scan_structured_sources,
    validate_structured_manifest,
)
from personal_learning_assistant.repositories.sqlite.compatibility_repository import (
    PROJECTION_PREFIX,
    STORE_ASSESSMENTS,
    STORE_ASSESSMENT_WORKSPACE,
    STORE_COURSES,
    STORE_GRADE_CONFIG,
    STORE_INTELLIGENT_PLANS,
    STORE_LEARNING_MEMORY,
    STORE_MULTI_COURSE_PLANS,
    STORE_PROGRESS_HISTORY,
    STORE_WEEKLY_PLANS,
)


PathLike = Union[str, Path]
SEED_MANIFEST_SETTING = "phase4.compatibility_projection_manifest_hash"

_SOURCE_TO_STORE = {
    "courses.json": STORE_COURSES,
    "assessments.json": STORE_ASSESSMENTS,
    "assessment_workspace.json": STORE_ASSESSMENT_WORKSPACE,
    "learning_memory.json": STORE_LEARNING_MEMORY,
    "course_progress_history.json": STORE_PROGRESS_HISTORY,
    "weekly_study_plans.json": STORE_WEEKLY_PLANS,
    "multi_course_weekly_plans.json": STORE_MULTI_COURSE_PLANS,
    "intelligent_study_plans.json": STORE_INTELLIGENT_PLANS,
    "semester_grade_config.json": STORE_GRADE_CONFIG,
}

_DEFAULT_GRADE_SCALE = [
    {"letter": "A+", "min_score": 90.0, "grade_point": 10.0},
    {"letter": "A", "min_score": 80.0, "grade_point": 9.0},
    {"letter": "B+", "min_score": 70.0, "grade_point": 8.0},
    {"letter": "B", "min_score": 60.0, "grade_point": 7.0},
    {"letter": "C", "min_score": 50.0, "grade_point": 6.0},
    {"letter": "D", "min_score": 40.0, "grade_point": 5.0},
    {"letter": "F", "min_score": 0.0, "grade_point": 0.0},
]


class CompatibilityProjectionSeedError(RuntimeError):
    pass


@dataclass(frozen=True)
class CompatibilityProjectionSeedResult:
    manifest_hash: str
    seeded_stores: Tuple[str, ...]
    optional_defaults: Tuple[str, ...]
    total_changes_before: int
    total_changes_after: int


def _default_optional(filename: str) -> Mapping[str, Any]:
    if filename == "intelligent_study_plans.json":
        return {"version": 1, "plans": []}
    if filename == "semester_grade_config.json":
        return {
            "version": 1,
            "semester_name": "Semester 1",
            "target_sgpa": None,
            "courses": [],
            "grade_scale": list(_DEFAULT_GRADE_SCALE),
        }
    raise CompatibilityProjectionSeedError("no default for optional source: {}".format(filename))


def _read_payload(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CompatibilityProjectionSeedError(
            "unable to load structured source for projection seed: {}".format(path.name)
        ) from error
    if not isinstance(value, Mapping):
        raise CompatibilityProjectionSeedError(
            "structured source must contain a top-level JSON object: {}".format(path.name)
        )
    return dict(value)


def seed_phase4_compatibility_projections(
    connection: sqlite3.Connection,
    *,
    data_directory: PathLike,
    authority_control_path: PathLike,
    seeded_at: str,
    replace: bool = False,
) -> CompatibilityProjectionSeedResult:
    """Atomically seed all Phase-4 compatibility projections before promotion."""
    if not isinstance(connection, sqlite3.Connection):
        raise TypeError("connection must be an open sqlite3.Connection")
    if connection.in_transaction:
        raise CompatibilityProjectionSeedError("projection seed refuses nested transactions")
    state = read_authority_control(authority_control_path)
    if state.storage_backend == BACKEND_SQLITE:
        raise CompatibilityProjectionSeedError(
            "compatibility projections must be seeded before SQLite authority is activated"
        )
    seeded_at = str(seeded_at or "").strip()
    if not seeded_at:
        raise CompatibilityProjectionSeedError("seeded_at must not be empty")

    data = Path(data_directory)
    manifest = scan_structured_sources(data)
    validate_structured_manifest(manifest)

    payloads: Dict[str, Mapping[str, Any]] = {}
    optional_defaults = []
    snapshot_by_name = {Path(item.canonical_path).name: item for item in manifest.sources}
    for filename, store_name in _SOURCE_TO_STORE.items():
        snapshot = snapshot_by_name.get(filename)
        if snapshot is None:
            raise CompatibilityProjectionSeedError("manifest omitted expected source: {}".format(filename))
        if snapshot.status == "missing":
            payloads[store_name] = _default_optional(filename)
            optional_defaults.append(store_name)
            continue
        payload = _read_payload(data / filename)
        if store_name == STORE_COURSES:
            # document_links remain Phase-5 legacy-owned and readable from JSON.
            payload = dict(payload)
            payload["document_links"] = {}
        payloads[store_name] = payload

    before = connection.total_changes
    connection.execute("BEGIN IMMEDIATE")
    try:
        for store_name, payload in payloads.items():
            key = PROJECTION_PREFIX + store_name
            exists = connection.execute(
                "SELECT 1 FROM app_settings WHERE key=?", (key,)
            ).fetchone()
            if exists is not None and not replace:
                raise CompatibilityProjectionSeedError(
                    "compatibility projection already exists: {}".format(store_name)
                )
            connection.execute(
                "INSERT INTO app_settings (key,value_json,updated_at) VALUES (?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
                (
                    key,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    seeded_at,
                ),
            )
        connection.execute(
            "INSERT INTO app_settings (key,value_json,updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
            (SEED_MANIFEST_SETTING, json.dumps(manifest.manifest_hash), seeded_at),
        )
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()
    after = connection.total_changes
    return CompatibilityProjectionSeedResult(
        manifest_hash=manifest.manifest_hash,
        seeded_stores=tuple(sorted(payloads)),
        optional_defaults=tuple(sorted(optional_defaults)),
        total_changes_before=before,
        total_changes_after=after,
    )


__all__ = (
    "CompatibilityProjectionSeedError",
    "CompatibilityProjectionSeedResult",
    "SEED_MANIFEST_SETTING",
    "seed_phase4_compatibility_projections",
)
