# Mobile Assessment Two Modes Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement the supplied specification in this session. The owner explicitly requested implementation without another planning handoff.

**Goal:** Two clear Assessment entry cards, mode-specific selection/preflight, shared practice Pause/Resume, and closed-book handwritten rubric review.

**Architecture:** Reuse approved packages, existing runner snapshots, optional extended practice state machine and signed revision-checked POST commands. Read-only navigation context selects CBT or handwritten; fixed-time exams and historical attempts retain their policies. No migration or new academic writer.

**Tech Stack:** Flask/Jinja, SQLite, existing browser JavaScript/CSS, Android WebView/embedded Python.

**Spec:** Owner's `ANVAYA_Mobile_Assessment_Studio_Two_Mode_Redesign_Work_Master_Prompt_2026-10-23.md` supplied 23 October 2026.

## Global Constraints

- Branch from latest observed Mobile #35 head `771868a1f2694b6f58d6584fee993362d68b1942`; draft PR targets `feature/mobile-v1-1-private-android-runtime-2026-10`. Never merge.
- Preserve local runtime, subject restoration, screenshots, scoring, all previous records and private self-assessment authority restrictions.
- Do not invent rubric allocations, admit unsupported papers or start timers through GET.
- Test only disposable synthetic data; never package those records in the app APK.

## Read-only audit

Actual Chromium at 390 px captured before edits in this session. Confirmed combined Pause/Resume promotion, two competing CBT start forms, visible reveal after marking paper attempted, and false synthetic-provenance copy. Legacy `/assessments/sessions/<id>` uses elapsed wall-clock and no Pause. Practice extended player `/assessments/extended/sessions/<id>` uses server active time, revision/receipt transactions and authenticated POST commands. Approved subjective imports pass `inspect_existing_paper` structurally; human grading authority remains unverified. Native SDK/emulator is unavailable locally; existing CI provides API31 build/lifecycle checks.

## Review Focus

- Mode parameter tampering cannot enable handwritten exams or expose answers.
- An existing attempt of another kind must be continued truthfully, never converted.
- Previously revealed guides from active legacy practice remain hidden until completion.
- Paper question position survives pause/restart, including palette navigation.
- Failed/double/stale mutations preserve unsaved work and never imply acknowledgement.

### Task 1: Mode selection and preflight

**Files:** `ui/web/routes.py`, assessment home/library/rows/preflight templates, `assessment_studio.css`, `tests/test_assessment_two_modes.py` (all UI paths under `personal_learning_assistant`).

- [ ] Add failing route tests for two primary cards, mode propagation, eligibility, invalid input, GET immutability and fixed-time exams.
- [ ] Run the new tests and verify expected failures.
- [ ] Implement validated `assessment_mode=cbt|handwritten`, safe eligibility metadata, one start form and practice-default extended execution.
- [ ] Run mode and production-integration regressions, updating obsolete copy assertions only.

### Task 2: Closed-book paper and compact player

**Files:** execution service, candidate routes/template/CSS/JS; same mode tests plus pause/paper regressions.

- [ ] Add failing service tests for active reveal denial and paper position persistence.
- [ ] Require persisted completion before any guide access; preserve historical reviews.
- [ ] Persist paper palette navigation with signed POST; compact palette above readable question; accessible Pause Test/Resume Test, save/next/clear controls and truthful provenance.
- [ ] Exercise partial credit, failure acknowledgement, stale revisions, timeout and restart against real SQLite.

### Task 3: Verification and delivery

**Files:** focused browser regression, Android instrumentation/workflow routing, audit evidence/report.

- [ ] Run real browser dark/light checks at 320,360,390,430,768,1366 and landscape; capture all main flows.
- [ ] Extend real native acceptance to both mode selection and handwritten pause/force-stop/resume.
- [ ] Run Smart Verification where present; otherwise record absence on mandated base, run focused then whole suite and frontend contracts without weakening gates.
- [ ] Commit, push child branch, open stacked draft PR; run exact-head Android/native CI when available. Report executed evidence and unavailable gates separately.
