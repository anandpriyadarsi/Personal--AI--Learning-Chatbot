# B3 authority and provenance contract

Base: merged main `e15c347e5a7bf58c7ec29708eee49b1fed13f712`. Contract versions: `anvaya.b3-authority.v1`, `anvaya.b3-attribution.v1`. This implements B3-A source-only inspection/composition. B3-B writes/schema and production deployment remain blocked/not authorized.

## Ownership and trust

| Subject | Existing owner | B3 observation |
|---|---|---|
| Canonical course/topic IDs and aliases | courses, topics, topic_aliases | Exact IDs; case-sensitive comparisons and ownership checks; no names as substitutes |
| Current question mapping | question_topic_mappings | Inventory/relationship checks only; mutable score/method/state cannot backfill historical trust |
| Reviewed package staging and source IDs | assessment_import_batches/questions, question_sources | Relationship counts/FK and course consistency; import links are current catalogue metadata, not immutable attempt review |
| Immutable question snapshot and response evaluation | assessment_test_session_questions, assessment_response_evaluations | Reuse B1's exact observation/source IDs, normalized content group, signed milli-marks and grading confidence |
| Attempts and mistakes | question_attempts, mistake_events, assessment_evaluation_mistakes | Bridges, never additional observations; ownership anomalies counted |
| Planning and compatibility stores | planner_tasks/agendas, study_plans/items, app_settings | Read-only inventory, nine projection shape/version observations; no recommendations/tasks generated |
| Backend control | existing .phase4_authority.json | Absent means legacy default with UNVERIFIABLE control lineage; malformed promoted controls are INVALID |

`AuthorityStatus`: PASS, BLOCKED, INVALID, UNVERIFIABLE. PASS applies only to its named check. It never promotes production authority. Ledger equality is separate from required schema/FK verification, integrity/FK violations, normalized identity, projection structure, exact ID parity and freshness.

The inspector requires an explicit query-only connection inside a read transaction, rejects TEMP objects, and qualifies SQL/PRAGMA targets to main. It checks required columns and all51 declared FK ownership/actions for its0001–0014 adapter scope, counts orphaned relationships independently, and returns known aggregate schema/relationship observations. Schema/FK hashes are reproducible observations, not a declaration of complete DDL/index/trigger parity. Unexpected schemas and ledger names are not exported as private text. No migrations execute in this inspector.

## Projection contract

Nine existing compatibility stores are inspected. Known top-level payload versions/shapes have separate status. Missing projection is BLOCKED; corrupt/partial known shape is INVALID; unsupported version is UNVERIFIABLE. Course/topic identity parity compares exact active IDs and explicit exact-key import-ledger links. Conflicting links, duplicate IDs, wrong course ownership or missing canonical IDs cannot pass. No name/code guessing or deterministic-ID generation substitutes for recorded lineage.

Course/topic parity does not establish payload-field parity or freshness. Assessment/workspace/planner projection ID parity is explicitly UNVERIFIABLE in this bounded adapter; key presence/count is never success. Existing app_settings.updated_at may show that a normalized source update is newer, proving a stale projection (INVALID plus projection_stale). Its converse does not prove freshness; naive/missing timestamps remain UNVERIFIABLE. These stores have no verified coupled source watermark. B3 creates none.

Future metadata must identify the exact normalized source/revision or a defined canonical state fingerprint, projection version and transactional commit watermark for every owned projection. Specify field-level parity and deletion/identity coverage before writing it; do not retrofit an invented watermark onto historical records.

## Attribution contract

Frozen strict records: ObservationIdentity (course/topic, evaluation/session evaluation/session/session question/question/response/assessment IDs), ReviewAuthority (review ref, reviewer ref/role, aware reviewed_at, source_version), MappingAttribution (state, mapping ID, confidence, method, review_required, review, calibration ref), IndependenceAttribution (status, declaration, reviewed authority, assistance exposure/refs), SyntheticReviewedAttribution (exact artifact digest and aware snapshot time), AttributedEvidence and B3AttributionBundle.

B3AttributionBundle retains the exact immutable B1 TopicIdentity (including stored manual status and separate student self-confidence) even for zero observations; its deterministic fingerprint includes that scope. Default historical composition retains unknown mapping/independence, the unchanged B1 source/content-equivalence identities and exclusion reasons, and every signed score. Grading confidence, mapping confidence, authoring confidence and topic self-confidence remain separate. No source confidence is averaged or fabricated. Nested mutable B1 input is rejected at the B3 boundary without changing B1. Confidence must be finite numeric0..1 or unknown; booleans are rejected. Review/snapshot/as_of timestamps are aware UTC values with explicit ordering. Exact canonical IDs never undergo Unicode/name normalization; B1's NFC/whitespace content group is a separate concept.

Only `compose_reviewed_fixture` accepts deliberately supplied synthetic reviewed records, pinned to the exact artifact digest and all nine observation IDs. Traceable mapping method/review/calibration and no pending review are required for REVIEWED. Declared independence is a scoped reviewed attestation, not proof of no external assistance. Known helper/assistance conflict remains visible. All B3 observations, including synthetic reviews, have automatic_eligible=False. There is no installed historical review adapter or new-session snapshot writer.

Future Gate C eligibility specification, not implemented here: reviewed reliable mapping>=0.90 with review_required=false and identifiable origin; confirmed deterministic/teacher/human grading with explicitly numeric confidence<0.75 excluded, null human confidence retained; reviewer-confirmed independence with no known assistance conflict; one evaluation per observation with duplicate content/retries accounted for; self-entered subjective marks and assisted practice supporting only. Exam mode or helper-disabled policy never proves unaided work. Existing scoring/reports remain authoritative.

## Conditional B3-B plan

Do not assign a migration number until genuine installed evidence is reviewed: actual launcher/interpreter/checkout, config/backend authority, stable copied schema ledger/checksum/integrity/FKs and normalized constraints, canonical mapping/source/projection lineage and truthful freshness status, existing session-start transactions and rollback, and collision review of current/parallel migration lineages. A synthetic0014 database cannot satisfy this condition.

Then design the smallest prospective additive snapshot/declaration contract. Capture exact mapping reference/state/method/reviewer/time/calibrated confidence/review_required/source version and immutable review link at the real session/question-start transaction. Capture scoped unknown/declared_independent/assisted declaration and known exposure with immutable corrections. Null/unreviewed/ambiguous input remains unknown under existing runner policy. No historical trusted backfill, exam inference, default1.0 confidence or regrading.

Test only disposable fixtures/copies: atomic rollback and interrupted writes, retry/idempotency, unique/link ownership, legacy/promoted compatibility, concurrency, exact case/Unicode IDs, source/version corrections and exact scorer/report parity. Preserve applied SQL checksums. Production migration application, live binding and deployment need later explicit authorization.
