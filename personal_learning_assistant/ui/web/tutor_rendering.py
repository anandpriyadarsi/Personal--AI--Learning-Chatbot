"""Safe, local Markdown rendering for Tutor assistant turns.

Reconciled from the historical Tutor 2.0 renderer against the current UI.
Only assistant messages are rendered; student input remains auto-escaped.
Source labels stay plain text until the evidence mapping is verified.
"""

from __future__ import annotations

import mistune
from markupsafe import Markup

_MARKDOWN = mistune.create_markdown(
    escape=True,
    plugins=["strikethrough", "table"],
)


def render_tutor_markdown(value: object) -> Markup:
    """Convert untrusted tutor Markdown to safely escaped presentation HTML."""
    if value is None:
        return Markup("")
    return Markup(_MARKDOWN(str(value)))
