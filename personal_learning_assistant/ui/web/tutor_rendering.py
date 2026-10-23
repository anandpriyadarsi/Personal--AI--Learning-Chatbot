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



# Some real providers write numerical matrices as multiple ASCII bracketed
# rows, e.g. "L = [1 0 0]\n[2 1 0]\n[4 3 1]". Markdown would collapse
# those rows into prose. Convert only bounded numeric rectangular blocks into
# the existing local, escaped TeX matrix renderer. Never parse arbitrary
# provider HTML, identifiers inside cells, or unbounded matrix contents.
_ASCII_ROW = re.compile(
    r"^[ \t]*(?:(?P<label>[A-Za-z][A-Za-z0-9]{0,2})[ \t]*=[ \t]*)?"
    r"\[(?P<cells>[0-9+\-./ \t]+)\][ \t]*$"
)
_ASCII_CELL = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:/\d+)?$")


def _numeric_ascii_row(line):
    match = _ASCII_ROW.fullmatch(str(line))
    if not match:
        return None
    cells = match.group("cells").split()
    if not 2 <= len(cells) <= 8 or not all(_ASCII_CELL.fullmatch(item) for item in cells):
        return None
    return (match.group("label") or "", cells)


def _promote_numeric_ascii_matrices(value):
    lines = str(value).split("\n")
    result = []
    index = 0
    while index < len(lines):
        first = _numeric_ascii_row(lines[index])
        if not first:
            result.append(lines[index])
            index += 1
            continue
        label, cells = first
        matrix = [cells]
        stop = index + 1
        while stop < len(lines) and len(matrix) < 8:
            next_row = _numeric_ascii_row(lines[stop])
            if not next_row or next_row[0] or len(next_row[1]) != len(cells):
                break
            matrix.append(next_row[1])
            stop += 1
        if len(matrix) < 2:
            result.append(lines[index])
            index += 1
            continue
        latex = (
            r"\[\begin{bmatrix}"
            + r"\\".join("&".join(row) for row in matrix)
            + r"\end{bmatrix}\]"
        )
        result.append((label + " = " if label else "") + latex)
        index = stop
    return "\n".join(result)

def render_tutor_markdown(value: object) -> Markup:
    """Convert untrusted tutor Markdown to safely escaped presentation HTML."""
    if value is None:
        return Markup("")
    return Markup(_MARKDOWN(_promote_numeric_ascii_matrices(value)))
