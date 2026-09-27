from __future__ import annotations

import io
import json
import sqlite3
from pathlib import Path


NOW = "2026-09-27T00:00:00Z"


def _database(tmp_path):
    from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations

    path = tmp_path / "learning_assistant.db"
    assert apply_migrations(path) == tuple(range(1, 15))
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "INSERT INTO courses "
            "(id, code, name, status, description, created_at, updated_at) "
            "VALUES ('course-ma','MA103N','Linear Algebra','active','',?,?)",
            (NOW, NOW),
        )
        connection.executemany(
            "INSERT INTO topics "
            "(id, course_id, name, normalized_name, position, status, created_at, updated_at) "
            "VALUES (?, 'course-ma', ?, ?, ?, 'not_started', ?, ?)",
            [
                ("topic-inverse", "Matrix Inverse", "matrix inverse", 1, NOW, NOW),
                ("topic-lu", "LU Factorization", "lu factorization", 2, NOW, NOW),
            ],
        )
        connection.execute(
            "INSERT INTO topic_aliases "
            "(id, topic_id, course_id, alias, normalized_alias, source, created_at) "
            "VALUES ('alias-lu','topic-lu','course-ma','LU decomposition',"
            "'lu decomposition','test',?)",
            (NOW,),
        )
        connection.commit()
    finally:
        connection.close()
    return path


def _package():
    root = Path(__file__).resolve().parents[1]
    return json.loads(
        (root / "examples/anvaya_assessment_package_v1.example.json").read_text(
            encoding="utf-8"
        )
    )


def _service(path):
    from personal_learning_assistant.services.assessment_package_service import (
        AssessmentPackageService,
    )

    return AssessmentPackageService(path)


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


def _raw(package):
    return json.dumps(package, ensure_ascii=False).encode("utf-8")


def test_blind_review_summary_separates_integrity_from_semantic_uncertainty(tmp_path):
    path = _database(tmp_path)
    package = _package()
    package["package_id"] = "ma103n.blind.semantic"
    package["questions"][0]["review_required"] = True
    package["questions"][0]["authoring_confidence"] = 0.6
    package["questions"][0]["academic_map"]["topic"] = "Unknown imported topic"
    package["questions"][0]["academic_map"]["topic_mapping_confidence"] = 0.45

    service = _service(path)
    staged = service.stage_upload(
        "blind.anvaya-assessment.json",
        _raw(package),
        workspace_kind="quiz",
        selected_course_id="course-ma",
    )
    review = service.review(staged["id"])

    assert review["blind_review"]["state"] == "alex_review"
    assert review["blind_review"]["integrity_issue_count"] == 0
    assert review["blind_review"]["semantic_warning_count"] > 0
    assert review["blind_review"]["review_required_count"] == 1
    assert review["blind_review"]["unmapped_topic_count"] == 1
    assert review["blind_review"]["low_authoring_count"] == 1
    assert review["can_approve"] is False


def test_clean_package_can_be_approved_without_human_question_review(tmp_path):
    path = _database(tmp_path)
    package = _package()
    package["package_id"] = "ma103n.blind.clean"

    service = _service(path)
    staged = service.stage_upload(
        "clean.anvaya-assessment.json",
        _raw(package),
        workspace_kind="quiz",
        selected_course_id="course-ma",
    )
    review = service.review(staged["id"])

    assert review["blind_review"]["state"] == "ready"
    assert review["blind_review"]["integrity_issue_count"] == 0
    assert review["blind_review"]["semantic_warning_count"] == 0
    assert review["can_approve"] is True


def test_blind_review_page_never_renders_question_answer_or_solution_content(tmp_path):
    path = _database(tmp_path)
    package = _package()
    package["package_id"] = "ma103n.blind.web"
    package["questions"][0]["review_required"] = True

    client = _app(path).test_client()
    upload = client.post(
        "/assessments/import",
        data={
            "workspace_kind": "quiz",
            "course_id": "course-ma",
            "package": (
                io.BytesIO(_raw(package)),
                "blind-web.anvaya-assessment.json",
            ),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert upload.status_code == 303

    review = client.get(upload.headers["Location"])
    assert review.status_code == 200
    html = review.get_data(as_text=True)

    assert "Spoiler protection active" in html
    assert "Test content is hidden from this review page." in html
    assert "Download Alex review file" in html
    assert "Copy Alex review prompt" in html
    assert "Open Alex / ChatGPT" in html

    hidden_fragments = [
        "Which statement best describes when a square matrix has an inverse?",
        "Its determinant is non-zero",
        "A square matrix is invertible exactly when its determinant is non-zero.",
        "Explain how LU factorization can be used to solve Ax=b.",
        "Factor A=LU, solve Ly=b by forward substitution",
        "1 mark for A=LU",
    ]
    for fragment in hidden_fragments:
        assert fragment not in html

    # The old content-editing workflow must not be linked from blind review.
    assert "Edit staged question" not in html
    assert "Options and answer key" not in html
    assert ">Edit<" not in html


def test_alex_review_prompt_is_non_spoiler_and_handoff_contains_hidden_source_package(tmp_path):
    path = _database(tmp_path)
    package = _package()
    package["package_id"] = "ma103n.blind.handoff"
    package["questions"][0]["review_required"] = True
    package["questions"][0]["academic_map"]["topic"] = "Unknown imported topic"
    package["questions"][0]["academic_map"]["topic_mapping_confidence"] = 0.2

    service = _service(path)
    staged = service.stage_upload(
        "handoff.anvaya-assessment.json",
        _raw(package),
        workspace_kind="quiz",
        selected_course_id="course-ma",
    )

    prompt = service.alex_review_prompt(staged["id"])
    assert "remain blind" in prompt
    assert "package_revision 2" in prompt
    assert "Which statement best describes" not in prompt
    assert "determinant is non-zero" not in prompt

    handoff = service.alex_review_handoff(staged["id"])
    payload = json.loads(handoff["json"])
    assert payload["schema"] == "anvaya.assessment-review-handoff"
    assert payload["required_next_package_revision"] == 2
    assert payload["package_id"] == "ma103n.blind.handoff"
    assert payload["flagged_questions"]
    assert payload["canonical_topic_catalogue"][0]["name"] == "Matrix Inverse"
    assert payload["source_package"]["questions"][0]["text"].startswith(
        "Which statement best describes"
    )


def test_alex_review_handoff_route_downloads_json_without_putting_content_on_page(tmp_path):
    path = _database(tmp_path)
    package = _package()
    package["package_id"] = "ma103n.blind.download"
    package["questions"][0]["review_required"] = True

    client = _app(path).test_client()
    upload = client.post(
        "/assessments/import",
        data={
            "workspace_kind": "quiz",
            "course_id": "course-ma",
            "package": (
                io.BytesIO(_raw(package)),
                "download.anvaya-assessment.json",
            ),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    batch_id = upload.headers["Location"].split("/import/", 1)[1].split("/review", 1)[0]

    response = client.get(
        f"/assessments/import/{batch_id}/alex-review-handoff"
    )
    assert response.status_code == 200
    assert response.mimetype == "application/json"
    assert "attachment;" in response.headers["Content-Disposition"]
    payload = json.loads(response.get_data(as_text=True))
    assert payload["schema"] == "anvaya.assessment-review-handoff"
    assert payload["source_package"]["questions"]


def test_default_authoring_prompt_injects_canonical_topics_and_requests_silent_review(tmp_path):
    workspace = _service(_database(tmp_path)).workspace(
        workspace_kind="quiz",
        course_id="course-ma",
    )

    prompt = workspace["resolved_prompt"]
    assert "CANONICAL ANVAYA COURSE TOPICS" in prompt
    assert "- Matrix Inverse" in prompt
    assert "- LU Factorization (aliases: LU decomposition)" in prompt
    assert "silent semantic review of every question" in prompt
    assert "{{COURSE_TOPICS}}" not in prompt
