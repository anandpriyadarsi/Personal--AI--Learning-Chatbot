# Phase 3.1 Fix 2 — Complete Academic SQLite Schema

## Purpose

This is the second implementation unit of **Phase 3 — SQLite and migration tooling**.
It adds the complete structured academic schema required for later shadow import,
reconciliation, and repository adapters.

The Phase 3 safety boundary remains unchanged:

> JSON/current files are still authoritative. SQLite is a temporary migration
> target until the Phase 4 structured-domain cutover is explicitly approved.

No real legacy JSON store, Obsidian note, source PDF, transcript, or semantic
vector is imported or rewritten by this fix.

## Controlled changes

Fix 2 adds:

- `0002_academic_schema.sql` after the immutable `0001_foundation.sql`;
- the academic structure, notes/vault metadata, resources/documents,
  assessments/performance, progress/planning, grades, and calendar tables;
- required relational indexes and six stable SQL read-model views;
- `tests/test_phase3_academic_schema.py`;
- `phase3_fix2_gate.ps1`;
- this design/verification note.

Fix 2 also updates the Fix 1 foundation test so it explicitly runs against a
temporary migration directory containing only `0001_foundation.sql`. This keeps
that test focused on the foundation migration after later migrations are added.

## Schema coverage

After migrations `0001` and `0002`, the temporary database contains the five
foundation tables plus 44 structured-domain tables.

### Academic structure

- `semesters`
- `courses`
- `semester_courses`
- `course_aliases`
- `course_relations`
- `topics`
- `topic_aliases`

`semester_courses.credits_milli` is the credit authority. External/supporting
courses remain distinct course identities and can be related with
`course_relations` rather than merged.

### Notes and vault metadata

- `vaults`
- `note_metadata`
- `tags`
- `note_tags`
- `note_courses`
- `note_topics`
- `note_links`
- `note_assessments`

`note_metadata` intentionally has no Markdown body column. Obsidian Markdown
remains the content authority; SQLite stores metadata, hashes, lifecycle state,
and relationships.

### Resources and knowledge documents

- `resources`
- `resource_courses`
- `resource_topics`
- `resource_notes`
- `resource_assessments`
- `resource_progress_events`
- `knowledge_documents`
- `resource_documents`
- `knowledge_chunks`
- `index_jobs`

`knowledge_chunks` may hold rebuildable extracted chunk text, but source files
remain authoritative. Semantic vectors are not stored in the primary database.
FTS virtual tables are deliberately not part of this core migration because FTS5
must remain an optional capability; a later search/index unit will detect FTS5
support and provide a degraded fallback when unavailable.

### Assessments and performance

- `assessments`
- `assessment_topics`
- `questions`
- `question_topic_mappings`
- `question_sources`
- `question_attempts`
- `mistake_events`

Questions use `ON DELETE RESTRICT` against assessments, so an assessment with
active question records cannot be hard-deleted accidentally. Normal removal is
represented by `deleted_at` on the assessment/question records.

### Progress, memory, and planning

- `topic_progress_events`
- `progress_snapshots`
- `learning_memory_entries`
- `study_plans`
- `study_plan_items`
- `study_sessions`

Topic state can remain materialized on `topics`, while changes/evidence are
preserved through append-only progress events. Historical plans and sessions are
modeled separately.

### Grades and calendar

- `grade_scales`
- `grade_bands`
- `semester_grade_settings`
- `manual_grade_entries`
- `semester_results`
- `academic_events`

Weights use basis points (`10000 = 100%`). Credits, marks, and grade points use
integer milli-units where exact arithmetic is important.

## Delete and relationship policy

Core user/history records use `ON DELETE RESTRICT` so hard deletion cannot
silently erase academic evidence. Pure relationship/cache rows use
`ON DELETE CASCADE` where removal of the parent should remove only the derived
relationship.

The schema also preserves unresolved relationships explicitly, for example:

- raw assessment topic labels before topic review;
- unresolved wiki-link target text;
- raw question source labels.

This allows later importers to be lossless rather than silently guessing.

## Stable read-model views

Fix 2 adds only stable relational views; academic formulas remain versioned
Python engines:

- `active_courses_with_semester`
- `open_assessments`
- `resource_latest_progress`
- `note_active_view`
- `question_latest_attempt`
- `course_assessment_weight_summary`

Priority scoring, performance evidence, grade projections, planner algorithms,
and the daily brief are intentionally not encoded as SQL formulas.

## Verification

Run from the repository root on `phase3/sqlite-foundation`:

```powershell
.\phase3_fix2_gate.ps1
```

The Fix 2 tests verify:

1. migrations `0001` and `0002` apply exactly once and checksum history is kept;
2. all required tables and read-model views exist;
3. `PRAGMA integrity_check` returns `ok`;
4. `PRAGMA foreign_key_check` returns no violations;
5. Obsidian note bodies are not stored in `note_metadata`;
6. hard deletion of an assessment with questions is rejected;
7. basis-point and milli-unit constraints reject invalid values;
8. pure join rows cascade while core records remain protected;
9. latest-attempt/latest-resource-progress and assessment-weight views behave as intended;
10. the core schema does not depend on FTS5 or vector storage.

The gate also runs the complete existing regression suite, compiles all Python,
runs `git diff --check`, and verifies that no production DB/WAL/SHM file is
created or tracked.

## Non-goals

Fix 2 does **not**:

- create or populate `data/learning_assistant.db`;
- import any legacy JSON/vault/document/package data;
- create domain SQLite repositories or switch application services to SQLite;
- create FTS tables or semantic vectors;
- reconcile malformed historical assessment/question data;
- add reverse exporters or migration reports;
- disable any legacy JSON writer;
- delete any legacy file or compatibility facade.

Those belong to later Phase 3 migration/import/reconciliation units and the
Phase 4 structured-domain cutover.
