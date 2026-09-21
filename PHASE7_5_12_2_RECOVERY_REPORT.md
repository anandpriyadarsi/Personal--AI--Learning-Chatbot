# Phase 7.5.12.2 Recovery — Unified Knowledge Search + Study Memory

## Recovery context

The original Work runtime completed Gates A–E and reached a strict-gate checkpoint, but the branch/checkpoint commits were never pushed and are no longer present on GitHub. Current authoritative `main` is `b89f32c` (Phase 7.5.13 Operational Planner).

This recovery therefore rebuilds the approved Phase 7.5.12.2 architecture **on top of current main** rather than attempting to overwrite Phase 7.5.13.

## Migration renumbering

The historical plan called the generalized interaction migration `0006_unified_study_interactions.sql`.

Current main already owns:

- `0006_operational_planner.sql`

The recovered phase therefore uses:

- `0007_unified_study_interactions.sql`

Do not rename or replace migration 0006.

## Recovered gates

### Gate A — Unified Study Search
- global top-bar search entry
- `/knowledge` student-facing grouped source results
- `/api/search/suggest`
- human titles, source labels, course/topic labels
- filters for course, topic, source type, provider
- Obsidian live-vault matches alongside indexed knowledge sources
- grouped chunk hits by source/document
- retrieval diagnostics moved to `/retrieval/diagnostics`

### Gate B — Retrieval runtime v2 hardening
- one lazy runtime per `(database_path, index_root)` per process
- optional semantic provider reused inside that runtime
- strict current-source-fingerprint validation before search/tutor retrieval
- stale current index is refused rather than silently serving stale evidence
- deterministic benchmark harness supplied

### Gate C — Unified interaction memory
- generalized reading session table
- generalized Companion entry table
- stable `(item_kind, item_identity, source_version_hash)` identity
- old Obsidian interaction rows backfilled
- historical Obsidian tables preserved for rollback/forensics
- normal Obsidian Reader runtime switched to the generalized persistence adapter
- existing Obsidian routes/UI remain compatible

### Gate D — Knowledge Reader + reusable Companion
- `/knowledge/item/<document_id>`
- readable source view
- active-time/progress tracking
- key points, doubts, personal notes
- history persisted by stable identity
- external-source link when safe
- "Ask this doubt" handoff

### Gate E — Source-grounded Ask ANVAYA
- source-scoped tutor sessions
- fixed `source_only` policy
- exact `document_id` retrieval filter
- app-scoped stale-safe retrieval runtime shared with search
- human-readable evidence titles in persisted transcript rendering
- no autonomous academic writes

## Important review blockers recovered

The lost Work review had identified two release blockers. This recovery explicitly addresses both:

1. **Tutor bypassing the application-scoped retrieval runtime**
   Fixed: `AcademicAgentWebService` now obtains the shared `UnifiedSearchRuntime`.

2. **Stale indexed evidence could still be served after source mutation**
   Fixed: runtime recomputes the authoritative source fingerprint before retrieval and raises `UnifiedSearchStaleIndexError` when it differs from the current index manifest.

## Phase boundary

This recovery does not:
- mutate Obsidian Markdown;
- rebuild retrieval automatically;
- auto-apply Companion notes into mastery/progress;
- change Operational Planner behavior;
- merge to `main`;
- apply migration 0007 to production during the development gate.

Production migration happens only after the recovery branch is fully green and reviewed.
