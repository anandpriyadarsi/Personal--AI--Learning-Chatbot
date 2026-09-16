# Phase 6.5 — Active Recall + Fast Quiz

## Starting point

Phase 6.5 starts from:

`039196863e1905e242354231ead468367550dcaf`

on:

`phase6/academic-tutor-intelligence`

This is the completed Phase 6.4 Lecture Learning Mode.

## Objective

Create source-grounded, low-friction practice without converting generated quiz
results into formal assessment truth or topic mastery.

The flow is:

```text
course/topic/resource scope
        |
Phase 5.8 retrieval
        |
source-only evidence packet
        |
quiz-generation provider
        |
strict JSON/schema/provenance validation
        |
practice session + items + exact chunk sources
        |
student response
        |
deterministic or advisory grading
        |
practice attempt history
```

## New migration 0004

Phase 6.1 intentionally deferred practice persistence until the actual practice
contract was known.

Phase 6.5 introduces:

- `practice_sessions`
- `practice_items`
- `practice_item_sources`
- `practice_attempts`

Generated practice is deliberately separate from formal:

- `assessments`
- `questions`
- `question_attempts`
- `mistake_events`

A fast quiz therefore cannot silently pollute PYQ/formal-assessment analytics.

## Practice item types

### single_choice

- exactly four A/B/C/D options;
- exactly one provider-declared correct option;
- locally/deterministically graded;
- no LLM call during submission.

### exact_recall

- one or more exact accepted answers;
- case/outer-whitespace/duplicate-space normalization only;
- no fuzzy semantic matching;
- locally/deterministically graded.

### free_response

- source-grounded reference explanation/rubric is stored;
- Phase 6.5 does **not** label the answer correct/incorrect;
- persisted outcome is `advisory_ungraded`;
- no score is produced.

This is the boundary that prevents an LLM opinion from becoming an authoritative
mastery result.

## Source grounding

Every generated item must cite one or more retrieved evidence labels.

Those labels are validated against the current retrieval packet and stored as:

- exact `knowledge_chunks.id`
- matching `knowledge_documents.id`
- citation label/order

Unavailable/fabricated labels reject the whole generation before any practice
rows are written.

Retrieved source text is explicitly treated as DATA, not instructions.

## Academic-state boundary

A practice attempt does not automatically write:

- topic progress/status/confidence;
- learning memory;
- formal question attempts;
- mistake events;
- study plans;
- resource progress;
- grades.

Self-confidence may be recorded on the practice attempt because it is an
explicit student input, but it does not update topic confidence.

Phase 6.7 may later consume repeated practice evidence through an explicit,
auditable mentor policy.

## Operation/outbox integration

Quiz generation, attempt recording and session completion emit normal outbox
events in the same SQLite transaction.

Provider or validation failure happens before the quiz transaction and therefore
cannot leave partial practice rows.

## Schema safety

Production migration is explicit:

```powershell
python .\phase6_practice_schema.py `
  --database .\data\learning_assistant.db `
  preview
```

After review:

```powershell
python .\phase6_practice_schema.py `
  --database .\data\learning_assistant.db `
  apply `
  --confirm APPLY_PHASE6_PRACTICE_SCHEMA
```

The Phase 6.5 gate never migrates the real database. It rehearses pending
migrations against a temporary database copy.

The old Phase 6.1 schema operator is also hardened so it refuses to silently
apply migrations newer than its own target version.

## Phase 6.1 regression compatibility

The Phase 6.1 tutor-foundation tests historically asserted that a fresh current
migration run returned exactly `(1, 2, 3)`.

Phase 6.5 changes those historical checks to require the intact prefix
`(1, 2, 3)` while allowing later append-only migrations.

Apply the supplied compatibility patch before running the gate:

```powershell
git apply --check .\phase6_fix5_phase61_compat.patch
git apply .\phase6_fix5_phase61_compat.patch
Remove-Item .\phase6_fix5_phase61_compat.patch
```

No earlier migration file is edited.

## Operator usage

Read-only evidence preview:

```powershell
python .\phase6_fast_quiz.py `
  --database .\data\learning_assistant.db `
  --index-root .\.phase5_retrieval `
  preview `
  "LU factorization intuition and mechanics" `
  --course-code MA103N `
  --mode fast_quiz `
  --difficulty medium `
  --item-count 5
```

Generation requires:

- migration 0004 already applied;
- active SQLite authority;
- configured tutor provider;
- explicit confirmation.

Submission is local/deterministic for `single_choice` and `exact_recall`.

The normal `show` command never exposes answer keys.

## Gate guarantees

The gate proves:

- 0004 is append-only and 0001–0003 are unchanged;
- migration rehearsal is isolated;
- real MA103N quiz preview is read-only and performs no provider call;
- generated items require exact source provenance;
- deterministic item types are graded locally;
- free response remains advisory;
- practice attempts do not mutate mastery/formal assessment state;
- Phase 6.1–6.4, Phase 5 and full project regressions remain green.

## Next boundary

Phase 6.6 — PYQ + Exam Intelligence.

That phase should use the formal assessment/question/source architecture and keep
generated practice distinct from historical PYQ evidence.
