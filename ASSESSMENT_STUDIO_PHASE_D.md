# Assessment Studio — Phase D: Evaluation Engine

## Baseline

Phase D starts from verified Assessment Studio Phase C:

`phase7.5.assessment-studio-c/timed-test-runner @ 50cfe500dbed6393987a61384f5fa43795c8655e`

Phase D does not merge to `main` and does not implement cross-test analytics, mastery mutation or planner recommendations.

## Product outcome

Phase D evaluates terminal Phase C test sessions.

The workflow is:

submitted/expired CBT session
→ deterministic objective evaluation
→ rubric review for subjective/custom questions
→ provisional/confirmed grading
→ signed question scores
→ canonical question attempts
→ confirmed mistake classifications
→ final session score when every question is final.

The evaluation engine uses the immutable question/answer/rubric snapshots captured when the test started. Later changes to the canonical assessment do not retroactively change a historical test evaluation.

## Migration 0012

`0012_assessment_evaluation_engine.sql` adds:

- `assessment_session_evaluations`;
- `assessment_response_evaluations`;
- `assessment_evaluation_mistakes`;
- `assessment_evaluation_events`.

It also adds backward-compatible fields to `question_attempts`:

- `signed_score_milli`;
- `evaluation_ref`.

The existing non-negative `earned_marks_milli` field is preserved for legacy compatibility. For Phase D attempts:

- `earned_marks_milli = max(0, signed_score_milli)`;
- `signed_score_milli` is the authoritative question score including penalties.

Phase D does not rewrite or recreate the legacy attempt table.

## Signed scoring

Phase D stores question scores as signed milli-marks.

Examples:

- +4 marks → `4000`;
- +2.667 marks → `2667`;
- 0 marks → `0`;
- −1 mark → `-1000`.

The authoritative session score is the sum of Phase D response-evaluation signed scores.

Phase D does not automatically write the score to `assessments.earned_points_milli` because:

1. that legacy field is non-negative;
2. a single assessment may have multiple test sessions/attempts.

## Deterministic objective rules

Blank responses are auto-confirmed as `unanswered` with zero marks.

### MCQ

For `standard`, `all_or_nothing` and `partial`:

- exact correct option → full marks;
- wrong selected option → configured negative mark penalty;
- blank → zero.

MCQ does not receive proportional partial credit.

### MSQ — standard / all_or_nothing

- exact correct set → full marks;
- incomplete set containing only correct options → zero marks, outcome `partially_correct`;
- any incorrect option selected → configured negative mark penalty;
- blank → zero.

### MSQ — partial

Phase B v1 does not carry an exam-specific subset scoring matrix, so Phase D uses one explicit provider-independent rule:

- exact correct set → full marks;
- non-empty strict subset containing only correct options → proportional credit;
- proportional credit = full marks × selected-correct-count / total-correct-count;
- result is rounded to the nearest milli-mark using decimal half-up rounding;
- any incorrect option selected → configured negative mark penalty;
- blank → zero.

This is JEE-style interaction and partial-credit behavior, but it is **not claimed to reproduce every historical JEE Advanced marking scheme**.

If an exact paper has a special subset rule, the package must use `custom`.

### Numerical

Accepted values are compared numerically using finite decimal normalization.

Thus values such as `4`, `4.0` and `4.00` compare equal.

Wrong non-blank response receives the configured negative penalty.

### Fill blank

Comparison is case-insensitive and collapses whitespace.

Wrong non-blank response receives the configured negative penalty.

### True / False

The following normalize to true:

`true`, `t`, `yes`, `1`.

The following normalize to false:

`false`, `f`, `no`, `0`.

Wrong non-blank response receives the configured negative penalty.

### Custom scoring

`scoring_policy = custom` is never guessed by the deterministic engine.

The response remains `awaiting_review` and requires an explicit manual/teacher/Alex evaluation.

## Subjective grading

Short and long subjective responses with content are never deterministically scored.

They enter `awaiting_review`.

The review page shows:

- question snapshot;
- student response;
- model solution;
- rubric snapshot;
- rubric version hash;
- maximum marks.

Manual review records:

- evaluator type;
- evaluator model when relevant;
- awarded marks;
- confidence when supplied;
- feedback;
- outcome;
- provisional/final state.

Manual score bounds are:

`-configured negative marks <= awarded marks <= maximum marks`.

For normal subjective questions the configured negative mark is usually zero.

## Alex / ChatGPT evaluation contract

Alex/ChatGPT is an external evaluation assistant, not an authority that silently finalizes grades.

When evaluator type is `alex_ai`:

- the score is always saved as `provisional`;
- checking a final-confirmation box cannot bypass this rule;
- no canonical `question_attempts` row is created yet;
- the user must explicitly confirm the provisional evaluation.

After confirmation:

- evaluation status becomes `confirmed`;
- the canonical question attempt is created;
- the session-level evaluation status is recalculated.

The evaluator model/version may be recorded for audit, but Phase D does not call an external LLM itself.

## Session evaluation states

A response evaluation is one of:

- `auto_confirmed`;
- `awaiting_review`;
- `provisional`;
- `confirmed`.

A session evaluation is:

- `pending_review` if any question is `awaiting_review`;
- otherwise `provisional` if any question is provisional;
- otherwise `confirmed`.

A final session score is displayed only when the session evaluation is confirmed.

Before that, ANVAYA distinguishes:

- scored-so-far signed total;
- confirmed signed total;
- questions awaiting review;
- provisional grades.

## Canonical question attempts

Every auto-confirmed or human-confirmed response creates exactly one canonical `question_attempts` row for that session question.

The attempt stores:

- canonical question ID;
- next attempt number;
- outcome;
- legacy non-negative earned credit;
- maximum marks;
- response reference;
- evaluation reference;
- signed score;
- occurrence time based on session submission/expiry.

Provisional and awaiting-review responses do not create attempts.

Evaluation creation and confirmation are idempotent with respect to attempts.

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

Correct responses cannot be assigned mistake classifications.

User/teacher classifications are confirmed immediately.

Alex/ChatGPT classifications are provisional and require explicit user confirmation.

A confirmed classification becomes a canonical `mistake_events` row only when the response has a confirmed canonical question attempt.

If the classification is confirmed before the grade, synchronization occurs when the grade is later confirmed.

## Result disclosure

Answer keys, accepted answers, solutions and rubrics remain hidden during Phase C attempts.

Phase D may show them only for a terminal submitted/expired session inside evaluation/results views.

Evaluation GET/read pages do not create attempts, mistakes, progress events or plan items.

## Audit

Phase D records meaningful evaluation events such as:

- evaluation created;
- manual provisional evaluation saved;
- manual evaluation confirmed;
- provisional evaluation confirmed;
- mistake classified;
- mistake classification confirmed.

It does not log keystrokes or every read.

## Academic evidence boundary

Confirmed question attempts and mistake events are assessment evidence.

Phase D **does not change topic mastery**, topic status, learning-memory mastery state, or study plans.

No `topic_progress_events` or `study_plan_items` are created by Phase D.

Assessment-level analytics and evidence aggregation belong to Phase E.

Planner recommendations and explicit progress application belong to Phase F.

## Web surfaces

Phase D adds:

- POST `/assessments/sessions/<session_id>/evaluate`;
- GET `/assessments/sessions/<session_id>/evaluation`;
- GET/POST `/assessments/evaluations/<evaluation_id>/review`;
- POST `/assessments/evaluations/<evaluation_id>/confirm`;
- POST `/assessments/evaluations/<evaluation_id>/mistakes`;
- POST `/assessments/evaluation-mistakes/<mistake_id>/confirm`.

The terminal Phase C session-summary page now exposes **Evaluate / Open Results**.

## Non-goals

Phase D does not implement:

- charts;
- chapter heatmaps;
- cross-test trends;
- time-per-mark analytics;
- difficulty-vs-accuracy analytics;
- weak-topic ranking;
- mastery/progress mutation;
- planner recommendations;
- planner auto-apply;
- adaptive retest generation;
- direct internal LLM calls.

Those belong to Phase E/F and later.
