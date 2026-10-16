# Assessment Pause and Paper implementation plan

> Execute inline using executing-plans, then one independent whole-delta review.

**Goal:** Implement and exercise server-authoritative Pause/Resume and guided paper self-review without implying production schema authority.
**Architecture:** Reuse immutable runner snapshots and answer normalization. A deliberately unregistered candidate service owns execution metadata, atomic commands, receipts and separately typed self-review revisions. Only a standalone disposable fixture app mounts its UI; no production migration is allocated. Legacy writers reject extended attempts.
**Tech stack:** Python, SQLite, Flask/Jinja, native forms, progressive JavaScript, pytest, Chromium.
**Spec:** `ANVAYA_ASSESSMENT_PAUSE_OFFLINE_SUBJECTIVE_SPEC.md`; current 15 October master prompt.

## Global constraints
- Do not modify applied migrations 0001–0014, production data, main or other feature branches.
- Production persistence and full B provenance approval remain BLOCKED pending genuine installed lineage.
- Self-entered marks never enter confirmed grading, mastery, recovery, Tutor or Planner.
- Preserve v1 imports, exact objective scoring, math rendering and Coding Helper 2.0.
- No unconditional heavy workflow; local validation before one final hosted run if available.

## Review focus
- Old readers/writers encountering paused or paper attempts must fail safely.
- Lost acknowledgement/replayed receipts must not replace current state with stale active state.
- Rubric dependencies, alternatives and malformed numeric data must fail closed.
- No solution in initial HTML/state; reveal is deliberate, token-guarded and recorded.
- Partial reviews remain missing, submitted versions immutable, amended history attributable.

## Task 1 — rubric domain
Files: domain/assessment_self_evaluation.py; tests/test_assessment_paper_rubric.py.
- [ ] RED strict structured schema, plain fallback, decimals, dependency/alternative tests.
- [ ] Implement parse_rubric(text, question_id, maximum) and mark_rubric(rubric, payload).
- [ ] GREEN parser/marking tests; preserve existing v1 schema.

## Task 2 — transactional candidate
Files: repositories/sqlite/assessment_execution_repository.py; services/assessment_execution_service.py; scripts/fixtures/assessment_execution_candidate.sql; tests/test_assessment_pause_paper.py.
- [ ] RED clocks/restart/races/replay/expiry/rollback/read-only and paper revision tests.
- [ ] Implement explicit adoption, query-only state, BEGIN IMMEDIATE commands with strict revisions and immutable receipts; reviewed fixture snapshots only.
- [ ] Protect old runner/evaluation entry points from extended attempts.
- [ ] GREEN deterministic transaction tests and compatibility characterization.

## Task 3 — student workspace
Files: ui/web/assessment_execution_candidate.py; templates/assessment_execution_candidate.html; static/js/assessment_execution_candidate.js; static/css/assessment_execution_candidate.css; scripts/assessment_execution_fixture.py; tests/test_assessment_pause_paper_web.py; tests/test_assessment_pause_paper_browser.py.
- [ ] RED route policy/CSRF/projection/browser behaviours.
- [ ] Native forms plus progressive fetch, truthful acknowledgement, same ID, full paper, private guides, self-marking drafts/submit/amend, read-only summary.
- [ ] GREEN Chromium at 390/768/1024/1366/1536/1920 and no-JS/restart/offline paths.

## Task 4 — review, validation and delivery
- [ ] Record baseline and before/after test IDs, run focused/full/Node/compile/diff checks and architecture validator.
- [ ] Independent engineering/security/learning UX review; fix important findings with RED/GREEN evidence.
- [ ] Commit and publish dedicated feature branch; verify remote tree; do not merge.
- [ ] Exact requirement matrix, authority blockers, commands, rollback and evidence archive.

Ruling: Production feature activation is withheld because the committed spec explicitly forbids speculative migration allocation. The disposable candidate is executable implementation, not production acceptance; later integration must replace fixture schema only after lineage/provenance approval.
