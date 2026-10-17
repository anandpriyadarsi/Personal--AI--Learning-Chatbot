# Cross-platform acceptance

Validation is in progress. Exact feature SHA, GitHub run/job links, counts, skips and source fingerprints will be appended before handoff. No pending job is treated as pass.

Baseline main `d3fc9b583be1b5e98cf00960f4b7ad7217526b43`, full browser-enabled baseline: 2274 passed, 4 skipped, 2 failed in 309.87s. Failures were architectural layering checks for pre-existing SQL/sqlite imports in web routes, now extracted unchanged to assessment_entry_service. The four missing external fixture cases are:

- tests.learning_studio.test_browser::test_external_recovered_pilot_real_browser
- tests.learning_studio.test_pilot::test_external_bad_v3_source_is_rejected
- tests.learning_studio.test_recovered_pilot::test_external_recovered_pilot_strict_import_and_durable_evidence
- tests.learning_studio.test_recovered_pilot::test_external_pilot_demo_does_not_fabricate_course_mappings

All require user-owned external pilot assets, not tracked built-in fixtures. They remain explicit skips; no deselection, xfail or weakened assertions. Earlier setup run without Chromium is not used as product acceptance.

Local real Chromium checkpoint: 32 passed in 29.76s (28 viewport/state sweeps plus four native action journeys). Later final-source counts replace this checkpoint for acceptance.

Final precommit checks: 126 passed in 42.01s across the five V2 files, characterization and existing planning route suites; subsequently the final shared-priority change passed 51 scheduler/proposal/characterization tests in 8.12s. Exact final-head CI remains required.

## Validation topology

The existing PR architecture workflow runs the complete cross-platform validator (full pytest, all built-in browser suites, focused/order/characterization, Node, compilation, migration integrity and manifests). The existing Assessment workflow runs the isolated Assessment regression and JavaScript gates. The dedicated V2 push matrix runs all five changed V2 test modules and the native Learning feature/browser validator on Ubuntu/Windows. It does not duplicate the full repository matrix already running on the same PR source. Cancellation skips new expensive native work; failed V2 work still retains logs and runs the native compatibility gate. No failed test is suppressed.

Local full core-source run (tree d0932b0c61f430a75f71abdabea5b56696622e14): 2368 passed, 4 external skips, zero failures/errors; full category exit 0 but strict zero-skip gate BLOCKED. Focused54, order41 in each direction, characterization17, headless-browser43 all passed; Node, dependency checks, compile, synthetic migration/FK integrity and source diff checks passed. Validator exits1 because external source-dependent cases remain blocked. Runtime/source fingerprint b0d84e6542d1753d221fac0bd3693812cd0b0304fa3f8349c85e556b8ffbdf03. Native Learning local matrix:304 passed4 allowed external skips; health, count gate, compile and whitespace passed.

Subsequent small actual-effort UI change:37 passed (V2 review regressions plus browser). Subsequent absolute-timestamp fix:23 evidence tests passed; independent reviewer repeated23 passed4.03sec. Final GitHub code head before CI-topology cleanup:9bdc42d67d308aaa84646f89a721ac5de03b7f57. Exact final runs will be recorded below.
