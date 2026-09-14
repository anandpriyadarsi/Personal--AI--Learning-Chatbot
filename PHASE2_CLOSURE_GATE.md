# Phase 2 Fix 19 — Closure Gate

## Purpose

This gate is the final verification layer for **Phase 2 — Services over current storage**.

It does **not** add SQLite, perform migration, change the user's academic data, or remove legacy compatibility facades.

The Phase 2 contract is:

> JSON/current files remain the structured authority, service and legacy-compatible behavior remain aligned for preserved cases, and read/query execution does not mutate authoritative files.

## Files added by Fix 19

- `tests/test_phase2_closure_architecture.py`
- `phase2_closure_gate.ps1`
- `PHASE2_CLOSURE_GATE.md`

No production feature module should need to change just to create this gate.

## What the automated architecture test proves

The test verifies that:

1. Core Phase 2 services exist for Courses, Notes, Resources, Knowledge, and Academic Agent routing.
2. Their required repository adapters exist.
3. Required repository protocols exist.
4. Application services do not call `input()` or `print()`.
5. Application services do not import CLI adapters.
6. Application services do not eagerly import optional AI/provider packages.
7. Course service/repository code no longer imports legacy `course_manager`.
8. The Course ↔ Knowledge cycle remains broken.
9. The Academic Agent routing service remains view-neutral.
10. Root compatibility facades remain present.
11. The Phase 2 service/repository layer has not begun SQLite cutover.
12. `data/learning_assistant.db` does not exist yet.

## What the PowerShell gate runs

Run from the repository root:

```powershell
.\phase2_closure_gate.ps1
```

It performs:

1. `pip check`
2. Phase 2 closure architecture tests
3. all tests selected by `-k phase2`
4. all tests marked `read_only`
5. the full regression suite
6. byte-level SHA-256 comparison of every `data/**/*.json` file before/after tests
7. Python compile check
8. V13 startup smoke test
9. `git diff --check`
10. secret/database tracking checks
11. pre-Phase-3 repository readiness checks

## Exit codes

### `0`

**Phase 2 closure: PASS**  
**Pre-Phase-3 readiness: PASS**

The service/current-storage architecture is verified and the repository hygiene checks required before Phase 3 also pass.

### `1`

**Phase 2 closure: BLOCKED**

A required architecture test, regression test, startup test, hash-preservation check, dependency check, or security/authority condition failed.

Do not begin Phase 3. Fix the reported blocker first.

### `2`

**Phase 2 closure: PASS**  
**Pre-Phase-3 readiness: PENDING**

The Phase 2 architecture and tests are green, but one or more repository/release items are not yet proven, such as:

- missing `.gitattributes`;
- missing tracked sanitized JSON fixtures under `tests/fixtures`;
- dirty Git working tree;
- no verified upstream branch.

This is expected on the first run while the Fix 19 files themselves are still uncommitted.

## Important non-goals

A green Fix 19 gate does **not** claim that these later systems are finished:

- SQLite migration;
- stable relational topic/document/assessment IDs;
- Dashboard 2;
- full Academic Agent entity/action execution;
- Notes Studio;
- Resources 2;
- final RAG/knowledge registry;
- full assessment/planner/grade/calendar service cutover;
- final backup/deprecation process.

Those belong to later phases of the modernization roadmap.

## Recommended workflow

1. Add the three Fix 19 files.
2. Run the closure gate.
3. If exit code is `1`, fix the exact Phase 2 blocker and rerun.
4. If exit code is `2`, Phase 2 code closure is green; resolve the listed pre-Phase-3 readiness items.
5. Commit Fix 19.
6. Rerun the gate from a clean working tree.
7. Only when the final output is appropriate for the repository state should Phase 3 SQLite/migration work begin.
