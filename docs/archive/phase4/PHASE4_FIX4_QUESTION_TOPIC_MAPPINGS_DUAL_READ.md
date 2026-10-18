# Phase 4.4 — Question ↔ Topic Mappings SQLite Dual-Read Foundation

## Starting point

Phase 4.4 starts from `phase4/structured-cutover` at `eb53aee`, after the gate-passing Phase 4.1, 4.2, and 4.3 foundations.

## Authority boundary

Legacy `data/assessment_workspace.json` remains authoritative for question topic decisions and writes. The existing `automatic_topic_mapping.py` and `assessment_question_workspace.py` public behavior is unchanged. Phase 4.4 does not rerun, tune, or replace the heuristic mapper.

SQLite remains observation-only shadow state. The new SQLite repository accepts only an explicit already-open `sqlite3.Connection`, performs no writes, and rejects `save_state()`.

## Architecture

- `LegacyJsonQuestionTopicMappingRepository` is an explicit Phase 4.4 alias over the Phase 4.3 legacy question workspace repository. It returns the exact legacy workspace shape and preserves the existing JSON write authority.
- `SQLiteQuestionTopicMappingRepository` reads `question_topic_mappings`, questions, assessments, topics, and migration ledger evidence from the Phase 3 schema.
- `DualReadQuestionTopicMappingRepository` reads legacy first, independently observes SQLite, records structured parity diagnostics, and returns the legacy result even if SQLite or diagnostic reporting fails.
- `QuestionTopicBackendConfig` supports only `legacy` and `dual_read`. No SQLite-only authority mode exists.

## Stored-decision policy

Phase 4.4 cuts over **stored mapping decisions**, not the mapping algorithm. Legacy fields inspected are:

- `topic`
- `topic_mapping.method`
- `topic_mapping.suggested_topic`
- `topic_mapping.score`
- `topic_mapping.confidence`
- `topic_mapping.alternatives`
- `topic_mapping.accepted`
- `topic_mapping.mapped_at`

The canonical relational projection follows the already-approved Phase 3 Fix 7 rules for accepted/proposed state, ranking, score selection, method, reason, and reviewed time. Raw JSON evidence is also compared exactly so canonical parity cannot hide raw drift.

## Parity domains

Phase 4.4 compares and/or validates:

- exact raw `topic` and `topic_mapping` observations per question;
- source version and SHA-256;
- accepted/proposed current mapping rows;
- question ownership;
- topic ownership;
- assessment-course versus topic-course relationship;
- normalized topic identity;
- score;
- candidate rank/order;
- method;
- state;
- provenance/reason;
- created/reviewed timestamps where Phase 3 mapping semantics make them meaningful;
- deleted or missing question/topic targets;
- duplicate current ranks;
- unledgered SQLite mapping rows;
- retained historical mapping rows from older source hashes.

Unresolved or ambiguous legacy candidates are not guessed into topic foreign keys. They remain explicit deferred/review evidence.

## Historical mapping rows

Phase 3 Fix 7 intentionally does not treat a later source omission as deletion authority. Therefore a mapping row supported only by an older source hash is reported as historical/deferred state, not silently treated as a current mapping and not automatically labelled corruption. A row with no migration ledger support is a structural anomaly.

## Safety guarantees

Focused tests use only sanitized JSON fixtures and temporary SQLite databases. They verify:

- legacy bytes/hash do not change during reads;
- SQLite logical state and `connection.total_changes` do not change during reads;
- `PRAGMA integrity_check` returns `ok`;
- `PRAGMA foreign_key_check` returns no rows;
- dual-read writes continue to go only to legacy JSON;
- SQLite failures do not replace successful legacy reads;
- diagnostic sink failures do not break legacy reads;
- no production database is opened implicitly.

## Explicit non-goals

Phase 4.4 does not:

- modify `automatic_topic_mapping.py`;
- modify `assessment_question_workspace.py`;
- rerun or retune topic similarity heuristics;
- infer new topic decisions from question text;
- make SQLite authoritative;
- disable legacy JSON writers;
- delete historical mapping rows;
- import or cut over attempts, mistakes, performance, learning memory, progress, plans, grades, calendar, notes, resources, RAG, Obsidian, or dashboards;
- begin Phase 5.

Attempts + Mistakes + Performance remain the next structured cutover domain.

## Verification

Run from the repository root before staging or committing:

```powershell
.\phase4_fix4_gate.ps1
```

The gate requires:

- branch `phase4/structured-cutover`;
- HEAD exactly `eb53aee70d85d8448d78067e6efa96c3daa33c62`;
- no pre-staged changes;
- only the approved Phase 4.4 change set;
- Phase 4.4 focused tests;
- Phase 4.3, 4.2, and 4.1 focused regressions;
- every Phase 3 regression/safety test;
- the full pytest suite;
- Python compilation;
- dependency consistency;
- `git diff --check` and repository hygiene.

Do not commit until this gate is completely green.

## Rollback

Before final Phase 4 authority cutover, rollback is simple: remove/disable the Phase 4.4 dual-read selection and continue using the legacy JSON workspace. No migration in Phase 4.4 changes the authoritative source or performs SQLite writes.
