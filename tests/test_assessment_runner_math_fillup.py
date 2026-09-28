from __future__ import annotations

import json

from personal_learning_assistant.services.assessment_evaluation_service import (
    _deterministic_score,
)
from personal_learning_assistant.services.assessment_runner_service import (
    AssessmentRunnerService,
    _fill_blank_fields,
    _split_legacy_fill_value,
)


def _fill_question():
    return {
        "question_type": "fill_blank",
        "options_json": "[]",
    }


def _score_question(*, response, accepted):
    return {
        "question_type": "fill_blank",
        "scoring_policy": "standard",
        "max_marks_milli": 2000,
        "negative_marks_milli": 0,
        "response_json": json.dumps(response),
        "answer_key_json": json.dumps({"accepted_answers": accepted}),
    }


def test_enter_cue_becomes_structured_fill_fields():
    fields = _fill_blank_fields(
        "For the system to be consistent, enter: k, μ, number of free variables."
    )
    assert [item["label"] for item in fields] == [
        "k",
        "μ",
        "number of free variables",
    ]


def test_enter_cue_without_colon_supports_subscript_like_labels():
    fields = _fill_blank_fields(
        "Using Doolittle factorization, enter ℓ43, u44."
    )
    assert [item["label"] for item in fields] == ["ℓ43", "u44"]


def test_single_enter_value_stays_legacy_single_input():
    assert _fill_blank_fields("Enter the determinant.") == ()


def test_visible_underscore_blanks_remain_supported():
    fields = _fill_blank_fields(
        "For consistency k = ___ and μ = ___."
    )
    assert len(fields) == 2
    assert fields[0]["label"] == "k"
    assert fields[1]["label"] == "μ"


def test_structured_fill_response_requires_all_parts_for_answered_state():
    response, answered = AssessmentRunnerService._normalize_response(
        _fill_question(),
        {"parts": ["3", "", "2"]},
    )
    assert response == {"value": "3,,2", "parts": ["3", "", "2"]}
    assert answered is False

    complete, complete_answered = AssessmentRunnerService._normalize_response(
        _fill_question(),
        {"parts": ["3", "3", "2"]},
    )
    assert complete == {"value": "3,3,2", "parts": ["3", "3", "2"]}
    assert complete_answered is True


def test_legacy_fill_string_can_be_redisplayed_in_structured_fields():
    assert _split_legacy_fill_value("(3, 3, 2)", 3) == ("3", "3", "2")
    assert _split_legacy_fill_value("4; 4", 2) == ("4", "4")


def test_structured_fill_evaluation_matches_legacy_accepted_answer_formats():
    result = _deterministic_score(
        _score_question(
            response={"value": "3,3,2", "parts": ["3", "3", "2"]},
            accepted=["3, 3, 2", "(3,3,2)"],
        )
    )
    assert result["status"] == "auto_confirmed"
    assert result["outcome"] == "correct"
    assert result["awarded_marks_milli"] == 2000


def test_structured_fill_evaluation_supports_semicolon_tuple_legacy_format():
    result = _deterministic_score(
        _score_question(
            response={"value": "2,2,3", "parts": ["2", "2", "3"]},
            accepted=["2; 2, 3", "2; (2, 3)"],
        )
    )
    assert result["outcome"] == "correct"


def test_incomplete_structured_fill_is_not_scored_as_blank_if_submitted_directly():
    result = _deterministic_score(
        _score_question(
            response={"value": "3,,2", "parts": ["3", "", "2"]},
            accepted=["3, 3, 2"],
        )
    )
    assert result["outcome"] == "incorrect"
