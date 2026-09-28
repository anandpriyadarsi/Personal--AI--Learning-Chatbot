# Assessment Runner Math + Fill-up UX Upgrade

## Baseline

Canonical baseline: `main @ ae1fab749f6db2ee4a013a003ecfadd38b1eaea1`.

Production branch: `phase7.5.assessment-runner-ux/math-fillup`.

This is a bounded runner upgrade. It does not add a database migration and does not redesign Assessment Studio outside the timed test-taking surface.

## Product problems

The live runner previously rendered math-heavy questions as ordinary text, which made superscripts, subscripts, Greek symbols and matrix literals difficult to read.

Multi-part fill-up questions also used one generic text field, forcing the student to guess how to combine values such as `k`, `μ` and the number of free variables.

Question-palette states were visually too faint for rapid exam navigation.

## Math rendering

The runner adds a small safe DOM math enhancement layer.

It improves common ANVAYA assessment notation including:

- Greek symbols such as λ and μ;
- common relation/set symbols;
- superscript notation such as `A^-1` and `x^2`;
- subscript notation such as `[p]_B`;
- rectangular `[[...], [...]]` matrix literals.

The renderer builds DOM nodes with `textContent` / text nodes. It does not evaluate question content and does not inject package text with `innerHTML`.

This is intentionally lightweight and offline-friendly. The assessment package remains the source of question text.

## Structured fill-up responses

No schema migration is required.

For a multi-part `fill_blank`, ANVAYA derives visible input labels only from student-visible question wording. It never reads answer keys to decide what fields to show.

Supported conventions:

- explicit response cue, for example `Enter: k, μ, number of free variables.`;
- explicit visible blanks, for example `k = ___ and μ = ___`.

Each part is rendered as a separate labelled input.

The response continues to live in the existing session response JSON:

```json
{
  "value": "3,3,2",
  "parts": ["3", "3", "2"]
}
```

The legacy `value` is preserved for backward compatibility.

Older saved single-string responses such as `(3, 3, 2)` are split for display only when the number of parts is unambiguous.

A partially completed multi-part response is saved, but its palette state remains Not Answered until every required part has a value.

## Evaluation compatibility

Deterministic fill-up evaluation accepts the structured `parts` representation while matching existing accepted-answer strings.

Legacy formats such as:

- `3, 3, 2`;
- `(3,3,2)`;
- `2; 2, 3`;
- simple labelled assignment strings where unambiguous

remain supported.

No historical response or accepted-answer data is rewritten.

## No-JavaScript fallback

The normal HTML form posts repeated `fill_parts` fields, and the Flask route reconstructs the same ordered structured response.

Therefore structured fill-ups do not depend exclusively on JavaScript.

## Question palette

The runner strengthens all five existing state treatments:

- Not Visited;
- Not Answered;
- Answered;
- Marked for Review;
- Answered + Marked for Review.

Answered/review states use stronger fills, borders and state dots. The current question receives a prominent outline.

State meaning and runner persistence semantics are unchanged.

## Authoring contract

The reusable Alex authoring prompt now asks multi-part fill questions to expose the expected ordered fields in the visible question, e.g.:

`Enter: k, μ, number of free variables.`

Accepted answers must follow the same order.

## Preserved behavior

This upgrade does not change:

- server-authoritative timing;
- autosave serialization;
- interruption recovery;
- MCQ/MSQ controls;
- true/false behavior;
- Save & Next;
- Clear Response;
- Mark for Review & Next;
- final submission;
- answer secrecy;
- evaluation/grading boundaries;
- Assessment Intelligence;
- Adaptive Academic Loop.

## Visual validation boundary

Automated tests validate the rendering/data contracts. Final visual acceptance should be performed on the user's local ANVAYA instance with a math-heavy assessment because this environment does not provide a live localhost browser for the user's database.
