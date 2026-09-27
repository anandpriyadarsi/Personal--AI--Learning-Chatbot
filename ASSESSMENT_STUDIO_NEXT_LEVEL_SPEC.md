# Assessment Studio next-level specification

## Scope and authority

Implement on `phase7.5.assessment-studio-ux/next-level` from
`c01e39d14d8945505e8acfa10a0fc2fb7cd2e058`. Do not merge main. The user explicitly
authorises audit, specification, planning, implementation, tests, commit and push
without another design approval unless a material architecture conflict appears.

Primary lifecycle: create with external Alex → prepare and blind review → timed
attempt → evaluate → understand → explicitly recover → create a retest.

Keep Flask → service → repository → canonical SQLite. No migration, new package
version, dependency, internal LLM, snapshot rewrite, automatic grading confirmation,
mastery mutation or automatic planner application.

## 1. Workspace and library

Add `AssessmentWorkspaceService` and `SQLiteAssessmentWorkspaceRepository` as a
read-only projection over existing package/runtime/session/evaluation metadata.
Reads use mode=ro and never create a missing database. Use explicit safe columns;
never load question bodies, options, answer keys, solutions, rubrics or package JSON
for home/library. SQL parameters bind all user filters. Do not call runner writes
or timeout synchronization from these overview GETs.

Provide a paginated library (20 entries/page) with literal case-insensitive text
search, course, Quiz/Exam/Test and state filters. Categories: all, preparation,
ready, active, results, rejected. Each canonical assessment appears once with its
latest attempt (active attempt prioritised). Display latest package revision for
unapproved package families; prior revisions remain accessible from authoring
history. A separate attempt history view, filtered by assessment, pages every
historical attempt. Rejected history is a deliberate filter, excluded by default.
No data is deleted or status rewritten by browsing.

Rows carry course, kind, title, marks/duration/count where available, revision,
state and one next action: blind preflight, instructions, resume, finish expired
attempt, evaluate, review grading or results. Expired active records display
"Time ended" until the existing runner command boundary closes them. Never start
a new attempt implicitly. Retake uses existing instruction/confirmation flow.

Home presents one priority continuation (active/time-ended attempt, pending
preparation/grading, then ready test), links to the full library/create/reports/
recovery, and recent rows. Keep course/template tools and the legacy academic
deadline timeline inside disclosed sections. No fake statistics or sample data.

## 2. Common presentation and safe preparation

Use existing ANVAYA dark tokens and iris course styles. Add an assessment-scoped
stylesheet; do not restyle unrelated products. Shared compact navigation links:
Overview, Library, Create, Reports, Recovery; templates remain in tools. Active
page has aria-current. Use wrapping controls and labelled non-color-only states.

Keep type selection → compact subject dialog → focused authoring workspace and
movable Create with Alex companion. Name dialogs, move focus into the opened
drawer and return focus on close. Offer a no-script subject selection path.

Blind review begins with title/course/revision, compact question/mark/duration
facts, one state-led next-action panel and a short spoiler assurance. Semantic and
integrity details and setup are disclosed below. Review blockers still prevent
approval. Rejected and approved lifecycle state takes precedence over preflight
readiness; approved links directly to that assessment's instructions. Handoff is
attachment-only and the safe prompt is manually copyable if clipboard fails.
Revision upload remains same package, exact next revision, same course. Reject
requires a deliberate confirmation before its existing POST. Preserve protected
rejected-only deletion.

## 3. Runner and readiness

Preflight adds aggregate section/type/positive and negative marking rows without
loading question text or hidden answers into the view. Existing instructions,
mode, read-instructions confirmation and resume behavior remain.

Fix unselected True/False serialization to an empty value. Serialize autosave
requests so an older request cannot overwrite a newer one from this page. A
change immediately shows unsaved status; success describes only the saved
revision. Cancel queued debounces and flush the latest response before palette,
Previous/Next, Save/Mark/Clear commands and explicit final submit. Save failure
keeps the current question and response visible and blocks navigation/submission;
provide retry and an unsaved-leave warning. Clear remains clear and cannot be
undone by a late save. Do not store answer material in browser persistence.

Timer remains server authoritative. Timeout checking cannot claim an answer was
saved; when expired, explain that the last successfully saved response is used.
Track visible focus intervals at visibility transitions, with failed focus deltas
retained where feasible; the existing server clamp remains. Do not claim exact
wall-clock solving time.

Show question first at narrow widths; palette can collapse. Keep all five palette
states, native answer controls, section navigation and actions. Save status is a
polite status region independent of the ticking timer. Submission confirmation
shows server-confirmed answered/unanswered/marked counts and offers Cancel. Native
no-script explicit confirmation remains safe.

## 4. Results, grading and recovery

Fix the grading editor's evaluation ID contract. Mistake classification requires
a graded non-correct response; enforce it in the service and repository so an
ungraded→correct path cannot create canonical mistake evidence. Existing historical
evidence is not silently edited; no data-cleanup migration is included.

Results retain all current grading/classification commands but present a compact
score/status/outcome/negative-impact overview, then one selected question. Use GET
`outcome` and `question` selection; filter values are allowlisted. Include navigation
across all/incorrect/partial/unanswered/pending questions, selected and correct
option text from the immutable snapshot, solution/rubric disclosure, focus time,
difficulty and available topic metadata. Do not invent historical provenance not
captured in a snapshot. Classification controls are disclosed only after grading.
Pending/provisional scores remain visibly incomplete and outside confirmed evidence.

A result next-action links to its first grading task when incomplete, otherwise
to session intelligence and course recovery. Recovery accepts optional course_id,
filters candidates/saved records consistently, and preserves context after POST
redirects. Label evidence as course-wide confirmed evidence, not solely caused by
this attempt. Existing explicit Generate and Apply remain the only mutations.
Retest entry links to existing Alex creation for the selected course; it does not
claim a stored original/retest relationship. Do not automatically generate tests.

## Verification and constraints

Preserve A–F, blind review, authoring and simplified-authoring regression tests.
New tests prove read-only storage, lifecycle transitions, literal search and paging,
answer absence, rendered form targets, pending/correct mistake guard, serialized
save behavior, failure blocking, True/False empty response, focus accounting,
accessible controls and recovery PRG context. Use actual JS with a minimal Node
DOM/fetch harness for event races, not string-only assertions.

Run compileall, pip check, focused and full assessment tests, broader pytest,
fresh migration integrity/FK checks and git diff --check. Report production-DB
constraints separately instead of silently declaring the entire local suite green.
Attempt live desktop/narrow visual validation; if the browser blocks localhost,
record the error, inspect rendered HTML/CSS/JS and supplied screenshots, and provide
exact local pages/checks. No fabricated visual pass or screenshots.
