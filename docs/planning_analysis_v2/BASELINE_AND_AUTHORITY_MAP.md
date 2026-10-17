# Baseline and authority map

Source baseline: `d3fc9b583be1b5e98cf00960f4b7ad7217526b43` on GitHub main, verified again 2026-10-17. Feature: `feature/planning-analysis-v2-2026-10-16`. A sibling worktree isolates this work. Historical EOL-only checkout differences in backup.py/dashboard.py were excluded from staging. No actual academic DB, vault, private authority document or migration was used.

Parallel development preserved: Learning refresh PR #20 (10cf1b0), B3 bridge PR #13 (36be698), Gate C0 PR #9 (5048dd3); no merge or modification to those branches. Shared base.html/app.css, Studio-owned UI and Tutor were not edited. Reconcile routes.py and __init__.py carefully with the separate frontend branch.

| Route / source | Service | Repository / authority | Disposition |
|---|---|---|---|
| /analysis, /planning evidence | AcademicOverviewService + academic_paper_projection | existing courses, sessions, evaluations, immutable session questions, submitted self-reviews, tasks, approved agenda rows | bounded, query-only, synthetic verified; strict reader refuses WAL |
| Notes on Analysis | existing Notes projection | Notes-owned files and DB | preserved |
| Learning on Analysis | existing learning_analysis_component | Learning Studio store and exact-source contracts | preserved; separate scope |
| Planning timeline | OperationalPlannerWebService → OperationalCalendarService | existing routine/event/task repositories | canonical readers; offset events conservatively block adjacent dates |
| day preview / proposal | DailyAgendaService + planning_proposals | existing planner source tables | deterministic, no writes until protected POST |
| save draft / approve | DailyAgendaService | SQLiteDailyAgendaRepository | canonical transaction, fingerprints, draft→approved only |
| task / month / weekly review | existing services | existing repositories | preserved; known historical limitations below |
| Assessment paper entry preflight | assessment_entry_service | existing Assessment session read | SQL moved out of web routes without grading changes |

## Earlier witnesses

These are scenario dispositions, not a claim to have repaired every architecture defect. The characterization probe now uses a deterministic clock and explicit availability; corrected witnesses assert desired behavior rather than expecting fixed bugs.

| ID | Status in this branch |
|---|---|
| A | Existing Topic automatic evidence-check policy remains a defect witness; new hub does not consume it as eligibility |
| B | DEV VERIFIED: no task before future preferred date |
| C | Existing desired missing-file read safety retained |
| D | Existing missing historical mapping provenance remains blocked; hub labels all mapping unreviewed |
| P01 | DEV VERIFIED: day primary view uses saved items/totals |
| P02 | DEV VERIFIED: task due marker is not a fixed routine / duplicate allocation |
| P03 | Remaining defect: close-day rollover decisions not fully consumed by tomorrow draft |
| P04 | DEV VERIFIED: recurrence COUNT anchored before display window |
| P05 | DEV VERIFIED: recurring events survive original end date |
| P06 | Remaining defect: changed month import can collide with ledger primary key; rollback preserved |
| P07 | DEV VERIFIED: saved study and tasks share timed capacity and deep-work ceiling |
| P08 | Remaining integration defect: legacy study completion does not create engagement / update source study status |

No installed Windows production authority, schema lineage or B3-B mapping approval is inferred from synthetic tests.
