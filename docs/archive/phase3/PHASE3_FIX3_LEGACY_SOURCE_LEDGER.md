# Phase 3.1 Fix 3 — Legacy Source Scanner + Migration Import Ledger

## Purpose

Fix 3 adds the read-only source inventory and idempotency boundary required before
any legacy record is imported into SQLite.

The Phase 3 authority rule is unchanged:

> Legacy JSON/current files remain authoritative. SQLite is still a temporary
> migration target until the Phase 4 structured-domain cutover is approved.

This fix does not import, repair, normalize, or rewrite user data.

## Legacy source scanner

`personal_learning_assistant/migration/legacy_source_scanner.py` defines the 12
legacy structured stores from the approved migration plan:

1. `data/notes.json`
2. `data/resources.json`
3. `data/courses.json`
4. `data/learning_memory.json`
5. `data/course_progress_history.json`
6. `data/weekly_study_plans.json`
7. `data/multi_course_weekly_plans.json`
8. `data/assessments.json`
9. `data/assessment_workspace.json`
10. `data/obsidian_config.json`
11. `data/intelligent_study_plans.json` — optional/absent is valid
12. `data/semester_grade_config.json` — optional/absent is valid

The scanner requires an explicit data-directory argument. It never creates that
directory. For each expected source it records portable metadata only:

- canonical project-relative path;
- raw-byte SHA-256 hash;
- byte count;
- source type;
- source version when safely discoverable from JSON;
- JSON shape;
- required/optional status;
- empty/missing/invalid status and issue text.

The deliberately zero-byte `resources.json` case is preserved as `empty` with
the standard SHA-256 of zero bytes and is not treated as corruption.

Unexpected top-level `*.json` files are reported instead of silently ignored.
Symlinks are not followed. Manifest serialization excludes the physical machine
path, so reports do not leak local usernames or drive paths.

The manifest hash is deterministic and is calculated from the portable source
metadata plus the unexpected-file list. Repeated scans of unchanged sources
therefore produce the same manifest hash.

## Migration import ledger

`personal_learning_assistant/migration/import_ledger.py` is a small adapter over
the existing `migration_imports` table created by migration `0001`.

One import identity is:

`source_path + source_hash + source_type + source_version + legacy_key + target_table`

The ledger:

- requires project-relative source paths;
- requires a valid SHA-256 source hash;
- validates target-table identifiers;
- generates deterministic UUID5 ledger IDs;
- records JSON-serializable details deterministically;
- returns the existing mapping when the same import is repeated;
- raises a conflict if the same source identity is remapped to a different
  target ID;
- treats a changed source hash as a new source identity;
- can list all mappings for a source/path/hash;
- does not commit or roll back on its own, allowing a later importer to create
  target rows and ledger rows in one explicit transaction.

`record_snapshot_import()` connects the scanner and ledger safely: only a
`valid_json` source snapshot can create an import mapping. Empty, missing, or
invalid sources cannot be marked as successfully imported by accident.

## Safety decisions

Fix 3 intentionally does **not**:

- open or populate `data/learning_assistant.db`;
- import any course, topic, assessment, question, note, resource, plan, or grade;
- write scan manifests into the user's data directory;
- scan the Obsidian vault or document library yet;
- reconcile malformed historical values;
- modify migrations `0001` or `0002`;
- switch any application service to SQLite;
- disable legacy JSON writers.

The vault/document scanner and one-idempotent-importer-per-store work remain
later Phase 3 units.

## Verification

Run:

```powershell
.\phase3_fix3_gate.ps1
```

The targeted tests verify:

1. all 12 approved legacy stores are represented;
2. scanner execution leaves source bytes unchanged;
3. repeated scans produce the same manifest hash;
4. zero-byte resources are preserved correctly;
5. optional absent stores are recorded as absent, not failures;
6. invalid/missing required stores and unexpected JSON files are surfaced;
7. portable manifest data contains no physical machine path;
8. identical ledger writes are idempotent;
9. conflicting target mappings are rejected;
10. changed source hashes create distinct import identities;
11. scanner snapshots produce portable ledger identities;
12. invalid snapshots cannot create successful import rows;
13. absolute/machine-specific source paths and malformed hashes are rejected.

The gate also runs all Phase 3 tests, the full regression suite, compilation,
`git diff --check`, and production-DB/private-data tracking checks.
