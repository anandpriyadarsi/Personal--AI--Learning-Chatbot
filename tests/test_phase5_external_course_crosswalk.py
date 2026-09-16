from __future__ import annotations

import json

import pytest

from personal_learning_assistant.ingestion.external_course_package import MIT1806PackageReader
from personal_learning_assistant.services.external_course_crosswalk_service import (
    ExternalCourseCrosswalkError,
    ExternalCourseCrosswalkService,
)
from personal_learning_assistant.services.external_course_knowledge_service import (
    ExternalCourseKnowledgeService,
)

from tests.test_phase5_external_course_knowledge import _env, _package


def _reviewed_template(service, package, *, local_course="MA103N"):
    template = service.crosswalk.build_template(
        package, local_course_code=local_course
    )
    for row in template["mappings"]:
        if row["current_state"] == "exact_mapped":
            continue
        suggestions = row.get("suggestions") or []
        # Synthetic tests explicitly review only the close LU/Gaussian-style
        # candidate when present; everything else is deliberately unresolved.
        chosen = next(
            (
                item
                for item in suggestions
                if item["topic_name"] == "LU Factorization"
                and "lu" in row["external_label"].casefold()
            ),
            None,
        )
        if chosen:
            row["decision"] = "map"
            row["reviewed"] = True
            row["target_topic_id"] = chosen["topic_id"]
            row["target_topic_name"] = chosen["topic_name"]
            row["review_note"] = "Synthetic explicit review."
        else:
            row["decision"] = "leave_unresolved"
            row["reviewed"] = True
            row["review_note"] = "Synthetic explicit out-of-scope/non-equivalent review."
    return template


def test_template_contains_all_package_labels_local_topics_and_review_only_suggestions(tmp_path):
    root = _package(tmp_path)
    _db, connection, repo, service = _env(tmp_path)
    package = MIT1806PackageReader(root).load()
    template = service.crosswalk.build_template(
        package, local_course_code="MA103N"
    )
    assert template["external_course_id"] == "mit-18.06-linear-algebra"
    assert len(template["mappings"]) == 4
    assert {item["name"] for item in template["local_topics"]} == {
        "Systems of Linear Equations",
        "LU Factorization",
    }
    pending = [item for item in template["mappings"] if item["decision"] == "pending"]
    assert pending
    assert all(item["reviewed"] is False for item in pending)
    connection.close()


def test_reviewed_crosswalk_maps_explicit_decision_and_preserves_unresolved(tmp_path):
    root = _package(tmp_path)
    _db, connection, repo, service = _env(tmp_path)
    package = MIT1806PackageReader(root).load()
    value = _reviewed_template(service, package)
    path = tmp_path / "crosswalk.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    reviewed = service.crosswalk.load_reviewed(
        path, package, local_course_code="MA103N", require_complete=True
    )
    preview = service.crosswalk.preview(
        package,
        local_course_code="MA103N",
        reviewed_crosswalk=reviewed,
    )
    assert preview.crosswalk_complete is True
    assert preview.exact_mapped_label_count >= 2
    assert preview.reviewed_unresolved_label_count >= 1
    assert preview.pending_review_label_count == 0
    connection.close()


def test_crosswalk_rejects_stale_package_manifest_hash(tmp_path):
    root = _package(tmp_path)
    _db, connection, repo, service = _env(tmp_path)
    package = MIT1806PackageReader(root).load()
    value = _reviewed_template(service, package)
    value["source_manifest_hash"] = "0" * 64
    path = tmp_path / "crosswalk.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ExternalCourseCrosswalkError, match="source_manifest_hash"):
        service.crosswalk.load_reviewed(
            path, package, local_course_code="MA103N", require_complete=True
        )
    connection.close()


def test_crosswalk_rejects_target_topic_name_drift(tmp_path):
    root = _package(tmp_path)
    _db, connection, repo, service = _env(tmp_path)
    package = MIT1806PackageReader(root).load()
    value = _reviewed_template(service, package)
    target = next(
        row for row in value["mappings"] if row["decision"] == "map"
    )
    target["target_topic_name"] = "Wrong Name"
    path = tmp_path / "crosswalk.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ExternalCourseCrosswalkError, match="target_topic_name drift"):
        service.crosswalk.load_reviewed(
            path, package, local_course_code="MA103N", require_complete=True
        )
    connection.close()


def test_real_apply_requires_complete_reviewed_crosswalk_object(tmp_path):
    root = _package(tmp_path)
    _db, connection, repo, service = _env(tmp_path)
    package = MIT1806PackageReader(root).load()
    with pytest.raises(ExternalCourseCrosswalkError, match="requires a reviewed crosswalk"):
        service.apply(
            package,
            package_key="mit1806-package",
            local_course_code="MA103N",
            reviewed_crosswalk=None,
        )
    connection.close()


def test_apply_with_crosswalk_writes_local_topic_ids_into_chunk_provenance(tmp_path):
    root = _package(tmp_path)
    _db, connection, repo, service = _env(tmp_path)
    package = MIT1806PackageReader(root).load()
    value = _reviewed_template(service, package)
    path = tmp_path / "crosswalk.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    reviewed = service.crosswalk.load_reviewed(
        path, package, local_course_code="MA103N", require_complete=True
    )
    result = service.apply(
        package,
        package_key="mit1806-package",
        local_course_code="MA103N",
        reviewed_crosswalk=reviewed,
    )
    rows = connection.execute(
        "SELECT chunk_type FROM knowledge_chunks ORDER BY ordinal"
    ).fetchall()
    from personal_learning_assistant.ingestion.chunking import decode_chunk_type
    locators = [decode_chunk_type(row[0])[1] for row in rows]
    assert all(locator["crosswalk_sha256"] == reviewed.crosswalk_sha256 for locator in locators)
    assert any(locator["local_topic_ids"] for locator in locators)
    assert result.extraction_version.endswith(
        "xwalk:" + reviewed.crosswalk_sha256[:16]
    )
    connection.close()


def test_revised_crosswalk_stales_previous_same_content_handoff(tmp_path):
    root = _package(tmp_path)
    _db, connection, repo, service = _env(tmp_path)
    package = MIT1806PackageReader(root).load()

    first_value = _reviewed_template(service, package)
    first_path = tmp_path / "first.json"
    first_path.write_text(json.dumps(first_value), encoding="utf-8")
    first = service.crosswalk.load_reviewed(
        first_path, package, local_course_code="MA103N", require_complete=True
    )
    service.apply(
        package,
        package_key="mit1806-package",
        local_course_code="MA103N",
        reviewed_crosswalk=first,
    )

    second_value = _reviewed_template(service, package)
    # Change one explicit leave-unresolved review note does not change semantic
    # crosswalk hash, so change a decision by mapping a previously unresolved
    # label to an existing topic intentionally.
    row = next(
        item
        for item in second_value["mappings"]
        if item["decision"] == "leave_unresolved"
    )
    row["decision"] = "map"
    row["target_topic_id"] = "t-lu"
    row["target_topic_name"] = "LU Factorization"
    row["review_note"] = "Intentional synthetic reviewed remap."
    second_path = tmp_path / "second.json"
    second_path.write_text(json.dumps(second_value), encoding="utf-8")
    second = service.crosswalk.load_reviewed(
        second_path, package, local_course_code="MA103N", require_complete=True
    )
    assert first.crosswalk_sha256 != second.crosswalk_sha256

    service.apply(
        package,
        package_key="mit1806-package",
        local_course_code="MA103N",
        reviewed_crosswalk=second,
    )
    jobs = connection.execute(
        "SELECT status,index_version FROM index_jobs ORDER BY created_at,id"
    ).fetchall()
    by_version = {row["index_version"]: row["status"] for row in jobs}
    assert by_version[service.handoff_index_version(first)] == "stale"
    assert by_version[service.handoff_index_version(second)] == "pending"
    connection.close()
