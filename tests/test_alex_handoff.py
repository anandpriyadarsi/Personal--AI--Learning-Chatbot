from __future__ import annotations

import io
import json
import zipfile


class FakeWorkspace:
    def workspace(self, query=""):
        return {
            "notes": (
                {
                    "relative_path": "MA103N/LU Factorization.md",
                    "title": "LU Factorization",
                    "tags": ["linear-algebra"],
                    "note_type": "concept",
                },
                {
                    "relative_path": "MA103N/Row Operations.md",
                    "title": "Row Operations",
                    "tags": [],
                    "note_type": "concept",
                },
            )
        }

    def markdown_snapshot(self, *, max_notes=500, max_bytes=32 * 1024 * 1024):
        return (
            {
                "relative_path": "MA103N/LU Factorization.md",
                "title": "LU Factorization",
                "source_hash": "a" * 64,
                "text": "# LU Factorization\n\nPA = LU\n",
                "size_bytes": 29,
            },
            {
                "relative_path": "MA103N/Row Operations.md",
                "title": "Row Operations",
                "source_hash": "b" * 64,
                "text": "# Row Operations\n",
                "size_bytes": 17,
            },
        )

    def note_preview(self, path):
        notes = {
            "MA103N/LU Factorization.md": {
                "title": "LU Factorization",
                "relative_path": "MA103N/LU Factorization.md",
                "tags": ["linear-algebra"],
                "note_type": "concept",
                "revision_status": "reviewed",
                "source_hash": "a" * 64,
                "vault_name": "NITK 2026-30",
                "text": "# LU Factorization\n\nPA = LU\n",
                "wikilinks": (
                    {
                        "raw": "Row Operations",
                        "target": "Row Operations",
                        "label": "Row Operations",
                        "resolved_path": "MA103N/Row Operations.md",
                    },
                ),
                "backlinks": (),
            },
            "MA103N/Row Operations.md": {
                "title": "Row Operations",
                "relative_path": "MA103N/Row Operations.md",
                "tags": [],
                "note_type": "concept",
                "revision_status": "reviewed",
                "source_hash": "b" * 64,
                "vault_name": "NITK 2026-30",
                "text": "# Row Operations\n",
                "wikilinks": (),
                "backlinks": (),
            },
        }
        return notes[path]


def test_alex_handoff_bundle_is_read_only_and_contains_prompt_context():
    from personal_learning_assistant.services.alex_handoff_service import (
        AlexHandoffService,
    )

    result = AlexHandoffService(FakeWorkspace()).build_note_bundle(
        "MA103N/LU Factorization.md",
        include_full_vault=True,
    )
    assert result["filename"].endswith(".zip")
    assert result["included_note_count"] == 2

    with zipfile.ZipFile(io.BytesIO(result["payload"])) as archive:
        names = set(archive.namelist())
        assert "PROMPT.md" in names
        assert "CONTEXT.json" in names
        assert "NITK 2026-30/VAULT_MANIFEST.json" in names
        assert "NITK 2026-30/MA103N/LU Factorization.md" in names
        assert "NITK 2026-30/MA103N/Row Operations.md" in names
        context = json.loads(archive.read("CONTEXT.json").decode("utf-8"))
        assert context["selected_note"]["title"] == "LU Factorization"
        assert context["full_vault_snapshot"] is True


def test_alex_handoff_route_returns_zip_without_provider_call():
    from personal_learning_assistant.ui.web import create_app

    class FakeHandoff:
        def build_note_bundle(self, path, include_full_vault=False):
            assert path == "MA103N/LU Factorization.md"
            assert include_full_vault is False
            return {
                "filename": "ANVAYA_ALEX_LU.zip",
                "payload": b"PK-test",
                "included_note_count": 1,
                "full_vault_snapshot": False,
            }

    app = create_app(
        {
            "TESTING": True,
            "ALEX_HANDOFF_SERVICE_FACTORY": lambda: FakeHandoff(),
        }
    )
    response = app.test_client().post(
        "/obsidian/note/alex-handoff",
        data={"path": "MA103N/LU Factorization.md"},
    )
    assert response.status_code == 200
    assert response.mimetype == "application/zip"
    assert "ANVAYA_ALEX_LU.zip" in response.headers["Content-Disposition"]
