# Phase 7.5.3 — Courses & Topics Web Interface

## Objective

Add a useful, read-only Courses & Topics page to the local Flask interface without changing structured-data authority, storage schemas, migrations, the existing CLI, or any completed Phase 7 work.

Base commit: `1bf256e40cc1a9177561541144f52750f5c34dca` (`feat: add Phase 7.5.2 home academic brief`).

## Scope

Phase 7.5.3 adds one browser read surface over the existing course application service:

- `personal_learning_assistant/services/course_dashboard_service.py`
  - lazily imports `CourseService` and `RoutedCourseRepository` only when the Courses page is requested;
  - calls `CourseService.list_courses()` rather than reading SQLite or JSON directly;
  - converts `CourseView` / `TopicView` objects into a small template-friendly catalogue;
  - computes display-only summary counts and per-course mastery percentage;
  - provides a safe unavailable model for graceful degradation.
- `personal_learning_assistant/ui/web/routes.py`
  - adds a GET-only `/courses` endpoint;
  - supports an injected `COURSE_CATALOGUE_PROVIDER` for focused tests;
  - converts read failures into a safe unavailable page without exposing exception text.
- `personal_learning_assistant/ui/web/templates/base.html`
  - promotes Courses from disabled navigation text to a real link;
  - marks Courses active when the catalogue is open.
- `personal_learning_assistant/ui/web/templates/courses.html`
  - displays course code, name, semester, course status, active-course marker, topic totals, mastery progress, topic status, confidence, and last-updated information;
  - includes meaningful empty and unavailable states;
  - contains no forms or write controls.

The existing Phase 7.5.1/7.5.2 CSS utilities are reused; no new styling dependency is required.

## Data flow

`GET /courses` → web route → `course_dashboard_service.load_course_catalogue()` → `CourseService.list_courses()` → `RoutedCourseRepository.load_state()` → current structured authority.

The route never imports SQLite repositories, legacy JSON modules, or `course_manager` directly. Storage/authority selection remains owned by the existing repository routing layer.

## Safety properties

- `/courses` is GET-only.
- No create/edit/delete/set-active browser action is introduced.
- Web application creation does not eagerly import course engines or structured-authority routing modules.
- The course subsystem is loaded only when `/courses` is requested.
- No direct browser access to SQLite, JSON, Obsidian, retrieval indexes, or authority files is added.
- No migration, authority switch, deprecation, retirement, or deletion occurs.
- Phase 7.1–7.4 and Phase 7.5.1–7.5.2 behavior remains regression-tested.
- Production SQLite, authority control, legacy JSON, and retrieval-index files are hash-checked across the gate.

## Failure behavior

If the course read fails, `/courses` still returns the application shell with a clear “Courses are temporarily unavailable” state. Exception content is logged by type only and is not rendered to the browser. The page explicitly states that academic data was not changed.

## Verification

`phase7_5_fix3_gate.ps1` verifies:

1. focused Phase 7.5.3 Courses/Topics tests;
2. the real existing `CourseService` / routed repository adapter;
3. the real GET-only `/courses` route;
4. Phase 7.5.1 and 7.5.2 regressions;
5. Phase 7.1–7.4 regressions;
6. the complete promotion-aware test suite;
7. Python compilation;
8. dependency consistency plus production SQLite integrity/FK checks;
9. scope, migrations, and completed-phase immutability;
10. Git hygiene plus production/runtime-data immutability.

Do not commit Phase 7.5.3 until the complete gate is green.
