# Phase 7.5.2 — Home / Academic Brief Dashboard

## Objective

Turn the Phase 7.5.1 local Flask Home shell into a useful, read-only academic dashboard without changing storage authority, migration state, retrieval state, legacy data, or the existing CLI.

Base commit: `c61c568d937b8bf7d50e44267e6e9d6ba24a8326` (`feat: add Phase 7.5.1 local web foundation`).

## Scope

Phase 7.5.2 adds one read boundary between the web layer and the existing V12.3 Daily Academic Brief logic:

- `personal_learning_assistant/services/home_dashboard_service.py`
  - lazily imports `daily_academic_brief` only when the Home page is requested;
  - performs no direct SQLite, JSON, Obsidian, retrieval-index, or authority-file access;
  - normalizes the existing brief's deadlines, study blocks, priorities, risk signals, and best-next-action into a template-friendly read model;
  - provides a safe unavailable read model for graceful degradation.
- `personal_learning_assistant/ui/web/routes.py`
  - keeps `/` GET-only;
  - resolves the dashboard through the service boundary;
  - supports an injected read provider for focused testing;
  - converts read failures into a safe degraded Home page without exposing exception content.
- `personal_learning_assistant/ui/web/templates/home.html`
  - renders academic summary metrics, best next action, deadline alerts, today's study blocks, study priorities, and academic risk;
  - includes meaningful empty and unavailable states.
- `personal_learning_assistant/ui/web/static/css/app.css`
  - extends the existing local responsive shell for dashboard cards and lists.

## Compatibility boundary

The current V12.3 Daily Academic Brief exposes its useful read calculations as module functions rather than as a canonical service object. Phase 7.5.2 therefore contains that compatibility dependency inside `home_dashboard_service.py`. The Flask route and Jinja template do not import or call legacy/root academic modules directly.

This is intentionally replaceable: when a later phase introduces a canonical academic-brief service, only the adapter needs to change; the web route/template contract can remain stable.

## Safety properties

- Home remains read-only and GET-only.
- Web application creation does not import Daily Brief, course, assessment, planner, RAG, or optional AI engines.
- Academic engines are loaded lazily only on an actual Home read.
- No browser route writes directly to SQLite or legacy JSON.
- No SQLite migration is added or modified.
- No authority switch, deprecation, retirement, or deletion occurs.
- Phase 7.1–7.4 files remain unchanged.
- Phase 7.5.1 launcher, dependency declaration, health contract, errors, and tests remain unchanged.
- Production SQLite, authority control, legacy JSON, and retrieval-index files are hash-checked across the Phase 7.5.2 gate.

## Failure behavior

If the academic read model cannot be loaded, `/` still returns the local application shell with a clear "Academic brief temporarily unavailable" state. The exception text is not rendered to the browser, and the user is told that academic data was not changed.

## Verification

`phase7_5_fix2_gate.ps1` verifies:

1. focused Phase 7.5.2 tests;
2. the real Daily Academic Brief adapter against the current repository data;
3. the real Home route;
4. Phase 7.5.1 regression tests;
5. Phase 7.1–7.4 regressions;
6. the complete promotion-aware test suite;
7. Python compilation;
8. installed dependency consistency and SQLite integrity/FK checks;
9. scope and completed-Phase-7 immutability;
10. Git diff hygiene plus production/runtime-data immutability.

No Phase 7.5.2 file should be committed until this gate is completely green.
