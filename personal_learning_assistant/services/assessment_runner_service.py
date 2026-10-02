"""Assessment Studio Phase C timed JEE-style test runner service."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

import config
from personal_learning_assistant.repositories.sqlite.assessment_runner_repository import (
    AssessmentRunnerRepositoryConflictError,
    AssessmentRunnerRepositoryDataError,
    AssessmentRunnerRepositoryNotFoundError,
    AssessmentRunnerRepositorySchemaError,
    SQLiteAssessmentRunnerRepository,
)
from personal_learning_assistant.repositories.sqlite.connection import connect_database


OBJECTIVE_TYPES = {"mcq", "msq"}
VALUE_TYPES = {"numerical", "fill_blank", "true_false"}
SUBJECTIVE_TYPES = {"short_subjective", "long_subjective"}
QUESTION_TYPES = OBJECTIVE_TYPES | VALUE_TYPES | SUBJECTIVE_TYPES

_FILL_BLANK_RE = re.compile(r"_{2,}")
_FILL_LABEL_RE = re.compile(
    r"(?P<label>(?:\[[^\]]+\](?:_[A-Za-z0-9{}-]+)?|[A-Za-zΑ-Ωα-ωμλ][A-Za-z0-9Α-Ωα-ωμλ _\[\]^{}-]{0,44}))\s*=\s*$"
)


def _compact_fill_label(value: str) -> str:
    label = " ".join(str(value or "").split()).strip(" ,;:.")
    label = re.sub(
        r"^(?:and|then|for these values,?|for consistency|"
        r"for the system to be consistent,?)\s+",
        "",
        label,
        flags=re.I,
    )
    if len(label) > 42:
        label = label[-42:].lstrip(" ,;:.")
    return label


def _enter_fill_fields(question_text: str):
    """Infer ordered multi-part fill labels from an explicit student-facing 'enter ...' cue."""
    text = " ".join(str(question_text or "").split())
    matches = list(
        re.finditer(
            r"\benter(?:\s+(?:the\s+)?(?:values?|answers?))?\s*:?\s*"
            r"(?P<labels>[^.?]+?)(?:[.?]|$)",
            text,
            flags=re.I,
        )
    )
    if not matches:
        return ()

    raw = matches[-1].group("labels").strip(" ,;:")
    labels = [
        _compact_fill_label(item)
        for item in re.split(r"\s*(?:,|;|\band\b)\s*", raw, flags=re.I)
        if _compact_fill_label(item)
    ]
    if not labels or len(labels) > 20:
        return ()
    if any(len(label) > 60 for label in labels):
        return ()

    return tuple(
        {
            "index": index,
            "name": f"Blank {index}",
            "label": label,
        }
        for index, label in enumerate(labels, start=1)
    )


def _fill_blank_fields(question_text: str):
    """Infer safe multi-part fill labels without reading answer keys or solutions."""
    text = str(question_text or "")

    entered = _enter_fill_fields(text)
    if entered:
        return entered

    matches = list(_FILL_BLANK_RE.finditer(text))
    if not matches:
        return ()

    fields = []
    for index, match in enumerate(matches, start=1):
        prefix = text[max(0, match.start() - 90):match.start()]
        label_match = _FILL_LABEL_RE.search(prefix)
        label = _compact_fill_label(label_match.group("label")) if label_match else ""

        if not label:
            open_paren = prefix.rfind("(")
            close_paren = prefix.rfind(")")
            if open_paren > close_paren:
                before_tuple = prefix[:open_paren]
                tuple_match = _FILL_LABEL_RE.search(before_tuple)
                base = _compact_fill_label(tuple_match.group("label")) if tuple_match else "Coordinate"
                component = prefix[open_paren + 1:].count(",") + 1
                label = f"{base} component {component}"

        if not label:
            cue = re.split(r"[.;\n]", prefix)[-1]
            cue = re.sub(r"\s+", " ", cue).strip(" ,;:()")
            cue = re.sub(r"^(?:and|then|for these values,?)\s+", "", cue, flags=re.I)
            cue = re.sub(r"\s+(?:is|equals)$", "", cue, flags=re.I)
            if 2 <= len(cue) <= 42 and not cue.endswith(("(", "=", ",")):
                label = cue

        fields.append({
            "index": index,
            "name": f"Blank {index}",
            "label": label or f"Blank {index}",
        })
    return tuple(fields)


def _inline_blank_segments(question_text: str, fields, values):
    """Build safe text/input segments for visible underscore blanks."""
    text = str(question_text or "")
    matches = list(_FILL_BLANK_RE.finditer(text))
    if not matches or len(matches) != len(fields):
        return ()
    segments = []
    cursor = 0
    for index, match in enumerate(matches):
        if match.start() > cursor:
            segments.append({
                "kind": "text",
                "text": text[cursor:match.start()],
            })
        field = fields[index]
        segments.append({
            "kind": "field",
            "index": int(field["index"]),
            "name": str(field["name"]),
            "label": str(field["label"]),
            "value": str(values[index] if index < len(values) else ""),
        })
        cursor = match.end()
    if cursor < len(text):
        segments.append({
            "kind": "text",
            "text": text[cursor:],
        })
    return tuple(segments)


def _split_legacy_fill_value(value: str, count: int):
    """Best-effort split for displaying an older single-string fill response."""
    if count <= 1:
        return (str(value or ""),)
    raw = str(value or "").strip()
    if not raw:
        return tuple("" for _ in range(count))
    simplified = re.sub(r"[\[\](){}]", ",", raw)
    parts = [item.strip() for item in re.split(r"[,;|]", simplified) if item.strip()]
    if len(parts) == count:
        return tuple(parts)
    return tuple([raw] + [""] * (count - 1))

STATE_LABELS = {
    "not_visited": "Not Visited",
    "not_answered": "Not Answered",
    "answered": "Answered",
    "marked_for_review": "Marked for Review",
    "answered_marked_for_review": "Answered + Marked for Review",
}


class AssessmentRunnerError(RuntimeError):
    pass


class AssessmentRunnerValidationError(AssessmentRunnerError):
    pass


class AssessmentRunnerNotFoundError(AssessmentRunnerError):
    pass


class AssessmentRunnerConflictError(AssessmentRunnerError):
    pass


class AssessmentRunnerUnavailableError(AssessmentRunnerError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _marks_text(value):
    if value is None:
        return ""
    number = Decimal(int(value)) / Decimal(1000)
    text = format(number, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _clamp_focus(value) -> int:
    try:
        result = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, min(result, 60))


def _safe_json(value, fallback):
    try:
        parsed = json.loads(str(value or ""))
    except (json.JSONDecodeError, TypeError, ValueError):
        return fallback
    return parsed


class AssessmentRunnerService:
    """Application boundary for test start/resume, response writes, and submission."""

    def __init__(self, database_path, *, now_fn=None):
        self.database_path = Path(database_path)
        self.now_fn = now_fn or _utc_now

    def _now(self) -> datetime:
        value = self.now_fn()
        if not isinstance(value, datetime):
            raise TypeError("now_fn must return datetime")
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @contextmanager
    def _repository(self, *, write: bool):
        path = self.database_path
        if not path.exists() or not path.is_file() or path.is_symlink():
            raise AssessmentRunnerUnavailableError(
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
                yield SQLiteAssessmentRunnerRepository(connection)
            finally:
                connection.close()
        except AssessmentRunnerError:
            raise
        except AssessmentRunnerRepositorySchemaError as error:
            raise AssessmentRunnerUnavailableError(
                "Assessment Runner migration 0011 has not been applied."
            ) from error
        except sqlite3.Error as error:
            raise AssessmentRunnerUnavailableError(
                "Assessment Runner storage is unavailable."
            ) from error

    @staticmethod
    def _map_repository_error(error):
        if isinstance(error, AssessmentRunnerRepositoryNotFoundError):
            raise AssessmentRunnerNotFoundError(str(error)) from error
        if isinstance(error, AssessmentRunnerRepositoryConflictError):
            raise AssessmentRunnerConflictError(str(error)) from error
        if isinstance(error, AssessmentRunnerRepositoryDataError):
            raise AssessmentRunnerValidationError(str(error)) from error
        raise error

    def library(self):
        now = self._now()
        with self._repository(write=False) as repository:
            assessments = repository.list_runnable_assessments()
            sessions = repository.list_sessions(limit=100)

        items = []
        for item in assessments:
            row = dict(item)
            row["max_marks"] = _marks_text(row.get("max_points_milli"))
            row["duration_label"] = "{} min".format(int(row["duration_minutes"]))
            active_id = str(row.get("active_session_id") or "")
            active_expiry = str(row.get("active_expires_at") or "")
            row["can_resume"] = bool(
                active_id and active_expiry and _parse_iso(active_expiry) > now
            )
            row["active_session_id"] = active_id if row["can_resume"] else ""
            items.append(row)

        history = []
        for item in sessions:
            row = dict(item)
            row["max_marks"] = _marks_text(row.get("max_marks_milli"))
            row["duration_minutes"] = int(row["duration_seconds"]) // 60
            row["focus_minutes"] = round(int(row.get("focus_seconds") or 0) / 60, 1)
            history.append(row)

        return {
            "available": True,
            "assessments": tuple(items),
            "sessions": tuple(history),
            "server_now": _iso(now),
        }

    def preflight(self, assessment_id: str):
        now = self._now()
        with self._repository(write=False) as repository:
            item = repository.get_preflight(str(assessment_id))
        if item is None:
            raise AssessmentRunnerNotFoundError(
                "Assessment is not available for the timed runner."
            )
        result = dict(item)
        if int(result.get("question_count") or 0) <= 0:
            raise AssessmentRunnerValidationError(
                "Assessment has no runnable questions."
            )
        result["max_marks"] = _marks_text(result.get("max_points_milli"))
        result["instructions"] = tuple(
            line.strip()
            for line in str(result.get("instructions_text") or "").splitlines()
            if line.strip()
        )
        active_id = str(result.get("active_session_id") or "")
        active_expiry = str(result.get("active_expires_at") or "")
        result["can_resume"] = bool(
            active_id and active_expiry and _parse_iso(active_expiry) > now
        )
        result["active_session_id"] = active_id if result["can_resume"] else ""
        result["marking_groups"] = tuple({
            **group,
            "marks": _marks_text(group["max_marks_milli"]),
            "negative_marks": _marks_text(group["negative_marks_milli"]),
        } for group in result.get("marking_groups", ()))
        return result

    def start(self, assessment_id: str, *, confirmed: bool):
        if not confirmed:
            raise AssessmentRunnerValidationError(
                "Confirm that you have read the test instructions before starting."
            )
        preflight = self.preflight(str(assessment_id))
        now = self._now()
        expires = now + timedelta(minutes=int(preflight["duration_minutes"]))
        try:
            with self._repository(write=True) as repository:
                result = repository.start_or_resume_session(
                    str(assessment_id),
                    session_id=str(uuid.uuid4()),
                    started_at=_iso(now),
                    expires_at=_iso(expires),
                )
            return result
        except (
            AssessmentRunnerRepositoryNotFoundError,
            AssessmentRunnerRepositoryConflictError,
            AssessmentRunnerRepositoryDataError,
        ) as error:
            self._map_repository_error(error)

    def _synchronize(self, session_id: str):
        now = self._now()
        try:
            with self._repository(write=True) as repository:
                header = repository.synchronize_timeout(
                    str(session_id), now=_iso(now)
                )
            if header is None:
                raise AssessmentRunnerNotFoundError("Test session not found.")
            return header, now
        except (
            AssessmentRunnerRepositoryNotFoundError,
            AssessmentRunnerRepositoryConflictError,
            AssessmentRunnerRepositoryDataError,
        ) as error:
            self._map_repository_error(error)

    @staticmethod
    def _remaining_seconds(header, now: datetime) -> int:
        if str(header.get("status")) != "active":
            return 0
        remaining = int((_parse_iso(str(header["expires_at"])) - now).total_seconds())
        return max(0, remaining)

    @staticmethod
    def _decorate_question(item):
        result = dict(item)
        result["options"] = tuple(
            option
            for option in _safe_json(result.pop("options_json", "[]"), [])
            if isinstance(option, dict)
            and set(option).issubset({"id", "text"})
            and "id" in option
            and "text" in option
        )
        result["response"] = _safe_json(result.get("response_json"), {})
        result.pop("response_json", None)
        result["concepts"] = _safe_json(result.get("concepts_json"), [])
        result.pop("concepts_json", None)
        result["marks"] = _marks_text(result.get("max_marks_milli"))
        result["negative_marks"] = _marks_text(result.get("negative_marks_milli"))
        question_type = str(result.get("question_type") or "")
        question_text = str(result.get("question_text") or "")
        if question_type == "fill_blank":
            fields = _fill_blank_fields(question_text)
            if fields:
                stored_parts = result["response"].get("parts")
                if isinstance(stored_parts, list) and len(stored_parts) == len(fields):
                    values = [str(item or "") for item in stored_parts]
                else:
                    values = list(
                        _split_legacy_fill_value(
                            result["response"].get("value", ""), len(fields)
                        )
                    )
                result["fill_fields"] = tuple(
                    {**field, "value": values[index]}
                    for index, field in enumerate(fields)
                )
                result["fill_segments"] = _inline_blank_segments(
                    question_text,
                    result["fill_fields"],
                    values,
                )
            else:
                result["fill_fields"] = ()
                result["fill_segments"] = ()
        elif question_type == "numerical":
            matches = list(_FILL_BLANK_RE.finditer(question_text))
            if len(matches) == 1:
                fields = _fill_blank_fields(question_text)
                if fields:
                    value = str(result["response"].get("value") or "")
                    result["numerical_segments"] = _inline_blank_segments(
                        question_text,
                        fields,
                        [value],
                    )
                else:
                    result["numerical_segments"] = ()
            else:
                result["numerical_segments"] = ()
        state = str(result.get("state") or "not_visited")
        result["state_label"] = STATE_LABELS.get(state, state.replace("_", " ").title())
        result["answered"] = state in {"answered", "answered_marked_for_review"}
        result["marked"] = state in {
            "marked_for_review",
            "answered_marked_for_review",
        }
        return result

    @staticmethod
    def _palette_counts(questions):
        counts = {key: 0 for key in STATE_LABELS}
        for item in questions:
            state = str(item.get("state") or "not_visited")
            counts[state] = counts.get(state, 0) + 1
        return counts

    def runner_view(self, session_id: str, *, ordinal: int | None = None):
        header, now = self._synchronize(str(session_id))
        if str(header["status"]) != "active":
            return self.summary(str(session_id))

        with self._repository(write=False) as repository:
            session = repository.get_public_session(str(session_id))
        if session is None:
            raise AssessmentRunnerNotFoundError("Test session not found.")

        question_count = int(session["question_count"])
        selected_ordinal = int(ordinal or session.get("current_ordinal") or 1)
        if selected_ordinal < 1 or selected_ordinal > question_count:
            raise AssessmentRunnerValidationError("Question number is out of range.")

        selected = next(
            (
                item
                for item in session["questions"]
                if int(item["ordinal"]) == selected_ordinal
            ),
            None,
        )
        if selected is None:
            raise AssessmentRunnerNotFoundError("Session question not found.")

        try:
            with self._repository(write=True) as repository:
                status = repository.mark_visited(
                    str(session_id),
                    str(selected["session_question_id"]),
                    now=_iso(now),
                )
        except (
            AssessmentRunnerRepositoryNotFoundError,
            AssessmentRunnerRepositoryConflictError,
            AssessmentRunnerRepositoryDataError,
        ) as error:
            self._map_repository_error(error)
        if status != "active":
            return self.summary(str(session_id))

        with self._repository(write=False) as repository:
            session = repository.get_public_session(str(session_id))
        questions = tuple(
            self._decorate_question(item) for item in session["questions"]
        )
        active_question = next(
            item for item in questions if int(item["ordinal"]) == selected_ordinal
        )

        return {
            "terminal": False,
            "session": {
                key: value
                for key, value in session.items()
                if key != "questions"
            },
            "question": active_question,
            "questions": questions,
            "palette_counts": self._palette_counts(questions),
            "remaining_seconds": self._remaining_seconds(session, now),
            "server_now": _iso(now),
            "previous_ordinal": selected_ordinal - 1 if selected_ordinal > 1 else None,
            "next_ordinal": (
                selected_ordinal + 1
                if selected_ordinal < question_count
                else None
            ),
        }

    def coding_context(self, session_id: str, session_question_id: str):
        """Side-effect-free helper projection; no visit, heartbeat or expiry write."""
        with self._repository(write=False) as repository:
            context = repository.get_coding_context(session_id, session_question_id)
        if context is None:
            raise AssessmentRunnerNotFoundError("Question does not belong to this test session.")
        if context["status"] != "active" or _parse_iso(context["expires_at"]) <= self._now():
            raise AssessmentRunnerConflictError("This timed attempt has ended.")
        if context["ordinal"] != context["current_ordinal"]:
            raise AssessmentRunnerConflictError("Open the current question before requesting help.")
        return {key: context[key] for key in ("mode", "course_code", "assessment_title", "question_text")}

    def _load_private_question(self, session_id: str, session_question_id: str):
        with self._repository(write=False) as repository:
            question = repository.get_private_question_snapshot(
                str(session_question_id)
            )
        if question is None or str(question["session_id"]) != str(session_id):
            raise AssessmentRunnerNotFoundError(
                "Question does not belong to this test session."
            )
        return question

    @staticmethod
    def _normalize_response(question, payload):
        question_type = str(question["question_type"])
        options = _safe_json(question.get("options_json"), [])
        option_ids = {
            str(item.get("id"))
            for item in options
            if isinstance(item, dict) and item.get("id") is not None
        }

        if question_type == "mcq":
            raw = payload.get("selected_option_ids") or []
            if isinstance(raw, str):
                raw = [raw] if raw else []
            selected = []
            for item in raw:
                value = str(item).strip()
                if value and value not in selected:
                    selected.append(value)
            if len(selected) > 1:
                raise AssessmentRunnerValidationError(
                    "MCQ allows only one selected option."
                )
            if any(item not in option_ids for item in selected):
                raise AssessmentRunnerValidationError(
                    "Selected MCQ option is invalid."
                )
            return {"selected_option_ids": selected}, bool(selected)

        if question_type == "msq":
            raw = payload.get("selected_option_ids") or []
            if isinstance(raw, str):
                raw = [raw] if raw else []
            selected = []
            for item in raw:
                value = str(item).strip()
                if value and value not in selected:
                    selected.append(value)
            if any(item not in option_ids for item in selected):
                raise AssessmentRunnerValidationError(
                    "Selected MSQ option is invalid."
                )
            return {"selected_option_ids": selected}, bool(selected)

        if question_type in VALUE_TYPES:
            value = str(payload.get("value") or "").strip()
            if question_type == "fill_blank":
                raw_parts = payload.get("parts")
                if isinstance(raw_parts, (list, tuple)):
                    parts = [str(item or "").strip() for item in raw_parts]
                    if len(parts) > 20:
                        raise AssessmentRunnerValidationError("Too many fill-up answer parts.")
                    if any(len(item) > 500 for item in parts):
                        raise AssessmentRunnerValidationError("A fill-up answer part is too long.")
                    value = ",".join(parts)
                    return {"value": value, "parts": parts}, bool(parts) and all(parts)
            if len(value) > 2000:
                raise AssessmentRunnerValidationError("Answer is too long.")
            return {"value": value}, bool(value)

        if question_type in SUBJECTIVE_TYPES:
            text = str(payload.get("text") or "")
            if len(text) > 100000:
                raise AssessmentRunnerValidationError(
                    "Subjective response is too long."
                )
            return {"text": text}, bool(text.strip())

        raise AssessmentRunnerValidationError(
            "Question type is not supported by the timed runner."
        )

    def save_response(
        self,
        session_id: str,
        session_question_id: str,
        payload: dict,
        *,
        mark_for_review: bool | None,
        focus_seconds_delta=0,
        event_type="response_saved",
    ):
        question = self._load_private_question(session_id, session_question_id)
        response, answered = self._normalize_response(question, payload)
        now = self._now()
        try:
            with self._repository(write=True) as repository:
                return repository.save_response(
                    str(session_id),
                    str(session_question_id),
                    response_json=json.dumps(
                        response,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    answered=answered,
                    mark_for_review=mark_for_review,
                    focus_seconds_delta=_clamp_focus(focus_seconds_delta),
                    event_type=str(event_type),
                    now=_iso(now),
                )
        except (
            AssessmentRunnerRepositoryNotFoundError,
            AssessmentRunnerRepositoryConflictError,
            AssessmentRunnerRepositoryDataError,
        ) as error:
            self._map_repository_error(error)

    def clear_response(
        self,
        session_id: str,
        session_question_id: str,
        *,
        focus_seconds_delta=0,
    ):
        question = self._load_private_question(session_id, session_question_id)
        question_type = str(question["question_type"])
        empty = (
            {"selected_option_ids": []}
            if question_type in OBJECTIVE_TYPES
            else {"value": ""}
            if question_type in VALUE_TYPES
            else {"text": ""}
        )
        return self.save_response(
            session_id,
            session_question_id,
            empty,
            mark_for_review=False,
            focus_seconds_delta=focus_seconds_delta,
            event_type="response_cleared",
        )

    def heartbeat(
        self,
        session_id: str,
        *,
        session_question_id: str | None,
        focus_seconds_delta=0,
    ):
        now = self._now()
        try:
            with self._repository(write=True) as repository:
                header = repository.add_focus_time(
                    str(session_id),
                    str(session_question_id) if session_question_id else None,
                    focus_seconds_delta=_clamp_focus(focus_seconds_delta),
                    now=_iso(now),
                )
                public_session = repository.get_public_session(str(session_id))
            if header is None:
                raise AssessmentRunnerNotFoundError("Test session not found.")
        except (
            AssessmentRunnerRepositoryNotFoundError,
            AssessmentRunnerRepositoryConflictError,
            AssessmentRunnerRepositoryDataError,
        ) as error:
            self._map_repository_error(error)
        return {
            "status": str(header["status"]),
            "remaining_seconds": self._remaining_seconds(header, now),
            "server_now": _iso(now),
            "palette_counts": self._palette_counts(tuple(
                self._decorate_question(question) for question in public_session["questions"]
            )),
        }

    def submit(self, session_id: str):
        now = self._now()
        try:
            with self._repository(write=True) as repository:
                result = repository.submit_session(
                    str(session_id), now=_iso(now)
                )
            return result
        except (
            AssessmentRunnerRepositoryNotFoundError,
            AssessmentRunnerRepositoryConflictError,
            AssessmentRunnerRepositoryDataError,
        ) as error:
            self._map_repository_error(error)

    def summary(self, session_id: str):
        header, now = self._synchronize(str(session_id))
        with self._repository(write=False) as repository:
            session = repository.get_public_session(str(session_id))
        if session is None:
            raise AssessmentRunnerNotFoundError("Test session not found.")
        questions = tuple(
            self._decorate_question(item) for item in session["questions"]
        )
        counts = self._palette_counts(questions)
        answered = counts["answered"] + counts["answered_marked_for_review"]
        marked = counts["marked_for_review"] + counts["answered_marked_for_review"]
        return {
            "terminal": str(session["status"]) != "active",
            "session": {
                key: value
                for key, value in session.items()
                if key != "questions"
            },
            "questions": questions,
            "palette_counts": counts,
            "answered_count": answered,
            "marked_count": marked,
            "unanswered_count": (
                counts["not_visited"] + counts["not_answered"] + counts["marked_for_review"]
            ),
            "focus_seconds": sum(int(q.get("focus_seconds") or 0) for q in questions),
            "remaining_seconds": self._remaining_seconds(header, now),
            "server_now": _iso(now),
        }


def build_assessment_runner_service(database_path=None) -> AssessmentRunnerService:
    return AssessmentRunnerService(database_path or config.DATABASE_PATH)
