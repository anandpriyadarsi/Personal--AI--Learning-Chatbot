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
from personal_learning_assistant.tutor.adaptive_state import load_adaptive_state
from personal_learning_assistant.tutor.correctness import extract_and_verify_math


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
        content = self.responses.pop(0)
        return TutorProviderResponse(
            content=content,
            provider_name="fake-provider",
            provider_model="fake-model",
            request_id="req-{}".format(len(self.requests)),
        )


def _env(tmp_path, responses):
    path = tmp_path / "tutor21_correctness.db"
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
            title="Correctness checks",
        )
    )
    provider = SequenceProvider(responses)
    engine = GroundedTutorService(
        tutor_session_service=sessions,
        retrieval_service=EmptyRetrieval(),
        provider=provider,
    )
    return connection, repository, sessions, session, provider, engine


def test_valid_vector_linear_combination_is_verified_and_marker_is_removed():
    raw = (
        '<!--ANVAYA_MATH {"claims":[{'
        '"type":"vector_linear_combination",'
        '"target":[3,4],'
        '"vectors":[[1,0],[0,1],[1,1]],'
        '"coefficients":[2,3,1]}]}-->\n'
        "Both decompositions reconstruct the same target."
    )

    content, verification = extract_and_verify_math(raw)

    assert content == "Both decompositions reconstruct the same target."
    assert verification.applicable is True
    assert verification.passed is True
    assert verification.checked_claims == 1
    assert verification.issues == ()


def test_false_live_vector_decomposition_is_rejected():
    raw = (
        '<!--ANVAYA_MATH {"claims":[{'
        '"type":"vector_linear_combination",'
        '"target":[3,4],'
        '"vectors":[[1,0],[0,1]],'
        '"coefficients":[2,2]}]}-->\n'
        r"\((3,4)=2(1,0)+2(0,1)\)"
    )

    _content, verification = extract_and_verify_math(raw)

    assert verification.applicable is True
    assert verification.passed is False
    assert verification.checked_claims == 1
    assert "(2, 2)" in verification.issues[0]
    assert "(3, 4)" in verification.issues[0]


def test_matrix_product_and_determinant_are_checked_exactly():
    raw = (
        '<!--ANVAYA_MATH {"claims":['
        '{"type":"matrix_product",'
        '"left":[[1,2],[3,4]],'
        '"right":[[2,0],[1,2]],'
        '"result":[[4,4],[10,8]]},'
        '{"type":"determinant",'
        '"matrix":[[1,2],[3,4]],'
        '"result":-2}'
        ']}-->\n'
        "Verified matrix example."
    )

    content, verification = extract_and_verify_math(raw)

    assert content == "Verified matrix example."
    assert verification.passed is True
    assert verification.checked_claims == 2


def test_incorrect_matrix_product_is_rejected():
    raw = (
        '<!--ANVAYA_MATH {"claims":[{'
        '"type":"matrix_product",'
        '"left":[[1,2],[3,4]],'
        '"right":[[2,0],[1,2]],'
        '"result":[[4,4],[9,8]]'
        '}]}-->\nWrong result.'
    )

    _content, verification = extract_and_verify_math(raw)

    assert verification.passed is False
    assert "matrix product evaluates to" in verification.issues[0]


def test_untrusted_numeric_expression_is_not_evaluated():
    raw = (
        '<!--ANVAYA_MATH {"claims":[{'
        '"type":"determinant",'
        '"matrix":[[1,0],[0,1]],'
        '"result":"__import__(\\"os\\").system(\\"echo unsafe\\")"'
        '}]}-->\nUnsafe metadata.'
    )

    _content, verification = extract_and_verify_math(raw)

    assert verification.passed is False
    assert "malformed" in verification.issues[0]


def test_wrong_math_gets_one_repair_and_only_corrected_answer_is_persisted(tmp_path):
    wrong = (
        '<!--ANVAYA_MATH {"claims":[{'
        '"type":"vector_linear_combination",'
        '"target":[3,4],'
        '"vectors":[[1,0],[0,1]],'
        '"coefficients":[2,2]}]}-->\n'
        "Wrong: (3,4) = 2(1,0) + 2(0,1)."
    )
    repaired = (
        '<!--ANVAYA_MATH {"claims":[{'
        '"type":"vector_linear_combination",'
        '"target":[3,4],'
        '"vectors":[[1,0],[0,1],[1,1]],'
        '"coefficients":[2,3,1]}]}-->\n'
        "Corrected: (3,4) = 2(1,0) + 3(0,1) + (1,1)."
    )
    (
        connection,
        repository,
        sessions,
        session,
        provider,
        engine,
    ) = _env(tmp_path, [wrong, repaired])

    result = engine.answer(
        session.session_id,
        "Give me a numerical example of redundancy.",
    )

    assert len(provider.requests) == 2
    assert provider.requests[1].metadata["correctness_repair"] is True
    assert "Verifier findings:" in provider.requests[1].messages[-1]["content"]
    assert "(2, 2)" in provider.requests[1].messages[-1]["content"]
    assert "Wrong:" not in result.assistant_turn.content
    assert "ANVAYA_MATH" not in result.assistant_turn.content
    assert result.assistant_turn.content.startswith("Corrected:")
    transcript = sessions.transcript(session.session_id)
    assert "Wrong:" not in transcript[-1].content
    state = load_adaptive_state(
        repository.get_session(session.session_id).metadata
    )
    assert state["last_math_verification"] == "repaired"
    assert state["last_math_claims_checked"] == 1
    connection.close()


def test_two_failed_math_attempts_are_blocked_from_student(tmp_path):
    wrong = (
        '<!--ANVAYA_MATH {"claims":[{'
        '"type":"vector_linear_combination",'
        '"target":[3,4],'
        '"vectors":[[1,0],[0,1]],'
        '"coefficients":[2,2]}]}-->\n'
        "Wrong numerical decomposition."
    )
    still_wrong = (
        '<!--ANVAYA_MATH {"claims":[{'
        '"type":"vector_linear_combination",'
        '"target":[3,4],'
        '"vectors":[[1,0],[0,1]],'
        '"coefficients":[1,1]}]}-->\n'
        "Still wrong numerical decomposition."
    )
    (
        connection,
        repository,
        sessions,
        session,
        provider,
        engine,
    ) = _env(tmp_path, [wrong, still_wrong])

    result = engine.answer(
        session.session_id,
        "Show me a worked vector decomposition.",
    )

    assert len(provider.requests) == 2
    assert result.assistant_turn.support_level == "insufficient"
    assert "caught an inconsistency" in result.assistant_turn.content
    transcript = sessions.transcript(session.session_id)
    assert "Wrong numerical" not in transcript[-1].content
    assert "Still wrong" not in transcript[-1].content
    state = load_adaptive_state(
        repository.get_session(session.session_id).metadata
    )
    assert state["last_math_verification"] == "blocked"
    assert state["last_teaching_move"] == "correctness_block"
    connection.close()


def test_quiz_evaluation_and_math_verification_can_coexist(tmp_path):
    first = "Question 1\n\nGive one redundant vector example in R2?"
    second = (
        '<!--ANVAYA_EVAL {"status":"correct",'
        '"reason":"Correct dependent-vector relation.",'
        '"misconception":""}-->\n'
        '<!--ANVAYA_MATH {"claims":[{'
        '"type":"vector_linear_combination",'
        '"target":[1,1],'
        '"vectors":[[1,0],[0,1]],'
        '"coefficients":[1,1]}]}-->\n'
        "Correct. The relation is numerically valid.\n\n"
        "Question 2\n\nWhy does that relation imply redundancy?"
    )
    (
        connection,
        repository,
        sessions,
        session,
        provider,
        engine,
    ) = _env(tmp_path, [first, second])

    engine.answer(session.session_id, "Quiz me one question at a time.")
    result = engine.answer(
        session.session_id,
        "Use v1=(1,0), v2=(0,1), and v3=(1,1).",
    )

    assert len(provider.requests) == 2
    assert "ANVAYA_EVAL" not in result.assistant_turn.content
    assert "ANVAYA_MATH" not in result.assistant_turn.content
    state = load_adaptive_state(
        repository.get_session(session.session_id).metadata
    )
    assert state["answer_status"] == "correct"
    assert "ANVAYA_" not in sessions.transcript(session.session_id)[-1].content
    connection.close()



def test_tutor_system_prompt_contains_deterministic_math_protocol():
    from personal_learning_assistant.tutor.grounding import _system_prompt

    prompt = _system_prompt(
        mode="doubt",
        source_policy="source_first",
        purpose="Diagnose a specific confusion without skipping prerequisites.",
        preferred_source_roles=("professor", "course", "personal_note"),
    )

    assert "DETERMINISTIC MATH VERIFICATION" in prompt
    assert "vector_linear_combination" in prompt
    assert "matrix_product" in prompt
    assert "determinant" in prompt
    assert "ANVAYA_MATH" in prompt



def test_system_prompt_formats_literal_correctness_json_without_keyerror():
    from personal_learning_assistant.tutor.correctness import correctness_protocol
    from personal_learning_assistant.tutor.grounding import _system_prompt

    protocol = correctness_protocol()
    assert '<!--ANVAYA_MATH {"claims":[...]}-->' in protocol

    prompt = _system_prompt(
        mode="concept",
        source_policy="source_first",
        purpose="Teach clearly.",
        preferred_source_roles=("course",),
    )

    assert '<!--ANVAYA_MATH {"claims":[...]}-->' in prompt
    assert '{"type":"vector_linear_combination"' in prompt
    assert '{"type":"matrix_product"' in prompt
    assert '{"type":"determinant"' in prompt
