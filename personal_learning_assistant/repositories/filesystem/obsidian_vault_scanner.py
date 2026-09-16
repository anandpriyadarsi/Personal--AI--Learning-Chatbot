"""Read-only Obsidian Markdown scanner for Phase 5.3.

The scanner parses metadata, tags and links without modifying vault bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
import uuid
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union
from urllib.parse import unquote, urlsplit

from personal_learning_assistant.domain.obsidian_vault_models import (
    NoteLinkIntent,
    VaultNoteFingerprint,
    VaultScanIssue,
    VaultScanResult,
)


PathLike = Union[str, os.PathLike]
DEFAULT_EXCLUDED_FOLDERS = {
    ".obsidian",
    ".trash",
    ".git",
    "node_modules",
}
_WIKI_LINK = re.compile(r"\[\[([^\[\]\r\n]+)\]\]")
_MARKDOWN_LINK = re.compile(r"(?<!!)\[([^\]\r\n]*)\]\(([^)\r\n]+)\)")
_BARE_URL = re.compile(r"(?<![\w\"'(])(https?://[^\s<>\])]+)")
_INLINE_TAG = re.compile(r"(?<![\w/#])#([\w][\w/-]*)", re.UNICODE)
_HEADING = re.compile(r"^\s*#\s+(.+?)\s*$")
_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)

_REVISION_ALIASES = {
    "": "unreviewed",
    "unreviewed": "unreviewed",
    "not_started": "unreviewed",
    "not-started": "unreviewed",
    "not started": "unreviewed",
    "learning": "learning",
    "in_progress": "learning",
    "in-progress": "learning",
    "in progress": "learning",
    "needs_practice": "needs_practice",
    "needs-practice": "needs_practice",
    "needs practice": "needs_practice",
    "needs_review": "needs_practice",
    "needs-review": "needs_practice",
    "needs review": "needs_practice",
    "review_due": "review_due",
    "review-due": "review_due",
    "review due": "review_due",
    "revised": "revised",
    "mastered": "mastered",
}


class ObsidianVaultScannerError(RuntimeError):
    pass


class ObsidianVaultRootError(ObsidianVaultScannerError):
    pass


def normalize_relative_path(value: str) -> str:
    text = unicodedata.normalize("NFC", str(value or "").replace("\\", "/").strip())
    while text.startswith("./"):
        text = text[2:]
    text = "/".join(part for part in text.split("/") if part not in ("", "."))
    if not text or text == ".." or text.startswith("../") or "/../" in text:
        raise ValueError("vault-relative path is empty or escapes the vault")
    return text


def normalized_note_path_key(relative_path: str) -> str:
    return normalize_relative_path(relative_path).casefold()


def normalized_note_reference(value: str) -> str:
    text = unquote(str(value or "").strip().replace("\\", "/"))
    if text.lower().endswith(".md"):
        text = text[:-3]
    text = normalize_relative_path(text)
    return text.casefold()


def normalized_basename(value: str) -> str:
    name = normalize_relative_path(value).rsplit("/", 1)[-1]
    if name.lower().endswith(".md"):
        name = name[:-3]
    return unicodedata.normalize("NFC", name).casefold()


def _hash_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _strip_quotes(value: str) -> str:
    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    return text


def _simple_list(value: str) -> Tuple[str, ...]:
    text = str(value or "").strip()
    if not text:
        return ()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
        return tuple(
            _strip_quotes(item.strip())
            for item in text.split(",")
            if item.strip()
        )
    return (_strip_quotes(text),)


def _parse_frontmatter(lines: Sequence[str]):
    if not lines:
        return {}, "", 0, ()
    first = lines[0].lstrip("\ufeff").strip()
    if first != "---":
        return {}, "", 0, ()

    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() in ("---", "..."):
            end = index
            break
    if end is None:
        issue = VaultScanIssue(
            severity="warning",
            category="unterminated_frontmatter",
            relative_path="",
            message="opening YAML frontmatter delimiter has no closing delimiter",
        )
        return {}, "", 0, (issue,)

    raw_lines = list(lines[1:end])
    values: Dict[str, object] = {}
    current_key = None
    list_values: Dict[str, List[str]] = {}

    for raw_line in raw_lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if raw_line[:1].isspace() and stripped.startswith("-") and current_key:
            list_values.setdefault(current_key, []).append(
                _strip_quotes(stripped[1:].strip())
            )
            continue
        if ":" not in raw_line:
            current_key = None
            continue
        key, raw_value = raw_line.split(":", 1)
        key = key.strip()
        if not key:
            current_key = None
            continue
        current_key = key
        raw_value = raw_value.strip()
        if raw_value:
            listed = _simple_list(raw_value)
            values[key] = listed if len(listed) > 1 or raw_value.startswith("[") else listed[0]
        else:
            values[key] = ""
            list_values.setdefault(key, [])

    for key, items in list_values.items():
        if items:
            values[key] = tuple(items)

    raw_text = "\n".join(raw_lines)
    return values, raw_text, end + 1, ()


def _metadata_value(values: Mapping[str, object], *keys: str):
    lowered = {str(key).casefold(): value for key, value in values.items()}
    for key in keys:
        if key.casefold() in lowered:
            return lowered[key.casefold()]
    return None


def _metadata_strings(value) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return _simple_list(str(value))


def _mask_inline_code(line: str) -> str:
    result = list(line)
    active = False
    tick_start = None
    index = 0
    while index < len(line):
        if line[index] == "`":
            if not active:
                active = True
                tick_start = index
            else:
                for pos in range(tick_start, index + 1):
                    result[pos] = " "
                active = False
                tick_start = None
        index += 1
    if active and tick_start is not None:
        for pos in range(tick_start, len(result)):
            result[pos] = " "
    return "".join(result)


def _split_wiki_target(raw_target: str):
    target = str(raw_target or "").strip()
    if "|" in target:
        target = target.split("|", 1)[0].strip()
    heading = ""
    block_id = ""
    if "^" in target:
        target, block_id = target.split("^", 1)
        block_id = block_id.strip()
    if "#" in target:
        target, heading = target.split("#", 1)
        heading = heading.strip()
    return target.strip(), heading, block_id


def _markdown_target(raw_target: str):
    target = str(raw_target or "").strip()
    if target.startswith("<") and ">" in target:
        target = target[1:target.index(">")]
    elif " " in target:
        target = target.split(" ", 1)[0]
    target = _strip_quotes(target.strip())
    parsed = urlsplit(target)
    if parsed.scheme in ("http", "https"):
        return "external_url", target, "", ""
    if parsed.scheme and parsed.scheme != "file":
        return "external", target, "", ""
    local = unquote(parsed.path or "")
    heading = unquote(parsed.fragment or "")
    return "markdown", local, heading, ""


def _extract_links_and_tags(lines: Sequence[str], body_start: int):
    links: List[NoteLinkIntent] = []
    tags = set()
    in_fence = False
    fence_marker = None
    occupied_spans: Dict[int, List[Tuple[int, int]]] = {}

    for line_index in range(body_start, len(lines)):
        original = lines[line_index]
        stripped = original.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = None
            continue
        if in_fence:
            continue

        line = _mask_inline_code(original)
        spans = occupied_spans.setdefault(line_index, [])

        for match in _WIKI_LINK.finditer(line):
            raw_target = match.group(1).strip()
            target, heading, block_id = _split_wiki_target(raw_target)
            if not target:
                continue
            links.append(
                NoteLinkIntent(
                    source_position="{}:{}".format(line_index + 1, match.start() + 1),
                    raw_target=target,
                    target_kind="wiki",
                    heading=heading,
                    block_id=block_id,
                )
            )
            spans.append((match.start(), match.end()))

        for match in _MARKDOWN_LINK.finditer(line):
            kind, target, heading, block_id = _markdown_target(match.group(2))
            if not target:
                continue
            links.append(
                NoteLinkIntent(
                    source_position="{}:{}".format(line_index + 1, match.start() + 1),
                    raw_target=target,
                    target_kind=kind,
                    heading=heading,
                    block_id=block_id,
                )
            )
            spans.append((match.start(), match.end()))

        for match in _BARE_URL.finditer(line):
            if any(start <= match.start() < end for start, end in spans):
                continue
            links.append(
                NoteLinkIntent(
                    source_position="{}:{}".format(line_index + 1, match.start() + 1),
                    raw_target=match.group(1),
                    target_kind="external_url",
                )
            )

        for match in _INLINE_TAG.finditer(line):
            if stripped.startswith("#") and match.start() == len(original) - len(stripped):
                continue
            tag = unicodedata.normalize("NFC", match.group(1)).strip()
            if tag:
                tags.add(tag)

    return tuple(links), tuple(sorted(tags, key=lambda item: item.casefold()))


def _title(lines: Sequence[str], body_start: int, frontmatter: Mapping[str, object], path: Path):
    front_title = _metadata_value(frontmatter, "title")
    if front_title is not None and str(front_title).strip():
        return str(front_title).strip()
    in_fence = False
    fence_marker = None
    for line in lines[body_start:]:
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = None
            continue
        if in_fence:
            continue
        match = _HEADING.match(line)
        if match:
            return match.group(1).strip()
    return path.stem


def _revision_status(raw_value):
    raw = "" if raw_value is None else str(raw_value).strip()
    normalized = raw.casefold().replace("_", " ")
    alias_key = normalized.replace("  ", " ")
    candidates = (
        raw.casefold(),
        alias_key,
        alias_key.replace(" ", "_"),
        alias_key.replace(" ", "-"),
    )
    for candidate in candidates:
        if candidate in _REVISION_ALIASES:
            return _REVISION_ALIASES[candidate], None
    return "unreviewed", raw


def _confidence(raw_value):
    if raw_value is None or str(raw_value).strip() == "":
        return None, None
    try:
        value = int(str(raw_value).strip())
    except ValueError:
        return None, str(raw_value)
    if 0 <= value <= 5:
        return value, None
    return None, str(raw_value)


def _assistant_id(raw_value):
    if raw_value is None or str(raw_value).strip() == "":
        return None, None
    value = str(raw_value).strip()
    if not _UUID.fullmatch(value):
        return None, value
    return str(uuid.UUID(value)), None


def _manifest_hash(notes: Iterable[VaultNoteFingerprint]) -> str:
    digest = hashlib.sha256()
    for note in sorted(notes, key=lambda item: item.path_key):
        row = "\0".join(
            (
                note.path_key,
                note.source_hash,
                str(note.file_mtime_ns),
                note.title,
                note.note_type,
                "" if note.confidence is None else str(note.confidence),
                note.revision_status,
                note.assistant_id or "",
                "\x1f".join(note.tags),
            )
        )
        digest.update(row.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


class ObsidianVaultScanner:
    """Scan one explicit vault root without writing Markdown."""

    def __init__(
        self,
        vault_key: str,
        vault_root: PathLike,
        *,
        vault_name: Optional[str] = None,
        excluded_folders: Iterable[str] = DEFAULT_EXCLUDED_FOLDERS,
    ):
        key = str(vault_key or "").strip().casefold()
        if not key or "/" in key or "\\" in key:
            raise ValueError("vault_key must be one non-empty logical key")
        self.vault_key = key
        self.vault_root = Path(vault_root).resolve(strict=False)
        self.vault_name = str(vault_name or self.vault_root.name or key).strip()
        self.excluded_folders = set(str(item) for item in excluded_folders)

    def _validate_root(self):
        if not self.vault_root.exists():
            raise ObsidianVaultRootError(
                "vault root does not exist: {}".format(self.vault_root)
            )
        if self.vault_root.is_symlink():
            raise ObsidianVaultRootError("vault root must not be a symlink")
        if not self.vault_root.is_dir():
            raise ObsidianVaultRootError("vault root is not a directory")

    def scan(self) -> VaultScanResult:
        self._validate_root()
        notes = []
        issues = []
        ignored_symlinks = 0
        path_keys = {}
        assistant_ids = {}

        for current_root, dir_names, file_names in os.walk(
            str(self.vault_root), topdown=True, followlinks=False
        ):
            current = Path(current_root)
            kept_dirs = []
            for name in sorted(dir_names):
                candidate = current / name
                if name in self.excluded_folders:
                    continue
                if candidate.is_symlink():
                    ignored_symlinks += 1
                    continue
                kept_dirs.append(name)
            dir_names[:] = kept_dirs

            for file_name in sorted(file_names):
                if not file_name.lower().endswith(".md"):
                    continue
                path = current / file_name
                if path.is_symlink():
                    ignored_symlinks += 1
                    continue
                try:
                    before = path.stat()
                    raw = path.read_bytes()
                    after = path.stat()
                except OSError as error:
                    relative = "<unavailable>"
                    try:
                        relative = normalize_relative_path(
                            path.relative_to(self.vault_root).as_posix()
                        )
                    except Exception:
                        pass
                    issues.append(
                        VaultScanIssue(
                            severity="blocking",
                            category="unreadable_note",
                            relative_path=relative,
                            message=type(error).__name__,
                        )
                    )
                    continue

                relative_path = normalize_relative_path(
                    path.relative_to(self.vault_root).as_posix()
                )
                path_key = normalized_note_path_key(relative_path)
                if (
                    before.st_size != after.st_size
                    or before.st_mtime_ns != after.st_mtime_ns
                ):
                    issues.append(
                        VaultScanIssue(
                            severity="blocking",
                            category="unstable_note",
                            relative_path=relative_path,
                            message="note changed while being fingerprinted",
                        )
                    )
                    continue
                try:
                    text = raw.decode("utf-8-sig")
                except UnicodeDecodeError:
                    issues.append(
                        VaultScanIssue(
                            severity="blocking",
                            category="non_utf8_note",
                            relative_path=relative_path,
                            message="Markdown is not valid UTF-8",
                        )
                    )
                    continue

                if path_key in path_keys and path_keys[path_key] != relative_path:
                    issues.append(
                        VaultScanIssue(
                            severity="blocking",
                            category="path_key_collision",
                            relative_path=relative_path,
                            message="two Markdown files normalize to one path identity",
                        )
                    )
                    continue
                path_keys[path_key] = relative_path

                lines = text.splitlines()
                frontmatter, raw_frontmatter, body_start, front_issues = _parse_frontmatter(lines)
                for issue in front_issues:
                    issues.append(
                        VaultScanIssue(
                            severity=issue.severity,
                            category=issue.category,
                            relative_path=relative_path,
                            message=issue.message,
                        )
                    )

                raw_assistant_id = _metadata_value(frontmatter, "assistant_id")
                assistant_id, invalid_assistant = _assistant_id(raw_assistant_id)
                if invalid_assistant is not None:
                    issues.append(
                        VaultScanIssue(
                            severity="warning",
                            category="invalid_assistant_id",
                            relative_path=relative_path,
                            message="assistant_id is not a valid UUID",
                        )
                    )
                if assistant_id:
                    previous = assistant_ids.get(assistant_id)
                    if previous and previous != relative_path:
                        issues.append(
                            VaultScanIssue(
                                severity="blocking",
                                category="duplicate_assistant_id",
                                relative_path=relative_path,
                                message="assistant_id is also present on another note",
                            )
                        )
                    assistant_ids[assistant_id] = relative_path

                confidence, invalid_confidence = _confidence(
                    _metadata_value(frontmatter, "confidence")
                )
                if invalid_confidence is not None:
                    issues.append(
                        VaultScanIssue(
                            severity="warning",
                            category="invalid_confidence",
                            relative_path=relative_path,
                            message="confidence is outside 0-5 or is not an integer",
                        )
                    )

                revision_status, raw_unknown_status = _revision_status(
                    _metadata_value(frontmatter, "revision_status", "status")
                )
                if raw_unknown_status:
                    issues.append(
                        VaultScanIssue(
                            severity="warning",
                            category="unknown_revision_status",
                            relative_path=relative_path,
                            message="revision status is preserved as raw evidence",
                        )
                    )

                links, inline_tags = _extract_links_and_tags(lines, body_start)
                front_tags = _metadata_strings(_metadata_value(frontmatter, "tags", "tag"))
                tags_by_key = {}
                for tag in tuple(front_tags) + tuple(inline_tags):
                    cleaned = unicodedata.normalize("NFC", str(tag).strip().lstrip("#"))
                    if cleaned:
                        tags_by_key.setdefault(cleaned.casefold(), cleaned)
                tags = tuple(
                    tags_by_key[key]
                    for key in sorted(tags_by_key)
                )

                note_type_value = _metadata_value(frontmatter, "note_type", "type")
                note_type = str(note_type_value or "note").strip() or "note"

                extra = {
                    "frontmatter_parser": "phase5.3-subset-v1",
                    "raw_frontmatter": raw_frontmatter,
                    "raw_revision_status": raw_unknown_status or "",
                    "raw_confidence": invalid_confidence or "",
                    "raw_assistant_id": invalid_assistant or "",
                }

                notes.append(
                    VaultNoteFingerprint(
                        relative_path=relative_path,
                        path_key=path_key,
                        absolute_path=str(path.resolve(strict=False)),
                        source_hash=_hash_bytes(raw),
                        file_mtime_ns=int(after.st_mtime_ns),
                        title=_title(lines, body_start, frontmatter, path),
                        note_type=note_type,
                        confidence=confidence,
                        revision_status=revision_status,
                        assistant_id=assistant_id,
                        tags=tags,
                        frontmatter_extra=extra,
                        links=links,
                    )
                )

        ordered_notes = tuple(sorted(notes, key=lambda item: item.path_key))
        ordered_issues = tuple(
            sorted(
                issues,
                key=lambda item: (
                    item.relative_path,
                    item.severity,
                    item.category,
                ),
            )
        )
        return VaultScanResult(
            vault_key=self.vault_key,
            vault_name=self.vault_name,
            vault_root=str(self.vault_root),
            notes=ordered_notes,
            issues=ordered_issues,
            ignored_symlinks=ignored_symlinks,
            manifest_hash=_manifest_hash(ordered_notes),
        )
