from __future__ import annotations

from markupsafe import Markup

import personal_learning_assistant.services.obsidian_markdown_renderer as renderer_module
from personal_learning_assistant.services.obsidian_markdown_renderer import (
    render_markdown,
)


def test_renderer_supports_required_reading_markdown_and_omits_frontmatter():
    source = """---
assistant_id: 11111111-1111-4111-8111-111111111111
title: Reader Fixture
tags: [study]
---
# Main heading

A **strong** and *emphasized* paragraph with [a link](https://example.com/docs).

- first bullet
- second bullet

1. first step
2. second step

> quoted evidence

Inline `value = 1` appears here.

```python
print("safe")
```

| Field | Value |
| --- | --- |
| Course | UC100N |
"""

    rendered = render_markdown(source)
    html = str(rendered)

    assert isinstance(rendered, Markup)
    assert "assistant_id" not in html
    assert "Reader Fixture" not in html
    assert "<h1>Main heading</h1>" in html
    assert "<strong>strong</strong>" in html
    assert "<em>emphasized</em>" in html
    assert "<ul>" in html and "<ol>" in html
    assert "<blockquote>" in html
    assert '<code>value = 1</code>' in html
    assert '<code class="language-python">' in html
    assert "<table>" in html and "<th>Field</th>" in html
    assert 'href="https://example.com/docs"' in html
    assert source.startswith("---\nassistant_id:")


def test_renderer_escapes_raw_html_and_blocks_harmful_link_protocols():
    source = """# Unsafe

<script>alert("x")</script>
<img src=x onerror=alert(1)>

[script link](javascript:alert(2))
[data link](data:text/html;base64,PHNjcmlwdD4=)
[file link](file:///etc/passwd)
![script image](javascript:alert(3))
"""

    html = str(render_markdown(source))
    lowered = html.casefold()

    assert "<script" not in lowered
    assert "<img src=x" not in lowered
    assert "&lt;script&gt;alert" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "javascript:" not in lowered
    assert "data:text/html" not in lowered
    assert "file:///" not in lowered
    assert "script link" in html
    assert "data link" in html
    assert "file link" in html


def test_renderer_keeps_unclosed_frontmatter_readable_instead_of_dropping_note():
    source = "---\ntitle: Unclosed\n# Still source\n"

    html = str(render_markdown(source))

    assert "title: Unclosed" in html
    assert "Still source" in html


def test_renderer_failure_falls_back_to_escaped_preformatted_source(monkeypatch):
    class BrokenMarkdown:
        def __call__(self, _value):
            raise RuntimeError("parser internals must not escape")

    monkeypatch.setattr(renderer_module, "_MARKDOWN", BrokenMarkdown())

    rendered = renderer_module.render_markdown(
        '<script>alert("fallback")</script>\n**source remains readable**'
    )
    html = str(rendered)

    assert isinstance(rendered, Markup)
    assert html.startswith('<pre class="obsidian-render-fallback">')
    assert "<script" not in html
    assert "&lt;script&gt;alert" in html
    assert "**source remains readable**" in html
