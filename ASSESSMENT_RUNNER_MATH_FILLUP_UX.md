# Assessment Runner — Math + Fill-up UX Upgrade

## Baseline

Canonical baseline: `main @ ae1fab749f6db2ee4a013a003ecfadd38b1eaea1`.

Production branch: `phase7.5.assessment-runner-ux/math-fillup`.

This is a bounded test-runner refinement. It does not add a database migration and does not redesign Assessment Studio outside the live timed assessment surface.

## Problems addressed

The runner previously displayed math-heavy assessment text almost exactly as authored. Notation such as `A^-1`, `A^T`, `[p]_B`, Greek symbols and matrix literals was therefore visually ambiguous.

Multi-part fill-up questions also used one generic response input. A student had to guess a serialization such as `2,(3,-2)` even when the visible question clearly contained several independent blanks.

Question-palette answer/review states were also too faint for fast navigation during a timed test.

## Math rendering

The runner now loads a small, dependency-free DOM math enhancer.

It improves common ANVAYA assessment notation including:

- Greek symbols such as λ and μ;
- common set and relation symbols;
- superscripts such as `A^-1`, `A^T`, `x^2`;
- subscripts such as `[p]_B`;
- rectangular matrix literals such as `[[1,2],[-3,λ]]`.

The renderer creates DOM nodes and text nodes. It does not execute TeX, use `eval`, or inject package question text with `innerHTML`.

The parser deliberately does **not** convert an ordinary mathematical variable `x` into a multiplication sign. Multiplication should be authored explicitly as `×`, `\\times`, `·`, or equivalent supported notation.

This is intentionally a lightweight offline-friendly formatter, not a complete LaTeX engine.

## Structured fill-up responses

No schema migration is required.

For `fill_blank` questions ANVAYA can infer multiple visible inputs from student-visible wording only. Answer keys and solutions are not used to determine the UI.

Supported patterns include:

- an explicit ordered cue such as `Enter: k, μ, number of free variables.`;
- multiple visible underscore blanks such as `k = ___ and μ = ___`;
- tuple/vector blanks such as `[p]_B = (___, ___)^T`.

Each inferred part is rendered as a separate labelled input.

The existing session-response JSON remains authoritative:

```json
{
  "value": "2,3,-2",
  "parts": ["2", "3", "-2"]
}
```

The legacy combined `value` is preserved for compatibility.

A partially completed multi-part fill response is saved, but the question remains Not Answered until every required part contains a value.

Older single-string responses are split for display only when the number of parts is unambiguous.

## Evaluation compatibility

Deterministic fill-up evaluation can score structured `parts` against existing accepted-answer strings.

Legacy accepted-answer formats remain supported when their ordering is unambiguous, including comma-, semicolon-, pipe-, tuple- and simple assignment-style representations.

Historical assessment data is not rewritten.

## No-JavaScript fallback

The normal HTML form posts repeated `fill_parts` values. The Flask route reconstructs the same ordered response.

Structured multi-blank questions therefore do not depend exclusively on JavaScript.

## Question palette

All five existing states remain unchanged semantically:

- Not Visited;
- Not Answered;
- Answered;
- Marked for Review;
- Answered + Marked for Review.

The new runner stylesheet strengthens fills, borders and state indicators, and the current question receives a prominent outline.

## Authoring contract

The reusable Alex authoring prompt now asks multi-part fill-up questions to expose their expected answer fields in the visible question text, preferably with an ordered cue such as:

`Enter: k, μ, number of free variables.`

Accepted answers must follow that same order.

For mathematical content, the prompt prefers clear UTF-8 or consistent lightweight notation that the runner can display safely.

## Preserved behavior

This upgrade does not change:

- server-authoritative timing;
- autosave serialization;
- interrupted-session recovery;
- MCQ/MSQ behavior;
- True/False behavior;
- Save & Next;
- Clear Response;
- Mark for Review & Next;
- final submission;
- answer secrecy before submission;
- grading boundaries;
- Assessment Intelligence;
- Adaptive Academic Loop.

## Visual validation boundary

Automated web-rendering tests validate the relevant HTML/CSS/JS contracts, but this environment does not provide a live browser against the user's production database.

Final visual acceptance should inspect:

1. a math-heavy MCQ;
2. a matrix question;
3. a multi-part fill question using explicit `Enter:` labels;
4. a coordinate/tuple fill question;
5. all five palette states;
6. narrow/mobile width.
