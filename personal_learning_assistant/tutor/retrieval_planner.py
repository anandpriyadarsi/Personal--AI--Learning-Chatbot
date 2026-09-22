"""Deterministic retrieval planning and reranking for ANVAYA Tutor 2.1.

The planner is intentionally bounded: no provider/LLM call occurs here.
"""

from __future__ import annotations

import re
from collections import defaultdict


_MAX_QUERIES = 4
_MAX_QUERY_CHARS = 900

_STOPWORDS = {
    "a", "about", "again", "am", "an", "and", "answer", "are", "as", "at",
    "be", "because", "can", "could", "do", "does", "explain", "for", "from",
    "give", "help", "how", "i", "in", "is", "it", "like", "me", "my", "of",
    "on", "please", "show", "so", "that", "the", "this", "to", "understand",
    "want", "what", "when", "where", "which", "why", "with", "you",
}

# Mostly orthographic/terminology variants. These are deliberately conservative
# rather than an open-ended knowledge graph.
_ALIAS_PAIRS = (
    ("factorisation", "factorization"),
    ("normalisation", "normalization"),
    ("optimisation", "optimization"),
    ("visualisation", "visualization"),
    ("modelling", "modeling"),
    ("linear independence", "linearly independent"),
    ("linearly dependent", "linear dependence"),
    ("eigen value", "eigenvalue"),
    ("sub-space", "subspace"),
    ("row-reduced echelon", "reduced row echelon"),
    ("rref", "reduced row echelon form"),
    ("ref", "row echelon form"),
    ("lu decomposition", "lu factorization"),
    ("lu factorisation", "lu factorization"),
)


def _clean(value, limit=_MAX_QUERY_CHARS):
    return " ".join(str(value or "").strip().split())[: int(limit)]


def _focus_query(question):
    clean = _clean(question)
    if not clean:
        return ""
    # Preserve mathematical identifiers and course terminology while removing
    # common conversational scaffolding.
    tokens = re.findall(r"[A-Za-z0-9_+\-^]+", clean)
    kept = [
        token
        for token in tokens
        if token.casefold() not in _STOPWORDS and len(token) > 1
    ]
    if len(kept) < 2:
        return ""
    return " ".join(kept[:16])


def _alias_variant(value):
    clean = _clean(value)
    lowered = clean.casefold()
    for left, right in _ALIAS_PAIRS:
        if left in lowered:
            start = lowered.index(left)
            return _clean(clean[:start] + right + clean[start + len(left):])
        if right in lowered:
            start = lowered.index(right)
            return _clean(clean[:start] + left + clean[start + len(right):])
    return ""


def plan_retrieval_queries(question, adaptive_state, intent_name):
    """Return ordered, unique retrieval queries with the original always first."""
    state = dict(adaptive_state or {})
    question = _clean(question)
    candidates = [question]

    pending = _clean(state.get("pending_question"))
    unresolved = _clean(state.get("unresolved_doubt"))
    misconception = _clean(state.get("last_misconception"))

    if intent_name == "quiz_answer" and pending:
        candidates.insert(0, _clean(pending + " " + question))
        candidates.append(pending)
    else:
        focus = _focus_query(question)
        if focus and focus.casefold() != question.casefold():
            candidates.append(focus)

    if intent_name in {"explain_differently", "hint", "quiz_answer"} and unresolved:
        candidates.append(unresolved)

    # A known misconception is often a better retrieval anchor than a terse
    # student reply, but it remains lower priority than the live question.
    if misconception and intent_name in {"quiz_answer", "explain_differently"}:
        candidates.append(misconception)

    # Spelling/terminology tolerance helps course material that uses a different
    # English variant, e.g. factorisation vs factorization.
    for seed in tuple(candidates[:2]):
        alias = _alias_variant(seed)
        if alias:
            candidates.append(alias)

    unique = []
    seen = set()
    for candidate in candidates:
        candidate = _clean(candidate)
        key = candidate.casefold()
        if candidate and key not in seen:
            unique.append(candidate)
            seen.add(key)
        if len(unique) >= _MAX_QUERIES:
            break
    return tuple(unique) or (question,)


def _source_text(hit):
    locator = dict(getattr(hit, "locator", {}) or {})
    source = locator.get("source")
    source = source if isinstance(source, dict) else {}
    values = [
        source.get("kind"),
        source.get("provider"),
        locator.get("source_kind"),
        locator.get("source_provider"),
        locator.get("lecture_title"),
        locator.get("topic"),
    ]
    values.extend(tuple(getattr(hit, "providers", ()) or ()))
    return " ".join(str(value or "") for value in values).casefold()


def infer_source_role(hit, *, selected_resource_id=None):
    if selected_resource_id and str(selected_resource_id) in tuple(
        str(value) for value in getattr(hit, "resource_ids", ())
    ):
        return "selected_resource"

    text = _source_text(hit)
    if any(token in text for token in (
        "pyq", "previous year", "past paper", "question paper", "past exam",
    )):
        return "pyq"
    if any(token in text for token in (
        "obsidian", "personal note", "personal_note", "note_metadata", "markdown note",
    )):
        return "personal_note"
    if any(token in text for token in (
        "professor", "ppt", "powerpoint", "slide", "class lecture", "class_note",
    )):
        return "professor"
    if any(token in text for token in (
        "mit", "ocw", "youtube", "external", "nptel", "coursera",
    )):
        return "external_course"
    return "course"


def _role_bonus(role, preferred_source_roles):
    preferred = tuple(preferred_source_roles or ())
    if role not in preferred:
        return 0.0
    # Small enough that relevance still dominates, but enough to break close
    # ties in the direction requested by the Tutor mode.
    index = preferred.index(role)
    return max(0.0, 0.14 - (0.025 * index))


def rerank_retrieval_hits(
    query_groups,
    *,
    limit,
    preferred_source_roles=(),
    selected_resource_id=None,
    diversify=True,
):
    """Rerank by multi-query agreement, query rank, source priority and diversity."""
    records = {}
    for query_index, group in enumerate(tuple(query_groups or ())):
        weight = max(0.55, 1.0 - 0.15 * query_index)
        for rank, hit in enumerate(tuple(group or ()), start=1):
            key = str(hit.chunk_id)
            rec = records.setdefault(
                key,
                {
                    "hit": hit,
                    "score": 0.0,
                    "queries": set(),
                    "best_rank": rank,
                },
            )
            rec["queries"].add(query_index)
            rec["best_rank"] = min(rec["best_rank"], rank)
            # Reciprocal rank within each planned query is more comparable than
            # raw hybrid scores across separate retrieval calls.
            rec["score"] += weight / float(rank)

    ranked = []
    for rec in records.values():
        hit = rec["hit"]
        role = infer_source_role(
            hit,
            selected_resource_id=selected_resource_id,
        )
        consensus = max(0, len(rec["queries"]) - 1)
        score = (
            rec["score"]
            + 0.18 * consensus
            + _role_bonus(role, preferred_source_roles)
        )
        ranked.append((score, rec["best_rank"], str(hit.chunk_id), hit))

    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))

    target = max(1, int(limit))
    if not diversify:
        return tuple(item[3] for item in ranked[:target])

    # For broad tutoring, avoid filling the whole context with adjacent chunks
    # from one document. A soft cap of 3 still allows coherent local context.
    selected = []
    deferred = []
    per_document = defaultdict(int)
    per_document_cap = 3

    for item in ranked:
        hit = item[3]
        document_id = str(hit.document_id)
        if per_document[document_id] < per_document_cap:
            selected.append(hit)
            per_document[document_id] += 1
        else:
            deferred.append(hit)
        if len(selected) >= target:
            break

    if len(selected) < target:
        for hit in deferred:
            selected.append(hit)
            if len(selected) >= target:
                break

    return tuple(selected[:target])
