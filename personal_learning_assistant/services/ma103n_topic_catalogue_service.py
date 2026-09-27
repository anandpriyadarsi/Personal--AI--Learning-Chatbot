"""Deterministic MA103N canonical-topic catalogue reconciliation.

This maintenance service expands the authoritative MA103N Linear Algebra topic
catalogue to the user's confirmed current syllabus (Weeks 1-6). It preserves
existing topic progress/status, appends only genuinely missing canonical topics,
and adds SQLite-only aliases that improve Assessment Studio topic matching.

Run explicitly after pulling the branch:

    python -m personal_learning_assistant.services.ma103n_topic_catalogue_service

The command is intentionally explicit rather than an application-startup side
effect so a running test session is never mutated underneath the student.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional, Tuple
from urllib.parse import quote

from personal_learning_assistant.domain import course_normalization
from personal_learning_assistant.migration.legacy_json_import import stable_target_id
from personal_learning_assistant.repositories.routed_course_repository import (
    RoutedCourseRepository,
)
from personal_learning_assistant.repositories.structured_authority_router import (
    BACKEND_SQLITE,
    current_structured_backend,
    database_path_for_store,
)


COURSE_CODE = "MA103N"
ALIAS_SOURCE = "ma103n_current_syllabus"


# Keep these names stable once published: assessment packages and learning
# evidence use them as the canonical MA103N taxonomy.
MA103N_CANONICAL_TOPICS: Tuple[Mapping[str, object], ...] = (
    {
        "name": "System of Linear Equations",
        "aliases": ("Systems of Linear Equations", "Linear Systems"),
    },
    {
        "name": "Elementary Row Operations",
        "aliases": ("Row Operations", "Elementary Row Operation"),
    },
    {
        "name": "Echelon Form",
        "aliases": ("Row Echelon Form", "REF"),
    },
    {
        "name": "RREF",
        "aliases": ("Reduced Row Echelon Form", "Reduced Echelon Form"),
    },
    {
        "name": "Rank of Matrix",
        "aliases": ("Matrix Rank", "Rank"),
    },
    {
        "name": "Rouche-Capelli Theorem",
        "aliases": (
            "Rouché-Capelli Theorem",
            "Rouché–Capelli Theorem",
            "Rouche Capelli Theorem",
        ),
    },
    {
        "name": "Consistency of Linear Systems",
        "aliases": (
            "Consistency and Inconsistency",
            "Consistency/Inconsistency",
            "Consistency of Linear Equations",
        ),
    },
    {
        "name": "Solution Classification",
        "aliases": (
            "Unique Infinite and No Solution",
            "Unique/Infinite/No Solution",
            "Unique Solution Infinite Solutions No Solution",
        ),
    },
    {
        "name": "Gauss Elimination",
        "aliases": ("Gaussian Elimination",),
    },
    {
        "name": "Gauss-Jordan Method",
        "aliases": ("Gauss Jordan Method", "Gauss-Jordan Elimination"),
    },
    {
        "name": "Inverse using Gauss-Jordan",
        "aliases": (
            "Matrix Inverse using Gauss-Jordan",
            "Matrix Inverses using Elimination",
            "Inverse by Elimination",
        ),
    },
    {
        "name": "LU Factorisation",
        "aliases": ("LU Factorization", "LU Decomposition", "LU-factorization"),
    },
    {
        "name": "Determinants",
        "aliases": ("Determinant",),
    },
    {
        "name": "Vector Spaces",
        "aliases": ("Vector Space",),
    },
    {
        "name": "Vector Space Axioms",
        "aliases": ("Axioms of Vector Spaces",),
    },
    {
        "name": "Vector Space Examples and Standard Spaces",
        "aliases": ("Standard Vector Spaces", "Examples of Vector Spaces"),
    },
    {
        "name": "Basic Structural Properties of Vector Spaces",
        "aliases": (
            "Structural Properties of Vector Spaces",
            "Basic Structural Properties",
        ),
    },
    {
        "name": "Subspaces",
        "aliases": ("Subspace",),
    },
    {
        "name": "Linear Independence",
        "aliases": (
            "Linear Dependence and Independence",
            "Linear Independence Test",
        ),
    },
    {
        "name": "Bases",
        "aliases": ("Basis", "Bases and Dimension"),
    },
    {
        "name": "Dimension",
        "aliases": ("Dimensions", "Dimension of a Vector Space"),
    },
    {
        "name": "Span",
        "aliases": ("Spanning Sets",),
    },
    {
        "name": "Basis Theorems",
        "aliases": ("Fundamental Results on Bases", "Basis Results"),
    },
    {
        "name": "Coordinate Representations",
        "aliases": (
            "Coordinate Representation",
            "Coordinates Relative to a Basis",
            "Bases and Coordinate Representations",
        ),
    },
    {
        "name": "Dimension Theorems",
        "aliases": ("Dimension-related Theorems", "Dimension Related Theorems"),
    },
    {
        "name": "Inner Products in R^n",
        "aliases": ("Inner Product in R^n", "Inner Products"),
    },
    {
        "name": "Orthogonal and Orthonormal Sets",
        "aliases": ("Orthogonal Sets", "Orthonormal Sets"),
    },
    {
        "name": "Orthogonal Matrices",
        "aliases": ("Orthogonal Matrix",),
    },
    {
        "name": "Gram-Schmidt Process",
        "aliases": ("Gram Schmidt", "Gram-Schmidt"),
    },
    {
        "name": "Orthonormal Bases",
        "aliases": ("Orthonormal Basis",),
    },
    {
        "name": "Orthogonal Complements",
        "aliases": ("Orthogonal Complement",),
    },
    {
        "name": "QR Factorisation",
        "aliases": ("QR Factorization", "QR Decomposition"),
    },
    {
        "name": "Least Squares",
        "aliases": ("Least Squares Problems", "Least-squares"),
    },
    {
        "name": "Best Approximation",
        "aliases": ("Best Approximation Theorem",),
    },
)


@dataclass(frozen=True)
class MA103NCatalogueResult:
    course_code: str
    added_topics: Tuple[str, ...]
    total_topics: int
    aliases_added: int
    alias_backend: str

    def to_dict(self):
        return {
            "course_code": self.course_code,
            "added_topics": list(self.added_topics),
            "added_topic_count": len(self.added_topics),
            "total_topics": self.total_topics,
            "aliases_added": self.aliases_added,
            "alias_backend": self.alias_backend,
        }


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _canonical_names() -> Tuple[str, ...]:
    return tuple(str(item["name"]) for item in MA103N_CANONICAL_TOPICS)


def _aliases_for(name: str) -> Tuple[str, ...]:
    wanted = str(name).casefold()
    for item in MA103N_CANONICAL_TOPICS:
        if str(item["name"]).casefold() == wanted:
            return tuple(str(alias) for alias in item.get("aliases", ()))
    return ()


class MA103NTopicCatalogueService:
    def __init__(
        self,
        course_path: Optional[Path] = None,
        *,
        now: Optional[Callable[[], str]] = None,
    ) -> None:
        self.repository = RoutedCourseRepository(path=course_path)
        self._now = now or _now

    def reconcile(self) -> MA103NCatalogueResult:
        state = self.repository.load_state()
        courses = list(state.get("courses") or ())
        course = next(
            (
                item
                for item in courses
                if str(item.get("code") or "").strip().casefold()
                == COURSE_CODE.casefold()
            ),
            None,
        )
        if course is None:
            raise ValueError(
                "{} is not present in the current course catalogue.".format(COURSE_CODE)
            )

        timestamp = self._now()
        topics = list(course.get("topics") or ())
        existing = {
            str(item.get("name") or "").strip().casefold(): item
            for item in topics
            if str(item.get("name") or "").strip()
        }

        added = []
        for name in _canonical_names():
            key = name.casefold()
            if key in existing:
                continue
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
            self.repository.save_state(state)

        backend = current_structured_backend(self.repository.path)
        aliases_added = 0
        if backend == BACKEND_SQLITE:
            aliases_added = self._sync_sqlite_aliases()

        # Re-read after the write so the result reflects the authority actually
        # persisted by the routed repository.
        saved = self.repository.load_state()
        saved_course = next(
            item
            for item in saved.get("courses") or ()
            if str(item.get("code") or "").strip().casefold()
            == COURSE_CODE.casefold()
        )
        return MA103NCatalogueResult(
            course_code=COURSE_CODE,
            added_topics=tuple(added),
            total_topics=len(saved_course.get("topics") or ()),
            aliases_added=aliases_added,
            alias_backend=backend,
        )

    def _sync_sqlite_aliases(self) -> int:
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

        added = 0
        try:
            course_rows = connection.execute(
                "SELECT id FROM courses "
                "WHERE code=? COLLATE NOCASE AND deleted_at IS NULL",
                (COURSE_CODE,),
            ).fetchall()
            if len(course_rows) != 1:
                raise RuntimeError(
                    "Expected exactly one active {} row in SQLite.".format(COURSE_CODE)
                )
            course_id = str(course_rows[0]["id"])

            topic_rows = connection.execute(
                "SELECT id, name, normalized_name FROM topics "
                "WHERE course_id=? AND deleted_at IS NULL",
                (course_id,),
            ).fetchall()
            topics = {
                str(row["name"]).strip().casefold(): dict(row)
                for row in topic_rows
            }

            connection.execute("BEGIN IMMEDIATE")
            try:
                for canonical in MA103N_CANONICAL_TOPICS:
                    name = str(canonical["name"])
                    topic = topics.get(name.casefold())
                    if topic is None:
                        raise RuntimeError(
                            "Canonical topic {!r} was not persisted before alias sync."
                            .format(name)
                        )
                    topic_id = str(topic["id"])
                    for alias in _aliases_for(name):
                        normalized = alias.strip().casefold()
                        if not normalized or normalized == name.casefold():
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
                                    .format(alias, COURSE_CODE)
                                )
                            continue
                        alias_id = stable_target_id(
                            "runtime/ma103n_topic_catalogue",
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
                        added += 1
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()
        finally:
            connection.close()

        return added


def main() -> int:
    result = MA103NTopicCatalogueService().reconcile()
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
