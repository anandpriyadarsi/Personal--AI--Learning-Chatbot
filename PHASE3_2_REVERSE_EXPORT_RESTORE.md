# Phase 3.2 — Reverse Export, Restore Rehearsal, and Completion Gate

Status: implemented and CI-gated on the Phase 3 SQLite foundation branch.

This completes Phase 3. It does **not** begin Phase 4. Legacy JSON remains authoritative until an explicit Phase 4 cutover decision.

## Scope

Phase 3.2 adds three related safeguards:

1. a reverse export from the Phase 3 SQLite shadow database;
2. a restore rehearsal performed entirely with newly created temporary copies and databases; and
3. a final gate that proves SQLite integrity, foreign-key integrity, migration/import idempotency, structural reconciliation, and source immutability.

The implementation is in
`personal_learning_assistant/migration/reverse_export_restore.py`. It exposes:

- `reverse_export_phase3(...)`
- `rehearse_phase3_restore(...)`
- `run_phase3_completion_gate(...)`

All destinations must be explicit, absent, isolated directories. No function has a default path to `data/`, `knowledge/`, an Obsidian vault, a backup directory, or the future production database.

## Safety contract

The implementation fails closed before writing when any of these conditions is true:

- the supplied SQLite connection uses the production filename `learning_assistant.db`;
- required Phase 3 schema or migration-ledger tables are absent;
- `PRAGMA integrity_check` is not exactly `ok`;
- `PRAGMA foreign_key_check` returns a row;
- an output directory already exists;
- an output path is inside, contains, or traverses a protected source root;
- an output path is under a directory component named `data`, `knowledge`, `obsidian`, `backup`, or `backups`;
- an output path traverses a symlink;
- the output name does not clearly identify a Phase 3/export/restore/rehearsal/temp use;
- any legacy source hash or source SQLite logical state changes during the operation.

Reverse export writes into a unique sibling staging directory and renames it only after every check succeeds. A failed run removes only that uniquely generated staging directory. It never removes or replaces its requested destination.

The restore rehearsal copies reverse-export artifacts into its own new directory. It never points importers at the real legacy source directory.

## Reverse-export contents

A successful reverse export creates:

```text
<isolated-output>/
├── legacy_json/
│   ├── courses.json
│   ├── assessments.json
│   ├── assessment_workspace.json
│   ├── learning_memory.json
│   ├── course_progress_history.json
│   ├── weekly_study_plans.json
│   ├── multi_course_weekly_plans.json
│   ├── intelligent_study_plans.json        # only when imported
│   └── semester_grade_config.json          # only when imported
├── phase3_relational_snapshot.json
└── reverse_export_manifest.json
```

The legacy JSON files are importer-compatible compatibility views. The relational snapshot is the lossless representation of every Phase 3 SQLite table, column definition, row, and logical database fingerprint. The snapshot exists because some normalized SQLite relationships have no exact legacy JSON representation.

The manifest records hashes, byte counts, source versions, record counts, direct source reconciliation, SQLite checks, documented discrepancies, and unmigrated stores. It records portable relative paths only.

## Legacy-equivalent mappings and unavoidable differences

| Legacy source | Reverse-export representation | Deliberately documented difference |
|---|---|---|
| `courses.json` | courses, topics, active course | `document_links` is emitted empty because Phase 3.1 deliberately deferred document-link content; no link is invented |
| `assessments.json` | assessments and ordered raw topic labels | normalized timestamps/aliases may use the canonical importer-compatible form |
| `assessment_workspace.json` | workspaces, questions, topic mappings, attempts, mistakes, and performance | workspace-only aliases/timestamps absent from relational storage cannot be reconstructed |
| `learning_memory.json` | weak/mastered topics, notes, and activity-compatible rows | activity aliases use one canonical compatibility shape |
| `course_progress_history.json` | per-course chronological progress snapshots | scaled relational numerics are emitted as legacy numeric values |
| weekly, multi-course, and intelligent plan stores | plans plus ordered canonical `items` | nested `days`/`sessions` are flattened into an importer-supported canonical item list |
| `semester_grade_config.json` | scale, bands, semester settings, course grades, and recorded result | grade aliases use canonical fields; verification flags are preserved |
| all Phase 3 relational tables | deterministic relational snapshot | tables/columns without a legacy JSON field remain available here without fabrication |

The reconciliation status is `exact` only when parsed source JSON equals the exported structure. Otherwise it is `documented_difference`, with source/export hashes, source/export entity counts, and an explicit reason. A supplied legacy source is read and hashed before and after; it is never rewritten.

These Phase 3.1 exclusions are listed as `not_reverse_exported` because they were not migrated and remain independently authoritative:

- `data/notes.json`
- `data/resources.json`
- `data/obsidian_config.json`

The exporter also never copies or invents Obsidian note bodies, knowledge files, PDFs, vector indexes, credentials, secrets, or other private user content.

## Historical discrepancies are evidence, not repair targets

The completion gate preserves and reports historical evidence instead of silently normalizing it:

- the V9.2 plan that requested 120 minutes but allocated/stored 108 minutes remains 120/108;
- assessment code/schema V2 versus legacy file version 1 remains file version 1;
- learning-memory code/schema V2 versus legacy file version 1 remains file version 1;
- unresolved assessment topic labels remain raw labels rather than guessed topic relationships;
- unverified grade scales remain unverified;
- collision-safe and source-derived identities remain those recorded by the migration ledger.

The reverse export does not rebalance a plan, promote a file version, assert verification, infer missing relationships, or rewrite a source identifier.

## Restore rehearsal

`rehearse_phase3_restore(...)` uses only an isolated, newly created rehearsal directory and performs both required recovery paths:

1. SQLite online backup and restore:
   - creates `phase3_online_backup.db` using `sqlite3.Connection.backup`;
   - validates the backup with `PRAGMA integrity_check` and `PRAGMA foreign_key_check`;
   - restores that backup into `phase3_restored_copy.db`;
   - validates the restored copy and compares deterministic logical fingerprints with the source shadow database.

2. Reverse-export rebuild:
   - copies exported JSON artifacts to `legacy_json_replay/`;
   - creates a fresh `phase3_reverse_reimport.db`;
   - applies migrations once and records versions 1 and 2;
   - applies migrations again and requires no version to run;
   - runs the complete Phase 3.1 importer sequence;
   - runs the same importer sequence again;
   - requires zero writes and an identical relational fingerprint on the second import;
   - runs both SQLite PRAGMAs on the rebuilt database.

The rehearsal verifies export hashes both before and after and requires the original SQLite connection's change count to remain unchanged. Its report contains only relative paths and declares that all work used temporary copies.

## Final Phase 3 completion gate

`run_phase3_completion_gate(...)` runs reverse export and restore rehearsal together. It succeeds only when:

- the source shadow database passes both SQLite PRAGMAs;
- the online backup and restored copy pass both PRAGMAs;
- source, backup, and restored logical fingerprints match;
- schema migration application is idempotent;
- the full reverse-export import sequence is idempotent;
- the rebuilt database passes both PRAGMAs;
- reverse-export hashes remain unchanged during rehearsal;
- all supplied legacy source hashes remain unchanged;
- the source SQLite connection remains unchanged; and
- every structural difference is explicitly represented in reconciliation evidence.

The PowerShell entry point is `phase3_final_gate.ps1`. It runs:

1. focused Phase 3.2 tests;
2. all `tests/test_phase3_*.py` tests;
3. the full pytest regression suite;
4. Python byte-compilation;
5. dependency consistency checks; and
6. `git diff --check` from the required Phase 3 base commit.

It also rejects changes to `backup.py`, `dashboard.py`, `phase3_fix6_gate.ps1`, or `phase3_fix7_gate.ps1`, and rejects tracked Phase 3 export/rehearsal database artifacts or production database side effects.

## Operational example

Use only a known shadow database and fresh temporary paths:

```python
from pathlib import Path

from personal_learning_assistant.migration.reverse_export_restore import (
    run_phase3_completion_gate,
)
from personal_learning_assistant.repositories.sqlite.connection import (
    connect_database,
)

connection = connect_database(Path("temporary") / "phase3-shadow.db")
try:
    result = run_phase3_completion_gate(
        connection,
        Path("temporary") / "phase3-reverse-export",
        Path("temporary") / "phase3-restore-rehearsal",
        legacy_source_directory=Path("temporary") / "legacy-source-copy",
    )
    assert result.status == "pass"
finally:
    connection.close()
```

The example intentionally uses only temporary locations. It is not permission to run against real/private project data.

## Phase boundary

Phase 3 is complete when the final gate and the repository CI validation are green. Phase 4 remains out of scope: no production cutover, authority switch, dual-write removal, legacy-data deletion, or private-data mutation is performed here.
