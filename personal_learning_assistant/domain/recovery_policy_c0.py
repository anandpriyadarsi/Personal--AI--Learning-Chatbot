"""Synthetic-only rehearsal of conservative recovery policy v1.

This is NOT the Gate C product service. Only explicitly reviewed B3 synthetic
fixtures are scored; historical/live observations never qualify. No storage,
provider, planner or route uses this module. No decision grants task authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from personal_learning_assistant.domain.b3_attribution import (
    AssistanceExposure, B3AttributionBundle, IndependenceState, MappingState,
)


@dataclass(frozen=True)
class RecoveryPolicyV1:
    window_days: int = 28
    recent_days: int = 7
    min_negative_questions: int = 5
    min_negative_sessions: int = 3
    min_negative_dates: int = 2
    poor_ratio: float = .60
    mapping_min: float = .90
    grading_min: float = .75
    success_ratio: float = .80
    success_questions: int = 3
    success_sessions: int = 2
    success_spacing_hours: int = 24
    version: str = 'anvaya.recovery-c0.synthetic.v1'

    def __post_init__(self):
        for name in ('window_days', 'recent_days', 'min_negative_questions', 'min_negative_sessions',
                     'min_negative_dates', 'success_questions', 'success_sessions', 'success_spacing_hours'):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f'{name} must be a positive integer')
        if self.recent_days > self.window_days:
            raise ValueError('recent_days exceeds window_days')
        for name in ('poor_ratio', 'mapping_min', 'grading_min', 'success_ratio'):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 1:
                raise ValueError(f'{name} must be finite and in (0,1]')
        if type(self.version) is not str or not self.version.strip():
            raise ValueError('Version must be explicit')


@dataclass(frozen=True)
class RecoverySimulation:
    state: str
    eligible_ids: tuple[str, ...]
    poor_ids: tuple[str, ...]
    excluded: tuple[tuple[str, str], ...]
    eligible_first_exposure_count: int
    poor_distinct_count: int
    poor_session_count: int
    poor_local_date_count: int
    cohort_mean: float | None
    recent_poor_count: int
    success_override: bool
    reason_codes: tuple[str, ...]
    fingerprint: str
    source: str = 'synthetic_fixture_only'
    automatic_task_allowed: bool = False


def _datetime(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Aware as_of required')
    try:
        return value.astimezone(timezone.utc)
    except (OverflowError, ValueError) as exc:
        raise ValueError('Invalid as_of') from exc


def _eligibility(entry, *, start, end, policy):
    e, mapping, independence = entry.observation, entry.mapping, entry.independence
    if entry.origin != 'synthetic_reviewed_fixture':
        return 'historical_untrusted'
    forbidden = set(e.exclusion_reasons) - {'mapping_snapshot_unknown', 'independence_unknown'}
    forbidden |= set(entry.warnings) - {'mapping_snapshot_unknown', 'independence_unknown'}
    if forbidden:
        return 'source_excluded'
    if e.source_kind != 'assessment_evaluation':
        return 'unsupported_evidence_source'
    if e.mode != 'exam' or e.session_status not in ('submitted', 'expired'):
        return 'not_terminal_independent_exam'
    if e.session_evaluation_status != 'confirmed' or e.evaluation_status not in ('auto_confirmed', 'confirmed'):
        return 'unconfirmed_grade'
    if e.outcome == 'unanswered' or e.awarded_marks_milli is None:
        return 'unanswered_or_ungraded'
    if type(e.awarded_marks_milli) is not int or type(e.max_marks_milli) is not int or e.max_marks_milli <= 0:
        return 'invalid_marks'
    if e.evaluator_type not in ('deterministic', 'teacher', 'human'):
        return 'not_independently_graded'
    if e.evaluator_type == 'deterministic' and e.evaluation_status != 'auto_confirmed':
        return 'deterministic_grade_not_auto_confirmed'
    if e.grading_confidence is not None and (not math.isfinite(e.grading_confidence) or e.grading_confidence < policy.grading_min):
        return 'low_grading_confidence'
    if e.grading_confidence is None and e.evaluator_type not in ('teacher', 'human'):
        return 'unconfirmed_grading_confidence'
    if mapping.state != MappingState.REVIEWED or mapping.confidence is None or mapping.confidence < policy.mapping_min or mapping.review_required is not False or mapping.review is None:
        return 'mapping_not_reliably_reviewed'
    if independence.status != IndependenceState.DECLARED_INDEPENDENT or independence.review is None or independence.exposure != AssistanceExposure.NONE_KNOWN or independence.assistance_refs:
        return 'independence_unverified_or_assisted'
    if not e.question_identity:
        return 'unknown_question_equivalence'
    if e.occurred_at_utc is None or e.occurred_at_utc.tzinfo is None or e.occurred_at_utc.utcoffset() is None:
        return 'unknown_occurrence_time'
    occurred = e.occurred_at_utc.astimezone(timezone.utc)
    if occurred > end:
        return 'future_or_after_as_of'
    if occurred < start:
        return 'outside_28_day_window'
    return None


def simulate_recovery(bundle: B3AttributionBundle, *, as_of: datetime,
                      timezone_name: str = 'Asia/Kolkata', policy: RecoveryPolicyV1 | None = None) -> RecoverySimulation:
    """Pure rehearsal; never returns an executable recommendation or task."""
    if type(bundle) is not B3AttributionBundle:
        raise TypeError('Strict B3 attribution bundle required')
    policy = policy if policy is not None else RecoveryPolicyV1()
    if type(policy) is not RecoveryPolicyV1:
        raise TypeError('Strict RecoveryPolicyV1 required')
    now = _datetime(as_of)
    if now != bundle.as_of_utc:
        raise ValueError('as_of must match snapshot boundary')
    if type(timezone_name) is not str or timezone_name != bundle.timezone:
        raise ValueError('Explicit snapshot timezone must agree')
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError('Unknown IANA timezone') from exc
    start = now - timedelta(days=policy.window_days)
    recent = now - timedelta(days=policy.recent_days)
    excluded = []
    qualifying = []
    for entry in bundle.evidence:
        e = entry.observation
        reason = _eligibility(entry, start=start, end=now, policy=policy)
        if reason:
            excluded.append((e.evidence_id, reason))
            continue
        # Times are compared on UTC; local dates are recomputed, not trusted from legacy rows.
        occurred = e.occurred_at_utc.astimezone(timezone.utc)
        local_date = occurred.astimezone(zone).date()
        ratio = max(0.0, min(1.0, e.awarded_marks_milli / e.max_marks_milli))
        qualifying.append((occurred, e.session_id, e.ordinal, e.evidence_id, e.question_identity, local_date, ratio))
    qualifying.sort(key=lambda r: (r[0], r[1], r[2], r[3]))
    first = []
    groups = set()
    for row in qualifying:
        if row[4] in groups:
            excluded.append((row[3], 'duplicate_question_exposure'))
        else:
            groups.add(row[4]); first.append(row)
    poor = [r for r in first if r[6] < policy.poor_ratio]
    poor_sessions = {r[1] for r in poor}
    poor_dates = {r[5] for r in poor}
    mean = (sum(r[6] for r in first) / len(first)) if first else None
    recent_poor = sum(r[0] >= recent for r in poor)
    breadth = (len(poor) >= policy.min_negative_questions and len(poor_sessions) >= policy.min_negative_sessions
               and len(poor_dates) >= policy.min_negative_dates)
    trigger = bool(breadth and recent_poor and mean is not None and mean < policy.poor_ratio)
    override = False
    if poor:
        latest_poor = max(r[0] for r in poor)
        success = [r for r in first if r[0] > latest_poor and r[6] >= policy.success_ratio]
        sessions = {}
        for row in success:
            sessions.setdefault(row[1], row[0])
        spaced = (len(sessions) >= policy.success_sessions and
                  (max(sessions.values()) - min(sessions.values())).total_seconds() >= policy.success_spacing_hours * 3600)
        override = len(success) >= policy.success_questions and spaced and (
            sum(r[6] for r in success) / len(success) >= policy.success_ratio)
    reasons = []
    if not first: state, reasons = 'no_evidence', ['no_eligible_independent_evidence']
    elif override: state, reasons = 'improving', ['recent_spaced_success_override']
    elif trigger: state, reasons = 'recovery_candidate', ['synthetic_policy_threshold_met']
    elif poor: state, reasons = 'watch', ['thresholds_not_all_met']
    elif (len(first) < policy.min_negative_questions or
          len({r[1] for r in first}) < policy.min_negative_sessions or
          len({r[5] for r in first}) < policy.min_negative_dates):
        state, reasons = 'limited_evidence', ['insufficient_breadth_for_stability']
    else: state, reasons = 'stable', ['no_qualifying_poor_results']
    if state == 'recovery_candidate':
        reasons.append('simulation_only_not_authorized_to_create_task')
    payload = {'contract':policy.version,'policy':asdict(policy),'as_of':now.isoformat(),'zone':timezone_name,
               'source_fingerprint':bundle.fingerprint,'first':[(r[3],r[4],r[6]) for r in first],
               'excluded':sorted(excluded),'state':state,'override':override}
    fingerprint = sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    return RecoverySimulation(state,tuple(r[3] for r in first),tuple(r[3] for r in poor),tuple(sorted(excluded)),
        len(first),len(poor),len(poor_sessions),len(poor_dates),mean,recent_poor,override,tuple(reasons),fingerprint)
