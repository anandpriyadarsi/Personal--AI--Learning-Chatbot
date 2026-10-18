# Phase 3.1 Fix 6 — Assessment Questions + Question Sources Importer

## Purpose

Fix 6 adds the next ordered structured-data shadow importer. It imports a
verified `data/assessment_workspace.json` snapshot after Fix 5 has established
stable assessment identities.

The Phase 3 authority boundary remains unchanged:

> Legacy JSON/current files remain authoritative. SQLite is a migration and
> reconciliation target until the Phase 4 cutover gate is explicitly approved.

The importer never creates or opens `data/learning_assistant.db` by default,
never rewrites the workspace, assessment, or course JSON files, and never
changes a source document.

## Prerequisite assessment mapping

Each workspace needs a valid SQLite assessment foreign key. Fix 6 resolves the
workspace `assessment_id` only through Fix 5 `migration_imports` evidence for
`data/assessments.json`.

The importer:

- requires the workspace object key to equal its `assessment_id`;
- resolves the exact `assessment:id:<legacy-id>` ledger identity;
- requires one unambiguous, existing, non-deleted assessment target;
- rejects missing or ambiguous mappings instead of guessing by title/course;
- rolls back every question/source write if any workspace cannot resolve.

Run the courses/topics importer and assessments/topics importer first against
the same temporary database.

## Question field mapping

| Legacy workspace field | SQLite | Policy |
|---|---|---|
| `assessment_id` | `questions.assessment_id` | Resolved only through Fix 5 ledger evidence |
| question array position | `ordinal` | Stored as one-based source order |
| `id` | `id` | Required; stable UUID5 scoped to assessment and legacy question ID |
| `text` | `question_text` | Required non-blank string; exact content/newlines retained |
| `marks` | `max_marks_milli` | Decimal marks multiplied by 1,000 |
| `status` | `status` | Canonical workspace status; known aliases normalized |
| `notes` | `user_notes` | Exact string retained; absent/`null` becomes empty text |
| source snapshot hash | `import_batch_id` | Stable UUID5 for one approved source snapshot |
| timestamps | timestamps | Original non-empty strings retained; workspace/import time is fallback |

Marks use decimal arithmetic and documented half-up rounding only when the
source has more precision than milli-marks. Non-finite or negative values
become `NULL` with an issue. Unknown statuses become `not_started` with an
issue. Exact raw values remain in the import-ledger evidence and untouched JSON.

## Lossless parser-review policy

`assessment_workspace.json` is already parsed data, but the supplied real store
contains equations, headings, prompts, and sentence continuations split into
separate records. Fix 6 deliberately treats every array element as one raw
question unit:

- no adjacent records are merged;
- no equation or heading is discarded;
- no question number is inferred from text;
- source order is retained;
- every imported question emits `question_parser_review_required` and appears
  in `result.review_items`.

The pure `render_assessment_question_review_markdown()` helper renders the raw
units for a human reconciliation decision without writing a report or exposing
the physical machine path of the legacy JSON source.

## Question-source policy

The legacy file importer may add `source_file`, `source_page`, and
`source_question_number` to a question. Those are annotations, not authoritative
document/resource/note IDs.

When a non-blank `source_file` exists, Fix 6 creates one `question_sources` row:

| Target column | Imported value |
|---|---|
| `question_id` | Stable imported question ID |
| `document_id`, `resource_id`, `note_id` | `NULL` — no relationship is guessed |
| `page_number` | Positive integer when valid; otherwise `NULL` plus an issue |
| `locator` | `question:<source_question_number>` when scalar/non-blank |
| `raw_source_label` | Exact `source_file` string |

Every imported raw source annotation emits `question_source_review_required`.
A page/locator without a usable source label is preserved in ledger evidence
but does not create a fake source row. A changed raw snapshot updates the raw
annotation while preserving any document/resource/note FK that a later human
review has already established.

## Explicitly deferred records

Fix 6 does not create topic mappings, attempts, or mistake events. Non-empty
legacy `topic`/`topic_mapping` data is counted as `deferred_topic_records`.
Non-empty `attempts`/`performance`/`mistakes` data is counted as
`deferred_performance_records`. Both remain available in the exact raw question
inside the ledger for their ordered follow-up importers.

## Transaction, identity, and delta behaviour

All questions, raw source rows, and import-ledger mappings are written in one
`BEGIN IMMEDIATE` transaction. Source bytes are hashed before parsing and again
before commit; a source change at either point prevents partial import.

For an unchanged source hash, re-import:

- creates no duplicate question, source, or ledger row;
- does not rewrite matched rows;
- returns the same parser/source review inventory.

For a changed source hash, deterministic IDs update the same logical question
and source rows while recording new ledger observations. Existing imported
questions are temporarily moved to safe ordinals inside the transaction so a
source reorder cannot violate `(assessment_id, ordinal)` uniqueness.

Source omissions are not treated as deletion authority. An omitted imported
question remains undeleted and is appended after current source rows, preserving
its prior relative order. A non-imported SQLite row occupying a required source
ordinal causes a hard reconciliation failure instead of silent movement.

## Verification

Run:

```powershell
.\phase3_fix6_gate.ps1
```

The focused tests verify:

1. sanitized questions import losslessly through the Fix 5 assessment mapping;
2. JSON prerequisite/source hashes stay byte-for-byte unchanged;
3. question/source/import-batch IDs are stable UUID values;
4. identical re-import is a true no-op, including source annotations;
5. changed snapshots preserve question IDs and safely reorder ordinals;
6. source omission does not silently delete an earlier question;
7. raw source labels/pages/locators import without guessed FKs;
8. a later reviewed document FK survives raw annotation updates;
9. marks/status normalization is explicit and raw unsafe values stay in ledger;
10. topic and performance evidence remains explicitly deferred;
11. known malformed parser fragments remain separate and review-required;
12. orphan/invalid source metadata creates issues, not invented relationships;
13. missing prerequisites and malformed/duplicate identities fail cleanly;
14. a late invalid workspace rolls back earlier workspace writes;
15. source changes before or during the transaction leave no partial rows.

The gate also runs every Phase 3 test, the full regression suite, Python
compilation, `git diff --check`, and repository hygiene checks for production
database/private JSON files.

## Supplied-data rehearsal

The ordered Fix 4 → Fix 5 → Fix 6 rehearsal against the supplied private data
copy imported 26/26 raw question units. All 26 were returned for parser review.
The supplied snapshot contained no recorded `source_file`, non-empty topic
mapping, attempt, or performance values, so Fix 6 correctly created zero source,
mapping, and attempt rows. A repeated import matched all 26 questions and made
zero changes. `PRAGMA foreign_key_check` was clean, `PRAGMA integrity_check`
returned `ok`, and SHA-256 checks confirmed all three source JSON files remained
byte-for-byte unchanged.

## Non-goals

Fix 6 does **not**:

- create or populate the production SQLite database;
- switch assessment services from JSON to SQLite;
- merge or correct parser fragments automatically;
- guess knowledge-document, resource, note, or topic relationships;
- import question topic decisions, attempts, mistakes, or performance history;
- delete rows because a later source snapshot omits them;
- disable legacy JSON writers.

Those remain later Phase 3/Phase 4 reconciliation and cutover units.
