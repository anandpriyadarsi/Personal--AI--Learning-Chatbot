from __future__ import annotations

import io
import json
import sqlite3
from pathlib import Path

import pytest


NOW = "2026-09-27T00:00:00Z"


def _database(tmp_path):
    from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations

    path = tmp_path / "learning_assistant.db"
    assert apply_migrations(path) == tuple(range(1, 11))
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "INSERT INTO courses "
            "(id, code, name, status, description, created_at, updated_at) "
            "VALUES (?, ?, ?, 'active', '', ?, ?)",
            ("course-ma", "MA103N", "Linear Algebra", NOW, NOW),
        )
        connection.execute(
            "INSERT INTO topics "
            "(id, course_id, name, normalized_name, position, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 1, 'not_started', ?, ?)",
            (
                "topic-lu",
                "course-ma",
                "LU Factorization",
                "lu factorization",
                NOW,
                NOW,
            ),
        )
        connection.execute(
            "INSERT INTO topics "
            "(id, course_id, name, normalized_name, position, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 2, 'not_started', ?, ?)",
            (
                "topic-inverse",
                "course-ma",
                "Matrix Inverse",
                "matrix inverse",
                NOW,
                NOW,
            ),
        )
        connection.execute(
            "INSERT INTO topic_aliases "
            "(id, topic_id, course_id, alias, normalized_alias, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "alias-lu",
                "topic-lu",
                "course-ma",
                "LU decomposition",
                "lu decomposition",
                "test",
                NOW,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return path


def _package(*, package_id="ma103n.quiz.001", revision=1, review_required=False):
    return {
        "schema": "anvaya.assessment-package",
        "version": 1,
        "package_id": package_id,
        "package_revision": revision,
        "created_at": "2026-09-27T00:00:00Z",
        "authoring": {
            "engine": "ChatGPT/Alex",
            "model": "test-model",
            "purpose": "generated_practice",
        },
        "assessment": {
            "course": {"code": "MA103N", "name": "Linear Algebra"},
            "title": "LU Practice Quiz",
            "type": "quiz",
            "mode": "exam",
            "duration_minutes": 30,
            "total_marks": 4,
            "instructions": ["Attempt independently."],
            "source": {"kind": "course_material", "label": "Test source"},
        },
        "questions": [
            {
                "id": "q1",
                "number": "1",
                "section": "A",
                "type": "mcq",
                "text": "In A=LU, which factor is lower triangular?",
                "marks": 1,
                "negative_marks": 0.25,
                "scoring_policy": "standard",
                "options": [
                    {"id": "A", "text": "A"},
                    {"id": "B", "text": "L"},
                    {"id": "C", "text": "U"},
                    {"id": "D", "text": "b"},
                ],
                "answer": {
                    "correct_option_ids": ["B"],
                    "accepted_answers": [],
                },
                "solution": "L is the lower-triangular factor in A=LU.",
                "rubric": "",
                "academic_map": {
                    "chapter": "Systems of Linear Equations",
                    "topic": "LU Factorization",
                    "subtopic": "Factor structure",
                    "concepts": ["lower triangular", "upper triangular"],
                    "difficulty": "easy",
                    "expected_method": "Recall the definition of LU factorization.",
                    "estimated_minutes": 1,
                    "topic_mapping_confidence": 0.95,
                },
                "source": {
                    "kind": "original",
                    "label": "Alex practice",
                    "page": None,
                    "locator": "Q1",
                },
                "authoring_confidence": 0.98,
                "review_required": review_required,
            },
            {
                "id": "q2",
                "number": "2",
                "section": "B",
                "type": "long_subjective",
                "text": "Explain how LU factorization solves Ax=b.",
                "marks": 3,
                "negative_marks": 0,
                "scoring_policy": "standard",
                "options": [],
                "answer": {
                    "correct_option_ids": [],
                    "accepted_answers": [],
                },
                "solution": "Factor A=LU, solve Ly=b, then solve Ux=y.",
                "rubric": "1 mark factorization, 1 mark forward solve, 1 mark backward solve.",
                "academic_map": {
                    "chapter": "Systems of Linear Equations",
                    "topic": "LU Factorization",
                    "subtopic": "Solving systems",
                    "concepts": ["forward substitution", "back substitution"],
                    "difficulty": "medium",
                    "expected_method": "Describe the two triangular solves.",
                    "estimated_minutes": 5,
                    "topic_mapping_confidence": 0.95,
                },
                "source": {
                    "kind": "original",
                    "label": "Alex practice",
                    "page": 2,
                    "locator": "Q2",
                },
                "authoring_confidence": 0.98,
                "review_required": False,
            },
        ],
    }


def _raw(package=None):
    return json.dumps(package or _package(), ensure_ascii=False).encode("utf-8")


def _subjective_package():
    package = _package(package_id="ma103n.subjective.001")
    package["assessment"]["title"] = "Subjective Review Test"
    package["assessment"]["total_marks"] = 6
    package["questions"] = [
        {
            "id": "s1",
            "number": "1",
            "section": "A",
            "type": "long_subjective",
            "text": "Explain factorization. SECOND QUESTION Explain forward substitution.",
            "marks": 3,
            "negative_marks": 0,
            "scoring_policy": "standard",
            "options": [],
            "answer": {"correct_option_ids": [], "accepted_answers": []},
            "solution": "Factorization followed by forward substitution.",
            "rubric": "Award marks for the method and reasoning.",
            "academic_map": {
                "chapter": "Systems",
                "topic": "LU Factorization",
                "subtopic": "Procedure",
                "concepts": ["factorization"],
                "difficulty": "medium",
                "expected_method": "Explain steps.",
                "estimated_minutes": 5,
                "topic_mapping_confidence": 0.95,
            },
            "source": {"kind": "original", "label": "Alex", "page": 1, "locator": "Q1"},
            "authoring_confidence": 0.98,
            "review_required": False,
        },
        {
            "id": "s2",
            "number": "2",
            "section": "A",
            "type": "long_subjective",
            "text": "Explain backward substitution.",
            "marks": 3,
            "negative_marks": 0,
            "scoring_policy": "standard",
            "options": [],
            "answer": {"correct_option_ids": [], "accepted_answers": []},
            "solution": "Solve from the final triangular equation upward.",
            "rubric": "Award marks for correct order and reasoning.",
            "academic_map": {
                "chapter": "Systems",
                "topic": "LU Factorization",
                "subtopic": "Procedure",
                "concepts": ["back substitution"],
                "difficulty": "medium",
                "expected_method": "Explain steps.",
                "estimated_minutes": 5,
                "topic_mapping_confidence": 0.95,
            },
            "source": {"kind": "original", "label": "Alex", "page": 1, "locator": "Q2"},
            "authoring_confidence": 0.98,
            "review_required": False,
        },
    ]
    return package


def test_migration_0010_adds_staging_runtime_and_question_metadata(tmp_path):
    path = _database(tmp_path)
    connection = sqlite3.connect(path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {
            "assessment_import_batches",
            "assessment_import_questions",
            "assessment_import_question_options",
            "assessment_runtime_specs",
            "assessment_question_specs",
            "question_options",
        }.issubset(tables)
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_strict_package_parser_rejects_duplicate_unknown_and_invalid_answer_keys(tmp_path):
    from personal_learning_assistant.services.assessment_package_service import (
        AssessmentPackageService,
        AssessmentPackageValidationError,
    )

    service = AssessmentPackageService(_database(tmp_path))

    duplicate = (
        '{"schema":"anvaya.assessment-package","schema":"x","version":1,'
        '"package_id":"x","package_revision":1,"created_at":"2026-09-27T00:00:00Z",'
        '"authoring":{},"assessment":{},"questions":[]}'
    ).encode()
    with pytest.raises(AssessmentPackageValidationError, match="Duplicate JSON key"):
        service.stage_upload("bad.anvaya-assessment.json", duplicate)

    unknown = _package(package_id="unknown-field")
    unknown["surprise"] = True
    with pytest.raises(AssessmentPackageValidationError, match="unsupported field"):
        service.stage_upload("bad.json", _raw(unknown))

    invalid_key = _package(package_id="bad-answer")
    invalid_key["questions"][0]["answer"]["correct_option_ids"] = ["Z"]
    with pytest.raises(AssessmentPackageValidationError, match="does not exist"):
        service.stage_upload("bad.json", _raw(invalid_key))


def test_stage_is_review_only_idempotent_and_detects_revision_conflict(tmp_path):
    from personal_learning_assistant.services.assessment_package_service import (
        AssessmentPackageConflictError,
        AssessmentPackageService,
    )

    path = _database(tmp_path)
    service = AssessmentPackageService(path)
    first = service.stage_upload("quiz.anvaya-assessment.json", _raw())
    second = service.stage_upload("quiz.anvaya-assessment.json", _raw())

    assert first["id"] == second["id"]
    review = service.review(first["id"])
    assert review["course_code"] == "MA103N"
    assert review["status"] == "review"
    assert review["can_approve"] is True
    assert [q["selected_topic_name"] for q in review["questions"]] == [
        "LU Factorization",
        "LU Factorization",
    ]

    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM assessments").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM question_attempts").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM topic_progress_events").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM study_plan_items").fetchone()[0] == 0
    finally:
        connection.close()

    changed = _package()
    changed["assessment"]["title"] = "Changed without revision"
    with pytest.raises(AssessmentPackageConflictError, match="Increase package_revision"):
        service.stage_upload("quiz.json", _raw(changed))


def test_review_required_question_can_be_explicitly_confirmed_and_edited(tmp_path):
    from personal_learning_assistant.services.assessment_package_service import (
        AssessmentPackageService,
    )

    service = AssessmentPackageService(_database(tmp_path))
    batch = service.stage_upload(
        "review.json", _raw(_package(package_id="needs-review", review_required=True))
    )
    review = service.review(batch["id"])
    assert review["can_approve"] is False
    assert any("Review required" in item for item in review["blockers"])

    question = review["questions"][0]
    service.update_question(
        question["id"],
        {
            "question_number": question["question_number"],
            "section_label": question["section_label"],
            "question_type": question["question_type"],
            "question_text": question["question_text"],
            "marks": question["marks"],
            "negative_marks": question["negative_marks"],
            "scoring_policy": question["scoring_policy"],
            "difficulty": question["difficulty"],
            "estimated_minutes": question["estimated_minutes"],
            "selected_topic_id": "topic-lu",
            "chapter_label": question["chapter_label"],
            "raw_topic_label": question["raw_topic_label"],
            "subtopic_label": question["subtopic_label"],
            "concepts": ", ".join(question["concepts"]),
            "expected_method": question["expected_method"],
            "solution_text": question["solution_text"],
            "rubric_text": question["rubric_text"],
            "source_kind": question["source_kind"],
            "source_label": question["source_label"],
            "source_page": question["source_page"] or "",
            "source_locator": question["source_locator"],
            "correct_option_ids": ["B"],
            "option_texts": [o["option_text"] for o in question["options"]],
            "accepted_answers": "",
            "review_complete": True,
        },
    )
    assert service.review(batch["id"])["can_approve"] is True


def test_non_subjective_segmentation_is_rejected(tmp_path):
    from personal_learning_assistant.services.assessment_package_service import (
        AssessmentPackageService,
        AssessmentPackageValidationError,
    )

    service = AssessmentPackageService(_database(tmp_path))
    batch = service.stage_upload("quiz.json", _raw())
    questions = list(service.review(batch["id"])["questions"])
    mcq = questions[0]

    with pytest.raises(AssessmentPackageValidationError, match="Only subjective"):
        service.split(mcq["id"], "which factor")

    with pytest.raises(AssessmentPackageValidationError, match="Only adjacent subjective"):
        service.merge_next(mcq["id"])


def test_split_merge_reorder_and_remove_only_change_staging(tmp_path):
    from personal_learning_assistant.services.assessment_package_service import (
        AssessmentPackageService,
    )

    path = _database(tmp_path)
    service = AssessmentPackageService(path)
    batch = service.stage_upload("subjective.json", _raw(_subjective_package()))
    questions = list(service.review(batch["id"])["questions"])

    service.split(questions[0]["id"], "SECOND QUESTION")
    after_split = service.review(batch["id"])
    assert len(after_split["questions"]) == 3
    assert [q["ordinal"] for q in after_split["questions"]] == [1, 2, 3]
    assert after_split["questions"][0]["review_required"] is True
    assert after_split["questions"][1]["review_required"] is True

    service.merge_next(after_split["questions"][0]["id"])
    after_merge = service.review(batch["id"])
    assert len(after_merge["questions"]) == 2

    second_id = after_merge["questions"][1]["id"]
    service.reorder(second_id, "up")
    reordered = service.review(batch["id"])
    assert reordered["questions"][0]["id"] == second_id

    service.remove(reordered["questions"][1]["id"])
    final = service.review(batch["id"])
    assert len(final["questions"]) == 1
    assert final["questions"][0]["ordinal"] == 1

    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM assessments").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 0
    finally:
        connection.close()


def test_approval_atomically_creates_canonical_assessment_and_provenance_only(tmp_path):
    from personal_learning_assistant.services.assessment_package_service import (
        AssessmentPackageService,
    )

    path = _database(tmp_path)
    service = AssessmentPackageService(path)
    batch = service.stage_upload("quiz.json", _raw())
    assessment_id = service.approve(batch["id"])
    assert assessment_id

    connection = sqlite3.connect(path)
    try:
        assessment = connection.execute(
            "SELECT course_id, assessment_type, title, max_points_milli, status "
            "FROM assessments WHERE id=?",
            (assessment_id,),
        ).fetchone()
        assert assessment == (
            "course-ma",
            "quiz",
            "LU Practice Quiz",
            4000,
            "pending",
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM questions WHERE assessment_id=?", (assessment_id,)
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM assessment_question_specs s "
            "JOIN questions q ON q.id=s.question_id WHERE q.assessment_id=?",
            (assessment_id,),
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM question_options o "
            "JOIN questions q ON q.id=o.question_id WHERE q.assessment_id=?",
            (assessment_id,),
        ).fetchone()[0] == 4
        assert connection.execute(
            "SELECT COUNT(*) FROM question_topic_mappings m "
            "JOIN questions q ON q.id=m.question_id "
            "WHERE q.assessment_id=? AND m.state='confirmed'",
            (assessment_id,),
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM question_sources s "
            "JOIN questions q ON q.id=s.question_id WHERE q.assessment_id=?",
            (assessment_id,),
        ).fetchone()[0] == 2
        runtime = connection.execute(
            "SELECT mode, duration_minutes, package_id, package_revision "
            "FROM assessment_runtime_specs WHERE assessment_id=?",
            (assessment_id,),
        ).fetchone()
        assert runtime == ("exam", 30, "ma103n.quiz.001", 1)
        assert connection.execute(
            "SELECT status, assessment_id FROM assessment_import_batches WHERE id=?",
            (batch["id"],),
        ).fetchone() == ("approved", assessment_id)

        assert connection.execute("SELECT COUNT(*) FROM question_attempts").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM topic_progress_events").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM study_plan_items").fetchone()[0] == 0
    finally:
        connection.close()

    assert service.approve(batch["id"]) == assessment_id


def _app(path):
    from personal_learning_assistant.services.assessment_package_service import (
        AssessmentPackageService,
    )
    from personal_learning_assistant.ui.web import create_app

    return create_app(
        {
            "TESTING": True,
            "ASSESSMENT_PACKAGE_SERVICE_FACTORY": lambda: AssessmentPackageService(path),
        }
    )


def test_web_upload_review_is_prg_and_gets_do_not_create_canonical_assessment(tmp_path):
    path = _database(tmp_path)
    client = _app(path).test_client()

    landing = client.get("/assessments/import")
    assert landing.status_code == 200
    assert "Import Alex assessment package" in landing.get_data(as_text=True)

    response = client.post(
        "/assessments/import",
        data={
            "package": (
                io.BytesIO(_raw()),
                "MA103N_quiz.anvaya-assessment.json",
            )
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "/review" in response.headers["Location"]

    review = client.get(response.headers["Location"])
    assert review.status_code == 200
    text = review.get_data(as_text=True)
    assert "LU Practice Quiz" in text
    assert "Approve import" in text
    assert "LU Factorization" in text

    connection = sqlite3.connect(path)
    try:
        before = connection.execute("SELECT COUNT(*) FROM assessments").fetchone()[0]
    finally:
        connection.close()
    assert before == 0

    assert client.get(response.headers["Location"]).status_code == 200
    assert client.get("/assessments/import").status_code == 200

    connection = sqlite3.connect(path)
    try:
        after = connection.execute("SELECT COUNT(*) FROM assessments").fetchone()[0]
    finally:
        connection.close()
    assert after == 0


def test_open_contract_schema_example_and_authoring_prompt_are_present():
    root = Path(__file__).resolve().parents[1]
    schema = json.loads(
        (root / "schemas/anvaya-assessment-package-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    example = json.loads(
        (root / "examples/anvaya_assessment_package_v1.example.json").read_text(
            encoding="utf-8"
        )
    )
    prompt = (
        root / "ANVAYA_ASSESSMENT_PACKAGE_AUTHORING_PROMPT.md"
    ).read_text(encoding="utf-8")

    assert schema["properties"]["schema"]["const"] == "anvaya.assessment-package"
    assert schema["properties"]["version"]["const"] == 1
    assert example["schema"] == "anvaya.assessment-package"
    assert example["version"] == 1
    assert "Alex / ChatGPT" in prompt
    assert "*.anvaya-assessment.json" in prompt
    assert "MCQ" in prompt and "MSQ" in prompt
    assert "review_required" in prompt
