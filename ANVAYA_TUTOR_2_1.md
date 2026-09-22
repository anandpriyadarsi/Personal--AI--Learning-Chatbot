# ANVAYA Tutor 2.1 — Adaptive Intelligence

Branch: \`anvaya/tutor-2.1-adaptive-intelligence\`  
Baseline: current \`anvaya/tutor-2.0\`.

## Goal

Make ANVAYA behave like a tutor that remembers the **state of the current
teaching interaction**, rather than treating every user message as an unrelated
search query.

Tutor 2.1 keeps the existing grounded evidence, source policy, provider,
retrieval, and Tutor persistence boundaries.

## 2.1.1 — Adaptive Session State

Adaptive state is stored inside the existing
\`tutor_sessions.metadata_json\` under:

\`adaptive_tutor_state\`

No new SQLite table or migration is required.

The state currently tracks:

- interaction count;
- previous teaching intent;
- whether an adaptive quiz is active;
- whether ANVAYA is waiting for the student's answer;
- the pending Tutor question;
- the student's latest quiz answer;
- an explicitly stated unresolved doubt;
- answer-status placeholder for later structured evaluation.

This state is **session-local**.

It does not update:

- learning-memory entries;
- topic/resource progress;
- mastery;
- grades;
- assessments;
- planner tasks;
- Obsidian notes;
- resources.

## Adaptive quiz continuity

When ANVAYA asks a quiz/check question, Tutor 2.1 stores that pending question.

If the next student message is a normal answer such as:

> Because v3 can be written as v1 + v2.

ANVAYA does not classify that as an unrelated "explain" request.

It becomes:

\`teaching_intent=quiz_answer\`

The Tutor Brain is instructed to:

1. evaluate the student's answer first;
2. identify exactly what is correct/missing;
3. avoid restarting the topic;
4. ask exactly one suitable next question.

If the student asks for a hint while a quiz is active, the pending question is
preserved rather than consumed.

## State-aware retrieval

Short student answers are poor search queries by themselves.

Tutor 2.1 therefore uses bounded multi-query retrieval.

For a quiz answer, retrieval can use:

1. pending Tutor question + student answer;
2. pending Tutor question;
3. unresolved doubt when relevant.

Results are deduplicated by chunk id and reranked by the best returned score.
The final context remains bounded by the existing Tutor top-k and character
limits.

Normal questions still use a single query unless adaptive context adds useful
information.

## Provider context

Tutor provider requests now include a small explicit:

\`STUDENT STATE\`

section in addition to:

- session scope;
- teaching intent;
- current question;
- academic evidence.

The state is treated as conversational context, not authoritative academic
truth.

Tutor 2.1 never invents a correctness label merely because a student replied.
Structured correct/partial/incorrect classification is a later 2.1 unit.

## UI

Tutor session pages identify themselves as **ANVAYA Tutor 2.1**.

When relevant, the header can show:

- Adaptive quiz active
- Waiting for your answer

Explicit unresolved doubt/pending-question state is available under a compact
"Current learning state" disclosure.

## 2.1.2 — Adaptive Answer Evaluation

For a `quiz_answer` turn, ANVAYA asks the configured Tutor provider to begin
its raw response with one hidden machine-readable evaluation containing:

- `correct`
- `partial`
- `incorrect`
- `unclear`

plus a brief reason and optional misconception.

The marker is parsed and removed **before** the assistant turn is persisted or
shown in the browser. It never appears in the student's Tutor transcript.

The evaluation updates only the session-local adaptive state:

- `answer_status`
- `last_evaluation_reason`
- `last_misconception`

If the provider omits or malforms the hidden evaluation, the visible Tutor
answer is preserved and the status safely falls back to `unclear`; the turn
does not become a 500 error.

This is an interaction-level teaching signal, **not a mastery score**. Tutor
2.1.2 still does not write learning memory, progress, grades, or assessments.

## Next Tutor 2.1 units

## 2.1.3 — Deterministic Correctness Layer

Tutor prompt self-checking is no longer the only protection for supported
worked calculations.

When a visible Tutor answer contains one of the supported numerical claim
types, the provider is instructed to emit one hidden \`ANVAYA_MATH\` JSON
marker describing the calculation.

Current deterministic claim types:

- \`vector_linear_combination\`
- \`matrix_product\`
- \`determinant\`

The verifier:

1. parses only bounded JSON data;
2. never evaluates arbitrary Python, LaTeX, or user code;
3. uses exact rational arithmetic where possible;
4. strips the hidden marker before persistence/display;
5. compares the declared result against the independently computed result.

If verification fails, ANVAYA performs at most **one repair provider call**.
The repair receives the deterministic verifier's concrete finding, such as:

> vector linear combination evaluates to (2, 2) instead of target (3, 4)

The repaired response must contain a valid machine-checkable math marker and
pass deterministic verification.

If the repair is absent or still wrong, ANVAYA does **not** display the bad
worked example. It persists a safe response explaining that a calculation
inconsistency was caught and marks that turn \`insufficient\`.

Session-local state records the latest check as:

- \`passed\`
- \`repaired\`
- \`blocked\`
- \`not_applicable\`

plus the number of checked claims.

### Correctness-layer limits

This layer does **not** claim to verify arbitrary mathematics.

It currently does not independently prove:

- abstract theorem proofs;
- symbolic identities outside the bounded schemas;
- arbitrary equation solving;
- calculus derivations;
- natural-language conceptual claims;
- numerical claims that the provider fails to declare in an \`ANVAYA_MATH\`
  marker.

Those remain future correctness work. The deterministic layer is designed to
expand incrementally rather than execute arbitrary mathematical text.

## 2.1.4 — Smarter Retrieval Planner

Tutor retrieval is no longer based only on the literal wording of the current
student message.

The planner now creates at most four deterministic query variants using:

- the original question;
- a conversational-noise-reduced academic focus query;
- pending Tutor question + short student answer during adaptive quizzes;
- unresolved doubt or known session-local misconception when relevant;
- conservative terminology/spelling variants such as
  \`factorisation\` / \`factorization\`.

No LLM/provider call is used for query planning.

Each planned query retrieves a bounded candidate set. Candidates are then
reranked using:

1. rank within each retrieval query;
2. agreement/consensus across multiple query variants;
3. Tutor-mode source preference;
4. deterministic document diversity for broad tutoring.

For concept/doubt/exam-style tutoring, at most three chunks from one document
are selected before other useful documents are allowed into context. This
reduces the risk that adjacent chunks from one PDF crowd out professor notes,
personal notes, PYQs, or another useful source.

For selected-resource, lecture, summary, or explicitly document-scoped sessions,
diversification is disabled so ANVAYA can remain concentrated on the chosen
material.

Current source-role inference is conservative and uses existing retrieval
metadata only. It recognizes common categories such as:

- selected resource;
- professor/slides;
- personal/Obsidian notes;
- PYQ/question-paper material;
- external course material;
- ordinary course material.

The final evidence count and context-character budget remain governed by the
existing Tutor mode limits.

## 2.1.5 — Live Study Validation / Live-Fix Round

A real MA103N-style Tutor session exposed several issues that synthetic tests
did not catch. Tutor 2.1 is not considered complete until these live-fix
regressions are green and revalidated in the browser.

### Live finding: stale state could override a new topic

A stored unresolved doubt about basis/redundancy could influence a later,
explicit LU-factorization question.

Fix:

- detect explicit topic shifts using bounded local heuristics;
- clear stale pending-quiz, unresolved-doubt, and misconception anchors for the
  current turn;
- never coerce an explicit new-topic request into a quiz answer;
- state explicitly in the Tutor prompt that CURRENT QUESTION overrides older
  student-state fields.

### Live finding: referential follow-up changed the example

For questions such as:

> In the LU example you just gave...

the model could invent a new matrix instead of using the recent transcript.

Fix:

- add a \`follow_up_reference\` teaching intent;
- recent transcript is authoritative for referenced examples;
- reuse exact numerical objects/notation unless the student explicitly asks for
  a new example.

### Live finding: supported computation could omit verification metadata

A 3x3 LU response visually claimed \`LU=A\` while the displayed \`L\` omitted
the required second-stage elimination multiplier.

Fix:

- explicit supported computation requests now require machine-checkable math
  metadata;
- LU/matrix requests require a \`matrix_product\` claim specifically;
- determinant/vector requests require their matching claim types;
- the same requirement is enforced on the one repair attempt;
- omission or wrong claim type triggers repair, then fail-closed blocking.

The exact faulty 3x3 LU structure observed during live validation is now a
regression test using exact rational arithmetic.

### Live finding: provider metadata was shown as the Tutor answer

A provider response containing only:

\`User Safety: safe\` / \`Response Safety: safe\`

was persisted as visible Tutor content.

Fix:

- strip provider/safety status lines;
- if nothing academic remains, perform one bounded retry;
- if the retry still contains no academic answer, return an \`insufficient\`
  Tutor turn rather than a 500 or misleading content.

### Completion criterion

Re-run the full Tutor 2.1 gate, then repeat a short browser validation covering:

1. basis/redundancy -> explicit topic switch to LU;
2. verified 3x3 LU example;
3. "the example you just gave" follow-up;
4. no internal safety/verification metadata visible;
5. correct course-scoped retrieval sources.

### Future Student Model Bridge
Only after explicit review: promote selected stable signals from session-local
state into ANVAYA learning memory. No automatic global-memory writes are
allowed in 2.1.1.

## Live validation target

A useful test:

1. "Quiz me one question at a time on span, independence and basis."
2. Answer the question normally without saying "check my answer."
3. ANVAYA should treat it as an answer to the pending question.
4. ANVAYA should evaluate before moving forward and ask only one next question.
5. Ask "give me a hint" on a later question.
6. The same pending question should remain active.
7. Refresh the page.
8. The adaptive state should persist because it is stored in the Tutor session.
