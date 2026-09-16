# Phase 6.3 — Knowledge Navigator / What Should I Study?

## Starting point

Phase 6.3 starts from:

`2f04768c5e5da72b414bc138acf1e3ac107de99b`

on:

`phase6/academic-tutor-intelligence`

This is the completed Phase 6.2 Grounded Academic Tutor Engine.

## Objective

Answer the planning question:

> What should I study next, in what order, and why?

using only already-authoritative structured academic evidence.

Phase 6.3 is deterministic, read-only and recommendation-only.

It does not ask an LLM to rank topics or sources and does not modify a study
plan, mastery state, learning memory, resource progress, or assessment data.

## Evidence used

Topic priority can use:

- current topic status;
- current topic confidence;
- linked active assessment deadlines;
- unresolved mistake events through accepted question-topic mappings;
- active learning-memory entry count;
- existing upcoming study-plan coverage;
- recorded topic study minutes.

Source ordering can use:

- direct topic relationship vs course-only relationship;
- current resource lifecycle/status;
- latest resource-progress event;
- whether unfinished progress exists;
- current retrievable knowledge-chunk availability;
- explicit resource rating;
- resource-assessment relationship near a deadline;
- recorded study minutes;
- note topic/course relationship;
- note pin/revision metadata.

No score is accepted without human-readable reasons.

## Deliberately excluded inference

Phase 6.3 does not:

- inspect arbitrary memory text and label the student weak;
- guess that a provider/title means "professor material";
- infer source authority from names;
- predict exam questions;
- automatically alter topic status/confidence;
- automatically edit a study plan;
- call the Phase 6.2 provider;
- call an LLM.

Those boundaries keep the recommendation explainable and auditable.

## Topic priority

The score is an ordering aid, not a mastery score.

Current deterministic signals include:

- learning/in-progress/not-started/revision/mastered status;
- lower recorded confidence;
- assessment proximity;
- unresolved mistake count.

Learning-memory, existing plan coverage and study minutes are reported as
contextual reasons rather than silently interpreted as positive/negative.

## Source recommendation

Direct topic relationships receive stronger weight than course-only
relationships.

Resources that are:

- already in progress;
- unfinished;
- backed by current retrievable chunks;

receive additional ranking support.

Completed resources are deprioritized rather than hidden, so the system can
still explain what has already been covered.

Pinned/reviewed notes are surfaced as note candidates.

## Read-only operator CLI

Course-wide navigation:

```powershell
python .\phase6_knowledge_navigator.py `
  --database .\data\learning_assistant.db `
  --course-code MA103N `
  --as-of 2026-09-16
```

Focused topic navigation:

```powershell
python .\phase6_knowledge_navigator.py `
  --database .\data\learning_assistant.db `
  --course-code MA103N `
  --topic "LU Factorization" `
  --as-of 2026-09-16
```

The CLI opens production SQLite with `mode=ro`.

## Example output meaning

A recommendation may say:

```text
LU Factorization
Priority reasons:
- topic status is learning
- confidence is 2/5
- Quiz 1 is due in 2 days
- 1 unresolved mistake event is linked
- an upcoming study-plan item already covers it

Suggested sources:
1. My LU Note
   - directly linked to topic
   - pinned
   - reviewed
2. MIT Lecture 04
   - directly linked to topic
   - currently in progress
   - current retrievable chunks exist
```

That is an explanation of structured evidence, not an opaque model judgment.

## No schema change

Phase 6.3 introduces no SQLite migration.

It uses the existing Phase 3/4 authoritative schema and remains compatible
whether production migration 0003 has already been applied or is still pending.

## Relationship to Phase 6.2

Phase 6.2 answers grounded academic questions.

Phase 6.3 decides what deserves attention and which registered source should
come first.

A later tutor/agent layer can compose them:

```text
Knowledge Navigator recommendation
        |
selected topic/source
        |
Phase 6.2 grounded tutor
```

without allowing the LLM itself to become the planning authority.

## Next boundary

Phase 6.4 — Lecture Learning Mode.

That phase should use existing `resource_progress_events` and `study_sessions`
for explicit start/pause/resume/finish behavior and lecture-specific tutoring,
without inventing a parallel watch-time store.
