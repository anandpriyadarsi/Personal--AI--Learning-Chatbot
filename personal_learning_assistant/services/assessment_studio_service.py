"""Assessment Studio Phase A application service.

Phase A owns reusable assessment-template configuration only. It deliberately
does not create attempts, evaluate answers, infer mastery, or mutate plans.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote

import config
from personal_learning_assistant.repositories.sqlite.assessment_studio_repository import (
    AssessmentStudioRepositoryConflictError,
    AssessmentStudioRepositoryDataError,
    AssessmentStudioRepositoryNotFoundError,
    AssessmentStudioRepositorySchemaError,
    SQLiteAssessmentStudioRepository,
)
from personal_learning_assistant.repositories.sqlite.connection import connect_database


QUESTION_TYPES = (
    ("mcq", "MCQ · single select"),
    ("msq", "MSQ · multiple select"),
    ("numerical", "Numerical answer"),
    ("fill_blank", "Fill in the blank"),
    ("true_false", "True / False"),
    ("short_subjective", "Short subjective"),
    ("long_subjective", "Long subjective"),
)
SCORING_POLICIES = (
    ("standard", "Standard / configured marks"),
    ("all_or_nothing", "All or nothing"),
    ("partial", "Partial marking"),
    ("custom", "Custom course rule"),
)
ASSESSMENT_TYPES = (
    ("quiz", "Quiz"),
    ("midsem", "Mid-Sem"),
    ("endsem", "End-Sem"),
    ("topic_test", "Topic Test"),
    ("previous_paper", "Previous Paper"),
    ("custom", "Custom"),
)
MODES = (("exam", "Exam mode"), ("practice", "Practice mode"))

PRESETS = {
    "quiz": {
        "name": "Quiz Practice",
        "assessment_type": "quiz",
        "mode": "exam",
        "duration_minutes": "30",
    },
    "midsem": {
        "name": "Mid-Sem Practice",
        "assessment_type": "midsem",
        "mode": "exam",
        "duration_minutes": "60",
    },
    "endsem": {
        "name": "End-Sem Practice",
        "assessment_type": "endsem",
        "mode": "exam",
        "duration_minutes": "180",
    },
    "topic_test": {
        "name": "Topic Test",
        "assessment_type": "topic_test",
        "mode": "practice",
        "duration_minutes": "30",
    },
}


class AssessmentStudioError(RuntimeError):
    pass


class AssessmentStudioValidationError(AssessmentStudioError):
    pass


class AssessmentStudioNotFoundError(AssessmentStudioError):
    pass


class AssessmentStudioConflictError(AssessmentStudioError):
    pass


class AssessmentStudioUnavailableError(AssessmentStudioError):
    pass


def _now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _marks_text(value):
    if value is None:
        return ""
    number = Decimal(int(value)) / Decimal(1000)
    text = format(number, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _milli(value, field: str, *, optional: bool = False):
    text = str(value or "").strip()
    if not text:
        if optional:
            return None
        raise AssessmentStudioValidationError("{} is required.".format(field))
    try:
        number = Decimal(text)
    except InvalidOperation as error:
        raise AssessmentStudioValidationError(
            "{} must be a number.".format(field)
        ) from error
    if not number.is_finite() or number < 0:
        raise AssessmentStudioValidationError(
            "{} must be zero or greater.".format(field)
        )
    scaled = number * Decimal(1000)
    if scaled != scaled.to_integral_value():
        raise AssessmentStudioValidationError(
            "{} supports at most three decimal places.".format(field)
        )
    return int(scaled)


def _positive_int(value, field: str, *, maximum: int | None = None):
    text = str(value or "").strip()
    try:
        result = int(text)
    except (TypeError, ValueError) as error:
        raise AssessmentStudioValidationError(
            "{} must be a whole number.".format(field)
        ) from error
    if result <= 0 or (maximum is not None and result > maximum):
        suffix = " and at most {}".format(maximum) if maximum is not None else ""
        raise AssessmentStudioValidationError(
            "{} must be greater than zero{}.".format(field, suffix)
        )
    return result


def _unique(values):
    result = []
    seen = set()
    for raw in values or ():
        value = str(raw or "").strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


class AssessmentStudioService:
    """Application boundary for template reads and explicit commands."""

    def __init__(self, database_path):
        self.database_path = Path(database_path)

    @contextmanager
    def _repository(self, *, write: bool):
        path = self.database_path
        if not path.exists() or not path.is_file() or path.is_symlink():
            raise AssessmentStudioUnavailableError(
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
                yield SQLiteAssessmentStudioRepository(connection)
            finally:
                connection.close()
        except AssessmentStudioUnavailableError:
            raise
        except AssessmentStudioRepositorySchemaError as error:
            raise AssessmentStudioUnavailableError(
                "Assessment Studio migration 0009 has not been applied."
            ) from error
        except sqlite3.Error as error:
            raise AssessmentStudioUnavailableError(
                "Assessment Studio storage is unavailable."
            ) from error

    @staticmethod
    def _decorate_template(item):
        result = dict(item)
        result["total_marks"] = _marks_text(result.get("total_marks_milli"))
        result["active"] = bool(result.get("is_active"))
        result["assessment_type_label"] = dict(ASSESSMENT_TYPES).get(
            str(result.get("assessment_type")), str(result.get("assessment_type") or "")
        )
        result["mode_label"] = dict(MODES).get(
            str(result.get("mode")), str(result.get("mode") or "")
        )
        if "patterns" in result:
            result["patterns"] = tuple(
                {
                    **dict(pattern),
                    "marks_each": _marks_text(pattern.get("marks_each_milli")),
                    "negative_marks": _marks_text(pattern.get("negative_marks_milli")),
                    "question_type_label": dict(QUESTION_TYPES).get(
                        str(pattern.get("question_type")),
                        str(pattern.get("question_type") or ""),
                    ),
                    "scoring_policy_label": dict(SCORING_POLICIES).get(
                        str(pattern.get("scoring_policy")),
                        str(pattern.get("scoring_policy") or ""),
                    ),
                }
                for pattern in result["patterns"]
            )
        return result

    def overview(self):
        with self._repository(write=False) as repository:
            courses = [dict(item) for item in repository.list_courses()]
            templates = [
                self._decorate_template(item)
                for item in repository.list_templates(include_inactive=True)
            ]
        counts = {}
        for template in templates:
            if template["active"]:
                counts[template["course_id"]] = counts.get(template["course_id"], 0) + 1
        return {
            "available": True,
            "courses": [
                {**course, "template_count": counts.get(course["id"], 0)}
                for course in courses
            ],
            "templates": templates,
            "active_template_count": sum(1 for item in templates if item["active"]),
            "presets": tuple({"id": key, **value} for key, value in PRESETS.items()),
        }

    def course_workspace(self, course_id: str):
        with self._repository(write=False) as repository:
            course = repository.get_course(str(course_id))
            if course is None:
                raise AssessmentStudioNotFoundError("Course not found.")
            topics = repository.list_topics(str(course_id))
            templates = repository.list_templates(
                course_id=str(course_id), include_inactive=True
            )
        return {
            "available": True,
            "course": dict(course),
            "topics": tuple(dict(item) for item in topics),
            "templates": tuple(self._decorate_template(item) for item in templates),
            "presets": tuple({"id": key, **value} for key, value in PRESETS.items()),
        }

    def list_templates(self, *, course_id: str | None = None):
        with self._repository(write=False) as repository:
            courses = tuple(dict(item) for item in repository.list_courses())
            if course_id and repository.get_course(course_id) is None:
                raise AssessmentStudioNotFoundError("Course not found.")
            templates = repository.list_templates(
                course_id=course_id, include_inactive=True
            )
        return {
            "available": True,
            "courses": courses,
            "selected_course_id": str(course_id or ""),
            "templates": tuple(self._decorate_template(item) for item in templates),
        }

    def template_detail(self, template_id: str):
        with self._repository(write=False) as repository:
            item = repository.get_template(str(template_id))
        if item is None:
            raise AssessmentStudioNotFoundError("Template not found.")
        return self._decorate_template(item)

    @staticmethod
    def _blank_patterns():
        return [
            {
                "question_type": "mcq",
                "question_count": "",
                "marks_each": "",
                "negative_marks": "0",
                "scoring_policy": "standard",
            }
            for _ in range(4)
        ]

    def form_context(
        self,
        *,
        course_id: str = "",
        preset: str = "",
        template_id: str | None = None,
        draft: dict | None = None,
    ):
        with self._repository(write=False) as repository:
            courses = tuple(dict(item) for item in repository.list_courses())
            topics = tuple(dict(item) for item in repository.list_topics())
            current = repository.get_template(template_id) if template_id else None
        if template_id and current is None:
            raise AssessmentStudioNotFoundError("Template not found.")

        form = {
            "id": "",
            "course_id": str(course_id or ""),
            "name": "",
            "assessment_type": "quiz",
            "mode": "exam",
            "description": "",
            "instructions": "",
            "duration_minutes": "30",
            "total_marks": "",
            "revision": "",
            "topic_ids": [],
            "patterns": self._blank_patterns(),
        }
        preset_values = PRESETS.get(str(preset or "").strip())
        if preset_values:
            form.update(preset_values)

        if current:
            decorated = self._decorate_template(current)
            form.update(
                {
                    "id": str(decorated["id"]),
                    "course_id": str(decorated["course_id"]),
                    "name": str(decorated["name"]),
                    "assessment_type": str(decorated["assessment_type"]),
                    "mode": str(decorated["mode"]),
                    "description": str(decorated.get("description") or ""),
                    "instructions": str(decorated.get("instructions") or ""),
                    "duration_minutes": str(decorated["duration_minutes"]),
                    "total_marks": str(decorated.get("total_marks") or ""),
                    "revision": str(decorated["revision"]),
                    "topic_ids": [str(item["id"]) for item in decorated["topics"]],
                    "patterns": [
                        {
                            "question_type": str(item["question_type"]),
                            "question_count": str(item["question_count"]),
                            "marks_each": str(item["marks_each"]),
                            "negative_marks": str(item["negative_marks"]),
                            "scoring_policy": str(item["scoring_policy"]),
                        }
                        for item in decorated["patterns"]
                    ],
                }
            )

        if draft:
            for key in (
                "course_id", "name", "assessment_type", "mode", "description",
                "instructions", "duration_minutes", "total_marks", "revision",
            ):
                if key in draft:
                    form[key] = str(draft.get(key) or "")
            form["topic_ids"] = list(draft.get("topic_ids") or [])
            rows = []
            kinds = list(draft.get("pattern_types") or [])
            counts = list(draft.get("pattern_counts") or [])
            marks = list(draft.get("pattern_marks") or [])
            negatives = list(draft.get("pattern_negative_marks") or [])
            policies = list(draft.get("pattern_scoring_policies") or [])
            row_count = max(
                len(kinds), len(counts), len(marks), len(negatives), len(policies), 0
            )
            for index in range(row_count):
                rows.append(
                    {
                        "question_type": kinds[index] if index < len(kinds) else "mcq",
                        "question_count": counts[index] if index < len(counts) else "",
                        "marks_each": marks[index] if index < len(marks) else "",
                        "negative_marks": negatives[index] if index < len(negatives) else "0",
                        "scoring_policy": policies[index] if index < len(policies) else "standard",
                    }
                )
            form["patterns"] = rows or self._blank_patterns()

        while len(form["patterns"]) < 4:
            form["patterns"].append(self._blank_patterns()[0])

        return {
            "available": True,
            "courses": courses,
            "topics": topics,
            "form": form,
            "question_types": QUESTION_TYPES,
            "scoring_policies": SCORING_POLICIES,
            "assessment_types": ASSESSMENT_TYPES,
            "modes": MODES,
        }

    @staticmethod
    def _validate_payload(payload: dict):
        course_id = str(payload.get("course_id") or "").strip()
        name = str(payload.get("name") or "").strip()
        if not course_id:
            raise AssessmentStudioValidationError("Choose a course.")
        if not name:
            raise AssessmentStudioValidationError("Template name is required.")
        if len(name) > 160:
            raise AssessmentStudioValidationError("Template name is too long.")

        assessment_type = str(payload.get("assessment_type") or "").strip()
        if assessment_type not in dict(ASSESSMENT_TYPES):
            raise AssessmentStudioValidationError("Choose a valid assessment type.")
        mode = str(payload.get("mode") or "").strip()
        if mode not in dict(MODES):
            raise AssessmentStudioValidationError("Choose a valid test mode.")
        duration = _positive_int(
            payload.get("duration_minutes"), "Duration", maximum=1440
        )
        total_marks_milli = _milli(
            payload.get("total_marks"), "Total marks", optional=True
        )

        topic_ids = _unique(payload.get("topic_ids") or ())
        kinds = list(payload.get("pattern_types") or ())
        counts = list(payload.get("pattern_counts") or ())
        marks = list(payload.get("pattern_marks") or ())
        negatives = list(payload.get("pattern_negative_marks") or ())
        policies = list(payload.get("pattern_scoring_policies") or ())
        patterns = []
        row_count = max(
            len(kinds), len(counts), len(marks), len(negatives), len(policies), 0
        )
        for index in range(row_count):
            kind = str(kinds[index] if index < len(kinds) else "").strip()
            count = str(counts[index] if index < len(counts) else "").strip()
            mark = str(marks[index] if index < len(marks) else "").strip()
            negative = str(
                negatives[index] if index < len(negatives) else ""
            ).strip()
            policy = str(
                policies[index] if index < len(policies) else "standard"
            ).strip() or "standard"
            if not count and not mark:
                continue
            if kind not in dict(QUESTION_TYPES):
                raise AssessmentStudioValidationError(
                    "Question pattern {} has an invalid type.".format(index + 1)
                )
            question_count = _positive_int(
                count, "Pattern {} question count".format(index + 1)
            )
            marks_each_milli = _milli(
                mark, "Pattern {} marks".format(index + 1)
            )
            negative_marks_milli = _milli(
                negative or "0",
                "Pattern {} negative marks".format(index + 1),
            )
            if negative_marks_milli > marks_each_milli:
                raise AssessmentStudioValidationError(
                    "Negative marks cannot exceed marks for the question."
                )
            if policy not in dict(SCORING_POLICIES):
                raise AssessmentStudioValidationError(
                    "Question pattern {} has an invalid scoring policy.".format(index + 1)
                )
            patterns.append(
                {
                    "id": str(uuid.uuid4()),
                    "question_type": kind,
                    "question_count": question_count,
                    "marks_each_milli": marks_each_milli,
                    "negative_marks_milli": negative_marks_milli,
                    "scoring_policy": policy,
                }
            )
        if not patterns:
            raise AssessmentStudioValidationError("Add at least one question pattern.")

        if total_marks_milli is None:
            total_marks_milli = sum(
                item["question_count"] * item["marks_each_milli"]
                for item in patterns
            )

        now = _now()
        return (
            {
                "course_id": course_id,
                "name": name,
                "assessment_type": assessment_type,
                "mode": mode,
                "description": str(payload.get("description") or "").strip(),
                "instructions": str(payload.get("instructions") or "").strip(),
                "duration_minutes": duration,
                "total_marks_milli": total_marks_milli,
                "provenance": "user",
                "updated_at": now,
            },
            topic_ids,
            patterns,
        )

    def create_template(self, payload: dict):
        record, topic_ids, patterns = self._validate_payload(payload)
        now = record["updated_at"]
        record.update({"id": str(uuid.uuid4()), "created_at": now})
        try:
            with self._repository(write=True) as repository:
                item = repository.create_template(
                    record, topic_ids=topic_ids, patterns=patterns
                )
            return self._decorate_template(item)
        except AssessmentStudioRepositoryConflictError as error:
            raise AssessmentStudioConflictError(str(error)) from error
        except AssessmentStudioRepositoryDataError as error:
            raise AssessmentStudioValidationError(str(error)) from error

    def update_template(self, template_id: str, payload: dict):
        record, topic_ids, patterns = self._validate_payload(payload)
        expected_revision = _positive_int(
            payload.get("revision"), "Template revision"
        )
        try:
            with self._repository(write=True) as repository:
                item = repository.update_template(
                    str(template_id),
                    expected_revision=expected_revision,
                    record=record,
                    topic_ids=topic_ids,
                    patterns=patterns,
                )
            return self._decorate_template(item)
        except AssessmentStudioRepositoryNotFoundError as error:
            raise AssessmentStudioNotFoundError(str(error)) from error
        except AssessmentStudioRepositoryConflictError as error:
            raise AssessmentStudioConflictError(str(error)) from error
        except AssessmentStudioRepositoryDataError as error:
            raise AssessmentStudioValidationError(str(error)) from error

    def set_active(self, template_id: str, *, revision, active: bool):
        expected_revision = _positive_int(revision, "Template revision")
        try:
            with self._repository(write=True) as repository:
                item = repository.set_active(
                    str(template_id),
                    expected_revision=expected_revision,
                    active=bool(active),
                    now=_now(),
                )
            return self._decorate_template(item)
        except AssessmentStudioRepositoryNotFoundError as error:
            raise AssessmentStudioNotFoundError(str(error)) from error
        except AssessmentStudioRepositoryConflictError as error:
            raise AssessmentStudioConflictError(str(error)) from error


def build_assessment_studio_service(database_path=None) -> AssessmentStudioService:
    return AssessmentStudioService(database_path or config.DATABASE_PATH)
