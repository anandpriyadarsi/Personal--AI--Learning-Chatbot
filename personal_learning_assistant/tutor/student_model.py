"""Read-only persistent student-model projection for ANVAYA Tutor 2.2.

This module does not create or promote mastery. It summarizes already-persisted
Tutor session signals and existing academic memory/progress rows for bounded
provider context.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Mapping

from personal_learning_assistant.tutor.adaptive_state import load_adaptive_state
from personal_learning_assistant.tutor.student_signals import (
    aggregate_stable_signals,
    fallback_session_signals,
    load_signal_history,
    stable_signal_mapping,
)


_MAX_SESSIONS = 12
_MAX_TEXT = 280
_MAX_ITEMS = 5


@dataclass(frozen=True)
class PersistentStudentModel:
    course_id: str
    previous_sessions_considered: int
    answer_status_counts: Mapping[str, int]
    recurring_doubts: tuple[str, ...]
    recurring_misconceptions: tuple[str, ...]
    verified_calculation_count: int
    repaired_calculation_count: int
    blocked_calculation_count: int
    learning_memory: tuple[str, ...]
    recent_progress: tuple[str, ...]
    stable_signals: tuple[Mapping[str, object], ...] = ()


def empty_student_model(course_id=""):
    return PersistentStudentModel(
        course_id=str(course_id or ""),
        previous_sessions_considered=0,
        answer_status_counts={},
        recurring_doubts=(),
        recurring_misconceptions=(),
        verified_calculation_count=0,
        repaired_calculation_count=0,
        blocked_calculation_count=0,
        learning_memory=(),
        recent_progress=(),
        stable_signals=(),
    )


def _clean(value, limit=_MAX_TEXT):
    return " ".join(str(value or "").strip().split())[: int(limit)]


def _normalized_key(value):
    return _clean(value).casefold()


def _top_text(counter, original, *, minimum=1):
    items = sorted(
        (
            (count, key, original[key])
            for key, count in counter.items()
            if count >= int(minimum) and key in original
        ),
        key=lambda item: (-item[0], item[1]),
    )
    return tuple(item[2] for item in items[:_MAX_ITEMS])


def _safe_json_object(raw):
    try:
        value = json.loads(str(raw or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _session_projection(connection, session):
    if not session.course_id:
        return {
            "count": 0,
            "answer_status_counts": {},
            "recurring_doubts": (),
            "recurring_misconceptions": (),
            "math": Counter(),
            "stable_signals": (),
        }

    rows = connection.execute(
        "SELECT id,course_id,topic_id,metadata_json,updated_at FROM tutor_sessions "
        "WHERE course_id=? AND id<>? "
        "ORDER BY updated_at DESC,id DESC LIMIT ?",
        (
            str(session.course_id),
            str(session.session_id),
            _MAX_SESSIONS,
        ),
    ).fetchall()

    answer_counts = Counter()
    doubt_counts = Counter()
    doubt_original = {}
    misconception_counts = Counter()
    misconception_original = {}
    math_counts = Counter()
    session_event_groups = []

    for row in rows:
        metadata = _safe_json_object(row["metadata_json"])
        state = load_adaptive_state(metadata)

        answer_status = _clean(state.get("answer_status"), 40).casefold()
        if answer_status in {"correct", "partial", "incorrect", "unclear"}:
            answer_counts[answer_status] += 1

        doubt = _clean(state.get("unresolved_doubt"))
        if doubt:
            key = _normalized_key(doubt)
            doubt_counts[key] += 1
            doubt_original.setdefault(key, doubt)

        misconception = _clean(state.get("last_misconception"))
        if misconception:
            key = _normalized_key(misconception)
            misconception_counts[key] += 1
            misconception_original.setdefault(key, misconception)

        math_status = _clean(
            state.get("last_math_verification"), 40
        ).casefold()
        if math_status in {"passed", "repaired", "blocked"}:
            math_counts[math_status] += 1

        events = load_signal_history(metadata)
        if not events:
            events = fallback_session_signals(
                session_id=str(row["id"]),
                course_id=str(row["course_id"] or ""),
                topic_id=str(row["topic_id"] or ""),
                updated_at=str(row["updated_at"] or ""),
                state=state,
            )
        session_event_groups.append((str(row["id"]), tuple(events)))

    stable_signals = tuple(
        stable_signal_mapping(item)
        for item in aggregate_stable_signals(session_event_groups)
    )

    return {
        "count": len(rows),
        "answer_status_counts": dict(answer_counts),
        "recurring_doubts": _top_text(
            doubt_counts,
            doubt_original,
            minimum=1,
        ),
        "recurring_misconceptions": _top_text(
            misconception_counts,
            misconception_original,
            minimum=1,
        ),
        "math": math_counts,
        "stable_signals": stable_signals,
    }


def _learning_memory_projection(connection, session):
    if not session.course_id:
        return ()

    params = [str(session.course_id)]
    topic_clause = ""
    if session.topic_id:
        topic_clause = " OR topic_id=?"
        params.append(str(session.topic_id))

    rows = connection.execute(
        "SELECT memory_text,kind,raw_topic,updated_at "
        "FROM learning_memory_entries "
        "WHERE archived_at IS NULL "
        "AND ((scope_type='course' AND scope_id=?)" + topic_clause + ") "
        "ORDER BY updated_at DESC,id DESC LIMIT ?",
        tuple(params + [_MAX_ITEMS]),
    ).fetchall()

    result = []
    for row in rows:
        memory = _clean(row["memory_text"])
        if not memory:
            continue
        kind = _clean(row["kind"], 60)
        topic = _clean(row["raw_topic"], 100)
        prefix = " / ".join(part for part in (kind, topic) if part)
        result.append(
            "{}: {}".format(prefix, memory) if prefix else memory
        )
    return tuple(result[:_MAX_ITEMS])


def _progress_projection(connection, session):
    if not session.course_id:
        return ()

    params = [str(session.course_id)]
    topic_clause = ""
    if session.topic_id:
        topic_clause = " AND t.id=?"
        params.append(str(session.topic_id))

    rows = connection.execute(
        "SELECT t.name AS topic_name,e.event_type,e.previous_status,"
        "e.new_status,e.confidence,e.occurred_at,e.note "
        "FROM topic_progress_events e "
        "JOIN topics t ON t.id=e.topic_id "
        "WHERE t.course_id=? AND t.deleted_at IS NULL" + topic_clause + " "
        "ORDER BY e.occurred_at DESC,e.id DESC LIMIT ?",
        tuple(params + [_MAX_ITEMS]),
    ).fetchall()

    result = []
    for row in rows:
        topic = _clean(row["topic_name"], 100) or "topic"
        event = _clean(row["event_type"], 80)
        previous = _clean(row["previous_status"], 50)
        new = _clean(row["new_status"], 50)
        confidence = row["confidence"]
        note = _clean(row["note"], 160)

        parts = [topic]
        if event:
            parts.append(event)
        if previous or new:
            parts.append("{} -> {}".format(previous or "?", new or "?"))
        if confidence is not None:
            parts.append("confidence {}".format(int(confidence)))
        if note:
            parts.append(note)
        result.append(" | ".join(parts))
    return tuple(result[:_MAX_ITEMS])


def build_persistent_student_model(repository, session):
    """Build a bounded profile with SELECT-only access to existing tables."""
    connection = getattr(repository, "connection", None)
    if connection is None or not session.course_id:
        return empty_student_model(session.course_id)

    historical = _session_projection(connection, session)
    memory = _learning_memory_projection(connection, session)
    progress = _progress_projection(connection, session)
    math = historical["math"]

    return PersistentStudentModel(
        course_id=str(session.course_id or ""),
        previous_sessions_considered=int(historical["count"]),
        answer_status_counts=dict(historical["answer_status_counts"]),
        recurring_doubts=tuple(historical["recurring_doubts"]),
        recurring_misconceptions=tuple(
            historical["recurring_misconceptions"]
        ),
        verified_calculation_count=int(math.get("passed", 0)),
        repaired_calculation_count=int(math.get("repaired", 0)),
        blocked_calculation_count=int(math.get("blocked", 0)),
        learning_memory=tuple(memory),
        recent_progress=tuple(progress),
        stable_signals=tuple(historical["stable_signals"]),
    )


def student_model_mapping(model):
    if model is None:
        return {}
    if isinstance(model, Mapping):
        return {
            "course_id": str(model.get("course_id") or ""),
            "previous_sessions_considered": int(
                model.get("previous_sessions_considered") or 0
            ),
            "answer_status_counts": dict(
                model.get("answer_status_counts") or {}
            ),
            "recurring_doubts": tuple(
                model.get("recurring_doubts") or ()
            ),
            "recurring_misconceptions": tuple(
                model.get("recurring_misconceptions") or ()
            ),
            "verified_calculation_count": int(
                model.get("verified_calculation_count") or 0
            ),
            "repaired_calculation_count": int(
                model.get("repaired_calculation_count") or 0
            ),
            "blocked_calculation_count": int(
                model.get("blocked_calculation_count") or 0
            ),
            "learning_memory": tuple(
                model.get("learning_memory") or ()
            ),
            "recent_progress": tuple(
                model.get("recent_progress") or ()
            ),
            "stable_signals": tuple(
                dict(item)
                for item in (model.get("stable_signals") or ())
                if isinstance(item, Mapping)
            ),
        }
    return {
        "course_id": str(model.course_id or ""),
        "previous_sessions_considered": int(
            model.previous_sessions_considered
        ),
        "answer_status_counts": dict(model.answer_status_counts or {}),
        "recurring_doubts": tuple(model.recurring_doubts or ()),
        "recurring_misconceptions": tuple(
            model.recurring_misconceptions or ()
        ),
        "verified_calculation_count": int(
            model.verified_calculation_count
        ),
        "repaired_calculation_count": int(
            model.repaired_calculation_count
        ),
        "blocked_calculation_count": int(
            model.blocked_calculation_count
        ),
        "learning_memory": tuple(model.learning_memory or ()),
        "recent_progress": tuple(model.recent_progress or ()),
        "stable_signals": tuple(
            dict(item) for item in (model.stable_signals or ())
        ),
    }


def student_model_prompt(model):
    """Render persistent history as advisory context, never authoritative mastery."""
    data = student_model_mapping(model)
    if not data:
        return "(none)"
    lines = [
        "previous_course_sessions={}".format(
            int(data["previous_sessions_considered"])
        )
    ]

    if data["answer_status_counts"]:
        status_text = ", ".join(
            "{}={}".format(key, data["answer_status_counts"][key])
            for key in ("correct", "partial", "incorrect", "unclear")
            if data["answer_status_counts"].get(key)
        )
        if status_text:
            lines.append("historical_answer_signals=" + status_text)

    for doubt in data["recurring_doubts"]:
        lines.append("previous_doubt=" + _clean(doubt))
    for misconception in data["recurring_misconceptions"]:
        lines.append(
            "previous_possible_misconception=" + _clean(misconception)
        )

    math_parts = []
    if data["verified_calculation_count"]:
        math_parts.append(
            "verified={}".format(data["verified_calculation_count"])
        )
    if data["repaired_calculation_count"]:
        math_parts.append(
            "repaired={}".format(data["repaired_calculation_count"])
        )
    if data["blocked_calculation_count"]:
        math_parts.append(
            "blocked={}".format(data["blocked_calculation_count"])
        )
    if math_parts:
        lines.append("historical_math_checks=" + ", ".join(math_parts))

    for item in data["learning_memory"]:
        lines.append("existing_learning_memory=" + _clean(item))
    for item in data["recent_progress"]:
        lines.append("existing_progress_event=" + _clean(item))

    for signal in data["stable_signals"]:
        kind = _clean(signal.get("kind"), 50)
        text = _clean(signal.get("text"))
        sessions = int(signal.get("session_count") or 0)
        events = int(signal.get("event_count") or 0)
        first_seen = _clean(signal.get("first_observed_at"), 80)
        last_seen = _clean(signal.get("last_observed_at"), 80)
        provenance = ", ".join(
            _clean(item, 160)
            for item in tuple(signal.get("provenance") or ())[:4]
        )
        payload = (
            "kind={}; sessions={}; events={}; first={}; last={}".format(
                kind,
                sessions,
                events,
                first_seen or "?",
                last_seen or "?",
            )
        )
        if text:
            payload += "; text=" + text
        if provenance:
            payload += "; provenance=" + provenance
        lines.append("stable_cross_session_signal=" + payload)

    if len(lines) == 1 and lines[0] == "previous_course_sessions=0":
        return "(none)"
    return "\n".join(lines)
