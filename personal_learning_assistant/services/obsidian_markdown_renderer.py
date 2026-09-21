"""Safe server-side Markdown rendering for the Obsidian Reader."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

import mistune
from markupsafe import Markup, escape


_MARKDOWN = mistune.create_markdown(
    escape=True,
    hard_wrap=False,
    plugins=["table"],
)
_WIKILINK = re.compile(r"(?<!!)\[\[([^\[\]\r\n]+)\]\]")


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


def _markdown_label(value: str) -> str:
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def _activate_wikilinks(source: str, wikilinks=()) -> str:
    resolved = {
        str(item.get("raw") or ""): item
        for item in tuple(wikilinks or ())
        if str(item.get("resolved_path") or "").strip()
    }

    def replace(match):
        raw = str(match.group(1) or "")
        item = resolved.get(raw)
        if item is None:
            return match.group(0)
        label = _markdown_label(item.get("label") or raw)
        target = "/obsidian/note?path={}".format(
            quote(str(item["resolved_path"]), safe="")
        )
        return "[{}]({})".format(label, target)

    return _WIKILINK.sub(replace, str(source or ""))


def render_markdown(markdown_text: str, *, wikilinks=()) -> Markup:
    """Return escaped parser-generated HTML with safe resolved Obsidian links."""
    source = _activate_wikilinks(
        _reading_body(str(markdown_text or "")),
        wikilinks=wikilinks,
    )
    try:
        rendered: Any = _MARKDOWN(source)
        return Markup(str(rendered))
    except Exception:
        return Markup('<pre class="obsidian-render-fallback">{}</pre>').format(
            escape(str(markdown_text or ""))
        )
