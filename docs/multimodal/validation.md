# Phase 1 verification record — 13 November 2026

Base main: `fea82a2d2d16c9ae8bec8f262da4fb6087e4f21b`; rechecked immediately before integration. Implementation commit `c1ab587` plus the review/hardening changes committed with this report. Remote commit identities may differ when transferred through GitHub's Git-data API; source tree identity is checked on upload.

Platform: Linux x86_64, Python 3.12.14. Exact installed dependency versions and synthetic status latency are in [environment.json](environment.json). No personal stores, professor files, keys, paid calls, model weights or media downloads were used.

## Executed gates

| Gate | Actual result |
|---|---|
| Pinned baseline in separate clean worktree | 76 passed, 3.93 s |
| Final focused regression command below | 284 passed, 53.11 s; zero failed/skipped |
| Additional independent-owner row comparison after ingestion + Tutor answer | 1 passed, 0.52 s |
| Combined real Chromium: new workflow + existing Library + Coding Studio | 22 passed, 98.00 s; zero failed/skipped |
| New workflow browser repeat after final hardening | 5 passed, 25.21 s (same five cases, not added to unique count) |
| Prior Tutor student model/signal/policy/memory subset during privacy fix | 40 passed, 2.20 s (included in the 284 regression set except one overlapping new test) |
| Synthetic 30-case retrieval pilot | 30/30 recall@5; mean returned-hit precision@5 recorded in pilot-results.json; 15/15 absent-query negatives returned no hits |
| `pip check` | No broken requirements |
| `git diff --check` | Clean |
| Activation dry-run/apply/help, backup/restore/integrity, repeated activation, old Native reader | Exercised on temporary owners; missing owners and nested symlinks refused |

The 284 regression run was followed only by an additional test asserting that independent authoritative tables remain byte-for-byte equal as rows across ingestion and a Tutor answer. No production code changed after that run. Unique checks: 285 non-browser + 22 browser = 307. A browser repeat is not counted twice.

Baseline and regression commands (use the verified virtual environment):

```text
python -m pytest -q tests/test_phase5_unified_ingestion.py tests/test_native_document_library.py tests/test_library2_tutor_bridge.py tests/test_phase6_grounded_tutor_engine.py tests/test_phase6_lecture_learning_mode.py

python -m pytest -q tests/test_multimodal_contracts.py tests/test_multimodal_jobs.py tests/test_multimodal_grounding.py tests/test_multimodal_web.py tests/test_multimodal_vision.py tests/test_multimodal_pilot.py tests/test_phase5_unified_ingestion.py tests/test_native_document_library.py tests/test_library2_tutor_bridge.py tests/test_phase6_grounded_tutor_engine.py tests/test_phase6_lecture_learning_mode.py tests/test_tutor_coding.py tests/test_learning_tutor_session_v24.py tests/test_learning_source_links_v24.py tests/test_native_library_routes.py tests/test_library2_legacy_migration.py tests/test_pao_command_boundaries.py tests/test_pao_obsidian_identity.py tests/test_tutor22_student_model.py tests/test_tutor22_signal_aggregation.py tests/test_tutor22_personalized_policy.py tests/test_tutor22_memory_candidates.py

python -m pytest -q tests/test_multimodal_grounding.py::test_multimodal_ingestion_and_answer_leave_independent_owners_unchanged
```

Browser environment: `ANVAYA_BROWSER_TESTS=1`, Playwright 1.51.0 (the repository's pinned optional tooling), Chromium Headless Shell 134.0.6998.35. New tests accept `ANVAYA_CHROMIUM_PATH`; existing Coding fixture accepts `ANVAYA_BROWSER_EXECUTABLE`. This host reused an already installed headless executable because full Chromium requires a Unix socket blocked by the environment. Initial full-Chromium launches failed before app testing; a fresh headless-shell download also failed. Neither failure is represented as a passing check.

```text
ANVAYA_BROWSER_TESTS=1 python -m pytest -q tests/test_multimodal_browser.py tests/test_native_library_browser.py tests/test_tutor_coding_browser.py
```

New browser cases use 320×568, 390×844, 768×1024, 1366×768 and 390×440. They perform the real Flask/SQLite/worker journey: original image → review → queued processing → existing Tutor → saved answer → expand Sources → exact image citation → source change → explicit 410 unavailable. They check horizontal overflow, composer separation and browser errors. Existing Library/Coding cases cover their original journeys. [Mobile screenshot](screenshots/tutor-mobile.png), [desktop screenshot](screenshots/tutor-desktop.png) show synthetic data only.

## Review findings and corrections

An independent reviewer inspected the branch and reproduced three release blockers. All have failing-then-passing regression tests:

1. PDF crop originally exposed full-page embedded text. Text extraction now uses the same normalized crop boundary as the selected image payload.
2. Paid answering used a random dispatch ID and could repeat an unknown outcome. IDs now derive from stable session/request/message/repair identity; a persisted unknown dispatch rejects replay.
3. An old selected session could follow a later generation at the same locator. Selection now pins full original/generation/metadata/artifact/recipe identity and requires reselection.

Additional checks/fixes: selected visual text cannot be republished as legacy text on rename/feature-off; exact citations save with exchange rollback; lost leases cannot write selected artifacts; partial canonical publication is excluded until the matching Native publication receipt completes; source/manifest frames retain exact supplied time in saved evidence; an exact citation streams the verified retained path rather than rereading a potentially replaced placement; private multimodal adaptive summaries are excluded from unrelated later conversations' persistent student models; owner tables outside the explicitly permitted registry/ingestion/Tutor set are unchanged.

## Scope decisions and remaining limits

- Applied the submitted blueprint directly. No additional design approval round was needed: the prompt explicitly authorized implementation of that design.
- Used an additive Native ledger and optional canonical SQL 0020; Native user_version stays 2. No automatic migration on startup/GET, destructive downgrade or cache deletion.
- One selected page/image per job keeps the first useful path bounded. Up to 20 supplied frames can be bound through the manifest API; the completion pass adds up to 20 named frames in the reader form. Ready overlapping frame readings join the selected caption; missing visual coverage is not invented.
- Kept paid extraction/answering disabled by default. No image-capable model ID or rate is silently chosen. The current ledger conservatively accounts the reserved maximum; live usage/cost calibration and actual model quality remain unverified.
- The synthetic retrieval pilot uses a 3-page PDF, five explicitly user-transcribed matrix PNGs and ten supplied timed cues. Its text-only projection gets 10/30, and added modalities get 30/30; it does **not** prove visual transcription or answer correctness. Full handwriting/diagram/model accuracy, the 30-positive/15-adversarial educational-answer benchmark, real lecture timing, broad parser fuzzing and Windows resource containment are not certified by this set.
- Optional C audio/video/ASR deferred. Existing Android, Learning, Assessment, Planning and vault owners were not expanded. No GitHub Actions/Android matrix was dispatched; commits use `[skip ci]` to respect the user's constrained CI budget. Required protections must still be respected.

The release is an opt-in evidence/citation pilot, not a claim of dependable live multimodal teaching quality. Run the documented Windows and bounded live-provider pilot before relying on visual mathematics for academic work.

## Completion pass on PR #77 main

Base `8e577432458ec91c40fa3e861fe286e0830d620c`. Continued A/B without touching the original checkout's unrelated backup.py/dashboard.py edits.

- **228 passed**, zero failures/skips: explicit multimodal contract/job/grounding/web/vision/pilot/validation-command tests, existing ingestion, Native Library/bridge/routes, grounded Tutor, lecture, Coding, Learning handoffs and Tutor title/empty-session lifecycle tests.
- **10 passed**, zero failures/skips: actual Flask/SQLite/Chromium journeys, including mobile/desktop crops, edited-scope invalidation, reload, delayed preview response, multiple named frames, late-start transcripts, matching PDF page and preserved PDF zoom.
- `python -m scripts.multimodal_validate --browser --output <temporary-report>`: 42 unit + 10 browser cases passed (subsets of the counts above). Report explicitly recorded Linux, Python 3.12.14, precommit dirty-tree state, Windows unverified and live-model quality unverified.
- `pip check`, JavaScript syntax checks and `git diff --check` passed.

The independent review reproduced delayed-response consent restoration, wrong-page selection restoration, queued-edit polling and PDF zoom issues. Revision fencing, matching-page restoration, dirty-state gates and wrapper-based zoom corrected them. Browser regression tests cover these paths. Duplicate frame placement IDs within one manifest are rejected to prevent contextual timestamp snapshots from aliasing the same chunk; explicit independent placement copies remain supported.

This closes the one-frame reader limitation and adds bounded crop controls/overlay, matching selection restoration, first-real-cue navigation, readable answering scope and a portable validation command. The original live educational-quality benchmark, actual Windows execution and optional audio/video/ASR limitations remain as documented; offline tests do not certify them. No paid calls, personal-store activation, Android work or manually dispatched CI occurred.
