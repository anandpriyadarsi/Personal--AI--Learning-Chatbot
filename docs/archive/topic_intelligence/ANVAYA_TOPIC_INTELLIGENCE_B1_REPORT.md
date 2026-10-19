# ANVAYA B1 source-only implementation report

Base: `710b249d575f18fcd720772b9c7393bdc7ea8f52`; branch `anvaya/topic-intelligence-b1-readonly`.

## Prerequisite and implementation

Gate A hosted [run38129594236](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/38129594236) passed Ubuntu, Windows and aggregate acceptance at the base SHA. Each platform ran1772 full tests and39 browser checks, plus focused54, both fixture orders41, characterization17, Node20 and dependency/migration/diff checks. Production authority remains BLOCKED.

Frozen TopicIdentity, MappingSnapshot, IndependenceSnapshot, EvidenceReference, TopicEvidence and TopicEvidenceBundle records hold observations, not mastery judgments. SQLiteTopicIntelligenceRepository reads only an explicitly supplied closed/checkpointed artifact with canonical course/topic IDs and aware as_of. No default path, snapshot copying, migrations, source initialization, legacy fallback, API/UI consumer, recovery policy or provider call is added.

Signed integer milli-marks, grading confidence and exact source IDs are preserved. Mapping confidence and independence remain unknown. Mutable mappings, package author confidence and exam mode never backfill historical trust. All rows are ineligible for automatic recovery. User-entered evaluations carry a self-reported exclusion; official reports are unchanged. Stored manual status/self-confidence are separate from assessed evidence.

Each evaluation yields one observation; attempt/mistake bridges remain references. Unicode/whitespace-normalized content hashes identify equivalent snapshot content without merging source IDs. Provisional sources and exclusions remain visible. No answer keys, solutions, raw learner responses or local DB path enter DTOs.

Missing session/assessment parents and noninteger score storage reject the artifact with TopicSchemaError. Bridges require exact evaluation/question linkage and existing mistake events owned by the evaluation's attempt. Invalid IDs remain visible with exclusions. Malformed/naive/future/extreme timestamps stay excluded and raw values retained.

Closed-snapshot attestation is required. Query-only immutable reads reject symlink paths and SQLite sidecars and compare stat/digest before and after. These checks do not prove that external writers are absent. Never use this adapter directly on the live database. No migration was allocated;0001–0014 are unchanged.

## Development usage

```python
from datetime import datetime, timezone
from personal_learning_assistant.repositories.sqlite.topic_intelligence_repository import SQLiteTopicIntelligenceRepository

reader = SQLiteTopicIntelligenceRepository(closed_synthetic_snapshot_path, closed_snapshot=True)
bundle = reader.read_topic_bundle(canonical_course_id, canonical_topic_id,
    as_of=datetime(2026, 10, 11, 12, tzinfo=timezone.utc), timezone='Asia/Kolkata')
```

## Review and validation history

Original TDD began with `B1 adapter missing`. Independent review of the initial34 passing tests found four Important issues: orphaned parents silently erased observations, bridge linkage was incomplete, SQLite affinity allowed malformed score types, and timezone conversion overflowed. Eleven new cases failed before repair;45 B1 and65 B1+existing Phase E/F passed afterward. Independent reviewer repeated65 and confirmed no remaining Important/Critical findings.

Two local runs before interruption failed browser setup because the workspace restored Chromium without executable permission: run-v7g0fg07 recorded1767 passed/39 errors; run-_gtr14l9 recorded1778 passed/39 errors. A browser extracted to temporary runtime storage proceeded through the full test sequence, but its final result was not observed before maintenance removed the workspace. None of these runs is counted as acceptance.

On12 October the repository was freshly recovered from GitHub and the reviewed B1 code/tests reconstructed from the conversation. Fresh final validation and recovery review are recorded below before publication. Source-only B1 does not certify fullB, live schema lineage or production rollout.

## Remaining scope

FullB needs immutable attribution/writer authority, canonical application read safety (legacy GET defectC remains), supported source adapters and consumers. C/D/E, Tutor, pause/resume and paper self-evaluation product changes remain unimplemented; the existing complete Assessment design is retained. Production Windows launcher/interpreter/backend/schema/projection parity remains unverified. The next prompt scopes the remaining safe source-only read-safety work.

## Final pre-publication evidence —12 October2026

Fresh local validator `run-ffjibcku` passed all15 categories: full1817 (zero failures/errors/skips), focused54, fixture orders41 each, characterization17, separate browser39, Node20, dependency checks, compile, migration fixture and four diff checks. Source/test bytes match the validated export; later edits only record this evidence. Independent recovery review repeated65 focused tests and found no Important/Critical issues. Hosted B1 acceptance remains pending publication and is recorded in the final evidence handoff.
