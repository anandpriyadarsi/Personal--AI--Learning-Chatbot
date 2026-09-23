"""Bounded course-scoped concept dependencies for ANVAYA Tutor 2.3.4.

The graph is explicit and inspectable. It is advisory orchestration data, not
academic mastery/progress state. One prerequisite may be selected per Tutor
turn; recursive prerequisite descent is deliberately forbidden in 2.3.4.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping


PREREQUISITE_REASONS = (
    "",
    "explicit_prerequisite_gap",
    "current_session_prerequisite_gap",
)


def _clean(value, limit=400):
    return " ".join(str(value or "").strip().split())[: int(limit)]


def _fold(value):
    return _clean(value, 600).casefold()


def _concept(label, *aliases):
    values = [label]
    values.extend(aliases)
    return {
        "label": label,
        "aliases": tuple(
            item.casefold()
            for item in values
            if str(item or "").strip()
        ),
    }


# Initial explicit graph. It is intentionally conservative: edges should be
# added only when they are stable pedagogical prerequisites, not merely related
# concepts. Course codes keep identical words in different disciplines from
# leaking into one another.
COURSE_DEPENDENCY_GRAPHS = {
    "MA103N": (
        {
            "target": _concept(
                "LU Factorization",
                "LU factorisation",
                "LU decomposition",
                "A=LU",
            ),
            "prerequisites": (
                _concept("Gaussian Elimination", "row elimination"),
                _concept(
                    "Elimination Multipliers",
                    "elimination multiplier",
                    "multipliers in elimination",
                    "row multiplier",
                ),
                _concept("Matrix Multiplication", "matrix product"),
            ),
        },
        {
            "target": _concept(
                "Matrix Inverse",
                "matrix inverses",
                "inverse using Gauss Jordan",
                "Gauss-Jordan inverse",
            ),
            "prerequisites": (
                _concept("Elementary Row Operations", "row operations"),
                _concept("Gauss-Jordan Elimination", "Gauss Jordan"),
            ),
        },
        {
            "target": _concept("Rank", "rank of matrix", "matrix rank"),
            "prerequisites": (
                _concept("Row Echelon Form", "echelon form", "REF"),
                _concept("Elementary Row Operations", "row operations"),
            ),
        },
        {
            "target": _concept("Basis", "bases"),
            "prerequisites": (
                _concept("Span", "spanning"),
                _concept(
                    "Linear Independence",
                    "linearly independent",
                    "linear dependence",
                    "linearly dependent",
                ),
            ),
        },
        {
            "target": _concept("Dimension", "dimension theorem"),
            "prerequisites": (
                _concept("Basis", "bases"),
                _concept(
                    "Linear Independence",
                    "linearly independent",
                ),
                _concept("Span", "spanning"),
            ),
        },
        {
            "target": _concept(
                "Coordinate Representation",
                "coordinates relative to a basis",
                "coordinate vector",
            ),
            "prerequisites": (
                _concept("Basis", "bases"),
                _concept(
                    "Linear Independence",
                    "linearly independent",
                ),
            ),
        },
        {
            "target": _concept("Subspace", "subspaces"),
            "prerequisites": (
                _concept("Vector Space", "vector spaces"),
            ),
        },
        {
            "target": _concept(
                "Linear Independence",
                "linearly independent",
                "linear dependence",
                "linearly dependent",
            ),
            "prerequisites": (
                _concept("Linear Combination", "linear combinations"),
                _concept("Span", "spanning"),
            ),
        },
    ),
    # Seed only stable, high-level dependencies for current first-semester
    # non-math courses. This graph is intentionally small and can be extended
    # from authoritative course material later.
    "UC100N": (
        {
            "target": _concept(
                "Data Cleaning",
                "cleaning data",
                "data preprocessing",
            ),
            "prerequisites": (
                _concept("Tabular Data", "rows and columns", "data table"),
                _concept("Missing Values", "missing data", "null values"),
            ),
        },
        {
            "target": _concept(
                "Data Visualization",
                "data visualisation",
                "plotting data",
            ),
            "prerequisites": (
                _concept("Variables and Data Types", "data types", "variables"),
            ),
        },
    ),
    "CY100N": (
        {
            "target": _concept(
                "Atomic Absorption Spectroscopy",
                "AAS",
                "atomic absorption",
            ),
            "prerequisites": (
                _concept("Absorption of Radiation", "absorption", "radiation absorption"),
                _concept("Electronic Transitions", "electronic transition"),
            ),
        },
    ),
}


_CONFUSION_CUES = (
    r"\bi (?:do not|don't) understand\b",
    r"\bi(?:'m| am) confused\b",
    r"\bconfused\b",
    r"\bstuck\b",
    r"\bstruggl",
    r"\bnot clear\b",
    r"\bunclear\b",
    r"\bdon't know\b",
    r"\bdo not know\b",
    r"\bmissing\b",
    r"\bproblem (?:is|with)\b",
    r"\bblocking\b",
)


@dataclass(frozen=True)
class PrerequisiteDecision:
    should_review: bool
    reason: str = ""
    course_code: str = ""
    target_concept: str = ""
    prerequisite_concept: str = ""
    target_topic_id: str = ""
    prerequisite_topic_id: str = ""
    return_to_goal: bool = True


def course_context_from_repository(repository, session):
    """Resolve read-only canonical course/topic context when repository supports it."""
    if repository is None or session is None or not getattr(session, "course_id", None):
        return {}

    course_identity = getattr(repository, "course_identity", None)
    topic_identity = getattr(repository, "topic_identity", None)
    list_topics = getattr(repository, "list_course_topics", None)
    if not callable(course_identity):
        return {}

    try:
        course = course_identity(session.course_id)
    except Exception:
        return {}
    if not isinstance(course, Mapping):
        return {}

    selected_topic = {}
    if getattr(session, "topic_id", None) and callable(topic_identity):
        try:
            resolved = topic_identity(session.topic_id, session.course_id)
        except TypeError:
            try:
                resolved = topic_identity(session.topic_id)
            except Exception:
                resolved = None
        except Exception:
            resolved = None
        if isinstance(resolved, Mapping):
            selected_topic = dict(resolved)

    topics = ()
    if callable(list_topics):
        try:
            raw_topics = list_topics(session.course_id)
        except Exception:
            raw_topics = ()
        topics = tuple(
            {
                "id": _clean(dict(item).get("id"), 120),
                "name": _clean(dict(item).get("name"), 220),
            }
            for item in tuple(raw_topics or ())
            if isinstance(item, Mapping)
        )

    return {
        "course_id": _clean(course.get("id"), 120),
        "course_code": _clean(course.get("code"), 60).upper(),
        "course_name": _clean(course.get("name"), 220),
        "selected_topic_id": _clean(selected_topic.get("id"), 120),
        "selected_topic_name": _clean(selected_topic.get("name"), 220),
        "topics": topics,
    }


def _contains_alias(text, concept):
    folded = _fold(text)
    return any(alias in folded for alias in concept["aliases"])


def _find_target(graph, text):
    matches = []
    for node in graph:
        target = node["target"]
        lengths = [
            len(alias)
            for alias in target["aliases"]
            if alias in _fold(text)
        ]
        if lengths:
            matches.append((max(lengths), node))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0], reverse=True)
    return matches[0][1]


def _find_prerequisite(node, text):
    matches = []
    folded = _fold(text)
    for prerequisite in node["prerequisites"]:
        lengths = [
            len(alias)
            for alias in prerequisite["aliases"]
            if alias in folded
        ]
        if lengths:
            matches.append((max(lengths), prerequisite))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0], reverse=True)
    return matches[0][1]


def _canonical_topic(context, concept):
    best = None
    for item in tuple(dict(context or {}).get("topics") or ()):
        name = _clean(dict(item).get("name"), 220)
        if not name:
            continue
        if _contains_alias(name, concept) or _contains_alias(
            " ".join(concept["aliases"]),
            _concept(name),
        ):
            score = max(
                (
                    len(alias)
                    for alias in concept["aliases"]
                    if alias in name.casefold() or name.casefold() in alias
                ),
                default=1,
            )
            if best is None or score > best[0]:
                best = (score, item)
    return {} if best is None else dict(best[1])


def _has_confusion_language(text):
    folded = _fold(text)
    return any(re.search(pattern, folded) for pattern in _CONFUSION_CUES)


def _explicit_intent_blocks_prerequisite(teaching_intent):
    return _clean(teaching_intent, 80).casefold() in {
        "hint",
        "example",
        "practice",
        "quiz",
        "summary",
        "verify_reasoning",
        "guidance",
    }


def plan_prerequisite_review(
    question,
    *,
    teaching_intent,
    adaptive_state,
    session_goal,
    course_context,
):
    """Select at most one prerequisite when current evidence identifies the gap."""
    context = dict(course_context or {})
    course_code = _clean(context.get("course_code"), 60).upper()
    graph = COURSE_DEPENDENCY_GRAPHS.get(course_code, ())
    if not graph:
        return PrerequisiteDecision(False, course_code=course_code)

    if _explicit_intent_blocks_prerequisite(teaching_intent):
        return PrerequisiteDecision(False, course_code=course_code)

    state = dict(adaptive_state or {})
    goal = dict(session_goal or {})
    selected_topic_name = _clean(context.get("selected_topic_name"), 220)
    target_text = " ".join(
        part
        for part in (
            _clean(goal.get("goal"), 360),
            selected_topic_name,
            _clean(question, 700),
        )
        if part
    )
    node = _find_target(graph, target_text)
    if node is None:
        return PrerequisiteDecision(False, course_code=course_code)

    target = node["target"]
    target_topic = _canonical_topic(context, target)

    question_prerequisite = _find_prerequisite(node, question)
    if question_prerequisite is not None and _has_confusion_language(question):
        prerequisite_topic = _canonical_topic(context, question_prerequisite)
        return PrerequisiteDecision(
            True,
            reason="explicit_prerequisite_gap",
            course_code=course_code,
            target_concept=target["label"],
            prerequisite_concept=question_prerequisite["label"],
            target_topic_id=_clean(target_topic.get("id"), 120),
            prerequisite_topic_id=_clean(prerequisite_topic.get("id"), 120),
        )

    historical_gap = " ".join(
        part
        for part in (
            _clean(state.get("last_misconception"), 300),
            _clean(state.get("last_evaluation_reason"), 300),
            _clean(state.get("unresolved_doubt"), 300),
        )
        if part
    )
    prior_outcome = _clean(state.get("last_socratic_outcome"), 40).casefold()
    state_prerequisite = _find_prerequisite(node, historical_gap)
    if (
        state_prerequisite is not None
        and prior_outcome in {"clarify", "repair", "unclear"}
    ):
        prerequisite_topic = _canonical_topic(context, state_prerequisite)
        return PrerequisiteDecision(
            True,
            reason="current_session_prerequisite_gap",
            course_code=course_code,
            target_concept=target["label"],
            prerequisite_concept=state_prerequisite["label"],
            target_topic_id=_clean(target_topic.get("id"), 120),
            prerequisite_topic_id=_clean(prerequisite_topic.get("id"), 120),
        )

    return PrerequisiteDecision(
        False,
        course_code=course_code,
        target_concept=target["label"],
        target_topic_id=_clean(target_topic.get("id"), 120),
    )


def prerequisite_decision_mapping(decision):
    if isinstance(decision, Mapping):
        reason = _clean(decision.get("reason"), 120)
        if reason not in PREREQUISITE_REASONS:
            reason = ""
        return {
            "should_review": bool(decision.get("should_review", False)),
            "reason": reason,
            "course_code": _clean(decision.get("course_code"), 60).upper(),
            "target_concept": _clean(decision.get("target_concept"), 220),
            "prerequisite_concept": _clean(
                decision.get("prerequisite_concept"),
                220,
            ),
            "target_topic_id": _clean(decision.get("target_topic_id"), 120),
            "prerequisite_topic_id": _clean(
                decision.get("prerequisite_topic_id"),
                120,
            ),
            "return_to_goal": bool(decision.get("return_to_goal", True)),
        }
    return prerequisite_decision_mapping(
        {
            "should_review": decision.should_review,
            "reason": decision.reason,
            "course_code": decision.course_code,
            "target_concept": decision.target_concept,
            "prerequisite_concept": decision.prerequisite_concept,
            "target_topic_id": decision.target_topic_id,
            "prerequisite_topic_id": decision.prerequisite_topic_id,
            "return_to_goal": decision.return_to_goal,
        }
    )


def prerequisite_retrieval_query(decision):
    data = prerequisite_decision_mapping(decision)
    if not data["should_review"] or not data["prerequisite_concept"]:
        return ""
    return "{} prerequisite for {}".format(
        data["prerequisite_concept"],
        data["target_concept"] or "current topic",
    )
