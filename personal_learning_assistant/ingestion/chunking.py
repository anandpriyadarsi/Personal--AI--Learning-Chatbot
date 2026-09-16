"""Deterministic Phase 5.6 chunking with machine-readable locators."""
from __future__ import annotations
import hashlib
import json
from typing import Iterable, Mapping, Tuple
from personal_learning_assistant.domain.ingestion_models import ExtractedUnit, PreparedChunk

CHUNKER_VERSION = "char-window-v1"
LOCATOR_PREFIX = ";locator=v1:"

def encode_chunk_type(kind: str, locator: Mapping[str, object]) -> str:
    payload = json.dumps(dict(locator or {}), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(kind or "text") + LOCATOR_PREFIX + payload

def decode_chunk_type(value: str):
    text = str(value or "")
    if LOCATOR_PREFIX not in text:
        return text, {}
    kind, raw = text.split(LOCATOR_PREFIX, 1)
    try:
        locator = json.loads(raw)
    except json.JSONDecodeError:
        return kind, {}
    return kind, locator if isinstance(locator, dict) else {}

def _window(text: str, max_chars: int):
    start = 0; length = len(text)
    while start < length:
        while start < length and text[start].isspace(): start += 1
        if start >= length: break
        end = min(length, start + max_chars)
        if end < length:
            floor = start + max_chars // 2
            split_at = max(text.rfind("\n", floor, end), text.rfind(" ", floor, end))
            if split_at > start: end = split_at
        raw = text[start:end]
        left = len(raw) - len(raw.lstrip()); right = raw.rstrip()
        actual_start = start + left; actual_end = start + len(right)
        chunk = text[actual_start:actual_end]
        if chunk: yield actual_start, actual_end, chunk
        start = max(end, actual_end)

def prepare_chunks(units: Iterable[ExtractedUnit], *, max_chars: int = 1600) -> Tuple[PreparedChunk, ...]:
    if max_chars < 200: raise ValueError("max_chars must be at least 200")
    result = []; ordinal = 0
    for unit_index, unit in enumerate(units):
        text = str(unit.text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text: continue
        base = dict(unit.locator or {}); base["unit"] = unit_index
        if unit.section_path: base.setdefault("section", unit.section_path)
        if unit.slide_number is not None: base.setdefault("slide", unit.slide_number)
        if unit.timestamp_start_ms is not None: base.setdefault("timestamp_start_ms", unit.timestamp_start_ms)
        if unit.timestamp_end_ms is not None: base.setdefault("timestamp_end_ms", unit.timestamp_end_ms)
        for char_start, char_end, chunk_text in _window(text, max_chars):
            locator = dict(base); locator["char_start"] = char_start; locator["char_end"] = char_end
            result.append(PreparedChunk(ordinal=ordinal, text=chunk_text, text_hash=hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(), page_number=unit.page_number, char_start=char_start, char_end=char_end, chunk_type=encode_chunk_type(unit.kind, locator), locator=locator))
            ordinal += 1
    return tuple(result)
