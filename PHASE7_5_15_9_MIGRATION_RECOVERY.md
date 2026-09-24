# Phase 7.5.15.9 — Historical Migration Source Recovery

Status: VERIFIED RECOVERY  
Branch: `phase7.5.15/notes-studio-rich`

## Problem discovered by the final gate

The read-only Phase 7.5.15.9 production verifier found that the production SQLite database contained an applied migration record that was absent from the current repository source:

- version: `8`
- name: `moodle_sync`
- applied_at: `2026-09-22T13:04:58Z`
- recorded SHA-256: `915903ca7d7845c1d85c0b9ccb149ecff111d2f20fbf7dd7faa4a6b87e7a8e96`

The verifier correctly blocked rather than weakening migration-history validation.

## Recovery evidence

Local Git object history still contained the original migration blob:

`37952ec7145b1cc7e15f7e34fa49e41ae6a7c99d`

for:

`personal_learning_assistant/repositories/sqlite/migrations/0008_moodle_sync.sql`

The historical blob was recovered byte-for-byte.

The user independently verified the recovered file against the production `schema_migrations` row:

- expected SHA-256: `915903ca7d7845c1d85c0b9ccb149ecff111d2f20fbf7dd7faa4a6b87e7a8e96`
- recovered SHA-256: `915903ca7d7845c1d85c0b9ccb149ecff111d2f20fbf7dd7faa4a6b87e7a8e96`
- result: **MATCH = True**

## Recovered migration

The migration creates the historical read-only Moodle connector ledger:

- table `moodle_sync_files`
- index `moodle_sync_files_course_status_ix`
- partial index `moodle_sync_files_local_path_ix`

No migration SQL was reconstructed or invented.

## Reconciliation ruling

Restoring `0008_moodle_sync.sql` is classified as **historical migration-source recovery**.

It is not:

- a new Phase 7.5.15 migration;
- a production database mutation;
- a schema upgrade;
- a Notes Studio authority change;
- a Tutor change.

The production database remains untouched.

## Final-gate requirement

The Phase 7.5.15.9 gate must:

1. allow this single recovered migration source file in the scoped diff;
2. verify its exact SHA-256 against the known production-recorded checksum;
3. continue protecting all migration files from runtime mutation;
4. require the production applied migration history to match current migration source without drift;
5. keep automatic migration disabled.

This recovery closes the migration-history source gap discovered during final reconciliation.
