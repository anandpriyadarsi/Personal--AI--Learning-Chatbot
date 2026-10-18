# Phase 6.6 — PYQ + Exam Intelligence

## Starting point

Phase 6.6 starts from:

`59977d36da575ac7573aeee90a45c3df136f3878`

on:

`phase6/academic-tutor-intelligence`

This is the completed Phase 6.5 Active Recall + Fast Quiz commit.

## Objective

Turn the existing formal assessment/question/source/performance graph into a
read-only, explainable exam-preparation intelligence layer.

Phase 6.6 answers questions such as:

- Which topics actually appear in the formal question corpus?
- How many recorded marks are attached to each accepted topic mapping?
- Which questions are explicitly labelled as PYQ/past-paper evidence?
- Which formal questions have source provenance?
- Where do unresolved mistakes exist?
- Which topics are explicitly in a selected upcoming assessment's recorded scope?
- What deserves preparation attention based on recorded evidence?

It does **not** predict future exam questions.

## Formal evidence boundary

Phase 6.6 reads only formal academic tables:

- `assessments`
- `assessment_topics`
- `questions`
- `question_topic_mappings`
- `question_sources`
- `question_attempts`
- `mistake_events`
- `topics`
- `courses`

Phase 6.5 generated-practice tables are deliberately excluded.

A generated fast-quiz item therefore cannot become PYQ evidence or historical
exam frequency.

## Explicit PYQ classification

An assessment is counted as PYQ/past-paper evidence only when its own metadata
explicitly says so.

Accepted signals are intentionally narrow:

- assessment type explicitly equals a PYQ/past-paper type; or
- title/description explicitly contains terms such as:
  - `PYQ`
  - `previous year`
  - `past paper`
  - `past exam paper`

A normal `quiz`, `mid_semester`, `end_semester`, or `exam` is **not**
automatically called a PYQ.

Completed assessments are not automatically treated as previous-year papers.

## Topic mappings

Only `question_topic_mappings.state='accepted'` contributes to topic frequency,
marks, PYQ counts, mistakes and topic preparation priority.

Questions with only proposed mappings are reported as `proposed_only`.

Questions with no mapping are reported as `unmapped`.

Phase 6.6 never promotes or guesses a topic mapping.

## Source provenance

Question-source evidence preserves the existing:

- document/resource/note ownership;
- raw source label;
- page number;
- locator.

Questions without source provenance are not hidden. Their missing provenance is
visible through report counts.

## Preparation priority

`preparation_priority_score` is an explainable ordering aid, **not an exam
probability** and not a prediction.

Signals may include:

- number of accepted formal questions on the topic;
- share of recorded mapped marks;
- explicitly labelled PYQ question count;
- unresolved mistakes on formal attempts;
- explicit target-assessment topic scope;
- current topic confidence;
- current topic status.

Every topic includes human-readable reasons.

No score claims that a topic "will come" in an exam.

## Target assessment

A caller may explicitly select an assessment:

```powershell
python .\phase6_exam_intelligence.py `
  --database .\data\learning_assistant.db `
  --course-code MA103N `
  --target-assessment-id <assessment-id> `
  --as-of 2026-09-16
```

Target scope comes only from:

- `assessment_topics.topic_id`; and
- accepted question-topic mappings already belonging to that assessment.

No topic is added through inference.

## Read-only operator

Course-wide report:

```powershell
python .\phase6_exam_intelligence.py `
  --database .\data\learning_assistant.db `
  --course-code MA103N `
  --as-of 2026-09-16
```

The CLI opens SQLite with `mode=ro` and performs no provider/network call.

## No schema migration

Phase 6.6 introduces no SQLite migration.

Migration 0004 from Phase 6.5 remains the newest schema version.

This phase is analytics over existing formal evidence.

## Relationship to the grounded tutor

Phase 6.2 remains the explanation engine for source-grounded learning material.

Phase 6.6 provides formal exam/PYQ structure and preparation evidence.

A later mentor/agent layer can combine:

```text
formal exam intelligence
        +
Knowledge Navigator
        +
grounded Tutor
        +
practice history
```

without confusing historical PYQs with generated practice.

## Gate guarantees

The Phase 6.6 gate verifies that:

- the report is read-only;
- explicit PYQ classification is conservative;
- only accepted topic mappings contribute to topic statistics;
- question-source provenance is preserved;
- proposed/unmapped questions remain visible;
- unresolved formal mistakes are reported;
- target assessment scope is exact;
- no prediction is performed;
- Phase 6.1–6.5 and Phase 5 regressions pass;
- production SQLite, authority state, legacy JSON and retrieval indexes remain
  byte-for-byte unchanged;
- no migration is introduced.

## Next boundary

Phase 6.7 — Adaptive Mentor.

That phase should combine the evidence streams from:

- Knowledge Navigator;
- Lecture Learning;
- Active Recall;
- formal Exam Intelligence;
- existing topic progress and learning memory;

to produce explainable mentor recommendations without silently promoting
advisory evidence into mastery state.
