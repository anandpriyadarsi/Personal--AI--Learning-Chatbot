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
