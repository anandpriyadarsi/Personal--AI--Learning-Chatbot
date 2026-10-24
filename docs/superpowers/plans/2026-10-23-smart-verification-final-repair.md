# Smart Verification V1.1 final repair plan

Goal: finish existing PR #37 without weakening full acceptance or touching other branches.
Spec: user master prompt, 23 October 2026.

Constraints: synthetic data only; no merge; both OSes at one final source SHA; four private IKS tests stay BLOCKED; preserve merged Tutor and Android work.

- [x] Inspect original Ubuntu artifact, traceback, JUnit and manifest. Root cause is unrelated transient SQLite journal hashing; current main already supplies exact fix and regression tests. Merge current main into existing PR branch and verify 33 focused tests.
- [x] Harden `scripts/smart_verify.py` with tests for missing/deleted selection targets, unknown infrastructure/configuration/native paths and renames. Keep full merge acceptance independent.
- [x] Repair `scripts/verification_benchmark.py`: reject skipped authoritative steps, mismatched run/source identities and malformed timings; expose queue/setup/browser/upload and critical-path evidence when run metadata is supplied. Add failure-first unit coverage.
- [x] Add duration diagnostics and exact-head artifact names to canonical workflow, retaining its OS matrix and exit propagation. Update existing benchmark workflow to collect run metadata.
- [ ] Verify focused Python/JS tests, syntax, full disposable Linux validator; push reviewed changes once ready. Read native Ubuntu/Windows and applicable feature checks at final head.
- [ ] Update PR with original failure, timings and immutable run links; document exact main ruleset settings and external admin blocker. No automatic merge.

Review focus: deleted/renamed code; missing smoke modules; skipped full step; mixed run identities; no status result; transient journal safety and canonical WAL mutation detection.

Ruling: no blanket parallelism or broad fixture caching: existing tests mutate process state and source copies; evidence does not establish isolation. Existing dependency cache retained. No guaranteed full-suite speedup claimed.

Verification before candidate push: 56 focused Python tests PASS; 25 JS tests PASS; compile/whitespace and YAML parsing PASS. Independent final reviewer: no critical/important findings; independently verified 40 selector/benchmark tests and four real historical API snapshots. Native full gates pending.
