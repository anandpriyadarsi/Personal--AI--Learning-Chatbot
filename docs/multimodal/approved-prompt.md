# ANVAYA 3.0 — Multimodal Tutor Phase 1
## Ready-to-upload implementation prompt for GPT-6.1 Sol Work
**Finalization check: 13 November 2026 (Asia/Kolkata).** GitHub main was rechecked and remains `fea82a2d2d16c9ae8bec8f262da4fb6087e4f21b`; the original 12 November code audit baseline is unchanged.


You are GPT-6.1 Sol in Work mode, implementing ANVAYA's next local-web milestone in the actual GitHub repository:

**`anandpriyadarsi/Personal--AI--Learning-Chatbot`**

Read the accompanying files completely:

1. `ANVAYA_MULTIMODAL_TUTOR_ASTRA6_FEASIBILITY_AUDIT.md`
2. `ANVAYA_MULTIMODAL_TUTOR_PHASE1_IMPLEMENTATION_BLUEPRINT.md`

This is an **actual implementation and verification task**, not a request for another generic audit or planning document. Proceed through the approved scope below. Preserve existing features and independent academic data. Do not stop after explaining what you could implement.

## 1. Baseline and authorization

The audit inspected current main **`fea82a2d2d16c9ae8bec8f262da4fb6087e4f21b`**, on **12 November 2026, Asia/Kolkata**, including merged PR #74. PR #72 Tutor/Coding is also merged. Recheck actual current main and relevant merged changes before editing; compare only the relevant drift, do not redo a generic audit. API merge metadata takes precedence over stale prose in PR bodies.

Create an isolated feature branch from current main. Inspect AGENTS.md and local instructions, preserve unrelated work, and use staged reviewable commits/PRs where appropriate. Do not blindly merge historical feature branches.

Authorized scope: implement local Windows-oriented Flask web functionality, synthetic fixtures, tests, documentation and normal GitHub integration. Merge only after relevant verification gates pass and branch protections are satisfied. Destructive personal-data changes, paid/live external-provider calls, personal source transmission, public deployment and unrelated scope require separate explicit authorization. Continue all safe implementation/testing while any live-spend decision is pending.

No Android APK, emulator or native-phone validation. Mobile-width browser checks matter. Do not bind publicly or deploy remotely.

## 2. Approved product scope

Deliver the smallest complete vertical slices:

**A — image/PDF-page understanding inside existing Tutor (required).** Store/open original in Library, explicitly select source/page/image, review local/cloud processing scope, process with uncertainty and recoverable states, ask within existing Tutor, and click a citation to the exact source/version/location. Preserve digital document extraction and PPTX slide ordering. Images are not a separate chat product.

**B — authorized timestamped transcript plus selected frames (required after A).** Import bounded SRT/VTT, bind supplied frames to an explicit source/version and timestamp provenance, retrieve relevant cue intervals, explain with visible evidence limits, and navigate back to the cue/frame/original reference. This is a complete useful lecture pilot even without ASR/video decoding.

**C — local short-file ASR/video processing (optional).** Only add after A/B work and constraints are proven: authorized ≤10 minute local media, killable bounded decoding, real presentation timestamps, optional ASR and sparse frames. No arbitrary URL download. If codecs, Windows, timing, model quality, licensing or cost block C, finish A/B and mark C deferred.

Do not add custom model training, mandatory PyTorch/GPU, a new chatbot, image-embedding database, autonomous agent, Redis/Celery/distributed queue, full media archive, public cloud hosting, automatic grading/mastery/tasks/calendar writes, or bidirectional Obsidian sync.

## 3. Repository facts to use

These were verified in code; confirm symbols if main changed:

- `phase7_web.py` delegates to `personal_learning_assistant/ui/web/__main__.py`. `main()` runs loopback port 5000, debug/reloader off. `prepare_local_app()` has existing Assessment activation/restore/Library initialization effects. Never launch against personal stores merely for a test.
- `services/native_document_library.py:NativeDocumentLibrary` owns `library.sqlite3`, original immutable blobs and placements. `native_document_formats.py` already accepts raster images, but not SRT/VTT/video.
- `services/native_document_extraction.py:extract_pages` returns stored-only for JPG/PNG/WEBP; `_pdf_text` supports optional local OCR; `_slides` respects presentation relationships. Image-only slides are not understood today.
- **Reproduced audit issue:** `ingestion/extractors.py:PPTXExtractor` sorts internal slide filenames, which can disagree with actual presentation order. Share native safe ordering, with compatibility tests; do not extend the defective behavior.
- `services/native_tutor_bridge.py` already has a durable leased queue: `_claim`, `_heartbeat`, `run_pending`, `_publish_native`, `_refresh_retrieval`, `_publication_is_current`. Reuse it; it runs while the app is open, not after shutdown.
- `_publish_native` uses `KnowledgeRegistryService` and `SQLiteIngestionRepository.commit_extraction`. Native generations, metadata revisions, course scope and original hashes already matter.
- `domain/ingestion_models.py:ExtractedUnit` and `ingestion/chunking.py:prepare_chunks` support page/slide/timestamp locators. Locator JSON is encoded in `chunk_type`; preserve backward compatibility.
- `ingestion/extractors.py:TranscriptExtractor` preserves SRT/VTT milliseconds. A synthetic VTT → chunk check passed in the audit. Strengthen bounds and timing validation, then connect it to the actual web workflow.
- `youtube_ingestion.py` uses `youtube-transcript-api` and saves Markdown start-time text. It is not a compliant guaranteed caption API or video understanding subsystem. Do not make it the required new workflow.
- `vision_math_reader.py` already has optional HTTP image transcription/rendering, but is not the verified native Library/Tutor integration. Do not call its raw HTTP path unchanged: add consent, budget, structured results, output bounds and safe errors.
- `retrieval/index_builder.py:RetrievalIndexBuilder` supports disposable generations; `retrieval/hybrid.py:HybridRetriever` supports lexical/optional semantics. Native bridge uses lexical-only builds. Do not replace these.
- `services/academic_agent_web_service.py:ask` invokes `GroundedTutorService`; `tutor/grounding.py` owns evidence/prompt assembly; `tutor/source_freshness.py:source_snapshot` validates current source/native integrity. Extend these, not a second answer endpoint.
- `templates/agent_session.html` evidence chips currently open `web.knowledge_item(document_id=...)`. Exact image/time/page navigation needs a proper resolver and saved evidence snapshot. `session_view` currently enriches from current metadata; don't use it to invent historical locations.
- `services/tutor_coding_service.py` has revision-bound source/provider consent. Preserve it; shared validators are welcome, implicit permission expansion is not.
- `services/lecture_learning_service.py` manages explicit study progress. It is not an ASR worker and must not receive inferred progress writes.
- `ui/web/learning_tutor_v24.py`, `services/learning_tutor_session_v24.py`, `ui/web/learning_source_links_v24.py`, `ui/web/pao_sources.py` provide existing identity-aware handoffs. Preserve them and their data owners.
- Native schema is currently version 2; optional canonical migrations 0015–0019 exist. Choose the next free number only after inspection. New schema activation must be explicit and backup-first.

Audit evidence limits: only three isolated synthetic characterization checks ran; no full suite, browser, Windows, OCR/model quality or paid API call ran during the audit. Historical PR test counts are documentation, not your baseline pass.

## 4. Required architecture and invariants

Use the existing chain:

`original owner → selected scope/consent → leased job → versioned evidence → native bridge → canonical chunks → current retrieval/Tutor → atomic saved exchange/evidence snapshot → exact citation resolver`.

Source identity is namespaced owner + stable placement/document ID + full original SHA-256 + generation/metadata revision. Never use filename or content hash alone as scope identity. Copies can share immutable bytes but must retain independent course/permission context.

Use typed versioned locator variants: PDF page/crop, PPTX slide/asset, image/crop, transcript cue interval, video segment/frame PTS. Page/slide ordinals are 1-based; times are finite integer milliseconds; all bounds validated. For external references with no video bytes, do not invent a video content hash. Bind supplied transcript/frame hashes in an explicit versioned manifest.

Derived artifacts include extractor/model/prompt recipe revision, source version, locator, content hash, evidence kind, coverage and uncertain spans. Keep machine reading distinct from user corrections. Unclear critical math symbols must remain unknown/alternatives until clarified. No fake accuracy/confidence numbers.

Persist authoritative consent/review receipts separately from disposable extraction caches. Add only necessary tables through current owners. No new central academic database. Preserve original files byte-for-byte; never delete Library metadata as an index reset. Retain legacy text-only behavior when flags are off.

Cross-owner publication uses durable idempotent stages, not a fictional cross-SQLite transaction. Do not hold native metadata locks while waiting on academic DB writes. Validate generation/lease/permission before publication and retrieval eligibility. Rebuild indexes from authoritative records; stale/partial publication fails closed.

## 5. Privacy, provider and cost boundary

No new outbound request without explicit source/version/scope/provider/purpose consent. Local indexing permission is not permission to send derived text to a Tutor API. Separate cloud extraction and cloud answering scopes. Show selected pages/crops/frames/audio and cost upper bound before consent.

Use an expiring review token, revisioned receipt, same-origin/CSRF checks, trusted configured endpoint and server-owned source selection. Scope expansion, provider change or source change invalidates consent. Revocation cancels pending matching work and blocks future calls; never claim it recalls transmitted data.

Wrap **every** relevant provider call, including existing automatic repair/retry calls, with the budget/permission guard. Reserve cost atomically before sending and reconcile actual usage. Unknown paid outcomes after timeout must not automatically resend. API key availability is not authorization. Default budget is zero/local-only; suggested user-configured ceiling is $3/month with 100 image analyses and 60 optional ASR minutes, but this prompt grants no spending authorization.

Keep adapters swappable and capability-aware. Recheck official docs for current chosen model, supported image/timestamp output, pricing, retention and license. Audit docs found GPT-4.1 mini image input, a current `gpt-transcribe` recommendation, and deprecation of older hosted transcription models; do not copy old model IDs blindly. No promise that `store=false` means zero provider retention. Use fake providers by default.

Never expose keys/raw provider bodies in browser/logs/tests. No arbitrary provider URLs from web inputs. Reject unsafe source links, local paths and redirect tricks. No media fetch from supplied URLs, access-control bypass or restricted YouTube download. Authorized uploaded transcripts/frames and safe external timestamp links are sufficient for B.

## 6. Processing and UI behavior

Reuse durable jobs/leases/checkpoints. Add source scope/recipe/consent revisions, progress and cancellation. Distinguish stored, queued, processing, partial, ready, blocked, failed and cancelled. Reasons include missing dependency/key, consent required, budget limit, source changed, unknown provider outcome and unclear math.

Proposed defaults: retain 100 MiB original upload ceiling; 10 MiB/20 megapixel static image processing; ≤10 selected pages/job, ≤2 page images initially sent per turn; 1 MiB/2,000-cue transcript; one processing job/provider call; 120-second selected-page local deadline; bounded provider connect/read deadlines and output. Optional media ≤10 min/20 retained frames/4 cloud frame calls, bounded decode resolution. These are proposed limits to validate, not measured performance claims.

Heavy native parsing/decoding must be killable and resource bounded. Do not rely on thread cancellation alone. Handle malformed PDFs, zip/XML bombs, duplicate members, corrupt images/media, symlinks/path traversal, temporary-disk exhaustion, restart, double worker, cancellation and late response publication. Treat all extracted content as untrusted data; no execution or write authority.

Explicit selected images must work even without lexical text matches. For a chosen lecture/time, resolve temporal overlap directly before adding normal retrieval. Distinguish observed, inferred, unknown and general explanation. Source-only cannot invent outside facts; source-first labels them.

Save evidence snapshot in the same canonical transaction as the Tutor exchange. Each citation opens the exact retained source version/location or an explicit unavailable screen. Never silently substitute newer source bytes. Old chats without snapshots retain an honest legacy fallback. PPTX without a faithful render opens a supplied slide image/asset or original external-viewer fallback with the exact slide number; no unsupported exact-slide promise.

Library displays originals, not OCR dumps. Add one “Ask about this page/image” action and compact status; details contain scope, coverage, review, cancel/retry. Keep existing Tutor history and compact composer, preserve failed-question drafts, avoid overlap and horizontal page overflow. Check 320/390/768/1366px and short viewports, keyboard/focus and long matrices. No native Android work.

## 7. Execution order and gates

Follow the detailed blueprint. Recommended order:

1. **WP0:** recheck main, isolated feature branch, independent-owner inventory/backups/restore drill, synthetic fixtures, focused baseline tests.
2. **WP1:** typed identity/locators, additive migration/activation, permissions/budget, exact citation resolver and immutable evidence snapshot contracts.
3. **WP2:** selected raster/scanned-page processing, PPTX extraction consolidation, structured fake-first vision, uncertainty and bounded job recovery.
4. **WP4:** canonical publication/retrieval/Tutor integration, direct image/time selection, guarded provider calls, atomic exchange snapshots and freshness checks.
5. **WP5(A):** working browser journey for first complete slice.
6. **WP3(B), WP5(B):** transcript + frame manifest, temporal retrieval and navigation. Consider optional C only after this passes.
7. **WP6:** full relevant regression/security/browser/evaluation evidence, Windows run instructions, restore/rollback documentation and verified merge decision.

Each gate must have actual evidence. If a package fails, fix it before building dependent features. If C is infeasible, deliver independently working A/B rather than a broad untested demo.

## 8. Testing requirements

Synthetic or explicitly authorized corpus: normal 3-page RREF/LU PDF; scanned matrix page; reordered 3-slide PPTX including image-only diagram; handwritten matrix with clear/ambiguous versions; 2–3 minute authorized recording **or** timestamped transcript + 3–5 frames. No real academic files assumed available.

Create a gold manifest and 30 answerable questions + 15 negatives: minus-sign corruption, pivot-required LU, 0/O and 1/l, matrix transpose, repeated slide with different annotation, missing frame/time, cross-course duplicate, source replacement mid-answer, prompt injection and provider failure. Compare to current text-only baseline on the same cases.

Non-negotiable gates: exact source/version/location or explicit unavailable on every citation fixture; zero unauthorized outbound calls/cap bypass/automatic unknown-outcome retry; no unintended academic owner writes; no late stale publication; original hashes preserved; ambiguous critical symbols surfaced; source-only negatives abstain; relevant existing tests pass. Initial retrieval targets: recall@5 ≥90%, precision@5 ≥70%; initial live answer target ≥90% fully correct on positives and zero confident wrong critical-math claims on release set. Report denominators and limits; small synthetic sets do not prove universal accuracy.

Existing test commands to start from in a complete checkout:

```powershell
python -m pytest -q tests/test_phase5_unified_ingestion.py tests/test_native_document_library.py tests/test_library2_tutor_bridge.py tests/test_phase6_grounded_tutor_engine.py tests/test_phase6_lecture_learning_mode.py
python -m pytest -q tests/test_tutor_coding.py tests/test_learning_tutor_session_v24.py tests/test_learning_source_links_v24.py
python -m pytest -q tests/test_native_library_routes.py tests/test_native_library_browser.py tests/test_tutor_coding_browser.py
```

Add tests for multimodal contracts, permissions, job recovery, exact citations, grounding and real browser journeys; optional media tests only if C implemented. Discover relevant current PAO/Obsidian/owner-migration tests when touching shared code. No skipped boundary tests counted as passes. Use synthetic SQLite, fake providers and real Flask/Chromium, not only template string assertions.

Record actual platform/Python/dependencies/SHA, commands, pass/fail/skip counts, screenshots, latency samples and constraints. Live model quality is separate from fake-provider functional tests. If no paid test is authorized, finish offline/fake-provider validation and label live quality unverified; keep paid capability opt-in. Do not claim Windows passed from Linux tests. Manual Windows validation can be reported separately; do not spend on heavy matrices unnecessarily.

## 9. Data safety, migration and rollback

Back up every affected authoritative owner plus originals and configuration, using stopped writers or verified SQLite online backups. External Obsidian vault remains independently owned/backed up. Never overwrite current records with synthetic fixtures or silently create a new empty academic database when the configured one is absent.

Implement explicit dry-run/apply activation for new optional schema; suggested script `scripts.multimodal_migrate` is a **proposal, not an existing command**. Validate backups/checksums, repeated activation and failure rollback. New feature flags default off: proposed `ANVAYA_MULTIMODAL_ENABLED`, `ANVAYA_MULTIMODAL_MEDIA_ENABLED`.

Feature-off on the new build is the primary safe rollback. Preserve optional tables/history. Old-code downgrade must be tested against cloned upgraded stores; current native code rejects unknown schema versions. Never restore an old backup over newer study activity as routine rollback. Rebuild derived indexes separately from authoritative metadata. Do not erase consent/user corrections as cache cleanup.

## 10. CI and completion

Respect constrained GitHub Actions/storage: focused local verification, small synthetic fixtures, no model weights or full media in Git/artifacts, no Android workflow dispatch, no unrelated repeated full matrices. Keep required protections. Do not claim skipped CI ran or delete unrelated artifacts as part of this feature.

Deliver:

- Implemented features by A/B/C, with an honest completed/deferred checklist.
- Actual PR/merge links and final commit SHA, if created/merged.
- Exact verification commands/results and platform; separately list live-provider, Windows and other unverified checks.
- Source/consent/citation/queue contracts, backup/activation/rollback instructions and unresolved risks.
- Exact PowerShell setup/run commands supported by your final code. Existing launcher is `python phase7_web.py`, default `http://127.0.0.1:5000`; verify actual environment/data paths and preserve current flags.
- No guessed new script names presented as runnable; implement and verify them first. Reuse existing `.venv` or `venv`, install only needed pinned dependencies, run `pip check`, and avoid global execution-policy changes.

Finish the authorized implementation and relevant verification. If an external condition blocks one component, state the precise blocker and deliver the best independently working approved slice. Never substitute another generic audit for implementation, and never label untested multimodal educational quality as dependable.
