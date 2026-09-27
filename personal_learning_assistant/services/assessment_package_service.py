"""Assessment Studio Phase B: ANVAYA Assessment Package import and review."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote

import config
from personal_learning_assistant.repositories.sqlite.assessment_import_repository import (
    AssessmentImportRepositoryConflictError,
    AssessmentImportRepositoryDataError,
    AssessmentImportRepositoryNotFoundError,
    AssessmentImportRepositorySchemaError,
    SQLiteAssessmentImportRepository,
)
from personal_learning_assistant.repositories.sqlite.connection import connect_database


PACKAGE_SCHEMA = "anvaya.assessment-package"
PACKAGE_VERSION = 1
MAX_PACKAGE_BYTES = 5 * 1024 * 1024
MAX_QUESTIONS = 200

QUESTION_TYPES = {
    "mcq",
    "msq",
    "numerical",
    "fill_blank",
    "true_false",
    "short_subjective",
    "long_subjective",
}
OBJECTIVE_OPTION_TYPES = {"mcq", "msq"}
ACCEPTED_ANSWER_TYPES = {"numerical", "fill_blank", "true_false"}
SUBJECTIVE_TYPES = {"short_subjective", "long_subjective"}
SCORING_POLICIES = {"standard", "all_or_nothing", "partial", "custom"}
ASSESSMENT_TYPES = {"quiz", "midsem", "endsem", "topic_test", "previous_paper", "custom"}
MODES = {"exam", "practice"}
DIFFICULTIES = {"easy", "medium", "hard", "very_hard"}
AUTHORING_PURPOSES = {
    "reproduced_paper",
    "adapted_paper",
    "generated_practice",
    "weak_topic_retest",
    "manual",
}

AUTHORING_WORKSPACE_KINDS = {
    "quiz": {
        "label": "Quiz",
        "eyebrow": "Quick assessment",
        "description": "Short quiz, class quiz or quiz-pattern practice.",
        "prompt_hint": "Use package assessment_type='quiz' unless the supplied source clearly requires a different exact type.",
    },
    "exam": {
        "label": "Exam",
        "eyebrow": "Mid-sem / End-sem",
        "description": "Full exam, mid-sem, end-sem or reproduced examination paper.",
        "prompt_hint": "Use assessment_type='midsem' or 'endsem' when the source identifies it. Use 'previous_paper' for a faithful reproduced historical exam paper.",
    },
    "test": {
        "label": "Test",
        "eyebrow": "Practice / Topic test",
        "description": "Topic test, recovery test, generated practice or custom assessment.",
        "prompt_hint": "Use assessment_type='topic_test' for a focused topic test; otherwise use the most accurate supported type such as 'custom'.",
    },
}

MASTER_PROMPT_FILENAME = "ANVAYA_ASSESSMENT_PACKAGE_AUTHORING_PROMPT.md"
MASTER_PROMPT_MAX_CHARS = 60000


class AssessmentPackageError(RuntimeError):
    pass


class AssessmentPackageValidationError(AssessmentPackageError):
    pass


class AssessmentPackageNotFoundError(AssessmentPackageError):
    pass


class AssessmentPackageConflictError(AssessmentPackageError):
    pass


class AssessmentPackageUnavailableError(AssessmentPackageError):
    pass


def _now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _normal(text) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).split())


def _tokens(text):
    stop = {
        "a", "an", "the", "is", "are", "of", "to", "in", "on", "for",
        "with", "and", "or", "as", "at", "by", "from", "using", "find",
        "solve", "show", "prove", "calculate", "determine", "question",
    }
    return {
        token for token in _normal(text).split()
        if len(token) > 1 and token not in stop
    }


def _milli(value, field: str, *, allow_zero: bool = True):
    if isinstance(value, bool) or value is None:
        raise AssessmentPackageValidationError("{} must be a number.".format(field))
    try:
        number = Decimal(str(value))
    except InvalidOperation as error:
        raise AssessmentPackageValidationError(
            "{} must be a number.".format(field)
        ) from error
    if not number.is_finite() or number < 0 or (not allow_zero and number == 0):
        comparison = "greater than zero" if not allow_zero else "zero or greater"
        raise AssessmentPackageValidationError(
            "{} must be {}.".format(field, comparison)
        )
    scaled = number * Decimal(1000)
    if scaled != scaled.to_integral_value():
        raise AssessmentPackageValidationError(
            "{} supports at most three decimal places.".format(field)
        )
    return int(scaled)


def _marks_text(value):
    if value is None:
        return ""
    number = Decimal(int(value)) / Decimal(1000)
    text = format(number, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _positive_int(value, field: str, *, maximum: int | None = None):
    if isinstance(value, bool):
        raise AssessmentPackageValidationError("{} must be a whole number.".format(field))
    try:
        result = int(str(value).strip())
    except (TypeError, ValueError) as error:
        raise AssessmentPackageValidationError(
            "{} must be a whole number.".format(field)
        ) from error
    if result <= 0 or (maximum is not None and result > maximum):
        raise AssessmentPackageValidationError(
            "{} must be between 1 and {}.".format(field, maximum)
            if maximum is not None
            else "{} must be greater than zero.".format(field)
        )
    return result


def _confidence(value, field: str, *, optional: bool = False):
    if value is None and optional:
        return None
    if isinstance(value, bool):
        raise AssessmentPackageValidationError("{} must be between 0 and 1.".format(field))
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise AssessmentPackageValidationError(
            "{} must be between 0 and 1.".format(field)
        ) from error
    if result < 0.0 or result > 1.0:
        raise AssessmentPackageValidationError("{} must be between 0 and 1.".format(field))
    return round(result, 6)


def _strict_keys(value, *, allowed, required, context):
    if not isinstance(value, dict):
        raise AssessmentPackageValidationError("{} must be an object.".format(context))
    missing = sorted(set(required) - set(value))
    if missing:
        raise AssessmentPackageValidationError(
            "{} is missing required field(s): {}.".format(context, ", ".join(missing))
        )
    extra = sorted(set(value) - set(allowed))
    if extra:
        raise AssessmentPackageValidationError(
            "{} contains unsupported field(s): {}.".format(context, ", ".join(extra))
        )


def _nonempty(value, field: str, *, maximum: int = 20000):
    if not isinstance(value, str):
        raise AssessmentPackageValidationError("{} must be text.".format(field))
    text = value.strip()
    if not text:
        raise AssessmentPackageValidationError("{} cannot be empty.".format(field))
    if len(text) > maximum:
        raise AssessmentPackageValidationError("{} is too long.".format(field))
    return text


def _optional_text(value, field: str, *, maximum: int = 20000):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise AssessmentPackageValidationError("{} must be text.".format(field))
    text = value.strip()
    if len(text) > maximum:
        raise AssessmentPackageValidationError("{} is too long.".format(field))
    return text


def _string_list(value, field: str, *, maximum_items: int = 50):
    if not isinstance(value, list):
        raise AssessmentPackageValidationError("{} must be a list.".format(field))
    if len(value) > maximum_items:
        raise AssessmentPackageValidationError("{} has too many items.".format(field))
    result = []
    for index, item in enumerate(value, start=1):
        result.append(_nonempty(item, "{} item {}".format(field, index), maximum=500))
    return result


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AssessmentPackageValidationError(
                "Duplicate JSON key is not allowed: {}.".format(key)
            )
        result[key] = value
    return result


def _reject_constant(value):
    raise AssessmentPackageValidationError(
        "Non-finite JSON number is not allowed: {}.".format(value)
    )


def _parse_json(raw: bytes):
    if not raw:
        raise AssessmentPackageValidationError("Choose a non-empty assessment package.")
    if len(raw) > MAX_PACKAGE_BYTES:
        raise AssessmentPackageValidationError(
            "Assessment package is larger than 5 MB."
        )
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise AssessmentPackageValidationError(
            "Assessment package must be UTF-8 JSON."
        ) from error
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except AssessmentPackageValidationError:
        raise
    except json.JSONDecodeError as error:
        raise AssessmentPackageValidationError(
            "Assessment package is not valid JSON (line {}, column {}).".format(
                error.lineno, error.colno
            )
        ) from error


def _validate_created_at(value):
    text = _nonempty(value, "created_at", maximum=80)
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise AssessmentPackageValidationError(
            "created_at must be an ISO-8601 timestamp."
        ) from error
    return text


def _validate_package(package):
    _strict_keys(
        package,
        allowed={
            "schema", "version", "package_id", "package_revision", "created_at",
            "authoring", "assessment", "questions",
        },
        required={
            "schema", "version", "package_id", "package_revision", "created_at",
            "authoring", "assessment", "questions",
        },
        context="Package",
    )
    if package["schema"] != PACKAGE_SCHEMA:
        raise AssessmentPackageValidationError(
            "Unsupported package schema: {!r}.".format(package["schema"])
        )
    if package["version"] != PACKAGE_VERSION:
        raise AssessmentPackageValidationError(
            "Unsupported package version: {!r}. Expected version 1.".format(
                package["version"]
            )
        )
    package_id = _nonempty(package["package_id"], "package_id", maximum=128)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", package_id):
        raise AssessmentPackageValidationError(
            "package_id may contain only letters, numbers, dot, underscore, colon and hyphen."
        )
    package_revision = _positive_int(package["package_revision"], "package_revision")
    created_at = _validate_created_at(package["created_at"])

    authoring = package["authoring"]
    _strict_keys(
        authoring,
        allowed={"engine", "model", "purpose"},
        required={"engine", "purpose"},
        context="authoring",
    )
    engine = _nonempty(authoring["engine"], "authoring.engine", maximum=120)
    model = _optional_text(authoring.get("model"), "authoring.model", maximum=120)
    purpose = _nonempty(authoring["purpose"], "authoring.purpose", maximum=80)
    if purpose not in AUTHORING_PURPOSES:
        raise AssessmentPackageValidationError(
            "authoring.purpose must be one of: {}.".format(
                ", ".join(sorted(AUTHORING_PURPOSES))
            )
        )

    assessment = package["assessment"]
    _strict_keys(
        assessment,
        allowed={
            "course", "title", "type", "mode", "duration_minutes", "total_marks",
            "instructions", "source",
        },
        required={
            "course", "title", "type", "mode", "duration_minutes", "total_marks",
            "instructions",
        },
        context="assessment",
    )
    course = assessment["course"]
    _strict_keys(
        course,
        allowed={"code", "name"},
        required={"code"},
        context="assessment.course",
    )
    course_code = _nonempty(course["code"], "assessment.course.code", maximum=40)
    course_name = _optional_text(course.get("name"), "assessment.course.name", maximum=200)
    title = _nonempty(assessment["title"], "assessment.title", maximum=240)
    assessment_type = _nonempty(assessment["type"], "assessment.type", maximum=60)
    if assessment_type not in ASSESSMENT_TYPES:
        raise AssessmentPackageValidationError(
            "assessment.type must be one of: {}.".format(
                ", ".join(sorted(ASSESSMENT_TYPES))
            )
        )
    mode = _nonempty(assessment["mode"], "assessment.mode", maximum=20)
    if mode not in MODES:
        raise AssessmentPackageValidationError("assessment.mode must be exam or practice.")
    duration_minutes = _positive_int(
        assessment["duration_minutes"], "assessment.duration_minutes", maximum=1440
    )
    total_marks_milli = _milli(
        assessment["total_marks"], "assessment.total_marks", allow_zero=False
    )
    instructions = _string_list(
        assessment["instructions"], "assessment.instructions", maximum_items=40
    )

    if "source" in assessment:
        source = assessment["source"]
        _strict_keys(
            source,
            allowed={"kind", "label"},
            required={"kind", "label"},
            context="assessment.source",
        )
        _nonempty(source["kind"], "assessment.source.kind", maximum=80)
        _nonempty(source["label"], "assessment.source.label", maximum=300)

    questions = package["questions"]
    if not isinstance(questions, list) or not questions:
        raise AssessmentPackageValidationError("questions must be a non-empty list.")
    if len(questions) > MAX_QUESTIONS:
        raise AssessmentPackageValidationError(
            "A package may contain at most {} questions.".format(MAX_QUESTIONS)
        )

    validated_questions = []
    seen_ids = set()
    warnings = []
    calculated_total = 0
    for ordinal, question in enumerate(questions, start=1):
        context = "questions[{}]".format(ordinal - 1)
        _strict_keys(
            question,
            allowed={
                "id", "number", "section", "type", "text", "marks",
                "negative_marks", "scoring_policy", "options", "answer",
                "solution", "rubric", "academic_map", "source",
                "authoring_confidence", "review_required",
            },
            required={
                "id", "number", "type", "text", "marks", "negative_marks",
                "scoring_policy", "answer", "solution", "academic_map", "source",
                "authoring_confidence", "review_required",
            },
            context=context,
        )
        question_id = _nonempty(question["id"], context + ".id", maximum=128)
        if question_id in seen_ids:
            raise AssessmentPackageValidationError(
                "Question ID is duplicated: {}.".format(question_id)
            )
        seen_ids.add(question_id)
        raw_number = question["number"]
        if raw_number is None or isinstance(raw_number, bool):
            raise AssessmentPackageValidationError(
                "{}.number must be a string or integer.".format(context)
            )
        number = _nonempty(str(raw_number), context + ".number", maximum=60)
        section = _optional_text(question.get("section"), context + ".section", maximum=100)
        question_type = _nonempty(question["type"], context + ".type", maximum=40)
        if question_type not in QUESTION_TYPES:
            raise AssessmentPackageValidationError(
                "{}.type is unsupported.".format(context)
            )
        text = _nonempty(question["text"], context + ".text", maximum=50000)
        marks_milli = _milli(question["marks"], context + ".marks", allow_zero=False)
        negative_milli = _milli(
            question["negative_marks"], context + ".negative_marks"
        )
        if negative_milli > marks_milli:
            raise AssessmentPackageValidationError(
                "{}.negative_marks cannot exceed marks.".format(context)
            )
        calculated_total += marks_milli
        scoring_policy = _nonempty(
            question["scoring_policy"], context + ".scoring_policy", maximum=40
        )
        if scoring_policy not in SCORING_POLICIES:
            raise AssessmentPackageValidationError(
                "{}.scoring_policy is unsupported.".format(context)
            )

        raw_options = question.get("options", [])
        if not isinstance(raw_options, list):
            raise AssessmentPackageValidationError(
                "{}.options must be a list.".format(context)
            )
        options = []
        option_ids = set()
        if question_type in OBJECTIVE_OPTION_TYPES:
            if len(raw_options) < 2 or len(raw_options) > 10:
                raise AssessmentPackageValidationError(
                    "{} requires between 2 and 10 options.".format(context)
                )
            for position, option in enumerate(raw_options, start=1):
                _strict_keys(
                    option,
                    allowed={"id", "text"},
                    required={"id", "text"},
                    context="{}.options[{}]".format(context, position - 1),
                )
                option_id = _nonempty(
                    option["id"],
                    "{}.options[{}].id".format(context, position - 1),
                    maximum=20,
                )
                if option_id in option_ids:
                    raise AssessmentPackageValidationError(
                        "{} contains duplicate option ID {}.".format(context, option_id)
                    )
                option_ids.add(option_id)
                options.append(
                    {
                        "id": option_id,
                        "text": _nonempty(
                            option["text"],
                            "{}.options[{}].text".format(context, position - 1),
                            maximum=10000,
                        ),
                    }
                )
        elif raw_options:
            raise AssessmentPackageValidationError(
                "{}.options is only supported for MCQ/MSQ questions.".format(context)
            )

        answer = question["answer"]
        _strict_keys(
            answer,
            allowed={"correct_option_ids", "accepted_answers"},
            required=set(),
            context=context + ".answer",
        )
        correct_ids = _string_list(
            answer.get("correct_option_ids", []),
            context + ".answer.correct_option_ids",
            maximum_items=10,
        )
        accepted_answers = _string_list(
            answer.get("accepted_answers", []),
            context + ".answer.accepted_answers",
            maximum_items=30,
        )
        if any(item not in option_ids for item in correct_ids):
            raise AssessmentPackageValidationError(
                "{} answer references an option ID that does not exist.".format(context)
            )
        if question_type == "mcq" and len(correct_ids) != 1:
            raise AssessmentPackageValidationError(
                "{} MCQ must have exactly one correct option.".format(context)
            )
        if question_type == "msq" and not correct_ids:
            raise AssessmentPackageValidationError(
                "{} MSQ must have at least one correct option.".format(context)
            )
        if question_type in ACCEPTED_ANSWER_TYPES and not accepted_answers:
            raise AssessmentPackageValidationError(
                "{} must provide at least one accepted answer.".format(context)
            )
        if question_type in SUBJECTIVE_TYPES and (correct_ids or accepted_answers):
            raise AssessmentPackageValidationError(
                "{} subjective answer must be expressed through solution/rubric, not an objective key.".format(
                    context
                )
            )

        solution = _nonempty(question["solution"], context + ".solution", maximum=50000)
        rubric = _optional_text(question.get("rubric"), context + ".rubric", maximum=30000)
        if question_type in SUBJECTIVE_TYPES and not rubric:
            raise AssessmentPackageValidationError(
                "{} subjective question requires a rubric.".format(context)
            )

        academic = question["academic_map"]
        _strict_keys(
            academic,
            allowed={
                "chapter", "topic", "subtopic", "concepts", "difficulty",
                "expected_method", "estimated_minutes", "topic_mapping_confidence",
            },
            required={
                "topic", "concepts", "difficulty", "expected_method",
                "estimated_minutes", "topic_mapping_confidence",
            },
            context=context + ".academic_map",
        )
        chapter = _optional_text(
            academic.get("chapter"), context + ".academic_map.chapter", maximum=300
        )
        topic = _nonempty(
            academic["topic"], context + ".academic_map.topic", maximum=300
        )
        subtopic = _optional_text(
            academic.get("subtopic"), context + ".academic_map.subtopic", maximum=300
        )
        concepts = _string_list(
            academic["concepts"], context + ".academic_map.concepts", maximum_items=30
        )
        difficulty = _nonempty(
            academic["difficulty"], context + ".academic_map.difficulty", maximum=30
        )
        if difficulty not in DIFFICULTIES:
            raise AssessmentPackageValidationError(
                "{}.academic_map.difficulty is unsupported.".format(context)
            )
        expected_method = _nonempty(
            academic["expected_method"],
            context + ".academic_map.expected_method",
            maximum=3000,
        )
        estimated_minutes = academic["estimated_minutes"]
        if isinstance(estimated_minutes, bool):
            raise AssessmentPackageValidationError(
                "{}.academic_map.estimated_minutes must be positive.".format(context)
            )
        try:
            estimated = Decimal(str(estimated_minutes))
        except InvalidOperation as error:
            raise AssessmentPackageValidationError(
                "{}.academic_map.estimated_minutes must be positive.".format(context)
            ) from error
        if not estimated.is_finite() or estimated <= 0 or estimated > Decimal(600):
            raise AssessmentPackageValidationError(
                "{}.academic_map.estimated_minutes must be between 0 and 600.".format(context)
            )
        estimated_seconds = int((estimated * Decimal(60)).to_integral_value())
        mapping_confidence = _confidence(
            academic["topic_mapping_confidence"],
            context + ".academic_map.topic_mapping_confidence",
        )

        source = question["source"]
        _strict_keys(
            source,
            allowed={"kind", "label", "page", "locator"},
            required={"kind", "label"},
            context=context + ".source",
        )
        source_kind = _nonempty(
            source["kind"], context + ".source.kind", maximum=80
        )
        source_label = _nonempty(
            source["label"], context + ".source.label", maximum=500
        )
        source_page = source.get("page")
        if source_page is not None:
            source_page = _positive_int(source_page, context + ".source.page")
        source_locator = _optional_text(
            source.get("locator"), context + ".source.locator", maximum=300
        )

        authoring_confidence = _confidence(
            question["authoring_confidence"], context + ".authoring_confidence"
        )
        if not isinstance(question["review_required"], bool):
            raise AssessmentPackageValidationError(
                "{}.review_required must be true or false.".format(context)
            )

        validated_questions.append(
            {
                "package_question_id": question_id,
                "ordinal": ordinal,
                "question_number": number,
                "section_label": section,
                "question_type": question_type,
                "question_text": text,
                "max_marks_milli": marks_milli,
                "negative_marks_milli": negative_milli,
                "scoring_policy": scoring_policy,
                "options": options,
                "answer": {
                    "correct_option_ids": correct_ids,
                    "accepted_answers": accepted_answers,
                },
                "solution_text": solution,
                "rubric_text": rubric,
                "chapter_label": chapter,
                "raw_topic_label": topic,
                "subtopic_label": subtopic,
                "concepts": concepts,
                "difficulty": difficulty,
                "expected_method": expected_method,
                "estimated_seconds": estimated_seconds,
                "package_mapping_confidence": mapping_confidence,
                "authoring_confidence": authoring_confidence,
                "review_required": bool(question["review_required"]),
                "source_kind": source_kind,
                "source_label": source_label,
                "source_page": source_page,
                "source_locator": source_locator,
            }
        )

    if calculated_total != total_marks_milli:
        warnings.append(
            "Assessment total marks ({}) do not match the sum of question marks ({}). "
            "Review question marks before approval.".format(
                _marks_text(total_marks_milli), _marks_text(calculated_total)
            )
        )

    return {
        "schema": PACKAGE_SCHEMA,
        "version": PACKAGE_VERSION,
        "package_id": package_id,
        "package_revision": package_revision,
        "created_at": created_at,
        "authoring": {
            "engine": engine,
            "model": model,
            "purpose": purpose,
        },
        "assessment": {
            "course_code": course_code,
            "course_name": course_name,
            "title": title,
            "assessment_type": assessment_type,
            "mode": mode,
            "duration_minutes": duration_minutes,
            "total_marks_milli": total_marks_milli,
            "instructions": instructions,
        },
        "questions": validated_questions,
        "warnings": warnings,
    }


def _topic_similarity(raw_label, topic):
    label = _normal(raw_label)
    if not label:
        return 0.0
    canonical = _normal(topic.get("name"))
    aliases = [_normal(item.get("alias")) for item in topic.get("aliases") or ()]
    if label == canonical:
        return 1.0
    if label in aliases:
        return 0.98
    label_tokens = _tokens(label)
    best = SequenceMatcher(None, label, canonical).ratio()
    topic_tokens = _tokens(canonical)
    if topic_tokens:
        best = max(best, len(label_tokens & topic_tokens) / len(topic_tokens))
    for alias in aliases:
        best = max(best, SequenceMatcher(None, label, alias).ratio())
    return round(min(1.0, max(0.0, best)), 6)


def _best_topic(raw_label, topics):
    ranked = sorted(
        (
            (_topic_similarity(raw_label, topic), topic)
            for topic in topics
        ),
        key=lambda pair: (-pair[0], str(pair[1].get("name") or "")),
    )
    if not ranked:
        return None, 0.0
    score, topic = ranked[0]
    return (str(topic["id"]) if score >= 0.38 else None), score


def _default_authoring_prompt() -> str:
    path = Path(config.BASE_PATH) / MASTER_PROMPT_FILENAME
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return (
            "Act as the external assessment-authoring engine for ANVAYA. "
            "Create one strict ANVAYA Assessment Package v1 JSON file for "
            "{{COURSE_CODE}} · {{COURSE_NAME}}. Workspace kind: "
            "{{ASSESSMENT_KIND}}. Follow schemas/anvaya-assessment-package-v1.schema.json."
        )


def _infer_workspace_kind(assessment_type: str) -> str:
    value = str(assessment_type or "").strip()
    if value == "quiz":
        return "quiz"
    if value in {"midsem", "endsem", "previous_paper"}:
        return "exam"
    return "test"


def _render_authoring_prompt(prompt: str, *, workspace_kind: str, course) -> str:
    kind = AUTHORING_WORKSPACE_KINDS.get(workspace_kind or "")
    kind_label = kind["label"] if kind else "Quiz / Exam / Test"
    kind_hint = kind["prompt_hint"] if kind else (
        "Choose the package assessment_type that most accurately matches the supplied material."
    )
    course_code = str((course or {}).get("code") or "[SELECT COURSE]")
    course_name = str((course or {}).get("name") or "[SELECT COURSE NAME]")
    values = {
        "{{ASSESSMENT_KIND}}": kind_label,
        "{{ASSESSMENT_KIND_ID}}": str(workspace_kind or "[SELECT KIND]"),
        "{{ASSESSMENT_TYPE_GUIDANCE}}": kind_hint,
        "{{COURSE_CODE}}": course_code,
        "{{COURSE_NAME}}": course_name,
    }
    rendered = str(prompt or "")
    for token, value in values.items():
        rendered = rendered.replace(token, value)
    return rendered


class AssessmentPackageService:
    """Application boundary for external package staging and explicit approval."""

    def __init__(self, database_path):
        self.database_path = Path(database_path)

    @contextmanager
    def _repository(self, *, write: bool):
        path = self.database_path
        if not path.exists() or not path.is_file() or path.is_symlink():
            raise AssessmentPackageUnavailableError(
                "The authoritative SQLite database is unavailable."
            )
        try:
            if write:
                connection = connect_database(path, synchronous="FULL")
            else:
                uri = "file:{}?mode=ro".format(
                    quote(path.resolve().as_posix(), safe="/:")
                )
                connection = sqlite3.connect(uri, uri=True, isolation_level=None)
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute("PRAGMA busy_timeout = 5000")
            try:
                yield SQLiteAssessmentImportRepository(connection)
            finally:
                connection.close()
        except AssessmentPackageError:
            raise
        except AssessmentImportRepositorySchemaError as error:
            raise AssessmentPackageUnavailableError(
                "Assessment Package migration 0010 has not been applied."
            ) from error
        except sqlite3.Error as error:
            raise AssessmentPackageUnavailableError(
                "Assessment Package storage is unavailable."
            ) from error

    @staticmethod
    def _map_repository_error(error):
        if isinstance(error, AssessmentImportRepositoryNotFoundError):
            raise AssessmentPackageNotFoundError(str(error)) from error
        if isinstance(error, AssessmentImportRepositoryConflictError):
            raise AssessmentPackageConflictError(str(error)) from error
        if isinstance(error, AssessmentImportRepositoryDataError):
            raise AssessmentPackageValidationError(str(error)) from error
        raise error

    def stage_upload(
        self,
        filename: str,
        raw: bytes,
        *,
        workspace_kind: str,
        selected_course_id: str,
    ):
        workspace_kind = str(workspace_kind or "").strip().lower()
        if workspace_kind not in AUTHORING_WORKSPACE_KINDS:
            raise AssessmentPackageValidationError(
                "Choose whether this package is a Quiz, Exam or Test."
            )
        selected_course_id = str(selected_course_id or "").strip()
        if not selected_course_id:
            raise AssessmentPackageValidationError(
                "Choose the ANVAYA subject/course for this package."
            )
        safe_filename = str(filename or "").replace("\\", "/").split("/")[-1]
        lower = safe_filename.lower()
        if not (lower.endswith(".json") or lower.endswith(".anvaya-assessment.json")):
            raise AssessmentPackageValidationError(
                "Upload a .json or .anvaya-assessment.json package."
            )
        package = _parse_json(raw)
        validated = _validate_package(package)
        source_hash = hashlib.sha256(raw).hexdigest()
        canonical_json = json.dumps(
            package, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        now = _now()

        try:
            with self._repository(write=True) as repository:
                course = repository.resolve_course_by_code(
                    validated["assessment"]["course_code"]
                )
                if course is None:
                    raise AssessmentPackageValidationError(
                        "Package course code {!r} does not exist in ANVAYA.".format(
                            validated["assessment"]["course_code"]
                        )
                    )
                selected_course = repository.get_course(selected_course_id)
                if selected_course is None:
                    raise AssessmentPackageValidationError(
                        "The selected ANVAYA subject/course no longer exists."
                    )
                if str(selected_course["id"]) != str(course["id"]):
                    raise AssessmentPackageValidationError(
                        "Selected subject {} does not match package course code {}. "
                        "Choose the matching subject or regenerate the package with Alex."
                        .format(
                            selected_course["code"],
                            validated["assessment"]["course_code"],
                        )
                    )
                existing = repository.find_batch_identity(
                    validated["package_id"], validated["package_revision"]
                )
                if existing is not None:
                    if str(existing["source_sha256"]) == source_hash:
                        return repository.get_batch(str(existing["id"]))
                    raise AssessmentPackageConflictError(
                        "The same package ID/revision already exists with different content. "
                        "Increase package_revision for a changed package."
                    )

                topics = repository.topic_catalogue(str(course["id"]))
                batch_id = str(uuid.uuid4())
                staged_questions = []
                for item in validated["questions"]:
                    selected_topic_id, local_score = _best_topic(
                        item["raw_topic_label"], topics
                    )
                    combined_confidence = min(
                        float(item["package_mapping_confidence"]), float(local_score)
                    )
                    review_required = (
                        bool(item["review_required"])
                        or selected_topic_id is None
                        or combined_confidence < 0.75
                        or float(item["authoring_confidence"]) < 0.75
                    )
                    correct = set(item["answer"]["correct_option_ids"])
                    staged_questions.append(
                        {
                            "id": str(uuid.uuid4()),
                            "batch_id": batch_id,
                            "package_question_id": item["package_question_id"],
                            "ordinal": item["ordinal"],
                            "question_number": item["question_number"],
                            "section_label": item["section_label"],
                            "question_type": item["question_type"],
                            "question_text": item["question_text"],
                            "max_marks_milli": item["max_marks_milli"],
                            "negative_marks_milli": item["negative_marks_milli"],
                            "scoring_policy": item["scoring_policy"],
                            "difficulty": item["difficulty"],
                            "expected_method": item["expected_method"],
                            "estimated_seconds": item["estimated_seconds"],
                            "chapter_label": item["chapter_label"],
                            "raw_topic_label": item["raw_topic_label"],
                            "subtopic_label": item["subtopic_label"],
                            "concepts_json": json.dumps(
                                item["concepts"], ensure_ascii=False
                            ),
                            "authoring_confidence": item["authoring_confidence"],
                            "mapping_confidence": combined_confidence,
                            "selected_topic_id": selected_topic_id,
                            "review_required": review_required,
                            "solution_text": item["solution_text"],
                            "rubric_text": item["rubric_text"],
                            "answer_json": json.dumps(
                                item["answer"], ensure_ascii=False, sort_keys=True
                            ),
                            "source_kind": item["source_kind"],
                            "source_label": item["source_label"],
                            "source_page": item["source_page"],
                            "source_locator": item["source_locator"],
                            "created_at": now,
                            "updated_at": now,
                            "options": [
                                {
                                    "option_id": option["id"],
                                    "position": position,
                                    "option_text": option["text"],
                                    "is_correct": option["id"] in correct,
                                }
                                for position, option in enumerate(
                                    item["options"], start=1
                                )
                            ],
                        }
                    )

                batch = {
                    "id": batch_id,
                    "package_id": validated["package_id"],
                    "package_revision": validated["package_revision"],
                    "package_schema": PACKAGE_SCHEMA,
                    "package_version": PACKAGE_VERSION,
                    "source_filename": safe_filename,
                    "source_sha256": source_hash,
                    "course_id": str(course["id"]),
                    "title": validated["assessment"]["title"],
                    "assessment_type": validated["assessment"]["assessment_type"],
                    "workspace_kind": workspace_kind,
                    "mode": validated["assessment"]["mode"],
                    "duration_minutes": validated["assessment"]["duration_minutes"],
                    "total_marks_milli": validated["assessment"]["total_marks_milli"],
                    "instructions_text": "\n".join(
                        validated["assessment"]["instructions"]
                    ),
                    "authoring_engine": validated["authoring"]["engine"],
                    "authoring_model": validated["authoring"]["model"],
                    "authoring_purpose": validated["authoring"]["purpose"],
                    "package_json": canonical_json,
                    "validation_notes_json": json.dumps(
                        validated["warnings"], ensure_ascii=False
                    ),
                    "created_at": now,
                    "updated_at": now,
                }
                return repository.create_batch(batch, staged_questions)
        except (
            AssessmentImportRepositoryNotFoundError,
            AssessmentImportRepositoryConflictError,
            AssessmentImportRepositoryDataError,
        ) as error:
            self._map_repository_error(error)

    def workspace(self, *, workspace_kind: str = "", course_id: str = ""):
        workspace_kind = str(workspace_kind or "").strip().lower()
        if workspace_kind and workspace_kind not in AUTHORING_WORKSPACE_KINDS:
            workspace_kind = ""
        course_id = str(course_id or "").strip()
        with self._repository(write=False) as repository:
            courses = tuple(dict(item) for item in repository.list_courses())
            selected_course = repository.get_course(course_id) if course_id else None
            if course_id and selected_course is None:
                course_id = ""
            batches = repository.list_batches(
                workspace_kind=workspace_kind or None,
                course_id=course_id or None,
                limit=100,
            )
            preference = repository.get_authoring_preference()

        default_prompt = _default_authoring_prompt()
        master_prompt = (
            str(preference["master_prompt"])
            if preference is not None
            else default_prompt
        )
        selected_course = (
            next((item for item in courses if str(item["id"]) == course_id), None)
            if course_id
            else None
        )
        return {
            "available": True,
            "batches": tuple(self._decorate_batch_summary(item) for item in batches),
            "schema": PACKAGE_SCHEMA,
            "version": PACKAGE_VERSION,
            "courses": courses,
            "workspace_kinds": tuple(
                {"id": key, **value}
                for key, value in AUTHORING_WORKSPACE_KINDS.items()
            ),
            "selected_kind": workspace_kind,
            "selected_course_id": course_id,
            "selected_course": selected_course,
            "master_prompt": master_prompt,
            "resolved_prompt": _render_authoring_prompt(
                master_prompt,
                workspace_kind=workspace_kind,
                course=selected_course,
            ),
            "prompt_is_custom": preference is not None,
            "prompt_revision": int(preference["revision"]) if preference else 0,
        }

    def save_master_prompt(self, prompt: str):
        value = str(prompt or "").strip()
        if not value:
            raise AssessmentPackageValidationError(
                "Master prompt cannot be empty."
            )
        if len(value) > MASTER_PROMPT_MAX_CHARS:
            raise AssessmentPackageValidationError(
                "Master prompt is too long."
            )
        try:
            with self._repository(write=True) as repository:
                return repository.save_authoring_prompt(value, now=_now())
        except (
            AssessmentImportRepositoryNotFoundError,
            AssessmentImportRepositoryConflictError,
            AssessmentImportRepositoryDataError,
        ) as error:
            self._map_repository_error(error)

    def reset_master_prompt(self):
        try:
            with self._repository(write=True) as repository:
                repository.reset_authoring_prompt()
        except (
            AssessmentImportRepositoryNotFoundError,
            AssessmentImportRepositoryConflictError,
            AssessmentImportRepositoryDataError,
        ) as error:
            self._map_repository_error(error)

    @staticmethod
    def _decorate_batch_summary(item):
        result = dict(item)
        result["status_label"] = str(result.get("status") or "").replace("_", " ").title()
        result["workspace_kind"] = str(
            result.get("workspace_kind")
            or _infer_workspace_kind(result.get("assessment_type"))
        )
        result["workspace_kind_label"] = AUTHORING_WORKSPACE_KINDS[
            result["workspace_kind"]
        ]["label"]
        return result

    @staticmethod
    def _decorate_question(item):
        result = dict(item)
        try:
            result["concepts"] = json.loads(str(result.get("concepts_json") or "[]"))
        except json.JSONDecodeError:
            result["concepts"] = []
        try:
            result["answer"] = json.loads(str(result.get("answer_json") or "{}"))
        except json.JSONDecodeError:
            result["answer"] = {}
        result["marks"] = _marks_text(result.get("max_marks_milli"))
        result["negative_marks"] = _marks_text(result.get("negative_marks_milli"))
        result["estimated_minutes"] = (
            round(int(result["estimated_seconds"]) / 60, 2)
            if result.get("estimated_seconds")
            else ""
        )
        result["review_required"] = bool(result.get("review_required"))
        result["options"] = tuple(
            {**dict(option), "is_correct": bool(option.get("is_correct"))}
            for option in result.get("options") or ()
        )
        return result

    def _decorate_batch(self, batch, topics):
        result = dict(batch)
        result["questions"] = tuple(
            self._decorate_question(item) for item in batch.get("questions") or ()
        )
        try:
            result["validation_notes"] = json.loads(
                str(result.get("validation_notes_json") or "[]")
            )
        except json.JSONDecodeError:
            result["validation_notes"] = []
        result["total_marks"] = _marks_text(result.get("total_marks_milli"))
        result["topics"] = tuple(dict(item) for item in topics)
        blockers = self._review_blockers(result)
        result["blockers"] = tuple(blockers)
        result["can_approve"] = (
            str(result.get("status")) == "review" and not blockers
        )
        result["calculated_marks_milli"] = sum(
            int(item.get("max_marks_milli") or 0) for item in result["questions"]
        )
        result["calculated_marks"] = _marks_text(result["calculated_marks_milli"])
        return result

    def review(self, batch_id: str):
        with self._repository(write=False) as repository:
            batch = repository.get_batch(str(batch_id))
            if batch is None:
                raise AssessmentPackageNotFoundError("Import batch not found.")
            topics = repository.topic_catalogue(str(batch["course_id"]))
        return self._decorate_batch(batch, topics)

    def question_editor(self, question_id: str):
        with self._repository(write=False) as repository:
            question = repository.get_question(str(question_id))
            if question is None:
                raise AssessmentPackageNotFoundError("Staged question not found.")
            batch = repository.get_batch(str(question["batch_id"]))
            if batch is None:
                raise AssessmentPackageNotFoundError("Import batch not found.")
            topics = repository.topic_catalogue(str(batch["course_id"]))
        return {
            "batch": self._decorate_batch(batch, topics),
            "question": self._decorate_question(question),
            "topics": tuple(dict(item) for item in topics),
            "question_types": tuple(sorted(QUESTION_TYPES)),
            "scoring_policies": tuple(sorted(SCORING_POLICIES)),
            "difficulties": tuple(sorted(DIFFICULTIES)),
        }

    @staticmethod
    def _review_blockers(batch):
        blockers = []
        questions = list(batch.get("questions") or ())
        if not questions:
            blockers.append("The package has no questions.")
            return blockers
        total = 0
        expected_ordinals = list(range(1, len(questions) + 1))
        ordinals = [int(item.get("ordinal") or 0) for item in questions]
        if ordinals != expected_ordinals:
            blockers.append("Question order is not contiguous.")
        for item in questions:
            label = "Question {}".format(item.get("question_number") or item.get("ordinal"))
            marks = item.get("max_marks_milli")
            if marks is None or int(marks) <= 0:
                blockers.append("{} needs positive marks.".format(label))
            else:
                total += int(marks)
            if not str(item.get("selected_topic_id") or ""):
                blockers.append("{} needs a confirmed course topic.".format(label))
            if bool(item.get("review_required")):
                blockers.append("{} is still marked Review required.".format(label))
            if not str(item.get("question_text") or "").strip():
                blockers.append("{} has no question text.".format(label))
            if not str(item.get("solution_text") or "").strip():
                blockers.append("{} needs a solution.".format(label))
            question_type = str(item.get("question_type") or "")
            options = list(item.get("options") or ())
            correct = [option for option in options if bool(option.get("is_correct"))]
            if question_type == "mcq":
                if len(options) < 2 or len(correct) != 1:
                    blockers.append("{} needs valid MCQ options and one correct answer.".format(label))
            elif question_type == "msq":
                if len(options) < 2 or not correct:
                    blockers.append("{} needs valid MSQ options and correct selections.".format(label))
            elif question_type in ACCEPTED_ANSWER_TYPES:
                try:
                    answer = json.loads(str(item.get("answer_json") or "{}"))
                except json.JSONDecodeError:
                    answer = {}
                if not list(answer.get("accepted_answers") or ()):
                    blockers.append("{} needs at least one accepted answer.".format(label))
            elif question_type in SUBJECTIVE_TYPES:
                if not str(item.get("rubric_text") or "").strip():
                    blockers.append("{} needs a subjective marking rubric.".format(label))
        if total != int(batch.get("total_marks_milli") or 0):
            blockers.append(
                "Assessment total marks ({}) do not match question marks ({}).".format(
                    _marks_text(batch.get("total_marks_milli")), _marks_text(total)
                )
            )
        return blockers

    def update_metadata(self, batch_id: str, payload: dict):
        title = _nonempty(str(payload.get("title") or ""), "Title", maximum=240)
        assessment_type = str(payload.get("assessment_type") or "").strip()
        if assessment_type not in ASSESSMENT_TYPES:
            raise AssessmentPackageValidationError("Choose a valid assessment type.")
        mode = str(payload.get("mode") or "").strip()
        if mode not in MODES:
            raise AssessmentPackageValidationError("Choose exam or practice mode.")
        duration = _positive_int(
            payload.get("duration_minutes"), "Duration", maximum=1440
        )
        total = _milli(payload.get("total_marks"), "Total marks", allow_zero=False)
        instructions = str(payload.get("instructions_text") or "").strip()
        try:
            with self._repository(write=True) as repository:
                return repository.update_batch_metadata(
                    str(batch_id),
                    title=title,
                    assessment_type=assessment_type,
                    mode=mode,
                    duration_minutes=duration,
                    total_marks_milli=total,
                    instructions_text=instructions,
                    now=_now(),
                )
        except (
            AssessmentImportRepositoryNotFoundError,
            AssessmentImportRepositoryConflictError,
            AssessmentImportRepositoryDataError,
        ) as error:
            self._map_repository_error(error)

    def update_question(self, question_id: str, payload: dict):
        editor = self.question_editor(question_id)
        current = editor["question"]
        if str(editor["batch"].get("status")) != "review":
            raise AssessmentPackageConflictError("Approved/rejected imports cannot be edited.")

        question_type = str(payload.get("question_type") or "").strip()
        if question_type not in QUESTION_TYPES:
            raise AssessmentPackageValidationError("Choose a valid question type.")
        question_text = _nonempty(
            str(payload.get("question_text") or ""), "Question text", maximum=50000
        )
        marks = _milli(payload.get("marks"), "Marks", allow_zero=False)
        negative = _milli(payload.get("negative_marks") or "0", "Negative marks")
        if negative > marks:
            raise AssessmentPackageValidationError("Negative marks cannot exceed marks.")
        scoring = str(payload.get("scoring_policy") or "").strip()
        if scoring not in SCORING_POLICIES:
            raise AssessmentPackageValidationError("Choose a valid scoring policy.")
        difficulty = str(payload.get("difficulty") or "").strip()
        if difficulty not in DIFFICULTIES:
            raise AssessmentPackageValidationError("Choose a valid difficulty.")
        estimated = str(payload.get("estimated_minutes") or "").strip()
        if not estimated:
            estimated_seconds = None
        else:
            try:
                minutes = Decimal(estimated)
            except InvalidOperation as error:
                raise AssessmentPackageValidationError(
                    "Estimated minutes must be a number."
                ) from error
            if not minutes.is_finite() or minutes <= 0 or minutes > Decimal(600):
                raise AssessmentPackageValidationError(
                    "Estimated minutes must be between 0 and 600."
                )
            estimated_seconds = int((minutes * Decimal(60)).to_integral_value())

        selected_topic_id = str(payload.get("selected_topic_id") or "").strip()
        topic_ids = {str(item["id"]) for item in editor["topics"]}
        if selected_topic_id not in topic_ids:
            raise AssessmentPackageValidationError(
                "Choose a topic from this assessment's course."
            )
        concepts = [
            item.strip()
            for item in re.split(r"[\n,]+", str(payload.get("concepts") or ""))
            if item.strip()
        ][:30]
        solution = str(payload.get("solution_text") or "").strip()
        rubric = str(payload.get("rubric_text") or "").strip()
        accepted_answers = [
            item.strip()
            for item in str(payload.get("accepted_answers") or "").splitlines()
            if item.strip()
        ]
        correct_ids = {
            str(item) for item in payload.get("correct_option_ids") or ()
            if str(item).strip()
        }

        options = []
        if question_type in OBJECTIVE_OPTION_TYPES:
            current_options = list(current.get("options") or ())
            if len(current_options) < 2:
                raise AssessmentPackageValidationError(
                    "MCQ/MSQ questions need at least two package options."
                )
            option_texts = list(payload.get("option_texts") or ())
            for index, option in enumerate(current_options):
                text_value = (
                    option_texts[index]
                    if index < len(option_texts)
                    else option.get("option_text")
                )
                option_text = _nonempty(
                    str(text_value or ""),
                    "Option {}".format(option.get("option_id")),
                    maximum=10000,
                )
                options.append(
                    {
                        "option_id": str(option["option_id"]),
                        "position": int(option["position"]),
                        "option_text": option_text,
                        "is_correct": str(option["option_id"]) in correct_ids,
                    }
                )
            if question_type == "mcq" and sum(x["is_correct"] for x in options) != 1:
                raise AssessmentPackageValidationError(
                    "MCQ requires exactly one correct option."
                )
            if question_type == "msq" and not any(x["is_correct"] for x in options):
                raise AssessmentPackageValidationError(
                    "MSQ requires at least one correct option."
                )
            answer = {
                "correct_option_ids": [
                    item["option_id"] for item in options if item["is_correct"]
                ],
                "accepted_answers": [],
            }
        else:
            options = []
            if question_type in ACCEPTED_ANSWER_TYPES and not accepted_answers:
                raise AssessmentPackageValidationError(
                    "This question type needs at least one accepted answer."
                )
            if question_type in SUBJECTIVE_TYPES:
                accepted_answers = []
            answer = {
                "correct_option_ids": [],
                "accepted_answers": accepted_answers,
            }

        if not solution:
            raise AssessmentPackageValidationError("Solution cannot be empty.")
        if question_type in SUBJECTIVE_TYPES and not rubric:
            raise AssessmentPackageValidationError(
                "Subjective questions require a marking rubric."
            )

        record = {
            "question_number": str(payload.get("question_number") or "").strip(),
            "section_label": str(payload.get("section_label") or "").strip(),
            "question_type": question_type,
            "question_text": question_text,
            "max_marks_milli": marks,
            "negative_marks_milli": negative,
            "scoring_policy": scoring,
            "difficulty": difficulty,
            "expected_method": str(payload.get("expected_method") or "").strip(),
            "estimated_seconds": estimated_seconds,
            "chapter_label": str(payload.get("chapter_label") or "").strip(),
            "raw_topic_label": str(payload.get("raw_topic_label") or "").strip(),
            "subtopic_label": str(payload.get("subtopic_label") or "").strip(),
            "concepts_json": json.dumps(concepts, ensure_ascii=False),
            "authoring_confidence": current.get("authoring_confidence"),
            "mapping_confidence": 1.0,
            "selected_topic_id": selected_topic_id,
            "review_required": not bool(payload.get("review_complete")),
            "solution_text": solution,
            "rubric_text": rubric,
            "answer_json": json.dumps(answer, ensure_ascii=False, sort_keys=True),
            "source_kind": str(payload.get("source_kind") or "").strip(),
            "source_label": str(payload.get("source_label") or "").strip(),
            "source_page": (
                _positive_int(payload.get("source_page"), "Source page")
                if str(payload.get("source_page") or "").strip()
                else None
            ),
            "source_locator": str(payload.get("source_locator") or "").strip(),
        }
        try:
            with self._repository(write=True) as repository:
                return repository.update_question(
                    str(question_id), record, options, now=_now()
                )
        except (
            AssessmentImportRepositoryNotFoundError,
            AssessmentImportRepositoryConflictError,
            AssessmentImportRepositoryDataError,
        ) as error:
            self._map_repository_error(error)

    def reorder(self, question_id: str, direction: str):
        if direction not in {"up", "down"}:
            raise AssessmentPackageValidationError("Direction must be up or down.")
        try:
            with self._repository(write=True) as repository:
                repository.reorder_question(str(question_id), direction, now=_now())
        except (
            AssessmentImportRepositoryNotFoundError,
            AssessmentImportRepositoryConflictError,
            AssessmentImportRepositoryDataError,
        ) as error:
            self._map_repository_error(error)

    def remove(self, question_id: str):
        try:
            with self._repository(write=True) as repository:
                repository.remove_question(str(question_id), now=_now())
        except (
            AssessmentImportRepositoryNotFoundError,
            AssessmentImportRepositoryConflictError,
            AssessmentImportRepositoryDataError,
        ) as error:
            self._map_repository_error(error)

    def split(self, question_id: str, marker: str):
        editor = self.question_editor(question_id)
        question = editor["question"]
        if question.get("question_type") not in SUBJECTIVE_TYPES:
            raise AssessmentPackageValidationError(
                "Only subjective questions can be split safely."
            )
        if question.get("options"):
            raise AssessmentPackageValidationError(
                "Subjective split cannot contain objective options."
            )
        marker = str(marker or "")
        if not marker.strip() or marker not in str(question["question_text"]):
            raise AssessmentPackageValidationError(
                "Enter an exact piece of text where the second question begins."
            )
        first_text, second_text = str(question["question_text"]).split(marker, 1)
        second_text = marker + second_text
        if not first_text.strip() or not second_text.strip():
            raise AssessmentPackageValidationError(
                "Split point must leave text on both sides."
            )
        now = _now()
        second = {
            "id": str(uuid.uuid4()),
            "package_question_id": "{}-split-{}".format(
                question["package_question_id"], uuid.uuid4().hex[:8]
            ),
            "question_number": "{}b".format(question.get("question_number") or question["ordinal"]),
            "section_label": question.get("section_label") or "",
            "question_type": question["question_type"],
            "question_text": second_text.strip(),
            "max_marks_milli": None,
            "negative_marks_milli": 0,
            "scoring_policy": question.get("scoring_policy") or "standard",
            "difficulty": question.get("difficulty") or "",
            "expected_method": question.get("expected_method") or "",
            "estimated_seconds": question.get("estimated_seconds"),
            "chapter_label": question.get("chapter_label") or "",
            "raw_topic_label": question.get("raw_topic_label") or "",
            "subtopic_label": question.get("subtopic_label") or "",
            "concepts_json": question.get("concepts_json") or "[]",
            "authoring_confidence": question.get("authoring_confidence"),
            "mapping_confidence": question.get("mapping_confidence"),
            "selected_topic_id": question.get("selected_topic_id"),
            "review_required": True,
            "solution_text": "",
            "rubric_text": "",
            "answer_json": "{}",
            "source_kind": question.get("source_kind") or "",
            "source_label": question.get("source_label") or "",
            "source_page": question.get("source_page"),
            "source_locator": question.get("source_locator") or "",
            "created_at": now,
            "updated_at": now,
            "options": [],
        }
        first = {
            "question_text": first_text.strip(),
            "question_number": "{}a".format(
                question.get("question_number") or question["ordinal"]
            ),
        }
        try:
            with self._repository(write=True) as repository:
                return repository.split_question(
                    str(question_id), first, second, now=now
                )
        except (
            AssessmentImportRepositoryNotFoundError,
            AssessmentImportRepositoryConflictError,
            AssessmentImportRepositoryDataError,
        ) as error:
            self._map_repository_error(error)

    def merge_next(self, question_id: str):
        editor = self.question_editor(question_id)
        batch = editor["batch"]
        question = editor["question"]
        questions = list(batch["questions"])
        index = next(
            (i for i, item in enumerate(questions) if str(item["id"]) == str(question_id)),
            None,
        )
        if index is None or index + 1 >= len(questions):
            raise AssessmentPackageValidationError(
                "There is no next question to merge."
            )
        other = questions[index + 1]
        if (
            question.get("question_type") not in SUBJECTIVE_TYPES
            or other.get("question_type") not in SUBJECTIVE_TYPES
        ):
            raise AssessmentPackageValidationError(
                "Only adjacent subjective questions can be merged safely."
            )
        if question.get("options") or other.get("options"):
            raise AssessmentPackageValidationError(
                "Subjective merge cannot contain objective options."
            )
        concepts = []
        for source in (question.get("concepts") or (), other.get("concepts") or ()):
            for item in source:
                if item not in concepts:
                    concepts.append(item)
        marks = (
            int(question["max_marks_milli"]) + int(other["max_marks_milli"])
            if question.get("max_marks_milli") is not None
            and other.get("max_marks_milli") is not None
            else None
        )
        selected_topic = (
            question.get("selected_topic_id")
            if question.get("selected_topic_id") == other.get("selected_topic_id")
            else None
        )
        merged = {
            "question_text": "{}\n\n{}".format(
                str(question["question_text"]).strip(),
                str(other["question_text"]).strip(),
            ),
            "question_number": "{}/{}".format(
                question.get("question_number") or question["ordinal"],
                other.get("question_number") or other["ordinal"],
            ),
            "section_label": question.get("section_label") or other.get("section_label") or "",
            "question_type": question["question_type"],
            "max_marks_milli": marks,
            "negative_marks_milli": int(question.get("negative_marks_milli") or 0)
            + int(other.get("negative_marks_milli") or 0),
            "scoring_policy": question.get("scoring_policy") or "standard",
            "difficulty": question.get("difficulty") or other.get("difficulty") or "",
            "expected_method": question.get("expected_method") or "",
            "estimated_seconds": (
                int(question.get("estimated_seconds") or 0)
                + int(other.get("estimated_seconds") or 0)
            ) or None,
            "chapter_label": question.get("chapter_label") or other.get("chapter_label") or "",
            "raw_topic_label": question.get("raw_topic_label") or other.get("raw_topic_label") or "",
            "subtopic_label": question.get("subtopic_label") or other.get("subtopic_label") or "",
            "concepts_json": json.dumps(concepts, ensure_ascii=False),
            "authoring_confidence": min(
                float(question.get("authoring_confidence") or 0),
                float(other.get("authoring_confidence") or 0),
            ),
            "mapping_confidence": (
                min(
                    float(question.get("mapping_confidence") or 0),
                    float(other.get("mapping_confidence") or 0),
                )
                if selected_topic
                else None
            ),
            "selected_topic_id": selected_topic,
            "solution_text": "\n\n".join(
                part for part in (
                    str(question.get("solution_text") or "").strip(),
                    str(other.get("solution_text") or "").strip(),
                ) if part
            ),
            "rubric_text": "\n\n".join(
                part for part in (
                    str(question.get("rubric_text") or "").strip(),
                    str(other.get("rubric_text") or "").strip(),
                ) if part
            ),
            "answer_json": "{}",
            "source_kind": question.get("source_kind") or other.get("source_kind") or "",
            "source_label": question.get("source_label") or other.get("source_label") or "",
            "source_page": question.get("source_page") or other.get("source_page"),
            "source_locator": question.get("source_locator") or other.get("source_locator") or "",
        }
        try:
            with self._repository(write=True) as repository:
                return repository.merge_with_next(
                    str(question_id), merged, now=_now()
                )
        except (
            AssessmentImportRepositoryNotFoundError,
            AssessmentImportRepositoryConflictError,
            AssessmentImportRepositoryDataError,
        ) as error:
            self._map_repository_error(error)

    def reject(self, batch_id: str):
        try:
            with self._repository(write=True) as repository:
                return repository.reject_batch(str(batch_id), now=_now())
        except (
            AssessmentImportRepositoryNotFoundError,
            AssessmentImportRepositoryConflictError,
            AssessmentImportRepositoryDataError,
        ) as error:
            self._map_repository_error(error)

    def approve(self, batch_id: str):
        review = self.review(batch_id)
        if str(review.get("status")) == "approved":
            return str(review.get("assessment_id") or "")
        blockers = list(review.get("blockers") or ())
        if blockers:
            raise AssessmentPackageConflictError(
                "Import cannot be approved yet: {}".format(" | ".join(blockers[:8]))
            )
        now = _now()
        assessment_id = str(uuid.uuid4())
        assessment_topics = []
        seen_topics = set()
        for question in review["questions"]:
            topic_id = str(question["selected_topic_id"])
            if topic_id in seen_topics:
                continue
            seen_topics.add(topic_id)
            assessment_topics.append(
                {
                    "id": str(uuid.uuid4()),
                    "topic_id": topic_id,
                    "raw_label": str(question.get("raw_topic_label") or ""),
                    "confidence": question.get("mapping_confidence"),
                }
            )

        canonical_questions = []
        for question in review["questions"]:
            question_id = str(uuid.uuid4())
            answer_json = str(question.get("answer_json") or "{}")
            canonical_questions.append(
                {
                    "id": question_id,
                    "staged_question_id": str(question["id"]),
                    "ordinal": int(question["ordinal"]),
                    "question_text": str(question["question_text"]),
                    "max_marks_milli": int(question["max_marks_milli"]),
                    "spec": {
                        "package_question_id": str(question["package_question_id"]),
                        "question_number": str(question.get("question_number") or ""),
                        "section_label": str(question.get("section_label") or ""),
                        "question_type": str(question["question_type"]),
                        "negative_marks_milli": int(
                            question.get("negative_marks_milli") or 0
                        ),
                        "scoring_policy": str(
                            question.get("scoring_policy") or "standard"
                        ),
                        "difficulty": str(question.get("difficulty") or ""),
                        "expected_method": str(question.get("expected_method") or ""),
                        "estimated_seconds": question.get("estimated_seconds"),
                        "chapter_label": str(question.get("chapter_label") or ""),
                        "subtopic_label": str(question.get("subtopic_label") or ""),
                        "concepts_json": str(question.get("concepts_json") or "[]"),
                        "authoring_confidence": question.get("authoring_confidence"),
                        "solution_text": str(question.get("solution_text") or ""),
                        "rubric_text": str(question.get("rubric_text") or ""),
                        "answer_json": answer_json,
                        "source_kind": str(question.get("source_kind") or ""),
                    },
                    "options": tuple(dict(option) for option in question.get("options") or ()),
                    "source": (
                        {
                            "id": str(uuid.uuid4()),
                            "page_number": question.get("source_page"),
                            "locator": str(question.get("source_locator") or ""),
                            "raw_source_label": str(question.get("source_label") or ""),
                        }
                        if (
                            question.get("source_label")
                            or question.get("source_page")
                            or question.get("source_locator")
                        )
                        else None
                    ),
                    "mapping": {
                        "id": str(uuid.uuid4()),
                        "topic_id": str(question["selected_topic_id"]),
                        "score": question.get("mapping_confidence"),
                        "reason": "Reviewed import mapping for package topic {!r}.".format(
                            str(question.get("raw_topic_label") or "")
                        ),
                    },
                }
            )

        canonical = {
            "assessment": {
                "id": assessment_id,
                "course_id": str(review["course_id"]),
                "assessment_type": str(review["assessment_type"]),
                "title": str(review["title"]),
                "max_points_milli": int(review["total_marks_milli"]),
                "description": (
                    "Imported from ANVAYA Assessment Package {} revision {}."
                    .format(review["package_id"], review["package_revision"])
                ),
            },
            "runtime": {
                "mode": str(review["mode"]),
                "duration_minutes": int(review["duration_minutes"]),
                "instructions_text": str(review.get("instructions_text") or ""),
                "origin": "external_package",
                "package_id": str(review["package_id"]),
                "package_revision": int(review["package_revision"]),
            },
            "assessment_topics": assessment_topics,
            "questions": canonical_questions,
        }
        try:
            with self._repository(write=True) as repository:
                return repository.approve_batch(str(batch_id), canonical, now=now)
        except (
            AssessmentImportRepositoryNotFoundError,
            AssessmentImportRepositoryConflictError,
            AssessmentImportRepositoryDataError,
        ) as error:
            self._map_repository_error(error)


def build_assessment_package_service(database_path=None) -> AssessmentPackageService:
    return AssessmentPackageService(database_path or config.DATABASE_PATH)
