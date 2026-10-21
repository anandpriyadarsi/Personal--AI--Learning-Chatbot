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
