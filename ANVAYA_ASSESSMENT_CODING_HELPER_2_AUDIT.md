# Assessment Coding Helper 2 audit

Baseline: `5916483b7c0e3af165c397faea657ed8bec5dd1d` (origin/main, fetched 2026-10-02).
Fresh isolated clone; feature branch `anvaya/assessment-uc100n-coding-helper-2`.
The old Assessment worktree was inspected read-only and is not reused. Its repair
is already present on main. No AGENTS.md is tracked. Two legacy blobs have CRLF
in conflict with .gitattributes; local info/attributes preserves their exact bytes.
No tracked normalization changes are included. Historical attached Phase 2/3
specifications predate this runner and are not implementation authority.

## Current architecture and strengths

- `assessment_runner_repository.get_coding_context` selects only session mode,
  status, expiry, ordinal, course snapshot, title and visible question text. It
  never selects answer_json, solution, rubric, expected_method or option metadata.
- `assessment_runner_service.coding_context` checks active, unexpired session,
  question ownership and current ordinal without heartbeat, visit or evidence writes.
- `assessment_coding_helper.build_request` validates field types/lengths and
  constructs TutorProviderRequest; route reuses OpenAICompatibleTutorProvider.
  Provider timeout is 45 seconds; browser abort is 55 seconds. Errors are generic.
- Eight actions already cover hints, concepts, operations, explanation, debug,
  memory, pseudocode and rebuild. Full solutions require an explicit switch and
  are limited to three practice actions. Restricted exams accept only predefined
  concept IDs and reject code, questions, attempts and free text. Unknown modes
  fail closed. Global disable is parsed explicitly from environment.
- Native dialog provides modal focus behaviour and Escape/return focus. Provider
  text uses textContent. Operations Map has 76 offline cards with seven useful
  fields, categories and search. Colab URL is HTTPS host-allowlisted and opens
  with target=_blank and rel=noopener noreferrer, without transmitting content.
- Existing Python, Node and real Chromium tests cover state isolation, navigation,
  persistence, failures and responsive layout. Catalogue examples are compiled;
  their execution/output was not asserted by existing automated tests.

## Findings answering the audit questions

1. The read-only projection, mode validation, offline map and drawer are sound.
2. Teaching is shallow: each action has one sentence of direction, no explicit
   response contract or explanation depth; output and debugging taxonomy are weak.
3. It is a prompted generic model, not an adaptive teacher; it cannot observe an
   independent attempt or measure mastery. Do not claim that it can.
4. It knows a course snapshot/title and optionally question text, plus submitted
   code/error/attempt. It lacks authoritative course authorization.
5. Policy instructions are separated from JSON, but teaching contracts can be
   stronger and catalogue entries currently never ground provider recommendations.
6. Hint depth exists but follow-up responses have no previous context. Rebuild
   hides the explanation but loses the teaching thread.
7. Static cards explain input/output/mistakes better than the unconstrained AI
   output. Viva, line changes and result interpretation need explicit contracts.
8. Map search is quick but only indexes category/what/why/syntax, has no category
   filter/copy/use-in-helper control, and lacks a distinct EDA group.
9. Allowed actions are repeated in policy, prompt and JS. Central mode definitions
   should own labels, instructions, exam eligibility and full-solution permission.
10. A single pre element visually flattens prose, code, lists and output. Full
    Markdown adds unnecessary attack surface; limited text block rendering fits.
11–12. Zero context makes ordinary follow-ups (groupby then agg) ambiguous. A
    small signed, expiring continuation envelope in page memory is worthwhile.
13. Existing actions partially distinguish intents; add output prediction, compare,
    viva and understanding-check, with explanation depth instead of more buttons.
14–15. Hidden fields are filtered, but ANY course can call the endpoint. Client
    mode already cannot bypass exam policy. Course code must come from a live
    session → assessment → course join, never title, text or request values.
16. Keep Colab an external tab; label it as execution and helper as teaching.
17. Highest value: course policy, explicit mode contracts, grounded operation cards,
    tiny follow-up context, safe readable blocks, viva and output reasoning.
18. Defer execution, IDE, Drive/OAuth, notebook sync, permanent chat, automatic
    mastery/evidence, Tutor integration and migrations.

## Integrity and UX risks to test

Signed history must be bounded, session/question/policy-bound, expire, and be
excluded from restricted exams. Opt-out of visible question or full solutions
must invalidate old context. Reset/close must abort and ignore late replies.
History and visible content remain untrusted data. Provider instructions reduce
solution leakage but are not a mathematical guarantee of provider obedience.
No claim of executed code is allowed. All rendered provider content remains text.
Assessment response, timer, palette and navigation handlers remain untouched.

Schema clarification: runner modes are constrained to exam/practice. Assignment
is an assessment_type; assignment acceptance uses type=assignment, mode=practice.
No schema expansion is needed. Existing policy's assignment mode spelling is
retained defensively but cannot be created as a session in the current schema.


## Independent second pass

A fresh reviewer independently read the full working delta and reran 97 helper
Python tests. Additional read-only synthetic probes rejected deleted/reassigned
course relationships and rejected question text changed during a provider call.
No critical or important authorization/data-integrity findings were reported.
One minor stale-error guard bypass was found: messages containing "Reset" could
bypass the request generation guard. Browser regressions reproduced it; the fix
makes stale guards unconditional and handles current reset responses explicitly.
The close regression additionally pinned synchronous cancellation before the
native dialog close event. No review findings remain deliberately deferred.

Author visual checks additionally found/fixed mobile Close-button width and the
category selector's accessible label. Core runner JS/CSS and answer logic remained
unchanged. Live provider quality remains a manual Windows check.
