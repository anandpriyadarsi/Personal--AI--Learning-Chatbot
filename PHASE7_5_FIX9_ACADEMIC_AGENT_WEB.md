# Phase 7.5.9 — Academic Agent Web Interface

## Objective

Expose the existing Phase 6 academic intelligence through a small local Flask workspace without creating a new intelligence engine. Phase 7.5.9 combines read-only Adaptive Mentor advice with persistent, source-grounded tutor conversations.

## Browser surface

The browser adds four endpoints: `GET /agent`, `POST /agent/sessions`, `GET /agent/sessions/<session_id>`, and `POST /agent/sessions/<session_id>/ask`. The landing page shows provider readiness, course-scoped mentor advice, recent tutor sessions, and a new-session form. The session page reopens persisted transcripts and shows support level, provider/model metadata, and evidence links for assistant turns.

## Architecture boundary

`AcademicAgentWebService` is the only browser-facing orchestration adapter. It lazily composes the existing course catalogue, `AdaptiveMentorService`, `TutorSessionService`, `GroundedTutorService`, Phase 5.8 retrieval service/index store, and OpenAI-compatible tutor provider. Flask routes do not construct Phase 6 service graphs directly.

GET requests use read-only SQLite connections. App creation and module import do not open SQLite, load the retrieval index, or make a network request.

## Tutor persistence boundary

The only permitted Phase 7.5.9 writes are existing tutor conversation state:

- `tutor_sessions`
- `tutor_turns`
- `tutor_evidence_links`

`tutor_feedback` is not used. Phase 7.5.9 does not mutate mastery/progress, learning memory, study plans, grades, assessments, notes, resources, lecture state, practice state, retrieval generations, or authority configuration.

## Source policy

New browser-created sessions default to `mode="concept"` and `source_policy="source_only"`. `source_first` is an explicit opt-in at session creation. Course, mode, and source policy remain fixed for the life of a session.

## Provider behavior

Provider configuration remains environment based: `LLM_API_URL`, `LLM_API_KEY`, and `LLM_MODEL`. Secrets are never rendered. `GET /agent`, course-scoped mentor refreshes, and session transcript reads never call the provider. Only the tutor ask POST path may call it, and only after retrieval grounding is prepared.

If the current tutor scope has no evidence, the existing grounded tutor persists its bounded insufficient-evidence response without calling the provider.

## Explicitly excluded Phase 6.8 execution

Adaptive Mentor output is advisory only. Phase 7.5.9 exposes no browser control for action execution, lecture mutation, practice generation, academic-state mutation, autonomous loops, session deletion/rename/completion/abandonment, feedback, streaming, WebSockets, or background jobs. Browser action execution is deferred to a later explicitly designed phase.

## Failure behavior

Known failures map to safe browser messages without exposing SQL, provider secrets, URLs, keys, or raw exception details:

- `AI tutor is not configured on this machine.`
- `The AI tutor could not complete this request. Your academic data was not changed.`
- `Grounded academic sources are temporarily unavailable.`

Missing sessions return a safe 404 and invalid user input returns a safe 400.

## Verification gate

Run `./phase7_5_fix9_gate.ps1` from branch `phase7/deprecation-observation` with the working tree containing only the nine Phase 7.5.9 implementation files. The gate verifies focused tests, lazy startup, GET immutability, isolated tutor persistence, Phase 7.5 and Phase 7 regressions, the full test suite, dependency/SQLite integrity, protected-file hashes, forbidden execution references, scoped diff, and production data/retrieval hash reconciliation.

Do not commit the implementation until the full gate prints the Phase 7.5.9 PASS banner.
