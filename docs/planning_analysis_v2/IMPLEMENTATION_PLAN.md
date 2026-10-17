# Planning & Analysis 2.0 Implementation Plan

**Goal:** Evidence-labelled Analysis and useful canonical Planning with safe previews.
**Spec:** MASTER_PROMPT.md. User explicitly authorizes independent safe design and implementation.
**Architecture:** One read-only AcademicOverviewService reads bounded existing SQLite facts. Existing Learning component and Notes remain owned by their studios. Canonical daily planner owns all approved writes; new composition never writes. Flask/Jinja and scoped CSS, no migration or external model.

## Tasks
- [x] P0: Verify main d3fc9b583be1b5e98cf00960f4b7ad7217526b43, isolate worktree, full baseline and finite contracts.
- [x] P1/P2: tests/test_planning_analysis_v2.py fail-first tests for unavailable DB, unchanged inventory, distinct self/evaluated/pending outcomes, filters, future exclusion and actual effort unknown. Implement services/academic_overview_service.py overview(course='',days=28,evidence='all'). Register read-only hub in existing routes. Preserve source IDs and links, never keys.
- [x] P3: tests/test_planning_v2_scheduler.py fail-first tests for preferred dates, explicit windows, deadlines, clocks, conflicts and recurrence. Repair canonical daily/calendar services without schema changes. Wire explicit configuration through facade.
- [x] P4: analysis.html/planning.html/scoped CSS; honest read model, course/time filters, commitment timeline, task inbox, Notes/Learning and canonical actions. Browser tests for widths 360/390/768/1024/1366/1536/1920, no overflow, keyboard and native forms.
- [x] P5: full regression, architecture and Node suites; cross-platform CI; four independent review domains, important fixes with regressions; branch commit/push/draft PR and accessible evidence.

## Review focus
- Unknown effort stays unknown; draft effort excluded from actual approved workload.
- Self-reported marks and unverified independence cannot become official grades/mastery.
- No future evidence; stable IDs and bounded histories, parameterized filters.
- Unknown availability is not free time; recurrence does not reset COUNT.
- Browser/mobile reading and native action paths preserve existing studio data.

## Execution record
Baseline: fresh clone has historical EOL-only dirty backup.py/dashboard.py; preserved untouched. Dedicated sibling worktree created; no unrelated files to stage. Initial runtime lacked pytest; isolated venv installed from tracked learning requirements. No production data or migration accessed.

Implementation and independent review checkpoints completed; P5 final cross-platform evidence is pending. Checked tasks record work performed, not production acceptance. See the reports for partial gates.
