# Coding Helper 2 Implementation Plan

> Execute inline using executing-plans and test-driven-development. Whole-delta
> independent review before commit. User authorized one final feature commit/push.

Goal: UC100N-only guided coding learning without changing assessment answers.
Architecture: persisted projection → centralized policy → validated teaching request
→ existing provider → signed ephemeral context + text-only blocks in modal drawer.
Tech: Python/Flask/SQLite, vanilla JS/CSS, pytest/Node/Playwright.
Spec: ANVAYA_ASSESSMENT_CODING_HELPER_2_DESIGN.md

Global constraints: no production DB, migrations, Tutor changes, schema changes,
learning evidence, main merge, worktree deletion or arbitrary provider HTML.

## Review focus

- Stale course snapshot or reassigned/deleted course: fail closed using live join.
- Permission change with retained history: reject/reset to prevent stale task context.
- Close/reset during slow request: ignore late reply and preserve answer state.
- Code with HTML/long lines/unclosed fence: inert text and contained overflow.
- Empty/malformed request/provider failure: preserve input, no token advancement.

## Task 1: policy (repository/service/routes/template; test_assessment_coding_helper)
- [x] Add course/mode/forgery/live-relationship tests, observe failures.
- [x] Add course_code to narrow projection and runner read model; centralized
  tool_options(context, settings) returns availability and policy; endpoint checks it.
- [x] Adapt existing helper fixtures explicitly to UC100N. Run focused pytest.

## Task 2: teaching and context (assessment_coding_helper, coding_helper_context,
assessment_tools, coding_operations; tests/test_assessment_coding_helper_2.py)
- [x] Add all-mode contracts/depth, signed context and provider boundary regressions.
- [x] Extend actions and grounded catalogue; preserve full solution/exam rules.
- [x] Implement signed continuation with three bounded exchanges/900-second expiry;
  validate before provider, return new token only on success, no persistent writes.
- [x] Add EDA/z-score cards; compile/run examples; run focused Python tests.

## Task 3: UI (helper template/JS/CSS; JS and live browser tests; acceptance script)
- [x] Add failing parser/lifecycle and browser tests for modes/search/reset/visibility.
- [x] Implement text-only blocks, mode hints/depth, copy and card actions, category
  search, guarded abort/reset. Never alter runner response JS or responsive grid.
- [x] Add --course/--mode to disposable Windows fixture. Run JS and browser suites.

## Task 4: release validation and handoff
- [x] Run focused/full pytest, Node tests, compile/syntax and diff checks.
- [x] Independent reviewer inspects entire delta; regress real defects before fixing.
- [x] Document exact baseline/new failure sets and limitations; Windows commands.
- [ ] Commit feature branch, push, verify remote SHA and clean status; leave main.

## Execution ledger

- Baseline main verified by connector and Git fetch: 5916483b7c0e3af165c397faea657ed8bec5dd1d.
- Ruling: preserve legacy CRLF blobs through checkout-local attributes; no unrelated
  normalization. Cost: another fresh clone may need the same local accommodation.
- Ruling: user requires final tested commit, so documentation is included in that
  commit instead of intermediate skill-prescribed commits. No scope expansion.

- Task 1 complete: 46 focused policy tests passed. Assignment uses existing assessment type + practice mode.
- Task 2 complete: expanded helper/fixture suite 97 passed, including all 82 operation examples.
- Task 3 implementation complete; browser and full regression verification in progress.
- Baseline: clean main full suite 1635 passed, 16 failed (missing production DB); browser baseline passed.

- Independent fresh-context read-only reviewer: no critical/important issues; one
  minor stale-error message bypass found in the generation guard. Reproduced both
  Reset and Close failures; removed text-based exception. A current expired-context
  error without that keyword was also reproduced and fixed with explicit handling.
- Close-event timing regression exposed queued native close processing. Invalidate
  synchronously when closing; all four reset/close/expiry/timeout browser regressions
  now pass (2026-10-03 user-local continuation).
- Ruling: user explicitly asks to fix real delta defects, so this minor race was
  fixed rather than deferred. Cost of the original behaviour: confusing old status
  after Reset/Close; no assessment mutation was observed.
- No extra feature scope or unrelated cleanup was added during review.

- Final validation: 1,716 passed + identical 16 baseline failures; zero new failures, errors or skips. Browser 34 passed, JS 20 passed, focused 125 passed. Compile and diff checks passed.
