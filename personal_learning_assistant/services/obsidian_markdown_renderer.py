"""Safe server-side Markdown rendering for Obsidian and Notes Studio readers."""
from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import mistune
from markupsafe import Markup, escape


_MARKDOWN = mistune.create_markdown(
    escape=True,
    hard_wrap=False,
    plugins=["table"],
)
_WIKILINK = re.compile(r"(?<!!)\[\[([^\[\]\r\n]+)\]\]")
_OBSIDIAN_IMAGE = re.compile(r"(?m)^!\[\[([^\[\]\r\n]+)\]\]\s*$")
_MARKDOWN_IMAGE = re.compile(r"(?m)^!\[([^\]\r\n]*)\]\(([^\r\n]*)\)\s*$")
_RICH_FENCE = re.compile(
    r"(?ms)^(?P<fence>\x60{3,}|~{3,})(?P<kind>flowchart|diagram|concept-map)\s*\n"
    r"(?P<body>.*?)^(?P=fence)\s*$"
)
_CODE_FENCE = re.compile(
    r"(?ms)^(?P<fence>\x60{3,}|~{3,})[^\r\n]*\r?\n.*?^(?P=fence)\s*$"
)
_INLINE_CODE = re.compile(r"(?<!\x60)\x60([^\x60\r\n]+)\x60(?!\x60)")
_BLOCK_MATH = re.compile(r"(?ms)^\$\$\s*\n?(?P<body>.*?)\n?\$\$\s*$")
_INLINE_MATH = re.compile(r"(?<!\$)\$(?!\$)([^$\r\n]+?)\$(?!\$)")
_CALLOUT = re.compile(
    r"(?m)^>\s*\[!(?P<kind>[A-Za-z][A-Za-z0-9_-]*)\]\s*(?P<title>[^\r\n]*)\r?\n"
    r"(?P<body>(?:>[^\r\n]*(?:\r?\n|$))*)"
)
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
_ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_ALLOWED_CALLOUTS = {
    "note",
    "key-idea",
    "important",
    "warning",
    "tip",
    "exam-tip",
    "common-mistake",
}


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


def _activate_wikilinks(source: str, wikilinks=(), *, note_route="/obsidian/note") -> str:
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
        target = "{}?path={}".format(
            str(note_route or "/obsidian/note"),
            quote(str(item["resolved_path"]), safe=""),
        )
        return "[{}]({})".format(label, target)

    return _WIKILINK.sub(replace, str(source or ""))


class _Placeholders:
    def __init__(self, source: str):
        self.source = source
        self.items = []

    def add(self, html: Markup, *, block: bool) -> str:
        seed = "{}\0{}\0{}".format(
            len(self.items),
            self.source,
            str(html),
        ).encode("utf-8")
        digest = hashlib.sha256(seed).hexdigest()[:20].upper()
        token = "ANVAYARICH{}TOKEN".format(digest)
        while token in self.source or any(token == item[0] for item in self.items):
            digest = hashlib.sha256(
                (digest + "x").encode("ascii")
            ).hexdigest()[:20].upper()
            token = "ANVAYARICH{}TOKEN".format(digest)
        self.items.append((token, str(html), block))
        return token

    def apply(self, rendered: str) -> str:
        output = str(rendered)
        for token, html, block in self.items:
            if block:
                output = output.replace("<p>{}</p>\n".format(token), html + "\n")
                output = output.replace("<p>{}</p>".format(token), html)
            output = output.replace(token, html)
        return output


def _callout_markup(kind: str, title: str, body: str) -> Markup:
    normalized = str(kind or "note").strip().casefold().replace("_", "-")
    if normalized not in _ALLOWED_CALLOUTS:
        normalized = "note"
    display = normalized.replace("-", " ").title()
    clean_title = str(title or "").strip() or display
    body_lines = []
    for line in str(body or "").splitlines():
        text = line
        if text.startswith(">"):
            text = text[1:]
            if text.startswith(" "):
                text = text[1:]
        body_lines.append(text)
    body_markdown = "\n".join(body_lines).strip()
    body_html = str(_MARKDOWN(body_markdown)) if body_markdown else ""
    return Markup(
        '<aside class="rich-callout rich-callout-{}" role="note">'
        '<div class="rich-callout-heading"><span class="rich-callout-label">{}</span>'
        '<strong>{}</strong></div><div class="rich-callout-body">{}</div></aside>'
    ).format(
        escape(normalized),
        escape(display),
        escape(clean_title),
        Markup(body_html),
    )


def _relationship_markup(body: str, *, kind: str) -> Markup:
    rows = []
    for raw_line in str(body or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        nodes = [part.strip() for part in line.split("->") if part.strip()]
        if not nodes:
            continue
        pieces = []
        for index, node in enumerate(nodes):
            if index:
                pieces.append(
                    '<span class="rich-visual-arrow" aria-hidden="true">→</span>'
                )
            pieces.append(
                '<span class="rich-visual-node">{}</span>'.format(escape(node))
            )
        rows.append(
            '<div class="rich-visual-row">{}</div>'.format("".join(pieces))
        )
    css_kind = "rich-flowchart" if kind == "flowchart" else "rich-diagram"
    label = "Flowchart" if kind == "flowchart" else "Concept diagram"
    if not rows:
        rows.append(
            '<div class="rich-visual-row">'
            '<span class="rich-visual-node">Empty visual block</span></div>'
        )
    return Markup(
        '<figure class="{}" aria-label="{}"><div class="rich-visual-canvas">{}</div>'
        '<figcaption>{}</figcaption></figure>'
    ).format(
        escape(css_kind),
        escape(label),
        Markup("".join(rows)),
        escape(label),
    )


def _math_block_markup(body: str) -> Markup:
    return Markup(
        '<div class="rich-math-block" role="math" aria-label="Mathematical expression">'
        '<code>{}</code></div>'
    ).format(escape(str(body or "").strip()))


def _math_inline_markup(body: str) -> Markup:
    return Markup(
        '<span class="rich-math-inline" role="math">{}</span>'
    ).format(escape(str(body or "").strip()))


def _image_target(target: str, *, note_path: str, asset_route: str):
    raw = unquote(str(target or "").strip())
    if raw.startswith("<") and raw.endswith(">"):
        raw = raw[1:-1].strip()
    if not raw or not note_path or not asset_route:
        return None
    if _WINDOWS_ABSOLUTE.match(raw) or raw.startswith(("/", "\\")):
        return None
    split = urlsplit(raw)
    if split.scheme or split.netloc or split.query:
        return None
    path_text = split.path.replace("\\", "/")
    base_parts = list(
        PurePosixPath(str(note_path).replace("\\", "/")).parent.parts
    )
    for part in PurePosixPath(path_text).parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not base_parts:
                return None
            base_parts.pop()
            continue
        base_parts.append(part)
    if not base_parts:
        return None
    normalized = PurePosixPath(*base_parts).as_posix()
    if PurePosixPath(normalized).suffix.casefold() not in _ALLOWED_IMAGE_SUFFIXES:
        return None
    return "{}?path={}".format(
        str(asset_route),
        quote(normalized, safe=""),
    )


def _image_markup(
    target: str,
    alt: str,
    *,
    note_path: str,
    asset_route: str,
) -> Markup:
    resolved = _image_target(
        target,
        note_path=note_path,
        asset_route=asset_route,
    )
    label = str(alt or "").strip() or PurePosixPath(str(target or "")).name
    if not resolved:
        return Markup(
            '<span class="rich-image-unavailable" role="note">'
            'Image unavailable: {}</span>'
        ).format(escape(label or "unsupported image"))
    return Markup(
        '<figure class="rich-image"><img src="{}" alt="{}" loading="lazy" '
        'decoding="async" referrerpolicy="no-referrer" />'
        '<figcaption>{}</figcaption></figure>'
    ).format(
        escape(resolved),
        escape(label),
        escape(label),
    )


def _extract_rich_blocks(
    source: str,
    *,
    note_path: str = "",
    asset_route: str = "",
):
    placeholders = _Placeholders(source)
    current = str(source or "")

    def fenced(match):
        kind = str(match.group("kind") or "").casefold()
        html = _relationship_markup(
            match.group("body"),
            kind="flowchart" if kind == "flowchart" else "diagram",
        )
        return placeholders.add(html, block=True) + "\n"

    current = _RICH_FENCE.sub(fenced, current)

    def ordinary_code(match):
        rendered = Markup(str(_MARKDOWN(match.group(0))))
        return placeholders.add(rendered, block=True) + "\n"

    current = _CODE_FENCE.sub(ordinary_code, current)

    def inline_code(match):
        html = Markup("<code>{}</code>").format(escape(match.group(1)))
        return placeholders.add(html, block=False)

    current = _INLINE_CODE.sub(inline_code, current)

    def callout(match):
        html = _callout_markup(
            match.group("kind"),
            match.group("title"),
            match.group("body"),
        )
        return placeholders.add(html, block=True) + "\n"

    current = _CALLOUT.sub(callout, current)

    def block_math(match):
        return placeholders.add(
            _math_block_markup(match.group("body")),
            block=True,
        ) + "\n"

    current = _BLOCK_MATH.sub(block_math, current)

    if note_path and asset_route:
        def obsidian_image(match):
            raw = str(match.group(1) or "")
            target, separator, label = raw.partition("|")
            caption = (
                label.strip()
                if separator
                else PurePosixPath(target.strip()).stem
            )
            return placeholders.add(
                _image_markup(
                    target.strip(),
                    caption,
                    note_path=note_path,
                    asset_route=asset_route,
                ),
                block=True,
            ) + "\n"

        current = _OBSIDIAN_IMAGE.sub(obsidian_image, current)

        def markdown_image(match):
            return placeholders.add(
                _image_markup(
                    match.group(2),
                    match.group(1),
                    note_path=note_path,
                    asset_route=asset_route,
                ),
                block=True,
            ) + "\n"

        current = _MARKDOWN_IMAGE.sub(markdown_image, current)

    def inline_math(match):
        return placeholders.add(
            _math_inline_markup(match.group(1)),
            block=False,
        )

    current = _INLINE_MATH.sub(inline_math, current)
    return current, placeholders


def _wrap_tables(rendered: str) -> str:
    return str(rendered).replace(
        "<table>",
        '<div class="rich-comparison-table"><table>',
    ).replace(
        "</table>",
        "</table></div>",
    )


def render_markdown(
    markdown_text: str,
    *,
    wikilinks=(),
    note_route="/obsidian/note",
    note_path="",
    asset_route="",
) -> Markup:
    """Return escaped HTML with deterministic, script-free academic visual blocks."""
    source = _activate_wikilinks(
        _reading_body(str(markdown_text or "")),
        wikilinks=wikilinks,
        note_route=note_route,
    )
    try:
        source, placeholders = _extract_rich_blocks(
            source,
            note_path=str(note_path or ""),
            asset_route=str(asset_route or ""),
        )
        rendered: Any = _MARKDOWN(source)
        rich = placeholders.apply(_wrap_tables(str(rendered)))
        return Markup(rich)
    except Exception:
        return Markup('<pre class="obsidian-render-fallback">{}</pre>').format(
            escape(str(markdown_text or ""))
        )
