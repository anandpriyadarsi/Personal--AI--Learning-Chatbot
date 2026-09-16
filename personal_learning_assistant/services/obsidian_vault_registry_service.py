"""Phase 5.3 Obsidian vault metadata/link-graph orchestration."""

from __future__ import annotations

import posixpath
import unicodedata
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple
from urllib.parse import unquote

from personal_learning_assistant.domain.obsidian_vault_models import (
    VaultRegistryPlan,
    VaultRegistryResult,
    VaultScanResult,
)
from personal_learning_assistant.repositories.filesystem.obsidian_vault_scanner import (
    normalized_basename,
    normalized_note_path_key,
    normalize_relative_path,
)
from personal_learning_assistant.repositories.sqlite.obsidian_vault_repository import (
    ObsidianVaultConflictError,
    SQLiteObsidianVaultRepository,
)


_NAMESPACE = uuid.UUID("356a56a7-4c4e-45fe-a078-32dc8d1b5e99")


def _utc_now():
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _stable_uuid(label: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, label))


def _note_reference_key(value: str) -> str:
    text = unquote(str(value or "").strip().replace("\\", "/"))
    if text.lower().endswith(".md"):
        text = text[:-3]
    text = normalize_relative_path(text)
    return text.casefold()


def _path_without_md(value: str) -> str:
    text = normalize_relative_path(value)
    if text.lower().endswith(".md"):
        text = text[:-3]
    return text


class ObsidianVaultRegistryService:
    """Register vault note metadata/tags/links without writing Markdown."""

    def __init__(self, repository: SQLiteObsidianVaultRepository, *, now=_utc_now):
        self.repository = repository
        self._now = now

    @staticmethod
    def vault_id(vault_key: str) -> str:
        return _stable_uuid("vault|" + str(vault_key).casefold())

    def _identity_map(self, scan: VaultScanResult):
        vault_id = self.vault_id(scan.vault_key)
        existing_vault = self.repository.get_vault_by_key(scan.vault_key)
        if existing_vault is not None and existing_vault.id != vault_id:
            raise ObsidianVaultConflictError(
                "vault path_key is already bound to an incompatible ID"
            )
        existing_notes = {
            item.path_key: item for item in self.repository.list_notes(vault_id)
        }
        existing_by_id = {
            item.id: item for item in self.repository.list_notes(vault_id)
        }

        note_ids = {}
        for note in scan.notes:
            existing_path = existing_notes.get(note.path_key)
            if existing_path is not None:
                if note.assistant_id and note.assistant_id != existing_path.id:
                    raise ObsidianVaultConflictError(
                        "frontmatter assistant_id conflicts with existing stable note identity"
                    )
                note_id = existing_path.id
            elif note.assistant_id:
                other = existing_by_id.get(note.assistant_id)
                if other is not None:
                    # assistant_id safely preserves identity across a move/rename.
                    note_id = other.id
                else:
                    note_id = note.assistant_id
            else:
                note_id = _stable_uuid(
                    "note|{}|{}".format(vault_id, note.path_key)
                )
            if note_id in note_ids.values():
                raise ObsidianVaultConflictError(
                    "multiple scanned notes resolved to one stable note ID"
                )
            note_ids[note.path_key] = note_id
        return vault_id, existing_notes, existing_by_id, note_ids

    @staticmethod
    def _resolver_indexes(scan: VaultScanResult, note_ids: Mapping[str, str]):
        exact = {}
        basenames = defaultdict(list)
        assistant_ids = {}
        for note in scan.notes:
            note_id = note_ids[note.path_key]
            without_md = _path_without_md(note.relative_path).casefold()
            exact[without_md] = note_id
            basenames[normalized_basename(note.relative_path)].append(note_id)
            if note.assistant_id:
                assistant_ids[note.assistant_id.casefold()] = note_id
        return exact, basenames, assistant_ids

    @staticmethod
    def _resolve_local_markdown(
        raw_target: str,
        source_relative_path: str,
        exact,
        basenames,
    ):
        target = unquote(str(raw_target or "").strip().replace("\\", "/"))
        if not target:
            return None, "unresolved"
        source_dir = str(PurePosixPath(source_relative_path).parent)
        relative_candidate = posixpath.normpath(
            posixpath.join(source_dir, target)
        ).replace("\\", "/")
        candidates = []
        if relative_candidate and not relative_candidate.startswith("../"):
            candidates.append(relative_candidate)
        candidates.append(target)
        for candidate in candidates:
            try:
                key = _note_reference_key(candidate)
            except ValueError:
                continue
            match = exact.get(key)
            if match:
                return match, "resolved"
        try:
            basename = normalized_basename(target)
        except ValueError:
            return None, "unresolved"
        matches = tuple(sorted(set(basenames.get(basename, ()))))
        if len(matches) == 1:
            return matches[0], "resolved"
        if len(matches) > 1:
            return None, "ambiguous"
        return None, "unresolved"

    @staticmethod
    def _resolve_wiki(raw_target: str, exact, basenames, assistant_ids):
        target = unquote(str(raw_target or "").strip().replace("\\", "/"))
        if not target:
            return None, "unresolved"
        try:
            exact_key = _note_reference_key(target)
        except ValueError:
            exact_key = None
        if exact_key and exact_key in exact:
            return exact[exact_key], "resolved"
        assistant = assistant_ids.get(target.casefold())
        if assistant:
            return assistant, "resolved"
        try:
            basename = normalized_basename(target)
        except ValueError:
            return None, "unresolved"
        matches = tuple(sorted(set(basenames.get(basename, ()))))
        if len(matches) == 1:
            return matches[0], "resolved"
        if len(matches) > 1:
            return None, "ambiguous"
        return None, "unresolved"

    def _resolved_graph(self, scan: VaultScanResult, note_ids, now: str):
        exact, basenames, assistant_ids = self._resolver_indexes(scan, note_ids)
        links = []
        counts = {
            "resolved": 0,
            "unresolved": 0,
            "ambiguous": 0,
            "external": 0,
        }
        for note in scan.notes:
            source_id = note_ids[note.path_key]
            for intent in note.links:
                target_note_id = None
                unresolved_target = ""
                link_type = intent.target_kind
                if intent.target_kind == "wiki":
                    target_note_id, state = self._resolve_wiki(
                        intent.raw_target, exact, basenames, assistant_ids
                    )
                    if state == "resolved":
                        link_type = "wiki"
                        counts["resolved"] += 1
                    elif state == "ambiguous":
                        link_type = "wiki_ambiguous"
                        unresolved_target = intent.raw_target
                        counts["ambiguous"] += 1
                    else:
                        link_type = "wiki_unresolved"
                        unresolved_target = intent.raw_target
                        counts["unresolved"] += 1
                elif intent.target_kind == "markdown":
                    target_note_id, state = self._resolve_local_markdown(
                        intent.raw_target,
                        note.relative_path,
                        exact,
                        basenames,
                    )
                    if state == "resolved":
                        link_type = "markdown"
                        counts["resolved"] += 1
                    elif state == "ambiguous":
                        link_type = "markdown_ambiguous"
                        unresolved_target = intent.raw_target
                        counts["ambiguous"] += 1
                    else:
                        link_type = "markdown_unresolved"
                        unresolved_target = intent.raw_target
                        counts["unresolved"] += 1
                else:
                    unresolved_target = intent.raw_target
                    counts["external"] += 1

                link_id = _stable_uuid(
                    "note-link|{}|{}|{}|{}|{}|{}".format(
                        source_id,
                        intent.source_position,
                        intent.target_kind,
                        intent.raw_target,
                        intent.heading,
                        intent.block_id,
                    )
                )
                links.append(
                    {
                        "id": link_id,
                        "source_note_id": source_id,
                        "target_note_id": target_note_id,
                        "unresolved_target": unresolved_target,
                        "source_position": intent.source_position,
                        "heading": intent.heading,
                        "block_id": intent.block_id,
                        "link_type": link_type,
                        "created_at": now,
                    }
                )
        return tuple(links), counts

    @staticmethod
    def _tag_rows(scan: VaultScanResult, note_ids, now: str):
        tags = {}
        note_tags = []
        for note in scan.notes:
            note_id = note_ids[note.path_key]
            for name in note.tags:
                normalized = unicodedata.normalize("NFC", name).casefold()
                tag_id = _stable_uuid("tag|" + normalized)
                tags.setdefault(
                    normalized,
                    {
                        "id": tag_id,
                        "name": name,
                        "normalized_name": normalized,
                        "created_at": now,
                    },
                )
                note_tags.append((note_id, tag_id))
        return tuple(tags[key] for key in sorted(tags)), tuple(sorted(set(note_tags)))

    def preview(self, scan: VaultScanResult) -> VaultRegistryPlan:
        vault_id, existing_notes, existing_by_id, note_ids = self._identity_map(scan)
        scanned_ids = set(note_ids.values())
        create_count = 0
        match_count = 0
        update_count = 0
        for note in scan.notes:
            note_id = note_ids[note.path_key]
            existing = existing_by_id.get(note_id) or existing_notes.get(note.path_key)
            if existing is None:
                create_count += 1
            elif (
                existing.source_hash == note.source_hash
                and existing.relative_path == note.relative_path
                and existing.title == note.title
                and existing.note_type == note.note_type
                and existing.confidence == note.confidence
                and existing.revision_status == note.revision_status
            ):
                match_count += 1
            else:
                update_count += 1

        now = self._now()
        links, counts = self._resolved_graph(scan, note_ids, now)
        tags, _note_tags = self._tag_rows(scan, note_ids, now)
        missing = tuple(
            sorted(
                item.id
                for item in self.repository.list_notes(vault_id)
                if item.id not in scanned_ids
            )
        )
        return VaultRegistryPlan(
            vault_id=vault_id,
            vault_key=scan.vault_key,
            note_count=scan.note_count,
            create_count=create_count,
            match_count=match_count,
            update_count=update_count,
            missing_registry_count=len(missing),
            tag_count=len(tags),
            resolved_link_count=counts["resolved"],
            unresolved_link_count=counts["unresolved"],
            ambiguous_link_count=counts["ambiguous"],
            external_link_count=counts["external"],
            blocking_issue_count=scan.blocking_issue_count,
            warning_count=scan.warning_count,
            scan_manifest_hash=scan.manifest_hash,
        )

    def apply(
        self,
        scan: VaultScanResult,
        *,
        require_clean_scan: bool = True,
    ) -> VaultRegistryResult:
        if require_clean_scan and scan.blocking_issue_count:
            raise ObsidianVaultConflictError(
                "vault scan contains {} blocking issue(s); registry was not changed".format(
                    scan.blocking_issue_count
                )
            )
        now = self._now()
        vault_id, existing_notes, existing_by_id, note_ids = self._identity_map(scan)
        scanned_ids = set(note_ids.values())
        links, counts = self._resolved_graph(scan, note_ids, now)
        tags, note_tags = self._tag_rows(scan, note_ids, now)

        created = 0
        matched = 0
        updated = 0
        note_rows = []
        for note in scan.notes:
            note_id = note_ids[note.path_key]
            existing = existing_by_id.get(note_id) or existing_notes.get(note.path_key)
            if existing is None:
                action = "created"
                created_at = now
                created += 1
            else:
                created_at = existing.created_at
                if (
                    existing.source_hash == note.source_hash
                    and existing.relative_path == note.relative_path
                    and existing.title == note.title
                    and existing.note_type == note.note_type
                    and existing.confidence == note.confidence
                    and existing.revision_status == note.revision_status
                ):
                    action = "matched"
                    matched += 1
                else:
                    action = "updated"
                    updated += 1
            note_rows.append(
                {
                    "id": note_id,
                    "relative_path": note.relative_path,
                    "path_key": note.path_key,
                    "title": note.title,
                    "note_type": note.note_type,
                    "confidence": note.confidence,
                    "revision_status": note.revision_status,
                    "source_hash": note.source_hash,
                    "file_mtime_ns": note.file_mtime_ns,
                    "frontmatter_extra": dict(note.frontmatter_extra),
                    "created_at": created_at,
                    "action": action,
                }
            )

        missing = tuple(
            sorted(
                item.id
                for item in self.repository.list_notes(vault_id)
                if item.id not in scanned_ids
            )
        )

        self.repository.apply_snapshot(
            vault={
                "id": vault_id,
                "name": scan.vault_name,
                "root_path": scan.vault_root,
                "path_key": scan.vault_key,
                "created_at": (
                    self.repository.get_vault(vault_id).created_at
                    if self.repository.get_vault(vault_id) is not None
                    else now
                ),
            },
            notes=tuple(note_rows),
            links=links,
            tags=tags,
            note_tags=note_tags,
            scanned_at=now,
        )

        return VaultRegistryResult(
            vault_id=vault_id,
            vault_key=scan.vault_key,
            created=created,
            matched=matched,
            updated=updated,
            missing_registry_ids=missing,
            tag_count=len(tags),
            resolved_link_count=counts["resolved"],
            unresolved_link_count=counts["unresolved"],
            ambiguous_link_count=counts["ambiguous"],
            external_link_count=counts["external"],
            blocking_issue_count=scan.blocking_issue_count,
            warning_count=scan.warning_count,
            scan_manifest_hash=scan.manifest_hash,
        )
