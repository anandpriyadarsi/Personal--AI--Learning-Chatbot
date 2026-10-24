# Cross-platform acceptance

ANVAYA UI V2 — FEATURE BRANCH READY FOR INTEGRATION: NO

The UI implementation and its focused gates pass. The existing strict architecture gate remains blocked by four external Learning Studio tests whose recovered-pilot/bad-V3 packages are absent. Do not waive or relabel that gate. PR #26 stays draft; no merge, deployment, production authority certification or real data edits occurred.

## Exact tested source

- Published source: `b19ead6d280c9098b53a637222235407ed28889d`; tree `721e365c2e18261451334f51978e1254dba71ca5`.
- Verified main/base: `ce2e4e06175f76778f114a85f7552160aeb08a99` (unchanged when checked on 19 October 2026).
- PR synthetic merge: `3e035c1702700cef670d548c52a53443a46fe02b`; **same tree** `721e365c2e18261451334f51978e1254dba71ca5`. PR and push workflows therefore used identical tracked bytes.
- The report/screenshot head bcee8f0b311c3719cfb605e0b31e730d889efb12 preserved the runtime and test sources above. A later test-only clock repair is described below; application code is still unchanged. The final branch head and its rerun outcomes are recorded in PR #26 and downloadable acceptance-results.json. Counts in the table refer specifically to the linked completed b19-source runs.

## Completed hosted outcomes

| Gate | Ubuntu | Windows | Workflow |
|---|---|---|---|
| Exact-head UI Chromium gate | 106 passed, 0 skipped, 0 failed; 84.26s | 106 passed, 0 skipped, 0 failed; 104.85s | [Push UI V2 run](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/39130013923) |
| Exact-head full pytest | 2501 passed, 4 skipped, 0 failed; 503.83s | 2501 passed, 4 skipped, 0 failed; 1276.95s; 7 warnings | Same push UI run |
| PR UI + full regression | Both steps passed | Both steps passed | [PR UI V2 run](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/39130017584) |
| Assessment preservation | 455 Python + 24 Node passed, 0 skipped/failed | 455 Python + 24 Node passed, 0 skipped/failed; 7 Python warnings | [Assessment matrix](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/39130017557) |
| Strict architecture aggregate | FAIL: full_pytest BLOCKED | FAIL: full_pytest BLOCKED | [Architecture matrix](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/39130017455) |

Workspace JavaScript syntax and whitespace checks passed on both UI jobs. The focused browser gate rejects every skip. Full-suite skips are preserved in JUnit and are not represented as executed coverage.

The architecture artifact was downloaded and inspected on **both** platforms. Each full suite has 2505 cases, exit code 0, no failures or errors, and the same four skips. The validator's explicit zero-skip policy marks this category BLOCKED and exits 1 for the platform aggregate. Its other 14 categories pass: focused54, fixture-order41 in each order, characterization17, headless browser43, Node, pip check/freeze, compilation, synthetic migration fixture, and all four source/diff checks. Existing A/D product-behaviour witness labels remain FAIL in that report; this UI task does not claim to repair or certify those pre-existing architecture behaviours.

## External evidence that is absent

- tests.learning_studio.test_browser::test_external_recovered_pilot_real_browser
- tests.learning_studio.test_pilot::test_external_bad_v3_source_is_rejected
- tests.learning_studio.test_recovered_pilot::test_external_recovered_pilot_strict_import_and_durable_evidence
- tests.learning_studio.test_recovered_pilot::test_external_pilot_demo_does_not_fabricate_course_mappings

The external recovered pilot and bad V3 source are absent. No real-source import/rejection/mapping validation is claimed. Resolving this belongs to the Learning/architecture validation owner using their authorized fixture process; do not add private course material to GitHub or substitute synthetic fixtures while claiming actual-source acceptance.

## Local and independent evidence

Local full run: 2501 passed, 4 explicit skips in 412.41s. Final UI/contract selection: 112 passed, zero skips in 78.15s. Independent protected browser:14 passed; source/sanitizer:60 passed; repaired interaction selection:7 passed; revised Home/launcher fixture selection:6 passed. These selections overlap and must not be summed as distinct product coverage. The archive retains JUnit, logs, manifests and review notes.

The focused browser matrix covers nine redesigned surfaces at 320, 360, 390, 768, 1024, 1366, 1536 and 1920px, plus seven actual protected surfaces at 390/1366. Hosted jobs install pinned dependencies and Chromium in disposable Ubuntu/Windows environments. No manual Windows setup is required. Physical-device Safari and full assistive-technology audits remain unperformed.

## Later Windows timing failure and test-only repair

At report/screenshot head `bcee8f0b311c3719cfb605e0b31e730d889efb12`, [architecture run39185292133](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/39185292133) retained full2501 passes/four external skips on both platforms. Ubuntu headless43 passed, but Windows headless had42 passes/one failure: `test_active_attempt_reopens_after_real_server_restart_with_authoritative_timer` sampled29 seconds after expecting the initial30, then counted down to25 while the assertion retried. Authoritative server expiry/remaining30 and restored-answer checks had passed. This actual failed run is retained in the archive, not replaced by a passing historical result.

The unchanged main test mixed a frozen server fixture clock with an advancing browser monotonic clock. A disposable diagnostic delaying the resumed Page.goto return by1.2 seconds reproduces the failure locally. The test-only repair installs/pauses Playwright's browser clock before resumed navigation, retaining every original saved-response, exact30, expiry and database-dump/static-CSS purity assertion. After that purity check, it revisits the resumed page, advances both fixture/browser clocks by2 seconds, and requires exact browser28, server28 and unchanged expiry. Independent engineering review accepted this ordering; advancing before the purity check was rejected because the existing beforeunload heartbeat correctly records accrued focus.

No Assessment application code, timing policy, scoring, routes, or records changed. No assertion was removed, tolerance widened, skip introduced or retry added. Playwright1.51 was already pinned. The delayed original fails and the repaired case passes; the complete focused/full/hosted rerun outcomes for the final source belong to PR #26 and acceptance-results.json.

Post-repair local verification: full2501 passed/four explicit external skips in404.13s; the UI workflow's expanded focused selection107 passed/zero skips in75.61s; complete architecture headless43 passed/zero skips in57.31s. Artifact-enabled timer capture passed in2.27s. The owned UI workflow adds this existing timer case to its zero-skip selection; no test selection was removed. Final hosted source/results remain governed by the actual PR/artifact records.
