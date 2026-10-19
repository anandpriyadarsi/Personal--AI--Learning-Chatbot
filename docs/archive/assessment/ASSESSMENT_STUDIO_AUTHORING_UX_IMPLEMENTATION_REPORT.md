# Assessment Studio Alex Authoring Workspace — Implementation Report

## Result

The Assessment Studio authoring/import surface has been rebuilt from the completed Phase F baseline:

`phase7.5.assessment-studio-f/adaptive-academic-loop @ 21a5e6f602229a227f0189f44efa87676c3613f9`

Production target:

`phase7.5.assessment-studio-ux/alex-authoring-workspace`

This is a bounded UX/product repair. The established Assessment Studio A–F test, evaluation, intelligence and adaptive-loop behavior remains intact.

## Product correction

The old Phase B page exposed a technically correct JSON upload form but did not represent the intended workflow.

The repaired workflow is:

Quiz / Exam / Test
→ subject
→ Alex / ChatGPT
→ copy personalized ANVAYA master prompt
→ upload source papers/notes/PPTs/PDFs in ChatGPT
→ receive ANVAYA-compatible JSON
→ validate and stage
→ Phase B review
→ explicit approval.

## Direct Alex / ChatGPT entry

The first view now contains a dedicated **Alex / ChatGPT** authoring card with a direct external link to:

`https://chatgpt.com/`

The UI says **Open Alex / ChatGPT** rather than presenting the action as asking ANVAYA a question.

## Compact master prompt

The first view contains a compact **Master Prompt** card.

It does not render the full prompt into the initial page.

Available actions:

- click card to preview;
- Copy prompt;
- Edit prompt.

The full prompt is shown in a modal dialog only when requested.

Copy uses the prompt personalized for the currently selected assessment workspace and subject.

## Editable prompt persistence

Migration 0014 adds the singleton:

`assessment_authoring_preferences`

The edited master prompt persists in SQLite and receives a revision number.

The user can reset it to the repository default.

The repository default remains:

`ANVAYA_ASSESSMENT_PACKAGE_AUTHORING_PROMPT.md`

## Master prompt upgrade

The repository prompt was upgraded into the full ANVAYA assessment-authoring contract.

It includes:

- selected Quiz / Exam / Test context;
- selected course code/name;
- package v1 requirements;
- supported assessment types;
- MCQ/MSQ/numerical/fill/true-false/subjective rules;
- JEE-style CBT intent;
- negative/custom marking guidance;
- solutions and subjective rubrics;
- chapter/topic/subtopic/concept metadata;
- confidence and review-required behavior;
- provenance;
- strict package validation checklist;
- downloadable `*.anvaya-assessment.json` output.

Supported placeholders include:

- `{{ASSESSMENT_KIND}}`;
- `{{ASSESSMENT_KIND_ID}}`;
- `{{ASSESSMENT_TYPE_GUIDANCE}}`;
- `{{COURSE_CODE}}`;
- `{{COURSE_NAME}}`.

## Quiz / Exam / Test cards

The authoring workspace now starts with three large fully-clickable cards:

- Quiz;
- Exam;
- Test.

This user-facing category is deliberately separate from the detailed package schema type.

Examples:

- Quiz workspace may contain package type `quiz`;
- Exam workspace may contain `midsem`, `endsem` or `previous_paper`;
- Test workspace may contain `topic_test` or `custom`.

## Subject cards

After the workspace type is selected, ANVAYA displays active canonical courses as clickable subject cards.

The list is dynamic and read from SQLite.

No fixed six-course list is hard-coded; when the user's canonical store contains six active subjects, those six are rendered automatically.

## Import classification and subject guard

Browser uploads now require:

- Save as: Quiz / Exam / Test;
- Subject: canonical ANVAYA course;
- package file.

The selected category is persisted in:

`assessment_import_batches.workspace_kind`.

ANVAYA verifies that the selected subject matches the course code inside the package.

A package for another subject is rejected rather than silently misfiled.

Direct service calls remain backward-compatible by inferring missing authoring context from the package.

## Automatic package history

Existing Phase B durable import history remains the source of truth.

The repaired screen now renders it as visual cards containing:

- Quiz / Exam / Test;
- course;
- package title;
- review status;
- detailed assessment type;
- mode;
- question count;
- source filename/package ID;
- package revision;
- review link.

When the user chooses a kind and subject, the history is filtered to that workspace automatically.

Older packages without `workspace_kind` remain readable through deterministic inference.

## Review continuity

The Phase B review page now displays the user-facing category and provides a context-preserving return link such as:

`Back to Quiz · MA103N`.

Package validation, editing, split/merge/reorder, approval and rejection behavior itself is unchanged.

## Visual redesign

The new authoring surface reuses Notes Studio design language:

- gallery/card workflow;
- subtle top accent;
- hover elevation;
- compact tags and metadata;
- responsive grids;
- compact detail dialogs.

The initial view is focused on actions rather than a large raw upload form.

## Migration

New migration:

`0014_assessment_authoring_workspace.sql`

Adds:

- nullable `assessment_import_batches.workspace_kind`;
- kind/course/history index;
- `assessment_authoring_preferences`.

Canonical migration range is now:

`0001..0014`.

## Validation

Clean GitHub validation completed successfully on the implementation head:

- focused authoring UX: **8 passed**;
- Phase B regressions: **9 passed**;
- Assessment Studio A–F + existing assessment regressions: **61 passed**;
- SQLite schema + recovery regressions: **22 passed**;
- compileall: **PASS**;
- `pip check`: **PASS**;
- broader clone-safe suite: **1512 passed, 2 deselected**;
- migrations `0001..0014`: **PASS**;
- SQLite integrity: **ok**;
- foreign-key check: **no violations**;
- diff hygiene: **PASS**.

The two clone-safe deselections are the established local-production-database-dependent tests.

## Visual validation boundary

The repair was driven directly by the supplied screenshots and the existing Notes Studio UI patterns.

No claim of a live localhost browser screenshot from this environment is made.

Automated Flask tests verify the rendered authoring page contains the direct ChatGPT action, compact prompt controls, type cards, dynamic subjects, classified upload form and history.
