# Final Phase 4 — Locked SQLite Authority Promotion

## Starting point

This unit starts from the completed, gate-passing Phase 4.11 commit on:

`phase4/structured-cutover`

`3b7b0d1aa6d1b5844694f29ca669ff779b0f109d`

`feat: add Phase 4.11 structured authority routing and compatibility cutover`

Phase 4.1–4.11 remain intact. This unit does not modify `main` and does not
perform promotion merely by being imported, tested, extracted, or committed.

## Objective

Phase 4.1–4.8 proved legacy-to-SQLite semantic parity while legacy JSON remained
authoritative. The final reconciliation gate proved the structured relational
foundation. Phase 4.9 added promotion safety primitives. Phase 4.10 added
transaction-safe SQLite commands and fail-closed legacy writer guards. Phase
4.11 routed the existing V8–V13 compatibility APIs so they can run under SQLite
authority.

This unit adds the **single explicit, locked operation** that can perform the
actual structured authority switch.

The promotion sequence is:

1. require explicit operator confirmation;
2. acquire the local Phase-4 mutation lock;
3. scan/hash the exact structured legacy sources;
4. build an isolated SQLite promotion candidate;
5. run the final structured import delta in dependency order;
6. bridge the documented V9 progress-history format boundary deliberately;
7. validate SQLite schema, integrity, FKs, ledger targets and duplicate import identities;
8. seed all Phase-4.11 compatibility projections from the same locked source manifest;
9. prove the legacy source manifest is unchanged;
10. create the final no-overwrite byte-preserving JSON + SQLite backup;
11. preserve the previous shadow DB separately when one exists;
12. atomically install the exact verified backup SQLite bytes at `data/learning_assistant.db`;
13. re-check the legacy source manifest immediately before authority switch;
14. atomically write `.phase4_authority.json` with `storage_backend=sqlite` and `legacy_writes_blocked=true`;
15. run post-promotion router, hash, integrity, FK, ledger and source-manifest smoke checks;
16. write promotion evidence;
17. release the cutover lock only after every post-promotion check succeeds.

## Authority boundary after success

After a successful final promotion:

- structured Phase-4 application state is authoritative in SQLite;
- legacy structured JSON is retained as read-only migration/rollback evidence;
- Phase-4.10 guards block legacy structured writes;
- Phase-4.11 compatibility APIs route reads/writes through SQLite;
- the final backup records the exact initial authoritative SQLite database;
- Notes, Resources, Obsidian, knowledge documents, RAG and other Phase-5 domains remain outside this switch.

`courses.json.document_links` remains the explicit Phase-5 deferred sub-domain.
It is not silently claimed by this structured cutover.

## Files added

This final unit adds only:

- `personal_learning_assistant/migration/final_locked_promotion.py`
- `phase4_promote_sqlite.py`
- `tests/test_phase4_final_locked_promotion.py`
- `PHASE4_FINAL_LOCKED_SQLITE_AUTHORITY_PROMOTION.md`
- `phase4_final_promotion_gate.ps1`

No Phase 4.1–4.11 implementation file is modified.

## Read-only preflight

The CLI provides a preflight that performs no writes:

```powershell
python .\phase4_promote_sqlite.py `
  --project-root . `
  --backup-dir .\phase4_cutover_backups\final-2026-09-15 `
  --preflight
```

The backup parent directory must already exist, while the named final backup
directory must not exist.

Preflight validates:

- project/data paths;
- current authority state is legacy or dual-read;
- no cutover lock exists;
- no stale `.phase4_cutover_work` directory exists;
- all mandatory Phase-4 structured sources are valid JSON;
- optional intelligent-plan/grade-config sources are either valid JSON or absent;
- an already-existing `data/learning_assistant.db`, if present, passes schema,
  migration, integrity and foreign-key checks;
- no DB, control file, lock, backup directory or work directory is created.

## Explicit execution confirmation

Execution requires the exact phrase:

`PROMOTE_PHASE4_SQLITE_AUTHORITY`

Example:

```powershell
python .\phase4_promote_sqlite.py `
  --project-root . `
  --backup-dir .\phase4_cutover_backups\final-2026-09-15 `
  --confirm PROMOTE_PHASE4_SQLITE_AUTHORITY
```

**Before running execution, stop every Personal AI Learning Assistant process**
that could write structured state. The local cutover lock prevents competing
promotion runs, but an unrelated old process that ignores that lock cannot be
forcibly terminated by this module.

## Promotion candidate policy

The final importer never performs the multi-step legacy import directly against
an authoritative production DB.

Instead it creates an isolated promotion candidate:

- if `data/learning_assistant.db` already exists, it is copied with SQLite's
  online backup API and current migrations are applied to the candidate;
- if no production/shadow DB exists yet, a new candidate is created from the
  repository's current schema migrations;
- all final legacy imports, reconciliation checks and compatibility seeding run
  against the candidate only;
- `data/learning_assistant.db` is created/replaced only after the candidate has
  passed validation and has been captured in the final cutover backup.

This avoids leaving a partially imported DB authoritative if a late importer
fails.

## Final import order

The locked final delta reuses the existing Phase-3 importers in dependency
order:

1. Courses + Topics
2. Assessments + Assessment Topics
3. Questions + Question Sources
4. Question Topic Mappings
5. Attempts + Mistakes + Performance
6. Learning Memory + Academic Progress
7. Weekly / Multi-Course / Intelligent Study Plans
8. Grades + Academic Calendar

Each importer retains its established stable-ID, raw-evidence, migration-ledger
and transaction semantics.

## Explicit V9 progress-history bridge

Phase 4.6 documented a real current-format boundary:

- the current `academic_progress.load_history()` API persists/reads a `courses`
  mapping;
- the older Phase-3 Fix 9 importer reads the legacy `history` mapping.

The final cutover cannot leave that discrepancy unresolved.

`final_locked_promotion.py` therefore performs one explicit bridge after the
Phase-3 Fix 9 importer:

- current `courses`-shape snapshots are copied into normalized
  `progress_snapshots`;
- stable IDs use the existing progress engine/version identity;
- source bytes are never rewritten;
- migration-ledger evidence uses the established `course_progress_snapshot` kind, with explicit `source_shape=courses` / bridge evidence, so the existing Phase 4.6 SQLite reader recognizes it as current progress history;
- if both `history` and `courses` contain the same course/date but disagree on
  total topics, mastered topics or progress percentage, promotion is blocked
  instead of silently choosing one version.

This is a deliberate final-cutover reconciliation, not a hidden normalization
inside an ordinary read path.

## Compatibility projection seed

Phase 4.11 compatibility projections are seeded only after final import and
before the authority switch.

The seed is built from the same locked structured source manifest and includes:

- courses;
- assessments;
- assessment workspace;
- learning memory;
- progress history;
- weekly study plans;
- multi-course weekly plans;
- intelligent study plans;
- semester grade configuration.

The two already-optional stores receive the Phase-4.11 safe default only when the
legacy source is absent.

Course `document_links` remain excluded from the SQLite structured projection,
matching the Phase-5 boundary.

## Final backup

The promotion uses the Phase-4.9 no-overwrite backup primitive.

The requested output directory contains at least:

```text
legacy_structured_json/
    courses.json
    assessments.json
    assessment_workspace.json
    learning_memory.json
    course_progress_history.json
    weekly_study_plans.json
    multi_course_weekly_plans.json
    [optional sources when present]

sqlite/
    learning_assistant.db
    [pre_promotion_shadow.db when an earlier DB existed]

cutover_backup_manifest.json
final_promotion_evidence.json
```

The legacy JSON files are copied byte-for-byte from the locked source manifest.
The final SQLite backup is checked with `PRAGMA integrity_check` and
`PRAGMA foreign_key_check` before it can be installed.

When an old shadow DB already exists, `pre_promotion_shadow.db` is preserved as
additional rollback evidence. It is never automatically made authoritative.

## Byte-identical initial authority

The exact SQLite file stored in the final backup is copied to a staging filename
inside `data/` and installed with `os.replace`.

Therefore the initial authoritative `data/learning_assistant.db` has the same
SHA-256 as the SQLite backup referenced by `.phase4_authority.json`.

Before replacing an existing shadow DB, the code checkpoints/truncates its WAL,
switches it to DELETE journal mode, and refuses promotion if stale WAL/SHM
sidecars cannot be cleared. This is another guard against running cutover while
an old application process still has the DB open.

## Atomic authority control

The authority file is written only after:

- all imports pass;
- known progress-history format reconciliation passes;
- integrity and FK checks pass;
- migration-ledger target validation passes;
- duplicate import identity validation passes;
- compatibility projection seeding passes;
- final backup passes;
- source manifest remains unchanged;
- verified SQLite backup bytes are installed.

The atomic state includes:

- `storage_backend = sqlite`
- `legacy_writes_blocked = true`
- `cutover_id`
- `source_manifest_hash`
- `sqlite_sha256`
- `promoted_at`

A compare-and-swap expectation prevents replacing authority state if it changed
since preflight.

## Failure policy

### Failure before authority switch

Before `storage_backend=sqlite` is written, **and only while the authority-control
file still exactly matches the preflight state**:

- legacy/current storage remains authoritative;
- the cutover lock is released after cleanup;
- a newly installed DB is deleted when no previous DB existed;
- when a previous DB existed and replacement happened, it is restored from the
  verified pre-promotion shadow backup;
- no automatic legacy source repair occurs.

If the authority-control file changes concurrently, automatic rollback is refused
and the operation fails closed with the lock retained. This prevents restoring an
old database underneath an authority state that another actor may already have
promoted.

### Failure after authority switch

After the atomic authority switch, automatic rollback is intentionally **not**
performed. A blind rollback could discard a legitimate SQLite write from
another process.

Instead:

- `.phase4_cutover.lock` is intentionally left in place;
- the final backup is retained;
- `PROMOTION_REQUIRES_ATTENTION.json` is written when possible;
- the operator is told not to run the application until the authority state and
  backup are reviewed.

This is fail-closed behavior.

## Post-promotion smoke checks

Before the lock is released, the promotion verifies:

- authority control exactly matches the intended SQLite state;
- production DB exists as a regular file;
- production DB SHA-256 equals the authority-control SQLite hash;
- SQLite schema/migrations are current;
- `PRAGMA integrity_check` returns `ok`;
- `PRAGMA foreign_key_check` returns no violations;
- migration ledger targets exist;
- no one current import identity maps to multiple relational targets;
- all nine compatibility projections exist;
- compatibility seed manifest hash equals the locked source manifest;
- the legacy source manifest is still unchanged;
- all nine Phase-4.11 runtime compatibility reads actually route through SQLite.

Only then is the lock released.

## Promotion evidence

A successful operation writes `final_promotion_evidence.json` inside the backup
directory. It records:

- cutover ID/time;
- source manifest hash;
- initial SQLite authority hash;
- backup manifest hash;
- import summaries;
- count of current-format progress snapshots bridged;
- compatibility stores seeded/smoked;
- prior and new authority states;
- whether a pre-existing DB existed;
- pre-promotion shadow backup hash when applicable;
- explicit confirmation that legacy structured JSON is retained and legacy
  structured writes are blocked;
- the deferred Phase-5 document-link boundary.

## Gate

Run before committing this final unit:

```powershell
.\phase4_final_promotion_gate.ps1
```

The gate uses temporary/synthetic projects and databases only. It **does not
promote your real data**.

It runs:

- 17 focused final-promotion safety/orchestration tests;
- Phase 4.11 routing regression;
- Phase 4.10 command/guard regression;
- Phase 4.9 promotion-foundation regression;
- final Phase-4 reconciliation regression;
- all Phase-4.1–4.8 regressions;
- all Phase-3 tests;
- the complete project test suite;
- Python compilation;
- dependency checks;
- `git diff --check`;
- strict change allow-list and private/runtime-data hygiene.

The gate must end with:

```text
FINAL PHASE 4 LOCKED SQLITE PROMOTION GATE: PASS
```

## Non-goals

This unit does not:

- modify `main`;
- create another development branch;
- run promotion automatically on import/startup;
- commit or push itself;
- delete legacy JSON after promotion;
- migrate course document links;
- migrate Notes/Resources/Obsidian/documents/RAG;
- start Phase 5;
- silently roll back after the authority switch;
- silently repair contradictory historical evidence.

## After this unit

After the gate passes, commit/push the implementation first.

Then run the CLI preflight against the real checkout and review its output. Only
after that review should the explicit final promotion command be executed.

A successful real promotion completes the **structured-storage authority cutover
for Phase 4**. Phase 5 can then begin on the remaining knowledge/document,
Notes/Resources/Obsidian/RAG boundaries without reopening the structured JSON
cutover.
