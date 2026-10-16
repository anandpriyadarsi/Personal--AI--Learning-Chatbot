"""Exact self-mark arithmetic. Structural validity never confers reviewer authority."""

from __future__ import annotations
import json
from decimal import Decimal, InvalidOperation


def _integer(value, minimum=0, maximum=100000000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Invalid integer allocation.")
    return value


def _text(value, maximum=12000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError("Invalid rubric text.")
    return value


def _texts(value):
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError("Invalid rubric list.")
    return [_text(item) for item in value]


def parse_rubric(text: str, question_id: str, maximum: int) -> dict:
    """Recognise the existing v1 rubric string, fail closed on structured content."""
    _integer(maximum, 1)
    _text(text, 100000)
    if not text.lstrip().startswith(("{", "[")):
        return dict(kind="per_question", text=text, maximum=maximum)
    try:

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate rubric key.")
                result[key] = value
            return result

        data = json.loads(text, object_pairs_hook=unique)
    except (json.JSONDecodeError, RecursionError) as error:
        raise ValueError("Malformed structured rubric requires review.") from error
    keys = {
        "schema",
        "version",
        "question_id",
        "total_marks_milli",
        "grading_increment_milli",
        "steps",
        "common_mistakes",
        "review_required",
    }
    if not isinstance(data, dict) or set(data) != keys:
        raise ValueError("Unrecognised structured rubric.")
    if (
        data["schema"] != "anvaya.subjective-rubric"
        or type(data["version"]) is not int
        or data["version"] != 1
    ):
        raise ValueError("Unsupported rubric contract.")
    if data["question_id"] != question_id or data["review_required"] is not False:
        raise ValueError("Rubric identity/review mismatch.")
    if _integer(data["total_marks_milli"], 1) != maximum:
        raise ValueError("Rubric maximum mismatch.")
    increment = _integer(data["grading_increment_milli"], 1, maximum)
    steps = data["steps"]
    if not isinstance(steps, list) or not 1 <= len(steps) <= 100:
        raise ValueError("Invalid rubric steps.")
    _texts(data["common_mistakes"])
    ids = set()
    groups = {}
    additive = 0
    required = {
        "id",
        "label",
        "expected_work",
        "max_marks_milli",
        "prerequisites",
        "award_when",
        "do_not_award_when",
        "allowed_awards_milli",
        "alternative_group",
    }
    for step in steps:
        if not isinstance(step, dict) or set(step) != required:
            raise ValueError("Invalid rubric step fields.")
        sid = _text(step["id"], 100)
        if sid in ids:
            raise ValueError("Duplicate step identity.")
        ids.add(sid)
        _text(step["label"], 500)
        _text(step["expected_work"])
        limit = _integer(step["max_marks_milli"], 1, maximum)
        if limit % increment:
            raise ValueError("Maximum does not match increment.")
        deps = _texts(step["prerequisites"])
        if len(set(deps)) != len(deps):
            raise ValueError("Duplicate prerequisite.")
        _texts(step["award_when"])
        _texts(step["do_not_award_when"])
        awards = step["allowed_awards_milli"]
        if not isinstance(awards, list) or not 2 <= len(awards) <= 1000:
            raise ValueError("Invalid allowed awards.")
        if (
            any(_integer(v, 0, limit) % increment for v in awards)
            or len(set(awards)) != len(awards)
            or 0 not in awards
            or limit not in awards
        ):
            raise ValueError("Invalid award allocation.")
        group = step["alternative_group"]
        if group is not None:
            _text(group, 100)
            groups[group] = max(groups.get(group, 0), limit)
        else:
            additive += limit
    graph = {step["id"]: step["prerequisites"] for step in steps}
    group_by_id = {step["id"]: step["alternative_group"] for step in steps}
    complete = {}

    def visit(sid, visiting):
        if sid not in ids or sid in visiting:
            raise ValueError("Unknown/cyclic prerequisite.")
        if sid in complete:
            return complete[sid]
        dependencies = set()
        for dep in graph[sid]:
            dependencies.add(dep)
            dependencies.update(visit(dep, visiting | {sid}))
        if group_by_id[sid] and any(
            group_by_id[d] == group_by_id[sid] for d in dependencies
        ):
            raise ValueError("Alternative method requires a competing method.")
        required_groups = {}
        for dep in dependencies:
            group = group_by_id[dep]
            if group and group in required_groups and required_groups[group] != dep:
                raise ValueError("Prerequisites require competing alternative methods.")
            if group:
                required_groups[group] = dep
        complete[sid] = dependencies
        return dependencies

    for sid in ids:
        visit(sid, set())
    if additive + sum(groups.values()) != maximum:
        raise ValueError("Step allocations do not reconcile.")
    return dict(kind="per_step", maximum=maximum, **data)


def marks_milli(value) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("Enter a decimal mark.")
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ValueError("Enter a decimal mark.") from None
    if (
        not number.is_finite()
        or number < 0
        or number.as_tuple().exponent < -3
        or number > 100000
    ):
        raise ValueError("Invalid mark precision or bounds.")
    return int(number * 1000)


def mark_rubric(rubric: dict, payload: dict) -> int:
    if rubric["kind"] == "per_question":
        if set(payload) != {"marks"}:
            raise ValueError("Use one per-question mark.")
        total = marks_milli(payload["marks"])
    else:
        if set(payload) != {"steps"} or not isinstance(payload["steps"], dict):
            raise ValueError("Use reviewed step awards.")
        awards = payload["steps"]
        steps = rubric["steps"]
        if set(awards) != {s["id"] for s in steps}:
            raise ValueError("Every step requires an explicit mark.")
        scores = {sid: marks_milli(value) for sid, value in awards.items()}
        groups = set()
        for step in steps:
            score = scores[step["id"]]
            if score not in step["allowed_awards_milli"]:
                raise ValueError("Award outside reviewed allocation.")
            if score and any(scores[dep] == 0 for dep in step["prerequisites"]):
                raise ValueError("Prerequisite credit missing.")
            group = step["alternative_group"]
            if score and group:
                if group in groups:
                    raise ValueError("Alternative methods cannot be counted twice.")
                groups.add(group)
        total = sum(scores.values())
    if total > rubric["maximum"]:
        raise ValueError("Mark exceeds question maximum.")
    return total
