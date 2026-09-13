"""V11.3 Math-aware + Vision-aware document reader.

Normal text-based PDFs:
    layout-preserving pypdf extraction + pdfplumber table extraction

Scanned/image-heavy PDF pages:
    optional vision fallback through vision_math_reader.py

Environment:
    MATH_VISION_MODE=auto   # default
    MATH_VISION_MODE=always
    MATH_VISION_MODE=off

In auto mode, vision is used only when extracted page text appears too sparse.
"""

import os
import re


try:
    from vision_math_reader import (
        transcribe_pdf_page,
        vision_is_configured,
    )
except ImportError:
    transcribe_pdf_page = None

    def vision_is_configured():
        return False


SUPERSCRIPT_MAP = str.maketrans({
    "⁰": "^0", "¹": "^1", "²": "^2", "³": "^3", "⁴": "^4",
    "⁵": "^5", "⁶": "^6", "⁷": "^7", "⁸": "^8", "⁹": "^9",
    "⁺": "^+", "⁻": "^-", "⁼": "^=", "⁽": "^(", "⁾": "^)",
})

SUBSCRIPT_MAP = str.maketrans({
    "₀": "_0", "₁": "_1", "₂": "_2", "₃": "_3", "₄": "_4",
    "₅": "_5", "₆": "_6", "₇": "_7", "₈": "_8", "₉": "_9",
    "₊": "_+", "₋": "_-", "₌": "_=", "₍": "_(", "₎": "_)",
})

MATH_SYMBOL_WORDS = {
    "∑": "sum",
    "∏": "product",
    "∫": "integral",
    "√": "sqrt",
    "∞": "infinity",
    "≈": "approximately",
    "≠": "not_equal",
    "≤": "less_equal",
    "≥": "greater_equal",
    "∈": "element_of",
    "∉": "not_element_of",
    "⊂": "subset",
    "⊆": "subset_equal",
    "∪": "union",
    "∩": "intersection",
    "→": "arrow",
    "⇒": "implies",
    "⇔": "iff",
    "×": "times",
    "÷": "divide",
    "·": "dot",
    "±": "plus_minus",
    "∇": "nabla",
    "∂": "partial",
    "λ": "lambda",
    "μ": "mu",
    "σ": "sigma",
    "θ": "theta",
    "α": "alpha",
    "β": "beta",
    "γ": "gamma",
    "δ": "delta",
    "π": "pi",
}


def math_vision_mode():
    value = os.getenv(
        "MATH_VISION_MODE",
        "auto"
    ).strip().lower()

    if value not in {
        "auto",
        "always",
        "off",
    }:
        return "auto"

    return value


def normalize_math_unicode(text):
    text = str(text or "")
    text = text.translate(
        SUPERSCRIPT_MAP
    )
    text = text.translate(
        SUBSCRIPT_MAP
    )
    return text


def math_search_tokens(text):
    text = normalize_math_unicode(
        text
    ).lower()

    symbol_tokens = []

    for symbol, word in MATH_SYMBOL_WORDS.items():
        if symbol in text:
            symbol_tokens.append(
                word
            )

    raw = re.findall(
        r"[a-z]+(?:_[a-z0-9]+|\^[a-z0-9+\-]+)?"
        r"|[a-z]\d*"
        r"|\d+(?:\.\d+)?"
        r"|[+\-*/=<>]",
        text
    )

    return raw + symbol_tokens


def _clean_cell(value):
    if value is None:
        return ""

    value = str(
        value
    ).replace(
        "\n",
        " "
    ).strip()

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.replace(
        "|",
        r"\|"
    )


def table_to_markdown(table):
    if not table:
        return ""

    rows = [
        [
            _clean_cell(cell)
            for cell in row
        ]
        for row in table
        if row
    ]

    if not rows:
        return ""

    width = max(
        len(row)
        for row in rows
    )

    normalized = [
        row
        + [""] * (
            width - len(row)
        )
        for row in rows
    ]

    header = normalized[0]
    separator = ["---"] * width

    lines = [
        "| "
        + " | ".join(header)
        + " |",
        "| "
        + " | ".join(separator)
        + " |",
    ]

    for row in normalized[1:]:
        lines.append(
            "| "
            + " | ".join(row)
            + " |"
        )

    return "\n".join(
        lines
    )


def _layout_extract_page(page):
    try:
        text = page.extract_text(
            extraction_mode="layout"
        )
    except TypeError:
        text = page.extract_text()
    except Exception:
        text = ""

    return (
        text
        or ""
    ).rstrip()


def _meaningful_character_count(text):
    return len(
        re.sub(
            r"\s+",
            "",
            str(text or "")
        )
    )


def page_needs_vision(
    layout_text,
    tables=None,
    threshold=80
):
    if tables:
        return False

    return (
        _meaningful_character_count(
            layout_text
        )
        < threshold
    )


def extract_pdf_tables(file_path):
    tables_by_page = {}

    try:
        import pdfplumber
    except ImportError:
        return tables_by_page

    try:
        with pdfplumber.open(
            file_path
        ) as pdf:
            for page_number, page in enumerate(
                pdf.pages,
                start=1
            ):
                try:
                    tables = (
                        page.extract_tables()
                        or []
                    )
                except Exception:
                    tables = []

                rendered = []

                for table in tables:
                    markdown = (
                        table_to_markdown(
                            table
                        )
                    )

                    if markdown:
                        rendered.append(
                            markdown
                        )

                if rendered:
                    tables_by_page[
                        page_number
                    ] = rendered

    except Exception:
        return {}

    return tables_by_page


def _vision_fallback(
    file_path,
    page_number
):
    if (
        transcribe_pdf_page
        is None
        or not vision_is_configured()
    ):
        return None

    try:
        return transcribe_pdf_page(
            file_path,
            page_number
        )
    except Exception as error:
        return (
            "[VISION TRANSCRIPTION FAILED: "
            + str(error)
            + "]"
        )


def read_pdf_pages_math_aware(
    file_path
):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError(
            "Math-aware PDF reading requires pypdf. "
            "Run: python -m pip install "
            "pypdf pdfplumber pymupdf pillow"
        )

    try:
        reader = PdfReader(
            file_path
        )
    except Exception as error:
        raise RuntimeError(
            f"Could not open PDF: {error}"
        )

    tables_by_page = (
        extract_pdf_tables(
            file_path
        )
    )

    mode = math_vision_mode()
    pages = []

    for page_number, page in enumerate(
        reader.pages,
        start=1
    ):
        layout_text = (
            _layout_extract_page(
                page
            )
        )

        tables = tables_by_page.get(
            page_number,
            []
        )

        use_vision = False

        if mode == "always":
            use_vision = True

        elif (
            mode == "auto"
            and page_needs_vision(
                layout_text,
                tables
            )
        ):
            use_vision = True

        vision_text = None

        if use_vision:
            vision_text = (
                _vision_fallback(
                    file_path,
                    page_number
                )
            )

        parts = []

        if (
            vision_text
            and not vision_text.startswith(
                "[VISION TRANSCRIPTION FAILED:"
            )
        ):
            parts.append(
                "[VISION MATH TRANSCRIPTION]\n"
                + vision_text.strip()
            )

            source = "vision"

        else:
            source = "layout"

            if layout_text.strip():
                parts.append(
                    "[LAYOUT-PRESERVED TEXT]\n"
                    + layout_text.strip()
                )

            for table_number, table in enumerate(
                tables,
                start=1
            ):
                parts.append(
                    f"[DETECTED TABLE "
                    f"{table_number}]\n"
                    f"{table}"
                )

            if (
                vision_text
                and vision_text.startswith(
                    "[VISION TRANSCRIPTION FAILED:"
                )
            ):
                parts.append(
                    vision_text
                )

        if not parts:
            # Preserve knowledge that the page existed.
            if (
                mode != "off"
                and not vision_is_configured()
            ):
                parts.append(
                    "[IMAGE/SCANNED PAGE - "
                    "vision model not configured]"
                )
            else:
                continue

        pages.append({
            "page": page_number,
            "text": "\n\n".join(
                parts
            ),
            "tables": tables,
            "source": source,
        })

    if not pages:
        raise RuntimeError(
            "No readable content was found in this PDF."
        )

    return pages


def read_pdf_math_aware(
    file_path
):
    pages = (
        read_pdf_pages_math_aware(
            file_path
        )
    )

    rendered = []

    for page in pages:
        rendered.append(
            f"\n--- Page "
            f"{page['page']} "
            f"[{page.get('source', 'unknown')}] ---\n"
            f"{page['text']}"
        )

    return "\n".join(
        rendered
    )


def _is_protected_block_start(
    line
):
    stripped = line.strip()

    return (
        stripped.startswith(
            "```"
        )
        or stripped.startswith(
            "$$"
        )
        or stripped.startswith(
            r"\["
        )
    )


def _is_protected_block_end(
    line,
    start_kind
):
    stripped = line.strip()

    if start_kind == "```":
        return stripped.startswith(
            "```"
        )

    if start_kind == "$$":
        return stripped.endswith(
            "$$"
        )

    if start_kind == r"\[":
        return stripped.endswith(
            r"\]"
        )

    return False


def split_math_aware_chunks(
    content,
    chunk_size=1400
):
    content = str(
        content
        or ""
    ).strip()

    if not content:
        return []

    lines = content.splitlines()
    units = []
    current = []
    protected = None

    def flush():
        nonlocal current

        if current:
            block = "\n".join(
                current
            ).strip()

            if block:
                units.append(
                    block
                )

            current = []

    for line in lines:
        stripped = line.strip()

        if protected:
            current.append(
                line
            )

            if _is_protected_block_end(
                line,
                protected
            ):
                protected = None
                flush()

            continue

        if _is_protected_block_start(
            line
        ):
            flush()

            if stripped.startswith(
                "```"
            ):
                protected = "```"

            elif stripped.startswith(
                "$$"
            ):
                protected = "$$"

            else:
                protected = r"\["

            current.append(
                line
            )

            if (
                protected == "$$"
                and stripped.count(
                    "$$"
                ) >= 2
            ):
                protected = None
                flush()

            continue

        if stripped.startswith(
            "|"
        ):
            current.append(
                line
            )
            continue

        if not stripped:
            flush()
            continue

        current.append(
            line
        )

    flush()

    chunks = []
    current_chunk = ""

    for unit in units:
        candidate = (
            unit
            if not current_chunk
            else current_chunk
            + "\n\n"
            + unit
        )

        if len(
            candidate
        ) <= chunk_size:
            current_chunk = candidate
            continue

        if current_chunk:
            chunks.append(
                current_chunk
            )
            current_chunk = ""

        if len(
            unit
        ) <= chunk_size * 2:
            chunks.append(
                unit
            )
        else:
            start = 0

            while start < len(
                unit
            ):
                chunks.append(
                    unit[
                        start:
                        start
                        + chunk_size
                    ]
                )

                start += chunk_size

    if current_chunk:
        chunks.append(
            current_chunk
        )

    return chunks
