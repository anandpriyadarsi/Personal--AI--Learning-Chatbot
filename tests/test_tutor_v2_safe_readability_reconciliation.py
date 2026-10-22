"""Safe subset of legacy Tutor V2.0 integration; no provider or installed DB."""

from __future__ import annotations

from personal_learning_assistant.ui.web.tutor_rendering import render_tutor_markdown


def test_assistant_markdown_heading_lists_and_tables():
    result = str(render_tutor_markdown(
        "## Concept\n\n**Key idea**\n\n- first\n- second\n\n| A | B |\n|---|---|\n| x | y |"
    ))
    assert "<h2>Concept</h2>" in result
    assert "<strong>Key idea</strong>" in result
    assert "<li>first</li>" in result
    assert "<table>" in result


def test_untrusted_html_is_escaped_and_not_promoted_to_dom():
    result = str(render_tutor_markdown("<script>alert('x')</script>\n\n<img src=x onerror=alert(1)>"))
    assert "<script>" not in result
    assert "<img " not in result
    assert "&lt;script&gt;" in result
    assert "&lt;img" in result


def test_literal_citation_labels_remain_unlinked_without_verified_mapping():
    result = str(render_tutor_markdown("According to [S1], see source."))
    assert "[S1]" in result
    assert 'href="#source-S1"' not in result




def test_ascii_lu_matrices_render_as_safe_structured_math():
    response = (
        "A = [2 1 1]\n [4 3 3]\n [8 7 9]\n\n"
        "L = [1 0 0]\n[2 1 0]\n[4 3 1]\n\n"
        "U = [2 1 1]\n[0 1 1]\n[0 0 2]\n"
    )
    result = str(render_tutor_markdown(response))
    assert result.count('data-assessment-math') == 3
    assert result.count(r"\begin{bmatrix}") == 3
    assert r"1&0&0\\2&1&0\\4&3&1" in result


def test_ascii_matrix_promotion_rejects_untrusted_html_and_ragged_rows():
    text = (
        "[1 0]\n[0 1]\n"
        "<img src=x onerror=alert(1)>\n"
        "[1 0 2]\n[0 1]\n"
    )
    result = str(render_tutor_markdown(text))
    assert result.count('data-assessment-math') == 1
    assert "<img " not in result
    assert "&lt;img" in result

def test_empty_response_is_safe():
    assert str(render_tutor_markdown(None)) == ""
    assert str(render_tutor_markdown("")) == ""


def test_student_messages_are_not_parsed_as_markdown_in_session_template():
    from pathlib import Path
    template = (
        Path(__file__).resolve().parents[1]
        / "personal_learning_assistant/ui/web/templates/agent_session.html"
    ).read_text(encoding="utf-8")
    assert "turn.content|tutor_markdown" in template
    assert "{{ turn.content }}" in template
    assert "{% if turn.role == 'assistant' %}" in template


def test_flask_jinja_filter_registration_and_escaping():
    from flask import render_template_string
    from personal_learning_assistant.ui.web import create_app

    app = create_app({"TESTING": True})
    with app.app_context():
        result = render_template_string(
            '{{ answer|tutor_markdown }}',
            answer="**Important** <script>bad()</script>",
        )
    assert "<strong>Important</strong>" in result
    assert "<script>" not in result
    assert "&lt;script&gt;" in result
