"""Strict B3 provenance contracts composed beside unchanged B1 observations.

Only the explicitly named fixture composition accepts reviewed attribution.
There is no installed/live review adapter, writer or eligibility policy here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
import hashlib
import json
import math
import re

from personal_learning_assistant.domain.topic_intelligence import (
    EvidenceReference, IndependenceSnapshot, MappingSnapshot,
    TopicEvidence, TopicEvidenceBundle, TopicIdentity,
)


class MappingState(StrEnum):
    UNKNOWN = 'unknown'
    UNREVIEWED = 'unreviewed'
    AMBIGUOUS = 'ambiguous'
    REVIEWED = 'reviewed'


class IndependenceState(StrEnum):
    UNKNOWN = 'unknown'
    DECLARED_INDEPENDENT = 'declared_independent'
    ASSISTED = 'assisted'


class AssistanceExposure(StrEnum):
    UNKNOWN = 'unknown'
    NONE_KNOWN = 'none_known'
    HELPER = 'coding_helper'
    EXTERNAL = 'external_assistance'


class ReviewerRole(StrEnum):
    TEACHER = 'teacher'
    HUMAN_REVIEWER = 'human_reviewer'


def _text(value, name):
    if type(value) is not str or not value.strip():
        raise ValueError(name + ' must be an exact nonempty string')


def _confidence(value):
    if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1):
        raise ValueError('confidence must be finite numeric in [0,1] or unknown')


def _utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('An aware provenance datetime is required')
    try:
        return value.astimezone(timezone.utc)
    except (OverflowError, ValueError) as error:
        raise ValueError('Invalid aware provenance datetime') from error


def _enum(value, enum):
    if type(value) is not enum:
        raise TypeError('Strict ' + enum.__name__ + ' value required')


def _deep_immutable(value):
    if value is None or type(value) in (str,int,bool,date,datetime):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is tuple:
        for item in value:
            _deep_immutable(item)
        return
    if is_dataclass(value) and value.__dataclass_params__.frozen:
        for field in fields(value):
            _deep_immutable(getattr(value,field.name))
        return
    raise TypeError('Deep immutable B1 input required')


def _validate_observation(evidence):
    if type(evidence) is not TopicEvidence or type(evidence.mapping) is not MappingSnapshot or type(evidence.independence) is not IndependenceSnapshot:
        raise TypeError('Strict immutable B1 observation records required')
    _deep_immutable(evidence)
    for ref in (*evidence.source_refs, *evidence.independence.assistance_provenance):
        if type(ref) is not EvidenceReference:
            raise TypeError('Strict immutable B1 references required')
        _text(ref.kind,'reference kind')
        _text(ref.identifier,'reference identity')
    for value in (*evidence.mistake_categories, *evidence.exclusion_reasons):
        _text(value,'reason or category')
    for name in ('ordinal','max_marks_milli'):
        if type(getattr(evidence,name)) is not int:
            raise TypeError('Exact integer observation values required')
    if evidence.awarded_marks_milli is not None and type(evidence.awarded_marks_milli) is not int:
        raise TypeError('Signed integer milli-marks required')
    _confidence(evidence.grading_confidence)
    _confidence(evidence.mapping.confidence)


@dataclass(frozen=True)
class ObservationIdentity:
    course_id: str
    topic_id: str
    evaluation_id: str
    session_evaluation_id: str
    session_id: str
    session_question_id: str
    question_id: str
    response_id: str
    assessment_id: str

    def __post_init__(self):
        for name, value in asdict(self).items():
            _text(value, name)

    @classmethod
    def from_evidence(cls, evidence: TopicEvidence) -> ObservationIdentity:
        if type(evidence) is not TopicEvidence:
            raise TypeError('B1 observation required')
        return cls(evidence.course_id, evidence.topic_id, evidence.evidence_id,
                   evidence.session_evaluation_id, evidence.session_id, evidence.session_question_id,
                   evidence.question_id, evidence.response_id, evidence.assessment_id)


@dataclass(frozen=True)
class ReviewAuthority:
    review_ref: str
    reviewer_ref: str
    role: ReviewerRole
    reviewed_at: datetime
    source_version: str

    def __post_init__(self):
        for name in ('review_ref', 'reviewer_ref', 'source_version'):
            _text(getattr(self, name), name)
        _enum(self.role, ReviewerRole)
        object.__setattr__(self, 'reviewed_at', _utc(self.reviewed_at))


@dataclass(frozen=True)
class MappingAttribution:
    state: MappingState = MappingState.UNKNOWN
    mapping_id: str | None = None
    confidence: float | None = None
    method: str | None = None
    review_required: bool | None = None
    review: ReviewAuthority | None = None
    calibration_ref: str | None = None

    def __post_init__(self):
        _enum(self.state, MappingState)
        _confidence(self.confidence)
        for name in ('mapping_id', 'method', 'calibration_ref'):
            if getattr(self, name) is not None:
                _text(getattr(self, name), name)
        if self.review_required is not None and type(self.review_required) is not bool:
            raise TypeError('review_required must be a boolean or unknown')
        if self.review is not None and type(self.review) is not ReviewAuthority:
            raise TypeError('Immutable review authority required')
        if self.state == MappingState.REVIEWED:
            if any(x is None for x in (self.mapping_id, self.confidence, self.method, self.review, self.calibration_ref)) or self.review_required is not False:
                raise ValueError('Reviewed mapping requires traceable calibrated authority and no pending review')
        elif self.review is not None:
            raise ValueError('Unreviewed mapping cannot carry reviewed authority')


@dataclass(frozen=True)
class IndependenceAttribution:
    status: IndependenceState = IndependenceState.UNKNOWN
    declaration_ref: str | None = None
    review: ReviewAuthority | None = None
    exposure: AssistanceExposure = AssistanceExposure.UNKNOWN
    assistance_refs: tuple[str, ...] = ()

    def __post_init__(self):
        _enum(self.status, IndependenceState)
        _enum(self.exposure, AssistanceExposure)
        if type(self.assistance_refs) is not tuple:
            raise TypeError('Immutable assistance reference tuple required')
        for value in self.assistance_refs:
            _text(value, 'assistance reference')
        if self.declaration_ref is not None:
            _text(self.declaration_ref, 'declaration reference')
        if self.review is not None and type(self.review) is not ReviewAuthority:
            raise TypeError('Immutable review authority required')
        if self.status == IndependenceState.DECLARED_INDEPENDENT and (self.declaration_ref is None or self.review is None):
            raise ValueError('Declared independence requires a scoped reviewed declaration')
        if self.status == IndependenceState.UNKNOWN and (self.declaration_ref is not None or self.review is not None):
            raise ValueError('Unknown independence cannot carry a reviewed declaration')


@dataclass(frozen=True)
class SyntheticReviewedAttribution:
    identity: ObservationIdentity
    artifact_sha256: str
    snapshot_at: datetime
    mapping: MappingAttribution
    independence: IndependenceAttribution
    authoring_confidence: float | None = None

    def __post_init__(self):
        for value, cls in ((self.identity, ObservationIdentity), (self.mapping, MappingAttribution), (self.independence, IndependenceAttribution)):
            if type(value) is not cls:
                raise TypeError('Strict immutable attribution records required')
        if type(self.artifact_sha256) is not str or re.fullmatch('[0-9a-f]{64}', self.artifact_sha256) is None:
            raise ValueError('Exact artifact SHA-256 required')
        object.__setattr__(self, 'snapshot_at', _utc(self.snapshot_at))
        _confidence(self.authoring_confidence)


@dataclass(frozen=True)
class AttributedEvidence:
    observation: TopicEvidence
    identity: ObservationIdentity
    mapping: MappingAttribution
    independence: IndependenceAttribution
    authoring_confidence: float | None
    origin: str
    snapshot_at: datetime | None
    warnings: tuple[str, ...]

    def __post_init__(self):
        _validate_observation(self.observation)
        if type(self.identity) is not ObservationIdentity or self.identity != ObservationIdentity.from_evidence(self.observation):
            raise ValueError('Exact observation identity required')
        if type(self.mapping) is not MappingAttribution or type(self.independence) is not IndependenceAttribution:
            raise TypeError('Strict immutable attribution required')
        if type(self.warnings) is not tuple or any(type(x) is not str for x in self.warnings):
            raise TypeError('Immutable warning tuple required')
        if self.origin not in ('historical_unavailable','synthetic_reviewed_fixture'):
            raise ValueError('Unsupported attribution origin')
        _confidence(self.authoring_confidence)
        if self.snapshot_at is not None:
            object.__setattr__(self,'snapshot_at',_utc(self.snapshot_at))

    @property
    def automatic_eligible(self) -> bool:
        # Gate C is not implemented; synthetic reviews never qualify live work.
        return False


@dataclass(frozen=True)
class B3AttributionBundle:
    evidence: tuple[AttributedEvidence, ...]
    as_of_utc: datetime
    timezone: str
    artifact_sha256: str
    fingerprint: str
    contract_version: str = 'anvaya.b3-attribution.v1'

    def __post_init__(self):
        if type(self.evidence) is not tuple or any(type(e) is not AttributedEvidence for e in self.evidence):
            raise TypeError('Immutable attributed evidence tuple required')
        object.__setattr__(self,'as_of_utc',_utc(self.as_of_utc))
        _text(self.timezone,'timezone')
        for digest in (self.artifact_sha256,self.fingerprint):
            if type(digest) is not str or re.fullmatch('[0-9a-f]{64}',digest) is None:
                raise ValueError('Exact SHA-256 required')


def compose_attribution(bundle: TopicEvidenceBundle) -> B3AttributionBundle:
    """Historical read composition: no current mappings or mode inference."""
    return compose_reviewed_fixture(bundle, reviews=())


def compose_reviewed_fixture(bundle: TopicEvidenceBundle, *, reviews: tuple[SyntheticReviewedAttribution, ...]) -> B3AttributionBundle:
    """Explicit synthetic contract rehearsal; not a production review adapter."""
    if type(bundle) is not TopicEvidenceBundle or type(reviews) is not tuple:
        raise TypeError('Immutable B1 bundle and review tuple required')
    if type(bundle.topic) is not TopicIdentity or type(bundle.evidence) is not tuple:
        raise TypeError('Strict immutable B1 bundle required')
    _deep_immutable(bundle)
    for source in bundle.evidence:
        _validate_observation(source)
    as_of = _utc(bundle.as_of_utc)
    observations = {e.evidence_id: e for e in bundle.evidence}
    if len(observations) != len(bundle.evidence):
        raise ValueError('Duplicate evaluation identity')
    index = {}
    for review in reviews:
        if type(review) is not SyntheticReviewedAttribution:
            raise TypeError('Explicit synthetic reviewed attribution required')
        if review.identity.evaluation_id in index:
            raise ValueError('duplicate review identity')
        source = observations.get(review.identity.evaluation_id)
        if source is None or ObservationIdentity.from_evidence(source) != review.identity or (source.course_id, source.topic_id) != (bundle.topic.course_id, bundle.topic.topic_id):
            raise ValueError('Exact scoped observation identity mismatch')
        if review.artifact_sha256 != bundle.snapshot_sha256:
            raise ValueError('Reviewed artifact does not match source artifact')
        if review.snapshot_at > as_of or any(r is not None and r.reviewed_at > review.snapshot_at for r in (review.mapping.review, review.independence.review)):
            raise ValueError('Review time must precede snapshot and as_of time')
        if {'cross_course_source','inconsistent_source_reference','deleted_source','inconsistent_bridge_reference'} & set(source.exclusion_reasons):
            raise ValueError('Invalid source identity cannot acquire fixture review authority')
        index[source.evidence_id] = review
    result = []
    for source in bundle.evidence:
        review = index.get(source.evidence_id)
        warnings = set(source.exclusion_reasons)
        mapping = review.mapping if review else MappingAttribution()
        independence = review.independence if review else IndependenceAttribution()
        if independence.status == IndependenceState.DECLARED_INDEPENDENT and (independence.exposure in (AssistanceExposure.HELPER, AssistanceExposure.EXTERNAL) or independence.assistance_refs):
            warnings.add('declared_independence_assistance_conflict')
        if independence.exposure == AssistanceExposure.UNKNOWN:
            warnings.add('assistance_exposure_unknown')
        result.append(AttributedEvidence(source, ObservationIdentity.from_evidence(source), mapping, independence,
            review.authoring_confidence if review else None, 'synthetic_reviewed_fixture' if review else 'historical_unavailable',
            review.snapshot_at if review else None, tuple(sorted(warnings))))
    payload = {'evidence': [asdict(x) for x in result], 'as_of': as_of, 'timezone': bundle.timezone, 'contract':'anvaya.b3-attribution.v1'}
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
        default=lambda x: x.isoformat(), allow_nan=False).encode()).hexdigest()
    return B3AttributionBundle(tuple(result), as_of, bundle.timezone, bundle.snapshot_sha256, fingerprint)
