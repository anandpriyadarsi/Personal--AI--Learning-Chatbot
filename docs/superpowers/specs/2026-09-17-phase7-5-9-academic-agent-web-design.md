# Phase 7.5.9 — Academic Agent Web Interface Design

## Status

Approved design for implementation planning.

## Starting point

- Repository: `anandpriyadarsi/Personal--AI--Learning-Chatbot`
- Branch: `phase7/deprecation-observation`
- Required base commit: `cec5957ac3f41b4dbcacca59de0d267dd0ed0945`
- Base feature: Phase 7.5.8 Knowledge Base / RAG web interface

Phase 7.5.9 is the first Phase 7.5 web feature that invokes the grounded tutor provider. It must preserve the local-first architecture and must not expose Phase 6.8 execution-capable Academic Agent actions.

## Goals

Phase 7.5.9 will provide one browser workspace for:

1. read-only Adaptive Mentor recommendations;
2. persistent grounded tutor sessions;
3. source-grounded AI answers using the existing Phase 5.8 retrieval index;
4. reopening existing tutor conversations;
5. viewing citation/evidence metadata for persisted assistant turns.

The feature must reuse existing Phase 6 services rather than reimplementing tutoring, retrieval, source policies, or mentor logic in Flask.

## Non-goals

Phase 7.5.9 will not:

- execute Phase 6.8 Academic Agent actions;
- start/resume lectures;
- generate practice quizzes;
- modify mastery, progress, learning memory, plans, grades, assessments, notes, or resources;
- rebuild or ingest the retrieval index;
- change structured-data authority;
- add autonomous agent loops;
- add WebSockets, streaming tokens, background jobs, or an asynchronous task system;
- add session deletion, rename, completion/abandonment controls, or tutor feedback/rating controls;
- expose raw prompts, provider payloads, API keys, or internal exception details.

## Chosen architecture

Use a dedicated `AcademicAgentWebService` as the browser-facing orchestration boundary.

```text
Browser
   |
   v
Phase 7.5.9 Flask routes
   |
   v
AcademicAgentWebService
   |-- AdaptiveMentorService       -> read-only recommendations
   |-- TutorSessionService         -> tutor-session persistence
   |-- GroundedTutorService        -> grounded AI answers
   |-- RetrievalService            -> Phase 5.8 retrieval index
   `-- OpenAICompatibleTutorProvider
```

The Flask layer must not construct or call `AcademicAgentService.execute()`.

### Why this approach

This keeps the execution-capable Phase 6.8 service outside the web path. The web adapter gets only the dependencies required for read-only mentor advice and user-initiated grounded tutoring. That is simpler to audit and test than either shelling out to CLI processes or wrapping the Phase 6.8 execution service and attempting to disable part of it.

## Write boundary

Phase 7.5.9 intentionally persists tutor conversations.

Permitted production writes are restricted to the existing tutor domain:

- `tutor_sessions`
- `tutor_turns`
- `tutor_evidence_links`

No other academic state may be mutated by this phase.

`tutor_feedback` remains unused in Phase 7.5.9 because feedback controls are outside this scope.

## Read boundary

Phase 7.5.9 may read:

- courses needed to scope sessions;
- Adaptive Mentor evidence and recommendations;
- existing tutor sessions and transcripts;
- Phase 5.8 retrieval evidence;
- provider configuration status.

Mentor reads must remain deterministic/read-only. Retrieval must use the existing current generation and must not trigger indexing or ingestion.

## Tutor source policy

New sessions default to:

- mode: `concept`
- source policy: `source_only`

The session-creation form may explicitly select `source_first`.

Once a session exists, its course, mode, and source policy are fixed for that session. Changing any of these requires creating a new session.

`source_only` retains the existing grounding rule that a normal generated answer must cite retrieved project evidence. `source_first` retains the existing rule that clearly separated general explanation may be included when needed.

## Tutor modes

The web form will expose the existing canonical modes rather than inventing new ones:

- `concept`
- `doubt`
- `summary`
- `exam`
- `lecture`
- `revision`
- `guidance`
- `free`

No new mode semantics are introduced in Phase 7.5.9.

## Web surface

### `GET /agent`

Renders the Academic Agent workspace.

The page contains:

1. a course selector for read-only Adaptive Mentor advice;
2. mentor topic priorities and advisory next actions for the selected course;
3. a recent tutor-session list;
4. a new tutor-session form;
5. provider readiness/status information.

`GET /agent?course=<course-code>` may refresh the mentor view for one course. This GET path must remain side-effect free and must never call the LLM.

Mentor actions are labeled advisory only. There is no Execute button.

### `POST /agent/sessions`

Creates a new tutor session through `TutorSessionService`.

Accepted browser inputs:

- course
- mode
- source policy
- optional title

Defaults:

- mode = `concept`
- source policy = `source_only`

The route performs no provider call. After creation it redirects to the session page.

### `GET /agent/sessions/<session_id>`

Renders one persisted tutor session and transcript.

The page shows:

- title;
- course scope;
- mode;
- source policy;
- session status;
- ordered user/assistant transcript;
- assistant support level;
- provider/model metadata where present;
- attached evidence/citation labels for each assistant turn.

### `POST /agent/sessions/<session_id>/ask`

Submits one explicit user question to the grounded tutor.

The request path is:

```text
question
  -> load active session
  -> load transcript
  -> retrieval grounding plan
  -> provider call when evidence exists
  -> validate provider citations
  -> persist user + assistant turn + evidence links
  -> render/redirect to updated session
```

This is the only Phase 7.5.9 route that may trigger an LLM provider call.

## Session history

`SQLiteTutorRepository` currently supports single-session reads and transcript reads but no recent-session listing API.

Phase 7.5.9 may add a read-only repository method such as:

```python
list_sessions(limit=20)
```

Requirements for this method:

- no writes;
- deterministic ordering by most-recently-updated session first;
- bounded result count;
- returns existing tutor-domain models;
- no changes to existing repository methods or persistence semantics.

This small repository extension exists only to support reopening persisted browser conversations.

## Mentor behavior

The Adaptive Mentor remains read-only and deterministic.

The web adapter may expose:

- prioritized topics;
- confidence/status evidence;
- assessment relevance;
- practice evidence summaries;
- recommended next actions;
- reasons attached to those recommendations.

The web UI must not execute those recommendations in Phase 7.5.9.

No Phase 6.8 fingerprint or confirmation-execution flow is exposed because execution is outside scope.

## Grounded answer behavior

The existing `GroundedTutorService` remains authoritative for generated tutor answers.

The web layer must preserve these semantics:

- provider is called only after a grounding plan is built;
- insufficient project evidence yields the existing bounded insufficient-evidence response without a provider call;
- unsupported citation labels are rejected;
- `source_only` generated answers require project-evidence citations;
- successful answers persist user turn, assistant turn, and evidence links;
- provider/model metadata remain attached to persisted assistant turns.

The web adapter must not duplicate citation validation or weaken source-policy rules.

## Provider configuration

The existing `OpenAICompatibleTutorProvider` remains the provider implementation.

Configuration continues to come from:

- `LLM_API_URL`
- `LLM_API_KEY`
- `LLM_MODEL`

The provider remains lazy. Merely importing the web app, opening `/agent`, viewing mentor advice, listing sessions, or reopening a transcript must not make a network request.

The page may show whether the provider is configured, but must never render configuration secrets.

## Error handling

Browser-safe failure behavior:

- provider not configured -> `AI tutor is not configured on this machine.`
- provider timeout/request failure -> `The AI tutor could not complete this request. Your academic data was not changed.`
- retrieval/index unavailable -> `Grounded academic sources are temporarily unavailable.`
- missing/invalid/non-active tutor session -> safe validation/404 response;
- insufficient source evidence -> preserve the existing persisted insufficient-evidence response;
- unexpected failure -> generic browser message; log exception type only.

The web layer must not log or render:

- API keys;
- raw provider request/response payloads;
- full grounding prompts;
- full retrieved academic source text solely for diagnostics;
- internal stack traces in user-facing HTML.

## UI principles

The implementation remains server-rendered Flask/Jinja.

No WebSocket, token streaming, SPA framework, or client-side chat state is required.

The session page should make grounding visible rather than hide it. Assistant messages should expose support state such as grounded, mixed, or insufficient and show evidence labels/details below the answer.

The existing disabled `Academic Agent` sidebar item becomes an active link to `/agent`.

## Protected execution boundary

Phase 7.5.9 must not add any web route or control for:

- `/execute`
- agent action execution
- starting/resuming lectures
- generating practice
- changing progress/mastery
- changing learning memory
- changing plans
- changing grades or assessments
- editing notes/resources

The implementation must not reference `AcademicAgentService.execute` from web production code.

## Expected implementation scope

Expected files:

```text
personal_learning_assistant/services/academic_agent_web_service.py
personal_learning_assistant/repositories/sqlite/tutor_repository.py
personal_learning_assistant/ui/web/routes.py
personal_learning_assistant/ui/web/templates/base.html
personal_learning_assistant/ui/web/templates/agent.html
personal_learning_assistant/ui/web/templates/agent_session.html
tests/test_phase7_5_academic_agent_web.py
PHASE7_5_FIX9_ACADEMIC_AGENT_WEB.md
phase7_5_fix9_gate.ps1
```

Existing Phase 6 grounding, retrieval, provider, Adaptive Mentor, and Academic Agent execution modules are protected and should remain unchanged unless implementation exposes a concrete compatibility defect that is separately reviewed.

## Test strategy

Implementation will be test-driven.

Focused tests must cover at least:

- app creation remains lazy and makes no provider call;
- `/agent` GET renders without provider configuration;
- mentor advice is GET-only and performs no write;
- recent tutor sessions are listed and reopenable;
- `list_sessions()` ordering and bounds;
- new session defaults to `concept` + `source_only`;
- explicit `source_first` is accepted at session creation;
- invalid mode/source policy/course is rejected safely;
- session GET renders persisted transcript;
- ask POST with fake provider persists one user turn, one assistant turn, and evidence links;
- evidence labels/support state render correctly;
- insufficient evidence does not call provider;
- provider-unavailable/provider-error paths degrade safely;
- GET routes remain side-effect free;
- no Phase 6.8 execution route/control/reference is exposed.

## Gate strategy

The Phase 7.5.9 Windows gate will verify:

1. focused Phase 7.5.9 tests;
2. real app startup without provider configuration;
3. real `/agent` GET with no LLM call;
4. recent tutor-session reads;
5. session creation and grounded-answer persistence against an isolated temporary database copy with a fake provider;
6. proof that only tutor-session/turn/evidence tables change in mutation tests;
7. no reference from web production code to `AcademicAgentService.execute`;
8. Phase 7.5.1-7.5.8 regression tests;
9. Phase 7.1-7.4 regression tests;
10. complete suite, compilation, dependency check, SQLite integrity/FK checks, protected-file hashes, retrieval-index immutability, and scoped Git diff validation.

The production database and retrieval index must be hashed before and after the gate and remain byte-for-byte unchanged. Any write-path validation runs only against an isolated temporary database copy.

## Acceptance criteria

Phase 7.5.9 is complete when:

- Academic Agent navigation is active;
- mentor advice is available in-browser and remains advisory/read-only;
- users can create and reopen persistent tutor sessions;
- Source Only is the creation default and Source First is an explicit alternative;
- grounded questions can be asked through the browser using the existing provider/retrieval services;
- persisted answers expose support state and evidence;
- missing provider configuration does not break non-LLM parts of the page;
- no Phase 6.8 execution capability is available from the browser;
- no academic authoritative state outside tutor conversation tables is mutated;
- the complete Phase 7.5.9 gate passes.

## Deferred work

Potential later phases may separately design and approve:

- confirmed execution of Phase 6.8 actions with fingerprint revalidation;
- session completion/abandonment controls;
- feedback/rating UI;
- topic/resource-specific session creation flows;
- streaming responses;
- richer chat interaction polish;
- autonomous or scheduled agent behavior.

None of these are implied by Phase 7.5.9.
