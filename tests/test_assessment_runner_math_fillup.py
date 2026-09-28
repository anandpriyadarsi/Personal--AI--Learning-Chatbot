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


def test_runner_template_and_form_fallback_keep_structured_fill_contract():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    template = (
        root
        / "personal_learning_assistant/ui/web/templates/assessment_test_runner.html"
    ).read_text(encoding="utf-8")
    routes = (
        root / "personal_learning_assistant/ui/web/routes.py"
    ).read_text(encoding="utf-8")

    assert "assessment_runner_math.css" in template
    assert "assessment_math.js" in template
    assert "data-assessment-math" in template
    assert 'name="fill_parts"' in template
    assert "data-fill-part" in template
    assert 'request.form.getlist("fill_parts")' in routes


def test_math_renderer_uses_dom_text_nodes_not_inner_html():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    script = (
        root
        / "personal_learning_assistant/ui/web/static/js/assessment_math.js"
    ).read_text(encoding="utf-8")

    assert "createTextNode" in script
    assert "textContent" in script
    assert "innerHTML" not in script
    assert "eval(" not in script


def test_palette_styles_make_attempt_states_visually_distinct():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    css = (
        root
        / "personal_learning_assistant/ui/web/static/css/assessment_runner_math.css"
    ).read_text(encoding="utf-8")

    for state in (
        "answered",
        "not_answered",
        "not_visited",
        "marked_for_review",
        "answered_marked_for_review",
    ):
        assert f".palette-{state}" in css

    assert ".palette-item.is-current" in css
    assert "outline: 3px solid var(--accent)" in css


def test_authoring_prompt_documents_multi_part_fill_contract():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    prompt = (root / "ANVAYA_ASSESSMENT_PACKAGE_AUTHORING_PROMPT.md").read_text(
        encoding="utf-8"
    )

    assert "fill_blank" in prompt
    assert "Enter: k, μ, number of free variables." in prompt
    assert "accepted answers in that exact same order" in prompt
