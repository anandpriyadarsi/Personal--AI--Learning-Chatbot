# Assessment live UX and coding tools — execution plan

**Goal:** Repair the current runner, then add direct Colab access and a focused DSAI teaching surface.

**Spec:** User-supplied `Pasted text(20261001-132122).txt`, Parts A–H. This is an authorized implementation task; no commit or push before Windows validation and subsequent explicit authorization.

**Baseline:** `b8ce54d02be139c5da62f212e682679368fb656a`, branch `anvaya/assessment-live-ux-coding-helper`.

**Architecture:** Existing Flask runner routes and SQLite persistence stay authoritative. Coding Helper adds a stateless provider request through the existing HTTP provider interface, with a separate read-only visible-context projection. Native dialog, semantic controls, scoped CSS, and static operation cards preserve the runner surface.

## Constraints

- No Tutor Scenario D/2.0.1 work, Library work, Planning/Dashboard redesign, Obsidian changes or package-authoring changes.
- No migrations added; all validation uses disposable fixture data.
- No automatic learning/progress/evidence writing from Coding Helper.
- Do not read hidden answers, solution text, marking rubrics or correct options for help.
- No OAuth, notebook editing, Drive synchronization, iframe Colab or code execution.
- Gate A must pass before implementing tools.
- Retain unrelated baseline changes in `backup.py` and `dashboard.py`.

## Task 1 — core repairs

- [x] Verify local/remote branches and locate the current runner.
- [x] Reproduce responsive collapse using actual DOM/computed styles.
- [x] Reproduce Save & Next through native browser, HTTP request, Flask and SQLite.
- [x] Add failing browser regressions, then apply the two minimal fixes.
- [x] Gate A: 137 focused Python tests, 16 browser tests and 10 Node tests pass.

## Task 2 — teaching tools

- [x] Test Colab destination validation, eight actions, hidden-field exclusion and no database writes before implementation.
- [x] Add tools row and native dialog with eight requested modes and explicit progressive hints.
- [x] Add `coding_context(session_id, session_question_id)` using a read-only connection and exact-column SELECT.
- [x] Enforce server-side helper policy using the persisted assessment mode; exam default disabled, optional restricted concepts.
- [x] Build safe `TutorProviderRequest` without orchestration, RAG, memory or grading integration.
- [x] Add 76 compact operation cards, input/output examples and browser-side search.
- [x] Test offline/provider-error states, safe text rendering, dialog focus, Escape, popup isolation and unchanged assessment data.

## Task 3 — final verification and Windows handoff

- [x] Run focused, complete Python, Node, browser and compile checks; report exact counts and environment limitations.
- [x] Obtain an independent review and resolve material findings.
- [x] Check patch application against the exact baseline, including new files.
- [x] Deliver a deterministic Windows handoff with a disposable fixture, existing-environment launch command and manual checklist.
- [x] Leave all changes uncommitted and unpushed.

Final automated result: 157 focused Python tests, 19 real-browser tests and 17 Node tests pass. Full suite: 1,635 passed, 16 failed; the exact same 16 failures reproduce on the untouched baseline because the production database is absent. No production database was created or migrated. Restricted exam topics now use server-validated predefined IDs. Windows visual validation and a live-provider teaching check remain manual acceptance steps.

## Review focus

Native form name collisions; saved sidebar preferences across breakpoints; helper mode tampering; hidden context leakage; dialog controls accidentally submitting the response form; invalid provider output; loss of student code on failure; original attempt expiry and response state unchanged by tools.
