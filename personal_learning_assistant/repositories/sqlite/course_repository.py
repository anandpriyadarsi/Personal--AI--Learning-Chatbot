"""Read-only Phase 4.1 SQLite repository for Courses + Topics.

SQLite is a shadow read backend in Phase 4.1.  The repository reconstructs the
legacy CourseRepository state from the Phase 3 relational schema plus migration
ledger evidence.  It intentionally rejects every write method so a
CourseService command can never accidentally make SQLite authoritative.
"""

from __future__ import annotations

import json
import re
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


CourseState = Dict[str, Any]
COURSE_SOURCE_PATH = "data/courses.json"
_REQUIRED_TABLES = {
    "app_settings",
    "courses",
    "migration_imports",
    "semester_courses",
    "semesters",
    "topics",
}


class SQLiteCourseRepositoryError(RuntimeError):
    """Base error for Phase 4.1 SQLite course reads."""


class SQLiteCourseRepositorySchemaError(SQLiteCourseRepositoryError):
    """Raised when the supplied database is not a Phase 3 schema."""


class SQLiteCourseRepositoryDataError(SQLiteCourseRepositoryError):
    """Raised when migration evidence cannot be reconciled with SQLite rows."""


class SQLiteCourseRepositoryReadOnlyError(SQLiteCourseRepositoryError):
    """Raised when a caller attempts a Phase 4.1 SQLite write."""


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _raw_text(value: Any) -> str:
    return "" if value is None else str(value)


def _slug(value: Any) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return slug or "course"


def _fetch_dicts(
    connection: sqlite3.Connection,
    sql: str,
    params: Sequence[Any] = (),
) -> Tuple[Dict[str, Any], ...]:
    cursor = connection.execute(sql, tuple(params))
    columns = tuple(item[0] for item in cursor.description or ())
    return tuple(
        {columns[index]: value for index, value in enumerate(tuple(row))}
        for row in cursor.fetchall()
    )


def _parse_object(raw: Any, *, context: str) -> Dict[str, Any]:
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise SQLiteCourseRepositoryDataError(
            "Invalid migration ledger details for {}.".format(context)
        ) from error
    if not isinstance(value, dict):
        raise SQLiteCourseRepositoryDataError(
            "Migration ledger details must be an object for {}.".format(context)
        )
    return value


def _normalised_confidence(value: Any) -> int:
    if value is None or value == "":
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(5, parsed))


def _aliases(value: Any) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values: Iterable[Any] = (value,)
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = (value,)
    result: List[str] = []
    seen = set()
    for item in values:
        text = _clean_text(item)
        folded = text.casefold()
        if text and folded not in seen:
            seen.add(folded)
            result.append(text)
    return tuple(result)


def _expected_enrollment_status(course_status: str) -> str:
    return {
        "active": "enrolled",
        "planned": "planned",
        "completed": "completed",
        "archived": "archived",
    }.get(str(course_status), "enrolled")


class SQLiteCourseRepository:
    """Read-only CourseRepository adapter over the Phase 3 SQLite shadow DB.

    The repository requires an already-open connection.  It never opens a
    default/production database and never commits, rolls back, migrates, or
    imports data.  All Phase 4.1 writes remain on the legacy repository.
    """

    supports_course_document_links = False
    course_document_relationship_support = (
        "deferred: Phase 3.1 intentionally did not import legacy "
        "courses.json document_links into a course-document relation"
    )

    def __init__(self, connection: sqlite3.Connection):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("connection must be an open sqlite3.Connection")
        self.connection = connection
        self._validate_schema()

    def _validate_schema(self) -> None:
        tables = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        missing = sorted(_REQUIRED_TABLES - tables)
        if missing:
            raise SQLiteCourseRepositorySchemaError(
                "Phase 3 course tables are missing: {}".format(", ".join(missing))
            )

    def _table_exists(self, table: str) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone() is not None

    def _latest_ledger_rows(self) -> Tuple[Dict[str, Any], ...]:
        rows = _fetch_dicts(
            self.connection,
            "SELECT rowid AS ledger_rowid, source_hash, source_version, "
            "legacy_key, target_table, target_id, imported_at, details_json "
            "FROM migration_imports "
            "WHERE source_path = ? AND source_type = 'legacy_json' "
            "ORDER BY imported_at, rowid",
            (COURSE_SOURCE_PATH,),
        )
        if not rows:
            return ()
        latest_hash = str(rows[-1]["source_hash"])
        result = []
        for row in rows:
            if str(row["source_hash"]) != latest_hash:
                continue
            parsed = dict(row)
            parsed["details"] = _parse_object(
                row["details_json"],
                context=str(row["legacy_key"]),
            )
            result.append(parsed)
        return tuple(result)

    @staticmethod
    def _row_kind(row: Mapping[str, Any]) -> str:
        details = row.get("details")
        if not isinstance(details, Mapping):
            return ""
        return str(details.get("kind", ""))

    def _row_by_id(self, table: str, target_id: str) -> Dict[str, Any]:
        if table not in {"courses", "topics"}:
            raise SQLiteCourseRepositoryDataError(
                "Unsupported Phase 4.1 target table: {}".format(table)
            )
        rows = _fetch_dicts(
            self.connection,
            "SELECT * FROM {} WHERE id = ?".format(table),
            (target_id,),
        )
        if not rows:
            raise SQLiteCourseRepositoryDataError(
                "Migration ledger target is missing: {}:{}".format(
                    table, target_id
                )
            )
        return rows[0]

    @staticmethod
    def _raw_from_ledger(row: Mapping[str, Any]) -> Dict[str, Any]:
        details = row.get("details")
        raw = details.get("raw", {}) if isinstance(details, Mapping) else {}
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise SQLiteCourseRepositoryDataError(
                "Raw migration evidence must be an object for {}.".format(
                    row.get("legacy_key", "")
                )
            )
        return deepcopy(raw)

    def _semantic_snapshot(self) -> Dict[str, Any]:
        ledger_rows = self._latest_ledger_rows()
        if not ledger_rows:
            return {
                "source_version": None,
                "course_catalogue": (),
                "active_course_id": None,
                "semester_mappings": (),
                "topics": (),
                "course_order": (),
                "topic_order": (),
                "course_statuses": (),
                "topic_statuses": (),
                "raw_identities": {"courses": (), "topics": ()},
                "course_aliases": (),
                "topic_aliases": (),
                "document_relationships": {},
                "document_relationships_supported": False,
                "document_relationships_reason": self.course_document_relationship_support,
                "anomalies": ("no data/courses.json migration ledger evidence",),
                "state": {
                    "version": 1,
                    "active_course_id": None,
                    "courses": [],
                    "document_links": {},
                },
            }

        source_versions = {
            str(row.get("source_version", ""))
            for row in ledger_rows
            if str(row.get("source_version", ""))
        }
        source_version: Any = 1
        if len(source_versions) == 1:
            only = next(iter(source_versions))
            source_version = int(only) if only.isdigit() else only
        elif len(source_versions) > 1:
            raise SQLiteCourseRepositoryDataError(
                "Latest courses source hash has conflicting source versions."
            )

        course_ledgers = [
            row
            for row in ledger_rows
            if row["target_table"] == "courses" and self._row_kind(row) == "course"
        ]
        topic_ledgers = [
            row
            for row in ledger_rows
            if row["target_table"] == "topics" and self._row_kind(row) == "topic"
        ]

        topics_by_course: Dict[str, List[Tuple[int, int, Dict[str, Any], Dict[str, Any]]]] = {}
        raw_topic_identities: List[Dict[str, Any]] = []
        semantic_topics: List[Dict[str, Any]] = []
        topic_statuses: List[Tuple[str, str, str]] = []
        topic_order: List[Tuple[str, Tuple[str, ...]]] = []
        anomalies: List[str] = []

        course_target_to_legacy: Dict[str, str] = {}
        course_target_to_key: Dict[str, str] = {}
        course_key_to_legacy: Dict[str, str] = {}
        used_legacy_ids = set()

        semester_target_to_label: Dict[str, str] = {}
        semester_link_target_by_course_key: Dict[str, str] = {}
        for ledger in ledger_rows:
            details = ledger.get("details")
            if not isinstance(details, Mapping):
                continue
            if (
                ledger.get("target_table") == "semesters"
                and self._row_kind(ledger) == "semester_placeholder"
            ):
                semester_target_to_label[str(ledger["target_id"])] = _raw_text(
                    details.get("legacy_semester")
                )
            elif (
                ledger.get("target_table") == "semester_courses"
                and self._row_kind(ledger) == "semester_course"
            ):
                key = str(ledger.get("legacy_key", ""))
                suffix = "/semester_course"
                if key.endswith(suffix):
                    semester_link_target_by_course_key[key[: -len(suffix)]] = str(
                        ledger["target_id"]
                    )

        prepared_courses: List[Tuple[Dict[str, Any], Dict[str, Any], str]] = []
        for ledger in course_ledgers:
            target = self._row_by_id("courses", str(ledger["target_id"]))
            raw = self._raw_from_ledger(ledger)
            details = ledger["details"]
            legacy_id = _clean_text(details.get("legacy_id")) or _clean_text(raw.get("id"))
            if not legacy_id:
                base = _slug(target.get("code") or target.get("name"))
                legacy_id = base
                suffix = 2
                while legacy_id in used_legacy_ids:
                    legacy_id = "{}-{}".format(base, suffix)
                    suffix += 1
            used_legacy_ids.add(legacy_id)
            course_target_id = str(ledger["target_id"])
            course_key = str(ledger["legacy_key"])
            course_target_to_legacy[course_target_id] = legacy_id
            course_target_to_key[course_target_id] = course_key
            course_key_to_legacy[course_key] = legacy_id
            prepared_courses.append((ledger, target, legacy_id))

        for ledger in topic_ledgers:
            target = self._row_by_id("topics", str(ledger["target_id"]))
            details = ledger["details"]
            raw = self._raw_from_ledger(ledger)
            expected_course_key = str(details.get("course_legacy_key", ""))
            expected_course_id = course_key_to_legacy.get(expected_course_key, "")
            actual_course_target_id = str(target.get("course_id", ""))
            actual_course_key = course_target_to_key.get(actual_course_target_id, "")
            actual_course_id = course_target_to_legacy.get(actual_course_target_id, "")
            if not actual_course_id:
                anomalies.append(
                    "topic {} points to SQLite course {} outside the latest courses import".format(
                        ledger["legacy_key"], actual_course_target_id
                    )
                )
            if expected_course_key != actual_course_key:
                anomalies.append(
                    "topic {} relationship differs from migration evidence: expected {} but SQLite points to {}".format(
                        ledger["legacy_key"],
                        expected_course_key or "<missing>",
                        actual_course_key or actual_course_target_id or "<missing>",
                    )
                )
            position = int(target.get("position") or 0)
            topics_by_course.setdefault(actual_course_key, []).append(
                (position, int(ledger["ledger_rowid"]), ledger, target)
            )
            topic_name = str(target.get("name") or "")
            semantic_topics.append(
                {
                    "course_id": actual_course_id,
                    "name": topic_name,
                    "status": str(target.get("status") or "not_started"),
                    "confidence": _normalised_confidence(target.get("confidence")),
                    "last_updated": raw.get("last_updated"),
                }
            )
            topic_statuses.append(
                (
                    actual_course_id,
                    topic_name,
                    str(target.get("status") or "not_started"),
                )
            )
            raw_topic_identities.append(
                {
                    "course_id": actual_course_id,
                    "expected_course_id": expected_course_id,
                    "position": position,
                    "legacy_key": str(ledger["legacy_key"]),
                    "raw_id": _raw_text(raw.get("id")),
                    "name": _raw_text(raw.get("name")),
                    "raw_status": _raw_text(raw.get("status")),
                    "raw_import_status": _raw_text(target.get("raw_import_status")),
                }
            )

        state_courses: List[Dict[str, Any]] = []
        catalogue: List[Dict[str, Any]] = []
        semester_mappings: List[Dict[str, Any]] = []
        raw_course_identities: List[Dict[str, Any]] = []
        course_statuses: List[Tuple[str, str]] = []

        for ledger, target, legacy_id in prepared_courses:
            raw = self._raw_from_ledger(ledger)
            course_key = str(ledger["legacy_key"])
            ordered_topics = sorted(
                topics_by_course.get(course_key, ()),
                key=lambda item: (item[0], item[1]),
            )
            legacy_topics = []
            names = []
            for _, _, topic_ledger, topic_target in ordered_topics:
                topic_raw = self._raw_from_ledger(topic_ledger)
                name = str(topic_target.get("name") or "")
                names.append(name)
                legacy_topics.append(
                    {
                        "name": name,
                        "status": str(topic_target.get("status") or "not_started"),
                        "confidence": _normalised_confidence(
                            topic_target.get("confidence")
                        ),
                        "last_updated": topic_raw.get("last_updated"),
                    }
                )
            topic_order.append((legacy_id, tuple(names)))

            expected_semester_label = _clean_text(raw.get("semester"))
            relation_rows = _fetch_dicts(
                self.connection,
                "SELECT sc.semester_id, sc.enrollment_status, s.name, s.academic_year "
                "FROM semester_courses AS sc "
                "JOIN semesters AS s ON s.id = sc.semester_id "
                "WHERE sc.course_id = ? ORDER BY sc.semester_id",
                (str(ledger["target_id"]),),
            )
            if len(relation_rows) != 1:
                anomalies.append(
                    "course {} has {} semester mappings; expected 1".format(
                        legacy_id, len(relation_rows)
                    )
                )
            actual_semester_label = ""
            if relation_rows:
                relation = relation_rows[0]
                actual_semester_id = str(relation["semester_id"])
                actual_semester_label = semester_target_to_label.get(
                    actual_semester_id, ""
                )
                if actual_semester_id not in semester_target_to_label:
                    anomalies.append(
                        "course {} points to semester {} without latest courses migration evidence".format(
                            legacy_id, actual_semester_id
                        )
                    )
                expected_link_target = semester_link_target_by_course_key.get(course_key)
                actual_link_target = "{}|{}".format(
                    actual_semester_id, str(ledger["target_id"])
                )
                if expected_link_target is None:
                    anomalies.append(
                        "course {} has no latest semester-course migration evidence".format(
                            legacy_id
                        )
                    )
                elif expected_link_target != actual_link_target:
                    anomalies.append(
                        "course {} semester relationship differs from migration evidence".format(
                            legacy_id
                        )
                    )
                expected_enrollment = _expected_enrollment_status(
                    str(target.get("status") or "active")
                )
                actual_enrollment = str(relation["enrollment_status"])
                if actual_enrollment != expected_enrollment:
                    anomalies.append(
                        "course {} enrollment_status is {} but {} is expected from course status".format(
                            legacy_id, actual_enrollment, expected_enrollment
                        )
                    )
                semester_mappings.append(
                    {
                        "course_id": legacy_id,
                        "semester": actual_semester_label,
                        "sqlite_semester_id": actual_semester_id,
                        "enrollment_status": actual_enrollment,
                    }
                )

            course_payload = {
                "id": legacy_id,
                "code": str(target.get("code") or ""),
                "name": str(target.get("name") or ""),
                "semester": actual_semester_label,
                "status": str(target.get("status") or "active"),
                "topics": legacy_topics,
                "created_at": raw.get("created_at", target.get("created_at")),
                "updated_at": raw.get("updated_at", target.get("updated_at")),
            }
            state_courses.append(course_payload)
            catalogue.append(
                {
                    "id": legacy_id,
                    "code": course_payload["code"],
                    "name": course_payload["name"],
                    "status": course_payload["status"],
                }
            )
            course_statuses.append((legacy_id, course_payload["status"]))
            raw_course_identities.append(
                {
                    "position": len(raw_course_identities),
                    "legacy_key": course_key,
                    "raw_id": _raw_text(raw.get("id")),
                    "legacy_id": legacy_id,
                    "code": _raw_text(raw.get("code")),
                    "raw_status": _raw_text(raw.get("status")),
                }
            )

        active_target = None
        setting = self.connection.execute(
            "SELECT value_json FROM app_settings WHERE key = 'active_course_id'"
        ).fetchone()
        if setting is not None:
            try:
                active_target = str(json.loads(str(setting[0])))
            except (TypeError, ValueError, json.JSONDecodeError) as error:
                raise SQLiteCourseRepositoryDataError(
                    "app_settings.active_course_id is not valid JSON."
                ) from error
        active_legacy = (
            course_target_to_legacy.get(active_target) if active_target else None
        )
        if active_legacy is None and state_courses:
            active_legacy = state_courses[0]["id"]

        course_aliases: Tuple[Dict[str, Any], ...] = ()
        if self._table_exists("course_aliases"):
            alias_rows = _fetch_dicts(
                self.connection,
                "SELECT course_id, alias, normalized_alias, provider, source "
                "FROM course_aliases ORDER BY course_id, provider, normalized_alias, id",
            )
            course_aliases = tuple(
                {
                    "course_id": course_target_to_legacy.get(
                        str(row["course_id"]), str(row["course_id"])
                    ),
                    "alias": str(row["alias"]),
                    "normalized_alias": str(row["normalized_alias"]),
                    "provider": str(row["provider"]),
                    "source": str(row["source"]),
                }
                for row in alias_rows
            )

        topic_target_to_identity = {
            str(row["target_id"]): (
                raw_topic_identities[index]["course_id"],
                raw_topic_identities[index]["name"],
            )
            for index, row in enumerate(topic_ledgers)
            if index < len(raw_topic_identities)
        }
        topic_aliases: Tuple[Dict[str, Any], ...] = ()
        if self._table_exists("topic_aliases"):
            alias_rows = _fetch_dicts(
                self.connection,
                "SELECT topic_id, course_id, alias, normalized_alias, source "
                "FROM topic_aliases ORDER BY course_id, normalized_alias, id",
            )
            topic_aliases = tuple(
                {
                    "course_id": course_target_to_legacy.get(
                        str(row["course_id"]), str(row["course_id"])
                    ),
                    "topic": topic_target_to_identity.get(
                        str(row["topic_id"]), ("", str(row["topic_id"]))
                    )[1],
                    "alias": str(row["alias"]),
                    "normalized_alias": str(row["normalized_alias"]),
                    "source": str(row["source"]),
                }
                for row in alias_rows
            )

        latest_course_targets = {str(row["target_id"]) for row in course_ledgers}
        latest_topic_targets = {str(row["target_id"]) for row in topic_ledgers}
        historical_course_targets = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT DISTINCT target_id FROM migration_imports "
                "WHERE source_path = ? AND source_type = 'legacy_json' "
                "AND target_table = 'courses'",
                (COURSE_SOURCE_PATH,),
            ).fetchall()
        }
        historical_topic_targets = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT DISTINCT target_id FROM migration_imports "
                "WHERE source_path = ? AND source_type = 'legacy_json' "
                "AND target_table = 'topics'",
                (COURSE_SOURCE_PATH,),
            ).fetchall()
        }
        stale_courses = tuple(
            sorted(
                target_id
                for target_id in historical_course_targets - latest_course_targets
                if self.connection.execute(
                    "SELECT 1 FROM courses WHERE id = ? AND deleted_at IS NULL",
                    (target_id,),
                ).fetchone()
                is not None
            )
        )
        stale_topics = tuple(
            sorted(
                target_id
                for target_id in historical_topic_targets - latest_topic_targets
                if self.connection.execute(
                    "SELECT 1 FROM topics WHERE id = ? AND deleted_at IS NULL",
                    (target_id,),
                ).fetchone()
                is not None
            )
        )
        if stale_courses:
            anomalies.append(
                "live course rows remain from older data/courses.json imports: {}".format(
                    ", ".join(stale_courses)
                )
            )
        if stale_topics:
            anomalies.append(
                "live topic rows remain from older data/courses.json imports: {}".format(
                    ", ".join(stale_topics)
                )
            )
        if active_target and active_target not in course_target_to_legacy:
            anomalies.append(
                "active_course_id setting points outside the latest courses import: {}".format(
                    active_target
                )
            )

        state = {
            "version": source_version if source_version is not None else 1,
            "active_course_id": active_legacy,
            "courses": state_courses,
            "document_links": {},
        }
        return {
            "source_version": source_version,
            "course_catalogue": tuple(catalogue),
            "active_course_id": active_legacy,
            "semester_mappings": tuple(semester_mappings),
            "topics": tuple(semantic_topics),
            "course_order": tuple(item["id"] for item in catalogue),
            "topic_order": tuple(topic_order),
            "course_statuses": tuple(course_statuses),
            "topic_statuses": tuple(topic_statuses),
            "raw_identities": {
                "courses": tuple(raw_course_identities),
                "topics": tuple(raw_topic_identities),
            },
            "course_aliases": course_aliases,
            "topic_aliases": topic_aliases,
            "document_relationships": {},
            "document_relationships_supported": False,
            "document_relationships_reason": self.course_document_relationship_support,
            "anomalies": tuple(anomalies),
            "state": state,
        }

    def parity_snapshot(self) -> Dict[str, Any]:
        """Return structured SQLite evidence used by dual-read comparison."""
        before = self.connection.total_changes
        snapshot = self._semantic_snapshot()
        if self.connection.total_changes != before:
            raise SQLiteCourseRepositoryDataError(
                "SQLite course read unexpectedly changed database state."
            )
        return deepcopy(snapshot)

    def load_state(self) -> CourseState:
        """Return a legacy-shaped semantic view without mutating SQLite."""
        return deepcopy(self.parity_snapshot()["state"])

    def get_document_link(self, document_key: str):
        """Phase 3 did not import legacy course document links."""
        return None

    def list_document_links(self):
        """Phase 3 did not import legacy course document links."""
        return {}

    def integrity_checks(self) -> Dict[str, Any]:
        """Run read-only integrity/FK checks for gates and diagnostics."""
        before = self.connection.total_changes
        integrity = tuple(
            str(row[0])
            for row in self.connection.execute("PRAGMA integrity_check").fetchall()
        )
        foreign_keys = tuple(
            tuple(row)
            for row in self.connection.execute("PRAGMA foreign_key_check").fetchall()
        )
        if self.connection.total_changes != before:
            raise SQLiteCourseRepositoryDataError(
                "SQLite integrity checks unexpectedly changed database state."
            )
        return {
            "integrity_check": integrity,
            "foreign_key_check": foreign_keys,
            "pass": integrity == ("ok",) and not foreign_keys,
        }

    def save_state(self, state: CourseState) -> CourseState:
        raise SQLiteCourseRepositoryReadOnlyError(
            "Phase 4.1 SQLite course repository is read-only; legacy JSON remains authoritative."
        )

    def upsert_document_link(self, document_key: str, link):
        raise SQLiteCourseRepositoryReadOnlyError(
            "Phase 4.1 SQLite course repository cannot write document links."
        )

    def delete_document_link(self, document_key: str) -> bool:
        raise SQLiteCourseRepositoryReadOnlyError(
            "Phase 4.1 SQLite course repository cannot delete document links."
        )


__all__ = (
    "COURSE_SOURCE_PATH",
    "SQLiteCourseRepository",
    "SQLiteCourseRepositoryDataError",
    "SQLiteCourseRepositoryError",
    "SQLiteCourseRepositoryReadOnlyError",
    "SQLiteCourseRepositorySchemaError",
)
