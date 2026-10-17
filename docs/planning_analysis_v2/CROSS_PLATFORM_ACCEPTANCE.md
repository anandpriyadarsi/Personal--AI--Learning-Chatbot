# Cross-platform acceptance

## Validated source

Implemented feature commit: `c0cfcb3d9253cd45219b9d7b51ab9f348aee9c6d` on `feature/planning-analysis-v2-2026-10-16`; draft PR #21. Verified main: `d3fc9b583be1b5e98cf00960f4b7ad7217526b43`.

PR workflows tested synthetic merge `61f91b0221bea635f247db7321876b85aa9a7bea`, with those two parents. Its tree exactly equals the feature tree `55c6b41c9b84ee9eb84f69bf3fb14d1fa1c655cd`. A subsequent documentation-only delivery commit does not change validated runtime, tests or workflows; the following results belong to this precise implementation commit, not to an untested later SHA.

## GitHub-backed results

All counts below are per platform, verified from downloaded XML and workflow metadata.

| Gate | Ubuntu | Windows | GitHub run |
|---|---|---|---|
| Planning/Analysis V2 | 94 passed, zero skips | 94 passed, zero skips | [39020554736](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/39020554736) SUCCESS |
| Native Learning feature | 304 passed, 4 external skips | 304 passed, 4 external skips | same run; native allowed-external count gate PASS |
| Assessment | 455 passed, zero skips | 455 passed, zero skips | [39020556756](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/39020556756) SUCCESS |
| Complete repository | 2370 passed, 4 external skips, zero failures/errors | 2370 passed, 4 external skips, zero failures/errors | [39020556720](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/39020556720) FAILURE: strict zero-skip gate BLOCKED |

Architecture pytest itself exited zero on both platforms; the validator exited one because of the four skips. This is not an all-green architecture acceptance. Each architecture matrix also passed focused54, both order permutations41 each, characterization17, headless-browser43, Node24, dependencies, compilation, synthetic migration/foreign-key integrity and source-diff checks. Assessment JavaScript gates passed. V2 includes 32 real Chromium tests (28 viewport/state checks and four native journeys). Screens cover widths360/390/768/1024/1366/1536/1920; separate no-JavaScript journey captures at390/1366 show proposal, draft, approval, completion with35 actual minutes and weekly review.

Exact jobs: V2 Windows117361688874, Ubuntu117361689101; Assessment Windows117361335459, Ubuntu117361335528, aggregate117362922922; architecture Windows117361335329, Ubuntu117361335493, aggregate117366771608. Full pytest times: Ubuntu445.944s, Windows1452.984s.

## Explicit external skips and remaining product gates

- tests.learning_studio.test_browser::test_external_recovered_pilot_real_browser
- tests.learning_studio.test_pilot::test_external_bad_v3_source_is_rejected
- tests.learning_studio.test_recovered_pilot::test_external_recovered_pilot_strict_import_and_durable_evidence
- tests.learning_studio.test_recovered_pilot::test_external_pilot_demo_does_not_fabricate_course_mappings

These require absent user-owned external pilot assets. There is no new skip, deselection, xfail or weakened assertion. Baseline main had2274 passed,4 skipped,2 failed; the two existing route-layering failures were repaired by moving unchanged Assessment SQL preflight into its service. The final total adds94 tests and fixes those2 failures.

Characterization dispositions: B/C/P01/P02/P04/P05/P07 PASS; A/D/P03/P06/P08 remain documented product-defect witnesses. Passing the characterization tests means their expected dispositions were verified, not that every product defect was fixed. Live-WAL physical invariance, installed B3-B authority, qualified topic recovery, persisted availability and canonical rollover/month-ledger/study-completion gates remain blocked or incomplete. See NEXT_PHASE_HANDOFF.md for precise scenario disposition. No production database, merge or deployment was performed.

## Evidence and provenance

Downloaded artifacts: V2 Windows12097430057 / Ubuntu12097160216; Assessment Windows12096692631 / Ubuntu12096955500; architecture Windows12097357110 / Ubuntu12096827010. Archive includes raw logs/XML, validation manifests, API run/job metadata, merge-tree proof, source-byte comparison, review findings and40 local screenshots with an offline gallery. Full upstream artifacts remain attached to the runs.

Architecture source fingerprints: Ubuntu `aaf1afa3451c7a60d45b857747809f9c4ffe345ca45a50c1a6439622c698bb86`; Windows `fe7265fe2039bfa588150863a14ec0f238ff6755f17712b34c4b9deb678615ab`. All109 differing file hashes match canonical LF/CRLF variants; zero unexplained source differences. Both source checks were clean. Raw fingerprint difference is retained, not hidden.

Independent engineering, compatibility and UX reviews produced fixes and regression tests; the final scheduling reviewer independently reran51 tests and23 absolute-timestamp tests successfully. Earlier authority review was bounded and does not establish comprehensive production authority. Reproduction instructions are in WINDOWS_MINIMAL_HANDOFF.md; duplicate manual Windows regression is unnecessary.
