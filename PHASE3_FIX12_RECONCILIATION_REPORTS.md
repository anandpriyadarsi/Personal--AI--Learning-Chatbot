# Phase 3.1 Fix 12 — Reconciliation Reports

## Purpose

Fix 12 turns the Fix 3–11 migration evidence into one machine-readable JSON
report and one matching Markdown review report. It reads an already-open
temporary SQLite shadow database and the exact legacy-source manifest used by
the import run.

The Phase 3 authority boundary remains unchanged:

> Legacy JSON/current files remain authoritative. SQLite is a temporary
> migration and reconciliation target until the Phase 4 cutover gate is
> explicitly approved.

Generating a report does not open or create a database, mutate SQLite, rewrite
a legacy file, run a planner/grade/priority engine, or switch an application
backend.

## Public API

`personal_learning_assistant/migration/reconciliation_reports.py` provides:

- `build_reconciliation_report(...)` / `generate_reconciliation_report(...)`;
- `summarize_import_result(...)` for every Fix 4–11 importer result;
- `make_parity_check(...)` with optional documented numeric tolerance;
- `RollbackEvidence` for the exact backup, hash, command, and runbook;
- `render_reconciliation_json(...)`;
- `render_reconciliation_markdown(...)`.

The report builder accepts explicit evidence. It does not reconstruct a
successful importer disposition, parity result, or verified rollback rehearsal
from row counts alone.

## Report coverage

Both formats contain the same core evidence:

1. report version, generated timestamp, shadow/authority status;
2. scanned and current source path, byte count, SHA-256, schema version,
   preservation result, and current-hash ledger coverage;
3. importer counts for before, imported, created, updated, matched, skipped,
   and flagged records, with per-entity tallies;
4. applied SQLite migration versions/checksums and every table count;
5. `PRAGMA integrity_check` and `PRAGMA foreign_key_check` results;
6. relationship counts across academic, notes/resources, assessment,
   performance, planning, grade, and calendar tables;
7. missing ledger targets and legacy identities that drifted to two targets;
8. unresolved references and durable ledger review/deferred markers;
9. assessment weight totals and invalid/incomplete score evidence;
10. requested, allocated, and active-item plan minutes for every plan;
11. semester-result arithmetic, unverified scales, and missing credits;
12. one-to-one assessment-deadline/calendar projection checks;
13. explicit priority, performance, plan, calendar, grade, and brief parity;
14. exact rollback backup/hash/command/runbook evidence;
15. structured findings and an overall `pass`, `review_required`, or `blocked`
    status.

The known V9.2 `120 requested / 108 allocated` fixture is preserved and appears
as `documented_difference`; it is never silently rewritten to make totals look
equal.

## Status rules

`blocked` means at least one error exists, including source-byte drift, schema
loss, failed SQLite checks, broken ledger targets, identity drift, invalid
assessment/semester arithmetic, calendar projection mismatches, or failed
old-versus-new parity.

`review_required` means the database is structurally usable but evidence still
needs review, such as an uncovered valid source, unresolved relationship,
flagged importer record, requested/allocated plan difference, unverified grade
scale, parity that has not run, or incomplete rollback evidence.

`pass` is possible only when there are no errors or warnings. A missing parity
domain is always `not_run`, never an implicit pass. Rollback evidence passes
only when the caller supplies portable project-relative evidence and explicitly
marks the rehearsal verified.

## Safety decisions

- The database connection is mandatory; importing this module has no I/O.
- A main database named `learning_assistant.db` is rejected in Phase 3.
- Only portable source, backup, and runbook paths enter reports.
- The source manifest is rebuilt after reconciliation, and every expected
  source exposes both scanned and current content hashes.
- Ledger table identifiers are checked against the live schema and safely
  quoted before target existence checks.
- Composite primary keys such as `semester_courses` are reconciled.
- The report checks `connection.total_changes` before and after generation.
- JSON rendering is deterministic and UTF-8 safe.
- No report artifact is written into `data/` automatically.

## Verification

Run:

```powershell
.\phase3_fix12_gate.ps1
```

The focused tests verify:

1. portable JSON and Markdown contain all required sections;
2. source and database bytes/rows remain unchanged;
3. Fix 4–11 result adapters expose exact import/match counts;
4. an identical second import reports matched rows and zero created/updated
   rows;
5. post-scan source changes block the report and include the new hash;
6. foreign-key violations and missing ledger targets block the report;
7. one legacy identity mapped to multiple targets is listed as a duplicate;
8. missing parity stays `not_run`, and failed parity blocks;
9. unverified/non-portable rollback evidence cannot pass;
10. the production database filename is rejected;
11. documented numeric parity tolerances are applied exactly;
12. the 120/108 planner discrepancy, grade verification state, assessment
    calendar relationship, schema checks, and relationship counts are visible.

The gate also runs every Phase 3 test, the full regression suite, Python
compilation, `git diff --check`, and repository hygiene checks for production
database/private JSON files.

## Non-goals

Fix 12 does **not**:

- perform final old/new engine characterization on behalf of callers;
- claim missing notes/resources/vault/document imports are complete;
- create reverse exporters or rehearse a restore;
- generate a backup or accept an unverified backup as sufficient;
- repair, delete, or normalize source content;
- promote a shadow database;
- disable legacy writers or perform Phase 4 cutover.

Those remain explicit later Phase 3 units and Phase 4 gates. Fix 12 makes each
gap measurable instead of hiding it.
