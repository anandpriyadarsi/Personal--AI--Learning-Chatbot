# Phase 3.1 Fix 4 — Legacy JSON Import Framework + Courses/Topics Importer

## Purpose

Fix 4 is the first real structured-data shadow importer in Phase 3. It imports a
verified `data/courses.json` snapshot into an explicit temporary SQLite database
without changing the authority boundary:

> Legacy JSON/current files remain authoritative. SQLite is a migration and
> reconciliation target until the Phase 4 cutover gate is explicitly approved.

The importer never creates or opens `data/learning_assistant.db` by default and
never rewrites `courses.json`.

## Shared legacy JSON import framework

`personal_learning_assistant/migration/legacy_json_import.py` adds reusable
safety helpers for later store-specific importers:

- verifies the scanner snapshot is still `valid_json`;
- re-hashes raw source bytes immediately before import;
- rejects a source that changed after scanning;
- supports an end-of-transaction re-hash to catch a file changing during import;
- validates the expected top-level JSON shape;
- checks that required SQLite tables exist before writing;
- generates stable UUID5 target IDs from portable source path + entity type +
  legacy identity, deliberately excluding the source hash;
- provides common import issue/tally models.

Excluding `source_hash` from target UUID generation is intentional. A changed
legacy file produces new `migration_imports` observations while the same logical
legacy course/topic can update the same stable SQLite target.

## Courses/topics importer

`personal_learning_assistant/migration/courses_topics_importer.py` imports the
approved first structured slice in migration order:

1. explicit legacy-semester placeholders;
2. courses;
3. semester/course offering rows;
4. topics;
5. the legacy active-course selection.

All domain rows and their `migration_imports` mappings are written inside one
explicit SQLite transaction.

### Semester placeholder policy

The current legacy course store contains a semester label but no authoritative
academic year. Fix 4 therefore does not guess one.

For legacy semester `1`, the temporary database receives a clearly marked
placeholder such as:

- name: `Legacy Semester 1`
- academic year: `legacy-unknown`
- credits: `NULL`

The placeholder must be reconciled with authoritative semester/credit data
before Phase 4 cutover.

### Stable identity policy

All new structured primary IDs are UUID strings as required by the SQLite
proposal. The importer prefers explicit legacy IDs when they exist. For a course
without a legacy ID, its normalized course code becomes the fallback legacy
identity. For a topic without a legacy ID, normalized topic name becomes the
fallback identity.

The migration ledger still stores the full source path/hash/version/legacy key
for each target mapping.

### Status and raw-value policy

Course/topic status uses the existing Phase 2 normalization vocabulary, which
already includes `practiced`. Topic `raw_import_status` preserves the original
legacy status text so aliases or unexpected values remain reviewable.

Invalid topic confidence is imported as `NULL` with a warning; out-of-range
numeric confidence is clamped to `0..5` with a warning. The original topic
record remains preserved in the import-ledger details and in the untouched JSON
source.

### Active course

If `active_course_id` resolves to an explicit legacy course ID, the imported
stable course UUID is recorded in `app_settings` under `active_course_id` and a
ledger mapping is created. An unresolved active-course reference is reported as
a warning rather than guessed.

## Explicitly deferred data

Fix 4 does not pretend to migrate fields whose authority is not available yet:

- `document_links` remain in `courses.json` and are reported as deferred for the
  later knowledge/document migration unit;
- `semester_courses.credits_milli` remains `NULL` because `courses.json` has no
  authoritative credit field;
- no course document, vault, assessment, grade, plan, or performance record is
  imported here.

## Idempotency and delta behavior

For an unchanged source hash, running the importer again:

- creates no duplicate domain row;
- creates no duplicate ledger row;
- does not rewrite already matched target rows.

If the source hash changes, the importer creates a new set of ledger
observations while deterministic UUIDs allow the same legacy identities to
update the same target rows. If an identity collision, duplicate course code, or
duplicate topic name would make the import ambiguous, the importer fails rather
than silently dropping or renaming source data.

## Verification

Run:

```powershell
.\phase3_fix4_gate.ps1
```

The targeted tests verify:

1. sanitized `courses.json` imports semester/course/topic structure correctly;
2. source bytes remain unchanged;
3. primary target IDs are valid stable UUIDs;
4. active course is preserved;
5. credits remain `NULL` and document links remain explicitly deferred;
6. identical re-import is a no-op with no duplicate ledger entries;
7. a changed source hash updates stable targets and records new ledger evidence;
8. the `practiced` status survives and aliases preserve raw status text;
9. duplicate course codes and malformed shapes fail without partial writes;
10. a source changed after scan is rejected before any import write.

The gate also runs every Phase 3 test, the full project regression suite, Python
compilation, `git diff --check`, and checks that production DB/private JSON files
remain outside Git.

## Non-goals

Fix 4 does **not**:

- create/populate the production SQLite database;
- cut any application service over to SQLite;
- import document links or knowledge metadata;
- import assessments/questions/performance;
- import learning memory/progress/plans/grades/calendar;
- reverse-export or reconcile all stores;
- disable legacy JSON writers.

Those remain later Phase 3/Phase 4 units.
