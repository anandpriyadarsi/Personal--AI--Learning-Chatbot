# Phase 6.4 — Lecture Learning Mode

## Starting point

Phase 6.4 starts from:

`b7bd07a0572a88c8063ccde8bb414f569574473f`

on:

`phase6/academic-tutor-intelligence`

This is the completed Phase 6.3 Knowledge Navigator.

## Objective

Turn registered lecture resources into an explicit learning workflow:

```text
list/show lecture
      |
start
      |
checkpoint position/progress
      |
pause
      |
resume
      |
finish
      |
completion snapshot
```

The workflow reuses the existing authoritative:

- `resources`
- `resource_progress_events`
- `study_sessions`

tables.

No parallel watch-time or lecture-progress database is introduced.

## Explicit time semantics

Phase 6.4 never guesses whether a student is actually watching a lecture.

Time is counted only between explicit:

- `start` -> `pause`
- `start` -> `finish`
- `resume` -> `pause`
- `resume` -> `finish`

events.

The existing schema stores integer minutes, so a segment records floor elapsed
minutes between the explicit timestamps. A 25 minute 30 second segment records
25 minutes.

If the user leaves a session open, the system does not pretend to know whether
the student kept watching. The user must explicitly pause or finish it.

## Position and progress

`resource_progress_events` remains append-only history.

Each start/checkpoint/pause/resume/finish may preserve:

- `position` — an explicit player/lecture locator such as `00:18:30`;
- `value`;
- `max_value`;
- `unit`.

The service never fabricates a player position.

When a later command omits these values, the most recent explicit values are
carried forward.

## Study-session segmentation

Every start/resume opens a new `study_sessions` row.

Pause/finish closes only that segment.

This means a lecture learned over three sittings has three study-session
segments rather than one overwritten total.

Total study time is the sum of closed segments.

## Topic/course scope

If a lecture has exactly one linked course, the study segment may use it.

If it has exactly one linked topic compatible with that course, the topic may
also be used.

If multiple reviewed topic links exist, Phase 6.4 does not guess which topic the
student was studying. The segment stores `topic_id=NULL` unless the caller
explicitly supplies a linked topic.

## Resources 2 integration

Every lecture action records a normal Resources 2 progress event.

The latest progress event updates the canonical resource lifecycle:

- start/resume/checkpoint -> `in_progress`
- pause -> `paused`
- finish -> `completed`

An outbox event is also written in the same transaction.

The underlying source URL/file is never modified.

## SQLite authority guard

Mutation commands require an explicit Phase 4 authority-control file whose state
is:

- `storage_backend=sqlite`
- `legacy_writes_blocked=true`

This prevents Phase 6.4 from accidentally writing to a shadow/pre-promotion
database.

Read-only listing/snapshot operations do not require the mutation authority
guard.

## Lecture-specific tutor mode

Phase 6.4 can create a normal Phase 6.1 tutor session with:

- mode = `lecture`
- exact `resource_id`
- single linked course when unambiguous
- single linked topic when unambiguous
- current resume position in metadata

Phase 6.2 then automatically scopes retrieval to that lecture resource.

No separate lecture-chat implementation is introduced.

## Operator CLI

Read-only listing:

```powershell
python .\phase6_lecture_learning.py `
  --database .\data\learning_assistant.db `
  list `
  --course-code MA103N `
  --provider mit_ocw
```

Read-only snapshot:

```powershell
python .\phase6_lecture_learning.py `
  --database .\data\learning_assistant.db `
  show `
  --resource-id <resource-id>
```

Start:

```powershell
python .\phase6_lecture_learning.py `
  --database .\data\learning_assistant.db `
  --authority .\.phase4_authority.json `
  start `
  --resource-id <resource-id> `
  --position "00:00:00" `
  --confirm START_LECTURE_SESSION
```

Checkpoint:

```powershell
python .\phase6_lecture_learning.py `
  --database .\data\learning_assistant.db `
  --authority .\.phase4_authority.json `
  checkpoint `
  --resource-id <resource-id> `
  --position "00:18:30" `
  --confirm CHECKPOINT_LECTURE_SESSION
```

Pause/resume/finish similarly require explicit confirmation phrases.

## Gate safety

The Phase 6.4 gate performs only a real read-only lecture listing against the
production database.

All write behavior is tested against temporary migrated databases and synthetic
resources.

The gate hashes production SQLite, authority control, legacy JSON and the Phase
5 retrieval index before/after execution.

## Non-goals

Phase 6.4 does not:

- embed or control a real YouTube player yet;
- infer playback time from browser activity;
- scrape YouTube watch history;
- modify topic mastery/confidence;
- write learning memory;
- edit study plans;
- generate a quiz;
- analyze PYQs;
- call an LLM during the gate;
- add a SQLite migration.

## Next boundary

Phase 6.5 — Active Recall + Fast Quiz.

It should create source-grounded practice items from selected
course/topic/resource evidence, evaluate deterministic answers where possible,
and preserve advisory-vs-authoritative grading boundaries.
