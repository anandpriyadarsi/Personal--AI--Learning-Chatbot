# Phase 3.1 Fix 5 — Assessments + Assessment Topics Importer

## Purpose

Fix 5 adds the next ordered structured-data shadow importer. It imports a
verified `data/assessments.json` snapshot into an explicit temporary SQLite
database after Fix 4 has established stable course identities.

The Phase 3 authority boundary remains unchanged:

> Legacy JSON/current files remain authoritative. SQLite is a migration and
> reconciliation target until the Phase 4 cutover gate is explicitly approved.

The importer never creates or opens `data/learning_assistant.db` by default,
never rewrites `assessments.json`, and never changes `courses.json`.

## Prerequisite course mapping

Every assessment needs a valid SQLite `course_id`. Fix 5 resolves the legacy
`course_id` only through the Fix 4 `migration_imports` evidence for
`data/courses.json`.

The importer:

- accepts an unambiguous `course:id:<legacy-id>` mapping;
- supports the Fix 4 `course:code:<normalized-code>` fallback used when a legacy
  course has no explicit ID;
- requires the mapped course row to exist and not be soft-deleted;
- rejects missing or ambiguous mappings instead of guessing by name;
- rolls back the entire assessment import if any course relationship cannot be
  resolved.

Run the courses/topics importer first against the same temporary database.

## Assessment field mapping

| Legacy JSON | SQLite | Policy |
|---|---|---|
| `id` | `assessments.id` | Required; converted to a stable UUID5 identity |
| `course_id` | `assessments.course_id` | Resolved through the Fix 4 import ledger |
| `type` | `assessment_type` | Known aliases normalized; unknown non-empty types retained and flagged |
| `title` | `title` | Required |
| `due_date` | `due_on` | Valid `YYYY-MM-DD` retained; invalid value becomes `NULL` and is flagged |
| `due_time` | `due_time` | Valid `HH:MM[:SS]` retained; invalid value becomes `NULL` and is flagged |
| `status` | `status` | Normalized to `pending`, `in_progress`, or `completed` |
| `weightage_percent` | `weight_bps` | Percentage multiplied by 100 |
| `total_marks` | `max_points_milli` | Marks multiplied by 1,000 |
| `obtained_marks` | `earned_points_milli` | Marks multiplied by 1,000 |
| `description` | `description` | Original string retained |
| timestamps | timestamps | Original non-empty strings retained; import timestamp is fallback |

The older `weight`, `max_score`, and `score` field names are accepted as
explicit aliases. Conflicting old/new values cause a hard failure rather than a
silent precedence choice.

Numeric conversion uses decimal arithmetic and documented half-up rounding only
when a value has more precision than the integer target unit. Invalid, negative,
or out-of-range values become `NULL` with a migration issue. Obtained marks that
exceed total marks also become `NULL`. In every case the exact original record
remains available in the import-ledger details and in the untouched JSON file.

Assessment-level `course_credits` is not copied into course offerings. It is
counted and flagged for later credit-authority reconciliation.

## Raw assessment-topic policy

Legacy assessment topics are free-text syllabus fragments, not authoritative
topic IDs. The supplied real source includes fragments produced by a
comma-separated split, so even a label that happens to equal a course-topic name
must not be linked automatically.

Fix 5 therefore creates one `assessment_topics` row per unique raw label with:

- a stable UUID5 row ID;
- the owning assessment ID;
- `topic_id = NULL`;
- the exact raw string in `raw_label`;
- a portable source marker;
- `confidence = NULL`.

Normalized label text is used only for deterministic identity and duplicate
detection. It is never substituted for `raw_label`.

Every label appears in `result.review_items` and emits an
`assessment_topic_review_required` issue. The pure
`render_assessment_topic_review_markdown()` helper can render those items for a
human decision without writing a report or exposing a physical machine path.

Blank, non-string, or normalization-equivalent duplicate labels are rejected.
They are not silently skipped or merged.

## Transaction, identity, and delta behavior

All assessment rows, raw topic rows, and import-ledger mappings are written in
one `BEGIN IMMEDIATE` transaction. Source bytes are hashed before parsing and
again before commit, so a source change during import rolls everything back.

For an unchanged source hash, a repeated import:

- creates no duplicate domain rows;
- creates no duplicate ledger rows;
- does not rewrite matched rows;
- still returns the review-required labels to the caller.

For a changed source hash, new ledger observations are recorded while the same
legacy assessment ID and normalized raw label continue to target the same UUID.

Source omissions are not interpreted as deletions in Fix 5. Legacy writers cap
history, so absence alone is not sufficient deletion authority. Deletion and
truncation reconciliation remains a later migration gate.

## Verification

Run:

```powershell
.\phase3_fix5_gate.ps1
```

The targeted tests verify:

1. assessment metadata and all raw labels import without changing either JSON
   prerequisite/source file;
2. assessment and topic IDs are stable UUIDs;
3. course relationships resolve only through Fix 4 ledger evidence;
4. an exact topic-name match remains unresolved and reviewable;
5. percentages and marks convert to basis points/milli-points;
6. V1 numeric aliases are supported and conflicting aliases are rejected;
7. invalid optional values are flagged without violating schema checks;
8. exact raw score evidence remains in the ledger when a target value is unsafe;
9. identical re-import is a no-op;
10. a changed hash updates stable targets and records new ledger evidence;
11. duplicate/malformed assessment or topic structures fail without partial
    writes;
12. a source changed after scanning is rejected before import writes.

The gate also runs every Phase 3 test, the full project regression suite, Python
compilation, `git diff --check`, and repository hygiene checks for production
database/private JSON files.

## Non-goals

Fix 5 does **not**:

- create or populate the production SQLite database;
- switch assessment services from JSON to SQLite;
- auto-merge or auto-correct malformed syllabus fragments;
- import questions, question sources, mappings, attempts, mistakes, or
  performance data from `assessment_workspace.json`;
- derive calendar events;
- resolve course credits;
- delete rows because a later legacy snapshot omits them;
- disable legacy JSON writers.

Those remain later Phase 3/Phase 4 units.
