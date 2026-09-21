"""Deterministic read-only retrieval quality benchmark harness."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalBenchmarkCase:
    query: str
    expected_document_ids: tuple[str, ...] = ()
    expected_course_ids: tuple[str, ...] = ()
    top_k: int = 5


def run_retrieval_benchmark(runtime, cases):
    rows = []
    passed = 0
    total = 0
    for case in tuple(cases):
        total += 1
        hits = tuple(runtime.search(case.query, top_k=case.top_k))
        document_ids = tuple(str(hit.document_id) for hit in hits)
        course_ids = {
            str(course_id)
            for hit in hits
            for course_id in tuple(hit.course_ids or ())
        }
        expected_documents = set(case.expected_document_ids)
        expected_courses = set(case.expected_course_ids)
        document_ok = (
            True
            if not expected_documents
            else bool(expected_documents.intersection(document_ids))
        )
        course_ok = (
            True
            if not expected_courses
            else bool(expected_courses.intersection(course_ids))
        )
        ok = document_ok and course_ok
        if ok:
            passed += 1
        rows.append(
            {
                "query": case.query,
                "passed": ok,
                "returned_document_ids": document_ids,
                "expected_document_ids": tuple(case.expected_document_ids),
                "expected_course_ids": tuple(case.expected_course_ids),
            }
        )
    return {
        "passed": passed,
        "total": total,
        "pass_rate": 1.0 if total == 0 else passed / total,
        "cases": tuple(rows),
    }
