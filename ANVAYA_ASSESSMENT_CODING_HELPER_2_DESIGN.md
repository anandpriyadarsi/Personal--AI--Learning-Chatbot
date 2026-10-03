# Assessment Coding Helper 2 design

DESIGN SELECTED: UC100N Guided Coding Companion

DESIGN AUTO-APPROVED FOR THIS TASK.

Anand authorized design selection and implementation without further approval.
This is a bounded Assessment Studio enhancement with an explicit service/UI
contract, not a new Tutor subsystem.

## Alternatives and decision

1. Stateless prompt-only upgrade: least code, but weak continuity and presentation.
2. Guided companion in existing drawer with authoritative policy, mode contracts,
   catalogue grounding and signed page-local context: selected for learning value,
   low coupling, testability and no persistent data changes.
3. Persistent tutoring platform/editor: excessive migration, coupling and scope.

## Policy and boundaries

One `tool_options(context, settings)` policy determines helper and Colab availability.
The repository resolves session → assessment → course, rejecting missing/deleted
relationships. Only exact persisted code UC100N qualifies. UI and endpoint use
this policy. A course snapshot, title, topic, URL or payload cannot enable tools.
Session mode remains its immutable persisted mode. Practice/assignment allow full
teaching; exams default disabled or predefined concepts-only. Unknown modes/policies
fail closed. Global helper disable remains authoritative. Colab is retained for
UC100N known modes, including exams as in 1.x; helper disable does not disable it.
Non-UC100N renders neither tools nor empty row. No production data writes or migrations.

## Teaching request model

Reuse TutorProviderRequest and OpenAICompatibleTutorProvider (45-second timeout).
Retain eight modes; add Viva, Predict output, Compare operations, Check understanding.
One action catalogue provides labels, contracts and permissions to both UI/server.
Code explanation has overall, line-by-line, operations-only and data-flow depths.
Hint levels give one clue, then stronger clue, then next step; never final answer.
Debug names probable error class, evidence, smallest correction and retry request.
Viva explains purpose, inputs, returns, parameters, alternatives, then asks ONE
unanswered question. Predict asks for a prediction first; after an attempt explain
shape/type/value, marking output as predicted. Check/rebuild never answer first.
Full solution remains explicit and only permitted for debug/explain/pseudocode.
Recommend at most three operations using compact Task/Operation/Why/Syntax/Input/
Output/Common mistake/Alternative sections. Retrieve at most three matching static
cards deterministically (no RAG or network). User-selected card ID has precedence.
Use simple first-year language and one actionable next step, not long lectures.

## Ephemeral continuity

A signed timed continuation token holds at most three exchanges (each user/reply
clipped to 4000 characters). Lifetime 15 minutes. Browser keeps it only in memory:
no cookies, localStorage, sessionStorage, DB, Tutor history or evidence writes.
Bind signature to session, question, authoritative course/mode, question context
permission and full-solution permission; include source text digest for staleness.
Never accept arbitrary history/role fields. New current request is always validated.
Concepts-only exams accept no token. Use a per-app random signing key; restarts
invalidate context. Multi-worker context sharing is deliberately not supported.
Reset, refresh/navigation and permission changes clear context. Closing aborts
in-flight work, with a generation guard discarding stale responses. Failed provider
requests do not advance context. Invalid/expired context offers a clear reset.
Tokens are signed, not encrypted; contain only already visible/user-provided text.

## Presentation and workflow

Keep right modal drawer; mobile full-height overlay; assessment remains primary.
Single mode select and explanation-depth control avoid a wall of mode buttons.
Mode guidance explains what to paste/attempt. Readable text headings/paragraphs,
fenced code and output blocks are created with DOM textContent, never provider HTML.
No arbitrary Markdown, links, images or HTML execution. Copy code/syntax/examples;
copy failure is visible and preserves content. Operations Map adds category filter,
all-field search, EDA and z-score cards and a Use this card action.
Colab label: Run your code in Colab. No content transfer. Escape closes; focus returns.
Timer continues. Reset affects helper only; no question/answer/review mutations.

## Validation and non-goals

Python tests: course matrix, live relationship vs stale snapshot, forged values,
mode matrix, all actions/depths, progressive hints, hidden-field exclusion, provider
failure/timeout/invalid input, bounded signed context/reset/expiry/foreign binding,
no writes, card schema/compiled examples/executable expected outputs.
Node: safe block parser and context request lifecycle. Chromium: six requested
sizes plus existing sizes, course visibility, drawer focus/reset/stale replies,
search/copy, code safety, Colab isolation and all existing navigation regressions.
Run full pytest baseline and final; compare actual failure names/reasons. Do not
create production DB. Optional live smoke only if configured; otherwise report
LIVE PROVIDER QUALITY: NOT VERIFIED. No Tutor/Library/Planning changes.

Schema clarification: runner modes are constrained to exam/practice. Assignment
is an assessment_type; assignment acceptance uses type=assignment, mode=practice.
No schema expansion is needed. Existing policy's assignment mode spelling is
retained defensively but cannot be created as a session in the current schema.
