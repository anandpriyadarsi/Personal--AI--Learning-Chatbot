# Phase 7.5.5 — Progress & Planning

## Objective

Add a local, read-only `/planning` workspace on top of the Phase 7.5 web shell. The page surfaces existing academic-progress evidence and already-saved study plans without creating snapshots, generating plans, changing topic state, or changing storage authority.

## Read boundaries

The web adapter lazily reads:

- current course identity through `CourseService` + `RoutedCourseRepository`;
- progress/trend and topic-priority evidence through the existing `academic_progress` read functions;
- the latest saved single-course weekly plan through `weekly_planner.get_saved_plans()`;
- the latest saved multi-course plan through `multi_course_planner.latest_plan()`;
- the latest saved intelligent plan through `intelligent_study_planner.latest_plan()`.

No planner/progress engine is imported during normal Flask app creation. Those modules are loaded only when `/planning` is requested.

## Browser surface

`GET /planning` shows:

- average course progress and mastered/weak/not-started totals;
- per-course progress, confidence, historical delta, weak/missing topics;
- up to five existing priority topics with status, score, confidence and reasons;
- read-only summaries of the latest stored weekly, multi-course and intelligent plans;
- normalized saved sessions, dates and minutes when present;
- safe empty and unavailable states.

`POST /planning` is intentionally unsupported.

## Non-goals / safety boundary

Phase 7.5.5 does not:

- call `record_progress_snapshot()`;
- generate any new weekly, multi-course or intelligent plan;
- save or update planner stores;
- change topic status, confidence or mastery;
- write SQLite or legacy JSON;
- modify retrieval indexes;
- add migrations or switch authority;
- modify completed Phase 7.1–7.5.4 implementation files outside the shared route/navigation shell required for this page.

## Files

- `personal_learning_assistant/services/planning_dashboard_service.py`
- `personal_learning_assistant/ui/web/routes.py`
- `personal_learning_assistant/ui/web/templates/base.html`
- `personal_learning_assistant/ui/web/templates/planning.html`
- `tests/test_phase7_5_progress_planning.py`
- `PHASE7_5_FIX5_PROGRESS_PLANNING.md`
- `phase7_5_fix5_gate.ps1`

## Gate

Run:

```powershell
.\phase7_5_fix5_gate.ps1
```

Do not commit until the full gate prints `PHASE 7.5.5 PROGRESS / PLANNING: PASS`.
