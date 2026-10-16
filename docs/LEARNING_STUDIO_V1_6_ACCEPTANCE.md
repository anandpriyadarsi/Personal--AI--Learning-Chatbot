# ANVAYA Learning Studio V1.6 — Complete Revision Queue

## Baseline and boundary

- Source baseline: verified V1.5 branch commit `8ba38d296521c9c4b11b024d24906206c15e22ef`, whose Ubuntu/Windows isolated workflow completed successfully (run `38845236875`).
- Integrating against the unchanged `main` merge `aebd8a8828cd4fa452128343882a44b9025aea0d` incorporates both V1.5 and V1.6 source changes.
- This phase changes **only** read-only Learning Studio practice/revision evidence presentation; no academic DB migration, modified source bytes, authored answer keys, official grading, Tutor consumer, Assessment Studio, Planner, Topic Intelligence writer or production-data operation.
- Original private PDF semantic fidelity, teacher intent, visual correctness, historical academic mapping and independent recheck equivalence remain explicitly **unverified**. The queue is low-stakes self-practice, **not** evidence of mastery.

## User-facing improvement

- `/learning/modules/<id>/<revision>/quality?format=html` offers status, original source page, and 20/50/100 item controls.
- Complete authored bank is accessible through next/previous links with readable `X–Y of Z` denominators and ordinary server-rendered links/forms without JavaScript.
- JSON evidence admits the same bounded filters and supplies `pagination`, `filters`, `questions_total`. Summary counts always describe the entire immutable revision regardless of filters or pagination.
- The server rejects unknown, repeated, negative, oversized, out-of-source and malformed filter values; it derives all timestamps and evidence identity, and marks responses `Cache-Control: no-store`.
- Every item continues to link to its original source and exact practice question. Repeated correct answers, a passage of time, teach-back, and questions merely sharing a page never become independent mastery evidence.
- If a page has no matching questions, a clear empty-state message explains how to recover. Mobile filters and keyboard focus are supported.

## Verification and merge gates

1. Run `python scripts/learning_studio_validate.py --scope all --base aebd8a8828cd4fa452128343882a44b9025aea0d --output learning-studio-evidence` on clean Ubuntu and Windows with installed Chromium and pinned `requirements-learning-studio.txt`.
2. Verify V1.6 tests in `test_v16_queue.py` and `test_v16_browser.py`, V1–V1.5 regressions, compilation and unchanged original assessment/tutor files.
3. Preserve baseline-versus-feature test ID accounting and record genuine external private-pilot tests as blocked/skipped if inputs remain unavailable; do **not** convert private skipped tests into passed academic acceptance.
4. Compare the proposed GitHub pull request with main and require successful mergeable status and accepted exact-head checks before merging. Do not modify any production SQLite file or invoke deployment.
5. Installed academic authority and private-source semantic acceptance remain separate operator gates even if the source-only code merges.

## Rollback

Revert the merge commit through Git if any regression appears. This phase is schema-free and reversible without academic-data migration. Keep prior published module revisions and event evidence untouched.
