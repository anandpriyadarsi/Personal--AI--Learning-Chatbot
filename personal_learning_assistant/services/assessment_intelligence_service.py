"""Assessment Studio Phase E: read-only assessment intelligence."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from statistics import median
from urllib.parse import quote

import config
from personal_learning_assistant.repositories.sqlite.assessment_intelligence_repository import (
    AssessmentIntelligenceRepositorySchemaError,
    SQLiteAssessmentIntelligenceRepository,
)


class AssessmentIntelligenceError(RuntimeError):
    pass


class AssessmentIntelligenceNotFoundError(AssessmentIntelligenceError):
    pass


class AssessmentIntelligenceUnavailableError(AssessmentIntelligenceError):
    pass


def _marks_text(value) -> str:
    if value is None:
        return "—"
    number = Decimal(int(value)) / Decimal(1000)
    text = format(number, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _percent(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round((float(numerator) / float(denominator)) * 100.0, 1)


def _clamp_percent(value) -> float:
    if value is None:
        return 0.0
    return round(max(0.0, min(100.0, float(value))), 1)


def _minutes(seconds) -> float:
    return round(int(seconds or 0) / 60.0, 1)


def _safe_list(raw):
    try:
        value = json.loads(str(raw or "[]"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def _evidence_weight(row) -> float:
    value = row.get("confidence")
    if value is None:
        return 1.0
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 1.0
    return max(0.0, min(1.0, result))


def _band(performance_percent: float | None, question_count: int) -> str:
    if question_count <= 0 or performance_percent is None:
        return "no_evidence"
    if question_count < 2:
        return "limited_evidence"
    if performance_percent >= 80:
        return "strong"
    if performance_percent >= 60:
        return "developing"
    return "needs_review"


def _band_label(value: str) -> str:
    return {
        "strong": "Strong observed performance",
        "developing": "Developing observed performance",
        "needs_review": "Needs review from observed evidence",
        "limited_evidence": "Limited evidence",
        "no_evidence": "No confirmed evidence",
    }.get(value, value.replace("_", " ").title())


def _occurred_label(value: str | None) -> str:
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y")
    except ValueError:
        return str(value)


def _empty_stats():
    return {
        "question_count": 0,
        "correct_count": 0,
        "partial_count": 0,
        "incorrect_count": 0,
        "unanswered_count": 0,
        "signed_score_milli": 0,
        "max_marks_milli": 0,
        "weighted_score": 0.0,
        "weighted_max": 0.0,
        "confidence_sum": 0.0,
        "focus_seconds": 0,
        "session_ids": set(),
    }


def _accumulate(stats, row):
    maximum = int(row.get("max_marks_milli") or 0)
    score = int(row.get("awarded_marks_milli") or 0)
    weight = _evidence_weight(row)
    stats["question_count"] += 1
    outcome = str(row.get("outcome") or "")
    if outcome == "correct":
        stats["correct_count"] += 1
    elif outcome == "partially_correct":
        stats["partial_count"] += 1
    elif outcome == "incorrect":
        stats["incorrect_count"] += 1
    elif outcome == "unanswered":
        stats["unanswered_count"] += 1
    stats["signed_score_milli"] += score
    stats["max_marks_milli"] += maximum
    stats["weighted_score"] += score * weight
    stats["weighted_max"] += maximum * weight
    stats["confidence_sum"] += weight
    stats["focus_seconds"] += int(row.get("focus_seconds") or 0)
    if row.get("session_id"):
        stats["session_ids"].add(str(row["session_id"]))


def _finalize_stats(stats):
    attempted = (
        int(stats["correct_count"])
        + int(stats["partial_count"])
        + int(stats["incorrect_count"])
    )
    performance = _percent(
        stats["signed_score_milli"],
        stats["max_marks_milli"],
    )
    weighted_performance = _percent(
        stats["weighted_score"],
        stats["weighted_max"],
    )
    full_accuracy = _percent(stats["correct_count"], attempted)
    available_marks = stats["max_marks_milli"] / 1000.0
    time_per_mark = (
        round(stats["focus_seconds"] / available_marks, 1)
        if available_marks > 0
        else None
    )
    average_question_seconds = (
        round(stats["focus_seconds"] / stats["question_count"], 1)
        if stats["question_count"]
        else None
    )
    average_confidence = (
        round(stats["confidence_sum"] / stats["question_count"], 3)
        if stats["question_count"]
        else None
    )
    band = _band(weighted_performance, int(stats["question_count"]))
    return {
        "question_count": int(stats["question_count"]),
        "correct_count": int(stats["correct_count"]),
        "partial_count": int(stats["partial_count"]),
        "incorrect_count": int(stats["incorrect_count"]),
        "unanswered_count": int(stats["unanswered_count"]),
        "attempted_count": attempted,
        "signed_score_milli": int(stats["signed_score_milli"]),
        "max_marks_milli": int(stats["max_marks_milli"]),
        "signed_score": _marks_text(stats["signed_score_milli"]),
        "max_marks": _marks_text(stats["max_marks_milli"]),
        "performance_percent": performance,
        "weighted_performance_percent": weighted_performance,
        "bar_percent": _clamp_percent(weighted_performance),
        "full_accuracy_percent": full_accuracy,
        "focus_seconds": int(stats["focus_seconds"]),
        "focus_minutes": _minutes(stats["focus_seconds"]),
        "time_per_available_mark_seconds": time_per_mark,
        "average_question_seconds": average_question_seconds,
        "average_confidence": average_confidence,
        "session_count": len(stats["session_ids"]),
        "band": band,
        "band_label": _band_label(band),
    }


def _aggregate(rows, key_fn, label_fn, *, extras_fn=None):
    buckets = {}
    metadata = {}
    for row in rows:
        key = key_fn(row)
        if key not in buckets:
            buckets[key] = _empty_stats()
            metadata[key] = {
                "key": key,
                "label": label_fn(row),
            }
            if extras_fn is not None:
                metadata[key].update(extras_fn(row))
        _accumulate(buckets[key], row)
    result = []
    for key, stats in buckets.items():
        item = dict(metadata[key])
        item.update(_finalize_stats(stats))
        result.append(item)
    return result


def _sort_dimension(items):
    return tuple(
        sorted(
            items,
            key=lambda item: (
                -int(item.get("question_count") or 0),
                str(item.get("label") or "").casefold(),
            ),
        )
    )


def _mistake_map(mistakes, key_name: str):
    counts = defaultdict(Counter)
    sessions = defaultdict(lambda: defaultdict(set))
    for item in mistakes:
        key = str(item.get(key_name) or "")
        if not key:
            continue
        category = str(item.get("category") or "other")
        counts[key][category] += 1
        sessions[key][category].add(str(item.get("session_id") or ""))
    return counts, sessions


def _decorate_mistake_patterns(mistakes):
    counts = Counter(str(item.get("category") or "other") for item in mistakes)
    session_sets = defaultdict(set)
    for item in mistakes:
        session_sets[str(item.get("category") or "other")].add(
            str(item.get("session_id") or "")
        )
    total = sum(counts.values())
    rows = []
    for category, count in counts.items():
        rows.append(
            {
                "category": category,
                "label": category.replace("_", " ").title(),
                "count": count,
                "session_count": len(session_sets[category]),
                "share_percent": _percent(count, total) or 0.0,
                "bar_percent": _clamp_percent(_percent(count, total)),
                "repeated": count >= 2,
            }
        )
    return tuple(
        sorted(
            rows,
            key=lambda item: (-item["count"], item["label"].casefold()),
        )
    )


def _historical_coverage(rows):
    historical = [
        row for row in rows
        if str(row.get("authoring_purpose") or "") == "reproduced_paper"
    ]
    if not historical:
        return {
            "question_count": 0,
            "session_count": 0,
            "topics": (),
            "difficulties": (),
            "note": (
                "No confirmed sessions from packages marked reproduced_paper "
                "are available yet."
            ),
        }
    topic_counts = Counter(
        str(row.get("topic_name") or "Unmapped topic") for row in historical
    )
    difficulty_counts = Counter(
        str(row.get("difficulty") or "Unlabelled") for row in historical
    )
    topic_rows = tuple(
        {
            "label": label,
            "count": count,
            "share_percent": _percent(count, len(historical)) or 0.0,
            "bar_percent": _clamp_percent(_percent(count, len(historical))),
        }
        for label, count in sorted(
            topic_counts.items(),
            key=lambda pair: (-pair[1], pair[0].casefold()),
        )
    )
    difficulty_rows = tuple(
        {
            "label": label.replace("_", " ").title(),
            "count": count,
            "share_percent": _percent(count, len(historical)) or 0.0,
            "bar_percent": _clamp_percent(_percent(count, len(historical))),
        }
        for label, count in sorted(
            difficulty_counts.items(),
            key=lambda pair: (-pair[1], pair[0].casefold()),
        )
    )
    return {
        "question_count": len(historical),
        "session_count": len({str(row["session_id"]) for row in historical}),
        "topics": topic_rows,
        "difficulties": difficulty_rows,
        "note": (
            "Historical coverage only. These counts describe reproduced papers "
            "already attempted; they are not a forecast of future exams."
        ),
    }


class AssessmentIntelligenceService:
    """Build accessible, read-only intelligence from confirmed evaluation evidence."""

    def __init__(self, database_path):
        self.database_path = Path(database_path)

    @contextmanager
    def _repository(self):
        path = self.database_path
        if not path.exists() or not path.is_file() or path.is_symlink():
            raise AssessmentIntelligenceUnavailableError(
                "The authoritative SQLite database is unavailable."
            )
        try:
            uri = "file:{}?mode=ro".format(
                quote(path.resolve().as_posix(), safe="/:")
            )
            connection = sqlite3.connect(uri, uri=True, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            try:
                yield SQLiteAssessmentIntelligenceRepository(connection)
            finally:
                connection.close()
        except AssessmentIntelligenceError:
            raise
        except AssessmentIntelligenceRepositorySchemaError as error:
            raise AssessmentIntelligenceUnavailableError(
                "Assessment Intelligence prerequisites are unavailable."
            ) from error
        except sqlite3.Error as error:
            raise AssessmentIntelligenceUnavailableError(
                "Assessment Intelligence storage is unavailable."
            ) from error

    @staticmethod
    def _overall(rows):
        stats = _empty_stats()
        for row in rows:
            _accumulate(stats, row)
        return _finalize_stats(stats)

    @staticmethod
    def _attach_topic_mistakes(topic_rows, mistakes):
        counts, sessions = _mistake_map(mistakes, "topic_id")
        result = []
        for item in topic_rows:
            row = dict(item)
            key = str(row.get("topic_id") or row.get("key") or "")
            category_counts = counts.get(key, Counter())
            row["mistake_count"] = sum(category_counts.values())
            row["mistake_categories"] = tuple(
                {
                    "category": category,
                    "label": category.replace("_", " ").title(),
                    "count": count,
                    "session_count": len(sessions[key][category]),
                }
                for category, count in sorted(
                    category_counts.items(),
                    key=lambda pair: (-pair[1], pair[0]),
                )
            )
            result.append(row)
        return result

    @staticmethod
    def _recovery_order(topic_rows):
        ordered = sorted(
            topic_rows,
            key=lambda item: (
                (
                    item["weighted_performance_percent"]
                    if item["weighted_performance_percent"] is not None
                    else 999.0
                ),
                -int(item.get("mistake_count") or 0),
                -int(item.get("incorrect_count") or 0),
                -int(item.get("partial_count") or 0),
                -int(item.get("question_count") or 0),
                str(item.get("label") or "").casefold(),
            ),
        )
        result = []
        for index, item in enumerate(ordered, start=1):
            row = dict(item)
            signals = []
            perf = row.get("weighted_performance_percent")
            if perf is not None and perf < 60:
                signals.append("low confirmed marks rate")
            if int(row.get("incorrect_count") or 0) >= 2:
                signals.append("repeated incorrect responses")
            if int(row.get("partial_count") or 0) >= 2:
                signals.append("repeated partial responses")
            if int(row.get("mistake_count") or 0) >= 2:
                signals.append("repeated confirmed mistake classifications")
            if int(row.get("question_count") or 0) < 2:
                signals.append("limited sample size")
            if not signals:
                signals.append("lower relative observed performance")
            row["recovery_order"] = index
            row["recovery_signals"] = tuple(signals)
            result.append(row)
        return tuple(result)

    @staticmethod
    def _session_trend(sessions, evidence):
        grouped = defaultdict(list)
        for row in evidence:
            grouped[str(row["session_id"])].append(row)
        trend = []
        by_id = {str(row["session_id"]): row for row in sessions}
        for session_id, rows in grouped.items():
            header = by_id.get(session_id, {})
            stats = _empty_stats()
            for row in rows:
                _accumulate(stats, row)
            metric = _finalize_stats(stats)
            trend.append(
                {
                    "session_id": session_id,
                    "title": str(header.get("title_snapshot") or rows[0].get("title_snapshot") or ""),
                    "occurred_at": str(rows[0].get("occurred_at") or ""),
                    "occurred_label": _occurred_label(rows[0].get("occurred_at")),
                    "assessment_type": str(header.get("assessment_type") or rows[0].get("assessment_type") or ""),
                    "authoring_purpose": str(header.get("authoring_purpose") or rows[0].get("authoring_purpose") or ""),
                    **metric,
                }
            )
        trend.sort(key=lambda item: (item["occurred_at"], item["session_id"]))
        return tuple(trend)

    @staticmethod
    def _course_cards(courses, evidence, mistakes):
        rows_by_course = defaultdict(list)
        mistakes_by_course = defaultdict(list)
        for row in evidence:
            rows_by_course[str(row["course_id"])].append(row)
        for item in mistakes:
            mistakes_by_course[str(item["course_id"])].append(item)

        result = []
        for course in courses:
            course_id = str(course["id"])
            stats = _empty_stats()
            for row in rows_by_course.get(course_id, ()):
                _accumulate(stats, row)
            metric = _finalize_stats(stats)
            result.append(
                {
                    **dict(course),
                    **metric,
                    "mistake_count": len(mistakes_by_course.get(course_id, ())),
                }
            )
        return tuple(result)

    def overview(self):
        with self._repository() as repository:
            courses = repository.list_courses_with_confirmed_sessions()
            sessions = repository.list_confirmed_sessions(limit=300)
            evidence = repository.list_confirmed_question_evidence()
            mistakes = repository.list_confirmed_mistakes()

        overall = self._overall(evidence)
        topics = _aggregate(
            evidence,
            lambda row: str(row.get("topic_id") or "unmapped"),
            lambda row: str(row.get("topic_name") or "Unmapped topic"),
            extras_fn=lambda row: {
                "topic_id": str(row.get("topic_id") or ""),
                "course_id": str(row.get("course_id") or ""),
                "course_code": str(row.get("course_code") or ""),
                "course_name": str(row.get("course_name") or ""),
            },
        )
        topics = self._attach_topic_mistakes(topics, mistakes)

        return {
            "available": True,
            "overall": overall,
            "confirmed_session_count": len(sessions),
            "course_count": len(courses),
            "courses": self._course_cards(courses, evidence, mistakes),
            "recent_trend": tuple(reversed(self._session_trend(sessions, evidence)[-10:])),
            "recovery_topics": self._recovery_order(topics)[:8],
            "mistake_patterns": _decorate_mistake_patterns(mistakes),
            "historical": _historical_coverage(evidence),
            "has_evidence": bool(evidence),
        }

    def course_report(self, course_id: str):
        with self._repository() as repository:
            course = repository.get_course(str(course_id))
            if course is None:
                raise AssessmentIntelligenceNotFoundError("Course not found.")
            sessions = repository.list_confirmed_sessions(course_id=str(course_id), limit=500)
            evidence = repository.list_confirmed_question_evidence(course_id=str(course_id))
            mistakes = repository.list_confirmed_mistakes(course_id=str(course_id))

        overall = self._overall(evidence)

        topics = _aggregate(
            evidence,
            lambda row: str(row.get("topic_id") or "unmapped"),
            lambda row: str(row.get("topic_name") or "Unmapped topic"),
            extras_fn=lambda row: {
                "topic_id": str(row.get("topic_id") or ""),
                "course_id": str(course["id"]),
            },
        )
        topics = self._attach_topic_mistakes(topics, mistakes)
        topics = tuple(
            sorted(
                topics,
                key=lambda item: (
                    item["weighted_performance_percent"]
                    if item["weighted_performance_percent"] is not None
                    else 999.0,
                    str(item["label"]).casefold(),
                ),
            )
        )

        chapters = _sort_dimension(
            _aggregate(
                evidence,
                lambda row: str(row.get("chapter_label") or "Unlabelled chapter"),
                lambda row: str(row.get("chapter_label") or "Unlabelled chapter"),
            )
        )
        subtopics = _sort_dimension(
            _aggregate(
                evidence,
                lambda row: str(row.get("subtopic_label") or "Unlabelled subtopic"),
                lambda row: str(row.get("subtopic_label") or "Unlabelled subtopic"),
            )
        )
        difficulties = _sort_dimension(
            _aggregate(
                evidence,
                lambda row: str(row.get("difficulty") or "unlabelled"),
                lambda row: str(row.get("difficulty") or "unlabelled").replace("_", " ").title(),
            )
        )
        question_types = _sort_dimension(
            _aggregate(
                evidence,
                lambda row: str(row.get("question_type") or "unknown"),
                lambda row: str(row.get("question_type") or "unknown").replace("_", " ").title(),
            )
        )

        heatmap = _aggregate(
            evidence,
            lambda row: "{}::{}".format(
                str(row.get("chapter_label") or "Unlabelled chapter"),
                str(row.get("topic_id") or row.get("topic_name") or "unmapped"),
            ),
            lambda row: str(row.get("topic_name") or "Unmapped topic"),
            extras_fn=lambda row: {
                "chapter": str(row.get("chapter_label") or "Unlabelled chapter"),
                "topic_id": str(row.get("topic_id") or ""),
            },
        )
        heatmap = tuple(
            sorted(
                heatmap,
                key=lambda item: (
                    str(item["chapter"]).casefold(),
                    str(item["label"]).casefold(),
                ),
            )
        )

        time_values = [
            item["time_per_available_mark_seconds"]
            for item in topics
            if item.get("time_per_available_mark_seconds") is not None
        ]
        median_time_per_mark = round(median(time_values), 1) if time_values else None

        recovery = []
        for item in self._recovery_order(topics):
            row = dict(item)
            value = row.get("time_per_available_mark_seconds")
            row["slower_than_course_median"] = bool(
                median_time_per_mark is not None
                and value is not None
                and value > median_time_per_mark * 1.25
                and row.get("question_count", 0) >= 2
            )
            if row["slower_than_course_median"]:
                row["recovery_signals"] = tuple(row["recovery_signals"]) + (
                    "slower time-per-mark than course median",
                )
            recovery.append(row)

        assessment_type_counts = Counter(
            str(item.get("assessment_type") or "unknown") for item in sessions
        )

        return {
            "available": True,
            "course": dict(course),
            "overall": overall,
            "confirmed_session_count": len(sessions),
            "trend": self._session_trend(sessions, evidence),
            "topics": topics,
            "chapters": chapters,
            "subtopics": subtopics,
            "difficulties": difficulties,
            "question_types": question_types,
            "heatmap": heatmap,
            "mistake_patterns": _decorate_mistake_patterns(mistakes),
            "recovery_topics": tuple(recovery),
            "median_time_per_mark_seconds": median_time_per_mark,
            "historical": _historical_coverage(evidence),
            "assessment_type_counts": tuple(
                {
                    "label": key.replace("_", " ").title(),
                    "count": value,
                }
                for key, value in sorted(
                    assessment_type_counts.items(),
                    key=lambda pair: (-pair[1], pair[0]),
                )
            ),
            "has_evidence": bool(evidence),
        }

    def session_analysis(self, session_id: str):
        with self._repository() as repository:
            header = repository.get_session_header(str(session_id))
            if header is None:
                raise AssessmentIntelligenceNotFoundError("Test session not found.")
            if not header.get("session_evaluation_id"):
                raise AssessmentIntelligenceNotFoundError(
                    "Evaluate this session before opening Assessment Intelligence."
                )
            rows = repository.list_session_question_evidence(str(session_id))
            mistakes = tuple(
                item for item in repository.list_confirmed_mistakes(
                    course_id=str(header["course_id"])
                )
                if str(item.get("session_id")) == str(session_id)
            )

        confirmed = [
            row for row in rows
            if str(row.get("evaluation_status")) in {"auto_confirmed", "confirmed"}
            and row.get("awarded_marks_milli") is not None
        ]
        provisional_count = sum(
            1 for row in rows if str(row.get("evaluation_status")) == "provisional"
        )
        awaiting_count = sum(
            1 for row in rows if str(row.get("evaluation_status")) == "awaiting_review"
        )

        topics = _aggregate(
            confirmed,
            lambda row: str(row.get("topic_id") or "unmapped"),
            lambda row: str(row.get("topic_name") or "Unmapped topic"),
            extras_fn=lambda row: {"topic_id": str(row.get("topic_id") or "")},
        )
        topics = self._attach_topic_mistakes(topics, mistakes)

        chapters = _sort_dimension(
            _aggregate(
                confirmed,
                lambda row: str(row.get("chapter_label") or "Unlabelled chapter"),
                lambda row: str(row.get("chapter_label") or "Unlabelled chapter"),
            )
        )
        difficulties = _sort_dimension(
            _aggregate(
                confirmed,
                lambda row: str(row.get("difficulty") or "unlabelled"),
                lambda row: str(row.get("difficulty") or "unlabelled").replace("_", " ").title(),
            )
        )
        question_types = _sort_dimension(
            _aggregate(
                confirmed,
                lambda row: str(row.get("question_type") or "unknown"),
                lambda row: str(row.get("question_type") or "unknown").replace("_", " ").title(),
            )
        )

        questions = []
        for row in rows:
            item = dict(row)
            item["score"] = _marks_text(item.get("awarded_marks_milli"))
            item["max_marks"] = _marks_text(item.get("max_marks_milli"))
            item["focus_minutes"] = _minutes(item.get("focus_seconds"))
            item["performance_percent"] = (
                _percent(item["awarded_marks_milli"], item["max_marks_milli"])
                if item.get("awarded_marks_milli") is not None
                else None
            )
            item["bar_percent"] = _clamp_percent(item["performance_percent"])
            item["outcome_label"] = str(item.get("outcome") or "pending_review").replace("_", " ").title()
            item["evaluation_status_label"] = str(item.get("evaluation_status") or "not_evaluated").replace("_", " ").title()
            questions.append(item)

        result = {
            "available": True,
            "session": dict(header),
            "is_final": str(header.get("evaluation_status")) == "confirmed",
            "overall": self._overall(confirmed),
            "confirmed_question_count": len(confirmed),
            "provisional_count": provisional_count,
            "awaiting_review_count": awaiting_count,
            "questions": tuple(questions),
            "topics": tuple(topics),
            "chapters": chapters,
            "difficulties": difficulties,
            "question_types": question_types,
            "mistake_patterns": _decorate_mistake_patterns(mistakes),
        }
        return result

    def weak_topics(self):
        with self._repository() as repository:
            evidence = repository.list_confirmed_question_evidence()
            mistakes = repository.list_confirmed_mistakes()

        topics = _aggregate(
            evidence,
            lambda row: "{}::{}".format(
                str(row.get("course_id") or ""),
                str(row.get("topic_id") or "unmapped"),
            ),
            lambda row: str(row.get("topic_name") or "Unmapped topic"),
            extras_fn=lambda row: {
                "topic_id": str(row.get("topic_id") or ""),
                "course_id": str(row.get("course_id") or ""),
                "course_code": str(row.get("course_code") or ""),
                "course_name": str(row.get("course_name") or ""),
            },
        )

        mistake_counts = defaultdict(Counter)
        mistake_sessions = defaultdict(set)
        for item in mistakes:
            key = "{}::{}".format(
                str(item.get("course_id") or ""),
                str(item.get("topic_id") or "unmapped"),
            )
            category = str(item.get("category") or "other")
            mistake_counts[key][category] += 1
            mistake_sessions[key].add(str(item.get("session_id") or ""))

        decorated = []
        for item in topics:
            row = dict(item)
            key = str(row["key"])
            row["mistake_count"] = sum(mistake_counts[key].values())
            row["mistake_session_count"] = len(mistake_sessions[key])
            row["mistake_categories"] = tuple(
                {
                    "category": category,
                    "label": category.replace("_", " ").title(),
                    "count": count,
                }
                for category, count in sorted(
                    mistake_counts[key].items(),
                    key=lambda pair: (-pair[1], pair[0]),
                )
            )
            decorated.append(row)

        return {
            "available": True,
            "topics": self._recovery_order(decorated),
            "has_evidence": bool(evidence),
            "note": (
                "This order uses confirmed assessment evidence only. It is not a "
                "mastery score and does not change your planner."
            ),
        }


def build_assessment_intelligence_service(database_path=None):
    return AssessmentIntelligenceService(database_path or config.DATABASE_PATH)
