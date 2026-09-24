"""Pure deterministic note-connection composition for Phase 7.5.15.7.

This module ranks already-read NoteCard metadata plus the current note's live
wikilink/backlink evidence. It performs no file, database, network, AI, or
index operations.
"""
from __future__ import annotations

import unicodedata


MAX_RELATED_NOTES = 8


def _key(value) -> str:
    return unicodedata.normalize(
        "NFC",
        " ".join(str(value or "").split()),
    ).casefold()


def _path_key(value) -> str:
    return _key(str(value or "").replace("\\", "/"))


def _tag_map(values):
    result = {}
    for raw in values or ():
        text = " ".join(str(raw or "").strip().lstrip("#").split())
        if text:
            result.setdefault(_key(text), text)
    return result


def _link_paths(wikilinks):
    return {
        _path_key(item.get("resolved_path"))
        for item in wikilinks or ()
        if str(item.get("resolved_path") or "").strip()
    }


def _backlink_paths(backlinks):
    return {
        _path_key(item.get("relative_path"))
        for item in backlinks or ()
        if str(item.get("relative_path") or "").strip()
    }


def _reason_bundle(current, candidate, outgoing_paths, backlink_paths):
    reasons = []
    score = 0
    candidate_path = _path_key(candidate.relative_path)

    if candidate_path in outgoing_paths:
        reasons.append("Linked from this note")
        score += 100
    if candidate_path in backlink_paths:
        reasons.append("Links to this note")
        score += 90

    current_course = _key(current.course)
    if current_course and current_course == _key(candidate.course):
        reasons.append("Same course")
        score += 20

    current_topic = _key(current.topic)
    if current_topic and current_topic == _key(candidate.topic):
        reasons.append("Same topic")
        score += 30

    current_source = _key(getattr(current, "source", ""))
    if current_source and current_source == _key(getattr(candidate, "source", "")):
        reasons.append("Same source")
        score += 15

    current_tags = _tag_map(current.tags)
    candidate_tags = _tag_map(candidate.tags)
    shared_keys = sorted(set(current_tags).intersection(candidate_tags))
    for tag_key in shared_keys[:3]:
        reasons.append("Shared tag: {}".format(current_tags[tag_key]))
        score += 3

    return score, reasons


def _facet(kind, label, current_path, cards):
    normalized = _key(label)
    if not normalized:
        return None

    count = 0
    current_key = _path_key(current_path)
    for card in cards:
        if _path_key(card.relative_path) == current_key:
            continue
        value = getattr(card, kind, "")
        if _key(value) == normalized:
            count += 1
    return {
        "kind": kind,
        "label": str(label),
        "peer_count": count,
    }


def build_connection_context(current, cards, *, wikilinks=(), backlinks=()):
    """Return explainable related-note ranking and course/topic/source facets."""

    ordered_cards = tuple(cards or ())
    outgoing_paths = _link_paths(wikilinks)
    backlink_paths = _backlink_paths(backlinks)
    current_path = _path_key(current.relative_path)
    ranked = []

    for candidate in ordered_cards:
        if _path_key(candidate.relative_path) == current_path:
            continue
        score, reasons = _reason_bundle(
            current,
            candidate,
            outgoing_paths,
            backlink_paths,
        )
        if score <= 0:
            continue
        ranked.append(
            (
                -score,
                _key(candidate.title),
                _path_key(candidate.relative_path),
                {
                    "relative_path": str(candidate.relative_path),
                    "title": str(candidate.title),
                    "course": str(candidate.course),
                    "topic": str(candidate.topic),
                    "source": str(getattr(candidate, "source", "")),
                    "note_type": str(candidate.note_type or "note"),
                    "reasons": tuple(reasons),
                },
            )
        )

    ranked.sort(key=lambda item: item[:3])
    related_notes = tuple(
        item[3] for item in ranked[:MAX_RELATED_NOTES]
    )

    facets = []
    for kind, label in (
        ("course", current.course),
        ("topic", current.topic),
        ("source", getattr(current, "source", "")),
    ):
        item = _facet(kind, label, current.relative_path, ordered_cards)
        if item is not None:
            facets.append(item)

    return {
        "related_notes": related_notes,
        "facets": tuple(facets),
    }
