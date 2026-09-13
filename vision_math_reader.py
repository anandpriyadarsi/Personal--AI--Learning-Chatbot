"""V11.3 Vision Math Reader.

Reads scanned/image-heavy PDF pages by rendering them as images and asking a
vision-capable LLM to transcribe mathematical content faithfully.

Design goals:
- preserve matrices, determinants, systems, fractions, roots, superscripts,
  subscripts, tables and aligned equations;
- preserve visible question numbering and page structure;
- never invent unreadable symbols;
- clearly mark uncertain transcription;
- work as a fallback for V11.2 text/layout extraction.

Configuration (.env):
    VISION_API_URL=https://openrouter.ai/api/v1/chat/completions
    VISION_API_KEY=...
    VISION_MODEL=<vision-capable model>

If VISION_* values are missing, LLM_API_URL / LLM_API_KEY / LLM_MODEL are used.
The selected model MUST actually support image input.
"""

import base64
import io
import os

import requests

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    from PIL import Image
except ImportError:
    Image = None


BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

if load_dotenv is not None:
    load_dotenv(
        os.path.join(BASE_DIR, ".env")
    )


VISION_PROMPT = r"""
You are a mathematical document transcription engine.

Transcribe the visible page faithfully for use in an academic RAG system.

STRICT RULES:
1. Do not solve the problems.
2. Do not simplify or correct the mathematics.
3. Do not invent missing or unreadable symbols.
4. Preserve question numbers, sub-question labels and ordering.
5. Preserve matrices, determinants, vectors, systems of equations, fractions,
   roots, exponents, subscripts, summations, integrals and set notation.
6. Use Markdown + LaTeX for mathematical expressions.
7. Use display math for important equations and matrices.
8. Represent matrices using \begin{bmatrix} ... \end{bmatrix} when appropriate.
9. Represent determinants using \begin{vmatrix} ... \end{vmatrix} when appropriate.
10. Convert visible tables to Markdown tables when possible.
11. If a symbol or region is genuinely unreadable, write [UNCLEAR] instead of guessing.
12. Preserve prose, labels and units.
13. Do not add explanations or answers that are not visible on the page.

Return only the transcription.
"""


def vision_config():
    api_url = (
        os.getenv("VISION_API_URL")
        or os.getenv("LLM_API_URL")
        or "https://openrouter.ai/api/v1/chat/completions"
    )

    api_key = (
        os.getenv("VISION_API_KEY")
        or os.getenv("LLM_API_KEY")
    )

    model = (
        os.getenv("VISION_MODEL")
        or os.getenv("LLM_MODEL")
    )

    return api_url, api_key, model


def vision_is_configured():
    _, api_key, model = vision_config()
    return bool(api_key and model)


def render_pdf_page(
    file_path,
    page_number,
    dpi=180
):
    if fitz is None:
        raise RuntimeError(
            "PyMuPDF is required for scanned PDF rendering. "
            "Run: python -m pip install pymupdf pillow"
        )

    document = fitz.open(
        file_path
    )

    try:
        if (
            page_number < 1
            or page_number > document.page_count
        ):
            raise RuntimeError(
                f"Page {page_number} is outside the PDF."
            )

        page = document.load_page(
            page_number - 1
        )

        zoom = dpi / 72.0

        matrix = fitz.Matrix(
            zoom,
            zoom
        )

        pixmap = page.get_pixmap(
            matrix=matrix,
            alpha=False
        )

        png_bytes = pixmap.tobytes(
            "png"
        )

        return png_bytes

    finally:
        document.close()


def _resize_png_if_needed(
    png_bytes,
    max_width=1800
):
    if Image is None:
        return png_bytes

    try:
        image = Image.open(
            io.BytesIO(
                png_bytes
            )
        )

        if image.width <= max_width:
            return png_bytes

        ratio = (
            max_width
            / image.width
        )

        new_height = int(
            image.height
            * ratio
        )

        image = image.resize(
            (
                max_width,
                new_height
            )
        )

        buffer = io.BytesIO()

        image.save(
            buffer,
            format="PNG"
        )

        return buffer.getvalue()

    except Exception:
        return png_bytes


def transcribe_image_bytes(
    png_bytes,
    page_label=None,
    timeout=90
):
    api_url, api_key, model = vision_config()

    if not api_key:
        raise RuntimeError(
            "Vision API key is not configured."
        )

    if not model:
        raise RuntimeError(
            "VISION_MODEL is not configured. "
            "Choose a model that supports image input."
        )

    png_bytes = _resize_png_if_needed(
        png_bytes
    )

    encoded = base64.b64encode(
        png_bytes
    ).decode(
        "ascii"
    )

    prompt = VISION_PROMPT

    if page_label:
        prompt += (
            "\nPage label: "
            + str(page_label)
        )

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt,
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": (
                                "data:image/png;base64,"
                                + encoded
                            )
                        },
                    },
                ],
            }
        ],
        "temperature": 0,
    }

    headers = {
        "Authorization": (
            f"Bearer {api_key}"
        ),
        "Content-Type": "application/json",
    }

    response = requests.post(
        api_url,
        headers=headers,
        json=payload,
        timeout=timeout,
    )

    if response.status_code >= 400:
        text = response.text[:500]

        raise RuntimeError(
            "Vision API request failed "
            f"({response.status_code}): {text}"
        )

    data = response.json()

    try:
        content = (
            data["choices"][0]
            ["message"]["content"]
        )
    except (
        KeyError,
        IndexError,
        TypeError
    ):
        raise RuntimeError(
            "Vision model returned an unexpected response."
        )

    if isinstance(content, list):
        parts = []

        for item in content:
            if (
                isinstance(item, dict)
                and item.get("type") == "text"
            ):
                parts.append(
                    item.get(
                        "text",
                        ""
                    )
                )

        content = "\n".join(
            part
            for part in parts
            if part
        )

    content = str(
        content or ""
    ).strip()

    if not content:
        raise RuntimeError(
            "Vision model returned an empty transcription."
        )

    return content


def transcribe_pdf_page(
    file_path,
    page_number,
    dpi=180
):
    image = render_pdf_page(
        file_path,
        page_number,
        dpi=dpi
    )

    return transcribe_image_bytes(
        image,
        page_label=page_number
    )


def transcribe_pdf_pages(
    file_path,
    page_numbers,
    dpi=180
):
    results = []

    for page_number in page_numbers:
        transcription = (
            transcribe_pdf_page(
                file_path,
                page_number,
                dpi=dpi
            )
        )

        results.append({
            "page": page_number,
            "text": transcription,
            "source": "vision",
        })

    return results


def transcribe_image_file(
    image_path
):
    with open(
        image_path,
        "rb"
    ) as file:
        data = file.read()

    return transcribe_image_bytes(
        data,
        page_label=os.path.basename(
            image_path
        )
    )
