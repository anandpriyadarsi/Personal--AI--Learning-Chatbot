from __future__ import annotations

import sqlite3

from personal_learning_assistant.domain.tutor_models import (
    TutorProviderResponse,
    TutorSessionSpec,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import (
    apply_migrations,
)
from personal_learning_assistant.repositories.sqlite.tutor_repository import (
    SQLiteTutorRepository,
)
from personal_learning_assistant.services.grounded_tutor_service import (
    GroundedTutorService,
)
from personal_learning_assistant.services.tutor_session_service import (
    TutorSessionService,
)
from personal_learning_assistant.tutor.adaptive_state import (
    contextualize_adaptive_state,
    is_explicit_topic_shift,
    resolve_adaptive_intent,
)
from personal_learning_assistant.tutor.correctness import (
    extract_and_verify_math,
    required_claim_types,
    requires_deterministic_math,
)
from personal_learning_assistant.tutor.intent import classify_tutor_intent


class EmptyRetrieval:
    def search(self, *args, **kwargs):
        return ()


class SequenceProvider:
    configured = True

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("unexpected provider call")
        return TutorProviderResponse(
            content=self.responses.pop(0),
            provider_name="fake-provider",
            provider_model="fake-model",
            request_id="req-{}".format(len(self.requests)),
        )


def _env(tmp_path, responses):
    path = tmp_path / "tutor21_livefix.db"
    apply_migrations(path)
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    repository = SQLiteTutorRepository(connection)
    sessions = TutorSessionService(repository)
    session = sessions.create_session(
        TutorSessionSpec(
            mode="doubt",
            source_policy="source_first",
            title="Live validation fixes",
        )
    )
    provider = SequenceProvider(responses)
    engine = GroundedTutorService(
        tutor_session_service=sessions,
        retrieval_service=EmptyRetrieval(),
        provider=provider,
    )
    return connection, repository, sessions, session, provider, engine


def test_explicit_new_lu_topic_drops_stale_redundancy_state():
    state = {
        "quiz_active": True,
        "awaiting_student_answer": True,
        "pending_question": "Why does linear dependence create redundancy?",
        "unresolved_doubt": (
            "I still do not understand why redundancy is a problem in a basis."
        ),
        "last_misconception": "Thinks spanning alone guarantees unique coordinates.",
    }
    question = (
        "Now explain LU factorization again, but focus only on why it is useful "
        "when solving several systems with the same coefficient matrix."
    )

    assert is_explicit_topic_shift(question, state) is True
    contextual = contextualize_adaptive_state(question, state)
    assert contextual["quiz_active"] is False
    assert contextual["awaiting_student_answer"] is False
    assert contextual["pending_question"] == ""
    assert contextual["unresolved_doubt"] == ""
    assert contextual["last_misconception"] == ""
    assert resolve_adaptive_intent(question, state).name == "explain"


def test_explain_it_differently_keeps_same_unresolved_topic():
    state = {
        "unresolved_doubt": "I do not understand why redundancy breaks uniqueness."
    }
    assert is_explicit_topic_shift("Explain it differently.", state) is False
    contextual = contextualize_adaptive_state("Explain it differently.", state)
    assert "redundancy" in contextual["unresolved_doubt"]


def test_reference_to_example_just_given_has_followup_intent():
    intent = classify_tutor_intent(
        "In the LU example you just gave, which elimination multipliers "
        "became entries of L, and why?"
    )
    assert intent.name == "follow_up_reference"
    assert "exact numerical objects" in intent.instruction
    assert "Do not substitute" in intent.instruction


def test_live_bad_three_by_three_lu_claim_is_rejected():
    raw = (
        '<!--ANVAYA_MATH {"claims":[{'
        '"type":"matrix_product",'
        '"left":[[1,0,0],["1/2",1,0],["1/2",0,1]],'
        '"right":[[2,1,1],[0,"3/2","1/2"],[0,0,"4/3"]],'
        '"result":[[2,1,1],[1,2,1],[1,1,2]]'
        '}]}-->\n'
        "Claimed LU=A."
    )
    _content, verification = extract_and_verify_math(raw)
    assert verification.applicable is True
    assert verification.passed is False
    assert "matrix product evaluates to" in verification.issues[0]


def test_explicit_lu_compute_requires_matrix_product_claim():
    question = (
        "Take a simple 3x3 matrix, compute its LU factorisation step by step, "
        "and verify that LU=A before showing the final result."
    )
    assert requires_deterministic_math(question) is True
    assert required_claim_types(question) == ("matrix_product",)


def test_missing_math_marker_for_explicit_lu_compute_gets_one_repair(tmp_path):
    first = (
        "Take A=[[2,1],[4,3]]. I get L=[[1,0],[2,1]] and "
        "U=[[2,1],[0,1]], so LU=A."
    )
    repaired = (
        '<!--ANVAYA_MATH {"claims":[{'
        '"type":"matrix_product",'
        '"left":[[1,0],[2,1]],'
        '"right":[[2,1],[0,1]],'
        '"result":[[2,1],[4,3]]'
        '}]}-->\n'
        "For this example, the verified factors are "
        "L=[[1,0],[2,1]] and U=[[2,1],[0,1]]."
    )
    connection, _repo, sessions, session, provider, engine = _env(
        tmp_path,
        [first, repaired],
    )

    result = engine.answer(
        session.session_id,
        "Take a simple 2x2 matrix, compute its LU factorisation step by step, "
        "and verify that LU=A.",
    )

    assert len(provider.requests) == 2
    assert provider.requests[1].metadata["correctness_repair"] is True
    assert "machine-checkable math claims" in provider.requests[1].messages[-1]["content"]
    assert "ANVAYA_MATH" not in result.assistant_turn.content
    assert result.assistant_turn.content.startswith("For this example")
    assert "L=[[1,0],[2,1]]" in sessions.transcript(session.session_id)[-1].content
    connection.close()


def test_wrong_claim_type_for_lu_compute_is_repaired(tmp_path):
    first = (
        '<!--ANVAYA_MATH {"claims":[{'
        '"type":"determinant","matrix":[[1,0],[0,1]],"result":1'
        '}]}-->\n'
        "Here is my LU result."
    )
    repaired = (
        '<!--ANVAYA_MATH {"claims":[{'
        '"type":"matrix_product",'
        '"left":[[1,0],[2,1]],'
        '"right":[[2,1],[0,1]],'
        '"result":[[2,1],[4,3]]'
        '}]}-->\n'
        "Here is the verified LU result."
    )
    connection, _repo, _sessions, session, provider, engine = _env(
        tmp_path,
        [first, repaired],
    )

    result = engine.answer(
        session.session_id,
        "Compute the LU factorisation of a simple matrix and verify LU=A.",
    )

    assert len(provider.requests) == 2
    assert "required verification claim type(s) missing: matrix_product" in (
        provider.requests[1].messages[-1]["content"]
    )
    assert result.assistant_turn.content == "Here is the verified LU result."
    connection.close()


def test_provider_safety_metadata_only_is_retried_not_displayed(tmp_path):
    connection, _repo, sessions, session, provider, engine = _env(
        tmp_path,
        [
            "User Safety: safe\nResponse Safety: safe",
            "LU factorization stores Gaussian-elimination multipliers in L.",
        ],
    )

    result = engine.answer(
        session.session_id,
        "Why is LU factorization related to Gaussian elimination?",
    )

    assert len(provider.requests) == 2
    assert provider.requests[1].metadata["provider_output_retry"] is True
    assert "safety" not in result.assistant_turn.content.casefold()
    assert "Gaussian-elimination multipliers" in result.assistant_turn.content
    assert "Safety:" not in sessions.transcript(session.session_id)[-1].content
    connection.close()


def test_repeated_provider_safety_metadata_fails_closed_without_500(tmp_path):
    connection, _repo, _sessions, session, provider, engine = _env(
        tmp_path,
        [
            "User Safety: safe\nResponse Safety: safe",
            "User Safety: safe\nResponse Safety: safe",
        ],
    )

    result = engine.answer(
        session.session_id,
        "Explain LU factorization.",
    )

    assert len(provider.requests) == 2
    assert result.assistant_turn.support_level == "insufficient"
    assert "did not return an academic answer" in result.assistant_turn.content
    connection.close()
