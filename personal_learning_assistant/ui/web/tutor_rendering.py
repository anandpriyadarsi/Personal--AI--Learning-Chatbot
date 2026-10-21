"""Safe, local Markdown rendering for Tutor assistant turns.

Reconciled from the historical Tutor 2.0 renderer against the current UI.
Only assistant messages are rendered; student input remains auto-escaped.
Source labels stay plain text until the evidence mapping is verified.
"""

from __future__ import annotations

import mistune
import re
from markupsafe import Markup, escape


class _TutorRenderer(mistune.HTMLRenderer):
    def image(self, text, url, title=None):
        # Provider-authored URLs must not initiate automatic network requests
        # or read local files. Original academic source previews have their
        # own verified reader; arbitrary Markdown images remain inert text.
        return '<span class="tutor-image-placeholder">' + str(escape(text or 'Image')) + ' (image not loaded)</span>'

    @staticmethod
    def _text(text):
        # TeX uses exactly one unbraced token for an index/exponent. The
        # shared plain-text renderer also supports longer legacy indices, so
        # make Tutor's explicit TeX grouping unambiguous before using it.
        text = re.sub(r'([_^])([A-Za-z0-9])', r'\1{\2}', text)
        return str(escape(text))

    def inline_math(self, text):
        return '<span data-assessment-math role="math">' + self._text(text) + '</span>'

    def block_math(self, text):
        return '<span class="tutor-display-math" data-assessment-math role="math">' + self._text(text) + '</span>\n'


def _slash_math(md):
    """Preserve provider LaTeX before Markdown consumes its backslashes.

    Code spans/fences still use Markdown. Math is escaped text for the
    existing bounded local DOM renderer, never executable HTML.
    """
    def parse(inline, match, state):
        block = match.group('tutor_block_math')
        state.append_token({
            'type': 'block_math' if block is not None else 'inline_math',
            'raw': block if block is not None else match.group('tutor_inline_math'),
        })
        return match.end()
    md.inline.register('tutor_slash_math',
        r'\\\((?P<tutor_inline_math>[\s\S]*?)\\\)|\\\[(?P<tutor_block_math>[\s\S]*?)\\\]',
        parse, before='escape')

_MARKDOWN = mistune.create_markdown(
    renderer=_TutorRenderer(escape=True),
    plugins=["strikethrough", "table", "math", _slash_math],
)


def render_tutor_markdown(value: object) -> Markup:
    """Convert untrusted tutor Markdown to safely escaped presentation HTML."""
    if value is None:
        return Markup("")
    return Markup(_MARKDOWN(str(value)))
