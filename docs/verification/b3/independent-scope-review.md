> TRANSCRIPT RECOVERY, 2026-10-14: Reconstructed from the reviewer's conversation record after workspace maintenance removed the original file. This preserves the earlier review content, not the original file bytes. No tests or code review were rerun during recovery; subsequent closure is recorded separately.

# Independent supplemental B3 scope review

Original review date: 2026-10-14. Tracked base reviewed: `8b4d629` (after `ed2bf73`). Scope was only the uncommitted addition of `TopicIdentity` to `B3AttributionBundle` and its fingerprint, its two new regression tests, plus inspection of the Restricted-policy workflow step. No broad implementation or prior R1–R4 closure review was repeated. No source/test/workflow edits, commits, merges or production operations were performed.

## Original disposition: one Important finding

### S1 — Important: the new exact topic scope is not checked against historical observations

Location at review: `personal_learning_assistant/domain/b3_attribution.py`, `B3AttributionBundle.__post_init__` (lines 259–266) and the initial validation loop in `compose_reviewed_fixture` (lines 285–289).

The new `topic` field was type-checked and deeply immutable, but its IDs were not compared with the bundle observations. Scope consistency was checked only for explicitly supplied synthetic reviews. Consequently ordinary historical composition accepted an otherwise well-typed B1 bundle labelled with a different topic/course and returned that unrelated topic alongside the original observations without a scope-conflict warning. The newly retained topic and fingerprint made this a concrete contradictory-scope output.

Reproduced against a disposable fixture:

```python
from dataclasses import replace
from tests.test_topic_evidence_repository import _database, read
from personal_learning_assistant.domain.b3_attribution import compose_attribution

b = read(_database(tmp_path))
different = replace(b.topic, course_id='other-course', topic_id='other-topic')
r = compose_attribution(replace(b, topic=different))
print(r.topic.course_id, r.topic.topic_id)
print(r.evidence[0].identity.course_id, r.evidence[0].identity.topic_id)
```

Actual original output:

```text
other-course other-topic
course-ma topic-lu
```

The public B3 constructor also accepted `replace(compose_attribution(b), topic=different)`. This used normal dataclass construction, with no mutation bypass. Normal repository-produced bundles avoided the artificial topic swap, but B3 explicitly exposed and validated a reusable composition/DTO boundary, so an unflagged inconsistent input should not be presented as a valid scoped contract.

Repair guidance: require observation topic IDs to match the retained topic, and reject or explicitly disclose unflagged course mismatches at the composition/public bundle boundary. **Preserve B1's intentional cross-course diagnostic behavior:** a repository bundle can legitimately retain a different source course with `cross_course_source` in its exclusion reasons. Do not silently drop those observations, rewrite their identities, or weaken unchanged B1 behavior. Add a mismatched topic test and an unflagged course mismatch test, plus a preservation case for an existing explicitly excluded cross-course observation.

## Confirmed aspects of that delta

- Including the complete immutable `TopicIdentity` in the deterministic payload fixed the collision between two empty topics at the same artifact/as-of/timezone.
- The new field preserved original manual status and self-reported confidence separately from review/grading fields. The two added regressions exercised the intended empty-scope and manual-state behaviors.
- Exact IDs were copied without normalization or name rebinding. No live binding, eligibility policy, migration or writer was added.
- `_deep_immutable` prevented mutable nested topic input; the bundle retained the frozen B1 value.

## Original verification performed

The previous `../.venv/bin/python` was absent after the environment refresh. Used the available primary-runtime Python with `PYTHONDONTWRITEBYTECODE=1`:

```text
python -m pytest -q tests/test_b3_attribution.py tests/test_topic_evidence_repository.py
82 passed in 4.11s
```

The S1 reproduction above ran independently and succeeded in producing the inconsistent result. `git diff --check` passed. At the initial inspection only `domain/b3_attribution.py` and `tests/test_b3_attribution.py` were uncommitted source changes; the implementer continued updating tests and delivery documents during the review.

## Original Restricted-policy workflow inspection

No additional Important/Critical static finding in the inspected step. It launched a child Windows PowerShell process with process-scoped `Restricted`, verified that effective precondition, evaluated the exact checked-out wrapper body as an interactive ScriptBlock, passed the current GitHub SHA as ToolsRef, checked the identity/no-copy/blocked-authority report, compared policy inventories before and after, and wrote a source-labelled acceptance artifact. It changed no persistent policy and left the full validator intact. It remained contingent on actual Windows execution, including module loading under that policy.

The step was after the full validator and subject to its success condition. At the time of this review, supplied run evidence said `38407985532` failed before reaching it (full-suite 1800-second timeout and characterization `read_routes.py` 120-second timeout). Thus **Restricted-policy hosted execution was unverified at that time**, and acceptance of `ed2bf73` was not acceptance of `8b4d629` or the then-uncommitted scope delta. This review did not independently rerun Windows or analyze those unrelated timeout causes.

Recovery note: the parent subsequently reported that the `8b4d629` retry achieved both-platform and aggregate success. This recovered historical report does not independently confirm that newer status or its policy artifact.
