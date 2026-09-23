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

**Implementation status:** Built; awaiting local gate validation.

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
