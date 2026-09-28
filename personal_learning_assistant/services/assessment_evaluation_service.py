"""Assessment Studio Phase D evaluation engine."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import quote

import config
from personal_learning_assistant.repositories.sqlite.assessment_evaluation_repository import (
    AssessmentEvaluationRepositoryConflictError,
    AssessmentEvaluationRepositoryDataError,
    AssessmentEvaluationRepositoryNotFoundError,
    AssessmentEvaluationRepositorySchemaError,
    SQLiteAssessmentEvaluationRepository,
)
from personal_learning_assistant.repositories.sqlite.connection import connect_database


ENGINE_VERSION = "assessment-evaluation-v1"

OBJECTIVE_OPTION_TYPES = {"mcq", "msq"}
VALUE_TYPES = {"numerical", "fill_blank", "true_false"}
SUBJECTIVE_TYPES = {"short_subjective", "long_subjective"}
QUESTION_TYPES = OBJECTIVE_OPTION_TYPES | VALUE_TYPES | SUBJECTIVE_TYPES
DETERMINISTIC_POLICIES = {"standard", "all_or_nothing", "partial"}

EVALUATOR_TYPES = {"user", "teacher", "alex_ai"}
MISTAKE_CATEGORIES = {
    "concept_gap",
    "formula_recall",
    "calculation_error",
    "misread",
    "wrong_method",
    "incomplete_reasoning",
    "time_pressure",
    "careless",
    "guessing",
    "other",
}

OUTCOME_LABELS = {
    "correct": "Correct",
    "partially_correct": "Partially Correct",
    "incorrect": "Incorrect",
    "unanswered": "Unanswered",
    "pending_review": "Pending Review",
}
STATUS_LABELS = {
    "auto_confirmed": "Auto-confirmed",
    "awaiting_review": "Awaiting Review",
    "provisional": "Provisional",
    "confirmed": "Confirmed",
}


class AssessmentEvaluationError(RuntimeError):
    pass


class AssessmentEvaluationValidationError(AssessmentEvaluationError):
    pass


class AssessmentEvaluationNotFoundError(AssessmentEvaluationError):
    pass


class AssessmentEvaluationConflictError(AssessmentEvaluationError):
    pass


class AssessmentEvaluationUnavailableError(AssessmentEvaluationError):
    pass


def _split_fill_answer_parts(value: str, expected_count: int):
    """Split a legacy accepted fill-up answer into scalar parts when unambiguous."""
    if expected_count <= 1:
        return [str(value or "").strip()]
    raw = str(value or "").strip()
    if not raw:
        return []

    assignments = re.findall(r"(?:^|[,;])\s*[^=,;]+?=\s*([^,;]+)", raw)
    if len(assignments) == expected_count:
        return [item.strip().strip("()[]{}") for item in assignments]

    simplified = re.sub(r"[\[\](){}]", ",", raw)
    parts = [item.strip() for item in re.split(r"[,;|]", simplified) if item.strip()]
    return parts if len(parts) == expected_count else []


def _fill_parts_match(actual_parts, accepted_answers):
    actual = [_normalize_text(item) for item in actual_parts]
    if not actual or any(not item for item in actual):
        return False, []
    for candidate in accepted_answers:
        expected = _split_fill_answer_parts(candidate, len(actual))
        if expected and actual == [_normalize_text(item) for item in expected]:
            return True, expected
    return False, []


def _now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _safe_object(raw):
    try:
        value = json.loads(str(raw or "{}"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _safe_list(raw):
    try:
        value = json.loads(str(raw or "[]"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def _marks_text(value):
    if value is None:
        return "—"
    number = Decimal(int(value)) / Decimal(1000)
    text = format(number, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _score_to_milli(value, field: str):
    if isinstance(value, bool) or value is None:
        raise AssessmentEvaluationValidationError(
            "{} must be a number.".format(field)
        )
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation as error:
        raise AssessmentEvaluationValidationError(
            "{} must be a number.".format(field)
        ) from error
    if not number.is_finite():
        raise AssessmentEvaluationValidationError(
            "{} must be a finite number.".format(field)
        )
    scaled = number * Decimal(1000)
    if scaled != scaled.to_integral_value():
        raise AssessmentEvaluationValidationError(
            "{} supports at most three decimal places.".format(field)
        )
    return int(scaled)


def _confidence(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        result = float(text)
    except ValueError as error:
        raise AssessmentEvaluationValidationError(
            "Confidence must be between 0 and 1."
        ) from error
    if result < 0.0 or result > 1.0:
        raise AssessmentEvaluationValidationError(
            "Confidence must be between 0 and 1."
        )
    return round(result, 6)


def _rubric_version(rubric_text: str) -> str:
    return hashlib.sha256(str(rubric_text or "").encode("utf-8")).hexdigest()


def _normalize_text(value) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _normalize_true_false(value) -> str:
    text = _normalize_text(value)
    if text in {"true", "t", "yes", "1"}:
        return "true"
    if text in {"false", "f", "no", "0"}:
        return "false"
    return text


def _normalize_number(value):
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    if not number.is_finite():
        return None
    return number.normalize()


def _response_blank(question_type: str, response: dict) -> bool:
    if question_type in OBJECTIVE_OPTION_TYPES:
        return not [
            str(item).strip()
            for item in response.get("selected_option_ids", [])
            if str(item).strip()
        ]
    if question_type in VALUE_TYPES:
        return not str(response.get("value") or "").strip()
    if question_type in SUBJECTIVE_TYPES:
        return not str(response.get("text") or "").strip()
    return True


def _partial_credit(max_marks_milli: int, selected_count: int, correct_count: int) -> int:
    if correct_count <= 0 or selected_count <= 0:
        return 0
    value = (
        Decimal(max_marks_milli)
        * Decimal(selected_count)
        / Decimal(correct_count)
    ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return min(int(max_marks_milli), max(0, int(value)))


def _deterministic_score(question: dict):
    qtype = str(question["question_type"])
    policy = str(question.get("scoring_policy") or "standard")
    maximum = int(question.get("max_marks_milli") or 0)
    negative = int(question.get("negative_marks_milli") or 0)
    response = _safe_object(question.get("response_json"))
    answer = _safe_object(question.get("answer_key_json"))

    if _response_blank(qtype, response):
        return {
            "status": "auto_confirmed",
            "outcome": "unanswered",
            "awarded_marks_milli": 0,
            "penalty_marks_milli": 0,
            "feedback_text": "No answer was recorded.",
            "confidence": 1.0,
            "details": {"reason": "blank_response"},
        }

    if qtype in SUBJECTIVE_TYPES:
        return {
            "status": "awaiting_review",
            "outcome": "pending_review",
            "awarded_marks_milli": None,
            "penalty_marks_milli": 0,
            "feedback_text": "",
            "confidence": None,
            "details": {"reason": "subjective_requires_rubric_review"},
        }

    if qtype in OBJECTIVE_OPTION_TYPES:
        selected = {
            str(item)
            for item in response.get("selected_option_ids", [])
            if str(item)
        }
        correct = {
            str(item)
            for item in answer.get("correct_option_ids", [])
            if str(item)
        }
        if not correct:
            return {
                "status": "awaiting_review",
                "outcome": "pending_review",
                "awarded_marks_milli": None,
                "penalty_marks_milli": 0,
                "feedback_text": "",
                "confidence": None,
                "details": {"reason": "missing_answer_key"},
            }
        if selected == correct:
            return {
                "status": "auto_confirmed",
                "outcome": "correct",
                "awarded_marks_milli": maximum,
                "penalty_marks_milli": 0,
                "feedback_text": "Answer matches the confirmed option key.",
                "confidence": 1.0,
                "details": {
                    "selected_option_ids": sorted(selected),
                    "correct_option_ids": sorted(correct),
                    "exact_match_auto_confirmed": True,
                    "scoring_policy": policy,
                },
            }
        if policy == "custom":
            return {
                "status": "awaiting_review",
                "outcome": "pending_review",
                "awarded_marks_milli": None,
                "penalty_marks_milli": 0,
                "feedback_text": "",
                "confidence": None,
                "details": {
                    "reason": "custom_scoring_requires_manual_review_for_non_exact_response",
                    "selected_option_ids": sorted(selected),
                    "correct_option_ids": sorted(correct),
                },
            }
        if policy not in DETERMINISTIC_POLICIES:
            return {
                "status": "awaiting_review",
                "outcome": "pending_review",
                "awarded_marks_milli": None,
                "penalty_marks_milli": 0,
                "feedback_text": "",
                "confidence": None,
                "details": {
                    "reason": "unsupported_scoring_policy_for_non_exact_response",
                    "selected_option_ids": sorted(selected),
                    "correct_option_ids": sorted(correct),
                },
            }
        wrong_selected = selected - correct
        correct_selected = selected & correct
        if qtype == "msq" and policy == "partial" and not wrong_selected and correct_selected:
            awarded = _partial_credit(
                maximum,
                len(correct_selected),
                len(correct),
            )
            return {
                "status": "auto_confirmed",
                "outcome": "partially_correct",
                "awarded_marks_milli": awarded,
                "penalty_marks_milli": 0,
                "feedback_text": (
                    "Partial credit: only correct options were selected, "
                    "but the full correct set was not selected."
                ),
                "confidence": 1.0,
                "details": {
                    "selected_option_ids": sorted(selected),
                    "correct_option_ids": sorted(correct),
                    "partial_rule": "proportional_correct_subset_no_wrong_options",
                },
            }
        if qtype == "msq" and not wrong_selected and correct_selected:
            outcome = "partially_correct"
            feedback = (
                "The selection contains only correct options but is incomplete; "
                "this scoring policy awards no partial marks."
            )
            awarded = 0
            penalty = 0
        else:
            outcome = "incorrect"
            penalty = negative if selected else 0
            awarded = -penalty
            feedback = (
                "The selected answer does not match the confirmed option key."
            )
        return {
            "status": "auto_confirmed",
            "outcome": outcome,
            "awarded_marks_milli": awarded,
            "penalty_marks_milli": penalty,
            "feedback_text": feedback,
            "confidence": 1.0,
            "details": {
                "selected_option_ids": sorted(selected),
                "correct_option_ids": sorted(correct),
                "wrong_selected_option_ids": sorted(wrong_selected),
            },
        }

    if qtype in VALUE_TYPES:
        actual = str(response.get("value") or "").strip()
        accepted = [
            str(item)
            for item in answer.get("accepted_answers", [])
            if str(item).strip()
        ]
        if not accepted:
            return {
                "status": "awaiting_review",
                "outcome": "pending_review",
                "awarded_marks_milli": None,
                "penalty_marks_milli": 0,
                "feedback_text": "",
                "confidence": None,
                "details": {"reason": "missing_accepted_answers"},
            }

        if qtype == "numerical":
            actual_number = _normalize_number(actual)
            accepted_numbers = [_normalize_number(item) for item in accepted]
            is_correct = (
                actual_number is not None
                and any(
                    value is not None and value == actual_number
                    for value in accepted_numbers
                )
            )
            normalized_actual = str(actual_number) if actual_number is not None else actual
        elif qtype == "true_false":
            normalized_actual = _normalize_true_false(actual)
            is_correct = normalized_actual in {
                _normalize_true_false(item) for item in accepted
            }
        else:
            normalized_actual = _normalize_text(actual)
            response_parts = response.get("parts")
            if qtype == "fill_blank" and isinstance(response_parts, list) and len(response_parts) > 1:
                is_correct, matched_parts = _fill_parts_match(response_parts, accepted)
                normalized_actual = ",".join(_normalize_text(item) for item in response_parts)
            else:
                matched_parts = []
                is_correct = normalized_actual in {
                    _normalize_text(item) for item in accepted
                }

        if is_correct:
            return {
                "status": "auto_confirmed",
                "outcome": "correct",
                "awarded_marks_milli": maximum,
                "penalty_marks_milli": 0,
                "feedback_text": "Answer matches an accepted answer.",
                "confidence": 1.0,
                "details": {
                    "normalized_response": normalized_actual,
                    "exact_match_auto_confirmed": True,
                    "scoring_policy": policy,
                    **({"matched_fill_parts": matched_parts} if qtype == "fill_blank" and matched_parts else {}),
                },
            }
        if policy == "custom":
            return {
                "status": "awaiting_review",
                "outcome": "pending_review",
                "awarded_marks_milli": None,
                "penalty_marks_milli": 0,
                "feedback_text": "",
                "confidence": None,
                "details": {
                    "reason": "custom_scoring_requires_manual_review_for_non_exact_response",
                    "normalized_response": normalized_actual,
                },
            }
        if policy not in DETERMINISTIC_POLICIES:
            return {
                "status": "awaiting_review",
                "outcome": "pending_review",
                "awarded_marks_milli": None,
                "penalty_marks_milli": 0,
                "feedback_text": "",
                "confidence": None,
                "details": {
                    "reason": "unsupported_scoring_policy_for_non_exact_response",
                    "normalized_response": normalized_actual,
                },
            }
        penalty = negative
        return {
            "status": "auto_confirmed",
            "outcome": "incorrect",
            "awarded_marks_milli": -penalty,
            "penalty_marks_milli": penalty,
            "feedback_text": "Answer does not match the accepted answer set.",
            "confidence": 1.0,
            "details": {"normalized_response": normalized_actual},
        }

    return {
        "status": "awaiting_review",
        "outcome": "pending_review",
        "awarded_marks_milli": None,
        "penalty_marks_milli": 0,
        "feedback_text": "",
        "confidence": None,
        "details": {"reason": "unsupported_question_type"},
    }


class AssessmentEvaluationService:
    """Evaluate terminal Phase C test sessions without mutating mastery/plans."""

    def __init__(self, database_path):
        self.database_path = Path(database_path)

    @contextmanager
    def _repository(self, *, write: bool):
        path = self.database_path
        if not path.exists() or not path.is_file() or path.is_symlink():
            raise AssessmentEvaluationUnavailableError(
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
                yield SQLiteAssessmentEvaluationRepository(connection)
            finally:
                connection.close()
        except AssessmentEvaluationError:
            raise
        except AssessmentEvaluationRepositorySchemaError as error:
            raise AssessmentEvaluationUnavailableError(
                "Assessment Evaluation migration 0012 has not been applied."
            ) from error
        except sqlite3.Error as error:
            raise AssessmentEvaluationUnavailableError(
                "Assessment Evaluation storage is unavailable."
            ) from error

    @staticmethod
    def _map_repository_error(error):
        if isinstance(error, AssessmentEvaluationRepositoryNotFoundError):
            raise AssessmentEvaluationNotFoundError(str(error)) from error
        if isinstance(error, AssessmentEvaluationRepositoryConflictError):
            raise AssessmentEvaluationConflictError(str(error)) from error
        if isinstance(error, AssessmentEvaluationRepositoryDataError):
            raise AssessmentEvaluationValidationError(str(error)) from error
        raise error

    def create(self, session_id: str):
        with self._repository(write=False) as repository:
            session = repository.get_terminal_session(str(session_id))
            if session is None:
                raise AssessmentEvaluationNotFoundError("Test session not found.")
            if str(session["status"]) not in {"submitted", "expired"}:
                raise AssessmentEvaluationConflictError(
                    "Submit the test before evaluating it."
                )
            existing = repository.get_session_evaluation_id(str(session_id))
            if existing:
                return existing
            questions = repository.get_private_session_questions(str(session_id))

        if not questions:
            raise AssessmentEvaluationValidationError(
                "The session contains no questions to evaluate."
            )

        session_evaluation_id = str(uuid.uuid4())
        rows = []
        for question in questions:
            score = _deterministic_score(question)
            rows.append(
                {
                    "id": str(uuid.uuid4()),
                    "session_question_id": str(question["session_question_id"]),
                    "question_id": str(question["question_id"]),
                    "response_id": str(question["response_id"]),
                    "evaluator_type": (
                        "deterministic"
                        if score["status"] == "auto_confirmed"
                        else "user"
                    ),
                    "evaluator_model": "",
                    "status": score["status"],
                    "outcome": score["outcome"],
                    "awarded_marks_milli": score["awarded_marks_milli"],
                    "max_marks_milli": int(question["max_marks_milli"]),
                    "penalty_marks_milli": score["penalty_marks_milli"],
                    "scoring_policy": str(question["scoring_policy"]),
                    "rubric_version": _rubric_version(
                        str(question.get("rubric_text") or "")
                    ),
                    "confidence": score["confidence"],
                    "feedback_text": score["feedback_text"],
                    "details_json": json.dumps(
                        score["details"],
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                }
            )
        try:
            with self._repository(write=True) as repository:
                return repository.create_evaluation(
                    session_id=str(session_id),
                    session_evaluation_id=session_evaluation_id,
                    engine_version=ENGINE_VERSION,
                    rows=rows,
                    now=_now(),
                )
        except (
            AssessmentEvaluationRepositoryNotFoundError,
            AssessmentEvaluationRepositoryConflictError,
            AssessmentEvaluationRepositoryDataError,
        ) as error:
            self._map_repository_error(error)

    @staticmethod
    def _decorate_question(item):
        result = dict(item)
        result["response"] = _safe_object(result.get("response_json"))
        result["answer_key"] = _safe_object(result.get("answer_key_json"))
        result["options"] = tuple(
            option
            for option in _safe_list(result.get("options_json"))
            if isinstance(option, dict)
        )
        result["concepts"] = tuple(
            str(value) for value in _safe_list(result.get("concepts_json"))
        )
        result["details"] = _safe_object(result.get("details_json"))
        result["awarded_marks"] = _marks_text(result.get("awarded_marks_milli"))
        result["max_marks"] = _marks_text(result.get("max_marks_milli"))
        result["negative_marks"] = _marks_text(result.get("penalty_marks_milli"))
        result["outcome_label"] = OUTCOME_LABELS.get(
            str(result.get("outcome")),
            str(result.get("outcome") or "").replace("_", " ").title(),
        )
        result["status_label"] = STATUS_LABELS.get(
            str(result.get("status")),
            str(result.get("status") or "").replace("_", " ").title(),
        )
        result["mistakes"] = tuple(dict(x) for x in result.get("mistakes") or ())
        options = {str(option.get("id")): str(option.get("text") or "") for option in result["options"]}
        def option_labels(ids):
            return tuple("{} · {}".format(value, options.get(str(value), "Option unavailable")) for value in ids)
        result["selected_options"] = option_labels(result["response"].get("selected_option_ids", ()))
        result["correct_options"] = option_labels(result["answer_key"].get("correct_option_ids", ()))
        result["can_classify"] = (result.get("status") != "awaiting_review"
            and result.get("awarded_marks_milli") is not None
            and result.get("outcome") in {"incorrect", "partially_correct", "unanswered"})
        return result

    def results(self, session_id: str, *, outcome="", question=""):
        with self._repository(write=False) as repository:
            evaluation = repository.get_evaluation(str(session_id))
        if evaluation is None:
            raise AssessmentEvaluationNotFoundError("Test session not found.")
        if evaluation.get("session_status") not in {"submitted", "expired"}:
            raise AssessmentEvaluationConflictError("Submit the test before viewing results.")
        if not evaluation.get("session_evaluation_id"):
            raise AssessmentEvaluationNotFoundError(
                "This session has not been evaluated yet."
            )
        result = dict(evaluation)
        questions = tuple(
            self._decorate_question(item) for item in result.get("questions") or ()
        )
        result["questions"] = questions

        scored = [
            item for item in questions if item.get("awarded_marks_milli") is not None
        ]
        confirmed = [
            item
            for item in questions
            if item.get("awarded_marks_milli") is not None
            and str(item.get("status")) in {"auto_confirmed", "confirmed"}
        ]
        awaiting = [
            item for item in questions if str(item.get("status")) == "awaiting_review"
        ]
        provisional = [
            item for item in questions if str(item.get("status")) == "provisional"
        ]
        result["scored_so_far_milli"] = sum(
            int(item["awarded_marks_milli"]) for item in scored
        )
        result["confirmed_score_milli"] = sum(
            int(item["awarded_marks_milli"]) for item in confirmed
        )
        result["max_marks_milli"] = sum(
            int(item.get("max_marks_milli") or 0) for item in questions
        )
        result["scored_so_far"] = _marks_text(result["scored_so_far_milli"])
        result["confirmed_score"] = _marks_text(result["confirmed_score_milli"])
        result["max_marks"] = _marks_text(result["max_marks_milli"])
        result["awaiting_review_count"] = len(awaiting)
        result["provisional_count"] = len(provisional)
        result["confirmed_count"] = len(confirmed)
        result["is_final"] = str(result.get("evaluation_status")) == "confirmed"
        result["final_score"] = (
            _marks_text(result["scored_so_far_milli"])
            if result["is_final"]
            else None
        )
        filters = (("", "All"), ("incorrect", "Incorrect"), ("partially_correct", "Partial"),
                   ("unanswered", "Unanswered"), ("needs_grading", "Needs grading"), ("correct", "Correct"))
        outcome = str(outcome) if outcome in dict(filters) else ""
        def matches(item, value):
            if value == "needs_grading":
                return item["status"] in {"awaiting_review", "provisional"}
            return not value or item["outcome"] == value
        result["outcome_filters"] = tuple({"value": value, "label": label,
            "count": sum(matches(item, value) for item in questions)} for value, label in filters)
        result["review_outcome"] = outcome
        visible = tuple(item for item in questions if matches(item, outcome))
        result["review_questions"] = visible
        selected = next((item for item in visible if item["evaluation_id"] == str(question)), visible[0] if visible else None)
        result["selected_question"] = selected
        position = visible.index(selected) if selected else -1
        result["previous_question"] = visible[position - 1] if position > 0 else None
        result["next_question"] = visible[position + 1] if position + 1 < len(visible) else None
        result["next_grading"] = next(iter(awaiting + provisional), None)
        result["negative_marks_total"] = _marks_text(sum(int(item.get("penalty_marks_milli") or 0) for item in scored))
        result["focus_seconds"] = sum(int(item.get("focus_seconds") or 0) for item in questions)
        return result

    def response_editor(self, evaluation_id: str):
        with self._repository(write=False) as repository:
            item = repository.get_response_evaluation(str(evaluation_id))
        if item is None:
            raise AssessmentEvaluationNotFoundError(
                "Response evaluation not found."
            )
        if item.get("session_status") not in {"submitted", "expired"}:
            raise AssessmentEvaluationConflictError("Submit the test before reviewing responses.")
        result = self._decorate_question(item)
        result["session_id"] = str(item["session_id"])
        result["evaluation_id"] = str(item["id"])
        result["evaluator_types"] = ("user", "teacher", "alex_ai")
        result["mistake_categories"] = tuple(sorted(MISTAKE_CATEGORIES))
        return result

    def save_manual_evaluation(self, evaluation_id: str, payload: dict):
        current = self.response_editor(evaluation_id)
        if str(current["status"]) in {"auto_confirmed", "confirmed"}:
            raise AssessmentEvaluationConflictError(
                "This evaluation is already final."
            )

        evaluator_type = str(payload.get("evaluator_type") or "").strip()
        if evaluator_type not in EVALUATOR_TYPES:
            raise AssessmentEvaluationValidationError(
                "Choose User, Teacher or Alex/ChatGPT as evaluator."
            )
        evaluator_model = str(payload.get("evaluator_model") or "").strip()[:120]
        awarded = _score_to_milli(payload.get("awarded_marks"), "Awarded marks")
        maximum = int(current["max_marks_milli"])
        minimum = -int(current.get("negative_marks_milli") or 0)
        if awarded < minimum or awarded > maximum:
            raise AssessmentEvaluationValidationError(
                "Awarded marks must be between {} and {}.".format(
                    _marks_text(minimum),
                    _marks_text(maximum),
                )
            )
        confidence = _confidence(payload.get("confidence"))
        feedback = str(payload.get("feedback_text") or "").strip()
        if len(feedback) > 30000:
            raise AssessmentEvaluationValidationError("Feedback is too long.")

        response = current["response"]
        blank = _response_blank(str(current["question_type"]), response)
        if blank:
            outcome = "unanswered"
        elif awarded == maximum:
            outcome = "correct"
        elif awarded > 0:
            outcome = "partially_correct"
        else:
            outcome = "incorrect"

        confirm_final = bool(payload.get("confirm_final"))
        if evaluator_type == "alex_ai":
            status = "provisional"
        else:
            status = "confirmed" if confirm_final else "provisional"

        details = {
            "manual_review": True,
            "confirm_requested": confirm_final,
            "alex_requires_human_confirmation": evaluator_type == "alex_ai",
        }
        try:
            with self._repository(write=True) as repository:
                return repository.update_manual_evaluation(
                    str(evaluation_id),
                    evaluator_type=evaluator_type,
                    evaluator_model=evaluator_model,
                    status=status,
                    outcome=outcome,
                    awarded_marks_milli=awarded,
                    confidence=confidence,
                    feedback_text=feedback,
                    details_json=json.dumps(
                        details,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    now=_now(),
                )
        except (
            AssessmentEvaluationRepositoryNotFoundError,
            AssessmentEvaluationRepositoryConflictError,
            AssessmentEvaluationRepositoryDataError,
        ) as error:
            self._map_repository_error(error)

    def confirm_provisional(self, evaluation_id: str):
        try:
            with self._repository(write=True) as repository:
                return repository.confirm_provisional_evaluation(
                    str(evaluation_id),
                    now=_now(),
                )
        except (
            AssessmentEvaluationRepositoryNotFoundError,
            AssessmentEvaluationRepositoryConflictError,
            AssessmentEvaluationRepositoryDataError,
        ) as error:
            self._map_repository_error(error)

    def classify_mistake(self, evaluation_id: str, payload: dict):
        current = self.response_editor(evaluation_id)
        if current["status"] == "awaiting_review" or current["awarded_marks_milli"] is None:
            raise AssessmentEvaluationValidationError("Grade the response before classifying a mistake.")
        if str(current["outcome"]) == "correct":
            raise AssessmentEvaluationValidationError(
                "A correct response does not need a mistake classification."
            )
        category = str(payload.get("category") or "").strip()
        if category not in MISTAKE_CATEGORIES:
            raise AssessmentEvaluationValidationError(
                "Choose a valid mistake category."
            )
        note = str(payload.get("note") or "").strip()
        if len(note) > 5000:
            raise AssessmentEvaluationValidationError(
                "Mistake note is too long."
            )
        source_type = str(payload.get("source_type") or "user").strip()
        if source_type not in EVALUATOR_TYPES:
            raise AssessmentEvaluationValidationError(
                "Choose a valid classification source."
            )
        status = "provisional" if source_type == "alex_ai" else "confirmed"
        try:
            with self._repository(write=True) as repository:
                return repository.add_mistake(
                    str(evaluation_id),
                    mistake_id=str(uuid.uuid4()),
                    category=category,
                    note=note,
                    source_type=source_type,
                    status=status,
                    now=_now(),
                )
        except (
            AssessmentEvaluationRepositoryNotFoundError,
            AssessmentEvaluationRepositoryConflictError,
            AssessmentEvaluationRepositoryDataError,
        ) as error:
            self._map_repository_error(error)

    def confirm_mistake(self, mistake_id: str):
        try:
            with self._repository(write=True) as repository:
                return repository.confirm_mistake(
                    str(mistake_id),
                    now=_now(),
                )
        except (
            AssessmentEvaluationRepositoryNotFoundError,
            AssessmentEvaluationRepositoryConflictError,
            AssessmentEvaluationRepositoryDataError,
        ) as error:
            self._map_repository_error(error)


def build_assessment_evaluation_service(database_path=None):
    return AssessmentEvaluationService(database_path or config.DATABASE_PATH)
