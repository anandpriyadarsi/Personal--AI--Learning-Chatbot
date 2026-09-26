# Assessment Studio Phase E — Implementation Report

## Result

Assessment Studio Phase E — Assessment Intelligence is implemented from the verified Phase D baseline:

`phase7.5.assessment-studio-d/evaluation-engine @ af72d701ccc7802e49a630b77e7682745f071bad`

The production target branch is:

`phase7.5.assessment-studio-e/assessment-intelligence`

Phase E has not been merged into `main`.

## Architecture

Phase E is intentionally read-only and adds **no migration**.

The current authoritative schema remains migrations `0001..0012`.

Analytics are derived directly from:

- immutable Phase C session/question snapshots;
- persisted Phase C response timing;
- Phase D confirmed session evaluations;
- Phase D confirmed response evaluations;
- Phase D confirmed mistake classifications;
- Phase B approved-package provenance.

The intelligence repository uses SQLite `mode=ro` and SELECT-only queries.

This avoids creating a second source of truth for derived analytics.

## Delivered

Phase E adds four read models and web surfaces:

- global Assessment Intelligence;
- course Assessment Intelligence;
- per-session analysis;
- Weak Topics / Recovery Evidence.

The Assessment Studio landing page now activates:

- Reports;
- Weak Topics.

Course workspaces link to course reports.

Phase D evaluation results link directly to session intelligence.

## Metrics and analytics

Implemented analytics include:

- signed score and available marks;
- raw marks performance;
- confidence-weighted marks performance;
- full-answer accuracy;
- correct / partial / incorrect / unanswered counts;
- focused minutes;
- average focus time per question;
- seconds per available mark;
- session-by-session trends;
- course-level summaries;
- topic-level summaries;
- chapter-level summaries;
- subtopic-level summaries;
- difficulty-vs-performance;
- question-type-vs-performance;
- chapter × topic performance heatmap;
- repeated confirmed mistake categories;
- topic mistake counts/categories;
- timing comparison against the course median;
- historical reproduced-paper coverage.

Negative Phase D scores remain signed in analytics.

Rendered bar width is clamped to 0..100 only for presentation; displayed numeric score/performance remains the real signed value.

## Confidence weighting

When a confirmed Phase D response has evaluator confidence:

`weight = confidence`.

When confidence is absent:

`weight = 1.0`.

Topic/group confidence-weighted marks performance is:

`100 × Σ(score × weight) / Σ(max marks × weight)`.

This changes analytics only. It does not alter Phase D scores or canonical attempts.

## Confirmed-only cross-test evidence

Cross-test analytics require:

- terminal test session;
- Phase D session evaluation status `confirmed`;
- response status `auto_confirmed` or `confirmed`;
- non-null awarded marks.

Provisional and awaiting-review evidence is excluded from:

- global/course trends;
- weak-topic ordering;
- historical-paper intelligence;
- difficulty/type cross-test analytics.

A provisional session can still open its own session-analysis page, where the page clearly identifies incomplete evaluation and calculates metrics from confirmed questions only.

## Recovery evidence

The Weak Topics / Recovery Evidence view does **not** create a hidden mastery score.

Ordering is transparent and deterministic:

1. lower confidence-weighted marks performance;
2. higher confirmed mistake count;
3. higher incorrect count;
4. higher partial count;
5. larger confirmed question sample;
6. topic name tie-break.

Displayed recovery signals include observed facts such as:

- low confirmed marks rate;
- repeated incorrect responses;
- repeated partial responses;
- repeated confirmed mistake classifications;
- limited sample size;
- slower time-per-mark than the course median.

The ordering is evidence for later action, not an automatic planner decision.

## Timing

Phase E reads Phase C persisted `focus_seconds`.

It computes:

- focused minutes;
- average seconds/question;
- seconds/available mark.

For course comparison, Phase E calculates the median topic seconds-per-mark.

A topic is flagged as slower than the course median only when:

- it has at least two confirmed questions; and
- its seconds-per-mark exceeds 1.25 × course median.

No causal claim is made about why the topic took longer.

## Historical paper intelligence

Historical coverage is restricted to approved Phase B package provenance with:

`authoring_purpose = reproduced_paper`.

Reports show observed:

- reproduced-paper session count;
- reproduced-paper question count;
- topic frequency;
- difficulty frequency.

The UI and spec explicitly state that this is **historical coverage only and not a forecast**.

Phase E does not predict which topic will appear in the next quiz, mid-sem or end-sem.

## Accessibility and UI

Phase E uses dependency-free HTML/CSS visualization components:

- bar charts;
- heatmap cards;
- metric cards;
- recovery evidence cards.

Critical numbers remain visible as text.

Heatmaps and major visual reports include table equivalents.

Color is not the only information carrier.

The report layout includes responsive behavior for smaller screens.

## No academic-state mutation

Phase E does not change:

- topic mastery;
- topic status;
- topic progress;
- study plans;
- planner schedules;
- planner recommendations;
- question attempts;
- canonical mistake events;
- Phase D evaluation events.

Focused tests verify repeated GET requests leave these counts unchanged.

## Schema mismatch discovered and corrected

The first clean validation run exposed one real repository mismatch:

`assessment_test_session_questions` does not contain `estimated_seconds`.

Phase E initially attempted to query that nonexistent snapshot field.

The implementation was corrected to rely only on persisted Phase C `assessment_test_responses.focus_seconds`, which is the authoritative timing evidence actually available.

No migration was added merely to satisfy the report.

## Validation

Clean GitHub validation of the corrected implementation head completed successfully with:

- focused Assessment Studio Phase E: **10 passed**;
- Assessment Studio Phase A/B/C/D + existing assessment regressions: **50 passed**;
- SQLite schema + recovery regressions: **22 passed**;
- Python compileall: **PASS**;
- dependency consistency via `pip check`: **PASS**;
- broader clone-safe project suite: **1494 passed, 2 deselected**;
- existing migrations `0001..0012`: **PASS**;
- SQLite `PRAGMA integrity_check`: **ok**;
- SQLite `PRAGMA foreign_key_check`: **no violations**;
- intelligence SELECT-only/read-only source guard: **PASS**;
- no Phase E migration guard: **PASS**;
- `git diff --check`: **PASS**.

The two clone-safe deselections remain the established production-database-dependent cases because the GitHub runner does not contain the gitignored local `data/learning_assistant.db`.

## Visual validation

No claim of live localhost browser validation is made from this environment.

Automated Flask/web tests verify:

- global report rendering;
- course report rendering;
- heatmap presence;
- heatmap table equivalent;
- difficulty analytics;
- timing analytics;
- historical coverage text;
- session analysis;
- Weak Topics / Recovery Evidence;
- non-mutating GET behavior.

## Deferred

The next architectural phase is **Assessment Studio Phase F — Adaptive Academic Loop**.

Phase F should consume Phase E evidence and create explicit, reviewable recommendations such as:

assessment evidence
→ topic recovery recommendation
→ suggested notes/tutor/practice/retest action
→ planner recommendation preview
→ user accept/reject
→ PlannerService application.

Phase F must preserve the current rule that assessment evidence does not silently rewrite mastery or the study plan.
