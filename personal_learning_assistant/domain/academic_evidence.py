"""Versioned immutable academic facts; never grade/mastery write authority."""
from dataclasses import asdict, dataclass, field
import hashlib
import json

def canonical_topic_reference(course_id, topic_id):
    """Stable tuple encoding; registry names cannot silently remap identity."""
    if course_id is None or topic_id is None:
        return None
    from personal_learning_assistant.learning_studio.validation import identity
    identity(course_id); identity(topic_id)
    encoded = json.dumps([course_id, topic_id], separators=(",", ":")).encode()
    return {"schema": "anvaya.topic-reference.v1", "owner": "academic_registry",
            "course_id": course_id, "topic_id": topic_id,
            "key": "academic-topic:" + hashlib.sha256(encoded).hexdigest()}


@dataclass(frozen=True)
class SourceReference:
    kind: str
    identifier: str
    sha256: str | None = None
    revision: int | None = None
    page: int | None = None
    url: str | None = None

@dataclass(frozen=True)
class AcademicEvidenceRecord:
    kind: str
    identifier: str
    course_id: str | None
    topic_id: str | None
    qualification: str
    source_status: str
    mapping_status: str
    evaluator: str
    outcome: str
    occurred_at: str | None
    source_refs: tuple[SourceReference, ...] = ()
    reasons: tuple[str, ...] = ()
    module_revision: int | None = None
    question_revision: int | None = None
    grading_confidence: float | None = None
    actual_minutes: int | None = None
    question_id: str | None = None
    assistance: str = 'unknown'
    independence: str = field(default='unknown', init=False)
    automatic_eligible: bool = field(default=False, init=False)

@dataclass(frozen=True)
class AcademicEvidenceView:
    as_of: str
    fingerprint: str
    course_id: str | None
    topic_id: str | None
    source_status: str
    mapping_status: str
    records: tuple[AcademicEvidenceRecord, ...]
    explanations: tuple[str, ...]
    module_id: str | None = None
    module_revision: int | None = None
    module_title: str = ''
    historical_revision: bool = False
    manual_task_allowed: bool = False
    source_id: str | None = None
    source_sha256: str | None = None
    schema: str = field(default='anvaya.academic-evidence.v1', init=False)
    policy_version: str = field(default='academic-evidence-v2.3.1', init=False)
    production_authority: str = field(default='blocked', init=False)
    mastery: str = field(default='unknown', init=False)
    automatic_eligible: bool = field(default=False, init=False)

    def to_dict(self):
        return {**asdict(self), "topic_reference": canonical_topic_reference(self.course_id, self.topic_id)}
