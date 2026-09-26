# Assessment Studio Phase D — Implementation Report

## Result

Assessment Studio Phase D — Evaluation Engine is implemented from the verified Phase C baseline:

`phase7.5.assessment-studio-c/timed-test-runner @ 50cfe500dbed6393987a61384f5fa43795c8655e`

The production target branch is:

`phase7.5.assessment-studio-d/evaluation-engine`

Phase D has not been merged into `main`.

## Delivered

Phase D adds a signed, auditable evaluation layer for terminal Phase C test sessions.

Implemented capabilities include:

- migration `0012_assessment_evaluation_engine.sql`;
- session-level evaluation records;
- per-response evaluation records;
- signed scores that preserve negative marking;
- backward-compatible signed-score/evaluation references on canonical `question_attempts`;
- deterministic MCQ evaluation;
- deterministic MSQ evaluation;
- proportional MSQ partial credit when `scoring_policy=partial`;
- configured negative marking;
- decimal-normalized numerical evaluation;
- whitespace/case-normalized fill evaluation;
- normalized True/False evaluation;
- `custom` scoring routed to explicit review rather than guessed;
- subjective rubric review;
- rubric-version hashes tied to the Phase C snapshot;
- manual/user and teacher grading;
- Alex/ChatGPT-assisted provisional grading;
- mandatory human confirmation before an Alex grade becomes final;
- canonical question-attempt creation only for auto-confirmed/final grades;
- mistake classification;
- provisional Alex mistake classification with explicit confirmation;
- canonical `mistake_events` synchronization;
- evaluation audit events;
- result and rubric-review web pages;
- terminal session-summary handoff through **Evaluate / Open Results**.

## Signed-score compatibility

Legacy `question_attempts.earned_marks_milli` remains non-negative for backward compatibility.

Phase D adds `signed_score_milli` and treats it as authoritative for Phase D evaluation.

For a −1 mark question:

- `earned_marks_milli = 0`;
- `signed_score_milli = -1000`.

The session result is calculated from response-evaluation signed scores, not by summing the legacy earned-credit column.

Phase D does not automatically write `assessments.earned_points_milli`, because that legacy field cannot represent a negative result and an assessment can have multiple test sessions.

## Objective scoring contract

Deterministic rules are documented in `ASSESSMENT_STUDIO_PHASE_D.md`.

Important rules:

- blank response → 0, auto-confirmed `unanswered`;
- exact MCQ → full marks;
- wrong MCQ → configured negative penalty;
- exact MSQ → full marks;
- partial-policy MSQ selecting only a strict subset of correct options → proportional credit;
- partial-policy MSQ selecting any incorrect option → configured negative penalty;
- standard/all-or-nothing MSQ incomplete correct-only subset → zero;
- numerical answers use decimal normalization;
- fill answers use case-insensitive collapsed-whitespace normalization;
- True/False accepts normalized common forms;
- custom policy is never guessed.

## Subjective and external-AI grading

Subjective/custom responses enter `awaiting_review`.

The review page displays the immutable:

- question snapshot;
- response;
- solution;
- rubric;
- rubric version.

Evaluator types are:

- user;
- teacher;
- Alex/ChatGPT.

Alex/ChatGPT evaluation is always provisional. Even if the form asks for final confirmation, the service preserves provisional state until a separate user confirmation action.

A provisional grade does not create a canonical question attempt.

Confirmation creates the canonical attempt exactly once.

## Mistake classification

Supported categories are:

- concept gap;
- formula recall;
- calculation error;
- misread;
- wrong method;
- incomplete reasoning;
- time pressure;
- careless;
- guessing;
- other.

User/teacher classifications are final immediately.

Alex/ChatGPT classifications are provisional until explicitly confirmed.

Confirmed classifications synchronize to `mistake_events` once a confirmed question attempt exists.

## Academic evidence boundary

Phase D creates assessment evidence only:

- confirmed `question_attempts`;
- confirmed `mistake_events`.

It does not create or modify:

- `topic_progress_events`;
- mastery/topic status;
- learning-memory mastery state;
- `study_plan_items`;
- planner recommendations;
- planner schedules.

These remain Phase E/F responsibilities.

## Validation

Clean GitHub validation of the implementation head completed successfully with:

- focused Assessment Studio Phase D: **12 passed**;
- Phase A/B/C + existing assessment regressions: **38 passed**;
- SQLite schema + recovery regressions: **22 passed**;
- Python compileall: **PASS**;
- dependency consistency via `pip check`: **PASS**;
- broader clone-safe project suite: **1484 passed, 2 deselected**;
- migrations `0001..0012`: **PASS**;
- SQLite `PRAGMA integrity_check`: **ok**;
- SQLite `PRAGMA foreign_key_check`: **no violations**;
- evaluation boundary source guard: **PASS**;
- `git diff --check`: **PASS**.

The two clone-safe deselections remain the established production-database-dependent cases because the GitHub runner does not contain the gitignored local `data/learning_assistant.db`.

The committed local strict Phase D gate still runs the complete project suite against the real local environment.

## Visual validation

No claim of live localhost browser validation is made from this environment.

Automated Flask/web coverage verifies the evaluation handoff, result page, solution disclosure after terminal submission, rubric review, Alex provisional state and explicit confirmation flow.

## Deferred

The next implementation phase should be **Assessment Studio Phase E — Assessment Intelligence**, including visual score/time/topic analytics, chapter/topic/subtopic aggregation, repeated-error patterns, difficulty-vs-accuracy, time-per-mark, trends and heatmaps.

Phase E should read Phase D evaluation evidence without changing mastery or the planner.
