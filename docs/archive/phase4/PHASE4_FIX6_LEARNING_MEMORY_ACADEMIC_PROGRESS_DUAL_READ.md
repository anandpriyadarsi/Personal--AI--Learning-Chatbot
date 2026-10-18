# Phase 4.6 — Learning Memory + Academic Progress SQLite Dual-Read Foundation

## Starting point

Phase 4.6 starts from `phase4/structured-cutover` at the completed and gate-passing
Phase 4.5 commit:

`2ca17c3238c2dbe7efc7f11d6db2c69f4de261bd`

Phase 4.1–4.5 remain unchanged.

## Objective and authority boundary

Phase 4.6 introduces read-only SQLite shadow support and structured semantic
parity for two related but separate domains:

1. Learning Memory
2. Academic Progress

> Legacy JSON/current storage remains authoritative during Phase 4.6.
> SQLite is shadow-read only.

The existing public modules `learning_memory.py` and `academic_progress.py` are
not rewired or rewritten. Existing application writes continue through the
legacy code. There is no `sqlite`/`sqlite_only` authority mode and no dual write.

## Architecture inspected

The implementation was based on the actual Phase 4 branch and Phase 3 Fix 9
migration model, including:

- `learning_memory.py` V8 memory normalization and course-aware scopes;
- `academic_progress.py` V9 history/snapshot and side-effect-free trend reads;
- `course_manager.py` current topic status/confidence and progress summary
  semantics;
- Phase 3 Fix 9 `learning_progress_importer.py`;
- Phase 3 tables `learning_memory_entries`, `topic_progress_events`, and
  `progress_snapshots`;
- migration-import ledger evidence for courses/topics and learning/progress;
- the established Phase 4.1–4.5 legacy-authoritative dual-read pattern.

The current `academic_progress.get_progress_trend()` already uses a read-only
history query path and does not create a new snapshot. Phase 4.6 preserves that
safety principle and does not call `record_progress_snapshot()` during parity.

## Legacy backend

`LegacyJsonLearningProgressRepository` is an explicit observational adapter over:

- `data/learning_memory.json`
- `data/course_progress_history.json`
- `data/courses.json` for the current topic progress view

Its memory normalization mirrors the existing V8 behavior: case-insensitive
weak/mastered de-duplication, weak-over-mastered precedence, bounded notes and
activity history, course-memory scopes, and the same activity/note shapes.

Its progress-history read mirrors the current `academic_progress.load_history()`
shape (`version` + `courses`). Current topic progress is derived from the
persisted course/topic state using the same topic-status normalization and the
same course progress summary formula already used by `course_manager`.

Unlike the public legacy memory loader, the observational adapter does not create
missing files. The returned default value is equivalent, but parity reads remain
side-effect free.

## SQLite repository

`SQLiteLearningProgressRepository` requires an already-open
`sqlite3.Connection`. It never accepts a database path, never creates a database,
and performs no writes.

Required Phase 3 tables are validated before reading:

- `migration_imports`
- `courses`
- `topics`
- `learning_memory_entries`
- `topic_progress_events`
- `progress_snapshots`

Migration ledger rows identify the current source hash and preserve raw/import
identity. Actual relational rows are then read independently. The ledger cannot
mask a missing row, moved relationship, wrong course/topic owner, stale target,
or duplicate legacy identity.

Every unsupported SQLite mutation raises
`SQLiteLearningProgressRepositoryReadOnlyError`.

## Learning Memory parity

Supported memory parity includes:

- global and course-scoped memory;
- weak topics;
- mastered topics;
- notes and note text;
- note timestamps when legacy source semantics retain them;
- recent activity question text;
- activity mode/topic/time;
- ordering inside each persisted memory list;
- raw course scope identity;
- raw topic labels;
- memory entry categories/kinds;
- source version/hash;
- resolved course/topic relationships;
- append-only weak/mastered `topic_progress_events` evidence;
- historical rows from older source hashes;
- unresolved/global topic labels retained as raw evidence.

Phase 3 Fix 9 deliberately does **not** mutate `topics.status` when importing a
weak/mastered memory marker. Phase 4.6 preserves that distinction: memory status
evidence is compared separately from current topic status.

Recent activity remains learning-memory evidence. It is not converted into a
study session.

## Academic Progress parity

Supported progress parity includes:

- current course/topic identity;
- topic order;
- current topic status;
- current confidence value;
- total/mastered topic counts;
- weak and not-started topic lists;
- existing course progress percentage semantics;
- persisted progress-history snapshot count;
- snapshot course identity;
- snapshot date/order;
- mastered/total topic counts stored in snapshot JSON;
- stored progress percentage;
- raw historical snapshot evidence retained by the migration ledger;
- source version/hash;
- current-vs-historical SQLite rows;
- actual course ownership of each snapshot.

Historical snapshots are compared as persisted historical evidence. Phase 4.6
does not call the current progress engine to regenerate an old snapshot and does
not rewrite old values to fit a newer algorithm.

## Important current-format difference

There is an existing format boundary that Phase 4.6 does not hide:

- current `academic_progress.load_history()` reads the `courses` mapping;
- Phase 3 Fix 9's migration helper `_progress_history()` reads the older
  `history` mapping.

Phase 4.6 does **not** silently rewrite one shape into the other. If the SQLite
shadow lacks current `courses`-shape history evidence, parity reports a mismatch.
If older `history`-shape evidence is observed, the difference remains explicit
and reviewable. A later migration/reconciliation fix can resolve the format
contract deliberately rather than changing historical data during a read.

## Memory and Progress remain distinct

Phase 4.6 does not collapse memory into progress:

- a memory note is not a progress snapshot;
- a weak/mastered memory marker is evidence, not an automatic mutation of topic
  status;
- current topic status/confidence comes from the course/topic state;
- historical progress snapshots remain historical records;
- user-authored memory is not converted into generated planner/dashboard data.

## Diagnostics

The backend follows the Phase 4 diagnostic convention and records structured
items containing:

- domain
- status
- key
- severity
- legacy value
- SQLite value
- message
- entity type
- course/topic identifiers when relevant

Mismatch/error states never replace the authoritative legacy read. Diagnostic
sink failures are swallowed after the report is stored because instrumentation
is observational.

Explicit deferred diagnostics are used for evidence that cannot safely become a
foreign-key claim, such as unresolved global memory topics or older rows retained
from previous source hashes.

## Raw vs canonical comparison

Canonicalization is limited to behavior already present in the legacy system,
for example existing topic status aliases and current memory normalization.

Raw/import evidence remains separately visible through:

- legacy keys;
- raw topic labels;
- migration source hashes/versions;
- ledger `raw` details;
- unresolved legacy scope/topic evidence.

The repository does not alter SQLite or legacy data in order to make parity pass.

## Structural validation

Focused tests exercise detection of:

- ledger targets missing from relational SQLite;
- memory scope moved to the wrong course;
- memory topic crossing course boundaries;
- current topic status/confidence divergence;
- progress snapshot attached to the wrong course;
- progress counts/score/date diverging from raw migration evidence;
- duplicate legacy identities mapping to multiple rows;
- unledgered live memory/progress rows;
- stale rows from older source hashes.

## Side-effect protections

Dual-read parity paths do not call:

- `record_progress_snapshot()`;
- learning-memory append/update functions;
- topic status writers;
- planner save functions;
- assessment-performance writers;
- grade/calendar writers.

Focused tests verify:

- learning-memory source bytes/hash unchanged;
- progress-history source bytes/hash unchanged;
- course source bytes/hash unchanged;
- relevant SQLite rows unchanged;
- `connection.total_changes` unchanged across parity reads;
- repeated reads deterministic;
- `PRAGMA integrity_check` returns `ok`;
- `PRAGMA foreign_key_check` returns no rows.

All fixtures are synthetic and all SQLite files are temporary test files.

## Files added

Phase 4.6 adds only:

- `personal_learning_assistant/repositories/json/learning_progress_repository.py`
- `personal_learning_assistant/repositories/sqlite/learning_progress_repository.py`
- `personal_learning_assistant/repositories/learning_progress_backend.py`
- `tests/fixtures/phase4/learning_memory.json`
- `tests/fixtures/phase4/course_progress_history.json`
- `tests/test_phase4_learning_progress_dual_read.py`
- `PHASE4_FIX6_LEARNING_MEMORY_ACADEMIC_PROGRESS_DUAL_READ.md`
- `phase4_fix6_gate.ps1`

## Verification

Run before committing:

```powershell
.\phase4_fix6_gate.ps1
```

The gate requires the exact Phase 4.5 base, only the approved Phase 4.6 working
files, focused Phase 4.6 tests, every previous Phase 4 focused test, all Phase 3
tests, the complete regression suite, compilation, dependency consistency,
`git diff --check`, and repository hygiene.

## Rollback

Before final structured cutover, rollback remains simple: use the `legacy`
backend or remove the Phase 4.6 observational adapters. Legacy files and writers
remain intact and SQLite has no application authority.

## Phase 4.6 non-goals

Phase 4.6 does not:

- modify `learning_memory.py` or `academic_progress.py`;
- modify planner/dashboard/agent consumers;
- create progress snapshots during reads;
- convert activity into study sessions;
- mutate current topic mastery from memory evidence;
- add SQLite writers or SQLite-only mode;
- migrate weekly/multi-course/intelligent study plans;
- cut over grades, semester intelligence, or academic calendar;
- migrate Notes, Resources, Obsidian, documents, RAG, or retrieval;
- begin Phase 5.

## Next Phase 4 boundary

After Phase 4.6 is gate-passing and committed, the next structured cutover unit
is the study-plan family (weekly / multi-course / intelligent plans), followed by
grades + academic calendar and the final Phase 4 cutover gate.
