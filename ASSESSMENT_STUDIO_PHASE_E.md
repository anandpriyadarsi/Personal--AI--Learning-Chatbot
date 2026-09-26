# Assessment Studio — Phase E: Assessment Intelligence

## Baseline

Phase E starts from verified Assessment Studio Phase D:

`phase7.5.assessment-studio-d/evaluation-engine @ af72d701ccc7802e49a630b77e7682745f071bad`

Phase E does not merge to `main` and does not change mastery, topic status or planner state.

## Architecture decision: no migration 0013

Phase E is intentionally a read-only derived intelligence layer.

The Phase C session snapshots and Phase D evaluation records already preserve the historical evidence needed for deterministic reports. Creating a second analytics authority would duplicate derived truth and introduce cache invalidation/versioning problems without a current product need.

Therefore Phase E adds **no migration**. The current schema remains `0001..0012`.

All Phase E services open SQLite with `mode=ro`.

The repository contains SELECT-only analytics queries.

GET reports do not write analysis snapshots, attempts, mistakes, progress events, plan items or evaluation events.

## Evidence boundary

Cross-test intelligence uses only:

- terminal Phase C sessions;
- Phase D session evaluations with `status = confirmed`;
- response evaluations with `status IN ('auto_confirmed', 'confirmed')`;
- non-null signed awarded marks;
- confirmed mistake classifications.

Phase D `awaiting_review` and `provisional` responses are excluded from:

- course trends;
- global trends;
- topic recovery ordering;
- historical-paper intelligence;
- difficulty/question-type cross-test analytics.

A session analysis page may open before final confirmation, but it clearly marks itself preliminary and includes only confirmed question rows in its calculated metrics.

The session is not included in cross-test intelligence until its Phase D session evaluation becomes confirmed.

## Core metrics

### Signed marks performance

`signed marks performance % = 100 × signed awarded marks / available marks`.

Negative marking is preserved. The raw percentage can therefore be below zero.

Visual bars clamp only the rendered width to `0..100`; the textual number remains the real signed percentage.

### Confidence-weighted marks performance

Topic/chapter/subtopic/difficulty/question-type evidence uses Phase D evaluator confidence when supplied:

`weight = confidence`.

When confidence is absent on confirmed evidence:

`weight = 1.0`.

Then:

`confidence-weighted performance % = 100 × Σ(score × weight) / Σ(max marks × weight)`.

This weighting affects analytics only. It does not alter official Phase D session scores.

### Full-answer accuracy

`accuracy % = fully correct questions / attempted questions × 100`.

Attempted questions include:

- correct;
- partially correct;
- incorrect.

Unanswered questions are excluded from the accuracy denominator and remain visible separately.

### Timing

Phase E reads bounded Phase C `focus_seconds`.

It exposes:

- total focused minutes;
- average focus seconds per question;
- seconds per available mark.

`seconds per available mark = focus_seconds / (max_marks_milli / 1000)`.

This is study/test interaction evidence, not proctoring truth.

## Topic intelligence

Every confirmed session question keeps the stable Phase C `topic_id` snapshot plus display labels.

Topic reports aggregate by stable topic ID.

Displayed evidence includes:

- question count;
- confirmed session count;
- signed marks;
- confidence-weighted marks percentage;
- full-answer accuracy;
- correct/partial/incorrect/unanswered counts;
- focused time;
- seconds per available mark;
- confirmed mistake count/categories.

Phase E does not write these values back to canonical topic mastery/state fields.

## Observed-performance bands

Heatmap styling uses descriptive bands only:

- `strong`: at least 2 questions and weighted performance >= 80%;
- `developing`: at least 2 questions and weighted performance >= 60% and < 80%;
- `needs_review`: at least 2 questions and weighted performance < 60%;
- `limited_evidence`: exactly 1 confirmed question;
- `no_evidence`: no confirmed questions.

These are visual report labels, not mastery classifications.

## Recovery / Weak Topics ordering

The **Weak Topics / Recovery Evidence** page is an evidence ordering, not a mastery score.

Topics are ordered deterministically by:

1. lower confidence-weighted marks performance;
2. higher confirmed mistake count;
3. higher incorrect count;
4. higher partial count;
5. larger confirmed question sample;
6. topic name as stable tie-break.

Displayed reasons may include:

- low confirmed marks rate;
- repeated incorrect responses;
- repeated partial responses;
- repeated confirmed mistake classifications;
- limited sample size;
- slower time-per-mark than the course median.

No hidden composite score is calculated.

The order does not create planner recommendations or change topic state.

## Course time comparison

For a course, Phase E computes the median topic seconds-per-available-mark across topics with timing evidence.

A topic is labelled slower than the course median only when:

- it has at least 2 confirmed questions; and
- its seconds-per-mark exceeds `1.25 × course median`.

This is a timing signal, not a diagnosis of why the student was slow.

## Difficulty and question-type intelligence

Confirmed question evidence is grouped by:

- difficulty snapshot;
- question type snapshot.

Each group exposes the same marks, accuracy and timing metrics.

This supports comparisons such as:

- easy/medium/hard observed performance;
- MCQ/MSQ/numerical/subjective observed performance;
- time-per-mark by format.

Phase E does not infer ability, intelligence or future performance from these groups.

## Chapter / topic heatmap

The course report includes a chapter × topic visual heatmap.

Each heat cell shows:

- chapter;
- canonical topic;
- confidence-weighted performance;
- question count;
- focus time.

Every heatmap has a full table equivalent.

## Trends

A trend point corresponds to one fully confirmed Phase D session.

Trend points include:

- assessment/session title;
- date;
- assessment type;
- signed score/max marks;
- marks performance;
- full-answer accuracy;
- focus time.

No provisional session enters the trend.

## Repeated mistakes

Only confirmed Phase D mistake classifications enter Phase E.

Reports aggregate:

- mistake category;
- count;
- distinct session count;
- topic association where available.

A category with count >= 2 is marked as repeated evidence.

Phase E does not infer an unrecorded mistake category from an incorrect answer.

## Historical previous-paper intelligence

A session is considered reproduced historical-paper evidence only when its approved Phase B import provenance has:

`authoring_purpose = reproduced_paper`.

Phase E reports observed:

- reproduced-paper session count;
- reproduced-paper question count;
- topic coverage frequency;
- difficulty coverage frequency.

This is **historical coverage only and not a forecast**.

Phase E must not claim that a topic is likely to appear in the next quiz/exam or provide predicted probabilities from historical frequency.

## Web surfaces

Phase E adds:

- GET `/assessments/reports` — global Assessment Intelligence;
- GET `/assessments/reports/courses/<course_id>` — course intelligence;
- GET `/assessments/sessions/<session_id>/analysis` — session analysis;
- GET `/assessments/weak-topics` — recovery evidence order.

Existing Assessment Studio navigation activates:

- Reports;
- Weak Topics.

Course workspaces link to their course report.

Phase D evaluation results link to the session intelligence page.

## Visual accessibility

Phase E visualizations use dependency-free HTML/CSS bars and heat cells.

Every critical visualization exposes the numeric value as visible text.

Heatmaps and major overview/topic visualizations have a **table equivalent**.

Color is never the only carrier of meaning.

Recovery entries include textual reasons.

The layout is responsive on narrow screens.

## No academic-state mutation

Phase E **does not change topic mastery**.

It does not write:

- `topic_progress_events`;
- topic status;
- mastery state;
- `study_plan_items`;
- planner schedules;
- planner recommendations;
- `question_attempts`;
- `mistake_events`;
- Phase D evaluation events.

Phase E consumes assessment evidence only.

## Non-goals

Phase E does not implement:

- planner recommendations;
- one-click recovery-plan application;
- automatic mastery updates;
- adaptive retest creation;
- automatic note/tutor recommendations;
- direct LLM calls;
- predictive exam-topic forecasting.

Those remain Phase F and later.
