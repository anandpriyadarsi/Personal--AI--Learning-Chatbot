# Phase 6.1 — Tutor Domain + Session/Evidence Foundation

## Starting point

Phase 6.1 starts from the completed Phase 5 closure commit:

`1746962e64e561edc9e8627ab0893f3c140edffc`

on a new development branch:

`phase6/academic-tutor-intelligence`

Phase 5 remains the knowledge/retrieval foundation.

## Objective

Introduce a stable tutor-domain boundary before any real LLM answer generation.

Phase 6.1 provides:

- canonical tutor modes and source-policy contracts;
- persisted tutor sessions;
- ordered user/assistant turns;
- exact chunk/document evidence links for assistant turns;
- support-level semantics;
- explicit user feedback;
- a provider protocol that is deliberately disabled in 6.1;
- append-only SQLite migration `0003_tutor_intelligence.sql`.

Phase 6.1 does not yet produce tutor answers.

## Authority model

The LLM is not an academic authority.

Existing authorities remain unchanged:

- SQLite academic records remain authoritative for courses, topics, assessments,
  progress, memory, plans and structured knowledge.
- source files remain authoritative for original bytes.
- Obsidian Markdown remains authoritative for note bodies.
- Phase 5 retrieval indexes remain disposable derived state.
- tutor evidence links point to exact `knowledge_chunks` and
  `knowledge_documents`.

A tutor turn never silently writes progress, mastery, weakness, resource
progress, study sessions, plans, grades, assessment performance, or notes.

## Migration 0003

The new tables are:

- `tutor_sessions`
- `tutor_turns`
- `tutor_evidence_links`
- `tutor_feedback`

No quiz/practice schema is added yet. Practice persistence belongs to Phase 6.5
when the actual quiz contract is known.

No lecture-time schema is added because Phase 4 already provides
`resource_progress_events` and `study_sessions`.

## Tutor modes

Canonical modes:

- `concept`
- `doubt`
- `summary`
- `exam`
- `lecture`
- `revision`
- `guidance`
- `free`

These are real policy identities, not just prompt labels.

Phase 6.2 will use them to choose retrieval/source priorities.

## Source policies

`source_only`

- answer only from project evidence;
- insufficient evidence must be explicit.

`source_first`

- project evidence remains primary;
- a later Phase 6.2 provider may add clearly separated general explanation.

Phase 6.1 stores the policy but performs no generation.

## Support levels

Assistant turns use one of:

- `grounded`
- `mixed`
- `insufficient`

`grounded` and `mixed` require at least one stored evidence link.

User turns always use `not_evaluated`.

This prevents an answer from being persisted as "grounded" without identifying
the chunks that support it.

## Evidence identity

Each evidence row preserves:

- exact tutor turn;
- ordinal/citation order;
- `knowledge_chunks.id`;
- matching `knowledge_documents.id`;
- relation type;
- retrieval score;
- citation label.

The repository verifies that the supplied chunk actually belongs to the supplied
document before inserting the assistant turn. Turn + evidence insertion is
transactional, so invalid provenance rolls back the whole turn.

## Provider boundary

`TutorProvider` is only a protocol in Phase 6.1.

`DisabledTutorProvider` fails closed.

There is deliberately no HTTP/OpenAI-compatible provider wiring in this phase.
The legacy `rag_answer.py` path is not routed into the new tutor architecture.

Phase 6.2 will introduce grounded generation after the session/evidence contract
is stable.

## Phase 5 compatibility

Phase 5 closure historically required migrations exactly `(1, 2)`. Phase 6.1
changes that check to require the intact Phase 5 prefix `(1, 2)` while allowing
append-only later migrations such as `0003`.

The Phase 5 migrations themselves are not edited.

## Production migration safety

The Phase 6.1 gate does not migrate the real database.

It rehearses `0003` against a temporary database copy and hashes the real
production database before/after the gate.

After Phase 6.1 is committed, production migration is a separate explicit
operator action:

```powershell
python .\phase6_tutor_schema.py `
  --database .\data\learning_assistant.db `
  apply `
  --confirm APPLY_PHASE6_TUTOR_SCHEMA
```

Preview is read-only:

```powershell
python .\phase6_tutor_schema.py `
  --database .\data\learning_assistant.db `
  preview
```

## Non-goals

Phase 6.1 does not:

- call an LLM;
- modify `rag_answer.py`;
- create tutor prompts;
- generate explanations;
- generate quizzes;
- grade free-text answers;
- change learning memory/progress;
- track lecture time;
- analyze PYQs;
- recommend study order;
- start the Academic Agent cutover;
- build UI;
- promote semantic retrieval.

## Next boundary

Phase 6.2 — Grounded Academic Tutor Engine.

It should consume:

- `TutorSessionService`
- Phase 5.8 `RetrievalService`
- `TutorProvider`
- stored evidence contracts

to produce source-grounded answers while normal tutor reads/writes remain
isolated from academic progress state.
