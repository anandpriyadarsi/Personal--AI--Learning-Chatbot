# Phase 4.2 — Assessments + Assessment Topics SQLite Dual-Read Foundation

## Starting point and architecture finding

Phase 4.2 starts from `fc8d443` on `phase4/structured-cutover`, after the
Phase 4.1 Courses/Topics dual-read gate.

Inspection of that exact baseline found an important boundary: there is **no
`AssessmentService` and no assessment repository protocol/adapter yet**. The
live assessment API is still the legacy root module `assignment_exam_assistant.py`,
which owns `load_store()`, `save_store()`, assessment commands, and
`data/assessments.json` directly. The modernization documents describe an
`AssessmentService` as a future architecture, not a current public service.

Phase 4.2 therefore does not invent or rewire a service. It introduces the
smallest repository seam needed for shadow parity while deliberately leaving
`assignment_exam_assistant.py` unchanged. This preserves every existing public
function and writer until a later, explicit service-extraction/cutover unit.

## Authority boundary

Legacy JSON remains authoritative for both reads and writes.

```text
LegacyJsonAssessmentRepository ── authoritative result ──► caller
              │
              └── DualReadAssessmentRepository
                         │
                         └── SQLiteAssessmentRepository (read-only shadow)
                                      │
                                      └── parity diagnostics only
```

Only two backend modes exist:

- `legacy`
- `dual_read`

There is intentionally no SQLite-authoritative mode in Phase 4.2. Dual-read
requires an explicit already-open SQLite connection/repository and never opens
`data/learning_assistant.db` implicitly.

## Repository seam

`AssessmentRepository` is added to `repositories/interfaces.py` with the
legacy-shaped `load_state()` / `save_state()` contract.

`LegacyJsonAssessmentRepository` mirrors the existing legacy store behavior:

- application-visible store version is `2`;
- only the last 200 raw assessment records are exposed;
- assessment records are not silently normalized;
- reads do not create a missing data directory/file;
- writes use an explicit temporary file and atomic replace.

Existing `assignment_exam_assistant.py` writers are not disabled or redirected.

## SQLite assessment projection

`SQLiteAssessmentRepository` is read-only and reconstructs assessment semantics
from the Phase 3 schema plus migration ledger evidence.

It reads:

- `assessments`
- `assessment_topics`
- `courses`
- `topics`
- `migration_imports`

The adapter uses the latest `data/assessments.json` source hash and the latest
`data/courses.json` identity mapping. Actual SQLite foreign-key relationships
are used for course/assessment/topic ownership; ledger expectations are only
comparison evidence. This prevents corrupted relationships from being hidden by
otherwise correct import metadata.

All write attempts on the SQLite adapter raise
`SQLiteAssessmentRepositoryReadOnlyError`.

## Semantic parity domains

Phase 4.2 compares, without sorting away meaningful order:

- assessment catalogue and identity;
- course relationship;
- type/category;
- title;
- status;
- due date and due time;
- weightage percentage;
- total marks and obtained marks;
- description;
- assessment source ordering;
- raw assessment-topic labels and assessment ownership;
- assessment-topic source ordering;
- exact raw identities/status spellings;
- exact raw assessment records;
- legacy field-alias provenance (`type`/`assessment_type`, `due_date`/`due_on`,
  `weightage_percent`/`weight`, `total_marks`/`max_score`,
  `obtained_marks`/`score`);
- source version;
- exact source SHA-256;
- SQLite structural anomalies.

Raw comparison is deliberately exact. Whitespace, aliases, or raw status text
are not normalized merely to make parity pass.

The Phase 3 schema has no assessment alias table, so no fictitious assessment
alias entity is created. Alias provenance is instead compared from preserved raw
ledger evidence.

## Assessment-topic policy

Phase 3 intentionally imported assessment topics as unresolved raw labels with
`topic_id = NULL`. Phase 4.2 preserves that policy.

If a later human-reviewed SQLite row has a non-null `topic_id`, Phase 4.2:

1. validates that the linked topic exists and belongs to the same course as the
   assessment;
2. exposes the resolved identity in diagnostics;
3. marks semantic authority for that resolved identity as **deferred**, because
   legacy `assessments.json` has no normalized topic-ID field.

A cross-course resolved topic is a structural mismatch.

## Explicitly deferred / not applicable

### Assessment-level course credits

Phase 3 Fix 5 intentionally kept `course_credits` only in raw source/ledger
metadata instead of copying it into course offerings. Phase 4.2 reports matching
raw credit evidence as `deferred`, never as silently migrated authority.

### Direct semester relationship

The Phase 3 `assessments` table has no semester foreign key. Semester ownership
is indirect through the assessment's course and remains owned by the Phase 4.1
course domain. Phase 4.2 compares the course relationship and does not invent a
second semester authority.

### Questions and performance

This fix does not include questions, question sources, question-topic mappings,
attempts, mistakes, performance, learning memory, progress, plans, grades,
calendar, notes, resources, RAG, Obsidian, or dashboards.

## Structural anomaly detection

The SQLite shadow explicitly reports, among other failures:

- latest imported assessment rows that are soft-deleted;
- assessment course links outside the latest course import;
- actual course relationships that differ from migration evidence;
- assessment-topic rows attached to the wrong assessment;
- invalid or duplicate raw-label positions;
- raw labels that differ from ledger evidence;
- resolved topic IDs that are missing, deleted, or cross-course;
- live assessment / assessment-topic rows left from older assessment source
  hashes.

Source omissions are not silently interpreted as successful deletions.

## Read-only safety

Focused tests use only temporary SQLite databases and synthetic JSON fixtures.
They verify:

- legacy JSON bytes and SHA-256 do not change during reads;
- SQLite logical dump does not change during reads;
- `sqlite3.Connection.total_changes` does not change during reads;
- `PRAGMA integrity_check` returns `ok`;
- `PRAGMA foreign_key_check` returns no rows;
- a SQLite shadow failure never replaces a valid legacy result;
- a diagnostic sink failure never replaces a valid legacy result;
- a dual-read write delegates only to legacy JSON and leaves SQLite unchanged.

No real `data/*.json`, Obsidian data, knowledge content, or production-like
SQLite database is used by Phase 4.2 tests.

## Tests

Focused tests are in:

`tests/test_phase4_assessments_dual_read.py`

The synthetic source fixture is:

`tests/fixtures/phase4/assessments.json`

The focused suite covers clean parity, field/status/order/relationship
mismatches, exact raw evidence, legacy field aliases, structural corruption,
stale historical rows, resolved topic validation, read-only guarantees,
integrity/FK checks, factory validation, legacy-only writes, and the existing
legacy store's version/last-200 behavior.

Because the baseline contains no `AssessmentService`, the requested service API
regression is enforced by **not modifying** `assignment_exam_assistant.py` and
by characterizing its storage contract through the JSON adapter. A future
service extraction must have its own explicit compatibility gate.

## Gate

Run from the repository root while HEAD is still `fc8d443`:

```powershell
.\phase4_fix2_gate.ps1
```

The gate verifies:

1. focused Phase 4.2 tests;
2. Phase 4.1 Courses/Topics regression;
3. all Phase 3 regression/safety tests;
4. the complete pytest suite;
5. Python compilation;
6. installed dependency consistency;
7. `git diff --check` from `fc8d443`, including untracked Phase 4.2 files via
   temporary intent-to-add markers;
8. repository/private-data/runtime-DB hygiene.

It also blocks changes outside the explicit Phase 4.2 file set and blocks any
change to `assignment_exam_assistant.py` or later assessment domains.

## Rollback

Before final structured cutover, rollback is simple: keep using the legacy
backend and discard/rebuild the SQLite shadow. Phase 4.2 creates no SQLite
writer, disables no JSON writer, and deletes no legacy source.

## Non-goals

Phase 4.2 does **not**:

- modify `main`;
- modify or merge into `main` branch;
- introduce SQLite sole authority;
- dual-write assessments;
- disable or replace `assignment_exam_assistant.py` writers;
- auto-resolve raw assessment-topic labels;
- add assessment questions or performance data;
- begin Phase 5.
