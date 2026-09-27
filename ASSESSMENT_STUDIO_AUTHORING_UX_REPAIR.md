# Assessment Studio — Alex Authoring Workspace UX Repair

## Baseline

This repair starts from the completed Assessment Studio Phase F production branch:

`phase7.5.assessment-studio-f/adaptive-academic-loop @ 21a5e6f602229a227f0189f44efa87676c3613f9`.

It is a bounded product/UX repair. It does not change the ANVAYA Assessment Package v1 schema, Phase B review semantics, Phase C runner, Phase D evaluation, Phase E intelligence, or Phase F adaptive loop.

## Product problem

The previous `/assessments/import` surface exposed the technically correct package upload but did not represent the intended human workflow.

The intended primary workflow is:

Quiz / Exam / Test
→ subject
→ Alex / ChatGPT
→ copy ANVAYA master prompt
→ source papers/notes/PPTs/PDFs in ChatGPT
→ ANVAYA-compatible JSON package
→ ANVAYA validation/review
→ approval
→ test/evaluation/intelligence/recovery.

The old page looked like a developer file-upload form and hid the master prompt in repository documentation.

## Authoring workspace

The authoring workspace now exposes three fully clickable workflow cards:

- Quiz
- Exam
- Test

After a workflow is selected, ANVAYA displays all active canonical courses as fully clickable subject cards.

Courses are read dynamically from the canonical course table. The UI does not hard-code a fixed course list.

## Alex / ChatGPT launch

The first-page utility area includes a direct external link:

`https://chatgpt.com/`

The UI label is:

**Open Alex / ChatGPT**

This is not an “Ask Alex” question interface. It opens ChatGPT as the external assessment-authoring engine.

## Master prompt card

The first page contains a compact Master Prompt card rather than rendering the entire prompt inline.

The card provides:

- click-to-preview;
- Copy prompt;
- Edit prompt.

The full prompt opens only in a dialog.

The editable master prompt is persisted in SQLite.

Reset restores the repository default prompt.

## Prompt personalization

The master prompt supports placeholders:

- `{{ASSESSMENT_KIND}}`
- `{{ASSESSMENT_KIND_ID}}`
- `{{ASSESSMENT_TYPE_GUIDANCE}}`
- `{{COURSE_CODE}}`
- `{{COURSE_NAME}}`

The copied prompt resolves those placeholders from the current workflow/subject selection.

The repository default prompt explicitly describes:

- ANVAYA Assessment Package v1;
- supported assessment/question types;
- MCQ/MSQ answer-key rules;
- JEE-style CBT intent;
- provenance;
- solutions/rubrics;
- topic metadata/confidence;
- strict final validation;
- downloadable `*.anvaya-assessment.json` output.

## Import context

The package upload form requires visible user-facing classification:

- Save as: Quiz / Exam / Test
- Subject: canonical ANVAYA course

This classification is distinct from detailed package `assessment_type`.

The package still carries the precise schema value such as:

- quiz
- midsem
- endsem
- topic_test
- previous_paper
- custom

The selected subject is validated against the package course code.

A package for a different course is rejected instead of silently being filed under the selected subject.

Direct non-web service calls remain backward-compatible by inferring workspace classification/course context from the package when UI context is absent.

## Persistence

Migration `0014_assessment_authoring_workspace.sql` adds:

- nullable `assessment_import_batches.workspace_kind`;
- index for kind/course/history;
- singleton `assessment_authoring_preferences` table.

New browser imports persist workspace kind.

Existing historical imports remain readable; user-facing kind is inferred from detailed assessment type when the new column is null.

## History

Staged package history is already durable in Phase B.

The repaired UI presents that history as visual cards containing:

- Quiz / Exam / Test classification;
- course;
- review status;
- package title;
- question count;
- detailed assessment type;
- mode;
- source filename/package ID;
- package revision;
- link back to review.

When kind/course are selected, history is filtered to that workspace.

## Review continuity

The Phase B review screen carries the user-facing classification and links back to the same kind/course workspace.

Review/approval behavior remains unchanged.

## Visual language

The repair reuses Notes Studio patterns:

- card gallery;
- subtle accent line;
- hover elevation;
- compact metadata chips;
- responsive multi-column grids;
- compact dialog-based detail views.

The master prompt does not occupy the initial viewport.

## Safety and boundaries

GET requests do not mutate prompt/history state.

Prompt editing requires POST.

Package staging remains Phase B validation first; selecting a file does not bypass review.

No test attempt, score, mastery, intelligence, recovery recommendation, or planner mutation is created by the authoring workspace.
