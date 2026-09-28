from __future__ import annotations

import json
import sqlite3

from test_assessment_studio_phase_c import Clock, _app, _database, _service


def _make_structured_fill_question(path):
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE questions SET question_text=? WHERE id='q-num'",
            (
                "Let W = {p in P3 : p(1)=0, p'(1)=0}. Then dim W = ____. "
                "With the ordered basis B=((x-1)^2,(x-1)^3), "
                "[p]_B=(____, ____)^T.",
            ),
        )
        connection.execute(
            "UPDATE assessment_question_specs SET question_type='fill_blank', "
            "answer_json=? WHERE question_id='q-num'",
            (json.dumps({"correct_option_ids": [], "accepted_answers": ["2,(3,-2)"]}),),
        )
        connection.commit()
    finally:
        connection.close()


def test_runner_infers_multiple_fill_fields_without_answer_key_leak(tmp_path):
    path = _database(tmp_path)
    _make_structured_fill_question(path)
    clock = Clock()
    service = _service(path, clock)
    sid = service.start("assessment-1", confirmed=True)["session_id"]

    view = service.runner_view(sid, ordinal=3)
    question = view["question"]

    assert question["question_type"] == "fill_blank"
    assert len(question["fill_fields"]) == 3
    labels = [item["label"] for item in question["fill_fields"]]
    assert any("dim W" in label for label in labels)
    assert all("2,(3,-2)" not in label for label in labels)
    assert "answer_json" not in json.dumps(view)


def test_runner_structured_fill_response_persists_parts_and_reloads_them(tmp_path):
    path = _database(tmp_path)
    _make_structured_fill_question(path)
    clock = Clock()
    service = _service(path, clock)
    sid = service.start("assessment-1", confirmed=True)["session_id"]
    question = service.runner_view(sid, ordinal=3)["question"]

    saved = service.save_response(
        sid,
        question["session_question_id"],
        {"parts": ["2", "3", "-2"], "value": "2,3,-2"},
        mark_for_review=False,
    )
    assert saved["state"] == "answered"

    reloaded = service.runner_view(sid, ordinal=3)["question"]
    assert [item["value"] for item in reloaded["fill_fields"]] == ["2", "3", "-2"]
    assert reloaded["response"]["value"] == "2,3,-2"
    assert reloaded["response"]["parts"] == ["2", "3", "-2"]


def test_structured_fill_evaluation_matches_legacy_accepted_answer(tmp_path):
    from personal_learning_assistant.services.assessment_evaluation_service import (
        AssessmentEvaluationService,
    )

    path = _database(tmp_path)
    _make_structured_fill_question(path)
    clock = Clock()
    runner = _service(path, clock)
    sid = runner.start("assessment-1", confirmed=True)["session_id"]

    for ordinal in (1, 2, 4):
        q = runner.runner_view(sid, ordinal=ordinal)["question"]
        if q["question_type"] == "mcq":
            response = {"selected_option_ids": ["B"]}
        elif q["question_type"] == "msq":
            response = {"selected_option_ids": ["A", "C"]}
        else:
            response = {"text": "Uses LU factorization."}
        runner.save_response(sid, q["session_question_id"], response, mark_for_review=False)

    fill = runner.runner_view(sid, ordinal=3)["question"]
    runner.save_response(
        sid,
        fill["session_question_id"],
        {"parts": ["2", "3", "-2"]},
        mark_for_review=False,
    )
    runner.submit(sid)

    evaluation = AssessmentEvaluationService(path)
    evaluation.create(sid)
    result = evaluation.results(sid)
    fill_result = next(item for item in result["questions"] if item["question_number"] == "3")
    assert fill_result["outcome"] == "correct"
    assert fill_result["awarded_marks_milli"] == 2000


def test_runner_html_uses_math_renderer_structured_fill_and_no_answer_key(tmp_path):
    path = _database(tmp_path)
    _make_structured_fill_question(path)
    clock = Clock()
    service = _service(path, clock)
    sid = service.start("assessment-1", confirmed=True)["session_id"]

    response = _app(path, clock).test_client().get(f"/assessments/sessions/{sid}?q=3")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "assessment_math.js" in html
    assert "data-assessment-math" in html
    assert "data-structured-fill" in html
    assert "data-inline-fill-question" in html
    assert html.count("data-fill-part") == 3
    assert "Enter each answer separately" in html
    assert "placeholder=\"Blank 1\"" in html
    assert "2,(3,-2)" not in html


def test_evaluation_css_formats_options_and_explanations_as_separate_rows():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    css = (
        root / "personal_learning_assistant/ui/web/static/css/assessment_runner_math.css"
    ).read_text(encoding="utf-8")
    assert ".evaluation-option-list" in css
    assert ".evaluation-correct-options li" in css
    assert ".evaluation-explanation-lines" in css
    assert ".evaluation-question-text[data-assessment-math]" in css
    assert "white-space: pre-wrap" in css


def test_palette_css_has_stronger_answered_review_and_current_states():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    css = (root / "personal_learning_assistant/ui/web/static/css/assessment_runner_math.css").read_text(encoding="utf-8")
    assert ".palette-answered" in css
    assert "rgba(45, 156, 148, .62)" in css
    assert ".palette-marked_for_review" in css
    assert "rgba(112, 85, 210, .52)" in css
    assert ".palette-item.is-current" in css
    assert "outline: 3px solid var(--accent)" in css


def test_runner_infers_structured_fields_from_visible_enter_cue(tmp_path):
    path = _database(tmp_path)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE questions SET question_text=? WHERE id='q-num'",
            (
                "For the system to be consistent determine the parameters and nullity. "
                "Enter: k, μ, number of free variables.",
            ),
        )
        connection.execute(
            "UPDATE assessment_question_specs SET question_type='fill_blank', "
            "answer_json=? WHERE question_id='q-num'",
            (json.dumps({"correct_option_ids": [], "accepted_answers": ["2,1,1"]}),),
        )
        connection.commit()
    finally:
        connection.close()

    service = _service(path, Clock())
    sid = service.start("assessment-1", confirmed=True)["session_id"]
    question = service.runner_view(sid, ordinal=3)["question"]

    assert [item["label"] for item in question["fill_fields"]] == [
        "k",
        "μ",
        "number of free variables",
    ]


def test_html_form_fallback_saves_structured_fill_parts(tmp_path):
    path = _database(tmp_path)
    _make_structured_fill_question(path)
    clock = Clock()
    service = _service(path, clock)
    sid = service.start("assessment-1", confirmed=True)["session_id"]
    question = service.runner_view(sid, ordinal=3)["question"]

    client = _app(path, clock).test_client()
    response = client.post(
        f"/assessments/sessions/{sid}/questions/{question['session_question_id']}/action",
        data={
            "action": "save_next",
            "current_ordinal": "3",
            "next_ordinal": "4",
            "fill_parts": ["2", "3", "-2"],
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    reloaded = service.runner_view(sid, ordinal=3)["question"]
    assert reloaded["response"]["parts"] == ["2", "3", "-2"]


def test_incomplete_structured_fill_is_saved_but_not_marked_answered(tmp_path):
    path = _database(tmp_path)
    _make_structured_fill_question(path)
    service = _service(path, Clock())
    sid = service.start("assessment-1", confirmed=True)["session_id"]
    question = service.runner_view(sid, ordinal=3)["question"]

    saved = service.save_response(
        sid,
        question["session_question_id"],
        {"parts": ["2", "", "-2"]},
        mark_for_review=False,
    )
    assert saved["state"] == "not_answered"

    reloaded = service.runner_view(sid, ordinal=3)["question"]
    assert reloaded["response"]["parts"] == ["2", "", "-2"]


def test_underscore_fill_labels_trim_instructional_cues(tmp_path):
    path = _database(tmp_path)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE questions SET question_text=? WHERE id='q-num'",
            ("For consistency k = ___ and μ = ___.",),
        )
        connection.execute(
            "UPDATE assessment_question_specs SET question_type='fill_blank', "
            "answer_json=? WHERE question_id='q-num'",
            (json.dumps({"correct_option_ids": [], "accepted_answers": ["3,3"]}),),
        )
        connection.commit()
    finally:
        connection.close()

    service = _service(path, Clock())
    sid = service.start("assessment-1", confirmed=True)["session_id"]
    question = service.runner_view(sid, ordinal=3)["question"]
    assert [item["label"] for item in question["fill_fields"]] == ["k", "μ"]


def test_single_named_fill_cue_gets_explicit_labeled_box(tmp_path):
    path = _database(tmp_path)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE questions SET question_text=? WHERE id='q-num'",
            ("Compute the determinant. Enter: det(A).",),
        )
        connection.execute(
            "UPDATE assessment_question_specs SET question_type='fill_blank', "
            "answer_json=? WHERE question_id='q-num'",
            (json.dumps({"correct_option_ids": [], "accepted_answers": ["-2"]}),),
        )
        connection.commit()
    finally:
        connection.close()

    service = _service(path, Clock())
    sid = service.start("assessment-1", confirmed=True)["session_id"]
    question = service.runner_view(sid, ordinal=3)["question"]
    assert [field["label"] for field in question["fill_fields"]] == ["det(A)"]
    assert question["fill_segments"] == ()

    html = _app(path, Clock()).test_client().get(
        f"/assessments/sessions/{sid}?q=3"
    ).get_data(as_text=True)
    assert "Blank 1 · det(A)" in html
    assert 'placeholder="Enter blank 1"' in html


def test_single_visible_fill_blank_becomes_inline_answer_field(tmp_path):
    path = _database(tmp_path)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE questions SET question_text=? WHERE id='q-num'",
            ("For A = [[1, 2], [3, 4]], det(A) = ____.",),
        )
        connection.execute(
            "UPDATE assessment_question_specs SET question_type='fill_blank', "
            "answer_json=? WHERE question_id='q-num'",
            (json.dumps({"correct_option_ids": [], "accepted_answers": ["-2"]}),),
        )
        connection.commit()
    finally:
        connection.close()

    service = _service(path, Clock())
    sid = service.start("assessment-1", confirmed=True)["session_id"]
    question = service.runner_view(sid, ordinal=3)["question"]

    assert len(question["fill_fields"]) == 1
    assert len(question["fill_segments"]) == 3
    assert question["fill_segments"][1]["kind"] == "field"

    html = _app(path, Clock()).test_client().get(
        f"/assessments/sessions/{sid}?q=3"
    ).get_data(as_text=True)
    assert "data-inline-fill-question" in html
    assert 'name="fill_parts"' in html
    assert "Answer for the blank" not in html


def test_numerical_visible_blank_becomes_inline_single_value_field(tmp_path):
    path = _database(tmp_path)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "UPDATE questions SET question_text=? WHERE id='q-num'",
            ("If det(A) = -3, compute det(2A) = ____.",),
        )
        connection.execute(
            "UPDATE assessment_question_specs SET question_type='numerical', "
            "answer_json=? WHERE question_id='q-num'",
            (json.dumps({"correct_option_ids": [], "accepted_answers": ["-24"]}),),
        )
        connection.commit()
    finally:
        connection.close()

    service = _service(path, Clock())
    sid = service.start("assessment-1", confirmed=True)["session_id"]
    question = service.runner_view(sid, ordinal=3)["question"]
    assert len(question["numerical_segments"]) == 3
    assert question["numerical_segments"][1]["kind"] == "field"

    html = _app(path, Clock()).test_client().get(
        f"/assessments/sessions/{sid}?q=3"
    ).get_data(as_text=True)
    assert "data-inline-numerical-question" in html
    assert 'name="answer_value"' in html
    assert "Enter the value directly in the highlighted blank" in html


def test_authoring_prompt_documents_ordered_multi_part_fill_inputs():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    prompt = (root / "ANVAYA_ASSESSMENT_PACKAGE_AUTHORING_PROMPT.md").read_text(
        encoding="utf-8"
    )
    assert "Enter: k, μ, number of free variables." in prompt
    assert "accepted answers in that exact same order" in prompt
    assert "literal underscore blanks" in prompt
    assert "det(A) = ____" in prompt
    assert "Every numerical question clearly identifies the single value" in prompt
    assert "Σ_{i=1}^{3} Σ_{j=1}^{3}" in prompt
    assert "E_3 E_2 E_1 A = U" in prompt
    assert "put each equation on its own line" in prompt
    assert "option A, option B, option C" in prompt
    assert "option-wise explanations are written on separate lines" in prompt
