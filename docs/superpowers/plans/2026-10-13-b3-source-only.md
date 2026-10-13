# B3 source-only implementation plan

> For agentic workers: use executing-plans inline and one independent whole-delta reviewer.

**Goal:** Implement deterministic attribution contracts and reusable authority inspection without live integration or production changes.

**Architecture:** Frozen domain DTOs, query-only repository inspector, existing local collector. B1 remains the closed-artifact observation reader.

**Tech Stack:** Python 3.12, SQLite, pytest, existing Node and Chromium validator.

**Spec:** `docs/superpowers/specs/2026-10-13-b3-source-only.md` and the user-supplied B3 master prompt.

## Global constraints

- Start from verified current main e15c347; dedicated feature branch only.
- No migrations, live integration, academic writes, deployment, main merge or Gate C policy.
- Preserve B1/B2, fourteen migration checksums, signed scoring and full Assessment designs.
- No historical mapping or independence inference; no numeric confidence fabrication.
- Default collector does no DB access; optional closed copy requires attestation and stable complete inventory.

## Review focus

- Malformed/forged control and permission errors must fail closed with redacted fixed codes.
- Nested mutable input, boolean/nonfinite confidence and naive/overflow timestamps must be rejected.
- Unicode equivalent content may share a group; exact case-sensitive canonical IDs must never merge.
- Partial/corrupt/stale projections and conflicting import-ledger links must never produce parity/freshness success.
- Symlink parents/sidecars, writer changes, failed copy disposal and source/copy mismatches must not leak or certify authority.

### Task 1: Authority inspection

Files: `domain/b3_authority.py`, `repositories/sqlite/b3_authority_repository.py`, `tests/test_b3_authority.py`.
Interface: `inspect_authority(connection, *, expected_ledger, backend, control_status) -> B3AuthorityManifest`; connection must already be query-only and in one read transaction. `source_migration_ledger(repo)` returns exact known source tuples.

- [x] Write fail-first real SQLite tests for ledger/schema/FKs, missing controls, all projection states, exact ID parity/import links and query-only/no mutation.
- [x] Run RED; implement frozen states, inspector and source ledger reader; run GREEN.

### Task 2: Attribution composition

Files: `domain/b3_attribution.py`, `tests/test_b3_attribution.py`.
Interface: `compose_attribution(bundle)`, `compose_reviewed_fixture(bundle, reviews=tuple)` return immutable B3 attribution bundles with unchanged observations and separate confidence/provenance.

- [x] Write fail-first tests for historical unknowns, immutable reviewed fixtures pinned to digest/all IDs, time/confidence validation, source/content separation and bridges.
- [x] Run RED; implement strict records/composition; run GREEN with unchanged B1 cases.

### Task 3: Safe collector

Files: existing `scripts/architecture_local_collector.py`, `tests/test_b3_collector.py`.
Consumes Task 1's exact manifest, serialized with enum values and only redacted aggregates. No second helper/authority.

- [x] Write RED tests for default no DB access, malformed controls, parent/sidecar links, complete copied WAL, unstable source, copied-byte mismatch, missing schema, permissions and redaction.
- [x] Implement minimal enhancements; run GREEN plus existing collector cases.

### Task 4: Validation, independent review and delivery

- [ ] Stage reviewed files, run the existing full validator from a fresh external directory; inspect all outputs.
- [x] Independent review of the entire delta; four Important findings reproduced and fixed with RED/GREEN. Final whole-suite validation follows.
- [ ] Commit/push locally green feature only; inspect exact-SHA hosted Ubuntu/Windows artifacts and aggregate.
- [ ] Track five required reports and next-work instructions; final hosted acceptance for delivered tip.
- [ ] Package actual evidence ZIP with hashes, logs/XML/screenshots/review; save accessible artifact and hand off exact boundaries.
