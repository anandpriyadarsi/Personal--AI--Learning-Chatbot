# ANVAYA Tutor 2.2 — Persistent Student Model

Branch: \`anvaya/tutor-2.2-student-model\`  
Baseline: completed Tutor 2.1 Adaptive Intelligence.

## Goal

Tutor 2.1 remembers the state of one tutoring conversation.

Tutor 2.2 begins the next layer: ANVAYA should be able to use stable learning
context from earlier sessions without treating one model judgment as permanent
truth.

The design priority is:

\`current question > current-session state > persistent student model\`

Historical context can change **how** ANVAYA teaches. It must not silently
change **what** the student is currently asking.

## 2.2.1 — Read-Only Cross-Session Student Model

The first Tutor 2.2 unit is intentionally read-only.

Before a course-scoped Tutor turn, ANVAYA builds a bounded projection from:

1. previous Tutor sessions for the same course;
2. existing active \`learning_memory_entries\`;
3. existing \`topic_progress_events\` for the selected course/topic.

No new database table or migration is required.

No Tutor 2.2.1 code writes:

- learning memory;
- topic progress;
- mastery;
- grades;
- assessments;
- plans;
- notes;
- resources;
- retrieval indexes.

### Previous Tutor-session signals

At most 12 recent sessions for the same course are considered.

The current session is always excluded.

The projection can summarize:

- historical answer-status signals:
  - correct
  - partial
  - incorrect
  - unclear
- prior unresolved doubts;
- prior possible misconceptions;
- previous deterministic math outcomes:
  - verified
  - repaired
  - blocked

Sessions from another course are not included.

These are historical interaction signals, **not mastery measurements**.

### Existing ANVAYA memory/progress context

The projection may read up to five current learning-memory records and five
recent topic-progress events within the active course/topic scope.

Those rows remain authoritative in their existing domains. Tutor 2.2.1 only
reads them.

## Provider contract

Provider requests contain a separate section:

\`PERSISTENT STUDENT MODEL (historical/advisory only)\`

The Tutor system prompt explicitly states:

- the current question has highest priority;
- current-session state has second priority;
- persistent history is third;
- history may influence explanation style, prerequisite reminders and
  difficulty;
- historical signals are not proof of current mastery;
- an old doubt must never hijack a clearly new topic.

## UI

Tutor pages identify themselves as **ANVAYA Tutor 2.2**.

When historical context exists, a compact collapsed section appears:

\`Across sessions\`

It can show:

- number of earlier same-course sessions considered;
- historical answer signals;
- previous doubts;
- previous possible misconceptions;
- existing learning-memory context;
- existing progress context.

The UI explicitly labels the information:

\`Historical/advisory context only · not a mastery score.\`

## Safety / correctness boundary

Tutor 2.2 inherits all Tutor 2.1 protections:

- adaptive current-session state;
- structured answer evaluation;
- deterministic supported-math verification and repair;
- smarter retrieval;
- topic-shift handling;
- referenced-example continuity;
- provider-output hygiene;
- source-grounding policies.

Persistent context cannot weaken any of these.

## Next Tutor 2.2 units

### 2.2.2 Stable Signal Aggregation

Move beyond "latest state from earlier sessions" and aggregate repeated
evidence over time with explicit provenance and recency.

Examples:

- repeated misconception across multiple sessions;
- repeatedly correct answers on the same topic;
- repeated need for hints;
- calculation failures followed by later verified success.

Still no automatic mastery write.

### 2.2.3 Candidate Memory Promotion

Create explicit **candidate** long-term learning signals with:

- source Tutor sessions/turns;
- course/topic;
- signal kind;
- confidence;
- first/last observed timestamps;
- evidence count;
- status: proposed / accepted / rejected / superseded.

Promotion to authoritative learning memory must be reviewable and reversible.

### 2.2.4 Personalized Teaching Policy

Use stable accepted signals to adjust:

- prerequisite depth;
- explanation style;
- amount of scaffolding;
- practice difficulty;
- quiz progression;
- when to revisit a misconception.

### 2.2.5 Live Cross-Session Validation

Create one MA103N session, establish a real difficulty, close/reopen another
session, and verify that ANVAYA remembers the useful learning context without
repeating or forcing the old topic.
