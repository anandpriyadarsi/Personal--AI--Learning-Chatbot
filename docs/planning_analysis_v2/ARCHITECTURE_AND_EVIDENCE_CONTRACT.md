# Architecture and evidence contract

Policy `planning-analysis-read-v2.1`. AcademicOverviewService.overview(course='', days=28, evidence='all') composes only existing facts. It has an aware injected UTC clock and configured local timezone (default Asia/Kolkata). Filters are validated: course code ≤32 safe characters, days 7/28/90, evidence all/evaluated/self_reported/pending. SQL uses parameters.

The projection returns `available`, `date`, `timezone`, `as_of`, `policy_version`, filters, source_status, limits, courses, assessments, topics, tasks, effort and summary. It creates no persistence store or migration. Bounds are 100 courses, 100 sessions, 100 open tasks and 500 topic responses. Counts describe the bounded sample, with truncation notices. Learning and Notes retain their owner projections, not a second combined score.

| Fact | Meaning / excluded inputs |
|---|---|
| evaluated session | terminal submitted/expired session; confirmed evaluation; every response final from deterministic/teacher evaluator; question count and max-marks denominator match; all response timestamps between session start and as_of |
| self-reported | user evaluator or valid submitted paper self-review; complete dated denominator needed for displayed marks; never official grade or independent mastery |
| pending | no complete final scored result; marks stay unknown |
| independence | always unknown in this projection; evaluated is not proof of unaided work |
| mapping review | never established by a current topic join; deleted/cross-course/missing mappings excluded from canonical topic display |
| topic observation | distinct question IDs and session IDs, first/last observation, latest outcome per question; equivalent questions without IDs cannot be deduplicated |
| recovery candidate | manual-review candidate only; no automatic task, mastery, urgency score or eligibility |
| planned/actual effort | approved/active/closed agenda items in selected local date range; actual NULL is not zero; course attribution requires a linked canonical task |
| task count | open statuses, bounded inbox; date/evidence filters do not pretend to filter task history |

Paper projection uses allowlisted bounded JSON, ≤256 KiB per snapshot/metadata, ≤200 questions, submitted revision as of clock, snapshot identity/provenance hashes, question IDs and denominator checks. Latest draft does not erase a valid earlier submitted revision. Source refs preserve session/review/revision/question identity; no answer key, private path or solution is returned. Canonical source links delegate to the Assessment owner.

## Physical read boundary

The new reader inspects SQLite's header before connecting. WAL mode is refused: even mode=ro/query_only can update SHM. No immutable mode, sidecar copying, checkpoint or journal conversion is used. DELETE-journal synthetic reads preserve complete file inventory and logical contents; existing/missing WAL-sidecar fixtures remain byte-identical because no connection opens. This is a safe unavailable state, not working live-WAL integration. Legacy page components and calendar readers keep their existing read semantics; complete all-route live-WAL/SHM physical invariance is BLOCKED.

## Proposal / approval boundary

GET preview requires explicit dated availability, never invents a day of free time. It signs a bounded preview hash/source fingerprint, date, timezone and window. Save draft requires same-origin protected POST with a 900-second token. Duplicate/stale inputs conflict rather than silently replacing an approved day. Fingerprint covers bounded canonical planner sources and is checked inside BEGIN IMMEDIATE. Approval requires a separate signed same-origin date intent and revalidates current slots, task duration/deadline/preference, current clock and commitments before transactional source comparison.

Availability/timezone are not persisted in the old schema. Approval can validate current slot safety but cannot reconstruct the original approved availability window. Persistent policy/versioned availability needs a separately authorized schema design. This branch applies no real migration.
