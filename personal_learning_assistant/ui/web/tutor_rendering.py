"""Safe rendering helpers for Tutor 2.0 answers."""

from __future__ import annotations

import re

import mistune
from markupsafe import Markup


_CITATION = re.compile(r"\[(S[1-9][0-9]*)\]")
_DISPLAY_MATH = re.compile(r"\\\[(.+?)\\\]", re.DOTALL)
_INLINE_MATH = re.compile(r"\\\((.+?)\\\)")

try:
    _MARKDOWN = mistune.create_markdown(
        escape=True,
        plugins=["strikethrough", "table", "task_lists", "url", "math"],
    )
except Exception:
    _MARKDOWN = mistune.create_markdown(
        escape=True,
        plugins=["strikethrough", "table", "task_lists", "url"],
    )


def render_tutor_markdown(value):
    """Render model Markdown safely while keeping Tutor citations navigable."""
    text = str(value or "").strip()
    if not text:
        return Markup("")

    # Markdown treats \(, \), \[ and \] as escape sequences and strips the
    # backslashes before MathJax sees them. Normalize the common LaTeX
    # delimiter styles to dollar-delimited math before Mistune parses the text.
    text = _DISPLAY_MATH.sub(
        lambda match: "$$\n{}\n$$".format(match.group(1).strip()),
        text,
    )
    text = _INLINE_MATH.sub(
        lambda match: "$" + match.group(1).strip() + "$",
        text,
    )

    rendered = _MARKDOWN(text)
    rendered = _CITATION.sub(
        lambda match: (
            '<a class="tutor-citation" href="#source-{0}" '
            'aria-label="Open source {0}">[{0}]</a>'
        ).format(match.group(1)),
        rendered,
    )
    return Markup(rendered)
