# Learning Studio V1.1 implementation and acceptance

V1.1 recovers the real 20-page pilot, completes the remaining navigation fixes and adds a bounded manual review brief. Work resumed from the actual pushed V1 `9ed585ca8e1fbcfb6f5a7e0426d030560109115e` on isolated `feature/learning-studio-v1-1`. Main remains `f859a3c7cdf44baadc17d9bd1a6c656530c1b5bf`. No merge, force push, production academic operation or Tutor change was performed.

## Existing work reused

V1 already supplied the strict package/source importer, versioned immutable derived store, append-only server grading, seven reader views, six-course synthetic volume library, ANVAYA shell/logo/Focus Reading, evidence export and disabled automatic Tutor action. These components were extended; architecture was not rebuilt. V1 CI run38233007085 was verified successful on **both** Ubuntu and Windows.

## Scoped changes and commits

| Pushed commit | Change |
|---|---|
| `6017294ff4f9d241eecc5f32eadd1bdbd63f93b0` | Strict real-candidate acceptance and separate damaged-V3 rejection; real demo keeps one unmapped module. |
| `ef5f72768ec71bee292af2b3affc609b2ea1907c` | Removed-course library bucket; Focus across Contents/views; historical weak anchors; source-verified manual brief; table overflow fix. |
| `bed1eb454696608a059a0b02bdffc948f0c33faa` | V1.1 Ubuntu/Windows workflow, V1 baseline, pinned dependencies and skip accounting. |
| `4298c5ac65a6e3269c39c2a6b6041147150ed0b6` | Independent-review repairs: erased-course Back link, optional semester labels, explicit focus-exit/history/sidebar restoration; missing-case/new-skip validation rejects incomplete evidence. |

Each remote commit tree was compared with its tested local tree before publication. The connected push preserves ancestry and scoped commits; local authored validation history is retained separately because remote commit metadata differs. The final documentation-only tip and its CI are reported in the final handoff/evidence package. Use `git rev-parse HEAD` in the branch checkout for its immutable current tip.

The unavailable bucket preserves historical mapping instead of inventing a course. Focus uses a bounded tab-local session preference plus URL fallback when storage is denied; explicit Exit overrides old focus URLs, and disabled preferences leave global sidebar restoration intact. Contents remains accessible on six desktop/mobile widths. Weak-question links retain the attempted module revision and exact lesson/source/question anchors. Manual briefs include only recorded misses and historical source identity, distinguish uncertain mapping and limited evidence, exclude private keys, and make no provider/session writes.

Independent read-only review found four issues, followed by two repair edge cases. Every finding was repaired with fail-first tests; reviewer confirmed no remaining important findings in the repairs. Source/package validation remains unchanged; no hidden-key leakage, cross-module mix or protected writes were found. Local real-browser tests subsequently passed.

## Acceptance matrix

All code evidence below is at implementation SHA4298c5a/tree943b85e; documentation tip CI is recorded separately. PASS means the stated automated boundary, not semantic/canonical authorization.

| # | Criterion | State | Evidence/limit |
|---|---|---|---|
| 1 | Matching real source +20 previews +31 questions via actual importer | PASS | External recovery/browser tests, recovery.json; private candidate executed locally. |
| 2 | Old inconsistent V3 rejected | PASS | External bad-V3 negative test; unchanged strict checksum rule. |
| 3 | Byte-preserved source and historical citations | PASS | Exact Flask/browser PDF response; source integrity/version/security tests. |
| 4 | Logo/nav/full-width Focus across desktop/mobile navigation | PASS | Browser tests at360/390/768/1024/1366/1920; history, storage denial and collapsed restore regressions. |
| 5 | Compact72-module organization and missing-course fallback | PASS | Synthetic library/UI tests; no real fabricated mappings. |
| 6 | Printable revision/recall/weak flows | PASS | Synthetic and real browser revision/practice/weak assertions. |
| 7 | Durable wrong→correct→reopen/idempotency/version/tamper protection | PASS | Service/web/security/recovery tests. |
| 8 | Read-only evidence/export and truthful Tutor boundary | PASS | Context version/key/GET-purity tests; automatic Tutor disabled; V1.2 handoff specification only. |
| 9 | Startup/GET isolation/integrity and regressions | PARTIAL | Feature75 +focused101 +zero full-suite delta; raw whole suite still16 baseline failures. |
| 10 | Final-tip automated Ubuntu/Windows validation | PARTIAL | CI dispatch enabled; final per-OS conclusions/counts in final acceptance package. Real private pilot is not supplied to public Windows CI. |
| 11 | Protected sources/data/main/Tutor/secrets untouched | PASS | Scoped diff/protected snapshot, source hashes and isolated fixture assertions. |
| 12 | Independent review/tested commit/push/no merge | PASS | Reviewed repairs, green scoped gates, exact pushed tree verification; final tip in handoff. |

Semantic fidelity remains `needs_review` on20 pages. Canonical course/topic mapping remains null. Tutor consumes mistakes **only if a user explicitly copies/pastes** the manual brief; no automatic adapter exists. Those limits do not block the independently safe feature code.

## Validation

Final local scoped suite:76 passed/0 failed/0 skipped, including all four external fixture cases. Focused regressions:101 passed/0 failed/0 skipped. Full unchanged V1:1771 passed/16 failed/0 skipped; V1.1:1791 passed/the identical16 failed/0 skipped. No missing cases/new skips/new failures. Full suite remains RED. An initial comparison showed one extra Assessment browser overflow failure while browser runs overlapped; the final sequential comparison passed with the identical baseline failures. Assessment code/tests were untouched; no assertion or failure was skipped or weakened.

See the recovery, automated-validation and optional Windows handoff reports. No manual Windows layout checklist is required; final CI gaps are reported honestly rather than delegated as screenshots.

## Final Windows timing repair

Documentation SHA2f11d0c passed Ubuntu but Windows failed the1024px Focus navigation test (70passed/1failed/4external skips). Original implementation SHA4298c5a passed both OSes. A deterministic delayed-reader initializer reproduced the immediate assertion reading static HTML before the deferred script restored Focus. Test-only repair uses bounded Playwright assertions for the same exact label and aria-pressed state after DOMContentLoaded; no product code or acceptance requirement changed. A new fail-first deferred-init regression raises scoped count to76, with zero failures/skips locally. Independent review confirmed the navigation-commit/deferred-script boundary and reviewed the test repair. Final pushed SHA/run conclusions are in the acceptance package.
