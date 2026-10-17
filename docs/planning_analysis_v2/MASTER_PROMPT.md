# ANVAYA — Planning & Analysis 2.0: Architecture + Backend Intelligence + Premium Frontend

**Primary execution instruction for ChatGPT Work — 16 October 2026**
**Mission:** Continue actual ANVAYA development, not another audit-only or mockup-only conversation. Turn the existing Planning and Analysis pages into a coherent, evidence-grounded personal academic intelligence and scheduling system. Preserve the recently integrated Learning Studio and Assessment Studio, and prepare a clean boundary for a future Tutor 2.0.

## 0. Repository and exact baseline discipline

- GitHub: `anandpriyadarsi/Personal--AI--Learning-Chatbot`
- Historical observed `main` HEAD on **2026-10-16**: `d3fc9b583be1b5e98cf00960f4b7ad7217526b43` (Assessment dark-theme palette/Resume merge).
- **Treat this SHA only as the starting observation**. Fetch GitHub and prove the current `origin/main` SHA before work; new commits may already exist. The repository and its tests, not screenshots or earlier chat reports, are authoritative.
- Learning Studio through V1.6 and the live Assessment Studio were already merged to main at the time of inspection. Check actual implementation and migrations; do not rebuild them.
- At that inspection, Learning Studio visual refresh **PR #20**, `feature/learning-studio-reader-visual-refresh`, was still open. Preserve it; do not merge, overwrite or import it automatically.
- Topic Intelligence B1/B2 are in main. **B3-A** `anvaya/topic-intelligence-b3-attribution-authority`, separate **Gate C0** `anvaya/gate-c0-synthetic-recovery` (PR #9), and B3 bridge fix PR #13 remain distinct. Verify current state; do not assume these branches were subsequently merged or production-authorized.
- Coding Helper 2.0, Assessment Pause/Resume/paper practice, existing Learning Studio evidence and the ANVAYA dark design language are protected dependencies.

### Mandatory initial commands / evidence

Use a clean isolated Work checkout/worktree; first collect:

```bash
git fetch origin --prune
git worktree list --porcelain
git status --short
git branch --show-current
git rev-parse HEAD
git rev-parse origin/main
git log --oneline --decorate -15 origin/main
git branch -avv
git diff --check
```

Inspect the latest Pull Requests, exact-head CI and protection/rules; do not guess status based on old documents. Capture a concise **verified source and branch ledger**. Inventory installed migrations but do **not** apply one to production. Identify and preserve any dirty checkout. Create a dedicated branch such as `feature/planning-analysis-v2-2026-10-16` from verified current main, in its own worktree. If Work cannot publish to GitHub, finish a complete tested patch and honest handoff; never pretend a push occurred.

## 1. Product definition and scope

The user is a first-year B.Tech student using ANVAYA as a local-first academic companion. Planning and Analysis are the present **top priority**. Existing Learn and Assessment should be relied upon as evidence sources, not rebuilt or redesigned in this task. Their visual refinement is proceeding separately.

Deliver an ANVAYA-quality product, not a template dump:

- **Analysis**: "What happened? Which courses and concepts need work? How strong is the evidence? What has improved? What should I recheck next, and why?"
- **Planning**: "What matters today/this week? What do I already have scheduled? What can fit? What is overdue? Can I preview and deliberately approve changes? What did I accomplish, and how should I adapt the next plan?"
- **Connected workflow**: verified evidence → explainable *read-only* recommendations → editable schedule *proposals* → explicit approval → execution → review and qualified future evidence.
- Both pages must work in **ANVAYA's existing dark theme** and gracefully handle empty/unavailable/partially trusted data. Avoid fabricated grades, AI predictions, unsupported mastery, fake productivity scores and invented class schedules.
- Prioritize a useful local, first-year, one-owner workflow; do not introduce cloud storage, costly providers, a separate planner DB authority or an independent "AI brain".

## 2. Preserve established ownership and evidence trust

Respect these existing owners:

| Authority | Owned facts | Allowed new use |
| --- | --- | --- |
| Assessment Studio | immutable attempt/question snapshots, official evaluated outcomes, grading/rubric and mistake events, approved packages | canonical drilldown; cautiously qualified evidence only |
| Learning Studio | append-only practice/recheck events, immutable module/source/question versions, reading engagement, reviewed mapping snapshots | low-stakes study and recheck signals, **not official grades/mastery** |
| Topic Intelligence B1/B2 | conservative read-only topic/source observations and query-only authority boundaries | reuse only validated contracts; do not infer historical review or independence |
| B3-A and Gate C0 separate branches | prospective provenance/authority checks; synthetic-only recovery simulation | read and reconcile design; **do not promote unmerged code or synthetic decisions** |
| Canonical planner | tasks, calendar commitments, daily agendas, weekly reviews, month-plan imports, assessment scheduling | sole approved writer for planning changes |
| Notes, Knowledge, Obsidian | their own authoritative records | optional read-only indicators, no accidental write/merge |
| Tutor 2.0 | future teaching/orchestration consumers | only an explicit documented bounded handoff, no Tutor implementation |

**Keep four distinct concepts:** (i) observed study activity, (ii) user-reported status/confidence, (iii) evaluated performance and (iv) reviewed source/mapping/independence authority. Never collapse them into one "mastery" score. Retain original IDs, timestamps, source/version locators, denominator, sample size, confidence type and exclusion reason. The absence of evidence must render **Unknown / Not enough evidence**, never `0%`, failure, or arbitrary risk.

For paper subjective self-marks, mark `self-reported`: helpful for reflecting and planning, but **not** independently confirmed assessment evidence. Assisted/hinted practice must not be labelled independent. Never treat exam mode or helper disabled as proof of unaided work. Incorrect-then-correct must remain "recovered / needs independent recheck", not automatically mastered.

## 3. Recover earlier architecture work without repeating it

Read (where available) and reconcile, rather than rewrite from scratch:

- `ANVAYA_PLANNING_AND_LEARNING_INTELLIGENCE_AUDIT.md`
- `ANVAYA_PLANNING_AND_LEARNING_INTELLIGENCE_IMPLEMENTATION_PLAN.md`
- `ANVAYA_ARCHITECTURE_BASELINE_2026_10.md`
- `ANVAYA_TOPIC_INTELLIGENCE_ARCHITECTURE_SPEC.md`
- `ANVAYA_ANALYSIS_2_0_DESIGN.md`
- `ANVAYA_PLANNING_2_0_DESIGN.md`
- `ANVAYA_PLANNING_ANALYSIS_IMPLEMENTATION_PLAN.md`
- B1/B2/B3 authority reports, Gate C0 source and associated validation notes
- live current code, tests and migration inventory

Some documents may exist only in ChatGPT Library or prior Work outputs rather than GitHub. Attempt retrieval if available; if missing, note the omission and proceed from current code. Do not spend the Work session searching indefinitely for archives. Earlier Scenario A (strong topics labelled as recovery), B (preferred future day scheduled too early), C (read-only GET created files), and D (unreliable mapping provenance) must be *re-verified*, not assumed fixed or still broken. Scenario C had a B2 read-safety repair; do not regress it.

### Specific current files to inspect (expand based on imports)

- `personal_learning_assistant/ui/web/routes.py` (GET `/analysis`, `/planning`, `/planning/tasks`, `/planning/day/<date>`, `/planning/review/week/<date>`, month import, calendar, POST routes)
- `ui/web/templates/analysis.html`, `planning.html`, `planning_tasks.html`, `planning_day.html`, `planning_month_plan.html`, `planning_weekly_review.html`, `_planning_operational.html`, `base.html`
- `services/planning_dashboard_service.py`, `home_dashboard_service.py`, `operational_planner_web_service.py`, `operational_calendar_service.py`, `weekly_review_service.py`, `month_plan_import_service.py`, daily agenda and operational task services
- `services/assessment_intelligence_service.py`, `adaptive_academic_loop_service.py`; bounded Learning Studio analysis/evidence projections
- `repositories/sqlite/planner_task_repository.py`, `weekly_review_repository.py`, calendar/agenda/month import/recovery repositories, B1/B2 topic reader and authority router
- `scripts/architecture_validation.py` and the relevant architecture, assessment, learning, planner and Playwright test suites

Observed on the starting code: `/analysis` assembles the home academic summary, Notes, Learning evidence and percentages for bars; `/planning` has a read-only progress-and-legacy-saved-plan section plus separate operational workflows. **Investigate this fragmentation before modifying it.** Some displays use manual topic labels or learner confidence: do not present them as official graded mastery.

## 4. Execution gates — implement as far as safely possible in this session

Do **not** stop after planning or produce only mockups. Work through these gates in dependency order. Each independently safe gate can finish while installed Windows/production authority remains unverified; only block operations genuinely requiring that authority.

### Gate P0 — Rebaseline and fail-first tests (short and bounded)

1. Identify current source of truth for each displayed metric, date, agenda, course/topic, recommendation and review.
2. Reproduce important UI/backend failures on **disposable synthetic fixtures**; capture exact failing IDs. Check archived A/B/C/D and local planner P01–P08 scenarios.
3. Define finite typed response contracts, date/time handling, evidence labels and provenance. Distinguish confirmed, self-reported, unreviewed, unavailable and stale inputs.
4. Run baseline full tests and a real browser sweep; record pre-existing failures and skips precisely. Do not mask baseline failures with arbitrary deselection or blanket `xfail`.
5. Check repository branches for parallel changes and avoid editing shared Studio-owned files where feasible.

### Gate P1 — Shared read model / backend service architecture

Create a **single tested read-side composition** for Planning/Analysis, built from existing authorities, without a second writable topic store. Suggested modular boundary (adapt to existing project conventions):

- `AcademicEvidenceReader` / adapter interfaces: read-only course, assessment, Learning, tasks, calendar and review facts with source IDs and timestamps.
- `AnalysisOverviewService`: validated totals, distinct topic coverage, trends, deadlines, evidence limits and drilldown locators.
- `PlanningOverviewService`: today's agenda, open/overdue tasks, next seven days, outstanding approved items and transparent scheduling capacity.
- `RecommendationProjection`: deterministic, **non-mutating**, bounded hints with `reason_codes`, `source_refs`, policy version, excluded evidence and data freshness. If B3 review/independence is unknown, return "candidate for manual review" rather than auto-eligible recovery.
- `PlanningProposalService` or equivalent **pure preview**: no change to canonical planner until explicit user approval.

Keep old API compatibility where needed and avoid duplicating grading formulas or creating false shared authority. Introduce only justified indexes/contracts, with migration gates below. Provide stable pagination/time-window limits and bounded SQL (avoid N+1, huge in-memory history and unbounded joins). Avoid live model/provider calls for deterministic dashboards.

Requirements for all reads: query-only GET; no file creation; no migration on render; no writes to Learning/Assessment history; no copy of DB/WAL sidecars; safe unavailable/partial state; stable source-backed IDs; UTC storage and configured local timezone presentation; deterministic injected clock; no future leakage. Preserve provenance through DTOs and serialized projections without exposing answer keys or confidential local paths.

### Gate P2 — Analysis 2.0 backend, then rich user-facing page

**Backend**: implement truthful and useful analytics with explicit metric definitions. Target:

1. **Overview:** today's actionable academic situation, overdue deadlines, outstanding assessments, scheduled vs actually recorded effort, courses with limited evidence.
2. **Course breakdown:** course codes/name, syllabus topic coverage, verified assessment performance *where available*, Learning practice/recheck separately, scheduled/actual study, upcoming deadlines. No average percentages across unlike denominators.
3. **Topic insight:** observed question count, evaluated sessions, dates, outcome trend, confidence/provenance categories, known mistaken concepts, first/last observation and independent recheck need. Distinguish reviewed mapping vs unmapped; let user inspect the supporting assessment question/review or exact Learning source lesson without leaking protected solutions pre-attempt.
4. **Learning behavior:** studied/read, remembered/reflected, graded practice, recheck completed/pending; different evidence categories, no inferred retention score.
5. **Assessment trends:** exact scored sessions, date/mode and consistent scales, selected time windows; self-marked papers labelled separately; do not mix them silently with graded tests.
6. **Study efficiency:** realistic completion/planned vs actual using canonical agenda and review data; "not recorded" is not zero effort.
7. **Risk / recovery:** explainable reason, urgency, strength of evidence, conflicting sources, missing mappings and user-facing 'why this?' details. Gate C0 synthetic results never become real recommendations automatically.
8. **Review queue / next action:** source-qualified 'review topic', 'retry question', 'open lesson', 'inspect assessment result', or 'suggest study slot'. No invisible persistence.
9. **Filters:** course, last 7/28/90 days or useful presets, evidence type, topic and date range, all validated server-side; deep links persist selection.
10. **Empty states:** zero assessments, no records, missing DB, stale topic mapping, unknown grade, low sample, paused attempt, and unavailable Learning source remain understandable.

**Frontend**: replace the existing card-and-bars-heavy information dump with a coherent, visually polished Analysis Hub built on existing ANVAYA dark design tokens:

- Clear hero: "Your learning, with evidence" plus *one* prioritized next action.
- Compact useful overview KPIs, readable source labels and tooltips; no decorative percent bars without denominators.
- Well-designed course selector, learning-vs-assessment evidence tabs, topic-priority table/cards, time-series/stacked small charts only where data justifies them, source drilldowns and empty/error states.
- Visual hierarchy, balanced whitespace, typography, legible charts with accessible text equivalents, keyboard/focus paths, loading/error messaging and compact mobile adaptation.
- Prefer SSR Flask/Jinja plus progressive JS, reusable partials and scoped CSS. Avoid a new framework or unnecessary bundle dependencies. If using charts, keep them deterministic, safe and responsive.
- Exact observed evidence in UI; every card must answer "what does this number mean?" and "where did it come from?".

**Integration acceptance**: all routes preserve existing Notes Analysis and Learning Studio read-only component; no baseline analysis data is lost. All GETs proven read-only at logical DB/table level and file/WAL/SHM invariance. Representative cross-source fixtures test conflicting/no-mapping evidence, unknown data and different denominators.

### Gate P3 — Planning 2.0 backend and scheduling intelligence

Implement or repair a single canonical planning workflow using existing task/agenda/calendar/month-import/weekly-review owners:

1. **Today**: upcoming fixed class/assessment commitments, approved agenda sessions, open/overdue items, next feasible work, actual/completed state.
2. **Week**: seven-day capacity and commitments, deadline timeline, workload by course, pending tasks, recovery/recheck proposals and unscheduled work.
3. **Month**: actual calendar and existing approved plan; month YAML import remains preview→hash-check→explicit approval. Do not generate imaginary timetable slots.
4. **Task inbox**: create/edit/status/priority/course/topic/due/preferred day/estimated effort; coherent search/filter/sort/empty states; preserve stable task IDs, external IDs and history.
5. **Time budget**: account for fixed class/assessment events, explicit user-configured free windows, break buffers, timezone, duration estimates, rest/shutdown constraints and realistic daily capacity. Unknown availability must remain "unspecified", not invented.
6. **Placement rules**: **never place a task before its future preferred date**, outside approved windows, after a hard deadline, atop fixed commitments, into the past or beyond capacity; explicitly report unscheduled reason. Handle recurrence, DST/timezone, cross-midnight, duplicate retries and horizon boundaries.
7. **Proposals**: produce explainable, stable/idempotent read-only drafts: what/why/source, suggested slot, alternative or unscheduled reason. User can adjust/accept/reject. Only a deliberate protected POST may write approved tasks/agendas to the existing canonical writer. Preview and opening pages never write.
8. **Carry forward**: visible pending/completed/overdue/dropped differentiation; no silent reschedule. If a task is moved, preserve provenance and link to original identity; do not create duplicates on retry.
9. **Day execution**: approved vs draft vs closed state, mark done, log actual effort, skip or replan with a reason, keep optimistic revisions and race protection.
10. **Weekly review**: planned vs actual, completed/unfinished, what worked/did not, academic evidence and next-week priorities; explicit save/close, revision and correct date boundaries. Do not turn user reflections into measured mastery.
11. **Assessment and Learning deep links**: 'review this topic', 'take retest', 'open exact revision question', but disabled/labelled when source identity or permission is missing.
12. **Recovery recommendation bridge**: read qualified candidates conservatively; an *unreviewed or synthetic* candidate must never auto-create tasks. Explicit approval and canonical persistence only.

Check earlier date defect B and recurrence under real-disposable fixtures before claiming completion. Preserve original installed data and its status history.

### Gate P4 — Planning 2.0 UX/UI implementation

Give `/planning` a serious redesign, not a static mockup and not a list of equal-sized boxes. Make it feel like an academic command center:

- A compact "Today" strip showing the next commitment, realistic free capacity, tasks due and state of the approved agenda.
- A **day/week/month segmented view** with responsive time-grid/timeline where event data exists; clear free/busy availability and click-through details.
- An agenda panel for immediate work; task inbox with course tags and deadlines; visually distinct fixed events, proposals and completed tasks.
- A prioritized queue of actionable recommendations with transparent reasons, limited evidence badges/labels and deliberate "Review / Schedule" controls.
- A review section and weekly reflection flow with actual vs planned comparisons; quick links to Learning and Assessment.
- Preserve the existing month YAML import feature and approvals in an accessible secondary location.
- Reuse ANVAYA dark-theme tokens, sidebar spacing, iconography, typography and components. Use restrained accents, clear labels, consistent rectangles/card densities, polished responsive skeleton/empty/error states, no horizontal overflow. At 390px, current task and next action must remain visible without scrolling past massive banners.
- Native HTML forms and keyboard interactions must remain usable without JavaScript. Use progressive disclosure, proper labels, semantic landmarks, contrast, focus rings, error/live regions and safe CSRF/origin patterns consistent with existing app.
- Do not modify Learning/Assessment visual designs or merge PR #20 as a shortcut. Keep common-shell edits minimal and isolate CSS/JS.

### Gate P5 — Cross-source boundary tests, regression validation and cleanup

Use a **real disposable** SQLite schema migrated from tracked SQL files, synthetic course/assessment/Learning data, source hashes, topic IDs, known absent/uncertain mapping, daily agendas and deadlines. Include tests for:

- A strong assessed topic not classified as urgent recovery from one or zero mistakes;
- Low confidence/unreviewed mapping not promoted; assisted and self-reported work excluded from official metric;
- repeated attempts, duplicate question equivalents, reversed timestamps, same-day evidence, stale revision and missing historical sources;
- 'no data' vs true zero, unknown vs explicit user-stated confidence;
- planned/actual effort and denominator correctness;
- fixed-event overlap, impossible due-date, future preferred date, repeat rules, capacity, timezone and mixed fixed/flexible events;
- idempotent acceptance, 409 stale/duplicate action, rollback on DB failure, partial failure and no auto-write on GET;
- cross-course, SQL, XSS, answer-key leakage and CSRF/origin boundary protections;
- existing assessment palette Pause/Resume, result grading, Coding Helper, Learning Studio reader/rechecks, Notes and B1/B2 exact-source contracts remaining functional;
- disabled/offline JS, browser history, deep links, native forms, mobile menu, print where useful, and accessible focus.

**Required viewports:** 390, 768, 1024, 1366, 1536 and 1920 CSS pixels; include a 360px extreme/narrow check. Verify layout with real headless Chromium, screenshots *and* assertions (not screenshot-only), keyboard paths and visible no-overflow checks.

**Run on Ubuntu and Windows GitHub Actions:** current project's Python/Node, syntax/compile, changed-unit tests, focused integrations, full pytest, Learning Studio browser matrix, Assessment browser regressions, architecture characterizations, Node suite, migration integrity/FK checks, and Git diff/source-manifest checks. Investigate currently conditional browser tests rather than accepting newly introduced skips as a green full gate. Report any pre-existing exceptions separately, with exact IDs and evidence. No blanket `--deselect`, `-k`, `xfail`, `continue-on-error`, reducing test assertions, or simply increasing timeouts without diagnosing resource conditions.

For the architecture runner, use its established CLI, e.g.:

```bash
python scripts/architecture_validation.py --output <new-external-disposable-evidence-directory>
```

Also run the native Learning Studio validation matrix when affected and its assessed/unchanged consumer regressions. If GitHub runners expose a Windows-only fixture/characterization timeout, isolate the test, capture timing + logs, confirm whether it is a real bug or test-harness contention, fix it with a regression, and rerun actual Windows. Do not treat Linux-only green as Windows acceptance.

Use independent reviewers for **(1) data authority/security, (2) scheduling/algorithmic correctness, (3) Learning/Assessment compatibility and (4) UX/accessibility**. Fix high/important findings with RED→GREEN tests; report unresolved findings accurately.

## 5. Gates that require installed Windows/production authority

A synthetic green test is not proof of installed academic data, schema lineage, immutable mapping review, or production readiness. Existing B3-B explicitly remains authority-gated.

- **Do not** access/copy/upload/delete/migrate actual personal SQLite DB/WAL/SHM, Obsidian vault, credentials or local academic records via Work.
- **Do not** allocate a migration number from the synthetic `0014` baseline alone. Read live/parallel migration history and exact installed ledger first. No speculative production schema/ownership changes.
- **Do not** import the B3-B writer or promote Gate C0 synthetic policy into live Analysis/Planning without independently verified lineage and authorization.
- If additional persistence is genuinely required, first determine whether existing canonical task/agenda/review tables suffice. Prefer no-migration read models and pure scheduling prototypes that can be fully tested now.
- If not, create a precise schema-change design and blocked gate; continue fully safe UI/service/test implementation using existing production contracts, feature-isolated disposable adapters or staged preview. Never silently ship a fake production writer.
- Work may request **one** minimal redacted installed-identity/closed-schema authority report from the user's existing `phase7_web.py` Windows environment only if necessary for actual release/migration. It must use documented collector with the real interpreter. A closed copy requires the user to stop ANVAYA and all DB/backup/sync writers and attest no writers. Never ask them to rebuild a separate environment, repeatedly run full suites, upload DB/keys, or manually collect many screenshots.
- Keep per-gate statuses explicit: `DEV VERIFIED`, `SOURCE-ONLY`, `PARTIALLY INTEGRATED`, `BLOCKED BY LOCAL AUTHORITY`, `NOT VERIFIED`, `RELEASE READY` (only if justified).

**Critical:** A production authority blocker must *not* cause Work to stop progress on independent frontend, read-only analytics, deterministic planner proposals or automated tests. Conversely, do not claim a working production Planning/Analysis feature if it is reachable only in a synthetic demo.

## 6. Scope and workflow discipline

- **Act, do not only plan**: brief focused audit → fail-first tests → production-safe implementation → browser/test evidence → independent review → commit/push. The user has approved independent safe design choices; do not ask for trivial design sign-off.
- Preserve user-facing feature compatibility, `main`, installed production data and unrelated feature branches.
- Do not merge to `main`, deploy, run real migrations, modify Tutor 2.0 or alter existing Studio scoring/source histories. The deliverable is a **new tested feature branch and a reviewable PR**, not a premature main update.
- Before opening a PR, compare against fresh main again. Resolve only owned conflicts without deleting parallel work.
- Fix regressions in-scope; do not silently reformat broad unrelated modules or add heavy JS/AI frameworks.
- Focus meaningful work in this order: P0/P1 correctness and data contracts → P2 user-value Analysis → P3 scheduler safety → P4 polished Planning UX → P5 acceptance. Timebox any purely theoretical architecture discussion.
- If time/usage ends, leave verified commits, a worktree-safe state, a resumable checkpoint and the exact next failed/untested acceptance items in GitHub. Do not declare completion if blockers remain.

## 7. Product-specific acceptance scenarios

Prove these end to end with synthetic data:

**S1 — New student / little evidence:** Analysis renders honest empty and limited states; Planning lets the student manually make a task without inventing a grade or syllabus.

**S2 — Real verified weak topic:** A canonical evaluated topic has enough distinct reliable negative observations, displays source counts, explanations and relevant deep links. The student *chooses* to create/review a study proposal; no automatic task creation.

**S3 — Strong topic with one recent mistake:** Does not outrank genuinely weak topics purely because of the most recent wrong answer. Report trend and needed recheck without inventing weakness.

**S4 — Learning recheck after wrong→correct:** Learning evidence supports a recheck recommendation, distinct from official Assessment grade; duplicates and attempts not double counted.

**S5 — Subjective paper self-score:** Analysis labels self-reported, preserves rubric/source references and does not silently mix it into confirmed grade/mastery.

**S6 — Busy Monday:** fixed timetable and an assessment consume all available minutes. A requested 90-minute study task is not double-booked; proposal explains 'no capacity' and shows valid alternatives.

**S7 — Future preferred date:** task cannot be scheduled earlier. Date/time/policy round-trip remains consistent on Windows and Ubuntu.

**S8 — Week replan:** missed task is carried forward only by explicit user acceptance; task identity/history preserved; weekly totals remain accurate.

**S9 — Stale/deleted topic mapping:** no confident canonical topic claim or misleading risk indicator; user can inspect source/resolve mapping through the existing review path.

**S10 — Missing DB / unavailable source:** GET does not initialize data, writes or crash; clear empty/unavailable status. No fabricated zero values.

**S11 — Protected Studios:** Assessment Pause/Resume and Coding Helper still work; Learning module imports, practice and revision history are unchanged; no answer keys leak.

**S12 — Mobile and desktop:** complete real browser journey: Analysis → why-this-topic → approved schedule proposal → Planning day → complete session → weekly review, at 390px and desktop, keyboard accessible and without horizontal overflow.

If authoritative provenance for S2 is not genuinely available, split into verified synthetic demonstration and **blocked production eligibility**, reporting both; do not mark production eligibility pass by pretending historical review exists.

## 8. Deliverables on GitHub and as downloadable artifacts

Create/update and publish in the dedicated feature branch:

1. `docs/planning_analysis_v2/BASELINE_AND_AUTHORITY_MAP.md` — exact SHAs and route→service→repository→authority table, status of old A/B/C/D findings.
2. `docs/planning_analysis_v2/ARCHITECTURE_AND_EVIDENCE_CONTRACT.md` — DTOs/read/write ownership, metric definitions, provenance, negative cases, policy boundaries.
3. `docs/planning_analysis_v2/ANALYSIS_V2_IMPLEMENTATION_REPORT.md` — real changes, screenshots, UI/drilldown, issues and source owners.
4. `docs/planning_analysis_v2/PLANNING_V2_IMPLEMENTATION_REPORT.md` — scheduling algorithm, preview/approval boundaries, date/capacity tests and realistic UI.
5. `docs/planning_analysis_v2/CROSS_PLATFORM_ACCEPTANCE.md` — test IDs/counts, command, exit codes, Ubuntu+Windows runs, skip explanation, fingerprints and baseline delta.
6. `docs/planning_analysis_v2/INDEPENDENT_REVIEWS_AND_FIXES.md` — findings, reproductions and fixes, remaining concerns.
7. `docs/planning_analysis_v2/WINDOWS_MINIMAL_HANDOFF.md` — zero mandatory duplicate manual regression, optional minimal installed authority/smoke only if needed.
8. `docs/planning_analysis_v2/NEXT_PHASE_HANDOFF.md` — precisely remaining blockers for Planner/Analysis, B3-B/real Topic policy and eventual Tutor 2.0.
9. End-to-end browser screenshots, JUnit/pytest/Node logs, manifests and synthetic fixtures in an **accessible private evidence ZIP**, plus a link to the PR and commit. Publish nonprivate summary and exact repro commands on GitHub so missing Work download attachments cannot destroy continuity. Keep private records/assets out of public CI/artifacts.

Final report must show separately:

| Acceptance gate | Exact disposition required |
| --- | --- |
| Main baseline / branch reconciliation | SHA(s), dirty/clean, parallel PR preservation |
| Planning and Analysis read-only source authority | PASS / BLOCKED with evidence |
| Backend and UI implementation | IMPLEMENTED+TESTED / PARTIAL / NOT DONE |
| Analysis user journeys | PASS / FAIL / NOT VERIFIED |
| Planning preview, conflict/date safety and approval | PASS / FAIL / NOT VERIFIED |
| Learning/Assessment compatibility | exact regression results |
| Ubuntu / Windows full & browser | exact runs, counts and skips |
| Installed production schema/provenance | VERIFIED or BLOCKED, never inferred |
| Data preservation | source and logical-before/after evidence |
| Merge/deployment | NOT PERFORMED |
| Next safe phase | exact recommended starting SHA, branch, commands, blockers |

## 9. Final execution directive

**Do the development in this Work conversation.** Do not conclude with only a fresh roadmap, theoretical architecture, or another master prompt. Implement the most substantial safe improvements to *both* Planning and Analysis—backend **and** frontend—subject to verified constraints. Maintain independently safe progress if a production-only gate blocks one integration. Use actual GitHub and real runnable tests. Commit, push and open a **draft or reviewable PR** only after testing and independent review. **Do not merge, deploy or change installed academic data.** Deliver a working synthetic/browser-verifiable product, an honest separation of development vs production readiness, an accessible evidence archive and a concrete handoff for the following phase.
