import json
import pytest
from personal_learning_assistant.domain import assessment_self_evaluation as domain


def rubric():
    def step(key, maximum, prereq=(), group=None):
        return dict(
            id=key,
            label=key,
            expected_work="Show working",
            max_marks_milli=maximum,
            prerequisites=list(prereq),
            award_when=["Correct method"],
            do_not_award_when=["Unsupported"],
            allowed_awards_milli=list(range(0, maximum + 1, 500)),
            alternative_group=group,
        )

    return dict(
        schema="anvaya.subjective-rubric",
        version=1,
        question_id="q",
        total_marks_milli=3000,
        grading_increment_milli=500,
        steps=[
            step("a", 1000),
            step("b", 2000, ["a"], "method"),
            step("c", 2000, ["a"], "method"),
        ],
        common_mistakes=["Sign error"],
        review_required=False,
    )


def test_plain_rubric_does_not_invent_step_marks():
    parsed = domain.parse_rubric("Method and final answer", "q", 3000)
    assert parsed["kind"] == "per_question" and "steps" not in parsed
    assert domain.mark_rubric(parsed, {"marks": "1.5"}) == 1500


def test_decimal_bounds_and_alternative_steps():
    parsed = domain.parse_rubric(json.dumps(rubric()), "q", 3000)
    assert (
        domain.mark_rubric(parsed, {"steps": {"a": "1", "b": "1.5", "c": "0"}}) == 2500
    )
    for awards in (
        {"a": "0", "b": "2", "c": "0"},
        {"a": "1", "b": "2", "c": "2"},
        {"a": "1", "b": "0.7", "c": "0"},
    ):
        with pytest.raises(ValueError):
            domain.mark_rubric(parsed, {"steps": awards})


@pytest.mark.parametrize(
    "value", [True, "NaN", "Infinity", "-1", "3.001", "1.0001", None, {}, ""]
)
def test_invalid_decimal_marks(value):
    parsed = domain.parse_rubric("Reviewed prose", "q", 3000)
    with pytest.raises(ValueError):
        domain.mark_rubric(parsed, {"marks": value})


@pytest.mark.parametrize(
    "change",
    [
        "cycle",
        "unknown",
        "total",
        "bool",
        "extra",
        "review",
        "identity",
        "duplicate",
        "malformed",
    ],
)
def test_bad_structured_rubric_needs_review(change):
    data = rubric()
    if change == "cycle":
        data["steps"][0]["prerequisites"] = ["b"]
    if change == "unknown":
        data["steps"][0]["prerequisites"] = ["missing"]
    if change == "total":
        data["total_marks_milli"] = 4000
    if change == "bool":
        data["steps"][0]["max_marks_milli"] = True
    if change == "extra":
        data["url"] = "https://example.invalid"
    if change == "review":
        data["review_required"] = True
    if change == "identity":
        data["question_id"] = "other"
    if change == "duplicate":
        data["steps"][1]["id"] = "a"
    text = '{"schema":' if change == "malformed" else json.dumps(data)
    with pytest.raises(ValueError):
        domain.parse_rubric(text, "q", 3000)


def test_alternative_method_prerequisite_cannot_require_competing_method():
    data = rubric()
    data["steps"][1]["prerequisites"] = ["c"]
    with pytest.raises(ValueError):
        domain.parse_rubric(json.dumps(data), "q", 3000)


def test_dependency_closure_cannot_require_both_alternative_methods():
    data = rubric()
    data["steps"][0]["prerequisites"] = ["b", "c"]
    data["steps"][1]["prerequisites"] = []
    data["steps"][2]["prerequisites"] = []
    with pytest.raises(ValueError):
        domain.parse_rubric(json.dumps(data), "q", 3000)
