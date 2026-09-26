# Assessment Studio — Phase B: ANVAYA Assessment Package + Import/Review

## Baseline

Phase B starts from verified Assessment Studio Phase A branch:

`phase7.5.assessment-studio-a/foundation @ a365ac8377d2354844cbf48170c572e669f85177`

Phase B does not merge to `main` and does not implement the timed Test Runner.

## Product workflow

The primary authoring workflow is:

academic papers / notes / PPTs / PDFs
→ Alex / ChatGPT
→ versioned `*.anvaya-assessment.json`
→ strict validation
→ persistent ANVAYA import review
→ edit / reorder / split / merge / remap
→ explicit approval
→ canonical assessment + questions.

ANVAYA remains the authoritative store for approved assessments, attempts and future analytics. Alex/ChatGPT remains an external authoring engine rather than a hidden dependency inside ANVAYA.

## Public package contract

Phase B publishes:

- `schemas/anvaya-assessment-package-v1.schema.json`;
- `examples/anvaya_assessment_package_v1.example.json`;
- `ANVAYA_ASSESSMENT_PACKAGE_AUTHORING_PROMPT.md`.

The runtime parser is deliberately strict and provider-independent. It rejects duplicate JSON keys, unknown top-level/domain fields, unsupported package versions, non-finite numbers, invalid answer-option references and malformed question-specific answer keys.

Package identity is `package_id + package_revision`.

Re-uploading byte-identical content for the same identity is idempotent. Different content with the same identity is rejected; a corrected package must increase `package_revision`.

## Migration 0010

`0010_assessment_package_import_review.sql` introduces:

- `assessment_import_batches`;
- `assessment_import_questions`;
- `assessment_import_question_options`;
- `assessment_runtime_specs`;
- `assessment_question_specs`;
- `question_options`.

Staging tables preserve package/review state. Canonical runtime/question-spec tables carry approved metadata required by the future CBT runner and evaluation engine.

Existing canonical tables remain in use:

- `assessments`;
- `assessment_topics`;
- `questions`;
- `question_topic_mappings`;
- `question_sources`.

No duplicate assessment authority is introduced.

## Review semantics

Uploading a valid package creates only a review batch and staged questions.

It does NOT create:

- a canonical assessment;
- canonical questions;
- attempts;
- mistake events;
- topic-progress evidence;
- planner changes.

The review UI supports:

- assessment title/type/mode/duration/marks/instruction editing;
- question text/type/marks/negative-mark/scoring editing;
- source/provenance editing;
- solution/rubric review;
- canonical topic selection;
- option text and objective answer-key review;
- accepted-answer review for numerical/fill/true-false;
- explicit reviewed/ready state;
- question reorder;
- safe subjective split;
- safe adjacent subjective merge;
- staged-question removal;
- package rejection.

Objective questions containing options cannot be split/merged because silently combining or dividing answer choices would be unsafe.

Split questions deliberately lose marks/solution/rubric and become Review required so ANVAYA cannot approve ambiguous segmentation accidentally.

## Topic mapping

Package topic labels remain preserved as raw provenance.

ANVAYA resolves the package course using canonical course code, then deterministically suggests canonical topics using exact names, aliases and bounded similarity.

Low-confidence, unmapped, package-marked or low-authoring-confidence questions remain Review required.

A final approved question always records a user-reviewed canonical `question_topic_mappings` row with state `confirmed`.

## Approval gate

Approval is blocked until:

- at least one question exists;
- ordinals are contiguous;
- every question has positive marks;
- assessment total marks equals the question-mark sum;
- every question has a canonical course topic;
- no question remains Review required;
- every question has a solution;
- MCQ has at least two options and exactly one correct option;
- MSQ has at least two options and at least one correct option;
- numerical/fill/true-false has accepted answers;
- subjective questions have rubrics.

Approval is one SQLite transaction.

The transaction creates:

- one canonical `assessments` row;
- `assessment_runtime_specs`;
- deduplicated `assessment_topics`;
- canonical `questions`;
- `assessment_question_specs`;
- normalized `question_options`;
- source provenance through `question_sources`;
- confirmed topic mappings through `question_topic_mappings`;
- the staging-to-canonical question links;
- approved batch status/assessment link.

If any write fails, the whole approval rolls back.

Approval does not create attempts, mastery/progress events or planner mutations.

## Future Test Runner compatibility

Phase B persists the fields Phase C needs for JEE-style CBT rendering:

- question type;
- stable option IDs and option order;
- correct option flags / controlled answer JSON;
- negative marks;
- scoring policy;
- exam/practice mode;
- duration and instructions;
- section and visible question number;
- estimated solving time;
- solution/rubric metadata kept server-side for later evaluation/display policy.

Phase C must still enforce hiding answer/solution material during Exam Mode.

## Security and file handling

Phase B accepts UTF-8 JSON packages only, up to 5 MB.

Uploaded package bytes are not written to arbitrary filesystem paths. The original package is preserved canonically as normalized JSON plus a SHA-256 provenance hash in SQLite.

The user-supplied filename is reduced to its basename.

Reads use read-only SQLite connections and never create a missing database.

## Non-goals

Phase B does not implement:

- direct PDF/OCR ingestion inside ANVAYA;
- an internal LLM provider;
- timed sessions;
- countdown timer;
- answer autosave;
- question palette state machine;
- test submission;
- objective grading;
- subjective AI grading;
- analytics/charts;
- mistake classification;
- mastery changes;
- planner recommendations or planner mutation.

Those remain Phase C and later.
