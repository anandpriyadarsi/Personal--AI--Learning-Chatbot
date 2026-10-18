# Phase 4.9 — SQLite Authority-Promotion Foundation

## Starting point

Phase 4.9 starts from `phase4/structured-cutover` at the completed and pushed
Final Phase 4 Structured Cutover / Reconciliation Gate commit:

`eaf49eed699c80cd72a43d4c853682eef27d08db`

Phase 4.1–4.8 and the final reconciliation gate remain unchanged.

## Why this is a separate substep

The migration plan defines the final structured cutover as:

1. acquire a local mutation lock;
2. rehash legacy inputs and import any delta;
3. run integrity/reconciliation checks;
4. take a final JSON + SQLite backup;
5. set `storage_backend=sqlite` atomically;
6. release the lock;
7. block legacy JSON writes at the application layer.

The current Phase 4 SQLite repositories were deliberately built as read-only
shadow readers.  They are safe for dual-read parity but are not yet a complete
application write authority.  Therefore Phase 4.9 must **not** flip production
authority simply because the read-side reconciliation gate is green.

Phase 4.9 establishes the safety primitives needed by the real authority switch.
It does not perform that switch on import and does not change the current
application backend.

## Authority boundary

During Phase 4.9:

- legacy/current JSON remains authoritative;
- the existing Phase 4 dual-read behavior remains unchanged;
- SQLite remains the structured candidate authority;
- no existing backend factory gains an implicit `sqlite` mode;
- no legacy writer is disabled yet;
- no production database is opened or created by importing the new module.

## New module

`personal_learning_assistant/migration/authority_promotion.py` adds explicit,
side-effect-controlled primitives for the final cutover.

### 1. Local mutation lock

`LocalMutationLock` uses exclusive file creation and records a random ownership
token, PID, and acquisition timestamp.

Safety rules:

- the caller supplies the lock path explicitly;
- the parent must already exist;
- an existing lock is never stolen automatically;
- a changed ownership token prevents release;
- no stale-lock timeout silently re-enables mutations during a cutover.

### 2. Structured-source rehashing

`scan_structured_sources(...)` reuses the Phase 3 legacy source scanner for only
the Phase 4 structured stores:

- `courses.json`
- `assessments.json`
- `assessment_workspace.json`
- `learning_memory.json`
- `course_progress_history.json`
- `weekly_study_plans.json`
- `multi_course_weekly_plans.json`
- optional `intelligent_study_plans.json`
- optional `semester_grade_config.json`

Notes, Resources, and Obsidian configuration are deliberately excluded because
they are Phase 5 domains, not Phase 4 structured authority.

`validate_structured_manifest(...)` blocks missing/invalid mandatory stores.
`verify_manifest_unchanged(...)` detects any source-byte/status/count change
between two scans while the mutation lock is expected to be held.

### 3. SQLite readiness validation

`validate_sqlite_readiness(connection)` requires an explicitly supplied
`sqlite3.Connection` and verifies:

- Phase 3 schema migration versions 1 and 2 are present;
- every Phase-4 structured table required for authority exists;
- `PRAGMA integrity_check` returns exactly `ok`;
- `PRAGMA foreign_key_check` returns no violations;
- validation changes neither logical rows nor `connection.total_changes`.

An empty SQLite file therefore cannot accidentally pass merely because its
`integrity_check` is technically `ok`.

### 4. Final JSON + SQLite backup

`create_final_cutover_backup(...)`:

- requires a validated source manifest;
- refuses to write inside the live `data/` directory;
- refuses to overwrite an existing backup directory;
- copies every present Phase-4 legacy JSON source byte-for-byte;
- uses SQLite's online backup API for the supplied database connection;
- writes a deterministic hash manifest;
- verifies the backed-up SQLite database with integrity and foreign-key checks;
- removes only the newly-created incomplete backup directory if backup creation
  fails;
- never edits the live legacy source files.

The helper records pre-promotion authority state when supplied, but never
pretends that a backup itself is an authority switch.

### 5. Atomic backend-control state

`AuthorityControlState` supports exactly:

- `legacy`
- `dual_read`
- `sqlite`

A SQLite state is invalid unless the same atomic state also contains:

- a cutover ID;
- the final structured-source manifest SHA-256;
- a verified SQLite backup SHA-256;
- promotion timestamp evidence;
- `legacy_writes_blocked=true`.

`write_authority_control_atomic(...)` uses a same-directory temporary file,
file flush/fsync, and `os.replace(...)`.  It also supports compare-and-swap via
`expected_current` so a backend control changed after preflight cannot be
silently overwritten.

Rollback from SQLite authority is rejected unless the caller explicitly asks
for an approved rollback transition.  Phase 3 reverse export/reconciliation
remains the required rollback evidence path; this helper does not invent it.

### 6. Legacy writer guard primitive

`assert_legacy_write_allowed(...)` is the application-layer primitive that later
writer adapters must call.  It permits writes in `legacy`/`dual_read` state and
raises `LegacyWriteBlockedError` once SQLite authority has been atomically
promoted.

Phase 4.9 deliberately does **not** scatter this guard through old procedural
modules yet.  Doing so before writable SQLite command repositories exist would
block legitimate writes without providing a replacement authority.

## What Phase 4.9 does not do

Phase 4.9 does **not**:

- run against Anand's real private JSON automatically;
- create `data/learning_assistant.db`;
- perform the final delta import;
- promote a temporary/staging database into the production path;
- make any Phase 4 SQLite repository writable;
- add `sqlite` authority mode to the existing domain backends;
- modify `config.py`;
- modify current legacy procedural writers;
- block legacy writes in the running application yet;
- touch Notes, Resources, Obsidian, knowledge, RAG, Dashboard 2, or Phase 5;
- merge or modify `main`.

## Focused tests

`tests/test_phase4_authority_promotion.py` covers:

- missing control state defaults safely to legacy without file creation;
- atomic backend-control writes and compare-and-swap behavior;
- invalid/unsupported control evidence rejection;
- explicit rollback approval requirement;
- SQLite authority requiring legacy writer blocking in the same state;
- legacy writer guard behavior;
- exclusive mutation lock and ownership protection;
- Phase-4-only structured source scope;
- mandatory/optional source manifest rules;
- manifest drift detection;
- full Phase 3 schema requirement before SQLite readiness;
- integrity/foreign-key/read-only readiness checks;
- final byte-preserving structured JSON backup;
- SQLite online backup and post-copy verification;
- no-overwrite and no-live-data-directory backup rules;
- source-drift detection between scan and backup;
- zero implicit production database path.

All fixtures/directories/databases are temporary and synthetic.

## Gate

Run:

```powershell
.\phase4_authority_promotion_gate.ps1
```

The gate pins the completed final Phase 4 reconciliation commit, runs the new
focused tests, final reconciliation regression, all Phase 4 regressions, all
Phase 3 tests, the complete test suite, compilation, dependency consistency,
`git diff --check`, and repository hygiene.

## Next boundary

After this foundation gate passes, the next authority-promotion unit must wire
**writable SQLite command repositories and legacy-writer guards** for the
structured domains while preserving rollback.  Only after those command paths
are green should a final locked delta-import + backup + atomic
`storage_backend=sqlite` cutover be executed.

That final switch is an explicit operation, not a side effect of importing this
module or committing Phase 4.9.
