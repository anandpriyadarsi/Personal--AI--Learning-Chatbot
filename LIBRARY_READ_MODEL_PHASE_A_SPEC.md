# Library read model — Phase A specification and execution plan

Status: authorized for implementation, feature branch only.
Parent: `main` at `2d05bd06b1f176d06b617ebb626c91eaee10d03b`.
Branch: `anvaya/library-read-model-phase-a`.

## Authority and scope

The execution instruction supplied by Anand is reproduced below. It supersedes historical vault-backed Notes assumptions. No production data, migration, indexing or branch integration is authorized.

ANVAYA — PHASE A: READ-ONLY LEARNING LIBRARY

Implement ONLY the bounded first unit described here.

This prompt authorizes implementation, fixture-based testing, documentation,
and a feature-branch commit/push after the required gates pass.

It does NOT authorize merging to main, changing production data, importing
legacy Resources, adopting Moodle/Tutor branches, or implementing later phases.

GOAL

Add a useful read-only Learning Library over existing Resources 2 and
registered Knowledge Documents.

Library is a projection, not a storage authority.

Use the existing Python/Flask/Jinja architecture and existing visual language.
Do not introduce a frontend framework or mandatory new runtime dependency.

AUTHORITATIVE BASELINE

Repository:
anandpriyadarsi/Personal--AI--Learning-Chatbot

Last verified main:
2d05bd06b1f176d06b617ebb626c91eaee10d03b

Tutor donor branch:
anvaya/tutor-2.3-teaching-orchestration
7fd24eb6695d7e1a904494756aa333fee274427b

These histories are divergent. Do not merge or cherry-pick Tutor/Moodle work.

The earlier audit established:
- Native ANVAYA Notes are independent from Obsidian.
- Native Notes currently use JSON and asset files.
- The Resources web page still uses legacy ResourceService.
- Resources 2 already exists in SQLite.
- Registered Documents and extraction metadata already exist.
- Library must not promote any storage authority.

Current code/tests and the corrective Notes/Obsidian separation specification
take precedence over older uploaded architecture reports.

EXECUTION METHOD

Use the executing-plans workflow for this bounded unit.
Do not restart the broad architecture audit.
Inspect only what is needed to confirm this scope and implement it safely.

1. REPOSITORY AND WORKTREE SAFETY

Before edits, inspect:
- git status --short
- git branch --show-current
- git rev-parse HEAD
- git log --oneline --decorate -15
- git branch -a
- applicable AGENTS.md instructions
- current remote main

Do not alter an existing dirty checkout.
Do not stash, reset, clean, rebase or discard unrelated work.

Create a new isolated worktree/checkout from freshly verified origin/main.
Use a new feature branch such as:
anvaya/library-read-model-phase-a

If that branch already exists, inspect it before deciding whether to resume
or use a new unique branch. Do not overwrite another session's branch.

If main advanced since the recorded baseline, inspect the relevant delta.
Proceed if it does not invalidate this unit. Report a material authority,
schema or route conflict rather than silently changing the architecture.

Do not use the old Phase 3 checkout or the Tutor checkout as the parent.

Record the starting commit and original worktree status.

2. EXACT SCOPE

Add:
- GET /library
- GET /library/resources/<resource_id>

Add a Library link to the existing Learning navigation group.

Keep existing Notes, Resources, Knowledge, Obsidian, Tutor, Assessment,
Planner and Calendar routes, labels and behavior unchanged.

Do not redirect /resources or rename /knowledge in this unit.

List:
- Active, non-deleted Resources 2 records.
- Registered Documents with no resource_documents relationship.

Do not make a Document linked only to an archived/deleted Resource reappear
as an ungrouped Library item.

One Resource produces one top-level row.
A Resource can contain multiple Documents.
A shared Document may appear within multiple Resource detail pages.
Do not merge Resources or Documents by content hash.

Expose:
- Course filter using existing SQLite relationship IDs.
- Item-kind filter: all, resource, document.
- Pagination.
- Resource detail showing recorded metadata, academic links and all linked
  Documents.
- Existing safe Knowledge reader links for Documents.
- Safe external Resource links when already present.

Do not add a second full-text search box. Universal Search owns discovery.

Do not scan the vault or source roots.
Do not read/import legacy Resources to populate this page.
Do not create demo rows in runtime databases.
Do not infer course relationships from titles or filenames.
Do not copy note bodies or source files.

3. MODEL AND SERVICE CONTRACT

Create immutable dataclasses in:
personal_learning_assistant/domain/learning_library_models.py

Define:
- LibraryQuery
- LibraryItemRef
- LibraryAcademicLabel
- LibraryItem
- LibraryDocumentView
- LibraryResourceDetail
- LibraryPage

LibraryQuery:
- course_id: optional string
- item_kind: all | resource | document; default all
- page: positive integer; default 1
- page_size: integer 1–100; default 25

Reject invalid query values with a safe 400 response.

LibraryItemRef:
- kind: resource | document
- id: canonical existing ID

Presentation keys:
- resource:<id>
- document:<id>

These are not new persisted IDs.

LibraryItem should expose only read-model fields needed by the UI:
- key and canonical reference
- title and recorded type/provider
- canonical course/topic labels
- learning status when applicable
- linked Document/note counts when supported
- extraction summary
- safe open target

LibraryResourceDetail contains a Document collection, not one document_id.

Document views can expose current content hash internally, but must not
present it as an immutable historical source_version_id.

Do not implement a source-version model in this unit.

Service interface:
LearningLibraryService.list_items(query: LibraryQuery) -> LibraryPage
LearningLibraryService.resource_detail(resource_id: str)
    -> LibraryResourceDetail

Routes call the service; routes/templates contain no SQL.

4. READ-ONLY PERSISTENCE

Create:
personal_learning_assistant/repositories/sqlite/learning_library_repository.py
personal_learning_assistant/services/learning_library_service.py

The repository reads existing canonical tables only.

Do not use the general connect_database helper for Library reads:
it can create databases and configure WAL.

Require an existing configured database.
Use SQLite URI mode=ro and query_only.
Do not change journal mode.
Do not run migrations or initialize schema.
Do not create missing directories or databases.
Close connections reliably.
Use a consistent read transaction for count/page/detail reads.

Do not use immutable=1 against a live database.

Use parameterized queries and bounded pagination.
Batch relationship reads; avoid per-row N+1 loading.
Use deterministic ordering:
updated_at descending, case-insensitive title, then stable kind/ID.

Preserve the archive/deletion semantics of existing Resources 2.

Filter courses using explicit resource_courses relationships.
Do not invent a course for an ungrouped Document.
Do not use unrelated JSON labels to replace SQLite identity.

Distinguish:
- Ready with results.
- Ready but empty.
- Ready with no filter matches.
- Unavailable database/schema.

Return a safe 503 for database/schema unavailability.
Do not disguise it as zero learning materials.
Return 404 for an unknown or hidden Resource detail.

Do not load retrieval indexes, embeddings, AI clients or Moodle.
Do not claim index readiness based solely on extraction status.

5. CONFIGURATION AND ROLLBACK

Provide:
- LEARNING_LIBRARY_ENABLED, default true.
- LEARNING_LIBRARY_DATABASE_PATH, default data/learning_assistant.db.
- LEARNING_LIBRARY_SERVICE_FACTORY for fixture/test injection.

When disabled:
- Hide the Library navigation link.
- Return 404 for the new Library routes.
- Do not construct the Library service or open the database.

Do not change existing service-factory configuration behavior.

6. UI

Create:
personal_learning_assistant/ui/web/templates/library.html
personal_learning_assistant/ui/web/templates/library_resource.html

Reuse existing ANVAYA components and dark-theme tokens.
Add a scoped stylesheet only if required.

List page:
- Title: Library.
- Course and item-kind filters.
- Readable rows/cards with title, type/provider, course labels,
  learning status where applicable, and extraction summary.
- Pagination.
- Clear empty/unavailable states.
- A normal link to existing Resources, explaining that this first view
  shows registered material while existing Resources remains available.

Resource detail:
- Resource metadata and learning status.
- Course/topic relationships.
- All linked Documents.
- Existing related-note information only where safely available.
- Safe external link if valid.
- Back to Library.

No Add, Import, Sync, Reindex, Edit, Delete, Generate or migration actions.

Do not render fake disabled feature buttons for later phases.
Do not expose absolute local paths, tokens or database errors.
Escape titles and metadata.
Permit external links only through established safe HTTP(S) validation.
Do not activate javascript:, data: or file: URLs.

Use “View source” or another accurate label for the existing Knowledge
reader; do not promise a native PDF viewer if that route displays extracted
content.

The new Library pages must not emit reading-heartbeat, Companion or other
mutation requests.

7. EXPECTED FILE BOUNDARY

Create:
- personal_learning_assistant/domain/learning_library_models.py
- personal_learning_assistant/repositories/sqlite/learning_library_repository.py
- personal_learning_assistant/services/learning_library_service.py
- personal_learning_assistant/ui/web/templates/library.html
- personal_learning_assistant/ui/web/templates/library_resource.html
- tests/test_learning_library_read_model.py
- tests/test_learning_library_routes.py

Bounded edits:
- personal_learning_assistant/ui/web/routes.py
- personal_learning_assistant/ui/web/templates/base.html
- tests/test_phase7_5_anvaya_shell.py

Optional:
- A dedicated Library stylesheet referenced only by these pages.

Documentation:
- LIBRARY_READ_MODEL_PHASE_A_SPEC.md
- LIBRARY_READ_MODEL_PHASE_A_IMPLEMENTATION_REPORT.md

Do not broadly refactor routes.py or unrelated services.
Explain any necessary scope expansion before making it.

8. TESTS

Use temporary fixture databases and fake source metadata.
Production data, Notes and the vault must not be used as test fixtures.

Add meaningful tests proving:
- One Resource with several Documents appears once at top level.
- Shared Documents remain correctly linked.
- Ungrouped Documents appear without automatic Resource creation.
- Documents linked to archived/deleted Resources do not reappear as orphans.
- Explicit course filtering works and never guesses.
- Stable pagination and deterministic ordering.
- Resource details contain all linked Documents.
- Missing database is not created.
- Missing/incompatible schema is not migrated.
- Unavailability differs from an empty result.
- Unknown/hidden detail returns 404.
- Invalid query values return 400.
- Read operations preserve academic rows, schema, source files and
  configured journal mode.
- No network, vault scan, ingestion, index or mutation service is invoked.
- Unsafe links and untrusted titles are handled safely.
- Feature disablement prevents service/database construction.
- Existing navigation/routes and Resources writes remain unchanged.

Use fixture fingerprints/row snapshots for read-purity checks.
Do not depend on global filesystem timestamps or ordinary SQLite
implementation details as the only proof.

Run the new tests plus relevant existing suites:
- tests/test_phase5_resources2_core.py
- tests/test_phase7_5_operational_notes_resources.py
- tests/test_phase7_5_anvaya_shell.py
- tests/test_phase7_5_12_2_recovery.py
- tests/test_phase7_5_15_10_notes_obsidian_separation.py

Reverify test paths at current HEAD.
Run additional existing gates only where required or needed to resolve
a concrete risk.

Record exact commands and actual results.
Do not treat historical reports as a fresh pass.

9. VISUAL VALIDATION

Run the app against isolated fixtures.

Inspect desktop and mobile views for:
- Mixed Resource and Document list.
- Multi-document Resource detail.
- Empty Library.
- No filter matches.
- Unavailable database.
- Long titles and multiple course labels.

Check:
- No horizontal overflow.
- Keyboard navigation and visible focus.
- Correct navigation active state.
- Usable filter labels and pagination.
- Adequate contrast.
- No misleading extraction/retrieval claims.

Use available browser/screenshot tooling and record the evidence.
Do not claim visual validation if it was not performed.

If visual tooling is unavailable, finish the implementation and executable
tests, document the remaining manual gate, and report the unit as awaiting
visual validation. Do not publish it as fully accepted.

10. DOCUMENTATION AND COMPLETION

Document:
- Verified parent branch/commit.
- Exact read-model and route scope.
- Authority boundaries.
- Queries/grouping behavior.
- Configuration.
- Empty/unavailable behavior.
- Tests and visual evidence.
- Known limitations.
- Feature-flag rollback.
- Explicitly deferred phases.

Before committing:
- Inspect the full diff.
- Check for unintended files and whitespace errors.
- Confirm no migrations, runtime databases, Notes, vault files, source
  materials, credentials or generated indexes are included.
- Confirm unrelated working trees were not altered.

Commit only the Phase A allowlisted changes after required gates pass.
Push only the new feature branch, without force.
Do not push directly to main.
Do not merge, rebase other branches or delete branches.
Do not start Phase B.

If a required gate is blocked, preserve the completed work in the isolated
checkout and report the exact blocker without claiming completion.

Final report:
- What changed.
- Parent and final commit.
- Tests and visual validation.
- Confirmation of unchanged data authorities.
- Remaining limitations.
- Feature branch/commit link if pushed.
- Confirmation that main was not merged or modified.

STOP after this unit.

### Task 1: Read-only Library vertical slice

- Write fixture-backed read-model and route tests; run them and observe missing-feature failures.
- Implement immutable models, read-only repository/service, two GET routes, templates and scoped styles.
- Run new and named regression suites; resolve regressions within scope.
- Validate populated, detail, empty, no-match, unavailable and long-title views at desktop/mobile sizes using isolated fixtures.
- Obtain one independent whole-diff review, address material findings with regression tests, finalize the implementation report.
- Commit and push only allowlisted Phase A files after gates pass. Never merge main.

Verification: the new Library tests and the five regression suites named above must pass. No database/source/index mutations may occur on Library reads. Visual evidence must be recorded before publication.
