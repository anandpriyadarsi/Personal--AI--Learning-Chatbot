# Phase 7.5.4 — Assessments Web Interface

## Objective

Add a useful, read-only Assessments page to the local Flask interface without changing structured-storage authority, assessment writers, migrations, retrieval state, legacy JSON, or the existing CLI.

Base commit: `d75a54a73a67d3e411b8104c738a72047f35c160` (`feat: add Phase 7.5.3 courses and topics dashboard`).

## Scope

Phase 7.5.4 adds one read boundary for assessment timeline data:

- `personal_learning_assistant/services/assessment_dashboard_service.py`
  - contains no eager assessment/storage imports;
  - reads the assessments compatibility store through the existing Phase 4.11 structured-authority router, falling back to the existing legacy assessment repository only when SQLite is not authoritative;
  - resolves course identity through the existing `CourseService` + `RoutedCourseRepository` read boundary;
  - normalizes assessment type, status, deadline, weightage and linked topic labels for presentation;
  - groups active records into overdue and upcoming, while keeping completed records separate;
  - never invokes an assessment writer.
- `personal_learning_assistant/ui/web/routes.py`
  - adds GET-only `/assessments`;
  - supports an injected assessment provider for focused tests;
  - converts read failures into a safe unavailable state without rendering exception content.
- `personal_learning_assistant/ui/web/templates/base.html`
  - activates the Assessments navigation item.
- `personal_learning_assistant/ui/web/templates/assessments.html`
  - renders summary counts, overdue assessments, upcoming/active assessments and completed assessment history;
  - shows course, type, status, due information, weightage and linked topics where present;
  - contains no form and exposes no browser write surface.

The existing Phase 7.5 CSS primitives are reused; Phase 7.5.4 does not change the stylesheet.

## Assessment compatibility boundary

The repository currently has no canonical `AssessmentService` equivalent to `CourseService`. The live compatibility API in `assignment_exam_assistant.py` routes assessment storage through `maybe_load_sqlite_structured_store`, but importing that root module also pulls unrelated RAG/AI dependencies. Phase 7.5.4 therefore keeps the web adapter at the existing repository authority seam directly: `LegacyJsonAssessmentRepository` supplies the legacy fallback path and `structured_authority_router` selects SQLite only when it is authoritative.

This avoids importing the interactive assignment/exam assistant or optional AI stack simply to render a read-only browser page. The browser route itself still knows nothing about SQLite, JSON paths, or authority files.

## Read model

The web read model exposes:

- total, active, overdue and completed counts;
- assessment ID and title;
- course code/name;
- assessment type and status;
- due date/time and a relative due label;
- weightage percentage when known;
- total/obtained marks when known;
- linked topic labels;
- `overdue`, `upcoming` and `completed` groups.

Completed assessments are never classified as overdue even if their due date is in the past. Missing or invalid due dates remain active/upcoming with the safe label `Date not set`.

## Safety properties

- `/assessments` is GET-only.
- No create/edit/delete/complete action is exposed in the browser.
- Web-app creation does not import assessment storage, SQLite compatibility repositories, the interactive assignment/exam assistant, or course storage engines.
- Storage engines are loaded only when `/assessments` is actually read.
- No SQLite migration is added or modified.
- No storage-authority switch occurs.
- No legacy JSON, production SQLite, retrieval index, or authority-control data is intentionally changed.
- Phase 7.1–7.4 and Phase 7.5.1–7.5.3 remain completed and unchanged except the shared `routes.py` and `base.html` extension required for the new page.

## Failure behavior

If the assessment or course read cannot be completed, the page still returns the local application shell with `Assessments are temporarily unavailable`. Exception content is logged by type only and is not rendered. The page explicitly states that academic data was not changed.

## Verification

`phase7_5_fix4_gate.ps1` verifies:

1. focused Phase 7.5.4 assessment tests;
2. the real authority-routed assessment read adapter;
3. the real GET-only Assessments route;
4. Phase 7.5.1–7.5.3 web regressions;
5. Phase 7.1–7.4 regressions;
6. the complete promotion-aware test suite;
7. Python compilation;
8. dependency consistency and production SQLite integrity/FK checks;
9. scope plus completed-phase/migration immutability;
10. Git diff hygiene and production/runtime-data hash immutability.

Do not commit Phase 7.5.4 until this gate is completely green on the real Windows working tree.
