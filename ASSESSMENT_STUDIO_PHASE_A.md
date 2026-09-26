# Assessment Studio — Phase A

## Baseline and scope

Phase A starts from canonical main commit 05c851a3f5219c2fe80b235f688b6c0d80053a2f. It introduces the reusable Assessment Studio foundation without implementing a test runner, AI grading, analytics, or planner mutation.

## Architecture

The application boundary is:

Flask route → AssessmentStudioService → SQLiteAssessmentStudioRepository → canonical SQLite

Existing canonical assessments, questions, mappings, attempts and mistakes remain authoritative for real assessment activity. Reusable templates are separate configuration introduced by migration 0009_assessment_studio_foundation.sql.

The normalized tables are:

- assessment_templates — course-scoped reusable configuration, duration, marks, exam/practice mode, lifecycle, provenance and optimistic revision.
- assessment_template_topics — normalized topic scope with real foreign keys.
- assessment_template_patterns — normalized question type/count/marks/negative-mark/scoring-policy rows.

Templates are not opaque app_settings JSON and are not fake rows in assessments.

## Phase A web surfaces

- GET /assessments — Assessment Studio overview plus the existing read-only assessment timeline.
- GET /assessments/courses/<course_id> — course workspace and non-mutating quick-start presets.
- GET /assessments/templates — reusable template catalogue.
- GET /assessments/templates/new — creation form.
- POST /assessments/templates — explicit creation command.
- GET /assessments/templates/<id> — template detail.
- GET /assessments/templates/<id>/edit — edit form.
- POST /assessments/templates/<id> — optimistic-revision update command.
- lifecycle POST routes deactivate/reactivate templates without hard deletion.

GET routes do not create templates, attempts, mastery evidence or planner items.

## Alex / ChatGPT authoring contract

The intended primary future workflow is:

academic papers + notes/PPTs/PDFs → Alex/ChatGPT → versioned ANVAYA Assessment Package → ANVAYA validation/review → timed test → evaluation → analytics → topic evidence → improvement recommendation.

ANVAYA is deliberately not coupled to a specific internal LLM provider. Phase B will define and parse an open, versioned *.anvaya-assessment.json contract. The package must use stable public identifiers or mapping labels instead of assuming transient database row IDs.

Reserved per-question concepts include question/package ID, ordinal/section, text, type, options, marks, negative/scoring rule, correct answer set, solution or rubric, course/chapter/topic/subtopic/concepts, difficulty, expected method, estimated time, source/provenance, page/locator, mapping confidence, authoring/extraction confidence and review-required state.

AI-authored metadata, solutions and rubric scores retain provenance and are not silently promoted to user-confirmed truth.

## Future JEE-style CBT contract

Phase C must use proper clickable controls: single-select radio controls for MCQ, multi-select checkbox controls for MSQ, numerical input, fill-in, true/false, and large subjective answer areas. MSQ responses are collections of stable option IDs, not a scalar answer.

Scoring is assessment-configurable and may be all-or-nothing, negative, partial, or custom. No single JEE Advanced scoring formula is globally hard-coded.

The future question palette reserves Not Visited, Not Answered, Answered, Marked for Review, and Answered + Marked for Review, with Save & Next, Clear Response, Mark for Review & Next, Previous/Next, section navigation and final submit.

The runner also reserves timer, autosave, per-question timing, interruption recovery, expiry submission and final confirmation.

Exam mode and practice mode stay distinct. Exam mode hides hints, solutions and correctness feedback during the attempt. Practice mode may later permit guided assistance.

## Validation and lifecycle

Server-side validation owns duration, marks, negative marks, type/mode, topic/course ownership, duplicate names and pattern rows. A case-insensitive course/name unique key prevents duplicates. Template updates and lifecycle commands use optimistic revision checks. Deactivation preserves configuration and history.

Reads open SQLite in read-only mode and never create a missing database. Writes require the canonical database and migration 0009.

## Non-goals

Phase A does not implement PDF extraction/OCR, package parsing, question import review, timed sessions, answer autosave, grading, AI evaluation, mistake inference, analytics/charts, planner rewriting, weak-topic retests or prediction of future professor questions.

Those remain Phases B–F.
