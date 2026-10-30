# ANVAYA Library 2.0 — Complete Android Academic File Manager Implementation Master Prompt

## Mission and authorization

Project: ANVAYA — Personal Learning Intelligence.
Repository: `anandpriyadarsi/Personal--AI--Learning-Chatbot`.
Implementation agent: GPT-6.1 Sol.
Priority: HIGH. Target: private, single-user, Android-first standalone app, especially Samsung Galaxy M11.

Perform real implementation, migration, meaningful testing, failure repair, verified GitHub integration and APK delivery. Do not respond with another proposal, a mockup-only change or an unverified APK. This prompt is the development handoff from a read-only audit dated 30 October 2026. You must refresh repository state before implementation, but need not repeat the entire audit.

Create an implementation branch from current verified main. Implement the scope below, preserve existing data and working features, open a reviewable PR, merge only after release gates pass, validate merged main, build/test the release APK and publish through the project's supported workflow. The user's instruction authorizes this development/release sequence subject to the stated gates. Never bypass failing tests, force-push unrelated work, merge stale draft PRs blindly, reset the user's data or claim unavailable checks passed.

The product principle is mandatory: **Library manages original academic files; Tutor understands them through private derived processing and retrieval.** Original viewing must never be replaced by extracted text, Markdown or AI summary.

## 1. Verified baseline to refresh

Audit main was `2e6d35627ae353835cf777e89fc23e994a4a6e44`, tree `82ee0e1662517c38efe200f84b3ae7b1f0c37b6e`, merged PR #60 (head `b000b834e53c94d4109d50c3e100adee72e056b8`). Version is `1.3.0-unified-debug`, code 18; application ID `in.anvaya.privateapp`; min API24; compile/target API35; ARM32, ARM64, x86_64. Keep application ID and private roots.

Latest audited release: `anvaya-unified-v1.3.0-debug-2e6d35627ae3`, a debug prerelease, not production signing. Canonical exact-main run `40790061955` has successful Ubuntu/Windows/aggregate jobs and logs for full pytest, real browser, Node, characterization, migration and cleanliness gates. Release run `40794767203` has successful build/JVM, installed API31/API35 and publish jobs. These prove the audited baseline only, not your changes.

PR heads #57/#55/#52/#51/#49/#44/#43/#41/#39/#35/#13/#9 were ancestors of main despite remaining open. #29 and #27 diverged. Refresh all open PRs, preserve applicable current functionality and do not blindly merge historical branches. Existing integration docs are context, not proof of current completion.

Current architecture is Java WebView + Chaquopy Python 3.11 + Flask served on authenticated numeric loopback inside Android. Core features run without a laptop or external server. Android currently blocks non-loopback Python networking and cloud AI. Preserve that policy in initial Library 2.0.

The current native file store and academic registry are separate:

- `/library/files`: `data/native_library/library.sqlite3` (user_version 1), `blobs/<sha256>`, `tmp/`. Native folders/documents/pages/page_fts; PDF/PPT/PPTX originals; 100 MiB individual upload; optional daemon indexing; secure original handoff.
- `/library`: read-only academic projection from `data/learning_assistant.db`; registered resources/documents plus Saved Links view. Legacy Android PDF import stores `data/documents/<hash>.pdf`, registers canonical identity, synchronously ingests text; 20 MiB cap; manual rebuild of `data/tutor_retrieval`.
- Native `pages` are not automatically included in Tutor's `knowledge_chunks`/retrieval generations. “Search Ready” in Files currently does not mean Tutor-ready.
- Registry View source goes to `/knowledge/item/<id>` and defaults to raw extracted passages. Its original link is based on an external HTTP(S) URI, not the private phone file.
- Learning Studio accepts authored JSON/ZIP packages tied to canonical registered PDF IDs/hashes; raw uploads do not generate lessons. Its source resolver currently enforces PDF and 20 MiB.
- Registry display renames use `<academic-db>.display.sqlite3`, while native renames use documents.display_name. Preserve both.
- Current backup is an unencrypted in-memory ZIP with 100 MiB aggregate/1,000-entry limits and native restore schema ==1. It is not adequate for a growing Library.

## 2. Source map and defects to address

All paths below are repository-relative; inspect the named functions before editing.

| Area | Existing files/functions |
|---|---|
| Native file ownership | `personal_learning_assistant/services/native_document_library.py`: `NativeDocumentLibrary.upload/update/copy/delete`, `create_folder/update_folder/delete_folder`, `run_pending`, `search`, `list_documents`, `resolve_android_document`, `_verified_original`, `document_filename` |
| Native extraction | `personal_learning_assistant/services/native_document_extraction.py`: `extract_pages`, `_pdf_text`, `_slides`, `_PDFBudget`, `ocr_available` |
| Native HTTP/UI | `personal_learning_assistant/ui/web/native_library.py`: `service/protect/home/upload/document/original/open_document/learning`; templates `native_library.html`, `native_document.html`, `native_learning_handoff.html`; `static/js/native_library.js`, `static/css/native_library.css` |
| Academic browse | `personal_learning_assistant/ui/web/routes.py`: `learning_library` around 4703, `learning_library_resource` around 4768; `services/learning_library_service.py`; `repositories/sqlite/learning_library_repository.py`; template `library.html` |
| Display names | `ui/web/library_rename.py`, `repositories/sqlite/library_display_repository.py` |
| Legacy import/rebuild | `ui/web/android_device.py`: `_register_local_pdf`, `library_pdf_upload`, `source`, `tutor_index` |
| Canonical ingestion | `services/knowledge_registry_service.py`, `unified_ingestion_service.py`; `repositories/sqlite/knowledge_registry_repository.py`, `ingestion_repository.py`; `ingestion/source_resolver.py`, `extractors.py` |
| Retrieval | `repositories/sqlite/retrieval_source_repository.py`: `active_records/source_fingerprint`; `retrieval/index_builder.py`: `RetrievalIndexBuilder.build`; `services/unified_search_runtime.py`: `assert_fresh/search`; `services/retrieval_service.py`, `retrieval/rag_context.py`, `tutor/retrieval_planner.py` |
| Old text reader | `ui/web/routes.py:knowledge_item` around 4281; `services/knowledge_reader_service.py:view`; `templates/knowledge_item.html` |
| Course authority | `services/android_subject_restore.py`, `domain/canonical_topic_catalogues.py`, `services/course_dashboard_service.py`, `repositories/routed_course_repository.py`, `domain/course_models.py` |
| Learning Studio | `learning_studio/sources.py:RegisteredSources.__call__/catalogue`, `learning_studio/store.py`, `ui/web/learning_studio.py` |
| Runtime/backup | `personal_learning_assistant/android_runtime.py:Runtime/_start/_offline_network_policy`; `android_backup.py:export_backup/_validate_databases/stage_restore/apply_pending_restore` |
| Native document bridge | `android/app/src/main/java/in/anvaya/privateapp/MainActivity.java:openNativeDocument/noDocumentViewer`; `NativeDocumentRequest.java`, `DocumentIntents.java`, `DocumentFileProvider.java`, `PdfPageActivity.java` |
| Picker/security | Same Java directory `UploadSnapshot.java`, `UploadFileProvider.java`; `android/app/src/main/AndroidManifest.xml`, `res/xml/document_paths.xml`; `android/app/build.gradle` |
| Migrations | Native schema in service constructor is separate from academic `repositories/sqlite/migration_runner.py` and `migrations/`; respect each owner. |

Verified failure/limitation details:

1. Same bytes + original filename reimport returns the old record globally, ignoring a newly selected folder/course. Audit reproduced this. Replace silent behavior with explicit reuse/copy decisions.
2. Native schema folders have no semester/course binding. File subject is independently nullable. Add consistent academic ownership rather than hard-coded folder names.
3. Native metadata/content search is normalized exact phrase, not expected prefix filename search; separate metadata search from content search.
4. Android `Runtime.authenticate_native_request` locks all non-static requests except `notes_media`, including Library uploads/status/browse. Do not assume Flask route-only concurrency tests prove installed responsiveness.
5. Native original verification hashes a full file under a storage lock; do not remove integrity checks casually. Measure and narrow locking safely.
6. Native service daemon restarts jobs on initialization; it is not durable OS scheduling and should have only one production owner. Add persisted lease/checkpoint semantics before adding another worker.
7. All folders are serialized into UI dropdowns; avoid whole-tree payloads at scale.
8. Native PPTX extraction honors actual presentation relationship order; academic PPTX extractor sorts slide filenames. The unified path must preserve real slide order/citations.
9. Current Native Library mobile overflow hit width is 32px and some toolbar heights 38px. Increase actual targets to ≥48 CSS px without oversized cards.
10. Current release workflow hard-codes 1.3.0/code18/report/tag metadata; update coherently for new release.

## 3. Product scope and course truth

Primary navigation: `Library → Semester 1 → Subject → Folder → Original file`.

Find actual IDs through the routed course owner. Confirmed authoritative Semester 1 subjects are:

- MA103N — Linear Algebra
- UC100N — Data Science and Artificial Intelligence
- CY100N — Engineering Chemistry
- DE100N — Design Thinking and Prototyping
- UC103N — Indian Knowledge System

The sixth course was not established. Preserve any legitimate sixth already configured on the user's device, otherwise show the five verified subjects plus Add subject. Record the missing sixth as unresolved, never invent one. Do not hard-code course names into storage keys. Support future term/semester bindings, including eight B.Tech semesters, but show only legitimately configured terms.

Initial release includes: semester/subject navigation; nested editable folders; opt-in templates; compact list/grid; metadata search; original storage/viewing; batch import; rename/move/copy; long-press and accessible multi-select; favorites/recent; file details; sorting name/date/size/type; recoverable Trash/Undo; Unsorted/repair; storage usage and reliable backup/export; automatic local processing/Tutor bridge; legacy compatibility; meaningful tests and release.

Defer eager document thumbnails, cloud sync, vector servers, full native UI rewrite, automatic lesson generation and mandatory OCR/multimodal models. These must not delay originals-first core functionality. Optional OCR is capability-gated and only claimed if actually executed and verified. Do not add unneeded infrastructure.

## 4. Data model and ownership decisions

Extend the existing native file engine; keep academic owners and add explicit mapping/outbox. Do not replace all stores with a new database or copy original bytes into every subsystem.

Implement versioned native schema migrations with:

- Semester stable IDs, number/label, optional year/program and ordering.
- Subject bindings referencing existing course identity + authority namespace and semester ID. Avoid duplicate course catalogues; course code alone is not a universal ID.
- Existing folder IDs retained; parent/name/normalized sibling key/binding/order/timestamps/node kind/template origin/lifecycle.
- Existing document IDs retained; immutable blob hash/size/MIME/format, names, placement, effective subject, favorite/opened/trash metadata, metadata revision.
- Blob locator/availability and reference accounting. Unique original bytes count separately from placement count.
- Native↔canonical source links with ID namespace, content hash/version, state and idempotent operation ID.
- Durable processing jobs/outbox with exact hash/extraction version/generation, lease/attempt/checkpoint/cancellation/error code.
- Migration ledger and template application records with stable origin keys.

Physical folder placement determines effective subject binding; ordinary folder moves may change binding and must propagate consistently to descendants, with a preview/confirmation for cross-subject bulk moves. Protect semester/subject roots from accidental generic-folder deletion; management occurs through academic settings. Preserve custom names/order. Use one physical placement per record; explicit copy/shortcut may share bytes. Do not silently infer courses from filenames.

Duplicate policy: same-name/different bytes defaults to Keep both with suffix; same bytes/name offers existing location or linked copy at chosen destination. No silent overwrite. If replacement is implemented, create a new content version, cancel old generation and preserve historical hash references; it must not be a hidden upload side effect.

Copies may reuse source/extraction for identical hash, but subject-filtered Tutor retrieval must honor current placement scope and deduplicate evidence. Never let a shared canonical identity leak unrelated subject results. Reference-aware deletion is required: Trash immediately excludes the placement from active search/Tutor; another live placement keeps shared bytes. Permanent deletion must inspect all live native and canonical/Studio references, explain linked-source consequences and either block until explicit resolution or retain a clearly disclosed source pin. Never orphan a lesson silently. Historical records may retain an unavailable-source tombstone, not silently retarget to different bytes. Existing indexing opt-outs remain respected.

## 5. Original storage, formats and native opening

Keep originals in app-private durable filesDir, not cache, WebView localStorage or temporary provider URIs. Import through the existing Android picker/snapshot mechanism, then stream/hash/fsync/stage/publish. Success means durable original plus metadata, independent of extraction. Handle low storage, cancellation, duplicate names, unsafe paths, interrupted writes and reimport repair. Account for temporary snapshot/staging headroom. Keep individual 100 MiB limit initially with clear units; increase only with evidence.

Storage and ACTION_VIEW scope: PDF, PPT, PPTX, DOC, DOCX, PNG/JPEG/WebP, TXT/Markdown/CSV and ordinary lab text such as `.py`. Treat code as text, never run it. Define a single safe format registry mirrored/tested at Python/native boundaries. Validate signatures/container structure where applicable, keep unsupported extraction as Stored only, and reject executable/app imports. Do not execute macros or active HTML. A valid stored file may still lack a compatible installed viewer.

Preserve PR #60's behavior:

- Default tap → same-origin native request → verified stable-ID resolver → ACTION_VIEW and correct MIME.
- Use non-exported narrow FileProvider path, `content://`, read-only temporary URI grant and ClipData. No write grants, raw file paths, auth cookie, loopback URL or arbitrary content path escapes.
- Open with forces chooser; Share/Export remain explicit. Viewing must not extract, upload or mutate the file.
- Provider MIME/filename must match actual immutable format, including Unicode/renamed files. Update `DocumentIntents.supportsMime`, `DocumentFileProvider.getType`, upload/export type policy consistently.
- No compatible viewer → retained-file message, Save/Export and Cancel; no raw-text fallback. Keep PDF visual matched-page reader as optional action.
- Returning from viewer preserves folder/search/scroll. External page/slide deep-link support varies; show locator and do not promise universal jump support.

Do not request broad all-files storage access. SAF handles explicit user import/export; originals remain durable after provider permissions lapse. App update persistence requires compatible signing; uninstall/clear-data removes private storage. Never advise uninstall as a migration workaround.

## 6. Automatic extraction, retrieval and privacy

Build a working end-to-end path: Original → durable local job → canonical source/chunks → current retrieval generation → Tutor answer/citation → original file.

New-file local processing may default on after a clear first-use local-only notice/setting; preserve old explicit disabled records. No mandatory rebuild after upload. Keep raw extracted text private; short content search snippets are optional explicit search results, never the default reader. Ordinary statuses should be Saved, Preparing for Tutor, Ready for Tutor, Partly readable, Stored only or Needs attention. Advanced retry/diagnostics live in Details/Settings.

Required bridge contract:

1. Native transaction records file and outbox event after bytes are durable.
2. Canonical owner registers/reuses verified identity; existing canonical IDs/path keys/relations survive. Introduce managed native-blob resolution with logical filename and MIME so digest filenames do not break extractor selection.
3. Use bounded native extraction once and adapt real page/slide units into canonical chunks. Preserve methods/coverage/locator/content version. Resolve PPTX order discrepancy. Do not duplicate source files merely to make a path resolver happy.
4. Publish owner transactions, refresh the academic WAL snapshot and build/coalesce matching Tutor index generations automatically. Mark Ready only after publication for exact source fingerprint/hash. Do not disable stale-index validation.
5. Idempotent replay after crashes must not create extra sources/chunks. Generation checks stop stale writes after disable/delete/replacement. Metadata rename does not re-extract; subject move updates retrieval scope; deletion cleans eligibility and stale hits.
6. Every citation carries source identity, version hash, real chunk/page/slide/line and original mapping. Click opens original; missing historic version is unavailable, not another file. Unknown answers/poor extraction must say insufficient evidence rather than fabricate citations.

Use one bounded extraction worker, short DB transactions, checkpoints and cancellation. Never parse every file on launch. For persistent Android scheduling, use WorkManager only as a dispatcher into the same leased queue through a lightweight Python worker entry point; avoid initializing the complete WebView/server or creating a second competing daemon. Support storage/battery constraints and resume. Document force-stop/reopen limitations. If no OS scheduler is added, state honestly that work resumes when app opens; do not claim closed-app completion. Prefer meeting durable scheduling in this release if compatible with existing host.

Offline supported baseline: embedded PDF text, PPTX slide text, UTF-8 text, local lexical retrieval. DOCX may use bounded XML; legacy DOC/PPT need external conversion for indexing. Current Android has no Tesseract/PyMuPDF OCR or FastEmbed model package. Never claim OCR, math/diagram understanding, image reasoning or semantic embeddings based on text extraction. If optional local OCR is supplied, test actual engine on scanned/mixed pages with limits; keep original intact. No network AI by default and no model download hidden in import. Future external processing requires explicit per-file/session consent, provider/data disclosure and revocation. Keep initial Android network policy unchanged.

Performance: remove broad request-lock interference only after separating owner-safe Library requests and proving thread/SQLite safety. Runtime-level tests must show navigation while import/indexing occurs. Bound pages/text/archive expansion; do not weaken existing parser safeguards. Full-file integrity verification stays off UI thread; optimize lock duration only with race tests.

## 7. Mobile interface specification

Retain dark ANVAYA identity, cyan/teal accents and bottom dock. No Samsung branding/assets.

- Library: semester cards, small Recent/Favorites entry and visible Unsorted count. One scoped search; overflow contains Sources & links, Trash, Storage & backup.
- Semester: subject folders with code/name, configured only, Add subject. No duplicated hero or upload panel.
- Subject/folder: compact breadcrumb/back, list default, `+` opens Import files/New folder. Search current scope; sort/view/filter sheet. File rows roughly 64–76 CSS px, ≥48px touch targets, readable two-line names and type/size. Persist layout/sort/folder/scroll.
- Row tap opens original. Overflow: Open with, Rename, Move, Copy, Favorite, Details, Export, Trash. Long press selects; accessible Select option too. Selection toolbar shows count and bulk actions with per-item errors.
- Upload: chosen destination explicit; native multi-picker; bounded sequential queue with per-file progress/results; cancel remaining safely; duplicate decision sheet.
- Search: filename prefix/substring and metadata/path/type/course; current/all scope. Optional Content results show filename and actual locator; navigate original. One search form, filters in sheet.
- Details: ordinary metadata and Tutor availability; no absolute storage paths/raw OCR. Advanced diagnostic codes/retry behind disclosure.
- Unsorted: all uncertain/unmapped/missing-source records retained; Assign and Repair original. No false auto-course classification.
- Sources & links: secondary view preserving registered resources, saved links/progress and provenance. Keep Notes, Obsidian and Learning Studio distinct owners under their appropriate workspaces; do not duplicate them into file rows.
- Trash: restore/undo and explicit permanent deletion with reference consequences. Initial policy: no silent automatic purge; show storage consumed.
- Storage & backup: unique bytes, cache/index, Trash/free space, last verified backup; export/restore/cache cleanup.

Library must not navigate to raw Knowledge Reader as default file viewing. Preserve its study companion/history/Ask ANVAYA data and old links via source-aware original adapters; links lacking a recoverable original show unavailable with repair, not extracted text as replacement. Keep legacy upload URLs as compatibility adapters into the new owner where safe; remove repeated upload surfaces. Route migration must preserve intended query/saved-link behavior.

Accessibility: text scaling to 200%, TalkBack labels/focus, no color-only status, keyboard support, reduced motion. Back first dismisses dialogs/selection, then ascends hierarchy. Lazy type icons first; do not eagerly generate thumbnails or add external CDNs.

## 8. Folder templates

Templates are editable, opt-in, previewed and versioned data, never hard-coded storage paths. Suggested defaults:

- CY100N: Lecture Notes, Professor's PPTs, PDFs, Assignments, Lab Materials, Previous Year Questions.
- UC100N: Lecture Materials, Lab Programs, Datasets, Assignments, Practice.
- MA103N: Lecture Notes, Practice Problems, Tutorials, Previous Year Questions.
- DE100N: Lecture Materials, Project Work, Assignments, References.
- UC103N: Lecture Notes, Readings, Assignments, Practice.

Custom folder is an action, not a compulsory empty folder. Record template-origin IDs; reapply is idempotent, respects renamed/deleted/reordered folders and shows additions before applying. Support reuse in a future term without linking its folders to the old term.

## 9. Mandatory backup/migration/rollback

Do backup compatibility before irreversible schema adoption. Current backup's aggregate 100 MiB limit and in-memory construction must be addressed, not merely documented as sufficient.

Implement bounded-memory streaming backup/export with consistent SQLite snapshots and manifest of sizes/hashes/schema versions. Support a realistic collection >100 MiB; use a validated larger cap or multipart manifest with safe restore limits, never unlimited decompression. Retain v1 import. Stage/validate restore before atomically replacing; keep previous data. Reject unsafe paths, symlinks, duplicate entries, corrupt DBs and any unexpectedly missing or hash-mismatched promised payload. For pre-existing unavailable/corrupt originals identified during inventory, backup v2 must support explicit unavailable-original tombstones with expected hash/reason and preserved metadata/source links. Restore these to Recover/Unsorted without claiming bytes were recovered; known legacy damage must not block migration of intact files. Update `android_backup._validate_databases` for new native schema and migrate staged v1 backups. New metadata/schema must be rejected safely by old apps. Unencrypted export must be labeled honestly; do not call it encrypted.

Migration rules:

1. Inventory identities, hashes, roots, folder tree, course authority, display-title overrides and Notes/Studio/Tutor relations.
2. Produce verified pre-migration backup/export of all available originals, with explicitly declared tombstones for pre-existing unavailable originals. On insufficient space leave old readable data and offer recovery; never silently omit available bytes or claim declared unavailable bytes were backed up.
3. Preserve every native ID/blob and explicit indexing choice. Preserve registered `knowledge_documents.id`, path_key, hash and source relations. Map through namespace+ID+hash, not titles.
4. Registered local originals may be exposed using a validated managed resolver or staged verified relocation. Do not delete old path until every consumer resolves the new locator; minimize byte duplication and bound temporary staging.
5. Same bytes across stores may share physical storage after verified migration, but separate meaningful placements/identities remain until explicitly reconciled. Missing originals keep metadata in Recover/Unsorted. External links stay links, not falsely offline files.
6. Uncertain/multiple course relationships and mixed folders remain Unsorted; filename-based guesses are suggestions only.
7. Notes, attachments, study history and Learning Studio package IDs/source hashes stay unchanged. Existing authored PDF packages retain their validation constraints; do not fabricate native PPT lessons or silently remove size checks.
8. Journal cross-store phases and idempotent operations. Inject crashes after each checkpoint; resume yields same counts and identities. Publish new retrieval generation only after checks.
9. Before new writes, rollback can restore verified snapshot with compatible binary/signature. After new writes, require reconciliation/reverse export; never restore old metadata over new originals blindly.

Do not clear originals/metadata/source maps in cache cleanup. Reference-aware garbage collection must use all owners and never race a live import/index/view/backup. No forced downgrade or uninstall to get a test green.

## 10. Test matrix and acceptance gates

Use real temporary files/DBs and installed receivers; UI-element presence alone is not acceptance. Extend existing tests:
`tests/test_native_document_library.py`, `test_native_library_routes.py`, `test_native_library_browser.py`, `test_learning_library_read_model.py`, `test_learning_library_routes.py`, `test_learning_library_wal_bridge.py`, `test_library_document_rename.py`, `test_library_knowledge_consolidation.py`, `test_library_saved_resources_consolidation.py`, `test_android_backup.py`, `test_android_runtime.py`, `test_android_navigation_performance.py`, `test_phase5_rebuildable_retrieval.py`.
Android: `NativePdfHandoffTest`, `NativePdfPageTest`, `UploadPickerTest`, `OfflineSmokeTest`, `MediaHandoffTest`, `SmartNestedNotesTest`. Add bridge/migration/format/queue tests with meaningful assertions.

| Required scenario | Verification |
|---|---|
| 1. Upload/byte integrity | Compare input/stored/export/receiver SHA256 across rename/restart; no rewrite. |
| 2. All supported formats | Valid fixtures, correct MIME/current filename, missing extraction truthful; malformed containers safe. |
| 3. Nested folders | Persist create/rename/move/order; reject cycles; effective subject inheritance. |
| 4. Rename/move/copy/delete | Stable IDs/bytes, shared blob reference counts, bulk partial failures, Trash/restore/undo. |
| 5. Duplicate names/bytes | Explicit same-file handling honors destination; Keep both for conflicting bytes. |
| 6. Migration | Mixed old stores/IDs/overrides/missing originals/courses; idempotent and interrupted migrations; no lost links. |
| 7. PDF viewer | Separate-UID reads/renders exact original; no write/delete grant; chooser/default/rename. |
| 8. PPT/PPTX viewer | Correct MIME/bytes with installed receiver and real valid slides; vendor-app smoke where available. |
| 9. Missing viewer | Retained original, export/cancel/return state; no extracted-text substitute. |
| 10. Search | Prefix/Unicode/scope/type/path; rename/move/delete freshness; content locator opens original. |
| 11. Background processing | Real Runtime middleware, concurrent navigation/upload; restart/job lease/retry/cancellation. |
| 12. Scans/OCR | Unsupported state without OCR; actual engine/scan test if enabled; partial coverage honest. |
| 13. Tutor | Upload unique fact → automatic retrieval → correct subject/hash/page/slide citation; absent fact no fabricated evidence. |
| 14. Offline | Airplane mode core operations, no provider/model/network dependency. |
| 15. Low storage | Fail snapshot/write/fsync/DB/backup safely; prior data intact and retry possible. |
| 16. Restart/reboot | Activity recreation, process kill, reboot; queue recoverable; physical M11 separate. |
| 17. Security | Forged IDs/cross-origin/path traversal/symlink/URI writes denied; decompression budgets; no private text logs. |
| 18. Slow device | 1,000 files/100 folders, large inputs; measure latency/RAM/ANR and impact on navigation. |
| 19. Regression | Notes/focus/nesting/media, Studio packages, Assessment pause/review, Tutor old sources, Obsidian/saved links. |
| 20. API31/API35 | Same built APK installed/tested on both; evidence source and binary hashes. |
| 21. Ubuntu/Windows | Existing canonical full validator, browser/Node/characterization/migration; exact head then merged main. |
| 22. Release/install | APK signature/version/ABI, tested==published hash; direct download verified; safe update/restore guidance. |
| 23. Backup >100 MiB | Bounded-memory round-trip, v1 import, declared unavailable-original recovery records, unexpected missing-payload rejection and interrupted swap recovery. |
| 24. Privacy | Existing opt-outs retained, no automatic cloud transmission, truthful offline capabilities. |
| 25. Templates/accessibility | Apply twice/customize/reapply; 200% text/TalkBack/back/keyboard and ≥48px targets. |
| 26. Race/stale index | Delete/disable/move/replace during extraction cannot publish stale chunks or cross-subject results. |

Proposed targets, to measure rather than claim: warm folder navigation p95 ≤500ms, metadata search p95 ≤300ms and tap feedback ≤100ms at stated synthetic scale on a low-memory Android profile. Record device/OS/WebView/data size/sample counts and peak memory. Physical M11 and real vendor viewers remain unverified if unavailable; do not label emulator tests as phone tests.

The audit's own local pytest attempt could not start because pytest/Flask were absent; local pypdf was 6.10.0 vs tracked 6.18.0. Do not interpret that as a product failure. Install/use tracked test dependencies in your implementation environment. Current native extraction relies on pypdf `apply_configuration`; preserve compatible pinning/security budgets.

## 11. Development phases

1. Refresh exact main/PRs/course truth/source manifest; create branch and baseline tests.
2. Reliable backup/export/restore compatibility and migration fixtures.
3. Additive academic hierarchy, lifecycle/source links, migration ledger.
4. Format/import/duplicate/batch/native handoff and reference-aware file actions.
5. Durable extraction queue, canonical source bridge, automatic index and Tutor citations.
6. Unified mobile screens, templates/search/Unsorted/Trash/accessibility and legacy adapters.
7. Runtime concurrency/performance/privacy/regression hardening.
8. Exact-head review/CI, merge, merged-main verification, tested APK publication.

Each phase must have behavior-based evidence. Do not stop after UI work or omit data safety to fit time. Use focused tests during development, then required broad gates. Fix underlying causes instead of suppressing failures or lowering assertions.

## 12. GitHub and Android release requirements

Read current workflow contracts before triggering publication. Canonical workflow: `.github/workflows/architecture-validation.yml`, tracked requirements plus browser setup, and `python scripts/architecture_validation.py --require-clean --output <isolated-results>`. Follow existing `scripts/architecture_checkout_eol.py` handling of known historical CRLF checkout artifacts. Do not rewrite unrelated files to satisfy cleanliness.

Android reusable workflow: `.github/workflows/verification-android.yml`, exact `source_sha`, `level: release`; inspect `scripts/android_emulator_acceptance.sh` and `scripts/android_acceptance_fixture.py`. Preserve actual app/test build and instrumentation evidence. No skipped critical new gates, no old APK substitution.

Publisher: `.github/workflows/unified-android-release.yml`. At audit it triggers on successful main canonical `workflow_run` plus merge message prefix `Release ANVAYA unified Android`, requires current exact main and builds/tests before publish. It hard-codes old version/code/tag/report in several places: update all to a consistent chosen new version and monotonically larger code. Do not merely rename a 1.3.0 binary to Library 2.0. Preserve no-overwrite release behavior, checksum/signature/BUILD metadata and downloaded-byte comparison. Current main is unprotected, so independently enforce checks before merging.

Sequence:

1. Review branch diff and data migrations; complete focused + canonical Ubuntu/Windows + installed API31/API35 tests on exact PR head.
2. Merge only after gates pass and no unresolved data-loss issue. No blind merge of unrelated draft branches.
3. Run canonical verification on actual merged-main SHA; changes introduced by merge invalidate earlier evidence if relevant.
4. Build release candidate from that verified SHA, install/test same binary on API31/API35, preserve artifact identity.
5. Publish with supported GitHub workflow after all required gates; include APK, source/tree hash, SHA256, byte size, version/code, ABI/min SDK, signing certificate, tests/limitations and migration/backup notes.
6. Download the published direct APK URL and verify bytes/checksum match the tested APK. Provide that direct link and release page.

Production signing was unavailable at audit. Inspect available supported signing, never expose keys. If only debug signing is available, publish an honestly labeled debug prerelease and record certificate compatibility. A same-package/higher-code APK is not enough for update compatibility when signing differs. Never instruct uninstall/clear-data to bypass a mismatch; preserve old app/data until backup and restore are verified. Report genuinely blocked release requirements rather than invent success.

## 13. Final deliverables

Provide the implemented feature summary, exact source/PR/merge SHAs and links, schema/migration/backup notes, actual test matrix results with run URLs, APK provenance and **verified direct APK download link**. Distinguish automated/emulator evidence from manual physical-phone/vendor-app checks. List missing sixth subject, unsupported extraction/OCR formats, signing limitations or other unresolved issues explicitly. Do not claim “complete” when a release gate is still failed or unavailable.

The expected result is a clean academic file manager where Anand can import a professor's original document into its semester/subject folder, open it in a phone viewer offline, and have Tutor use supported content automatically with accurate provenance—without manual index rebuilds, duplicated upload interfaces or loss of existing study data.
