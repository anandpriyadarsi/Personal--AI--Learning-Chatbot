"""Build explicit, local-only context ZIPs for handing an Obsidian note to Alex/ChatGPT.

The service is read-only with respect to ANVAYA and the Obsidian vault. It never
calls an AI provider, uploads files, or writes Markdown back into the vault.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import PurePosixPath

from personal_learning_assistant.services.obsidian_workspace_service import (
    ObsidianWorkspaceError,
    build_obsidian_workspace_service,
)


MAX_FULL_VAULT_NOTES = 500
MAX_UNCOMPRESSED_BYTES = 32 * 1024 * 1024


class AlexHandoffError(RuntimeError):
    """Safe handoff bundle failure."""


def _safe_note_path(value: str) -> str:
    text = str(value or "").strip().replace("\\", "/")
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise AlexHandoffError("Choose a valid Markdown note inside the vault.")
    normalized = "/".join(parts)
    if not normalized.lower().endswith(".md"):
        raise AlexHandoffError("Only Markdown notes can be included in an Alex handoff.")
    return normalized


def _slug(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-")
    return clean[:80] or "anvaya-note"


class AlexHandoffService:
    def __init__(self, workspace_service):
        self.workspace_service = workspace_service

    @staticmethod
    def _prompt(note, *, full_vault: bool) -> str:
        scope = (
            "A full read-only Markdown snapshot of the connected vault is included."
            if full_vault
            else "Only the selected note plus a vault manifest and link context are included."
        )
        return """# ANVAYA → Alex handoff

You are helping with the ANVAYA Personal Learning Intelligence workspace.

Selected note:
- Title: {title}
- Vault path: {path}

{scope}

Task:
1. Read the supplied source note and context before drafting.
2. Preserve the existing NITK 2026-30 vault organization and Obsidian-style links.
3. Create or improve the requested Obsidian note using clear student-friendly Markdown.
4. Do not rewrite unrelated notes.
5. If information is missing, mark the gap rather than inventing academic facts.
6. Return the result as a ZIP whose Markdown paths are relative to the NITK 2026-30 folder.
7. Include a short CHANGELOG.md explaining which files you created or changed.

ANVAYA remains the local authority. The returned ZIP will be previewed before any import.
""".format(
            title=str(note.get("title") or ""),
            path=str(note.get("relative_path") or ""),
            scope=scope,
        )

    def build_note_bundle(self, relative_path, *, include_full_vault=False):
        try:
            selected = dict(self.workspace_service.note_preview(relative_path))
            workspace = self.workspace_service.workspace("")
        except ObsidianWorkspaceError as error:
            raise AlexHandoffError(str(error)) from error
        except Exception as error:
            raise AlexHandoffError(
                "The Alex handoff could not read the current Obsidian workspace."
            ) from error

        selected_path = _safe_note_path(selected.get("relative_path", ""))
        note_rows = tuple(workspace.get("notes", ()) or ())
        manifest = [
            {
                "relative_path": str(row.get("relative_path") or ""),
                "title": str(row.get("title") or ""),
                "tags": list(row.get("tags") or ()),
                "note_type": str(row.get("note_type") or "note"),
            }
            for row in note_rows[:MAX_FULL_VAULT_NOTES]
        ]
        context = {
            "bundle_version": "anvaya.alex_handoff/1.0.0",
            "selected_note": {
                "title": str(selected.get("title") or ""),
                "relative_path": selected_path,
                "tags": list(selected.get("tags") or ()),
                "note_type": str(selected.get("note_type") or "note"),
                "revision_status": str(selected.get("revision_status") or ""),
                "source_hash": str(selected.get("source_hash") or ""),
            },
            "wikilinks": list(selected.get("wikilinks") or ()),
            "backlinks": list(selected.get("backlinks") or ()),
            "vault_name": str(selected.get("vault_name") or ""),
            "full_vault_snapshot": bool(include_full_vault),
            "manifest_note_count": len(manifest),
        }

        buffer = io.BytesIO()
        total = 0
        included = 0
        with zipfile.ZipFile(
            buffer,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            prompt = self._prompt(selected, full_vault=bool(include_full_vault))
            archive.writestr("PROMPT.md", prompt.encode("utf-8"))
            archive.writestr(
                "CONTEXT.json",
                json.dumps(context, indent=2, ensure_ascii=False).encode("utf-8"),
            )
            archive.writestr(
                "NITK 2026-30/VAULT_MANIFEST.json",
                json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8"),
            )

            selected_bytes = str(selected.get("text") or "").encode("utf-8")
            archive.writestr(
                "NITK 2026-30/" + selected_path,
                selected_bytes,
            )
            total += len(selected_bytes)
            included += 1

            if include_full_vault:
                seen = {selected_path.casefold()}
                for row in note_rows[:MAX_FULL_VAULT_NOTES]:
                    raw_path = str(row.get("relative_path") or "")
                    try:
                        path = _safe_note_path(raw_path)
                    except AlexHandoffError:
                        continue
                    if path.casefold() in seen:
                        continue
                    try:
                        note = self.workspace_service.note_preview(path)
                    except Exception:
                        continue
                    payload = str(note.get("text") or "").encode("utf-8")
                    if total + len(payload) > MAX_UNCOMPRESSED_BYTES:
                        break
                    archive.writestr("NITK 2026-30/" + path, payload)
                    total += len(payload)
                    included += 1

        buffer.seek(0)
        filename = "ANVAYA_ALEX_{}.zip".format(
            _slug(PurePosixPath(selected_path).stem)
        )
        return {
            "filename": filename,
            "payload": buffer.getvalue(),
            "included_note_count": included,
            "full_vault_snapshot": bool(include_full_vault),
        }


def build_alex_handoff_service():
    return AlexHandoffService(build_obsidian_workspace_service())
