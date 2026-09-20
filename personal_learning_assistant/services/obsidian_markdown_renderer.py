"""Safe server-side Markdown rendering for the Obsidian Reader."""

from __future__ import annotations

from typing import Any

import mistune
from markupsafe import Markup, escape


_MARKDOWN = mistune.create_markdown(
    escape=True,
    hard_wrap=False,
    plugins=["table"],
)


def _reading_body(markdown_text: str) -> str:
    """Omit valid leading frontmatter from reading mode, never from source."""
    text = str(markdown_text or "")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].lstrip("\ufeff").strip() != "---":
        return text

    for index in range(1, len(lines)):
        if lines[index].strip() in ("---", "..."):
            return "".join(lines[index + 1 :]).lstrip("\r\n")
    return text


def render_markdown(markdown_text: str) -> Markup:
    """Return only escaped, parser-generated HTML or an escaped fallback."""
    source = str(markdown_text or "")
    try:
        rendered: Any = _MARKDOWN(_reading_body(source))
        return Markup(str(rendered))
    except Exception:
        return Markup('<pre class="obsidian-render-fallback">{}</pre>').format(
            escape(source)
        )
