from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from personal_learning_assistant.ingestion.chunking import decode_chunk_type
from personal_learning_assistant.ingestion.external_course_package import (
    ExternalCoursePackageError,
    MIT1806PackageReader,
)
from personal_learning_assistant.repositories.sqlite.external_course_knowledge_repository import (
    SQLiteExternalCourseKnowledgeRepository,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
from personal_learning_assistant.services.external_course_knowledge_service import (
    ExternalCourseKnowledgeService,
)


NOW = "2026-09-16T15:00:00Z"


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _package(tmp_path: Path):
    root = tmp_path / "Chatbot Knowledge"
    root.mkdir()
    inventory = [
        {
            "lecture_number": "01",
            "lecture_title": "Geometry",
            "official_lecture_url": "https://ocw.mit.edu/courses/18-06/resources/l1/",
            "official_sc_session_url": "https://ocw.mit.edu/sc/l1/",
            "official_summary_url": "https://ocw.mit.edu/sc/l1sum/",
            "official_session_problems_url": "https://ocw.mit.edu/sc/l1prob/",
            "official_session_solutions_url": "https://ocw.mit.edu/sc/l1sol/",
            "major_concepts": ["Systems of Linear Equations", "Column Space"],
            "prerequisites": ["Vectors"],
            "reading": "1.1",
            "spring_2010_problem_sets": ["Problem Set 1"],
            "exam_scope": "Exam 1",
            "spring_2010_calendar_alignment": "S1",
            "nitk_weeks": ["Week 1"],
            "nitk_alignment": "Direct foundation.",
            "priority": "CORE",
        },
        {
            "lecture_number": "04",
            "lecture_title": "Factorization into A = LU",
            "official_lecture_url": "https://ocw.mit.edu/courses/18-06/resources/l4/",
            "official_sc_session_url": "https://ocw.mit.edu/sc/l4/",
            "official_summary_url": "https://ocw.mit.edu/sc/l4sum/",
            "official_session_problems_url": "https://ocw.mit.edu/sc/l4prob/",
            "official_session_solutions_url": "https://ocw.mit.edu/sc/l4sol/",
            "major_concepts": ["LU Factorization", "Gaussian Elimination"],
            "prerequisites": ["Gaussian Elimination"],
            "reading": "2.6",
            "spring_2010_problem_sets": ["Problem Set 2"],
            "exam_scope": "Exam 1",
            "spring_2010_calendar_alignment": "S4",
            "nitk_weeks": ["Week 2"],
            "nitk_alignment": "Direct LU match.",
            "priority": "CORE",
        },
    ]
    base = {
        "course": "MIT 18.06 Linear Algebra",
        "course_id": "mit-18.06-linear-algebra",
        "instructor": "Prof. Gilbert Strang",
        "prerequisites": [],
        "related_concepts": [],
        "nitk_weeks": ["Week 1"],
        "priority": "CORE",
        "supporting_source_urls": ["https://ocw.mit.edu/support/"],
        "retrieval_queries": ["explain"],
        "answer_modes": ["intuition_first"],
        "content_version": "2.0",
    }
    chunk_rows = []
    specs = [
        ("mit-L01-a", "01", "Geometry", "Systems of Linear Equations",
         ["Systems of Linear Equations", "Column Space"], "lecture_mathematics"),
        ("mit-L04-a", "04", "Factorization into A = LU", "LU Factorization",
         ["LU Factorization", "Gaussian Elimination"], "lecture_mathematics"),
        ("mit-concept-lu", None, None, "LU Factorization",
         ["LU Factorization"], "concept_definition_structure"),
    ]
    for chunk_id, number, title, topic, concepts, chunk_type in specs:
        text = ("This is a sufficiently long original analytical paraphrase for {}. "
                "It preserves package identity and deterministic source evidence.").format(chunk_id)
        row = dict(base)
        row.update(
            {
                "chunk_id": chunk_id,
                "chunk_type": chunk_type,
                "lecture_number": number,
                "lecture_numbers": [] if number is None else [number],
                "lecture_title": title,
                "topic": topic,
                "concepts": concepts,
                "source": {
                    "provider": "MIT OpenCourseWare",
                    "kind": "official analytical synthesis",
                    "title": chunk_id,
                    "scope_note": "Original paraphrased analysis; not a verbatim transcript.",
                },
                "source_url": "https://ocw.mit.edu/source/{}/".format(chunk_id),
                "text": text,
                "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
        )
        chunk_rows.append(row)
    manifest = {
        "course_id": "mit-18.06-linear-algebra",
        "course": "MIT 18.06 Linear Algebra",
        "instructor": "Prof. Gilbert Strang",
        "version": "2.0",
        "source_policy": ["MIT OpenCourseWare official pages"],
        "counts": {
            "lecture_inventory_records": 2,
            "rag_chunks": 3,
            "lecture_chunks": 2,
            "concept_chunks": 1,
        },
        "official_hubs": {
            "course": "https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/"
        },
    }
    (root / "course_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (root / "lecture_inventory.json").write_text(
        json.dumps(inventory), encoding="utf-8"
    )
    (root / "schema.json").write_text(
        json.dumps({"title": "synthetic test schema"}), encoding="utf-8"
    )
    (root / "chunks.jsonl").write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in chunk_rows) + "\n",
        encoding="utf-8",
    )
    return root


def _env(tmp_path):
    db = tmp_path / "db.sqlite"
    apply_migrations(db)
    connection = sqlite3.connect(str(db), isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(
        "INSERT INTO courses(id,code,name,status,description,created_at,updated_at,deleted_at) "
        "VALUES ('c1','MA103N','Linear Algebra','active','',?,?,NULL)",
        (NOW, NOW),
    )
    topics = [
        ("t-system", "Systems of Linear Equations", "systems of linear equations", 1),
        ("t-lu", "LU Factorization", "lu factorization", 2),
    ]
    for topic_id, name, normalized, position in topics:
        connection.execute(
            "INSERT INTO topics(id,course_id,name,normalized_name,position,status,"
            "confidence,raw_import_status,created_at,updated_at,deleted_at) "
            "VALUES (?, 'c1', ?, ?, ?, 'not_started',NULL,NULL,?,?,NULL)",
            (topic_id, name, normalized, position, NOW, NOW),
        )
    repo = SQLiteExternalCourseKnowledgeRepository(connection)
    service = ExternalCourseKnowledgeService(repo, now=lambda: NOW)
    return db, connection, repo, service



def _complete_crosswalk(service, package, tmp_path):
    value = service.crosswalk.build_template(
        package, local_course_code="MA103N"
    )
    for row in value["mappings"]:
        if row["current_state"] == "exact_mapped":
            continue
        row["decision"] = "leave_unresolved"
        row["reviewed"] = True
        row["review_note"] = "Synthetic explicit review."
    path = tmp_path / "reviewed_crosswalk.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return service.crosswalk.load_reviewed(
        path,
        package,
        local_course_code="MA103N",
        require_complete=True,
    )

def test_package_reader_validates_counts_hashes_and_official_sources(tmp_path):
    package = MIT1806PackageReader(_package(tmp_path)).load()
    assert package.course_id == "mit-18.06-linear-algebra"
    assert len(package.lectures) == 2
    assert len(package.chunks) == 3
    assert all(len(item.content_hash) == 64 for item in package.chunks)


def test_package_reader_rejects_chunk_text_hash_drift(tmp_path):
    root = _package(tmp_path)
    lines = (root / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[0])
    row["text"] += " changed"
    lines[0] = json.dumps(row)
    (root / "chunks.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ExternalCoursePackageError, match="content_hash"):
        MIT1806PackageReader(root).load()


def test_preview_is_read_only_maps_exact_topics_and_keeps_unresolved(tmp_path):
    root = _package(tmp_path)
    db, connection, repo, service = _env(tmp_path)
    package = MIT1806PackageReader(root).load()
    before_changes = connection.total_changes
    before_counts = (
        connection.execute("SELECT COUNT(*) FROM resources").fetchone()[0],
        connection.execute("SELECT COUNT(*) FROM knowledge_documents").fetchone()[0],
        connection.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0],
    )
    preview = service.preview(
        package, package_key="mit1806-package", local_course_code="MA103N"
    )
    after_counts = (
        connection.execute("SELECT COUNT(*) FROM resources").fetchone()[0],
        connection.execute("SELECT COUNT(*) FROM knowledge_documents").fetchone()[0],
        connection.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0],
    )
    assert connection.total_changes == before_changes
    assert after_counts == before_counts
    assert preview.mapped_topic_label_count == 2
    assert preview.unresolved_topic_label_count >= 2
    assert preview.planned_resource_count == 3
    connection.close()


def test_apply_creates_course_lectures_documents_exact_chunks_and_handoff(tmp_path):
    root = _package(tmp_path)
    _db, connection, repo, service = _env(tmp_path)
    package = MIT1806PackageReader(root).load()
    reviewed = _complete_crosswalk(service, package, tmp_path)
    result = service.apply(
        package, package_key="mit1806-package", local_course_code="MA103N",
        reviewed_crosswalk=reviewed,
    )
    assert result.lecture_resource_count == 2
    assert result.knowledge_document_count == 4
    assert result.chunk_count == 3
    assert result.handoff_job_id
    resources = connection.execute(
        "SELECT resource_type,provider,external_id FROM resources ORDER BY external_id"
    ).fetchall()
    assert len(resources) == 3
    assert {row["resource_type"] for row in resources} == {
        "external_course", "external_lecture"
    }
    chunks = connection.execute(
        "SELECT * FROM knowledge_chunks ORDER BY ordinal"
    ).fetchall()
    assert len(chunks) == 3
    kind, locator = decode_chunk_type(chunks[0]["chunk_type"])
    assert locator["external_course_id"] == "mit-18.06-linear-algebra"
    assert locator["source"]["provider"] == "MIT OpenCourseWare"
    assert locator["source_url"].startswith("https://ocw.mit.edu/")
    assert locator["package_chunk_id"]
    jobs = connection.execute(
        "SELECT index_kind,status FROM index_jobs"
    ).fetchall()
    assert [(row[0], row[1]) for row in jobs] == [
        ("retrieval_handoff", "pending")
    ]
    connection.close()


def test_external_course_is_related_to_ma103n_not_relabelled_as_ma103n(tmp_path):
    root = _package(tmp_path)
    _db, connection, repo, service = _env(tmp_path)
    package = MIT1806PackageReader(root).load()
    reviewed = _complete_crosswalk(service, package, tmp_path)
    result = service.apply(
        package,
        package_key="mit1806-package",
        local_course_code="MA103N",
        reviewed_crosswalk=reviewed,
    )
    row = connection.execute(
        "SELECT r.title,r.provider,r.external_id,rc.course_id,rc.role "
        "FROM resources r JOIN resource_courses rc ON rc.resource_id=r.id "
        "WHERE r.id=?",
        (result.course_resource_id,),
    ).fetchone()
    assert row["title"] == "MIT 18.06 Linear Algebra"
    assert row["provider"] == "mit_ocw"
    assert row["external_id"] == "mit-18.06-linear-algebra"
    assert row["course_id"] == "c1"
    assert row["role"] == "external_course"
    connection.close()


def test_only_exact_local_topic_matches_are_linked(tmp_path):
    root = _package(tmp_path)
    _db, connection, repo, service = _env(tmp_path)
    package = MIT1806PackageReader(root).load()
    reviewed = _complete_crosswalk(service, package, tmp_path)
    service.apply(
        package, package_key="mit1806-package", local_course_code="MA103N",
        reviewed_crosswalk=reviewed,
    )
    links = connection.execute(
        "SELECT t.name,rt.relation_source,rt.confidence "
        "FROM resource_topics rt JOIN topics t ON t.id=rt.topic_id "
        "ORDER BY t.name"
    ).fetchall()
    assert {row["name"] for row in links} == {
        "LU Factorization", "Systems of Linear Equations"
    }
    assert all(row["relation_source"] == "imported" for row in links)
    connection.close()


def test_apply_is_idempotent_and_preserves_user_resource_state(tmp_path):
    root = _package(tmp_path)
    _db, connection, repo, service = _env(tmp_path)
    package = MIT1806PackageReader(root).load()
    reviewed = _complete_crosswalk(service, package, tmp_path)
    first = service.apply(
        package, package_key="mit1806-package", local_course_code="MA103N",
        reviewed_crosswalk=reviewed,
    )
    connection.execute(
        "UPDATE resources SET status='in_progress',rating=5,quality_note='Keep me' "
        "WHERE id=?",
        (first.course_resource_id,),
    )
    second = service.apply(
        package, package_key="mit1806-package", local_course_code="MA103N",
        reviewed_crosswalk=reviewed,
    )
    assert second.course_resource_id == first.course_resource_id
    row = connection.execute(
        "SELECT status,rating,quality_note FROM resources WHERE id=?",
        (first.course_resource_id,),
    ).fetchone()
    assert tuple(row) == ("in_progress", 5, "Keep me")
    assert connection.execute("SELECT COUNT(*) FROM resources").fetchone()[0] == 3
    assert connection.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0] == 3
    assert connection.execute("SELECT COUNT(*) FROM index_jobs").fetchone()[0] == 1
    connection.close()


def test_package_source_bytes_never_change(tmp_path):
    root = _package(tmp_path)
    before = {
        path.name: path.read_bytes()
        for path in root.iterdir()
        if path.is_file()
    }
    _db, connection, repo, service = _env(tmp_path)
    package = MIT1806PackageReader(root).load()
    reviewed = _complete_crosswalk(service, package, tmp_path)
    service.apply(
        package,
        package_key="mit1806-package",
        local_course_code="MA103N",
        reviewed_crosswalk=reviewed,
    )
    after = {
        path.name: path.read_bytes()
        for path in root.iterdir()
        if path.is_file()
    }
    assert after == before
    connection.close()


def test_integrity_foreign_keys_and_no_new_schema_tables(tmp_path):
    root = _package(tmp_path)
    _db, connection, repo, service = _env(tmp_path)
    before_tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    package = MIT1806PackageReader(root).load()
    reviewed = _complete_crosswalk(service, package, tmp_path)
    service.apply(
        package,
        package_key="mit1806-package",
        local_course_code="MA103N",
        reviewed_crosswalk=reviewed,
    )
    after_tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert after_tables == before_tables
    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    connection.close()
