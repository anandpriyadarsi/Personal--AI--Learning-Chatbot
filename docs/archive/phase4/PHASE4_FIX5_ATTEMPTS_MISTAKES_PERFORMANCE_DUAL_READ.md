# Phase 4.5 — Attempts + Mistakes + Performance SQLite Dual-Read Foundation

## Starting point

Phase 4.5 starts from `phase4/structured-cutover` at gate-passed Phase 4.4
commit `f4fe74f46ccf208e2d4dfd9bdb5d053bfd7e9b35`.

## Purpose and authority boundary

Phase 4.5 brings the Phase 3 Fix 8 attempt/performance domain into the same
legacy-authoritative dual-read pattern established by Phase 4.1–4.4.

Legacy `data/assessment_workspace.json` remains authoritative for both reads and
writes. Existing `assessment_performance.py` and
`assessment_question_workspace.py` are not rewired. SQLite is a read-only
shadow used only for semantic and structural parity diagnostics.

There is no SQLite-authoritative mode and no dual write in this phase.

## Legacy evidence shapes

Phase 3 Fix 8 deliberately supports both historical attempt shapes:

- top-level `question["attempts"]`;
- V10.4 `question["performance"]["attempts"]`.

Phase 4.5 therefore preserves origin and ordering across both shapes when
comparing imported attempts. It also preserves exact raw JSON evidence before
canonical comparison, so normalization cannot hide source differences.

The current V10.4 `question_performance()` calculation is narrower: its derived
attempt count, accuracy, marks accuracy, and outcome counts use only
`performance.attempts`. Phase 4.5 mirrors that read behavior separately from the
broader Fix 8 migration inventory.

## Repository seam

Phase 4.5 adds:

- `LegacyJsonAttemptPerformanceRepository`, an explicit alias over the existing
  legacy question-workspace authority;
- `SQLiteAttemptPerformanceRepository`, which requires an already-open
  `sqlite3.Connection`, reads actual `question_attempts` / `mistake_events`
  relationships, and rejects writes;
- `AttemptPerformanceBackendConfig` supporting only `legacy` and `dual_read`;
- `DualReadAttemptPerformanceRepository`, which returns/saves only through the
  legacy repository while independently recording SQLite parity reports.

A failed SQLite shadow read or failed diagnostic sink never replaces a valid
legacy result.

## Parity domains

Current evidence is compared across:

- exact raw top-level attempt / mistake / `performance` evidence;
- source hash and source version;
- attempt question ownership;
- attempt origin and source position;
- meaningful per-question attempt order / attempt number;
- canonical outcome;
- canonical weight evidence retained in the Fix 8 ledger;
- earned and maximum marks in milli-units;
- response and feedback references;
- occurrence timestamp;
- attempt-attached mistake ownership;
- mistake category, exact text, creation timestamp, and unresolved state;
- V10.4 nested-performance attempt counts, accuracy, marks accuracy, and outcome
  counts;
- current-vs-historical migration rows;
- unledgered live attempt/mistake rows and relational corruption.

Migration ledger evidence supports identity and raw provenance, but actual live
SQLite foreign-key relationships are inspected independently; ledger
expectations cannot mask a moved attempt or mistake.

## Standalone mistakes are explicitly deferred

Fix 8 imports only mistake text attached to a concrete attempt. Standalone
`performance["mistakes"]` and top-level `question["mistakes"]` lists cannot be
safely attached because the core `mistake_events` schema requires a real
attempt owner.

Phase 4.5 preserves these lists as explicit `deferred` diagnostics. It never
invents an attempt relationship merely to make parity pass.

## Historical rows

Stable attempt/mistake IDs can survive a changed source hash, while an omitted
legacy attempt is not deletion authority. Live rows evidenced only by older
workspace hashes are therefore reported as deferred historical rows rather than
silently treated as current performance.

A live attempt or mistake with no migration-ledger evidence at any source hash
is a structural mismatch.

## Performance and learning-memory boundary

Phase 4.5 validates persisted attempt evidence and current V10.4 performance
summaries only. It does not mark topics weak/mastered, accept mastery
suggestions, change learning memory, or change academic progress. Those domains
remain separate and Phase 4.6 handles Learning Memory + Academic Progress.

## Safety guarantees

Focused tests verify:

- the authoritative JSON bytes/hash remain unchanged during reads;
- SQLite table contents and `connection.total_changes` remain unchanged;
- `PRAGMA integrity_check` returns `ok`;
- `PRAGMA foreign_key_check` returns no violations;
- SQLite write attempts fail explicitly;
- dual-read saves affect only legacy JSON;
- no production database is opened implicitly.

All fixtures are synthetic and SQLite databases are temporary.

## Verification

Before committing Phase 4.5, run:

```powershell
.\phase4_fix5_gate.ps1
```

The gate requires the exact Phase 4.4 base, a clean/uncommitted Phase 4.5 change
set, focused Phase 4.5 tests, every earlier Phase 4 focused regression, all
Phase 3 tests, the complete pytest suite, compilation, dependency consistency,
`git diff --check`, and repository-hygiene checks.

## Rollback

Before final structured cutover, rollback is trivial: select the `legacy`
backend or remove the Phase 4.5 shadow adapter. JSON writers and the public
performance engine remain unchanged, and SQLite has no authority over user
performance data.

## Non-goals

Phase 4.5 does not:

- modify `assessment_performance.py` or `assessment_question_workspace.py`;
- make SQLite authoritative;
- add SQLite performance writers;
- delete legacy JSON;
- infer topic mappings from attempt/mistake text;
- change weak/mastered topics or learning memory/progress;
- cut over study plans, grades, calendar, Notes, Resources, RAG, Obsidian, or
  dashboards;
- begin Phase 5.
