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
