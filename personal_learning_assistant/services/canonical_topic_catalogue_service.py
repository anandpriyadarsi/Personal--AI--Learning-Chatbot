"""Explicit reconciliation of source-backed Semester-1 canonical topics.

Assessment Studio can only verify imported academic_map.topic values when the
selected ANVAYA course already has a canonical topic catalogue. This service
adds missing source-backed topics without resetting existing progress and, when
SQLite is authoritative, adds stable aliases used by Assessment Studio.

Nothing runs at application startup. Execute explicitly:

    python -m personal_learning_assistant.services.canonical_topic_catalogue_service

Optionally reconcile one or more courses:

    python -m personal_learning_assistant.services.canonical_topic_catalogue_service UC103N MA103N
"""

from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional, Tuple
from urllib.parse import quote

from personal_learning_assistant.domain import course_normalization
from personal_learning_assistant.domain.canonical_topic_catalogues import (
    CANONICAL_TOPIC_CATALOGUES,
    COURSE_CATALOGUE_METADATA,
    aliases_for,
    canonical_names,
)
from personal_learning_assistant.migration.authority_promotion import BACKEND_SQLITE
from personal_learning_assistant.migration.legacy_json_import import stable_target_id
from personal_learning_assistant.repositories.routed_course_repository import (
    RoutedCourseRepository,
)
from personal_learning_assistant.repositories.structured_authority_router import (
    current_structured_backend,
    database_path_for_store,
)


ALIAS_SOURCE = "semester1_canonical_topic_catalogue_v1"


@dataclass(frozen=True)
class CourseCatalogueResult:
    course_code: str
    present: bool
    added_topics: Tuple[str, ...]
    total_topics: int
    aliases_added: int
    coverage: str

    def to_dict(self):
        return {
            "course_code": self.course_code,
            "present": self.present,
            "added_topics": list(self.added_topics),
            "added_topic_count": len(self.added_topics),
            "total_topics": self.total_topics,
            "aliases_added": self.aliases_added,
            "coverage": self.coverage,
        }


@dataclass(frozen=True)
class CanonicalCatalogueResult:
    backend: str
    courses: Tuple[CourseCatalogueResult, ...]

    @property
    def missing_courses(self) -> Tuple[str, ...]:
        return tuple(item.course_code for item in self.courses if not item.present)

    @property
    def added_topic_count(self) -> int:
        return sum(len(item.added_topics) for item in self.courses)

    @property
    def aliases_added(self) -> int:
        return sum(item.aliases_added for item in self.courses)

    def to_dict(self):
        return {
            "backend": self.backend,
            "course_count": len(self.courses),
            "added_topic_count": self.added_topic_count,
            "aliases_added": self.aliases_added,
            "missing_courses": list(self.missing_courses),
            "courses": [item.to_dict() for item in self.courses],
        }


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _normal(value: object) -> str:
    return " ".join(str(value or "").strip().split()).casefold()


def _requested_codes(course_codes: Optional[Iterable[str]]) -> Tuple[str, ...]:
    if course_codes is None:
        return tuple(CANONICAL_TOPIC_CATALOGUES)
    result = []
    seen = set()
    for value in course_codes:
        code = str(value or "").strip().upper()
        if not code or code in seen:
            continue
        if code not in CANONICAL_TOPIC_CATALOGUES:
            raise ValueError(
                "No source-backed canonical topic catalogue is defined for {}."
                .format(code)
            )
        seen.add(code)
        result.append(code)
    if not result:
        raise ValueError("Choose at least one supported course code.")
    return tuple(result)


class CanonicalTopicCatalogueService:
    def __init__(
        self,
        course_path: Optional[Path] = None,
        *,
        now: Optional[Callable[[], str]] = None,
    ) -> None:
        self.repository = RoutedCourseRepository(path=course_path)
        self._now = now or _now

    def reconcile(
        self,
        course_codes: Optional[Iterable[str]] = None,
    ) -> CanonicalCatalogueResult:
        codes = _requested_codes(course_codes)
        state = self.repository.load_state()
        courses = list(state.get("courses") or ())
        by_code = {
            str(item.get("code") or "").strip().upper(): item
            for item in courses
            if str(item.get("code") or "").strip()
        }
        timestamp = self._now()
        added_by_code = {}
        changed = False

        for code in codes:
            course = by_code.get(code)
            if course is None:
                added_by_code[code] = ()
                continue
            topics = list(course.get("topics") or ())
            existing = {
                _normal(item.get("name")): item
                for item in topics
                if _normal(item.get("name"))
            }
            added = []
            for name in canonical_names(code):
                candidate_keys = (_normal(name),) + tuple(
                    _normal(alias) for alias in aliases_for(code, name)
                )
                if any(key in existing for key in candidate_keys if key):
                    # Preserve a pre-existing legacy spelling as the student's
                    # persisted topic identity rather than creating a semantic
                    # duplicate. SQLite alias sync attaches the published
                    # canonical spelling to that topic.
                    continue
                key = _normal(name)
                topic = course_normalization._normalise_topic(
                    {
                        "name": name,
                        "status": "not_started",
                        "confidence": 0,
                        "last_updated": timestamp,
                    }
                )
                topics.append(topic)
                existing[key] = topic
                added.append(name)
            if added:
                course["topics"] = topics
                course["updated_at"] = timestamp
                changed = True
            added_by_code[code] = tuple(added)

        if changed:
            self.repository.save_state(state)

        backend = current_structured_backend(self.repository.path)
        aliases_by_code = {code: 0 for code in codes}
        if backend == BACKEND_SQLITE:
            aliases_by_code = self._sync_sqlite_aliases(codes)

        saved = self.repository.load_state()
        saved_by_code = {
            str(item.get("code") or "").strip().upper(): item
            for item in saved.get("courses") or ()
            if str(item.get("code") or "").strip()
        }
        results = []
        for code in codes:
            course = saved_by_code.get(code)
            metadata = COURSE_CATALOGUE_METADATA[code]
            results.append(
                CourseCatalogueResult(
                    course_code=code,
                    present=course is not None,
                    added_topics=tuple(added_by_code.get(code, ())),
                    total_topics=len(course.get("topics") or ()) if course else 0,
                    aliases_added=int(aliases_by_code.get(code, 0)),
                    coverage=str(metadata["coverage"]),
                )
            )
        return CanonicalCatalogueResult(backend=backend, courses=tuple(results))

    def _sync_sqlite_aliases(self, codes: Iterable[str]):
        database_path = database_path_for_store(self.repository.path)
        if (
            not database_path.exists()
            or not database_path.is_file()
            or database_path.is_symlink()
        ):
            raise RuntimeError(
                "SQLite authority is active but the project database is unavailable."
            )

        uri = "file:{}?mode=rw".format(
            quote(database_path.resolve().as_posix(), safe="/:")
        )
        connection = sqlite3.connect(uri, uri=True, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        added_by_code = {code: 0 for code in codes}
        try:
            connection.execute("BEGIN IMMEDIATE")
            try:
                for code in codes:
                    course_rows = connection.execute(
                        "SELECT id FROM courses "
                        "WHERE code=? COLLATE NOCASE AND deleted_at IS NULL",
                        (code,),
                    ).fetchall()
                    if not course_rows:
                        continue
                    if len(course_rows) != 1:
                        raise RuntimeError(
                            "Expected exactly one active {} row in SQLite."
                            .format(code)
                        )
                    course_id = str(course_rows[0]["id"])
                    topic_rows = connection.execute(
                        "SELECT id, name FROM topics "
                        "WHERE course_id=? AND deleted_at IS NULL",
                        (course_id,),
                    ).fetchall()
                    topics = {
                        _normal(row["name"]): dict(row)
                        for row in topic_rows
                    }
                    for canonical_name in canonical_names(code):
                        candidate_names = (canonical_name,) + aliases_for(
                            code, canonical_name
                        )
                        candidate_rows = {
                            str(topics[key]["id"]): topics[key]
                            for key in (_normal(value) for value in candidate_names)
                            if key in topics
                        }
                        exact = topics.get(_normal(canonical_name))
                        if exact is not None:
                            topic = exact
                        elif len(candidate_rows) == 1:
                            topic = next(iter(candidate_rows.values()))
                        elif not candidate_rows:
                            raise RuntimeError(
                                "Canonical topic {!r} was not persisted for {} before alias sync."
                                .format(canonical_name, code)
                            )
                        else:
                            raise RuntimeError(
                                "Multiple existing {} topics match canonical topic {!r}; "
                                "manual reconciliation is required."
                                .format(code, canonical_name)
                            )
                        topic_id = str(topic["id"])
                        target_name = str(topic["name"])
                        for alias in (canonical_name,) + aliases_for(code, canonical_name):
                            normalized = _normal(alias)
                            if not normalized or normalized == _normal(target_name):
                                continue
                            existing = connection.execute(
                                "SELECT topic_id FROM topic_aliases "
                                "WHERE course_id=? AND normalized_alias=?",
                                (course_id, normalized),
                            ).fetchone()
                            if existing is not None:
                                if str(existing["topic_id"]) != topic_id:
                                    raise RuntimeError(
                                        "Alias {!r} already belongs to another {} topic."
                                        .format(alias, code)
                                    )
                                continue
                            alias_id = stable_target_id(
                                "runtime/canonical_topic_catalogue_v1",
                                "topic_alias",
                                "{}:{}".format(topic_id, normalized),
                            )
                            connection.execute(
                                "INSERT INTO topic_aliases "
                                "(id, topic_id, course_id, alias, normalized_alias, source, created_at) "
                                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                                (
                                    alias_id,
                                    topic_id,
                                    course_id,
                                    alias,
                                    normalized,
                                    ALIAS_SOURCE,
                                    self._now(),
                                ),
                            )
                            added_by_code[code] += 1
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()
        finally:
            connection.close()
        return added_by_code


def main(argv=None) -> int:
    args = tuple(sys.argv[1:] if argv is None else argv)
    result = CanonicalTopicCatalogueService().reconcile(args or None)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
