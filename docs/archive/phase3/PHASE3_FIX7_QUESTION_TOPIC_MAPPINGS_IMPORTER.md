# Phase 3.1 Fix 7 — Question Topic Mappings Importer

## Purpose

Fix 7 imports the legacy question-topic decision layer from a verified
`data/assessment_workspace.json` snapshot after Fixes 4–6 have established
stable courses, topics, assessments, and questions.

The Phase 3 authority boundary remains unchanged:

> Legacy JSON/current files remain authoritative. SQLite is a migration and
> reconciliation target until the Phase 4 cutover gate is explicitly approved.

The importer never runs the heuristic topic mapper, never creates or opens
`data/learning_assistant.db` by default, never rewrites any JSON file, and never
changes course progress/mastery.

## Legacy mapping contract

The V10.3 mapper stores two related facts inside each question:

- `topic` is the question's current accepted topic tag;
- `topic_mapping` stores `method`, `suggested_topic`, `score`, `confidence`,
  ranked `alternatives`, `accepted`, and `mapped_at`.

Fix 7 preserves both facts. A current `topic` is imported as accepted. A
resolved candidate that has not been accepted remains `proposed`. Ranked
alternatives remain separate relational rows rather than being flattened into
one guessed answer.

If `topic_mapping.accepted` is true but `suggested_topic` and the current
`topic` disagree or the current topic is absent, the explicit accepted flag is
preserved, but the inconsistency emits a warning and review item.

## Ordered prerequisites

Fix 7 requires this sequence against the same temporary SQLite database:

1. Fix 4 imports courses and topics.
2. Fix 5 imports assessments and resolves their course foreign keys.
3. Fix 6 imports questions for the exact workspace source hash.
4. Fix 7 imports topic decisions/candidates from that same verified snapshot.

Question lookup uses the Fix 6 ledger identity for the exact source path, hash,
type, version, assessment ID, and question ID. A changed workspace must therefore
pass through Fix 6 before Fix 7. This prevents topic mappings from moving ahead
of their owning question version.

## Exact topic resolution policy

A raw topic label resolves only when exactly one live Fix 4 topic satisfies all
of these conditions:

- it belongs to the assessment's imported course;
- its `topics.normalized_name` equals the raw label after case-folding and
  whitespace normalization;
- it has Fix 4 `data/courses.json` migration-ledger evidence;
- it is not soft-deleted.

Fix 7 does not use fuzzy similarity, question text, a topic from another course,
or an undeclared alias during migration. Zero or multiple targets create a
review item and no `question_topic_mappings` foreign key.

## Target mapping

| Legacy evidence | SQLite target | Policy |
|---|---|---|
| current `topic` only | one mapping row | `state = accepted`, `method = legacy_manual_topic`, nullable score/rank |
| `suggested_topic` | mapping row | rank 1; state follows explicit acceptance/current tag |
| matching alternative | same stable mapping row | suggestion + alternative origins retained in ledger |
| other alternatives | separate mapping rows | source-order rank, normally `state = proposed` |
| `score` | `score` | finite `0..1`; otherwise `NULL` plus warning |
| `method` | `method` | original non-blank method; explicit legacy fallback if invalid/missing |
| `mapped_at` | timestamps | mapping time retained; question/import time is fallback |
| accepted decision | `reviewed_at` | set to mapping/fallback time |
| confidence/origin | `reason` | transparent provenance text; exact raw object remains in ledger |

Stable UUID5 mapping IDs are scoped to the question identity and normalized
topic label. Whitespace/case-only changes therefore update the same target.

If a suggested topic is unexpectedly absent from `alternatives`, it becomes
rank 1 and the listed alternatives retain their relative order starting at rank
2. Duplicate normalized alternatives are rejected rather than silently merged.
If the primary suggestion score conflicts with its matching alternative score,
the primary score is used, both raw values remain in ledger evidence, and a
warning is emitted.

## Audited absence and review reporting

The supplied workspace currently has no non-empty topic tags or mapping
metadata. Creating fake mapping rows would violate the no-guessing policy.

Fix 7 therefore creates one idempotent migration-ledger observation per
question, even when no mapping exists. The observation records:

- raw `topic` and `topic_mapping` values;
- the owning question/course target IDs;
- every candidate's exact resolution outcome and target IDs;
- explicit audited absence when the candidate list is empty.

An unmapped question emits `question_topic_mapping_missing` and appears in the
pure `render_question_topic_mapping_review_markdown()` report with its raw
question text. Proposed, unresolved, ambiguous, and inconsistent mappings also
remain reviewable. The renderer writes no file and exposes only the portable
canonical source path, never the physical machine path.

## Malformed optional evidence

Structural ambiguity is rejected before writes:

- `topic` must be string/null;
- `topic_mapping` must be object/null;
- `alternatives` must be an array of objects with non-blank topic labels;
- duplicate normalization-equivalent alternatives are invalid.

Unsafe scalar metadata is handled conservatively:

- invalid/out-of-range scores become `NULL`;
- a non-boolean accepted flag becomes false, so nothing is silently accepted;
- invalid methods use `legacy_topic_mapping`;
- unknown confidence labels remain visible in reason/ledger evidence.

## Transaction, idempotency, and omissions

All resolved mapping rows, mapping ledger rows, and per-question observations
are written in one `BEGIN IMMEDIATE` transaction. Source bytes are hashed before
parsing and again before commit. Any prerequisite, identity, or TOCTOU failure
rolls back the complete Fix 7 unit.

For an unchanged source hash, re-import:

- creates no duplicate mapping or observation row;
- does not rewrite matched rows;
- returns the same accepted/proposed/unmapped/review inventory.

For a changed source hash, stable mapping IDs update the same logical rows while
new ledger evidence records the new source observation. An omitted legacy
mapping is not treated as deletion authority: its earlier row remains as mapping
history, while the new observation records the current absence.

## Verification

Run:

```powershell
.\phase3_fix7_gate.ps1
```

The focused tests verify:

1. unmapped questions create audited observations without guessed mappings;
2. all source/prerequisite JSON hashes remain unchanged;
3. identical re-import is a no-op for observations and real mapping rows;
4. manual tags import as accepted exact-course mappings;
5. pending suggestions stay proposed with score, rank, method, and confidence;
6. confirmed mappings preserve accepted/reviewed state;
7. ranked alternatives become separate deterministic rows;
8. a missing suggested candidate is prepended without changing relative order;
9. a same-name topic in another course is never linked;
10. invalid scalar metadata cannot silently accept or fabricate data;
11. score conflicts preserve both raw values and emit a warning;
12. inconsistent accepted metadata remains explicitly reviewable;
13. malformed/duplicate candidate structures fail before Fix 7 writes;
14. changed snapshots update stable IDs and record new evidence;
15. Fix 6 evidence is required for the exact workspace hash;
16. source omissions preserve earlier mapping history;
17. a late missing prerequisite rolls back earlier mapping writes;
18. source changes before or during the transaction leave no partial rows.

The gate also runs every Phase 3 test, the full regression suite, Python
compilation, `git diff --check`, and repository hygiene checks for production
database/private JSON files.

## Supplied-data rehearsal

The ordered Fix 4 → Fix 5 → Fix 6 → Fix 7 rehearsal against the supplied private
data copy scanned all 26 questions. The current snapshot contains no accepted
topic tags or mapping candidates, so Fix 7 correctly created zero relational
mapping rows, classified all 26 questions as unmapped/review-required, and
created 26 audited-absence observations. An identical rerun matched all 26
observations and changed zero rows. `PRAGMA foreign_key_check` was clean,
`PRAGMA integrity_check` returned `ok`, and SHA-256 checks confirmed all three
source JSON files remained byte-for-byte unchanged.

## Non-goals

Fix 7 does **not**:

- execute or tune the V10.3 heuristic mapper;
- infer topics from question text;
- change topic/course mastery or progress;
- import attempts, marks earned, mistakes, or performance evidence;
- reconcile the malformed question fragments from Fix 6;
- delete mapping history because a later snapshot omits it;
- switch application services from JSON to SQLite;
- disable legacy JSON writers.

Those remain later Phase 3 reconciliation/import units and Phase 4 cutover work.
