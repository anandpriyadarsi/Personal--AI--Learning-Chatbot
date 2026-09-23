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

## 2.2.3 — Candidate Memory Promotion

Stable Tutor patterns can now enter an explicit human-review workflow.

A new migration, \`0009_tutor_memory_candidates.sql\`, adds
\`tutor_memory_candidates\`.

Candidate records contain:

- course/topic scope;
- originating stable signal kind;
- candidate memory kind/text;
- confidence from bounded deterministic evidence counts;
- distinct session count;
- total observation count;
- first/last observed timestamps;
- JSON provenance back to Tutor session/turn references;
- review status;
- optional review note;
- accepted learning-memory entry id when applicable;
- supersession link when a newer evidence window replaces an older proposal.

Supported statuses are:

- \`proposed\`
- \`accepted\`
- \`rejected\`
- \`superseded\`

### Proposal is explicit

A stable pattern does **not** automatically become a candidate.

The **Across sessions** UI exposes a \`Propose memory\` action for each stable
cross-session pattern.

The browser sends only the stable-pattern index. The server recomputes the
persistent student model and resolves the pattern from authoritative SQLite
state rather than trusting arbitrary candidate text posted by the browser.

Proposal writes only a \`tutor_memory_candidates\` row.

It does not write \`learning_memory_entries\`.

### Candidate identity and supersession

Exact reproposal of the same evidence window is idempotent.

If the same pattern gathers newer evidence while an older version is still
\`proposed\`, the older proposal is retained as \`superseded\` and the new
candidate links back to it.

Accepted or rejected history is never rewritten merely because new evidence
arrives.

### Human review

A proposed candidate can be explicitly:

- **Accept memory**
- **Reject**

Both actions can include an optional review note.

Rejecting changes only candidate review state.

Accepting performs one atomic transaction that:

1. verifies the candidate is still \`proposed\`;
2. creates exactly one \`learning_memory_entries\` row;
3. links the memory row back with
   \`source_entity_type='tutor_memory_candidate'\`;
4. records the candidate id as \`source_entity_id\`;
5. updates the candidate to \`accepted\`;
6. records the accepted memory entry id and review timestamp.

A reviewed candidate cannot be accepted/rejected again.

### Memory kinds

Stable signals map deterministically to candidate memory kinds, for example:

- misconception -> \`misconception\`
- recurring doubt -> \`recurring_doubt\`
- repeated hint use -> \`scaffolding_need\`
- repeated partial/incorrect answers -> \`practice_need\`
- repeated correct answers -> \`demonstrated_strength\`
- repeated repaired calculations -> \`calculation_review_need\`
- repeated blocked calculations -> \`calculation_risk\`

These labels remain reviewable learning context, not grades or mastery scores.

### Trust boundary

Tutor 2.2.3 may write:

- Tutor session metadata signal history;
- reviewable Tutor memory candidates;
- one long-term learning-memory row **only after explicit acceptance**.

It still does not automatically write:

- topic progress;
- mastery;
- grades;
- assessments;
- plans;
- notes;
- resources;
- retrieval indexes.

## Next Tutor 2.2 units

## 2.2.4 — Personalized Teaching Policy

Tutor 2.2 now derives an explicit deterministic teaching policy before each
provider request.

The policy controls only **how ANVAYA teaches the current question**.

It does not choose a different topic, create mastery, update progress, or write
learning memory.

### Policy inputs

The policy reads:

1. contextualized current-session state;
2. accepted/existing learning-memory context already visible in the persistent
   student model;
3. stable cross-session Tutor signals;
4. the current teaching intent.

The existing priority remains unchanged:

\`current question > current-session state > persistent history\`

A clear topic shift therefore clears stale session-local confusion anchors
before personalization is calculated.

### Deterministic policy fields

Each Tutor request carries:

- \`scaffolding\`
  - standard
  - guided
  - light
- \`prerequisite_depth\`
  - normal
  - brief_reinforcement
  - reinforce
  - minimal
- \`explanation_style\`
  - balanced
  - intuition_then_steps
  - concise_then_challenge
- \`practice_difficulty\`
  - standard
  - supported
  - challenge
- \`quiz_progression\`
  - normal
  - hold
  - slow
  - advance
- bounded possible misconceptions to revisit;
- deterministic policy reasons.

### Conservative adaptation rules

Repeated support signals such as:

- recurring misconception;
- recurring doubt;
- repeated hint use;
- partial/incorrect/unclear answers;
- repaired or blocked calculations;

can increase scaffolding, add a brief prerequisite reminder, keep practice at
the same/easier level, or slow quiz progression.

Historical success alone can **never** increase difficulty.

A modest challenge is allowed only when:

1. the current session shows recent success, such as a correct answer or
   verified calculation; and
2. repeated historical strength also exists.

Current confusion always overrides historical strength.

### Misconception handling

Accepted/stable misconception context may be passed as a possible item to
revisit.

The provider is explicitly instructed to revisit it only when directly
relevant to the current question. It may not hijack a new topic.

### Provider contract

Provider requests now contain:

\`PERSONALIZED TEACHING POLICY (style only; CURRENT QUESTION still controls)\`

The section includes the deterministic policy plus explicit constraints such
as:

- never replace the current question with an old topic;
- never describe historical signals as proof of mastery, weakness,
  intelligence, or ability;
- use smaller steps when guided scaffolding is active;
- increase challenge by at most one modest step when challenge mode is valid.

The same policy is stored in provider-request metadata and in the
\`GroundingPlan\`, so rebuilt provider requests cannot silently drift from the
original plan.

### Write boundary

Building and applying the personalized teaching policy is read-only.

Tutor 2.2.4 performs no additional writes to:

- Tutor memory candidates;
- learning memory;
- topic progress;
- mastery;
- grades;
- plans;
- notes;
- resources;
- retrieval indexes;
- the Obsidian vault.

## 2.2.5 — Live Cross-Session Validation

Status: **PASS — live validated on 2026-09-23**

The disposable local-web validation demonstrated:

- canonical topic isolation for LU Factorization;
- repeated Tutor observations across distinct sessions;
- stable cross-session signal aggregation;
- historical support signals changing teaching style in a fresh session;
- current-question/topic priority over historical context;
- explicit candidate acceptance creating provenance-linked learning memory;
- explicit rejection creating no additional accepted memory;
- accepted memory surviving into later Tutor sessions;
- user-visible personalization without labelling the student as weak/strong or
  presenting history as a mastery score;
- rendered Markdown/LaTeX and stable local runtime during the validated flow.

Detailed evidence and the reproducible validation protocol are recorded in
`ANVAYA_TUTOR_2_2_LIVE_VALIDATION.md`.

## Tutor 2.2 status

Tutor 2.2 units are complete:

- 2.2.1 Read-Only Cross-Session Student Model — PASS
- 2.2.2 Stable Signal Aggregation — PASS
- 2.2.3 Candidate Memory Promotion — PASS
- 2.2.4 Personalized Teaching Policy — PASS
- 2.2.5 Live Cross-Session Validation — PASS

The final `tutor22_gate.ps1` must remain green before starting Tutor 2.3.
