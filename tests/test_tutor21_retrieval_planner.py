from __future__ import annotations

from personal_learning_assistant.domain.retrieval_models import RetrievalHit
from personal_learning_assistant.tutor.retrieval_planner import (
    infer_source_role,
    plan_retrieval_queries,
    rerank_retrieval_hits,
)


def _hit(
    chunk_id,
    *,
    document_id=None,
    score=0.02,
    provider="",
    source_kind="course",
    resource_ids=(),
):
    return RetrievalHit(
        chunk_id=str(chunk_id),
        document_id=str(document_id or ("doc-" + str(chunk_id))),
        text="text {}".format(chunk_id),
        score=float(score),
        lexical_rank=1,
        semantic_rank=None,
        page_number=None,
        locator={
            "source": {
                "provider": provider,
                "kind": source_kind,
            }
        },
        resource_ids=tuple(resource_ids),
        course_ids=("course-1",),
        topic_ids=(),
        providers=(provider,) if provider else (),
    )


def test_query_planner_adds_focus_and_spelling_variant():
    queries = plan_retrieval_queries(
        "Why do we need LU factorisation for solving linear systems?",
        {},
        "explain",
    )

    assert queries[0] == "Why do we need LU factorisation for solving linear systems?"
    assert any("LU factorisation" in query for query in queries[1:])
    assert any("factorization" in query for query in queries)
    assert len(queries) <= 4


def test_quiz_answer_retrieval_starts_with_pending_question_plus_answer():
    state = {
        "pending_question": "Why does linear dependence create redundancy?",
        "unresolved_doubt": "I do not understand why basis needs independence.",
        "last_misconception": "Thinks spanning alone guarantees unique coordinates.",
    }
    queries = plan_retrieval_queries(
        "Because one vector is made from the others.",
        state,
        "quiz_answer",
    )

    assert queries[0].startswith(
        "Why does linear dependence create redundancy?"
    )
    assert "Because one vector is made from the others." in queries[0]
    assert "Why does linear dependence create redundancy?" in queries
    assert len(queries) <= 4


def test_multi_query_consensus_can_beat_single_query_rank_one():
    consensus = _hit("consensus")
    single = _hit("single")
    other = _hit("other")

    ranked = rerank_retrieval_hits(
        (
            (single, consensus),
            (other, consensus),
        ),
        limit=3,
        preferred_source_roles=("course",),
        diversify=False,
    )

    assert ranked[0].chunk_id == "consensus"


def test_retrieval_diversifies_documents_for_broad_tutoring():
    dominant = tuple(
        _hit("a{}".format(index), document_id="doc-a")
        for index in range(1, 6)
    )
    secondary = tuple(
        _hit("b{}".format(index), document_id="doc-b")
        for index in range(1, 4)
    )

    ranked = rerank_retrieval_hits(
        (dominant + secondary,),
        limit=5,
        preferred_source_roles=("course",),
        diversify=True,
    )

    document_ids = [hit.document_id for hit in ranked]
    assert len(ranked) == 5
    assert document_ids.count("doc-a") == 3
    assert document_ids.count("doc-b") == 2


def test_selected_resource_mode_can_remain_concentrated():
    hits = tuple(
        _hit(
            "a{}".format(index),
            document_id="doc-a",
            resource_ids=("resource-1",),
        )
        for index in range(1, 6)
    )

    ranked = rerank_retrieval_hits(
        (hits,),
        limit=5,
        preferred_source_roles=("selected_resource", "course"),
        selected_resource_id="resource-1",
        diversify=False,
    )

    assert len(ranked) == 5
    assert all(hit.document_id == "doc-a" for hit in ranked)
    assert infer_source_role(
        ranked[0],
        selected_resource_id="resource-1",
    ) == "selected_resource"


def test_source_role_inference_recognizes_common_academic_sources():
    professor = _hit(
        "p",
        provider="Professor PPT",
        source_kind="slides",
    )
    note = _hit(
        "n",
        provider="Obsidian",
        source_kind="markdown note",
    )
    external = _hit(
        "e",
        provider="MIT OCW",
        source_kind="video transcript",
    )
    pyq = _hit(
        "q",
        provider="NITK",
        source_kind="previous year question paper",
    )

    assert infer_source_role(professor) == "professor"
    assert infer_source_role(note) == "personal_note"
    assert infer_source_role(external) == "external_course"
    assert infer_source_role(pyq) == "pyq"


def test_query_planner_is_bounded_and_deduplicated():
    state = {
        "pending_question": "What is basis?",
        "unresolved_doubt": "What is basis?",
        "last_misconception": "What is basis?",
    }
    queries = plan_retrieval_queries(
        "What is basis?",
        state,
        "quiz_answer",
    )

    assert 1 <= len(queries) <= 4
    assert len(queries) == len({query.casefold() for query in queries})
