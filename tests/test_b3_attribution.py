"""Reviewed fixture inputs are explicit test authority, never historical backfill."""
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
import importlib
from pathlib import Path

import pytest
from tests.test_topic_evidence_repository import _database, read, update, inventory
from personal_learning_assistant.domain.topic_intelligence import EvidenceReference

ROOT = Path(__file__).resolve().parents[1]
STAMP = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)


def api():
    name = 'personal_learning_assistant.domain.b3_attribution'
    assert (ROOT / (name.replace('.', '/') + '.py')).exists(), 'B3 attribution adapter missing'
    return importlib.import_module(name)


def reviewed(bundle):
    m = api()
    observation = bundle.evidence[0]
    authority = m.ReviewAuthority('review-1', 'reviewer-1', m.ReviewerRole.TEACHER, STAMP, 'fixture-v1')
    mapping = m.MappingAttribution(m.MappingState.REVIEWED, 'mapping-1', 0.95, 'human-exact-id',
                                   False, authority, 'fixture-calibration-v1')
    independence = m.IndependenceAttribution(m.IndependenceState.DECLARED_INDEPENDENT, 'declaration-1',
                       authority, m.AssistanceExposure.NONE_KNOWN, ())
    return m.SyntheticReviewedAttribution(m.ObservationIdentity.from_evidence(observation),
        bundle.snapshot_sha256, STAMP, mapping, independence, 0.6)


def test_historical_composition_preserves_unknowns_scores_and_one_evaluation(tmp_path):
    bundle = read(_database(tmp_path))
    m = api()
    before = inventory(tmp_path)
    result = m.compose_attribution(bundle)
    assert len(result.evidence) == len(bundle.evidence)
    assert tuple(x.observation for x in result.evidence) == bundle.evidence
    assert all(x.mapping.state == 'unknown' and x.independence.status == 'unknown' for x in result.evidence)
    assert all(x.authoring_confidence is None and x.origin == 'historical_unavailable' for x in result.evidence)
    assert all(not x.automatic_eligible for x in result.evidence)
    assert m.compose_attribution(bundle) == result and inventory(tmp_path) == before
    assert result.as_of_utc == bundle.as_of_utc
    assert result.evidence[0].observation.grading_confidence == 1.0


def test_explicit_reviewed_fixture_keeps_each_confidence_separate(tmp_path):
    bundle = read(_database(tmp_path))
    m = api()
    fixture = reviewed(bundle)
    result = m.compose_reviewed_fixture(bundle, reviews=(fixture,))
    first = result.evidence[0]
    assert first.mapping.confidence == 0.95
    assert first.authoring_confidence == 0.6
    assert first.observation.grading_confidence == 1.0
    assert first.independence.status == 'declared_independent'
    assert first.mapping.review.role == m.ReviewerRole.TEACHER
    assert first.origin == 'synthetic_reviewed_fixture'
    assert not first.automatic_eligible
    assert result.evidence[1].mapping.state == 'unknown'
    with pytest.raises(FrozenInstanceError):
        first.mapping.confidence = 1.0


@pytest.mark.parametrize('field', ['course_id','topic_id','evaluation_id','session_id','session_question_id','question_id','response_id','assessment_id','session_evaluation_id'])
def test_review_pins_every_exact_source_identifier(tmp_path, field):
    bundle = read(_database(tmp_path))
    fixture = reviewed(bundle)
    bad = replace(fixture, identity=replace(fixture.identity, **{field:'OTHER'}))
    with pytest.raises(ValueError, match='identity'):
        api().compose_reviewed_fixture(bundle, reviews=(bad,))


def test_artifact_digest_is_pinned_and_current_mutable_mapping_cannot_backfill(tmp_path):
    path = _database(tmp_path)
    original = read(path)
    fixture = reviewed(original)
    update(path, "INSERT INTO question_topic_mappings(id,question_id,topic_id,score,rank,method,state,created_at) VALUES('mutable','q1','topic-lu',1,1,'human','confirmed','2026-10-01')")
    changed = read(path)
    assert api().compose_attribution(changed).evidence == api().compose_attribution(original).evidence
    with pytest.raises(ValueError, match='artifact'):
        api().compose_reviewed_fixture(changed, reviews=(fixture,))


@pytest.mark.parametrize('confidence', [True, -0.01, 1.01, float('nan'), float('inf'), '0.95'])
def test_mapping_confidence_is_finite_numeric_not_boolean(tmp_path, confidence):
    bundle = read(_database(tmp_path))
    fixture = reviewed(bundle)
    with pytest.raises((TypeError, ValueError), match='confidence'):
        replace(fixture.mapping, confidence=confidence)


@pytest.mark.parametrize('field', ['snapshot_at','reviewed_at'])
def test_naive_time_is_not_a_review_authority(tmp_path, field):
    fixture = reviewed(read(_database(tmp_path)))
    with pytest.raises(ValueError, match='aware'):
        if field == 'snapshot_at':
            replace(fixture, snapshot_at=datetime(2026,10,10))
        else:
            replace(fixture.mapping.review, reviewed_at=datetime(2026,10,10))


def test_future_review_and_review_after_snapshot_are_refused(tmp_path):
    bundle = read(_database(tmp_path))
    fixture = reviewed(bundle)
    later = replace(fixture.mapping.review, reviewed_at=datetime(2026,10,12,tzinfo=timezone.utc))
    with pytest.raises(ValueError, match='time'):
        api().compose_reviewed_fixture(bundle, reviews=(replace(fixture, mapping=replace(fixture.mapping, review=later)),))


@pytest.mark.parametrize('field,value', [('review',None), ('mapping_id',None), ('method',None), ('calibration_ref',None), ('review_required',True)])
def test_reviewed_mapping_requires_complete_traceable_review(tmp_path, field, value):
    fixture = reviewed(read(_database(tmp_path)))
    with pytest.raises((TypeError,ValueError)):
        replace(fixture.mapping, **{field:value})


def test_assistance_conflict_is_visible_and_never_treated_as_independent(tmp_path):
    bundle = read(_database(tmp_path))
    fixture = reviewed(bundle)
    m = api()
    known = replace(fixture.independence, exposure=m.AssistanceExposure.HELPER, assistance_refs=('helper-ref',))
    result = m.compose_reviewed_fixture(bundle, reviews=(replace(fixture, independence=known),))
    assert 'declared_independence_assistance_conflict' in result.evidence[0].warnings
    assert not result.evidence[0].automatic_eligible


def test_lists_and_untyped_states_are_not_immutable_typed_provenance(tmp_path):
    bundle = read(_database(tmp_path))
    fixture = reviewed(bundle)
    with pytest.raises(TypeError):
        replace(fixture.independence, assistance_refs=['helper'])
    with pytest.raises(TypeError):
        replace(fixture.mapping, state='reviewed')
    with pytest.raises(TypeError):
        api().compose_reviewed_fixture(bundle, reviews=[])


def test_duplicate_reviews_are_refused_instead_of_silently_overwriting(tmp_path):
    bundle = read(_database(tmp_path))
    fixture = reviewed(bundle)
    with pytest.raises(ValueError, match='duplicate'):
        api().compose_reviewed_fixture(bundle, reviews=(fixture,fixture))


def test_unicode_content_equivalence_retains_distinct_question_source_ids(tmp_path):
    path = _database(tmp_path)
    update(path, "UPDATE assessment_test_session_questions SET question_text=? WHERE id='sq1'", ('Café  rank',))
    update(path, "UPDATE assessment_test_session_questions SET question_text=? WHERE id='sq3'", ('Cafe\u0301\nrank',))
    result = api().compose_attribution(read(path))
    assert result.evidence[0].observation.question_identity == result.evidence[1].observation.question_identity
    assert result.evidence[0].identity.question_id != result.evidence[1].identity.question_id


@pytest.mark.parametrize('field', ['source_refs','mistake_categories','exclusion_reasons'])
def test_mutable_nested_b1_collections_are_rejected_at_b3_boundary(tmp_path, field):
    bundle = read(_database(tmp_path))
    first = bundle.evidence[0]
    mutable = list(getattr(first,field))
    bad = replace(bundle, evidence=(replace(first,**{field:mutable}),)+bundle.evidence[1:])
    with pytest.raises(TypeError, match='immutable'):
        api().compose_attribution(bad)


def test_mutable_outer_and_assistance_collections_are_rejected(tmp_path):
    bundle = read(_database(tmp_path))
    with pytest.raises(TypeError, match='immutable'):
        api().compose_attribution(replace(bundle, evidence=list(bundle.evidence)))
    first = bundle.evidence[0]
    bad = replace(first, independence=replace(first.independence, assistance_provenance=[]))
    with pytest.raises(TypeError, match='immutable'):
        api().compose_attribution(replace(bundle, evidence=(bad,)+bundle.evidence[1:]))


def test_mutable_reference_scalar_and_public_output_fields_are_rejected(tmp_path):
    bundle = read(_database(tmp_path))
    first = bundle.evidence[0]
    bad = replace(first, source_refs=(EvidenceReference('source', ['mutable']),))
    with pytest.raises((TypeError,ValueError)):
        api().compose_attribution(replace(bundle,evidence=(bad,)+bundle.evidence[1:]))
    composed = api().compose_attribution(bundle)
    with pytest.raises(TypeError):
        replace(composed, evidence=list(composed.evidence))
    with pytest.raises(TypeError):
        replace(composed.evidence[0], warnings=[])


def test_empty_topics_keep_exact_scope_and_distinct_fingerprints(tmp_path):
    path = _database(tmp_path)
    for identifier in ('empty-a','empty-b'):
        update(path, "INSERT INTO topics(id,course_id,name,normalized_name,status,created_at,updated_at) VALUES(?, 'course-ma',?,?,'not_started',?,?)", (identifier,identifier,identifier,'2026-10-01','2026-10-01'))
    first = api().compose_attribution(read(path,'empty-a'))
    second = api().compose_attribution(read(path,'empty-b'))
    assert first.evidence == second.evidence == ()
    assert first.artifact_sha256 == second.artifact_sha256
    assert first.fingerprint != second.fingerprint
    assert first.topic.topic_id == 'empty-a' and second.topic.topic_id == 'empty-b'
    assert first.topic.course_id == second.topic.course_id == 'course-ma'


def test_stored_manual_status_and_confidence_remain_separate_from_attribution(tmp_path):
    path = _database(tmp_path)
    update(path,"UPDATE topics SET status='mastered',confidence=5 WHERE id='topic-lu'")
    bundle = read(path)
    result = api().compose_attribution(bundle)
    assert result.topic == bundle.topic
    assert result.topic.stored_status == 'mastered' and result.topic.self_reported_confidence == 5
    assert result.evidence[0].mapping.confidence is None
    assert not any(x.automatic_eligible for x in result.evidence)


@pytest.mark.parametrize('field', ['course_id','topic_id'])
def test_composition_refuses_unflagged_observation_scope_mismatch(tmp_path, field):
    bundle = read(_database(tmp_path))
    with pytest.raises(ValueError, match='scope'):
        api().compose_attribution(replace(bundle,topic=replace(bundle.topic,**{field:'other'})))


@pytest.mark.parametrize('field', ['course_id','topic_id'])
def test_public_bundle_refuses_unflagged_observation_scope_mismatch(tmp_path, field):
    composed = api().compose_attribution(read(_database(tmp_path)))
    with pytest.raises(ValueError, match='scope'):
        replace(composed,topic=replace(composed.topic,**{field:'other'}))


def test_flagged_cross_course_observation_is_preserved_without_rebinding(tmp_path):
    path = _database(tmp_path)
    update(path,"INSERT INTO courses(id,code,name,created_at,updated_at) VALUES('other','OTHER','Other',?,?)",('2026-10-01','2026-10-01'))
    update(path,"UPDATE assessments SET course_id='other' WHERE id='a1'")
    bundle = read(path)
    composed = api().compose_attribution(bundle)
    assert composed.topic == bundle.topic and composed.topic.course_id == 'course-ma'
    assert tuple(x.observation for x in composed.evidence) == bundle.evidence
    first = composed.evidence[0]
    assert first.identity.course_id == 'other'
    assert 'cross_course_source' in first.observation.exclusion_reasons
    assert 'cross_course_source' in first.warnings and not first.automatic_eligible
