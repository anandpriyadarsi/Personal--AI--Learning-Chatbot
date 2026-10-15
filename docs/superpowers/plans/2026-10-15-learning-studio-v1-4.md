# Learning Studio V1.4 Implementation Plan

> Execute inline using superpowers:executing-plans and fail-first tests. The supplied master instruction authorizes architecture choices and implementation without another design approval.

**Goal:** Reconcile V1.3 with verified main and close concrete reading, exam revision and content-review gaps.

**Architecture:** Merge main without replacing shared files. Add read-only indexed revision/coverage projections and conservative authoring diagnostics. Reuse immutable Learning Studio storage, grading, manual Tutor producer and local owner boundaries.

**Tech Stack:** Flask/Jinja, SQLite, Python 3.12, pytest, Playwright Chromium.

**Spec:** User-supplied `02_LEARNING_STUDIO_NEXT_WORK_MASTER_PROMPT_2026-10-15.md`, recovered from the identified saved file; no private material is published.

## Global Constraints

- Start from V1.3 `6e520035b6b9ccf8e14c176b35b43e384c95d103`; integrate main `e15c347e5a7bf58c7ec29708eee49b1fed13f712` only here.
- No main merge/deploy, production migration/write, Assessment/Tutor/B3 branch changes, source rewriting, provider calls or automatic Tutor consumer.
- Test synthetic public data. Private source acceptance is separate from public CI.
- Record exact failed test IDs and exit codes. One final reviewed push triggers one Ubuntu/Windows matrix.

## Review Focus

- Equal-valued recall blocks need distinct immutable indices and saved states.
- No-card quick revision must not silently render an unlimited full companion.
- Revision links must preserve lesson/page/question context and disclose coverage omissions.
- Denied browser storage and navigation races must retain usable reading controls.
- Structural diagnostics must not imply semantic or external certification.

### Task 1: Reviewed integration

- [x] Fetch, verify both tips and successful V1.3 hosted jobs; create dedicated worktree from V1.3.
- [x] Merge main without conflicts, inspect shared ownership and commit both parents.
- [x] Run retained non-browser feature baseline (169 passed, 37 explicitly skipped); install missing Chromium before browser acceptance.

### Task 2: Reading and complete revision

**Files:** `learning_studio/reader.py`, `revision.py`, `ui/web/templates/learning_module.html`, new revision-completeness template, scoped CSS/JS, `tests/learning_studio/test_v14_*.py`.

**Interfaces:** `select()` returns indexed `revision_items`, bounded card selection with reasons, coverage omissions, selected related question. Existing `revision_blocks` remains compatible. No persisted schema changes.

- [x] Add fail-first tests for bounded no-card quick mode, duplicate indices, priority reasons and completeness.
- [x] Preserve every full companion block and offer all original lesson concepts in expandable printable supplements; disclose author-reported review and page citations.
- [x] Add one selected original-page preview and one related exercise path in Learn; preserve exact section on source links.
- [x] Verify browser journeys, print/offline loaded notes, key-free preattempt content, durable/indexed self-report and all seven widths.

### Task 3: Preflight and coverage honesty

**Files:** `authoring.py`, new `diagnostics.py`, `coverage_view.py`, coverage template, new domain/route tests.

**Interfaces:** `quality_diagnostics(package)` returns bounded, source-linked warnings, never repairs inputs. Read-only coverage summary separates physical previews/text, page self-review and ledger semantic status.

- [x] Reproduce missing citations/preview/numbering/truncation/material warnings without leaking keys.
- [x] Implement mechanical warnings, explicit unresolved counts and fidelity boundaries; preserve strict hard rejection for malformed/unsafe payloads.
- [x] Verify before/after bytes, new revision history, owner/course limits and protected source diff.

### Task 4: Independent acceptance and delivery

- [x] Separate engineering/security and learner/UX review agents; fix important findings with failing regressions.
- [ ] Run final feature/Chromium, focused regressions, main architecture characterizations and sequential whole-suite comparison against V1.3.
- [ ] Pin new branch-only CI base to V1.3; push reviewed commits once, collect actual exact-SHA Ubuntu/Windows jobs and artifacts.
- [ ] Publish integration audit, implementation/acceptance report and precise next phase in Git. Save a private indexed evidence archive after hosted results.

## Execution ledger

Ruling: use the clean conflict-free merge, preserving both parents, rather than rebase/cherry-pick — reviewable ancestry and no old branch rewrite. Cost if wrong: integration regressions caught by exact-ID delta and main characterizations.

Ruling: preserve the existing package schema; derive priorities from authored misconceptions, explicit revisit, actual misses and review state rather than inventing importance fields. Cost if wrong: priorities remain heuristic and are labelled as such.

Review fixes: concealed diagnostic totals, widget DOM scope, exact revision/source/question context and retained companion test scope were reproduced and fixed. Independent reports and RED/GREEN logs remain in the private evidence archive. No deferred review minors.
