# Final Phase 4 Structured Cutover / Reconciliation Gate

## Starting point

This gate starts from the completed Phase 4.8 commit on `phase4/structured-cutover`:

`a6786de29dfdaaa1ab10bfb2eae005d069164c08`

That commit contains the completed Phase 4.1-4.8 sequence:

1. Courses + Topics
2. Assessments + Assessment Topics
3. Assessment Questions + Question Sources
4. Question Topic Mappings
5. Attempts + Mistakes + Assessment Performance
6. Learning Memory + Academic Progress
7. Study Plans
8. Grades + Academic Calendar

## Why this final gate exists

The eight Phase 4 units deliberately established **legacy-authoritative dual-read foundations**. Each unit kept JSON/current storage authoritative, read SQLite as a shadow, compared semantic parity, and prevented SQLite failures from changing application-visible results.

A final gate is still needed because per-domain green tests do not by themselves prove that:

- every Phase 4 domain is represented in the final evidence set;
- the shared SQLite schema is intact as one database;
- migration-ledger targets still resolve to real relational rows;
- no Phase 4 domain silently introduced an SQLite-authoritative mode;
- Phase 3 reverse-export/reconciliation protections still pass after all Phase 4 work;
- the whole repository remains regression-green.

This gate supplies that cross-domain proof.

## Critical authority statement

> Legacy/current structured storage remains authoritative during this gate.
> SQLite remains read-only shadow state.

This final gate **does not** perform the production authority switch.

The project migration plan describes a later promotion sequence that requires a mutation lock, final delta import, final integrity/reconciliation checks, immutable backup, atomic `storage_backend=sqlite` switch, and application-layer blocking of legacy JSON writers.

The current Phase 4.1-4.8 implementation intentionally exposes only `legacy` and `dual_read` modes. It does not contain a global `storage_backend=sqlite` application switch. Therefore this gate must not pretend that SQLite has already become authoritative.

A green gate means:

> the Phase 4.1-4.8 shadow/reconciliation foundation is coherent and ready for the explicit authority-promotion implementation.

It does **not** mean the final authority promotion has already happened.

## New final reconciliation helper

`personal_learning_assistant/repositories/phase4_reconciliation.py` adds a read-only aggregator over the eight existing Phase 4 parity-report families.

It requires evidence for exactly these domains:

- `courses_topics`
- `assessments_topics`
- `questions_sources`
- `question_topic_mappings`
- `attempts_performance`
- `learning_progress`
- `study_plans`
- `grades_calendar`

The aggregator does not replace or rewrite the existing per-domain comparators. It only summarizes their explicit results.

### Domain status policy

- any mismatch/error -> `blocked`
- no mismatch but documented deferred evidence -> `review_required`
- no mismatch and no deferred evidence -> `pass`

Deferred evidence is never silently converted into success.

## SQLite structural reconciliation

The final helper checks one explicit SQLite connection and performs zero writes.

It verifies:

- all Phase 4 structured-domain tables exist;
- `PRAGMA integrity_check` returns only `ok`;
- `PRAGMA foreign_key_check` returns no rows;
- Phase 4-owned `migration_imports` targets still exist in the relational tables;
- composite `semester_courses` ledger targets still resolve;
- one current legacy identity does not point to multiple targets for the same source hash/version;
- `connection.total_changes` remains unchanged by reconciliation.

The helper refuses a database whose filename is `learning_assistant.db`. Tests and reconciliation must use an explicit temporary/shadow database.

## Required Phase 4 tables

The final readiness report covers the relational structures already introduced and exercised by Phase 4:

- semesters / courses / semester_courses / aliases
- topics / topic aliases
- assessments / assessment topics
- questions / question sources
- question-topic mappings
- question attempts / mistake events
- learning-memory entries / topic-progress events / progress snapshots
- study plans / study-plan items
- grade scales / grade bands / semester grade settings
- manual grade entries / semester results
- academic events
- migration ledger and schema migrations

Notes, Resources, document registry, RAG, Obsidian, Dashboard 2 and agent cutover remain Phase 5/6 work and are not promoted into this gate.

## Gate sequence

`phase4_final_gate.ps1` is fail-fast and runs:

1. final Phase 4 cross-domain reconciliation tests;
2. Phase 4.8 regression;
3. Phase 4.7 regression;
4. Phase 4.6 regression;
5. Phase 4.5 regression;
6. Phase 4.4 regression;
7. Phase 4.3 regression;
8. Phase 4.2 regression;
9. Phase 4.1 regression;
10. Phase 3 reconciliation + reverse-export/restore regression;
11. every Phase 3 regression/safety test;
12. complete repository pytest suite;
13. Python compilation;
14. dependency consistency;
15. Git whitespace and repository hygiene.

The gate also checks that all Phase 4.1-4.8 documentation and gate scripts are present and that only the final-gate files are modified while gating.

## Safety boundary

The final gate must not:

- modify `main`;
- create another development branch;
- open or create `data/learning_assistant.db`;
- read Anand's private structured JSON for test fixtures;
- modify real legacy JSON;
- modify Obsidian/vault content;
- run a production delta import;
- create a production backup;
- switch storage authority;
- block legacy writers;
- start Phase 5;
- weaken any earlier Phase 4 gate.

All new tests use temporary SQLite databases and synthetic/existing sanitized fixtures.

## Files added

This final readiness unit adds only:

- `personal_learning_assistant/repositories/phase4_reconciliation.py`
- `tests/test_phase4_final_reconciliation.py`
- `PHASE4_FINAL_STRUCTURED_CUTOVER_RECONCILIATION.md`
- `phase4_final_gate.ps1`

Existing Phase 4.1-4.8 implementation files remain unchanged.

## Passing interpretation

If `phase4_final_gate.ps1` is completely green, it proves that the completed shadow foundations still compose safely and that no unexplained regression was introduced across the full Phase 4 sequence.

It is then safe to review/commit this final reconciliation gate and begin the **explicit authority-promotion step** required by the migration plan.

Do not merge `main`, delete legacy JSON, or begin Phase 5 merely because this readiness gate passes.
