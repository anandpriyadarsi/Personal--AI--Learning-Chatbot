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

## 2.2.2 — Stable Signal Aggregation

Tutor 2.2 now records a bounded event history inside each Tutor session's
existing \`metadata_json\` under:

\`tutor_signal_history_v1\`

No new SQLite table or migration is required.

Each completed Tutor turn can deterministically produce observations such as:

- \`answer_correct\`
- \`answer_partial\`
- \`answer_incorrect\`
- \`answer_unclear\`
- \`hint_requested\`
- \`doubt\`
- \`misconception\`
- \`math_verified\`
- \`math_repaired\`
- \`math_blocked\`

Each event carries bounded provenance:

- Tutor session id;
- assistant turn id;
- course id;
- topic id when present;
- teaching intent;
- observation timestamp;
- short signal text where applicable.

Each session keeps at most 40 normalized events. Re-appending the same
turn/kind/text observation is idempotent.

### Stable-pattern threshold

A signal becomes a **stable cross-session pattern** only when matching evidence
exists in at least **two distinct previous Tutor sessions**.

One session is never enough.

The aggregate records:

- signal kind;
- optional normalized text;
- course/topic scope;
- event count;
- distinct session count;
- first observed timestamp;
- last observed timestamp;
- bounded source session/turn provenance.

When an explicit topic is selected, historical Tutor sessions are restricted to
that same topic before aggregation. Basis history cannot become LU history just
because both belong to MA103N.

### Legacy-session compatibility

Older Tutor 2.1 sessions do not contain event histories.

For those sessions, Tutor 2.2 can project a small fallback observation set from
their final adaptive state so existing history remains useful. New sessions use
the richer per-turn event history.

### Provider and UI use

Stable patterns are included in the persistent model as advisory context, for
example:

\`stable_cross_session_signal=kind=hint_requested; sessions=2; events=3; ...\`

The Tutor may use that pattern to decide that more scaffolding could be useful,
but it still may not claim mastery or weakness as a fact.

The **Across sessions** UI shows stable patterns compactly with session count,
observation count, optional text, and last-observed time.

### Write boundary

Tutor 2.2.2 writes only to Tutor-session metadata.

It still does **not** write:

- learning memory;
- topic progress;
- mastery;
- grades;
- assessments;
- plans;
- notes;
- resources;
- retrieval indexes.

Stable signals are observations, not authoritative academic state.

## Next Tutor 2.2 units

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
