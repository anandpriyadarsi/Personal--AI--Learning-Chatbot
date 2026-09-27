from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from personal_learning_assistant.migration.authority_promotion import (
    AuthorityControlState,
    write_authority_control_atomic,
)
from personal_learning_assistant.repositories.sqlite.assessment_import_repository import (
    SQLiteAssessmentImportRepository,
)
from personal_learning_assistant.repositories.sqlite.compatibility_repository import (
    SQLiteCompatibilityProjectionRepository,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import (
    apply_migrations,
)
from personal_learning_assistant.services.assessment_package_service import _best_topic
from personal_learning_assistant.services.ma103n_topic_catalogue_service import (
    MA103N_CANONICAL_TOPICS,
    MA103NTopicCatalogueService,
)


NOW = "2026-09-27T18:30:00"


EXISTING_TOPICS = [
    "System of Linear Equations",
    "Echelon Form",
    "RREF",
    "Rank of Matrix",
    "Rouche-Capelli Theorem",
    "Gauss Elimination",
    "Gauss-Jordan Method",
    "Inverse using Gauss-Jordan",
    "LU Factorisation",
]


def _payload():
    topics = []
    for name in EXISTING_TOPICS:
        topics.append(
            {
                "name": name,
                "status": "learning" if name == "LU Factorisation" else "not_started",
                "confidence": 3 if name == "LU Factorisation" else 0,
                "last_updated": NOW,
            }
        )
    return {
        "version": 1,
        "active_course_id": "ma103n",
        "courses": [
            {
                "id": "ma103n",
                "code": "MA103N",
                "name": "Linear Algebra",
                "semester": "Semester 1",
                "status": "active",
                "topics": topics,
                "created_at": NOW,
                "updated_at": NOW,
            }
        ],
        "document_links": {},
    }


def _sqlite_project(tmp_path: Path):
    root = tmp_path / "project"
    data = root / "data"
    data.mkdir(parents=True)
    course_path = data / "courses.json"
    course_path.write_text(
        json.dumps(_payload(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    database_path = data / "learning_assistant.db"
    assert apply_migrations(database_path) == tuple(range(1, 15))

    control_path = root / ".phase4_authority.json"
    state = AuthorityControlState(
        storage_backend="sqlite",
        cutover_id="ma103n-catalogue-test",
        source_manifest_hash="a" * 64,
        sqlite_sha256="b" * 64,
        promoted_at="2026-09-27T18:00:00Z",
        legacy_writes_blocked=True,
    )
    write_authority_control_atomic(control_path, state)

    connection = sqlite3.connect(database_path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        repository = SQLiteCompatibilityProjectionRepository(
            connection,
            authority_control_path=control_path,
        )
        repository.save_projection("courses", _payload())
    finally:
        connection.close()

    return root, course_path, database_path


def test_catalogue_matches_confirmed_ma103n_current_syllabus():
    names = [str(item["name"]) for item in MA103N_CANONICAL_TOPICS]

    assert len(names) == len(set(name.casefold() for name in names))
    assert set(
        [
            "System of Linear Equations",
            "Elementary Row Operations",
            "Echelon Form",
            "RREF",
            "Rank of Matrix",
            "Rouche-Capelli Theorem",
            "Consistency of Linear Systems",
            "Solution Classification",
            "Gauss Elimination",
            "Gauss-Jordan Method",
            "Inverse using Gauss-Jordan",
            "LU Factorisation",
            "Determinants",
            "Vector Spaces",
            "Vector Space Axioms",
            "Vector Space Examples and Standard Spaces",
            "Basic Structural Properties of Vector Spaces",
            "Subspaces",
            "Linear Independence",
            "Bases",
            "Dimension",
            "Span",
            "Basis Theorems",
            "Coordinate Representations",
            "Dimension Theorems",
            "Inner Products in R^n",
            "Orthogonal and Orthonormal Sets",
            "Orthogonal Matrices",
            "Gram-Schmidt Process",
            "Orthonormal Bases",
            "Orthogonal Complements",
            "QR Factorisation",
            "Least Squares",
            "Best Approximation",
        ]
    ) == set(names)


def test_reconcile_expands_sqlite_authority_without_resetting_progress(tmp_path):
    _, course_path, database_path = _sqlite_project(tmp_path)

    result = MA103NTopicCatalogueService(
        course_path=course_path,
        now=lambda: NOW,
    ).reconcile()

    assert result.total_topics == len(MA103N_CANONICAL_TOPICS)
    assert set(result.added_topics).isdisjoint(EXISTING_TOPICS)
    assert "Determinants" in result.added_topics
    assert "Coordinate Representations" in result.added_topics
    assert "Orthogonal Complements" in result.added_topics
    assert result.aliases_added > 0
    assert result.alias_backend == "sqlite"

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        course = connection.execute(
            "SELECT id FROM courses WHERE code='MA103N' COLLATE NOCASE "
            "AND deleted_at IS NULL"
        ).fetchone()
        rows = connection.execute(
            "SELECT name, status, confidence, position FROM topics "
            "WHERE course_id=? AND deleted_at IS NULL ORDER BY position",
            (course["id"],),
        ).fetchall()
        names = [str(row["name"]) for row in rows]
        assert names[: len(EXISTING_TOPICS)] == EXISTING_TOPICS
        assert len(names) == len(MA103N_CANONICAL_TOPICS)

        lu = next(row for row in rows if row["name"] == "LU Factorisation")
        assert lu["status"] == "learning"
        assert lu["confidence"] == 3
    finally:
        connection.close()


def test_reconcile_is_idempotent_and_adds_no_duplicate_aliases(tmp_path):
    _, course_path, database_path = _sqlite_project(tmp_path)
    service = MA103NTopicCatalogueService(
        course_path=course_path,
        now=lambda: NOW,
    )

    first = service.reconcile()
    second = service.reconcile()

    assert first.added_topics
    assert second.added_topics == ()
    assert second.aliases_added == 0
    assert second.total_topics == len(MA103N_CANONICAL_TOPICS)

    connection = sqlite3.connect(database_path)
    try:
        duplicates = connection.execute(
            "SELECT course_id, normalized_alias, COUNT(*) "
            "FROM topic_aliases GROUP BY course_id, normalized_alias "
            "HAVING COUNT(*) > 1"
        ).fetchall()
        assert duplicates == []
    finally:
        connection.close()


def test_expanded_catalogue_resolves_all_topic_labels_that_blocked_quiz_review(tmp_path):
    _, course_path, database_path = _sqlite_project(tmp_path)
    MA103NTopicCatalogueService(
        course_path=course_path,
        now=lambda: NOW,
    ).reconcile()

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        course_id = connection.execute(
            "SELECT id FROM courses WHERE code='MA103N' COLLATE NOCASE "
            "AND deleted_at IS NULL"
        ).fetchone()["id"]
        catalogue = SQLiteAssessmentImportRepository(connection).topic_catalogue(
            str(course_id)
        )

        labels = [
            "Determinants",
            "Coordinate Representations",
            "Span",
            "Dimension Theorems",
            "Vector Space Axioms",
            "Bases and Coordinate Representations",
            "Subspaces",
            "Bases and Dimension",
        ]
        for label in labels:
            topic_id, score = _best_topic(label, catalogue)
            assert topic_id is not None, label
            assert score >= 0.98, (label, score)
    finally:
        connection.close()
