# Assessment Studio — Spoiler-Safe Blind Review Repair

## Baseline

This bounded repair starts from:

`phase7.5.assessment-studio-ux/alex-authoring-workspace @ 99e9b7c806388902f2329fa76d130171aa029dee`

No new database migration is required. Assessment Package v1, runner, evaluation, intelligence and adaptive academic loop contracts remain unchanged.

## Product problem

The Phase B import review exposed question text and provided direct access to options, answer keys, solutions and rubrics before the assessment was attempted.

It also required the student to manually clear review flags and topic mappings before approval.

That workflow conflicts with a blind exam/practice experience.

## Product rule

The student reviews only safe assessment setup:

- title;
- workspace kind;
- course;
- detailed assessment type;
- mode;
- duration;
- total marks;
- instructions;
- aggregate validation status.

Before the test, the default review page must not render:

- question text;
- objective option text;
- correct option IDs;
- accepted answers;
- solutions;
- subjective rubrics;
- detailed source locators that reveal question content.

## Responsibility split

### ANVAYA

ANVAYA automatically performs deterministic checks:

- question ordering;
- positive marks;
- configured total versus question total;
- required question text presence without rendering it;
- required solution presence without rendering it;
- MCQ option/answer-key cardinality;
- MSQ option/answer-key presence;
- accepted answers for numerical/fill/true-false;
- subjective rubric presence;
- topic mapping presence/confidence;
- authoring confidence;
- package review flags.

### Alex / ChatGPT

Alex handles semantic uncertainty:

- whether an answer is actually correct;
- whether extraction/OCR changed meaning;
- whether question segmentation is correct;
- whether a solution/rubric matches the question;
- uncertain topic mapping.

### Student

The student remains blind to test content and only approves a package when the non-spoiler preflight is clear.

## Blind preflight states

- `ready`: no deterministic integrity blockers and no semantic warnings.
- `alex_review`: deterministic checks pass, but semantic/topic uncertainty remains.
- `repair`: deterministic package integrity problems remain.

## Alex review handoff

For `alex_review`, ANVAYA creates an attachment-only JSON handoff:

`anvaya.assessment-review-handoff` version 1.

The handoff includes:

- original hidden source package;
- package ID and current revision;
- required next revision;
- canonical course/topic catalogue;
- flagged question identifiers;
- issue codes;
- mapping/authoring confidence;
- instructions for Alex.

The review page itself does not render hidden content.

The student uploads the handoff plus original source materials to Alex and pastes the non-spoiler review prompt.

Alex returns a complete ANVAYA Assessment Package with:

- same package ID;
- incremented package revision;
- corrected metadata/content where supported;
- `review_required=false` only where genuinely verified.

The revised package is imported normally and receives a new blind preflight.

## Authoring prompt improvement

The normal assessment-authoring master prompt now receives the canonical ANVAYA topic catalogue through:

`{{COURSE_TOPICS}}`

It also instructs Alex to perform a silent semantic review before returning a package, reducing future review flags.

## Manual editor

Legacy question-edit/split/merge routes remain available internally for exceptional repair and backwards compatibility, but they are not linked from the default blind review page.

The default product path does not require the student to open them.

## Approval

Approval remains strict.

A package can be approved only when:

- deterministic integrity blockers are empty;
- semantic warnings are empty.

This preserves the Phase B quality gate without requiring the student to spoil the assessment.

## Test secrecy

This repair is limited to import/review. Existing runner protections against pre-submission answer exposure remain authoritative.
