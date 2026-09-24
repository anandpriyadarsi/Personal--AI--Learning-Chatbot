"""Read-only final reconciliation for Notes Studio Phase 7.5.15.9.

The final decision is deliberately conservative: Obsidian Markdown remains the
active rich-note authority and the legacy JSON notes store remains preserved
until a separately reviewed migration/cutover unit is approved.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Iterable

from personal_learning_assistant.services.legacy_note_reconciliation import (
    preview_legacy_notes,
)


CUTOVER_DECISION = "preserve_legacy_no_automatic_migration"


@dataclass(frozen=True)
class _RegisteredNote:
    id: str
    title: str
    relative_path: str


def _strip_frontmatter(source: str) -> str:
    text = str(source or "")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].lstrip("\ufeff").strip() != "---":
        return text
    for index in range(1, len(lines)):
        if lines[index].strip() in ("---", "..."):
            return "".join(lines[index + 1 :]).lstrip("\r\n")
    return text


def _registered(cards: Iterable[object]):
    result = []
    by_id = {}
    for card in cards or ():
        identity = str(getattr(card, "identity", "") or "")
        relative_path = str(getattr(card, "relative_path", "") or "")
        title = str(getattr(card, "title", "") or "")
        if not relative_path:
            continue
        note_id = identity or "vault-note:{}".format(relative_path)
        row = _RegisteredNote(
            id=note_id,
            title=title,
            relative_path=relative_path,
        )
        result.append(row)
        by_id[note_id] = row
    return tuple(result), by_id


def _legacy_status(decisions, path: Path):
    if not path.exists():
        return "missing"
    if any(int(item.legacy_index) < 0 for item in decisions):
        return "invalid"
    return "valid"


class NotesStudioReconciliationService:
    """Preview legacy/rich-note reconciliation without performing any mutation."""

    def __init__(self, *, read_service, legacy_path):
        self.read_service = read_service
        self.legacy_path = Path(legacy_path)

    def report(self):
        cards = tuple(self.read_service.list_cards())
        registered, registered_by_id = _registered(cards)
        body_cache = {}

        def body_lookup(note):
            note_id = str(note.id)
            if note_id in body_cache:
                return body_cache[note_id]
            row = registered_by_id.get(note_id)
            if row is None:
                return None
            try:
                detail = self.read_service.get_detail(row.relative_path)
            except Exception:
                return None
            body = _strip_frontmatter(str(detail.text or ""))
            body_cache[note_id] = body
            return body

        decisions = preview_legacy_notes(
            self.legacy_path,
            registered,
            body_lookup=body_lookup,
        )
        counts = {
            "match_existing": 0,
            "needs_review": 0,
            "create_markdown": 0,
        }
        items = []
        for item in decisions:
            decision = str(item.decision)
            if decision in counts:
                counts[decision] += 1
            items.append(
                {
                    "legacy_index": int(item.legacy_index),
                    "legacy_title": str(item.legacy_title),
                    "decision": decision,
                    "candidate_note_ids": [
                        str(candidate)
                        for candidate in item.candidate_note_ids
                    ],
                    "reason": str(item.reason),
                }
            )

        managed = sum(
            1
            for card in cards
            if bool(getattr(card, "managed", False))
            or str(getattr(card, "identity", "")).startswith("assistant:")
        )
        legacy_count = sum(1 for item in decisions if int(item.legacy_index) >= 0)

        return {
            "cutover_decision": CUTOVER_DECISION,
            "automatic_migration": False,
            "legacy_write_compatibility": "preserved",
            "default_note_authority": "obsidian_markdown",
            "legacy_status": _legacy_status(decisions, self.legacy_path),
            "legacy_record_count": legacy_count,
            "rich_note_count": len(cards),
            "managed_note_count": managed,
            "unmanaged_note_count": len(cards) - managed,
            "decision_counts": counts,
            "items": items,
        }


def build_notes_studio_reconciliation_service():
    read_module = import_module(
        "personal_learning_assistant.services.notes_studio_read_service"
    )
    config_module = import_module("config")
    return NotesStudioReconciliationService(
        read_service=read_module.build_configured_notes_studio_read_service(),
        legacy_path=getattr(config_module, "NOTES_FILE", "data/notes.json"),
    )
