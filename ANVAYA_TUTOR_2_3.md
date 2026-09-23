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

**Implementation status:** Built; awaiting local gate validation.

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
