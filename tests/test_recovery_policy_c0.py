"""Gate C0 pure rehearsal, no learner records or application side effects."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import pytest

from personal_learning_assistant.domain.topic_intelligence import TopicEvidence, TopicIdentity, MappingSnapshot, IndependenceSnapshot
from personal_learning_assistant.domain.b3_attribution import (
    AssistanceExposure, AttributedEvidence, B3AttributionBundle, IndependenceAttribution, IndependenceState,
    MappingAttribution, MappingState, ObservationIdentity, ReviewAuthority, ReviewerRole,
)
from personal_learning_assistant.domain.recovery_policy_c0 import RecoveryPolicyV1, simulate_recovery

NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)
TOPIC = TopicIdentity('MA103N', 'MA103N', 'Linear Algebra', 'rank', 'Rank', 'mastered', 5)
REVIEW = ReviewAuthority('review', 'teacher', ReviewerRole.TEACHER, NOW - timedelta(days=1), 'fixture-v1')


def entry(i, days_ago=1, score=.5, session=None, group=None, origin='synthetic_reviewed_fixture',
          mapping_conf=.95, grading_conf=.95, exposure=AssistanceExposure.NONE_KNOWN,
          mode='exam', outcome='incorrect'):
    now = NOW - timedelta(days=days_ago)
    marks = round(score*1000)
    e = TopicEvidence(
        evidence_id=f'e{i}', session_evaluation_id=f'se{i}', session_question_id=f'sq{i}',
        response_id=f'r{i}', question_id=f'q{i}', question_identity=group or f'g{i}',
        session_id=session or f's{i%3}', assessment_id=f'a{i}', course_id='MA103N', topic_id='rank',
        ordinal=i, mode=mode, session_status='submitted', occurred_at_raw=now.isoformat(),
        occurred_at_utc=now, local_date=now.date(), awarded_marks_milli=marks, max_marks_milli=1000,
        outcome=outcome, evaluation_status='auto_confirmed', session_evaluation_status='confirmed',
        evaluator_type='deterministic', grading_confidence=grading_conf, rubric_version='v1',
        difficulty='medium', mapping=MappingSnapshot(), independence=IndependenceSnapshot(),
        mistake_categories=(), source_refs=(), exclusion_reasons=('mapping_snapshot_unknown','independence_unknown'),
    )
    mapping = MappingAttribution(MappingState.REVIEWED, f'map{i}', mapping_conf, 'reviewed-human', False, REVIEW, 'calibration-v1')
    independence = IndependenceAttribution(IndependenceState.DECLARED_INDEPENDENT, f'dec{i}', REVIEW, exposure, ())
    return AttributedEvidence(e, ObservationIdentity.from_evidence(e), mapping, independence, None,
                              origin, NOW, e.exclusion_reasons)


def bundle(*observations):
    return B3AttributionBundle(TOPIC, tuple(observations), NOW, 'Asia/Kolkata', 'a'*64, 'b'*64)


def call(*observations, **kwargs):
    return simulate_recovery(bundle(*observations), as_of=NOW, **kwargs)


def test_no_evidence_and_manual_mastery_never_generates_automatic_action():
    decision = call()
    assert decision.state == 'no_evidence'
    assert decision.cohort_mean is None
    assert not decision.automatic_task_allowed


def test_five_distinct_weak_questions_three_sessions_two_dates_trigger_simulation_only():
    items = [entry(i, days_ago=5-i, session=f's{i%3}') for i in range(5)]
    result = call(*items)
    assert result.state == 'recovery_candidate'
    assert result.poor_distinct_count == 5
    assert result.poor_session_count == 3
    assert result.poor_local_date_count == 5
    assert result.recent_poor_count == 5
    assert result.cohort_mean == .5
    assert not result.automatic_task_allowed
    assert 'simulation_only_not_authorized_to_create_task' in result.reason_codes


def test_four_unique_and_six_identical_retries_are_watch_only():
    rows = [entry(i, days_ago=12-i, group='same' if i < 6 else f'g{i}') for i in range(9)]
    decision = call(*rows)
    assert decision.state == 'watch'
    assert decision.poor_distinct_count == 4  # one repeated group + three new identities
    assert len([x for x in decision.excluded if x[1] == 'duplicate_question_exposure']) == 5
    fewer = call(*[entry(i, days_ago=3, group='same') for i in range(6)])
    assert fewer.poor_distinct_count == 1 and fewer.state == 'watch'


def test_strong_topic_only_successes_is_stable():
    decision = call(*(entry(i,score=.9,days_ago=i+1) for i in range(6)))
    assert decision.state == 'stable' and not decision.poor_ids


def test_historical_unknown_cannot_be_promoted_by_mutable_marks():
    d = call(entry(1,origin='historical_unavailable'))
    assert d.state == 'no_evidence' and d.excluded[0][1] == 'historical_untrusted'


def test_reviewed_mapping_and_grading_boundaries():
    badmap = call(entry(1,mapping_conf=.899))
    assert badmap.state == 'no_evidence' and badmap.excluded[0][1] == 'mapping_not_reliably_reviewed'
    assert call(entry(1,mapping_conf=.90)).state == 'watch'
    badgrade = call(entry(1,grading_conf=.749))
    assert badgrade.excluded[0][1] == 'low_grading_confidence'
    assert call(entry(1,grading_conf=.75)).state == 'watch'


def test_known_assistance_and_unanswered_excluded():
    assert call(entry(1,exposure=AssistanceExposure.HELPER)).state == 'no_evidence'
    assert call(entry(1,outcome='unanswered')).state == 'no_evidence'


def test_60_percent_not_poor_599_percent_poor():
    a = call(entry(1,score=.599))
    assert a.poor_distinct_count == 1
    b = call(entry(1,score=.6))
    assert b.poor_distinct_count == 0


def test_28_day_boundary_inclusive_and_future_rejected():
    in_window = call(entry(1,days_ago=28))
    assert in_window.eligible_first_exposure_count == 1
    out = call(entry(1,days_ago=29))
    assert out.state == 'no_evidence' and out.excluded[0][1] == 'outside_28_day_window'
    future = call(entry(1,days_ago=-1))
    assert future.state == 'no_evidence' and future.excluded[0][1] == 'future_or_after_as_of'


def test_recent_seven_day_boundary_and_no_recent_poor():
    d = call(*(entry(i, days_ago=12-i) for i in range(5)))
    assert d.state == 'watch' and d.recent_poor_count == 0
    boundary = call(*(entry(i, days_ago=(11-i) if i<4 else 7) for i in range(5)))
    assert boundary.recent_poor_count == 1 and boundary.state == 'recovery_candidate'


def test_spaced_new_successes_override_existing_failure():
    negatives = [entry(i, days_ago=13-i, score=.2) for i in range(5)]
    positive = [entry(10,days_ago=4,score=1,session='new1'),
                entry(11,days_ago=3,score=1,session='new1'),
                entry(12,days_ago=2,score=1,session='new2')]
    d = call(*(negatives+positive))
    assert d.state == 'improving' and d.success_override and not d.automatic_task_allowed


def test_repeated_runs_deterministic_even_if_bundle_input_reordered():
    rows = [entry(i,days_ago=5-i) for i in range(5)]
    a=call(*rows)
    b=call(*reversed(rows))
    assert a==b
    assert len(a.fingerprint)==64 and a.fingerprint==b.fingerprint


def test_invalid_clock_timezones_and_config_fail_closed():
    with pytest.raises(ValueError,match='as_of'):
        simulate_recovery(bundle(),as_of=datetime(2026,10,14))
    with pytest.raises(ValueError,match='timezone'):
        call(timezone_name='UTC')
    with pytest.raises(ValueError):
        RecoveryPolicyV1(mapping_min=float('nan'))
    with pytest.raises(ValueError):
        RecoveryPolicyV1(recent_days=30)


def test_user_scored_and_unrecognized_evaluator_fail_closed():
    record = entry(1)
    bad = replace(record, observation=replace(record.observation, evaluator_type='user'))
    assert call(bad).state == 'no_evidence'
    strange = replace(record, observation=replace(record.observation, evaluator_type='unrecognized_provider'))
    assert call(strange).state == 'no_evidence'


def test_versioned_threshold_changes_affect_rehearsal_without_mutation():
    record = entry(1, mapping_conf=.91, grading_conf=.80)
    original = simulate_recovery(bundle(record), as_of=NOW)
    strict = simulate_recovery(bundle(record), as_of=NOW, policy=RecoveryPolicyV1(mapping_min=.95))
    assert original.state == 'watch'
    assert strict.state == 'no_evidence'
    assert original.fingerprint != strict.fingerprint
    assert not original.automatic_task_allowed and not strict.automatic_task_allowed


def test_many_strong_scores_from_one_session_are_limited_not_stable():
    d = call(*(entry(i,days_ago=i+1,score=.9,session='one') for i in range(6)))
    assert d.state == 'limited_evidence' and not d.automatic_task_allowed


def test_supporting_source_cannot_be_treated_as_assessment():
    observed = entry(1)
    altered = replace(observed, observation=replace(observed.observation, source_kind='self_reported_paper'))
    d = call(altered)
    assert d.state == 'no_evidence' and d.excluded[0][1] == 'unsupported_evidence_source'


def test_teacher_confirmed_null_grading_confidence_is_not_averaged_or_invented():
    observed = entry(1)
    teacher = replace(observed, observation=replace(observed.observation, evaluator_type='teacher',
                                                   evaluation_status='confirmed',grading_confidence=None))
    assert call(teacher).state == 'watch'


def test_duplicate_evaluation_identity_with_distinct_questions_is_rejected():
    source = entry(1)
    forged = entry(2)
    altered = replace(forged.observation, evidence_id=source.observation.evidence_id)
    forged = replace(forged, observation=altered, identity=ObservationIdentity.from_evidence(altered))
    with pytest.raises(ValueError, match='duplicate.*evaluation'):
        call(source, forged)


def test_overmaximum_marks_are_not_silently_clamped_into_strong_results():
    source = entry(1, score=1)
    forged = replace(source, observation=replace(source.observation, awarded_marks_milli=2000))
    decision = call(forged)
    assert decision.state == 'no_evidence'
    assert decision.excluded == (('e1', 'invalid_marks'),)


def test_stale_successes_do_not_claim_recent_recovery():
    # Two-spaced sessions after historical poor attempts, but all successes are >7 days old.
    negatives = [entry(i, days_ago=26-i, score=.2) for i in range(5)]
    successes = [entry(10,days_ago=17,score=1,session='new1'),
                 entry(11,days_ago=16,score=1,session='new1'),
                 entry(12,days_ago=15,score=1,session='new2')]
    decision = call(*(negatives + successes))
    assert decision.state != 'improving'
    assert not decision.success_override


def test_extreme_as_of_fails_cleanly_instead_of_underflowing():
    from datetime import timezone
    extreme = datetime.min.replace(tzinfo=timezone.utc)
    scope = replace(bundle(), as_of_utc=extreme)
    with pytest.raises(ValueError, match='window'):
        simulate_recovery(scope, as_of=extreme)
