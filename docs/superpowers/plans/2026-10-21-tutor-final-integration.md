# Tutor final integration implementation plan

**Goal:** Continue PR #32 without restarting the recovered Tutor; make its adaptive state, writes and browser journey trustworthy.
**Spec:** Owner-supplied `ANVAYA_TUTOR_V2_0_TO_V2_3_FINAL_INTEGRATION_MASTER_PROMPT_2026-10-21.md`.
**Execution:** Native implementation in this session. Owner explicitly authorized implementation, testing, push and PR update; no merge/deployment.

## Constraints

- Preserve main `bf3ca0e7` and parallel Architecture V2.4 PR #33. No installed database, private source, provider credentials or academic records used in tests.
- Keep default migrations 0001–0014, optional Assessment 0015 and optional Tutor 0016 separate. Tutor memory remains disabled.
- Only transcript/session/feedback owners may write. Synthetic acceptance cannot certify live A–K.

## Review focus

Explanatory prose misclassified as practice; malformed hidden provider metadata; failed state/turn persistence; replayed feedback; offline matrix rendering losing Markdown or creating unsafe HTML.

## Tasks

- [x] Reproduce baseline Tutor suites; retain original suites and tests unchanged.
- [x] Add failing regressions for practice false positives, malformed evaluation markers and repeated feedback; repair narrowly in Tutor-owned modules.
- [x] Add transactional exchange persistence with rollback and stale-state protection; test injected failures without changing shared SQLite transaction semantics.
- [x] Reuse the existing local bounded math renderer for explicit Tutor math spans; preserve code/student literals and disclose unsupported LaTeX. Verify in real Chromium at 390/768/1366.
- [x] Extend disposable real-service browser acceptance (create, ask, refresh, answer, hint, feedback, invalid CSRF, source review), migration combinations and protected-table checks.
- [ ] Repair native workflow validation and report exact source SHA, environment, test totals, screenshots and full regression results. Push non-forced commits to existing PR.
- [ ] Review engineering/pedagogy/security, recheck main and V2.4, update audit and PR with exact blockers. Only declare merge-ready after every mandatory gate, including live provider, passes.
