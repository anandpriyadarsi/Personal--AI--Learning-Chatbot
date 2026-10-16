"""Read-only structural paper-admission review; does NOT grant production authority.

Examined from an explicitly opened, query-only snapshot transaction. This
verifies approved import lineage against canonical question/spec metadata,
not a human reviewer or a B3 immutable writer attestation. Never show solutions
or answer keys in the result and never convert self-grades into official marks.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

from personal_learning_assistant.domain.assessment_self_evaluation import parse_rubric

SUBJECTIVE = frozenset({"short_subjective", "long_subjective"})


def inspect_paper_import(connection: sqlite3.Connection, assessment_id: str, *, _trusted_write_transaction=False) -> dict:
    """Return bounded, redacted, fail-closed evidence about one imported assessment.

    Caller must explicitly attest a read transaction on a query-only database
    connection. No opening, schema installation, writing, mutation or repair.
    A structurally complete import is still BLOCKED for production pending
    independently verified reviewer/rubric/writer provenance.
    """
    if not isinstance(connection, sqlite3.Connection):
        raise TypeError("An explicit SQLite connection is required.")
    if not connection.in_transaction or (
        not _trusted_write_transaction
        and connection.execute("PRAGMA query_only").fetchone()[0] != 1
    ):
        raise ValueError("Use an explicit read transaction and query-only connection.")
    # A caller already inside an IMMEDIATE transaction may inspect its own
    # immutable snapshots before atomically inserting local self-study state.
    # This exception is private; the inspector still executes SELECT only.
    if not isinstance(assessment_id, str) or not 0 < len(assessment_id) <= 256:
        raise ValueError("Invalid assessment identity.")

    reasons = []
    question_count = 0
    try:
        batch = connection.execute(
            "SELECT id,package_id,package_revision,status,approved_at,assessment_id,"
            "course_id,mode,source_sha256,total_marks_milli FROM main.assessment_import_batches "
            "WHERE assessment_id=?", (assessment_id,)
        ).fetchall()
        canonical = connection.execute(
            "SELECT id,question_text,max_marks_milli,import_batch_id FROM main.questions "
            "WHERE assessment_id=? AND deleted_at IS NULL ORDER BY ordinal,id",
            (assessment_id,)
        ).fetchall()
        question_count = len(canonical)
        runtime = connection.execute(
            "SELECT origin,mode,package_id,package_revision FROM main.assessment_runtime_specs "
            "WHERE assessment_id=?", (assessment_id,)
        ).fetchall()
        owner = connection.execute(
            "SELECT course_id,max_points_milli FROM main.assessments WHERE id=? AND deleted_at IS NULL",
            (assessment_id,)
        ).fetchall()
        if len(batch) != 1 or batch[0][3] != "approved" or not batch[0][4]:
            reasons.append("approved_package_link_missing")
        if len(owner) != 1 or not canonical:
            reasons.append("canonical_assessment_missing_or_empty")
        if len(runtime) != 1:
            reasons.append("runtime_snapshot_missing")
        if reasons:
            return _result(reasons, question_count)
        approved = batch[0]
        spec = runtime[0]
        # Allocation must agree across the approved batch, canonical assessment,
        # and the complete immutable question lineage. A silent aggregate mark
        # change would mislead handwritten self-evaluation even if each rubric
        # remained individually parseable.
        if (approved[9] != owner[0][1]
                or approved[9] != sum(row[2] for row in canonical)):
            reasons.append("approved_total_marks_mismatch")
        if (approved[5] != assessment_id or approved[6] != owner[0][0]
                or approved[7] != "practice" or spec[1] != "practice"
                or spec[0] != "external_package"
                or approved[1] != spec[2] or approved[2] != spec[3]
                or not isinstance(approved[8], str) or len(approved[8]) != 64):
            reasons.append("package_runtime_identity_mismatch")
        staged = connection.execute(
            "SELECT canonical_question_id,question_text,max_marks_milli,question_type,"
            "solution_text,rubric_text,review_required,negative_marks_milli,package_question_id "
            "FROM main.assessment_import_questions WHERE batch_id=?",
            (approved[0],)
        ).fetchall()
        specs = connection.execute(
            "SELECT s.question_id,s.question_type,s.solution_text,s.rubric_text,s.package_question_id "
            "FROM main.assessment_question_specs s "
            "JOIN main.questions q ON q.id=s.question_id "
            "WHERE q.assessment_id=? AND q.deleted_at IS NULL",
            (assessment_id,)
        ).fetchall()
        staged_by_id = {row[0]: row for row in staged}
        specs_by_id = {row[0]: row for row in specs}
        ids = {row[0] for row in canonical}
        if (len(staged) != len(ids) or len(staged_by_id) != len(ids)
                or set(staged_by_id) != ids or len(specs) != len(ids)
                or set(specs_by_id) != ids):
            reasons.append("question_lineage_incomplete")
        else:
            for qid, text, maximum, import_batch_id in canonical:
                old = staged_by_id[qid]
                new = specs_by_id[qid]
                if (import_batch_id != approved[0]
                        or old[1] != text or old[2] != maximum
                        or old[3] not in SUBJECTIVE or new[1] != old[3]
                        or old[4] != new[2] or old[5] != new[3]
                        or not old[8] or old[8] != new[4]
                        or old[6] != 0 or old[7] != 0
                        or not isinstance(old[4], str) or not old[4].strip()
                        or not isinstance(old[5], str) or not old[5].strip()):
                    reasons.append("subjective_snapshot_or_rubric_mismatch")
                    break
                try:
                    # Reviewed structured rubrics are authored against the
                    # immutable PACKAGE question ID, not a newly assigned
                    # canonical SQLite UUID. Never guess by text or ordinal.
                    parse_rubric(new[3], old[8], maximum)
                except (ValueError, TypeError, KeyError):
                    reasons.append("rubric_not_verifiable")
                    break
    except sqlite3.Error:
        reasons.append("schema_or_query_unavailable")
    return _result(reasons, question_count)


def _result(reasons: list[str], question_count: int) -> dict:
    # These results carry no question text, solutions, marks, reviewer names or
    # stable identifiers. A structurally clean import cannot authorize itself.
    unique = sorted(set(reasons))
    return {
        "schema": "anvaya.paper-import-admission-inspection",
        "version": 1,
        "structural_status": "PASS" if not unique else "BLOCKED",
        "issues": unique,
        "question_count": question_count,
        "human_rubric_review": "UNVERIFIABLE",
        "immutable_review_provenance": "UNVERIFIABLE",
        "source_mapping_authority": "UNVERIFIABLE",
        "production_admission": "BLOCKED",
        "self_marks_official_grade_eligible": False,
    }
