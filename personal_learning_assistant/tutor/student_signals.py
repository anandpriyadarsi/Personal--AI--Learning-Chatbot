"""Bounded Tutor learning-signal history and cross-session aggregation.

Signals are observations from tutoring interactions. They are not mastery,
grades, topic progress, or authoritative learning memory.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping


SIGNAL_HISTORY_KEY = "tutor_signal_history_v1"
SIGNAL_HISTORY_VERSION = 1
_MAX_EVENTS_PER_SESSION = 40
_MAX_TEXT = 240
_STABLE_MIN_SESSIONS = 2

_ALLOWED_KINDS = {
    "answer_correct",
    "answer_partial",
    "answer_incorrect",
    "answer_unclear",
    "hint_requested",
    "doubt",
    "misconception",
    "math_verified",
    "math_repaired",
    "math_blocked",
}


@dataclass(frozen=True)
class StableTutorSignal:
    kind: str
    text: str
    event_count: int
    session_count: int
    first_observed_at: str
    last_observed_at: str
    provenance: tuple[str, ...]


def _clean(value, limit=_MAX_TEXT):
    return " ".join(str(value or "").strip().split())[: int(limit)]


def _key(kind, text):
    return (str(kind or "").strip().casefold(), _clean(text).casefold())


def load_signal_history(metadata):
    raw = dict(metadata or {}).get(SIGNAL_HISTORY_KEY, ())
    if not isinstance(raw, (list, tuple)):
        return ()
    cleaned = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        kind = _clean(item.get("kind"), 50).casefold()
        if kind not in _ALLOWED_KINDS:
            continue
        cleaned.append(
            {
                "version": SIGNAL_HISTORY_VERSION,
                "kind": kind,
                "text": _clean(item.get("text")),
                "session_id": _clean(item.get("session_id"), 120),
                "turn_id": _clean(item.get("turn_id"), 120),
                "course_id": _clean(item.get("course_id"), 120),
                "topic_id": _clean(item.get("topic_id"), 120),
                "intent": _clean(item.get("intent"), 80),
                "observed_at": _clean(item.get("observed_at"), 80),
            }
        )
    return tuple(cleaned[-_MAX_EVENTS_PER_SESSION:])


def derive_turn_signals(
    *,
    session,
    assistant_turn,
    teaching_intent,
    adaptive_state,
):
    """Derive deterministic observations from one completed Tutor exchange."""
    state = dict(adaptive_state or {})
    base = {
        "version": SIGNAL_HISTORY_VERSION,
        "session_id": str(session.session_id or ""),
        "turn_id": str(assistant_turn.turn_id or ""),
        "course_id": str(session.course_id or ""),
        "topic_id": str(session.topic_id or ""),
        "intent": str(teaching_intent or ""),
        "observed_at": str(assistant_turn.created_at or ""),
    }
    events = []

    def add(kind, text=""):
        if kind not in _ALLOWED_KINDS:
            return
        event = dict(base)
        event["kind"] = kind
        event["text"] = _clean(text)
        events.append(event)

    if str(teaching_intent or "") == "hint":
        add("hint_requested")

    answer_status = _clean(state.get("answer_status"), 40).casefold()
    if answer_status in {"correct", "partial", "incorrect", "unclear"}:
        add("answer_" + answer_status, state.get("last_evaluation_reason"))

    doubt = _clean(state.get("unresolved_doubt"))
    if doubt:
        add("doubt", doubt)

    misconception = _clean(state.get("last_misconception"))
    if misconception:
        add("misconception", misconception)

    math_status = _clean(state.get("last_math_verification"), 40).casefold()
    if math_status == "passed":
        add("math_verified")
    elif math_status == "repaired":
        add("math_repaired")
    elif math_status == "blocked":
        add("math_blocked")

    # One event per kind/text for a turn.
    unique = []
    seen = set()
    for event in events:
        event_key = (
            event["turn_id"],
            event["kind"],
            event["text"].casefold(),
        )
        if event_key not in seen:
            unique.append(event)
            seen.add(event_key)
    return tuple(unique)


def append_signal_history(metadata, events):
    result = dict(metadata or {})
    existing = list(load_signal_history(result))
    seen = {
        (
            item["turn_id"],
            item["kind"],
            item["text"].casefold(),
        )
        for item in existing
    }
    for event in tuple(events or ()):
        if not isinstance(event, Mapping):
            continue
        kind = _clean(event.get("kind"), 50).casefold()
        if kind not in _ALLOWED_KINDS:
            continue
        normalized = {
            "version": SIGNAL_HISTORY_VERSION,
            "kind": kind,
            "text": _clean(event.get("text")),
            "session_id": _clean(event.get("session_id"), 120),
            "turn_id": _clean(event.get("turn_id"), 120),
            "course_id": _clean(event.get("course_id"), 120),
            "topic_id": _clean(event.get("topic_id"), 120),
            "intent": _clean(event.get("intent"), 80),
            "observed_at": _clean(event.get("observed_at"), 80),
        }
        event_key = (
            normalized["turn_id"],
            normalized["kind"],
            normalized["text"].casefold(),
        )
        if event_key in seen:
            continue
        existing.append(normalized)
        seen.add(event_key)

    result[SIGNAL_HISTORY_KEY] = existing[-_MAX_EVENTS_PER_SESSION:]
    return result


def fallback_session_signals(*, session_id, course_id, topic_id, updated_at, state):
    """Project one legacy final-state signal set when history is absent."""
    state = dict(state or {})
    base = {
        "version": SIGNAL_HISTORY_VERSION,
        "session_id": str(session_id or ""),
        "turn_id": "",
        "course_id": str(course_id or ""),
        "topic_id": str(topic_id or ""),
        "intent": _clean(state.get("last_intent"), 80),
        "observed_at": str(updated_at or ""),
    }
    events = []

    def add(kind, text=""):
        event = dict(base)
        event["kind"] = kind
        event["text"] = _clean(text)
        events.append(event)

    status = _clean(state.get("answer_status"), 40).casefold()
    if status in {"correct", "partial", "incorrect", "unclear"}:
        add("answer_" + status, state.get("last_evaluation_reason"))

    if _clean(state.get("last_intent"), 40).casefold() == "hint":
        add("hint_requested")

    doubt = _clean(state.get("unresolved_doubt"))
    if doubt:
        add("doubt", doubt)

    misconception = _clean(state.get("last_misconception"))
    if misconception:
        add("misconception", misconception)

    math_status = _clean(state.get("last_math_verification"), 40).casefold()
    if math_status == "passed":
        add("math_verified")
    elif math_status == "repaired":
        add("math_repaired")
    elif math_status == "blocked":
        add("math_blocked")

    return tuple(events)


def aggregate_stable_signals(session_event_groups):
    """Return only patterns observed in at least two distinct sessions."""
    grouped = defaultdict(list)

    for session_id, events in tuple(session_event_groups or ()):
        session_id = str(session_id or "")
        for event in tuple(events or ()):
            if not isinstance(event, Mapping):
                continue
            kind = _clean(event.get("kind"), 50).casefold()
            if kind not in _ALLOWED_KINDS:
                continue
            text = _clean(event.get("text"))
            grouped[_key(kind, text)].append(
                {
                    "kind": kind,
                    "text": text,
                    "session_id": session_id or _clean(
                        event.get("session_id"), 120
                    ),
                    "turn_id": _clean(event.get("turn_id"), 120),
                    "observed_at": _clean(event.get("observed_at"), 80),
                }
            )

    stable = []
    for (_kind_key, _text_key), events in grouped.items():
        sessions = {
            item["session_id"]
            for item in events
            if item["session_id"]
        }
        if len(sessions) < _STABLE_MIN_SESSIONS:
            continue

        ordered = sorted(
            events,
            key=lambda item: (
                item["observed_at"],
                item["session_id"],
                item["turn_id"],
            ),
        )
        provenance = []
        for item in ordered:
            ref = "{}:{}".format(
                item["session_id"],
                item["turn_id"] or "session-state",
            )
            if ref not in provenance:
                provenance.append(ref)

        stable.append(
            StableTutorSignal(
                kind=ordered[-1]["kind"],
                text=ordered[-1]["text"],
                event_count=len(events),
                session_count=len(sessions),
                first_observed_at=ordered[0]["observed_at"],
                last_observed_at=ordered[-1]["observed_at"],
                provenance=tuple(provenance[:8]),
            )
        )

    stable.sort(
        key=lambda item: (
            -item.session_count,
            -item.event_count,
            item.kind,
            item.text.casefold(),
        )
    )
    return tuple(stable[:8])


def stable_signal_mapping(signal):
    return {
        "kind": str(signal.kind or ""),
        "text": str(signal.text or ""),
        "event_count": int(signal.event_count),
        "session_count": int(signal.session_count),
        "first_observed_at": str(signal.first_observed_at or ""),
        "last_observed_at": str(signal.last_observed_at or ""),
        "provenance": tuple(signal.provenance or ()),
    }
