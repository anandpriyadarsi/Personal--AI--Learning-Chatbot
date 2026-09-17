# ANVAYA Operational Dashboard Design

**Date:** 2026-09-17  
**Status:** Approved design, ready for implementation planning after user review  
**Repository:** `anandpriyadarsi/Personal--AI--Learning-Chatbot`  
**Target branch:** `phase7/deprecation-observation`  
**Starting implementation baseline:** current branch state after Phase 7.5.9 Academic Agent Web Interface (`9019b02` when this design process began)

---

## 1. Purpose

ANVAYA is the presentation and orchestration layer for the Personal AI Learning Assistant project.

The existing project already contains substantial academic functionality: notes, learning resources, Obsidian integration, retrieval and RAG, course management, progress tracking, assessment workflows, planning, grade intelligence, calendar/deadline logic, learning memory, adaptive mentoring, and a persistent tutor. The current web interface exposes only part of that capability and is mainly read-oriented.

This design changes the web product from a passive dashboard into the primary operational interface for daily academic work.

The intended product identity is:

> **ANVAYA — Personal Learning Intelligence**

ANVAYA must feel like an academic operating system with a unified tutor at its centre, not a collection of static web pages and not a browser wrapper around `main.py`.

---

## 2. Problem Statement

The Phase 7.5 web work established a useful browser foundation, but the current experience does not yet satisfy the intended daily-use model.

The existing CLI exposes meaningful actions such as creating/searching notes, adding/updating resources, connecting Obsidian, running planning workflows, managing assessments, inspecting progress, using grade/calendar intelligence, and invoking the Personal Academic Agent. The web UI currently exposes many of these domains only as read-only views.

This produces three problems:

1. **The web UI is less useful than `main.py` for actual work.**
2. **The Academic Agent feels like a separate feature instead of the control surface for the whole system.**
3. **The project contains capable engines, but the user must know which menu/module to open rather than interacting through one coherent product.**

The redesign must solve these problems without discarding the academic engines, storage authority, migrations, tests, or compatibility work already completed.

---

## 3. Approved Product Decisions

The following decisions were explicitly approved during design review and are normative for implementation.

### 3.1 Delivery strategy

Use a **daily-use ANVAYA first** strategy rather than attempting complete CLI parity in one phase.

The first operational product must prioritize:

- unified ANVAYA tutor;
- notes;
- Obsidian;
- resources;
- tasks and calendar;
- study planning;
- assessments;
- knowledge search;
- progress context.

Specialized/admin capabilities such as backup/restore, advanced imports, developer diagnostics, and full legacy-menu parity may follow after the daily-use product is genuinely operational.

### 3.2 Write confirmation policy

Use a three-level action policy:

- **Read actions:** execute immediately.
- **Safe writes:** execute immediately after required fields are known and validated.
- **Important/destructive writes:** require preview and explicit confirmation.

Examples of safe writes include creating a normal note, creating a task, adding an assessment, creating a study block, and marking a task/study session complete.

Examples requiring confirmation include deleting data, overwriting existing Obsidian content, changing an existing assessment deadline, bulk rescheduling, replacing an accepted plan, restoring backups, and other large state changes.

### 3.3 Home experience

Use a **hybrid home screen**:

- upper area: ANVAYA conversation/input and quick actions;
- lower area: today’s schedule, deadlines, priorities, risks, progress, and recommendations.

The home page must not be dominated by statistics or passive reports.

### 3.4 Interaction model

Support both:

- natural-language operations through ANVAYA; and
- normal forms/buttons/pages for structured workflows.

Both paths must call the same application service/command boundary.

### 3.5 Obsidian integration

Use **controlled two-way integration**:

- read/search/retrieve/use Obsidian notes freely when configured;
- allow creation of new Obsidian notes;
- allow the user to choose ANVAYA, Obsidian, or later both as a note destination;
- require confirmation for edits to existing Obsidian files;
- require confirmation for deletions.

### 3.6 Calendar ownership

ANVAYA owns the authoritative academic task/deadline/study schedule locally.

External calendars are optional downstream integrations. External sync must not become the default source of truth for academic planning.

### 3.7 Unified tutor

Use **one unified ANVAYA conversation** for both tutoring and academic operations.

Do not create separate “Tutor” and “Command Agent” personalities or incompatible chat histories.

### 3.8 Memory model

Use layered persistent memory:

- global student memory;
- course-specific learning memory;
- current conversation memory;
- explicit/pinned memory.

Do not permanently store arbitrary chat text as learning memory.

### 3.9 Proactivity

ANVAYA should be proactive inside the application and support optional reminders/notifications later.

It should surface overdue work, upcoming assessments, weak topics, missed blocks, conflicts, and recommended next actions using deterministic academic signals where available.

### 3.10 Grounding policy

Use **source-first tutoring with clearly separated outside knowledge**.

The default should prioritize the user’s own academic materials. If outside/general model knowledge is used, the UI must distinguish it clearly instead of silently mixing it with course sources.

A strict Source Only mode must remain available for exam-oriented or evidence-sensitive use.

---

## 4. Architectural Direction

### 4.1 Core rule

ANVAYA is an orchestration and interaction layer, not a replacement for the academic engines.

The intended dependency direction is:

```text
Browser / ANVAYA UI
        |
        v
ANVAYA web routes / controllers
        |
        v
ANVAYA orchestration + action registry
        |
        v
Application services / command services
        |
        v
Existing academic engines
        |
        v
Repositories / SQLite / files / retrieval indexes
```

The web UI must not calculate academic formulas, mastery, priority, risk, deadline pressure, grade projections, SGPA, or retrieval scores when an authoritative service/engine already owns that logic.

### 4.2 Do not wrap terminal interaction

Web routes must not invoke interactive CLI functions that depend on `input()`/`print()` as the implementation mechanism.

Instead, existing terminal features should be exposed through non-interactive service boundaries.

Correct pattern:

```text
Browser -> route -> application service -> repository/engine
```

Rejected pattern:

```text
Browser -> main.py/menu function -> input()/print()
```

The CLI remains available for debugging, recovery, migration support, and features not yet migrated to the primary interface.

### 4.3 Preserve storage authority

The redesign must respect all existing structured-authority, SQLite cutover, repository, migration, and compatibility boundaries.

Presentation work must not silently introduce a second source of truth.

Every write-capable web feature must go through the appropriate existing or newly defined application service, which in turn uses the established authority-routing/repository layer.

---

## 5. ANVAYA Action Registry

The unified tutor needs a controlled way to invoke project capabilities.

Introduce an ANVAYA action registry rather than allowing the model or route code to directly manipulate repositories or files.

Each action definition must contain, at minimum:

- action name;
- human-readable description;
- validated input schema;
- required context;
- risk level;
- confirmation policy;
- application-service handler;
- result type;
- safe user-facing failure mapping.

Illustrative actions include:

```text
create_note
search_notes
search_obsidian
create_obsidian_note
create_resource
update_resource_status
create_task
complete_task
create_assessment
schedule_study_block
generate_today_plan
generate_week_plan
replan_schedule
search_knowledge
get_course_progress
get_deadlines
get_grade_status
```

The language model may help classify intent and fill structured fields, but it must never receive unrestricted database/file-write authority.

### 5.1 Action safety levels

**READ**

- search notes;
- search Obsidian;
- retrieve knowledge;
- show deadlines;
- show course progress;
- show plan.

Execute immediately.

**SAFE_WRITE**

- create note;
- create resource;
- create task;
- create assessment;
- create study block;
- mark task complete;
- mark study session complete.

Execute after validation without a second confirmation step.

**CONFIRM_WRITE**

- delete data;
- overwrite existing Obsidian files;
- change existing assessment deadlines;
- bulk reschedule;
- replace accepted plans;
- restore backup;
- large automatic state rewrites.

Require a human-readable preview and explicit confirmation.

---

## 6. Unified ANVAYA Tutor

### 6.1 One conversation

The same conversation must support teaching, retrieval, planning, and operations.

Example continuous flow:

```text
User: Explain LU factorization using my notes.
ANVAYA: retrieves sources, explains, cites.

User: Search my Obsidian vault too.
ANVAYA: retrieves relevant vault notes.

User: Save that explanation as a note.
ANVAYA: creates the note through the note service.

User: My quiz is next Monday. Add it and plan revision.
ANVAYA: creates the assessment, then proposes a study plan.
```

The user should not have to restart context in a different chat for operational commands.

### 6.2 Tutor response envelope

Tutor responses should be structured internally so the UI can distinguish:

- main answer;
- source-supported content;
- outside-knowledge content;
- citations/evidence;
- retrieved sources;
- support/confidence state where available;
- suggested follow-up actions;
- proposed system actions.

### 6.3 Source modes

Support visible source modes:

- **Course First** — default; use course-linked user sources first, add outside knowledge only when needed and label it;
- **Source Only** — answer only from selected/indexed user sources; say when evidence is insufficient;
- **All My Knowledge** — allow broader explanation while still identifying user-source evidence separately.

Implementation may map these product modes onto existing source policies where possible, but the UI semantics above are authoritative.

### 6.4 Tutor modes

Existing concept/doubt/summary/exam/lecture/revision/guidance/free capabilities should become behaviour inside one tutor rather than separate products.

Use an **Auto** mode by default, with optional manual mode selection/locking.

### 6.5 Active context

Every relevant tutor request should be able to carry active page context such as:

- active semester;
- active course;
- current object type;
- current object ID;
- current topic;
- current assessment/question/resource/note;
- source mode.

This enables natural requests such as “explain the second example”, “quiz me from this lecture”, or “help me with this question” without repeatedly restating IDs/titles.

---

## 7. Memory Design

### 7.1 Global memory

Store only durable student-level context that materially improves academic assistance, such as stable learning preferences and long-term study goals.

### 7.2 Course memory

Course memory may include:

- weak topics;
- mastered topics;
- recent study activity;
- important learning notes;
- unresolved mistakes/evidence when already represented by existing engines;
- upcoming assessment context when appropriate.

Reuse and extend the existing learning-memory architecture rather than creating an unrelated second memory store.

### 7.3 Conversation memory

Use the persistent tutor session/turn infrastructure for immediate conversational continuity.

### 7.4 Pinned memory

Provide explicit user actions such as “Remember this” / “Pin to memory”. Pinned memory persists until deliberately changed/removed through the product’s memory controls.

### 7.5 Memory admission rule

Do not permanently save arbitrary chat text.

Durable learning memory should come from meaningful events, including:

- explicit user pin;
- weak/mastered status change;
- study-session feedback;
- assessment result;
- recorded mistake;
- completed resource;
- accepted durable preference.

---

## 8. Notes Studio

The first operational Notes milestone must support real work, not only listing.

Required capabilities:

- create note;
- view note;
- search notes;
- edit note;
- archive note;
- filter by course/topic;
- Markdown content;
- readable math/LaTeX rendering in the viewing experience;
- ask ANVAYA about the current note;
- create a note from a tutor conversation;
- choose supported storage destination.

Each note should conceptually support academic context including:

- title;
- course;
- topic;
- content;
- tags;
- source/origin;
- created/updated timestamps;
- storage location.

Metadata enrichment must be introduced through compatible services/migrations rather than breaking legacy note data.

Advanced backlinks, graph views, complex templates, bulk operations, and deep analytics are explicitly deferred until the operational core works.

---

## 9. Obsidian Workspace

Obsidian must be visible as a first-class workspace, not a hidden terminal menu.

Required first operational capabilities:

- connect/change vault;
- validate vault;
- show connection status;
- browse Markdown files;
- search vault notes;
- preview Markdown notes inside ANVAYA;
- use selected Obsidian notes as tutor sources;
- create new Markdown notes in the vault;
- show safe errors when the vault becomes unavailable.

Edits to existing files require a change preview and confirmation.

Deletes require confirmation.

The interface must never silently rewrite user vault content.

---

## 10. Learning Resources Workspace

The Resources workspace must expose operational capabilities already supported by service-layer functionality.

Required first operational capabilities:

- add resource;
- view/list resources;
- search/filter resources;
- update learning status;
- open resource;
- associate resource with course/topic when the model supports it;
- ask ANVAYA about a resource when its content is available to retrieval;
- clearly show indexed/not-indexed or transcript/extraction state when known.

Supported resource categories may include PDF, YouTube, website, book, course, PPT/document, or other existing model-compatible types.

Do not pretend that ANVAYA searched inside a resource when no indexed/extracted content exists.

---

## 11. Unified Academic Search

Provide one product-level search surface that can eventually return typed results across:

- ANVAYA notes;
- Obsidian notes;
- resources;
- indexed PDF/PPT/document content;
- YouTube transcripts;
- courses;
- topics;
- assessments;
- knowledge/retrieval chunks.

Each result must identify its origin and expose context-appropriate actions such as:

- Open;
- Ask ANVAYA;
- Use as source.

Search implementation may be delivered incrementally, but the product contract is one coherent search experience rather than several unrelated search menus.

---

## 12. Tasks

Introduce a real daily-use task concept that planning and calendar workflows can understand.

A task should conceptually support:

- title;
- course;
- topic;
- type;
- due date/time;
- estimated duration;
- priority;
- status;
- source/origin;
- links to relevant assessment/resource/note when available.

Required first milestone operations:

- create;
- view;
- complete;
- reschedule;
- query through ANVAYA.

Task creation must work from both structured forms and natural language through the same command boundary.

---

## 13. Academic Calendar

Separate Calendar from Grades in the primary navigation.

Required product views:

- Today;
- Week;
- Month;
- Agenda.

The calendar should be able to show typed academic items such as:

- assessment deadlines;
- study blocks;
- tasks;
- submissions;
- academic events;
- later optional class/lecture events where supported.

The calendar must support creating at least:

- task;
- assessment;
- study block.

ANVAYA remains the local source of truth. External calendar integration is deferred to a later optional sync/export feature.

---

## 14. Study Planning

The current project has several planners. ANVAYA should present them through a simpler user model rather than exposing every engine as a separate menu.

Primary planning intents:

- **Today** — realistic current-day plan;
- **Week** — balanced seven-day plan;
- **Recovery/Replan** — adapt after missed tasks/blocks or changed constraints.

Plans should consider deterministic academic signals already available, such as deadlines, assessment weightage, weak topics, progress, priorities, existing work, and stored study plans.

Generated plans must be previewable.

A plan that materially replaces or bulk-changes an accepted schedule requires confirmation.

Study blocks should support:

- Start Session;
- Complete;
- Reschedule;
- Skip;
- Ask ANVAYA.

Completing a study session should allow learning feedback such as:

- Understood well;
- Need more practice;
- Still confused.

That feedback may update existing learning-memory/progress evidence through the appropriate service boundary.

---

## 15. Assessments

The Assessments workspace must evolve from read-only catalogue to active preparation workspace.

Required first milestone operations:

- create assessment;
- view assessment;
- set course/type/title;
- set due date/time;
- set weightage when known;
- associate topics;
- query/create through ANVAYA;
- open an assessment preparation workspace.

Assessment workspace should converge relevant existing capabilities rather than exposing many unrelated menus.

It should progressively bring together:

- topics;
- tracked questions;
- question sources;
- automatic topic mapping;
- source-grounded help;
- mistakes/performance evidence;
- assignment file import;
- preparation plan;
- linked notes/resources.

The first operational milestone does not require every advanced assessment subsystem to be writable in the browser, but the workspace architecture must provide a coherent home for them.

---

## 16. Proactive Academic Intelligence

ANVAYA should proactively surface useful signals inside Home and relevant workspaces.

Examples:

- deadline approaching;
- task overdue;
- assessment risk increased;
- missed study block;
- plan conflict;
- weak topic near an assessment;
- unfinished high-priority resource;
- best next action.

Where deterministic academic engines already calculate priority, risk, progress, deadline pressure, or mentor actions, ANVAYA must consume those structured signals rather than asking an LLM to invent priorities.

The language model may explain or summarize the signal, but should not replace authoritative deterministic calculations.

Optional OS/external notifications are deferred; routine recommendations should initially remain inside ANVAYA.

---

## 17. Product Shell and Information Architecture

### 17.1 Visible identity

Use:

> **ANVAYA**  
> **Personal Learning Intelligence**

Do not rename stable internal Python packages, classes, migrations, database tables, or compatibility modules purely for branding.

### 17.2 Primary navigation

Use the following hierarchy:

**Home**
- Home

**ANVAYA**
- Tutor

**Learning**
- Notes
- Obsidian
- Resources
- Knowledge

**Academics**
- Courses
- Assessments
- Calendar
- Planning
- Progress
- Grades

**System**
- Settings

### 17.3 Persistent top bar

The product shell should support, as the relevant phases become available:

- active semester;
- active course;
- global search;
- knowledge/index status;
- Obsidian status;
- settings access.

Active course/semester context should reduce repeated filtering across Notes, Resources, Knowledge, Tutor, Progress, and Assessments.

### 17.4 Home layout

Priority order:

1. ANVAYA input/conversation entry;
2. quick academic actions;
3. today’s schedule;
4. deadlines/risk;
5. ANVAYA recommendation;
6. progress snapshot;
7. recent learning activity.

Do not lead with a large statistics grid.

### 17.5 Contextual tutor access

Major objects should offer context-aware actions such as:

- Ask ANVAYA about this note;
- Ask ANVAYA about this assessment;
- Ask ANVAYA about this lecture/resource;
- Ask ANVAYA about this course/topic.

The tutor may open as a side panel or dedicated Tutor screen, but must preserve the current object context.

---

## 18. ANVAYA Brand System

Use the approved ANVAYA brand direction in the presentation layer.

Brand colours:

- Primary Dark: `#0B0F14`
- Primary Light: `#E8EDF2`
- Accent Teal: `#55C2B8`
- Supporting Blue-Gray: `#64748B`

The product should be dark-first, with subtle surface variation rather than pure black everywhere.

Use the supplied assets according to role:

- transparent ANVAYA wordmark: desktop dark shell/sidebar;
- symbol-only mark: favicon, collapsed sidebar, mobile header, tutor avatar, app icon;
- README/banner artwork: GitHub documentation/portfolio use;
- splash artwork: optional welcome/about/onboarding experience;
- brand guide: repository documentation/reference, not ordinary dashboard content.

Do not place a giant logo in the centre of every working screen.

Use accent teal sparingly for active state, focus, primary action, and brand identity.

Avoid heavy glow, random recolouring, distortion, excessive decorative gradients, and constant animated branding.

---

## 19. Responsive and Accessibility Requirements

### Desktop

- persistent sidebar;
- wide working canvas;
- optional contextual side panel when useful.

### Tablet

- compact/collapsible sidebar;
- primary content remains dominant.

### Mobile

- drawer navigation;
- single-column workflow;
- large touch targets;
- quick access to Tutor and create actions;
- no normal-workflow horizontal scrolling.

Accessibility requirements:

- visible keyboard focus;
- status must not rely on colour alone;
- readable contrast;
- semantic form labels;
- keyboard-operable primary workflows;
- reduced-motion-friendly behaviour;
- clear destructive-action treatment.

---

## 20. Status, Settings, and Diagnostics

Normal UI status should be understandable without developer knowledge, for example:

```text
Tutor       Ready
Knowledge   Indexed
Obsidian    Connected
Database    Healthy
```

User-facing failures must not expose raw tracebacks.

Settings should progressively contain:

- student/tutor preferences;
- default source policy;
- active semester/default course;
- study preferences;
- Obsidian integration;
- AI provider configuration/status;
- optional external calendar integration later;
- knowledge/index status and re-index controls;
- appearance/density;
- diagnostics;
- backup/export links when migrated.

Developer-level details belong under Settings/Diagnostics, not in normal study workflows.

---

## 21. Failure Handling

ANVAYA must never fake success.

If an integration or optional dependency fails:

- report the capability that is unavailable;
- state whether academic data was changed;
- keep unaffected capabilities usable;
- provide a recovery action when one exists.

Examples:

- Obsidian unavailable -> user can still use ANVAYA notes and indexed sources;
- AI provider unavailable -> search, notes, calendar, plans, and other deterministic features remain usable;
- retrieval index unavailable -> tutor reports grounded sources unavailable instead of fabricating citations;
- write failure -> no success toast/card may be shown unless the service confirms persistence.

Raw exceptions may be logged/available in diagnostics but must not be the normal user experience.

---

## 22. Compatibility and Migration Constraints

The redesign must preserve existing architectural investments.

Required constraints:

- do not modify `main` as part of this redesign work;
- do not restart or rewrite completed Phase 7.1–7.5.9 foundations without a demonstrated defect;
- preserve current service APIs where practical;
- add service/command boundaries instead of bypassing repositories;
- keep CLI workflows available until web replacements are validated;
- preserve authority routing and SQLite/legacy compatibility guarantees;
- do not mutate production academic data in read-only GET requests;
- do not use presentation code to calculate authoritative academic values;
- optional dependencies must degrade safely;
- Windows paths, Obsidian paths, and local-first execution remain supported.

---

## 23. Implementation Decomposition

The redesign is intentionally split into sub-phases so the project becomes useful incrementally and each gate remains reviewable.

### Phase 7.5.10 — ANVAYA Product Shell + Branding

Scope:

- dark-first ANVAYA shell;
- approved brand assets;
- sidebar/top bar/navigation hierarchy;
- responsive navigation;
- shared UI primitives;
- consistent page layout;
- preserve existing page behaviour and backend semantics.

This phase is presentation-focused and must not introduce broad write capability.

### Phase 7.5.11 — Operational Notes + Resources

Scope:

- create/search/edit/archive notes;
- Markdown/math-capable note experience;
- add/search/update resources;
- safe write routes/services;
- contextual Ask ANVAYA actions;
- tests proving writes use established repositories/services.

### Phase 7.5.12 — Obsidian Workspace + Search

Scope:

- connect/status/browse/search/preview vault;
- use vault notes as tutor sources;
- create new Obsidian note;
- confirmation boundary for edits/deletes;
- safe Windows-path handling.

### Phase 7.5.13 — Tasks + Calendar Operations

Scope:

- local task model/service if not already represented adequately;
- create/view/complete/reschedule tasks;
- create study blocks;
- Today/Week/Month/Agenda views;
- separate Calendar from Grades;
- local schedule remains authoritative.

### Phase 7.5.14 — Assessment Operations

Scope:

- create/edit supported assessment fields;
- assessment preparation workspace;
- course/topic/deadline integration;
- natural-language assessment creation through action boundary;
- preserve existing assessment authority.

### Phase 7.5.15 — Interactive Study Planning

Scope:

- generate Today/Week plans;
- plan preview/accept;
- missed-work recovery/replan;
- interactive study blocks;
- session completion feedback.

### Phase 7.5.16 — Unified ANVAYA Action Layer

Scope:

- typed action registry;
- validated command schemas;
- READ/SAFE_WRITE/CONFIRM_WRITE policy;
- deterministic service dispatch;
- action-result cards;
- confirmation workflow;
- no direct model writes.

### Phase 7.5.17 — Unified Tutor + Context + Memory

Scope:

- one tutor/operations conversation;
- active-page context;
- source-mode UX;
- layered memory integration;
- pinned memory;
- structured answer/evidence presentation;
- tutor action suggestions.

### Phase 7.5.18 — Proactive Home + Operational Integration

Scope:

- proactive daily signals;
- best-next-action presentation;
- missed-work/deadline prompts;
- quick actions connected to real services;
- integrated home workflow across tutor/tasks/planning/assessment/progress.

### Phase 7.5.19 — Final Dashboard 2 / ANVAYA Acceptance Gate

Scope:

- full cross-feature validation;
- primary navigation completeness;
- critical daily workflows from browser;
- responsive/accessibility acceptance;
- safe degradation tests;
- no regression to CLI/authority/migration guarantees;
- documentation/run instructions.

Phase numbers may be adjusted only if repository state requires it; the decomposition and dependency order should remain unless a later written design amendment is approved.

---

## 24. Testing and Gate Strategy

Every implementation sub-phase must define a focused gate before code changes are committed.

At minimum, gates should validate relevant items from the following set:

- unit tests for new service/command behaviour;
- route tests;
- CSRF/request validation where applicable;
- read-only GET requests do not mutate data;
- safe write routes persist through the correct repository/authority layer;
- confirmation-required actions cannot execute without confirmation;
- existing academic calculations are reused, not reimplemented in templates/routes;
- optional dependencies fail safely;
- production data integrity and foreign keys remain valid;
- protected/legacy boundaries remain intact;
- responsive templates render without missing assets/routes;
- existing Phase 7.5 tests continue to pass unless an explicitly approved behaviour change requires a test update;
- focused compile/import checks;
- full regression suite at major integration gates.

Implementation work must follow test-driven development where practical: first prove the missing behaviour with a failing test, then implement the smallest service/UI change that makes it pass.

No sub-phase should be declared complete based only on visual appearance.

---

## 25. First Operational Product Acceptance Criteria

Before ANVAYA is described as a genuinely operational academic tutor interface, the browser must support all of the following in working form:

1. Unified ANVAYA conversation for tutoring and supported academic commands.
2. Visible source policy and grounded citations/evidence.
3. Course/object context carried into tutor requests.
4. Conversation memory plus integration with existing course learning memory.
5. Explicit pinned-memory action.
6. Structured action registry with safety policy.
7. Notes: create, view, search, edit, archive.
8. Obsidian: connect, browse, search, preview, use as source, create new note.
9. Resources: add, search, view, update status.
10. Tasks: create, view, complete, reschedule.
11. Calendar: Today/Week/Month plus study blocks.
12. Assessments: create, view, topic/deadline context.
13. Planning: generate Today/Week plan, preview/accept, basic replan.
14. Study session: start/complete and record learning feedback.
15. Proactive Home: deadlines, weak topics, missed work, and best next action.
16. Failure handling never reports success after failed persistence or unavailable grounding.
17. The CLI remains usable as fallback/recovery while web parity is incomplete.

---

## 26. Non-Goals for This Redesign Sequence

The following are deliberately not prerequisites for the first operational ANVAYA release:

- complete migration of every legacy `main.py` menu option;
- mandatory React/Node rewrite;
- public cloud hosting;
- multi-user accounts;
- replacing local-first data ownership;
- full Google Calendar bidirectional authority;
- advanced note graph visualization;
- complex note-template ecosystem;
- every advanced assessment importer exposed in the first browser milestone;
- autonomous destructive actions;
- unrestricted LLM database/file access;
- large-scale rebranding of internal package/service/database names.

These may be designed later if they become useful, but they must not delay the daily-use operational core.

---

## 27. Design Invariants

The following statements should remain true throughout implementation:

1. **ANVAYA is the primary user interface, not the primary source of academic truth.**
2. **Existing engines own academic calculations.**
3. **Application services own controlled operations.**
4. **Repositories/authority routing own persistence.**
5. **The LLM may propose actions but does not directly write academic storage.**
6. **Important/destructive changes require human confirmation.**
7. **Grounded answers distinguish user-source evidence from outside knowledge.**
8. **Obsidian remains user-owned and is never silently overwritten.**
9. **A failed operation is never presented as successful.**
10. **A page is not considered complete merely because it displays data; core user actions must work.**

---

## 28. Final Product Definition

ANVAYA is not merely a dashboard and not merely a chatbot.

It is the local-first academic interaction layer that connects:

```text
Tutor
+ Notes
+ Obsidian
+ Resources
+ Knowledge Retrieval
+ Courses
+ Assessments
+ Tasks
+ Calendar
+ Planning
+ Progress
+ Grades
+ Learning Memory
```

through one coherent interface while preserving the deterministic academic engines and persistence architecture already built.

The success condition is simple:

> A student should be able to open ANVAYA and actually study, ask, create, schedule, plan, search, track, and recover from missed work without falling back to `main.py` for the core daily workflow.
