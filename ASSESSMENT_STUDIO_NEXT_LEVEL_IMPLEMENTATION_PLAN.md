# Assessment Studio Next-Level Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Connect preparation, safe testing, useful results and explicit recovery in one coherent Assessment Studio.

**Architecture:** Add a read-only lifecycle projection and reuse existing mutation services. Refine current surfaces and fix evidenced runner/evaluation defects. Keep schema 0014 and Assessment Package v1.

**Tech Stack:** Existing Python, Flask/Jinja, SQLite, plain JavaScript and CSS; pytest and Node for validation.

**Spec:** `ASSESSMENT_STUDIO_NEXT_LEVEL_SPEC.md`

## Global Constraints

- Baseline `c01e39d14d8945505e8acfa10a0fc2fb7cd2e058`; branch `phase7.5.assessment-studio-ux/next-level`; no main merge.
- No migration, new dependency, package-version change, internal LLM or historical snapshot rewrite.
- No answer material on preparation/library pages; terminal-only result reveal.
- No implicit evaluation confirmation, mastery or planner mutation.
- Preserve all existing advanced capabilities and course identity styles.
- User approval gates were explicitly waived for this implementation. Audit reviewers hit a runtime usage limit; continue inline rather than abandon work.

## Review Focus

- An older autosave completes after a newer edit: final response must retain the latest input.
- Network failure during submit/clear/navigation: user stays with unsaved input and no silent submission.
- Expired active session on a GET library: honest state without any SQLite write.
- More than 100 entries, wildcard search and multiple revisions: complete stable pagination with no hidden-content projection.
- Pending response classified then graded correct: no canonical mistake evidence; form targets use actual returned IDs.

### Task 1: Safe lifecycle read model and workspace

**Files:** new services/assessment_workspace_service.py and repositories/sqlite/assessment_workspace_repository.py; routes.py; assessments.html; assessment_test_library.html; shared assessment navigation/row partials; base.html; static/css/assessment_studio.css; tests/test_assessment_studio_next_level.py.

**Interfaces:** `AssessmentWorkspaceService(database_path, now_fn=None).library(query='', course_id='', kind='', state='', page=1, assessment_id='')` returns safe rows, courses, counts, filters, pagination and continuation. `history(assessment_id, page=1)` returns paged snapshot headers. Routes consume this service via ASSESSMENT_WORKSPACE_SERVICE_FACTORY; default canonical path follows existing builders.

- [ ] Write failing tests for safe projection, missing DB non-creation, zero writes on GET, revision grouping, active/expired/evaluation states, filters and >100-row pagination.
- [ ] Run `python -m pytest -q tests/test_assessment_studio_next_level.py`; expect missing implementation failures.
- [ ] Implement repository parameterized reads, service labels/actions and overview/library route integration. Retain legacy timeline and tools in disclosures.
- [ ] Run new tests and existing A/C/legacy assessment tests; expect pass. Update only deliberately replaced presentation assertions with documented reasons.
- [ ] Commit scoped task files after verification.

### Task 2: Compact blind review and authoring accessibility

**Files:** assessment_import_review.html, assessment_import.html, assessment_review.js, assessment_authoring.js, assessment_studio.css, tests/test_assessment_studio_next_level.py.

**Interfaces:** existing package `review`, `stage_revision`, `approve`, `reject` and handoff remain unchanged. Use safe batch fields only.

- [ ] Add failing route/markup tests: rejected/approved state-specific actions, no hidden snippets, named dialogs, manual prompt fallback, contextual test link.
- [ ] Run focused new cases; expect failure before template changes.
- [ ] Reorganize current review into next action → facts → disclosures. Preserve exact revision upload and strict gate, add reject confirmation and accessible drawer focus.
- [ ] Run blind/simplified/authoring/B regressions and new cases; expect pass.
- [ ] Commit scoped task files.

### Task 3: Reliable exam actions and preflight

**Files:** assessment_runner.js; assessment_test_runner.html; assessment_test_preflight.html; runner service/repository; assessment_studio.css; tests/js/assessment_runner.test.cjs; tests/test_assessment_studio_next_level_runner.py.

**Interfaces:** existing autosave/heartbeat/action/submit endpoints. `preflight` adds safe `marking_groups` only. JS remains plain browser script; test harness executes that actual script.

- [ ] Reproduce unselected True/False, failed save followed by submit/nav, overlapping requests, clear race and hidden focus interval in executable Node tests.
- [ ] Run `node --test tests/js/assessment_runner.test.cjs`; expect regression failures.
- [ ] Serialize saves and require flush success before actions; visible dirty/error/retry state; separate timer announcement; summary confirmation; safe responsive palette. Add aggregate preflight marking metadata.
- [ ] Run JS tests and Phase C/new runner tests; expect pass, with secret-answer checks unchanged.
- [ ] Commit scoped task files.

### Task 4: Focused post-test review and connected recovery

**Files:** evaluation service/repository; assessment_evaluation_results.html; assessment_evaluation_review.html; adaptive service/routes/template; intelligence templates; assessment_studio.css; tests/test_assessment_studio_next_level_results.py.

**Interfaces:** existing `results` snapshot plus pure review selection in service; `response_editor` supplies `evaluation_id`. Adaptive `workspace(course_id='')` returns filtered candidates and saved records; POST redirects carry course_id.

- [ ] Write failing tests for rendered grading action, pending classification guard, correct-outcome canonical exclusion, question filtering/option text/secret active protection and course recovery GET/PRG.
- [ ] Run focused tests; expect failures reproducing audit defects.
- [ ] Implement guards, stable editor ID, one-question review and concise score/outcome next action. Preserve provisional/confirmed boundaries and disclose classification. Connect course recovery/retest without new evidence lineage.
- [ ] Run new results tests and D/E/F regressions; expect pass.
- [ ] Commit scoped task files.

### Task 5: Integrated verification and delivery

**Files:** ASSESSMENT_STUDIO_NEXT_LEVEL_IMPLEMENTATION_REPORT.md, repeatable next-level verification command/script if needed; update this plan's progress.

- [ ] Run compileall and pip check; expect no errors.
- [ ] Run focused Python/Node tests, all Assessment Studio regressions, then broader project suite; record all counts and unavailable production-DB tests.
- [ ] Apply migrations 0001..0014 to a fresh temporary DB; integrity_check must be ok and foreign_key_check empty.
- [ ] Attempt browser rendering; if blocked, verify representative rendered markup and CSS breakpoints, document exact local commands and all required desktop/narrow screens.
- [ ] Review whole diff; fix important findings with regression tests. Run git diff --check with inherited line-ending-only files excluded from staging.
- [ ] Write report with baseline, changes/deferred scope, test evidence, visual limits, exact implementation HEAD and explain that report commit SHA is supplied in final delivery (a file cannot embed its own commit hash).
- [ ] Commit report, push only next-level, verify remote HEAD matches, return concise user report with final SHA. Do not merge.
