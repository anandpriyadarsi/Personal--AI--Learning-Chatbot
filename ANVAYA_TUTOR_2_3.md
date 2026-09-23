# ANVAYA Tutor 2.3 — Teaching Orchestration Architecture / Specification

**Status:** Draft  
**Depends on:** Tutor 2.2 Persistent Student Model — PASS  
**Purpose:** Move ANVAYA from an adaptive answer generator into a tutor that can deliberately run a learning session.

---

## 1. Goal

Tutor 2.3 should make ANVAYA decide **how to teach next**, not only how to answer the current message.

The core tutoring loop is:

```text
student goal / question
        ↓
diagnose current understanding
        ↓
choose next teaching move
        ↓
explain / ask / hint / practice
        ↓
evaluate response
        ↓
repair or advance
        ↓
check goal completion
```

Tutor 2.2 memory remains advisory. The **current question and current-session evidence stay authoritative**.

---

## 2. Core Principles

1. **Teach, do not merely answer.**
2. **Ask only useful diagnostic questions.**
3. **Do not over-question when the student clearly asks for a direct explanation.**
4. **Use the minimum prerequisite needed to unblock the current topic.**
5. **Increase difficulty only from current evidence, never from historical memory alone.**
6. **Keep teaching decisions deterministic and inspectable where possible.**
7. **Do not write mastery, progress, grades, plans, notes, vault files, or learning memory automatically.**
8. **Tutor 2.2 memory remains human-reviewed and advisory.**

Priority order:

```text
current question
    >
current-session learning state
    >
current session goal / teaching plan
    >
accepted + stable historical context
```

---

## 3. Proposed Architecture

### A. Session Goal

Each Tutor session may have a bounded learning goal, for example:

> Understand why elimination multipliers form L in LU factorization.

Store session-local fields such as:

- `session_goal`
- `goal_status`: `active | likely_met | unresolved`
- `goal_evidence`
- `goal_created_at`
- `goal_updated_at`

A session goal is not a mastery record.

### B. Teaching Plan

A deterministic planner chooses the next teaching move from:

- `explain`
- `ask_diagnostic`
- `give_hint`
- `ask_student_to_try`
- `repair_misconception`
- `review_prerequisite`
- `give_example`
- `practice`
- `quiz`
- `check_understanding`
- `summarize`
- `finish_goal`

The provider controls wording; ANVAYA controls the teaching move.

### C. Diagnostic Questioning

ANVAYA may ask one short diagnostic question when the student's exact gap is unclear.

### D. Socratic Multi-Turn Loop

ANVAYA should be able to teach a small idea, ask one question, wait, inspect the answer, then hint, repair, or advance.

### E. Concept Dependency / Prerequisite Reasoning

Introduce a bounded, explicit, course-scoped concept dependency layer.

### F. Adaptive Practice Sequencing

Practice should progress through bounded levels from concept check to challenge, with difficulty changes based on current evidence.

### G. Understanding / Exit Check

Use current-session evidence to mark a session goal as `active`, `likely_met`, or `unresolved`. Do not call this mastery.

---

## 4. Main Runtime Components

```text
Tutor request
    ↓
Adaptive State
    ↓
Persistent Student Model (Tutor 2.2)
    ↓
Session Goal
    ↓
Teaching Orchestrator
    ↓
Grounding / Retrieval
    ↓
Provider Request
    ↓
Tutor Response
    ↓
Current-session evidence update
```

Suggested modules:

```text
personal_learning_assistant/tutor/
    session_goal.py
    teaching_orchestrator.py
    diagnostic_planner.py
    concept_dependencies.py
    practice_sequencer.py
    goal_evaluator.py
```

Avoid placing orchestration logic directly in Flask routes or templates.

---

## 5. Tutor 2.3 Delivery Plan

- **2.3.1 — Session Goal + Teaching Plan**
- **2.3.2 — Diagnostic Questioning**
- **2.3.3 — Socratic Multi-Turn Loop**
- **2.3.4 — Prerequisite / Concept Dependency Reasoning**
- **2.3.5 — Adaptive Practice Sequencing**
- **2.3.6 — Understanding / Exit Check**
- **2.3.7 — Live Validation**

---

## 6. Trust / Write Boundary

Tutor 2.3 may write only Tutor-owned session state required for orchestration.

It must not automatically write long-term learning memory, mastery, topic progress, grades, academic plans, notes, resources, retrieval indexes, or Obsidian vault content.

Any future promotion from Tutor 2.3 evidence into long-term memory must continue to use the Tutor 2.2 human-review workflow.

---

## 7. Required Acceptance Criteria

Tutor 2.3 is complete only when ANVAYA can start/infer a useful session goal, choose appropriate teaching moves, preserve current-question priority, preserve Tutor 2.2 trust boundaries, pass regressions/protected-hash/repository-hygiene gates, and pass live browser validation.

---

## 8. First Implementation Rule

Do **not** begin with autonomous agents, voice, web browsing, large local models, or more long-term memory.

Tutor 2.3 should first prove:

> **Can ANVAYA conduct a coherent, multi-turn tutoring session that diagnoses, teaches, checks, repairs, and advances like a real tutor?**


---

## 2.3.1 — Session Goal + Teaching Plan

**Implementation status:** PASS — local gate validated on 2026-09-23.

### Session goal

Tutor 2.3.1 adds session-local goal state under:

\`tutor23_session_goal\`

The goal contains:

- bounded goal text;
- status (\`active | likely_met | unresolved\`);
- bounded goal evidence container for later Tutor 2.3 units;
- source (\`inferred\` or \`topic_shift\`);
- created/updated timestamps once persisted.

In 2.3.1 the goal status remains \`active\`; Tutor 2.3.6 will own goal-completion evaluation.

The first real Tutor request infers a goal deterministically. Ordinary follow-ups
reuse it. An explicit topic-shift request replaces it with a new session-local
goal.

### Deterministic teaching plan

Tutor 2.3.1 adds:

\`tutor23_teaching_plan\`

and chooses one bounded next teaching move from the Tutor 2.3 move vocabulary.

The first implementation intentionally chooses only moves that already have
safe Tutor behavior:

- \`explain\`
- \`give_hint\`
- \`give_example\`
- \`practice\`
- \`quiz\`
- \`check_understanding\`
- \`summarize\`
- \`repair_misconception\`

\`ask_diagnostic\`, \`review_prerequisite\`, and \`finish_goal\` are reserved
for later Tutor 2.3 units and are not autonomously selected by 2.3.1.

### Provider contract

Every grounded Tutor request now contains explicit sections:

\`SESSION GOAL (session-local orientation; not mastery/progress)\`

and:

\`TEACHING PLAN (deterministic orchestration; CURRENT QUESTION still controls)\`

The priority order is enforced as:

\`current question > current-session state > session goal/teaching plan > persistent history\`

### Persistence boundary

Goal and plan writes occur only inside \`tutor_sessions.metadata_json\`.

Tutor 2.3.1 does not automatically write:

- learning memory;
- mastery/progress;
- grades;
- plans;
- notes/resources;
- retrieval indexes;
- Obsidian vault content.

### UI

The Tutor conversation header now exposes a **Session goal** summary containing:

- current goal;
- goal status;
- last deterministic teaching move;
- plan reason;
- explicit statement that this is not mastery or academic progress.

### Gate

Run:

\`\`\`powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\tutor23_fix1_gate.ps1
\`\`\`

Do not begin Tutor 2.3.2 until this gate is completely green.

### 2.3.1 validation result

Local gate result on 2026-09-23:

```text
1375 passed
5 skipped
1 deselected

ANVAYA TUTOR 2.3.1 SESSION GOAL + TEACHING PLAN: PASS
```

Validated properties:

- session-goal inference;
- goal continuity across ordinary follow-ups;
- explicit topic-shift goal replacement;
- deterministic teaching-move selection;
- current-question priority over orchestration/history;
- Tutor 2.2 memory/personalization compatibility;
- Tutor 2.1 adaptive/correctness/retrieval compatibility;
- provider-output hygiene;
- protected production/index/vault hashes;
- repository hygiene.

Tutor 2.3.1 is therefore **COMPLETE**.


---

## 2.3.2 — Diagnostic Questioning

**Implementation status:** PASS — local gate validated on 2026-09-23.

### Purpose

Tutor 2.3.2 allows ANVAYA to ask **one short diagnostic question** before
teaching only when the student's initial gap is genuinely unclear.

Examples that may trigger diagnosis:

- \`I don't understand LU factorization.\`
- \`I'm confused about basis.\`
- \`Help me with determinants.\`
- a bare initial topic such as \`LU factorization\`

Examples that must bypass diagnosis:

- \`Explain LU factorization.\`
- \`Explain why elimination multipliers enter L.\`
- \`How is L constructed?\`
- explicit hint/example/practice/quiz/verification requests;
- a current-session misconception or unresolved doubt that already identifies
  the gap.

### Bounded behavior

Tutor 2.3.2 automatically diagnoses only an **initial ambiguous request**.

It does not yet own pending diagnostic state or interpret the student's answer
to that question. Those multi-turn semantics belong to Tutor 2.3.3.

The deterministic diagnostic question is intentionally simple:

\`Which part is blocking you most: the core idea, how the steps work, or why the method works?\`

The current session goal supplies the topic phrase.

### Teaching-plan integration

When diagnosis is required:

\`\`\`text
next_move = ask_diagnostic
reason = initial_gap_unclear
student_action_expected = true
diagnostic_question = <bounded exact question>
\`\`\`

The provider is instructed to:

- ask exactly the supplied question;
- ask only one diagnostic question;
- stop after the question;
- wait for the student's response;
- not begin the explanation yet.

### Priority / bypass rules

Explicit current intent always wins over diagnostic logic.

\`\`\`text
explicit hint/example/practice/quiz/check request
    >
known current-session misconception/doubt
    >
initial ambiguity diagnosis
    >
ordinary explanation
\`\`\`

This remains inside the wider Tutor 2.3 hierarchy:

\`current question > current-session state > session goal/teaching plan > persistent history\`

### Persistence / trust boundary

No new database migration is introduced.

The diagnostic decision is stored only as part of the existing
\`tutor23_teaching_plan\` in Tutor session metadata.

Tutor 2.3.2 does not automatically write learning memory, mastery, progress,
grades, study plans, notes/resources, retrieval indexes, or Obsidian vault
content.

### UI

When the current teaching move is \`Ask Diagnostic\`, the Tutor session summary
shows the exact planned diagnostic question for inspection.

### Gate

Run:

\`\`\`powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\tutor23_fix2_gate.ps1
\`\`\`

Do not begin Tutor 2.3.3 until this gate is completely green.

### 2.3.2 validation result

Local gate result on 2026-09-23:

```text
1389 passed
5 skipped
1 deselected

ANVAYA TUTOR 2.3.2 DIAGNOSTIC QUESTIONING: PASS
```

Validated properties:

- bounded diagnostic questioning for ambiguous first-turn confusion;
- bypass for explicit explanation/hint/example/practice/quiz/check requests;
- known current-session misconception/doubt takes priority over diagnosis;
- one-question provider contract;
- inspectable diagnostic question in Tutor session state/UI;
- Tutor 2.3.1 session-goal and teaching-plan compatibility;
- Tutor 2.2 memory/personalization compatibility;
- Tutor 2.1 adaptive/correctness/retrieval compatibility;
- Tutor 2.0 grounded/safety behavior;
- protected production/index/vault hashes;
- repository hygiene.

Tutor 2.3.2 is therefore **COMPLETE**.


---

## 2.3.3 — Socratic Multi-Turn Loop

**Implementation status:** PASS — local gate validated on 2026-09-23.

### Purpose

Tutor 2.3.3 turns a pedagogical question into a real multi-turn Tutor loop:

\`\`\`text
ANVAYA asks one bounded question
        ↓
pending question is stored in Tutor session state
        ↓
student replies
        ↓
reply is recognized as the answer to that question
        ↓
answer is evaluated
        ↓
advance / clarify / repair / unclear
        ↓
at most one next check question
\`\`\`

### Session-local state

The existing adaptive Tutor state is extended rather than creating a second
conversation-state system.

New bounded fields include:

- \`pending_question_kind\`: \`diagnostic | quiz | socratic_check\`;
- \`last_socratic_outcome\`: \`advance | clarify | repair | unclear\`;
- \`socratic_step_count\`.

The existing fields remain authoritative for the active exchange:

- \`awaiting_student_answer\`;
- \`pending_question\`;
- \`last_student_answer\`;
- \`answer_status\`;
- \`last_evaluation_reason\`;
- \`last_misconception\`.

All state remains inside Tutor session metadata.

### Diagnostic continuity

A Tutor 2.3.2 diagnostic question is now persisted as a genuine pending Tutor
question.

The deterministic diagnostic question is returned directly without spending a
provider call. This guarantees exactly one question and also allows a
diagnostic question in \`source_only\` mode even when no academic evidence was
retrieved.

### Answer handling

When a pending Tutor question exists, a normal short reply is treated as an
answer to that question.

The provider receives the pending question, the student's answer, and the
existing hidden evaluation protocol.

The evaluation maps deterministically to:

\`\`\`text
correct   -> advance
partial   -> clarify
incorrect -> repair
unclear   -> unclear
\`\`\`

The provider is instructed to respond to that outcome without restarting the
topic and to ask **at most one** next pedagogical question.

### Student control

The student can escape the loop.

Requests such as:

- \`Just explain it.\`
- \`Skip the question.\`
- \`Don't ask me.\`
- \`Give me the explanation.\`

cancel the pending pedagogical question and restore direct current-request
behavior.

An explicit topic shift also clears the old pending question.

A requested hint preserves the pending question so the student can still answer
it afterward.

### Boundaries

Tutor 2.3.3 does not introduce:

- prerequisite graphs;
- adaptive practice difficulty;
- mastery or goal-completion decisions;
- automatic long-term learning memory;
- academic progress writes.

Those remain later Tutor 2.3 units.

### UI

The current learning-state panel exposes:

- pending Tutor question;
- pending-question kind;
- last Socratic outcome;
- Socratic loop step count.

These labels are session-local diagnostics, not mastery judgments.

### Gate

Run:

\`\`\`powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\tutor23_fix3_gate.ps1
\`\`\`

Do not begin Tutor 2.3.4 until this gate is completely green.

### 2.3.3 validation result

Local gate result on 2026-09-23:

```text
1402 passed
5 skipped
1 deselected

ANVAYA TUTOR 2.3.3 SOCRATIC MULTI-TURN LOOP: PASS
```

Validated properties:

- pending-question continuity across Tutor turns;
- diagnostic-answer evaluation;
- bounded Socratic outcomes: advance / clarify / repair / unclear;
- at-most-one next pedagogical question;
- student override of pending questions;
- hint-without-consuming-pending-question behavior;
- explicit topic-shift cancellation;
- adaptive quiz lineage compatibility;
- Tutor 2.3.2 diagnostic compatibility;
- Tutor 2.3.1 session-goal/teaching-plan compatibility;
- Tutor 2.2 memory/personalization compatibility;
- Tutor 2.1 adaptive/correctness/retrieval compatibility;
- Tutor 2.0 grounding/safety behavior;
- protected production/index/vault hashes;
- repository hygiene.

Tutor 2.3.3 is therefore **COMPLETE**.


---

## 2.3.4 — Prerequisite / Concept Dependency Reasoning

**Implementation status:** PASS — local gate validated on 2026-09-23.

### Purpose

Tutor 2.3.4 lets ANVAYA recognize when the current difficulty is not the target
topic itself but a smaller prerequisite concept.

The bounded loop is:

\`\`\`text
current session goal
        ↓
current question + current-session evidence
        ↓
course-scoped dependency graph
        ↓
is one prerequisite gap explicitly justified?
        ↓
yes → review only that prerequisite
        ↓
bridge back to the original target / session goal
\`\`\`

ANVAYA must not recursively walk backward through an arbitrary dependency tree.

### Course-scoped dependency graph

Dependencies are explicit, inspectable, and keyed by canonical course code.

The initial conservative graph includes selected stable relationships for:

- \`MA103N\` Linear Algebra;
- \`UC100N\` Data Science and AI;
- \`CY100N\` Engineering Chemistry.

The graph is deliberately small. New edges should be added from authoritative
course material rather than by broad model inference.

Examples in the initial graph include:

\`\`\`text
MA103N
LU Factorization
    <- Gaussian Elimination
    <- Elimination Multipliers
    <- Matrix Multiplication

Basis
    <- Span
    <- Linear Independence

Coordinate Representation
    <- Basis
    <- Linear Independence
\`\`\`

### Canonical academic scope

Tutor 2.3.4 reads canonical scope through the existing Tutor repository:

- \`course_identity()\`;
- \`topic_identity()\`;
- \`list_course_topics()\`.

No new database migration or authoritative academic-data write is introduced.

If no canonical course scope exists, automatic prerequisite reasoning is
disabled.

A dependency graph for one course cannot leak into another course.

### When prerequisite repair is allowed

ANVAYA may select one prerequisite when either:

1. the current student message explicitly identifies confusion with a known
   prerequisite of the current target; or
2. current-session Socratic evidence is \`clarify | repair | unclear\` and the
   recorded misconception/evaluation identifies a known prerequisite.

Examples:

\`\`\`text
"I don't understand elimination multipliers in LU factorization."
    -> review Elimination Multipliers
    -> return to LU Factorization
\`\`\`

\`\`\`text
Current goal: LU Factorization
Last Socratic outcome: repair
Misconception: "Student does not understand Gaussian elimination."
    -> review Gaussian Elimination
    -> return to LU Factorization
\`\`\`

### What must not trigger it

Tutor 2.3.4 must not automatically move backward merely because the target has
prerequisites.

For example:

\`\`\`text
"Explain LU factorization."
\`\`\`

does not itself justify prerequisite review.

Explicit requests such as hint, example, practice, quiz, summary, verification,
or guidance remain authoritative and are not replaced by prerequisite review.

If the gap is vague rather than known, Tutor 2.3.2 Diagnostic Questioning still
wins.

### Teaching plan

When prerequisite repair is justified:

\`\`\`text
next_move = review_prerequisite
target_concept = <current target>
prerequisite_concept = <one justified prerequisite>
prerequisite_reason =
    explicit_prerequisite_gap
    | current_session_prerequisite_gap
return_to_goal = true
\`\`\`

The provider is instructed to:

- teach only the minimum prerequisite required now;
- explicitly connect it back to the target;
- return to the original session goal;
- avoid opening another prerequisite branch in the same turn.

### Retrieval behavior

When the dependency maps to a canonical prerequisite topic, retrieval
temporarily uses that prerequisite topic while preserving the same course
scope.

A bounded retrieval query is appended:

\`\`\`text
<prerequisite> prerequisite for <target>
\`\`\`

If no canonical prerequisite topic exists, the existing session topic scope is
retained.

### Trust / persistence boundary

Tutor 2.3.4 persists only the resulting teaching plan in existing Tutor session
metadata.

It does not automatically write:

- mastery;
- academic progress;
- learning memory;
- grades;
- study plans;
- notes/resources;
- retrieval indexes;
- Obsidian vault content.

The concept graph itself is code-owned orchestration configuration, not student
academic state.

### UI

The Tutor session goal panel exposes a compact prerequisite bridge:

\`\`\`text
Prerequisite repair: Gaussian Elimination -> LU Factorization
\`\`\`

This is an orchestration explanation, not a mastery judgment.

### Gate

Run:

\`\`\`powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\tutor23_fix4_gate.ps1
\`\`\`

Do not begin Tutor 2.3.5 until this gate is completely green.

### 2.3.4 validation result

Local gate result on 2026-09-23:

```text
1418 passed
5 skipped
1 deselected

ANVAYA TUTOR 2.3.4 PREREQUISITE / CONCEPT DEPENDENCY REASONING: PASS
```

Validated properties:

- course-scoped dependency reasoning;
- bounded one-prerequisite repair;
- canonical prerequisite-topic retrieval scope;
- explicit return-to-goal planning;
- known prerequisite gaps overriding generic diagnosis;
- vague gaps continuing through Tutor 2.3.2 diagnosis;
- Tutor 2.3.3 Socratic continuity compatibility;
- Tutor 2.3.2 diagnostic compatibility;
- Tutor 2.3.1 session-goal/teaching-plan compatibility;
- Tutor 2.2 memory/personalization compatibility;
- Tutor 2.1 adaptive/correctness/retrieval compatibility;
- Tutor 2.0 grounding/safety behavior;
- protected production/index/vault hashes;
- repository hygiene.

Tutor 2.3.4 is therefore **COMPLETE**.


---

## 2.3.5 — Adaptive Practice Sequencing

**Implementation status:** Built; awaiting local gate validation.

### Purpose

Tutor 2.3.5 gives ANVAYA a bounded practice ladder so practice is not a stream
of unrelated randomly difficult questions.

The session-local ladder is:

\`\`\`text
1  Concept check
2  Guided application
3  Standard application
4  Mixed / transfer application
5  Challenge
\`\`\`

These levels are orchestration labels only. They are not mastery, ability,
intelligence, grades, or academic progress.

### Starting level

The current session remains authoritative.

When a new practice sequence starts, Tutor 2.2 personalized policy may provide
an advisory starting bias:

\`\`\`text
supported -> level 2
standard  -> level 3
challenge -> level 4
\`\`\`

Tutor 2.2 historical context cannot by itself start at level 5 and cannot prove
that the student is strong or weak.

An explicit current request such as \`harder\`, \`easier\`, \`conceptual\`, or
\`computational\` remains authoritative.

### One-step adaptation

After an evaluated practice answer:

\`\`\`text
correct   -> one level up
partial   -> hold level
incorrect -> one level down
unclear   -> one level down
\`\`\`

Levels are clamped to 1..5.

One answer can never change difficulty by more than one level.

### Practice formats

Tutor 2.3.5 supports bounded task formats:

- \`conceptual\`;
- \`computational\`;
- \`mixed\`;
- \`misconception_targeted\`;
- \`prerequisite_bridge\`.

If current-session evidence records a misconception, the next relevant
practice may target that misconception.

After Tutor 2.3.4 repairs a prerequisite, a later practice request may become a
\`prerequisite_bridge\` task that reconnects the repaired prerequisite to the
original session goal.

Explicit student format requests remain authoritative.

### Multi-turn practice loop

Practice now participates in the existing Tutor 2.3 Socratic pending-question
state.

\`\`\`text
ANVAYA gives one practice task
        ↓
pending_question_kind = practice
        ↓
student attempts it
        ↓
hidden evaluation
        ↓
correct / partial / incorrect / unclear
        ↓
bounded level transition
        ↓
brief feedback + at most one next practice task
\`\`\`

Initial imperative tasks such as \`Compute ...\` can still be tracked even if
they do not end with a question mark.

After an evaluated answer, continuation requires a real next question. This
prevents ordinary feedback prose from accidentally becoming a pending task.

A requested hint preserves the pending practice task.

An explicit topic shift clears the old practice sequence.

### Teaching-plan fields

Tutor 2.3.5 extends the existing Tutor teaching plan with:

\`\`\`text
practice_active
practice_level
practice_level_name
practice_format
practice_focus
practice_reason
practice_after_correct_level
practice_after_partial_level
practice_after_incorrect_level
practice_after_unclear_level
\`\`\`

For an answer inside an active practice loop:

\`\`\`text
next_move = practice
reason = adaptive_practice_answer
\`\`\`

The provider must evaluate the current answer before generating the one next
task.

### Existing quiz behavior

Tutor 2.3.5 does not silently redefine the existing quiz lineage.

\`pending_question_kind=quiz\` remains a quiz and continues through the Tutor
2.1 / Tutor 2.3.3 quiz/Socratic behavior.

Adaptive practice sequencing is owned by
\`pending_question_kind=practice\`.

### Priority

The relevant priority is:

\`\`\`text
explicit current practice request
    >
current-session answer / misconception evidence
    >
Tutor 2.3.4 prerequisite repair when strongly justified
    >
existing session practice level
    >
Tutor 2.2 historical policy
\`\`\`

If Tutor 2.3.4 has strong evidence that a prerequisite is blocking the current
work, prerequisite repair may pause practice. The next practice request can
then bridge back to the target.

### Persistence / trust boundary

Tutor 2.3.5 extends only Tutor-owned session metadata.

Session-local adaptive state includes:

- \`practice_active\`;
- \`practice_level\`;
- \`practice_step_count\`;
- \`practice_format\`;
- \`practice_focus\`.

It does not automatically write:

- mastery;
- academic progress;
- grades;
- long-term learning memory;
- study plans;
- notes/resources;
- retrieval indexes;
- Obsidian vault content.

### UI

The Tutor learning-state panel exposes the current practice sequence as
session-local information:

\`\`\`text
Practice sequence: Level 3 · Computational
Practice steps: 2 · Session-local, not mastery
\`\`\`

The teaching-plan panel also exposes the planned practice level, format, and
reason.

### Gate

Run:

\`\`\`powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\tutor23_fix5_gate.ps1
\`\`\`

Do not begin Tutor 2.3.6 until this gate is completely green.


---

## 2.3.6 — Understanding / Exit Check

**Implementation status:** PASS — local gate validated on 2026-09-23.

### Purpose

Tutor 2.3.6 lets ANVAYA close a Tutor session goal conservatively.

It answers a narrower question than mastery:

> Based on evidence from this Tutor session, does the current goal appear met
> well enough to close, or is something still unresolved?

The only allowed goal states remain:

\`\`\`text
active
likely_met
unresolved
\`\`\`

\`likely_met\` is a session-local orchestration conclusion only.

It is not:

- mastery;
- a topic-progress update;
- a grade;
- a learning-memory promotion;
- a claim about intelligence or ability.

### Self-report is not enough

Statements such as:

\`\`\`text
"I understand now."
"Got it."
"That makes sense."
\`\`\`

do **not** directly set the goal to \`likely_met\`.

Instead, they may trigger one bounded exit check.

This protects ANVAYA from confusing confidence with demonstrated
understanding.

### Explicit exit-check requests

The student may also request the check directly:

\`\`\`text
"Check if I understand this."
"Check my understanding."
"Am I ready to move on?"
\`\`\`

If another Tutor question is already pending, ANVAYA does not open a competing
exit check.

### Exit-check question

Tutor 2.3.6 generates one bounded session-goal check:

\`\`\`text
Before we close this session goal, explain in your own words the key idea or
method you would use for: <current session goal>?
\`\`\`

The question is stored with:

\`\`\`text
pending_question_kind = exit_check
\`\`\`

It uses the existing Tutor pending-question and hidden answer-evaluation
machinery.

The check is deliberately one-shot. Tutor 2.3.6 does not create an endless
exit-check quiz loop.

### Exit-check result

After the student's answer is evaluated:

\`\`\`text
correct
    -> goal status = likely_met

partial
incorrect
unclear
    -> goal status = unresolved
\`\`\`

A mathematically blocked answer cannot produce \`likely_met\`, even if the
provider's semantic evaluation says \`correct\`.

If no usable evaluation is available, the goal remains \`active\`.

### Goal evidence

Tutor 2.3.6 records only bounded session-local goal evidence, for example:

\`\`\`text
exit_check_correct: Correctly explains why L stores elimination multipliers.
exit_check_partial: Understands U but not where L comes from.
student_reported_unresolved: I am still confused about the sign in L.
\`\`\`

The evidence is stored inside the existing Tutor session goal metadata and is
bounded to a small history.

It is not written into academic progress or long-term learning memory.

### Reopening a goal

A goal that was previously \`likely_met\` may become \`unresolved\` again if
the student explicitly reports current confusion, for example:

\`\`\`text
"I am still confused about why the multiplier has a positive sign in L."
\`\`\`

This is intentional.

Tutor 2.3.6 treats current evidence as more important than an earlier
session-local conclusion.

An explicit topic shift still creates a new active session goal through Tutor
2.3.1 behavior.

### Teaching-plan integration

When an exit check is requested:

\`\`\`text
next_move = check_understanding
reason =
    student_reports_understanding
    | explicit_exit_check_requested
exit_check_question = <one bounded question>
\`\`\`

When the student answers that check:

\`\`\`text
next_move = finish_goal
reason = pending_exit_check_answer
\`\`\`

\`finish_goal\` means "evaluate the exit check and update the session-local goal
status." It does not mean "declare mastery."

### Source policy

The deterministic exit-check question may be asked even in \`source_only\`
mode when retrieval is empty.

This is allowed because the question does not introduce unsupported academic
content; it asks the student to demonstrate the current session goal.

The student's answer is still evaluated under the normal Tutor provider,
grounding, correctness, and safety rules.

### Persistence / trust boundary

Tutor 2.3.6 writes only existing Tutor-owned session metadata:

- session goal status;
- bounded goal evidence;
- pending exit-check state;
- exit-check count;
- ordinary Tutor answer-evaluation state.

It does not automatically write:

- mastery;
- topic progress;
- grades;
- study plans;
- learning memory;
- notes/resources;
- retrieval indexes;
- Obsidian vault content.

Any future long-term promotion still belongs to the existing Tutor 2.2
human-review workflow.

### UI

The Session Goal panel now exposes:

- current goal;
- \`Active\`, \`Likely Met\`, or \`Unresolved\`;
- the planned exit-check question when applicable;
- bounded goal evidence;
- explicit wording that \`Likely Met\` is current-session evidence only and not
  mastery.

The Current Learning State panel also exposes the number of session-local exit
checks asked.

### Gate

Run:

\`\`\`powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\tutor23_fix6_gate.ps1
\`\`\`

Do not begin Tutor 2.3.7 live validation until this gate is completely green.

### 2.3.6 validation result

Local gate result on 2026-09-23:

```text
1466 passed
5 skipped
1 deselected

ANVAYA TUTOR 2.3.6 UNDERSTANDING / EXIT CHECK: PASS
```

Validated properties:

- one-shot session-goal exit checks;
- self-reported understanding does not directly close a goal;
- mixed "I understand X, but why Y?" requests remain normal Tutor questions;
- correct exit-check answers can set only `likely_met`;
- partial / incorrect / unclear checks set `unresolved`;
- current confusion can reopen a previously `likely_met` goal;
- Source Only exit-check behavior;
- Tutor 2.3.5 adaptive-practice compatibility;
- Tutor 2.3.4 prerequisite-reasoning compatibility;
- Tutor 2.3.3 Socratic continuity compatibility;
- Tutor 2.3.2 diagnostic compatibility;
- Tutor 2.3.1 session-goal/teaching-plan compatibility;
- Tutor 2.2 memory/personalization compatibility;
- Tutor 2.1 adaptive/correctness/retrieval compatibility;
- Tutor 2.0 grounding/safety behavior;
- protected production/index/vault hashes;
- repository hygiene.

Tutor 2.3.6 is therefore **COMPLETE**.
