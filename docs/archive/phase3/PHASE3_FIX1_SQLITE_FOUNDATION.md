# Phase 3.1 Fix 1 — SQLite Connection + Migration Runner Foundation

## Purpose

This is the first implementation unit of **Phase 3 — SQLite and migration tooling**.
It introduces the SQLite infrastructure required for later shadow imports without
cutting any application service over to SQLite.

The Phase 3 safety boundary remains:

> JSON/current files are still authoritative. SQLite is a temporary migration
> target until the Phase 4 structured-domain cutover is explicitly approved.

## Controlled changes

Fix 1 adds:

- `config.DATABASE_PATH` for `data/learning_assistant.db` without import-time I/O;
- `personal_learning_assistant/repositories/sqlite/connection.py`;
- `personal_learning_assistant/repositories/sqlite/migration_runner.py`;
- ordered SQL migrations under `personal_learning_assistant/repositories/sqlite/migrations/`;
- `0001_foundation.sql` for the Phase 3 infrastructure tables;
- targeted regression tests in `tests/test_phase3_sqlite_foundation.py`;
- `phase3_fix1_gate.ps1` for local verification;
- an LF rule for tracked `.sql` source files.

No legacy JSON store, Obsidian note, PDF, semantic index, or application service
is migrated or rewritten by this fix.

## Connection policy

Every explicit SQLite connection configures:

```sql
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
```

The migration runner opens its connection with `synchronous = FULL` for safer
schema migration work.

The helper uses Python's standard-library `sqlite3` module, one connection per
operation, parameterized SQL at call sites, and explicit transactions. It does
not create parent directories and importing the module never opens a database.

## Migration runner guarantees

Migration files use the format:

```text
0001_foundation.sql
0002_next_change.sql
...
```

The runner:

1. requires contiguous versions beginning at `0001`;
2. hashes every migration with SHA-256;
3. records version, name, checksum, and UTC `Z` timestamp in `schema_migrations`;
4. applies each pending migration inside an explicit `BEGIN IMMEDIATE` transaction;
5. rejects an applied migration if its name/checksum later changes;
6. rejects an applied migration that disappears from source;
7. can be rerun safely with no duplicate schema migration rows;
8. requires the caller to provide a database path explicitly.

The runner deliberately does not default to `config.DATABASE_PATH`. During
Phase 3, callers and tests should point it at a temporary database.

## Foundation schema

`0001_foundation.sql` creates only the infrastructure tables required before
legacy data importers are built:

- `schema_migrations`
- `app_settings`
- `migration_imports`
- `operation_journal`
- `outbox_events`

`migration_imports` includes the source path/hash/type/version/legacy key and
target table/ID needed by later idempotent importers. The actual academic domain
schema is intentionally deferred to later Phase 3 units.

## Verification

Run from the repository root on `phase3/sqlite-foundation`:

```powershell
.\phase3_fix1_gate.ps1
```

The gate checks:

1. the targeted Phase 3.1 test module;
2. the complete regression suite;
3. Python compilation;
4. `git diff --check`;
5. that `data/learning_assistant.db`, WAL, and SHM files were not created;
6. that those production database files are not tracked by Git.

The targeted tests verify connection PRAGMAs, commit/rollback behavior,
idempotent migration application, migration checksum drift detection, rollback
of a failed migration, integrity checking, and the absence of import-time
SQLite I/O.

## Non-goals

Fix 1 does **not**:

- create the production `data/learning_assistant.db`;
- import any legacy JSON/vault/document data;
- switch Course/Notes/Resources/Knowledge services to SQLite;
- add academic domain tables;
- add reverse exporters or reconciliation reports;
- change the storage backend setting;
- delete or deprecate any legacy file/module.

Those belong to later Phase 3 and Phase 4 units.
