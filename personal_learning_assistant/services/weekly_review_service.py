"""Weekly evidence review for the Phase 7.5.13 Operational Planner."""

from __future__ import annotations

import uuid
import json
from .weekly_evidence_service import fingerprint
from datetime import datetime, timedelta, timezone

from personal_learning_assistant.repositories.sqlite.weekly_review_repository import (
    SQLiteWeeklyReviewRepository,
    WeeklyReviewRepositoryConflictError,
    WeeklyReviewRepositoryError,
)


class WeeklyReviewError(RuntimeError):
    """Base safe weekly-review error."""


class WeeklyReviewValidationError(WeeklyReviewError):
    """Weekly review input is invalid."""


class WeeklyReviewConflictError(WeeklyReviewError):
    """Weekly review is already closed."""


class WeeklyReviewUnavailableError(WeeklyReviewError):
    """Weekly review storage is unavailable."""


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _date(value):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError) as error:
        raise WeeklyReviewValidationError("Week date must be YYYY-MM-DD.") from error


class WeeklyReviewService:
    def __init__(self, repository, *, now=_now):
        self.repository = repository
        self._now = now

    def period(self, anchor_date):
        anchor = _date(anchor_date)
        start = anchor - timedelta(days=anchor.weekday())
        return start.isoformat(), (start + timedelta(days=6)).isoformat()

    def workspace(self, anchor_date):
        week_start, week_end = self.period(anchor_date)
        try:
            review = self.repository.get_review(week_start, week_end)
            if review and review.get('closed_at'):
                if review.get('evidence_json'):
                    evidence = json.loads(review['evidence_json'])
                else:
                    evidence = {key: review[key] for key in ('planned_items','completed_items','planned_focus_minutes','actual_focus_minutes','carry_forward_count','missed_deadline_count')}
                    evidence.update(legacy_snapshot=True, recorded_items=None)
            else:
                evidence = self.repository.aggregate_period(week_start, week_end, as_of=self._now())
        except WeeklyReviewRepositoryError as error:
            raise WeeklyReviewUnavailableError("Weekly review is temporarily unavailable.") from error
        return {
            "available": True,
            "week_start": week_start,
            "week_end": week_end,
            "evidence": evidence,
            "review": review,
            "evidence_fingerprint": fingerprint(evidence),
        }

    def save(self, anchor_date, payload, *, close=False):
        week_start, week_end = self.period(anchor_date)
        priorities = [
            str(payload.get("next_priority_1") or "").strip(),
            str(payload.get("next_priority_2") or "").strip(),
            str(payload.get("next_priority_3") or "").strip(),
        ]
        if any(len(item) > 500 for item in priorities):
            raise WeeklyReviewValidationError("Weekly priorities are too long.")
        try:
            evidence = self.repository.aggregate_period(week_start, week_end, as_of=self._now())
        except WeeklyReviewRepositoryError as error:
            raise WeeklyReviewUnavailableError("Weekly evidence is unavailable.") from error
        if payload.get('evidence_fingerprint') and payload['evidence_fingerprint'] != fingerprint(evidence):
            raise WeeklyReviewConflictError('Evidence changed. Reload the weekly review before closing.')
        now = self._now()
        row = {
            "id": str(uuid.uuid5(uuid.UUID("d229e1a4-dbc8-5ecf-85ce-f9b0c63c9d24"), week_start)),
            "week_start": week_start,
            "week_end": week_end,
            **evidence,
            "evidence_json": json.dumps(evidence, sort_keys=True),
            "expected_revision": payload.get("expected_revision"),
            "expected_evidence_fingerprint": payload.get("evidence_fingerprint"),
            "evidence_fingerprint": fingerprint(evidence),
            "evidence_as_of": evidence['as_of'],
            "policy_version": evidence['policy_version'],
            "what_worked": str(payload.get("what_worked") or "").strip()[:4000],
            "what_failed": str(payload.get("what_failed") or "").strip()[:4000],
            "remove_next_week": str(payload.get("remove_next_week") or "").strip()[:4000],
            "next_priority_1": priorities[0],
            "next_priority_2": priorities[1],
            "next_priority_3": priorities[2],
            "created_at": now,
            "updated_at": now,
            "closed_at": now if close else None,
        }
        try:
            return self.repository.save_review(row)
        except WeeklyReviewRepositoryConflictError as error:
            raise WeeklyReviewConflictError("Weekly review is already closed.") from error
        except WeeklyReviewRepositoryError as error:
            raise WeeklyReviewUnavailableError("Weekly review could not be saved.") from error


def build_weekly_review_service(database_path="data/learning_assistant.db"):
    return WeeklyReviewService(SQLiteWeeklyReviewRepository(database_path))
