from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from markupsafe import Markup

from personal_learning_assistant.repositories.filesystem.obsidian_workspace_reader import (
    ObsidianWorkspacePathError,
    ObsidianWorkspaceReadError,
    ObsidianWorkspaceReader,
)
from personal_learning_assistant.services.notes_studio_asset_service import (
    NotesStudioAssetNotFoundError,
    NotesStudioAssetService,
    NotesStudioAssetUnavailableError,
)
from personal_learning_assistant.services.obsidian_markdown_renderer import (
    render_markdown,
)


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "Vault"
    (vault / ".obsidian").mkdir(parents=True)
    return vault


def _write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def test_renderer_supports_safe_callouts_math_flowcharts_diagrams_and_tables():
    source = r"""
> [!IMPORTANT] Pivot condition
> A zero pivot may require a row swap.

Inline math $A=LU$ appears here.

$$
Ax=b
$$

~~~flowchart
System -> Elimination -> U
Elimination -> Multipliers -> L
~~~

~~~diagram
Vector Space -> Subspace
Subspace -> Basis
~~~

| Method | Result |
| --- | --- |
| Elimination | U |
"""

    html = str(render_markdown(source))

    assert 'class="rich-callout rich-callout-important"' in html
    assert "Pivot condition" in html
    assert "zero pivot" in html
    assert 'class="rich-math-inline"' in html
    assert 'class="rich-math-block"' in html
    assert "A=LU" in html and "Ax=b" in html
    assert 'class="rich-flowchart"' in html
    assert "System" in html and "Elimination" in html and "Multipliers" in html
    assert 'class="rich-diagram"' in html
    assert "Vector Space" in html and "Basis" in html
    assert 'class="rich-comparison-table"' in html
    assert "<table>" in html


def test_rich_blocks_escape_script_like_content_and_do_not_emit_script_tags():
    source = r"""
> [!WARNING] <script>alert(1)</script>
> Never trust raw HTML.

~~~flowchart
Start -> <img src=x onerror=alert(2)> -> End
~~~

$$
<script>alert(3)</script>
$$
"""

    html = str(render_markdown(source))
    lowered = html.casefold()

    assert "<script" not in lowered
    assert "<img src=x" not in lowered
    assert "&lt;script&gt;" in html
    assert "&lt;img src=x onerror=alert(2)&gt;" in html


def test_local_standard_and_obsidian_images_use_notes_asset_route():
    source = """
![LU diagram](images/lu.png)

![[figures/matrix.webp|Matrix view]]
"""

    html = str(
        render_markdown(
            source,
            note_path="Math/LU.md",
            asset_route="/notes/asset",
        )
    )

    assert '<figure class="rich-image">' in html
    assert "LU diagram" in html
    assert "Matrix view" in html
    assert "/notes/asset?path=Math%2Fimages%2Flu.png" in html
    assert "/notes/asset?path=Math%2Ffigures%2Fmatrix.webp" in html


@pytest.mark.parametrize(
    "source",
    (
        "![bad](../../outside.png)",
        "![bad](C:/secret.png)",
        "![bad](file:///etc/passwd)",
        "![bad](javascript:alert(1))",
        "![remote](https://example.com/image.png)",
        "![[../../outside.png]]",
        "![[diagram.svg]]",
    ),
)
def test_unsafe_or_unsupported_images_never_emit_img(source):
    html = str(
        render_markdown(
            source,
            note_path="Math/LU.md",
            asset_route="/notes/asset",
        )
    )

    assert "<img" not in html.casefold()
    assert "rich-image-unavailable" in html


def test_workspace_reader_reads_only_bounded_safe_raster_assets(tmp_path):
    vault = _vault(tmp_path)
    raw = b"\x89PNG\r\n\x1a\nANVAYA"
    _write(vault / "Math" / "images" / "lu.png", raw)
    reader = ObsidianWorkspaceReader(vault)

    payload = reader.read_asset("Math/images/lu.png")

    assert payload["relative_path"] == "Math/images/lu.png"
    assert payload["bytes"] == raw
    assert payload["mimetype"] == "image/png"
    assert payload["source_hash"] == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize(
    "path",
    (
        "../outside.png",
        "Math/../../outside.png",
        "/absolute.png",
        r"C:\secret.png",
        "Math/image.svg",
        "Math/note.md",
    ),
)
def test_workspace_reader_rejects_unsafe_or_unsupported_asset_paths(tmp_path, path):
    vault = _vault(tmp_path)
    reader = ObsidianWorkspaceReader(vault)

    with pytest.raises(ObsidianWorkspacePathError):
        reader.read_asset(path)


def test_workspace_reader_rejects_symlink_asset_when_supported(tmp_path):
    vault = _vault(tmp_path)
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"outside")
    target = vault / "Math" / "linked.png"
    target.parent.mkdir(parents=True)

    try:
        target.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")

    reader = ObsidianWorkspaceReader(vault)
    with pytest.raises(ObsidianWorkspacePathError):
        reader.read_asset("Math/linked.png")


def test_asset_service_maps_reader_failures_without_leaking_paths():
    class MissingReader:
        def read_asset(self, _path):
            raise ObsidianWorkspacePathError("C:/SECRET/image.png")

    class BrokenReader:
        def read_asset(self, _path):
            raise ObsidianWorkspaceReadError("C:/SECRET/image.png")

    with pytest.raises(NotesStudioAssetNotFoundError):
        NotesStudioAssetService(lambda: MissingReader()).read_asset("x.png")
    with pytest.raises(NotesStudioAssetUnavailableError):
        NotesStudioAssetService(lambda: BrokenReader()).read_asset("x.png")


class FakeAssetService:
    def __init__(self, *, error=None):
        self.error = error
        self.paths = []

    def read_asset(self, path):
        self.paths.append(path)
        if self.error:
            raise self.error
        return {
            "relative_path": "Math/images/lu.png",
            "bytes": b"PNGDATA",
            "mimetype": "image/png",
            "source_hash": "a" * 64,
            "size_bytes": 7,
        }


def _app(asset_service):
    from personal_learning_assistant.ui.web import create_app

    return create_app(
        {
            "TESTING": True,
            "NOTES_STUDIO_ASSET_SERVICE_FACTORY": lambda: asset_service,
        }
    )


def test_asset_route_serves_safe_bytes_with_nosniff_and_private_cache():
    service = FakeAssetService()
    response = _app(service).test_client().get(
        "/notes/asset?path=Math%2Fimages%2Flu.png"
    )

    assert response.status_code == 200
    assert response.data == b"PNGDATA"
    assert response.mimetype == "image/png"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "private" in response.headers["Cache-Control"]
    assert service.paths == ["Math/images/lu.png"]


@pytest.mark.parametrize(
    ("error", "status"),
    (
        (NotesStudioAssetNotFoundError("C:/SECRET"), 404),
        (NotesStudioAssetUnavailableError("C:/SECRET"), 503),
    ),
)
def test_asset_route_redacts_internal_errors(error, status):
    response = _app(FakeAssetService(error=error)).test_client().get(
        "/notes/asset?path=bad.png"
    )
    text = response.get_data(as_text=True)

    assert response.status_code == status
    assert "SECRET" not in text


def test_full_note_reader_passes_note_path_and_asset_route_to_renderer():
    from personal_learning_assistant.domain.notes_studio_read_models import (
        NoteCard,
        NoteDetail,
    )
    from personal_learning_assistant.services.notes_studio_reader_service import (
        NotesStudioReaderWebService,
    )

    card = NoteCard(
        identity="assistant:11111111-1111-4111-8111-111111111111",
        relative_path="Math/LU.md",
        source_hash="a" * 64,
        title="LU",
        topic="",
        course="MA103N",
        note_type="concept",
        note_date="",
        card_summary=(),
        tags=(),
        revision_status="unreviewed",
    )
    detail = NoteDetail(
        card=card,
        text="![diagram](images/lu.png)\n",
        wikilinks=(),
        backlinks=(),
    )

    class ReadService:
        def get_detail(self, _path):
            return detail

    calls = []

    def renderer(source, **kwargs):
        calls.append((source, kwargs))
        return Markup("<p>rendered</p>")

    NotesStudioReaderWebService(
        ReadService(),
        renderer=renderer,
    ).reader_view("Math/LU.md")

    assert calls[0][1]["note_path"] == "Math/LU.md"
    assert calls[0][1]["asset_route"] == "/notes/asset"
    assert calls[0][1]["note_route"] == "/notes/note"


def test_rich_visual_blocks_require_no_js_network_ai_tutor_or_write_path():
    root = Path(__file__).resolve().parents[1]
    renderer = (
        root / "personal_learning_assistant/services/obsidian_markdown_renderer.py"
    ).read_text(encoding="utf-8")
    assets = (
        root / "personal_learning_assistant/services/notes_studio_asset_service.py"
    ).read_text(encoding="utf-8")
    routes = (
        root / "personal_learning_assistant/ui/web/routes.py"
    ).read_text(encoding="utf-8")

    combined = (renderer + "\n" + assets).casefold()
    for forbidden in (
        "personal_learning_assistant.tutor",
        "notesstudioservice",
        "sqlite3",
        "openai",
        "requests",
        "httpx",
        ".write_text(",
        ".write_bytes(",
        "os.replace(",
        "<script",
        "mermaid",
        "mathjax",
        "katex",
    ):
        assert forbidden not in combined

    assert '@web_blueprint.get("/notes/asset")' in routes
    assert '@web_blueprint.post("/notes/asset")' not in routes


def test_rich_visual_css_is_responsive_and_covers_all_block_types():
    root = Path(__file__).resolve().parents[1]
    css = (
        root / "personal_learning_assistant/ui/web/static/css/app.css"
    ).read_text(encoding="utf-8")

    for selector in (
        ".rich-image",
        ".rich-callout",
        ".rich-math-inline",
        ".rich-math-block",
        ".rich-flowchart",
        ".rich-diagram",
        ".rich-comparison-table",
    ):
        assert selector in css
    assert "@media (max-width: 680px)" in css
