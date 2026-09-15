# Phase 4.11 — Structured Authority Routing + Compatibility Writer Cutover

## Starting point

Phase 4.11 starts from `phase4/structured-cutover` at:

`0a92938ba468bd78d8188e45a661a080c85f1f8e`

`feat: add Phase 4.10 SQLite command repositories and legacy writer guards`

Phase 4.1–4.10 and the Final Phase 4 Structured Reconciliation Gate remain
intact. Phase 4.11 does **not** change `main` and does **not** perform the final
production authority switch.

## Objective

Phase 4.10 made two prerequisites true:

1. SQLite has an explicit transaction-safe command surface for the structured
   domains; and
2. legacy JSON writers fail closed after SQLite authority is activated.

Phase 4.11 adds the missing application compatibility/routing layer. Existing
V8–V13 public functions keep their signatures, but their persisted structured
reads and writes can now follow the explicit authority-control state.

The routing contract is:

- missing control / `legacy`: preserve the exact existing JSON behavior;
- `dual_read`: preserve the exact existing legacy-authoritative behavior;
- `sqlite`: read and write the structured compatibility state in the already
  existing SQLite database and leave legacy JSON bytes unchanged.

This unit makes the application *capable* of operating after promotion. It does
not itself write `storage_backend=sqlite`.

## Why compatibility projections are needed

The Phase 3 normalized schema is relational, while many V8–V13 procedural APIs
still expose exact JSON-shaped dictionaries. Rewriting every old public module
and caller in the same cutover would unnecessarily expand risk.

Phase 4.11 therefore stores an exact application-visible compatibility
projection for each migrated structured JSON store inside SQLite `app_settings`
under:

`phase4.compatibility_projection.<store>`

These projections are not a second authority. They live in the same SQLite
transactional authority as the normalized relational tables. Runtime writes
update the relevant normalized rows and their compatibility projection in one
transaction. Legacy JSON is no longer written when SQLite authority is active.

The nine compatibility stores are:

- courses;
- assessments;
- assessment workspace;
- learning memory;
- course progress history;
- weekly study plans;
- multi-course weekly plans;
- intelligent study plans;
- semester grade configuration.

## Runtime structured authority router

`personal_learning_assistant/repositories/structured_authority_router.py`
provides the small compatibility decision point used by the old modules.

### Legacy / dual-read state

The router returns a sentinel indicating that the caller should continue through
its pre-existing JSON code path. It does not open SQLite and does not create a
database.

### SQLite state

The router:

1. resolves the project-local `.phase4_authority.json` from the structured
   store path;
2. resolves `<project>/data/learning_assistant.db`;
3. requires that database to already exist as a regular non-symlink file;
4. opens it with SQLite URI `mode=rw`, which refuses to create a replacement
   database;
5. reads/writes through `SQLiteCompatibilityProjectionRepository`;
6. closes the explicit connection after the operation.

No import, read, or routing decision creates the production database or flips
authority.

## SQLite compatibility repository

`personal_learning_assistant/repositories/sqlite/compatibility_repository.py`
reconstructs the old JSON-shaped persisted API on top of SQLite.

### Read contract

After promotion, a missing compatibility projection is a hard error. The router
never silently falls back to legacy JSON for a structured domain that SQLite is
supposed to own.

### Write contract

A runtime compatibility write:

1. verifies `storage_backend=sqlite` and `legacy_writes_blocked=true`;
2. starts `BEGIN IMMEDIATE`;
3. reads the previous SQLite compatibility projection;
4. validates/resolves stable imported relational identities;
5. applies normalized relational updates for the changed store;
6. replaces the exact application-visible projection inside `app_settings`;
7. commits both together;
8. rolls everything back on failure.

The migration ledger remains historical migration evidence. Runtime commands do
not rewrite it to pretend that new application mutations were migration imports.

### Relational synchronization coverage

The compatibility writer synchronizes the Phase 4 structured domains already
migrated and reconciled:

- courses, semesters, semester-course relationships, topics and active course;
- assessments, assessment topics and assessment-backed academic deadline events;
- questions, raw sources, stored topic mappings, attempts and mistake events;
- learning-memory entries and topic-progress evidence;
- academic progress snapshots;
- study-plan headers and ordered items;
- grade scales/bands, semester settings, credits, manual grades, semester
  results and academic events.

It does not run planners, grading engines, automatic topic mapping, performance
algorithms, or progress engines merely to manufacture persistence state.

## Pre-promotion compatibility seed

`personal_learning_assistant/migration/compatibility_projection_seed.py` adds:

`seed_phase4_compatibility_projections(...)`

This helper is intentionally **pre-promotion only**. The final locked cutover
must call it after the last legacy delta import/reconciliation and before the
atomic authority switch.

The seed:

- requires an explicit SQLite connection;
- reuses the Phase 4.9 structured source scanner;
- validates the exact structured source manifest;
- copies application-visible JSON shapes into SQLite `app_settings`;
- records the source manifest hash used for the seed;
- seeds safe defaults only for the two already-optional Phase 4 sources:
  intelligent study plans and semester grade configuration;
- performs one SQLite transaction;
- never writes legacy source bytes;
- never writes the authority control file;
- never opens a default production database itself.

## Courses and Phase-5 document links

`courses.json.document_links` were deliberately deferred by Phase 3/4 because
knowledge/document identity belongs to Phase 5.

Phase 4.11 therefore does **not** silently claim this sub-domain as SQLite
structured authority.

After SQLite promotion:

- course catalogue/topic/active-course state comes from SQLite;
- document-link reads continue from the existing legacy `courses.json` as a
  read-only deferred sub-domain;
- document links are not copied into the SQLite compatibility projection;
- a course write that would change `document_links` raises
  `DeferredStructuredDomainWriteError` rather than losing or inventing a Phase
  5 relationship.

This is a deliberate, explicit boundary rather than hidden fallback.

## CourseService compatibility

`CourseService` already writes through a repository interface, so changing only
`course_manager.save_course_data()` would not be enough.

`personal_learning_assistant/repositories/routed_course_repository.py` wraps the
existing `LegacyJsonCourseRepository` and applies the same authority decision:

- legacy/dual-read -> existing legacy repository;
- SQLite -> compatibility projection/router.

`course_manager._build_course_service()` now injects this routed repository.
The new repository does **not** import the root `course_manager` compatibility
facade, preserving the Phase 2 dependency-direction guarantee.

## Procedural compatibility routing

The following public compatibility modules now check the router before their
old persisted read/write code:

- `course_manager.py`
- `assignment_exam_assistant.py`
- `assessment_question_workspace.py`
- `learning_memory.py`
- `academic_progress.py`
- `weekly_planner.py`
- `multi_course_planner.py`
- `intelligent_study_planner.py`
- `semester_grade_intelligence.py`

While authority is legacy or dual-read, their existing code remains the executed
path. When authority is SQLite, the read returns the SQLite projection and the
write returns before any JSON directory/temp-file/write operation.

The Phase 4.10 legacy guards remain in place as defence in depth.

## Side-effect and failure policy

Phase 4.11 fails closed after promotion:

- missing production DB -> explicit routing error, no new DB is created;
- missing required projection -> explicit error, no fallback to stale JSON;
- relational validation failure -> SQLite transaction rollback;
- deferred course document-link mutation -> explicit error;
- no write uses legacy JSON as a fallback after SQLite is authoritative.

Read paths do not run planners or engines and do not create progress snapshots,
plans, assessment evidence, grades, calendar state or memory events.

## Tests

`tests/test_phase4_structured_authority_routing.py` covers, among other cases:

- project-local DB routing without implicit creation;
- missing/legacy/dual-read control preserving old behavior;
- SQLite authority refusing a missing database;
- pre-promotion atomic projection seeding for all nine stores;
- optional-source defaults;
- document-link exclusion from the compatibility seed;
- fail-closed missing projection behavior after promotion;
- promoted reads using SQLite rather than changed legacy structured bytes;
- read-only deferred document-link merge;
- rejected post-promotion document-link mutation;
- promoted writes changing SQLite while leaving legacy JSON bytes unchanged;
- relational assessment/calendar synchronization;
- atomic rollback of workspace writes on invalid relationships;
- memory/progress/plan/grade write-through;
- integrity and foreign-key checks after routed commands;
- preservation of the Phase 2 course dependency direction;
- all nine compatibility readers/writers checking the router before legacy I/O;
- no implicit authority flip or production-database creation;
- exact Phase 4.10 baseline pin.

All test data is temporary and synthetic.

## Gate

Run:

```powershell
.\phase4_fix11_gate.ps1
```

The gate pins Phase 4.10 commit `0a92938`, runs the Phase 4.11 focused tests,
Phase 4.10 and 4.9 regressions, final Phase 4 reconciliation, Phase 4.1–4.8,
all Phase 3 tests, the complete project suite, compilation, dependency checks,
`git diff --check`, and repository/private-data hygiene.

It also statically verifies that:

- only declared Phase 4.11 files changed;
- Phase 4.1–4.8 shadow backends/readers remain unchanged;
- Phase 4.9 authority-promotion primitives remain unchanged;
- Phase 4.10 command repositories and legacy guards remain unchanged;
- runtime routing uses `mode=rw` and cannot silently create a DB;
- Phase 4.11 does not call the atomic authority-control writer;
- no production DB/control/lock/private JSON artifact is created or tracked;
- the Phase 2 course dependency-direction boundary remains intact.

## Non-goals

Phase 4.11 does **not**:

- modify `main` or `main` branch;
- create another development branch;
- set `storage_backend=sqlite`;
- create/copy/open a missing production DB implicitly;
- execute the final delta import;
- execute the final backup;
- disable rollback evidence;
- remove legacy JSON;
- migrate course document links;
- migrate Notes, Resources, Obsidian, knowledge documents, RAG, Dashboard 2 or
  agents;
- start Phase 5.

## Next boundary: final locked promotion

Once the Phase 4.11 gate is green and committed, the application has both:

- writable SQLite structured commands; and
- application-visible routing that can operate under SQLite authority.

The next unit is therefore the **Final Locked SQLite Authority Promotion**:

1. acquire the Phase 4 mutation lock;
2. scan/rehash all structured legacy sources;
3. import the final delta into the intended SQLite database;
4. run final reconciliation, integrity and foreign-key checks;
5. seed the nine Phase 4.11 compatibility projections from the exact locked
   source manifest;
6. create the final byte-preserving JSON + SQLite backup;
7. atomically write `storage_backend=sqlite` with legacy-writes-blocked evidence;
8. release the lock;
9. run post-promotion compatibility smoke tests and reconciliation;
10. retain the legacy JSON and rollback artifacts read-only for observation.

That promotion must be an explicit reviewed operation. Merely importing or
committing Phase 4.11 cannot perform it.
