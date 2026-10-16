"""Paper authoring provenance checks: no live store, no secret disclosure."""
import json
import sqlite3

import pytest

from test_assessment_studio_phase_b import _database, _raw, _subjective_package


def approved_paper(tmp_path):
    from personal_learning_assistant.services.assessment_package_service import AssessmentPackageService
    path = _database(tmp_path)
    authored = _subjective_package()
    authored["assessment"]["mode"] = "practice"
    service = AssessmentPackageService(path)
    staged = service.stage_upload("subjective.json", _raw(authored))
    aid = service.approve(staged["id"])
    assert aid
    return path, aid


def inspect(path, aid):
    from personal_learning_assistant.services.assessment_paper_admission import inspect_paper_import
    uri = path.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        before = db.total_changes
        verdict = inspect_paper_import(db, aid)
        assert db.total_changes == before
        db.rollback()
    return verdict


def test_approved_subjective_paper_has_structural_lineage_but_no_reviewer_authority(tmp_path):
    path, aid = approved_paper(tmp_path)
    verdict = inspect(path, aid)
    assert verdict["structural_status"] == "PASS", verdict
    assert verdict["question_count"] == 2
    assert verdict["issues"] == []
    assert verdict["production_admission"] == "BLOCKED"
    assert verdict["human_rubric_review"] == "UNVERIFIABLE"
    assert verdict["immutable_review_provenance"] == "UNVERIFIABLE"
    assert verdict["self_marks_official_grade_eligible"] is False
    payload = json.dumps(verdict)
    assert "Solve from the final triangular equation" not in payload
    assert "Factorization followed by forward" not in payload


def test_forged_package_and_canonical_solution_edit_block_structural_admission(tmp_path):
    path, aid = approved_paper(tmp_path)
    with sqlite3.connect(path) as db:
        db.execute(
            "UPDATE assessment_question_specs SET solution_text='stale-secret' "
            "WHERE question_id=(SELECT id FROM questions WHERE assessment_id=? LIMIT 1)",
            (aid,),
        )
    verdict = inspect(path, aid)
    assert verdict["structural_status"] == "BLOCKED"
    assert "subjective_snapshot_or_rubric_mismatch" in verdict["issues"]
    assert "stale-secret" not in json.dumps(verdict)
    assert verdict["production_admission"] == "BLOCKED"


def test_unapproved_or_unlinked_assessment_cannot_be_treated_as_reviewed(tmp_path):
    path = _database(tmp_path)
    verdict = inspect(path, "not-a-reviewed-import")
    assert verdict["production_admission"] == "BLOCKED"
    assert verdict["structural_status"] == "BLOCKED"
    assert "approved_package_link_missing" in verdict["issues"]


def test_read_only_transaction_is_mandatory(tmp_path):
    from personal_learning_assistant.services.assessment_paper_admission import inspect_paper_import
    path, aid = approved_paper(tmp_path)
    with sqlite3.connect(path) as db:
        with pytest.raises(ValueError, match="query-only"):
            inspect_paper_import(db, aid)
        db.execute("PRAGMA query_only=ON")
        with pytest.raises(ValueError, match="read transaction"):
            inspect_paper_import(db, aid)
        db.execute("BEGIN")
        assert inspect_paper_import(db, aid)["production_admission"] == "BLOCKED"
        db.rollback()
