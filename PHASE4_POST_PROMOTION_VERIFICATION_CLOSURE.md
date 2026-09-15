# Phase 4 — Post-Promotion Verification & Closure

## Purpose

This unit closes Phase 4 **after** the real locked SQLite authority promotion has
already succeeded.

It does not perform another migration and does not switch authority. Its job is
to prove that the promoted runtime is internally consistent, routes structured
reads through SQLite, keeps legacy structured JSON frozen, preserves the final
backup, and exposes any deferred review evidence without guessing or repairing
user data.

## Starting point

The expected Git base is:

`b6bb37ebbacc613f795c8c2df792e89218bd2906`

on:

`phase4/structured-cutover`

That commit contains the gate-passing final locked promotion implementation.

The real local runtime is expected to have already completed promotion, so the
following local artifacts are **required runtime state**, not source files:

- `.phase4_authority.json`
- `data/learning_assistant.db`

The following must be absent after successful promotion:

- `.phase4_cutover.lock`
- `.phase4_cutover_work/`

## Authority invariant

Closure requires:

- `storage_backend = sqlite`
- `legacy_writes_blocked = true`
- a non-empty cutover ID
- promotion source-manifest hash evidence
- promotion SQLite SHA-256 evidence

No rollback or second promotion is attempted.

## Read-only verification

`post_promotion_verification.py` performs only reads.

It verifies:

1. the authority-control state is valid SQLite authority;
2. the cutover lock and staging directory are absent;
3. all Phase-4 structured legacy JSON sources still hash to the exact promotion
   manifest;
4. `data/learning_assistant.db` exists as a regular non-symlink file;
5. the immediate closure database bytes still match the promotion-time SHA-256;
6. the repository migration history is exact;
7. `PRAGMA integrity_check` returns `ok`;
8. `PRAGMA foreign_key_check` returns no violations;
9. all nine Phase-4.11 compatibility projections exist and contain JSON objects;
10. the compatibility-seed manifest hash equals the authority source-manifest hash;
11. all nine runtime compatibility routes select SQLite authority;
12. the legacy structured writer guard fails closed;
13. router/read verification changes neither SQLite bytes nor legacy source hashes;
14. the final promotion backup manifest and every listed artifact hash verify;
15. the backed-up SQLite database passes integrity and foreign-key checks;
16. final promotion evidence agrees with the live authority-control state.

The promotion evidence records the boundary database hash as `initial_sqlite_authority_sha256`; closure verifies that field and the nested `new_authority_state.sqlite_sha256` against the live authority-control state.

## Deferred study-plan topic review

Phase 3/4 deliberately refuses to guess unresolved topic foreign keys.

Closure scans the **current promotion source hash** in `migration_imports` for
study-plan items whose raw topic evidence was retained but whose
`target_topic_id` was unresolved.

Those items are reported by source path + legacy key + target ID only. The raw
topic text is intentionally not emitted by the closure report.

An unresolved review item produces `pass_with_review`, not silent success and not
automatic repair. Structural corruption still blocks closure.

## Runtime source-control hygiene

`.gitignore` now explicitly ignores:

- `.phase4_authority.json`
- `.phase4_cutover.lock`
- `.phase4_cutover_work/`
- `PROMOTION_REQUIRES_ATTENTION.json`

The SQLite database/WAL/SHM were already ignored.

These files are local runtime/private state and must never be committed.

## Gate

Run:

```powershell
.\phase4_post_promotion_gate.ps1 -BackupDir "..\phase4-final-backup-2026-09-15"
```

The gate is promotion-aware. It does **not** rerun old gate scripts that were
designed to require absence of production authority artifacts.

It runs:

1. focused post-promotion closure tests;
2. the real read-only post-promotion verifier;
3. Phase 4.11 routing regression;
4. Phase 4.10 command/legacy-guard regression;
5. final locked promotion regression;
6. Phase 4.9 authority-promotion regression;
7. final reconciliation regression;
8. Python compilation + dependency consistency;
9. Git/runtime/private-data hygiene.

## Closure meaning

A green closure gate means:

- SQLite is the live authority for Phase-4 structured state;
- legacy structured JSON is frozen compatibility/backup evidence;
- final backup evidence is verifiable;
- runtime routing and writer guards are active;
- no active cutover lock/work directory remains;
- migration, relational integrity and compatibility projections are intact;
- known deferred references remain explicit and reviewable.

It does **not** migrate Phase-5 domains such as Notes, Resources, Obsidian
registry, document registry, RAG or semantic retrieval.

## Next boundary

After this closure is committed, Phase 4 is complete.

The next architecture unit is Phase 5, beginning with the explicitly deferred
knowledge/notes/resources/Obsidian/document-registry boundary. Phase 5 must not
reinterpret or silently rewrite Phase-4 promotion evidence.
