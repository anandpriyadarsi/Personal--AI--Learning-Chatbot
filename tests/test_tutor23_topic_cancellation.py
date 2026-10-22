"""Explicit cancellation must not become a request to repeat cancelled work."""
import pytest

from personal_learning_assistant.tutor.adaptive_state import (
    contextualize_adaptive_state, resolve_adaptive_intent,
)
from personal_learning_assistant.tutor.session_goal import (
    SESSION_GOAL_KEY, resolve_session_goal,
)

PENDING = {
    "awaiting_student_answer": True, "pending_question_kind": "practice",
    "pending_question": "What multiplier eliminates 6 below pivot 2?",
    "practice_active": True, "practice_level": 4, "practice_format": "computational",
    "last_misconception": "Reverses the LU elimination multiplier",
    "unresolved_doubt": "Cannot construct L", "practice_step_count": 2,
}


@pytest.mark.parametrize("question, intent, subject", [
    ("Skip the practice question. Now explain determinant expansion by cofactors. Do not continue LU.", "explain", "determinant"),
    ("Cancel the quiz. Instead explain basis. Don't continue LU.", "explain", "basis"),
    ("Skip the hint; now give me one computational practice problem on determinants.", "practice", "determinants"),
    ("Skip the practice question and show one example of cofactor expansion.", "example", "cofactor"),
])
def test_cancelled_task_does_not_override_new_teaching_request(question, intent, subject):
    decision = resolve_adaptive_intent(question, PENDING)
    assert decision.name == intent
    goal = resolve_session_goal(question, {
        SESSION_GOAL_KEY: {"goal": "Practice LU elimination multipliers", "status": "active"},
    }, teaching_intent=decision.name)
    assert goal["source"] == "topic_shift"
    assert subject in goal["goal"].lower()
    assert "LU" not in goal["goal"]
    state = contextualize_adaptive_state(question, PENDING)
    assert state["pending_question"] == state["pending_question_kind"] == ""
    assert state["last_misconception"] == state["unresolved_doubt"] == ""
    assert state["practice_level"] == state["practice_step_count"] == 0
    assert not state["practice_active"]


@pytest.mark.parametrize("question, intent", [
    ("Give me one hint only. Keep the question for me to answer.", "hint"),
    ("Give me a harder computational practice problem. One problem only.", "practice"),
    ("Explain why we skip the zero pivot in this practice example.", "example"),
])
def test_cancel_words_inside_academic_request_do_not_strip_it(question, intent):
    assert resolve_adaptive_intent(question, PENDING).name == intent


@pytest.mark.parametrize("question", [
    "Do not cancel the question. My answer is 3.",
    "Don't stop the question. My answer is 3.",
    "Do not skip the question. My answer is 3.",
])
def test_negated_cancellation_preserves_pending_answer_lineage(question):
    assert resolve_adaptive_intent(question, PENDING).name == "quiz_answer"
    state = contextualize_adaptive_state(question, PENDING)
    assert state["pending_question"] == PENDING["pending_question"]
    assert state["awaiting_student_answer"]


def test_cancel_question_on_same_topic_preserves_relevant_gap_and_level():
    question = "Skip the practice question and explain elimination multipliers in LU factorization."
    assert resolve_adaptive_intent(question, PENDING).name == "explain"
    state = contextualize_adaptive_state(question, PENDING)
    assert state["pending_question"] == ""
    assert not state["practice_active"]
    assert state["last_misconception"] == PENDING["last_misconception"]
    assert state["unresolved_doubt"] == PENDING["unresolved_doubt"]
    assert state["practice_level"] == PENDING["practice_level"]
