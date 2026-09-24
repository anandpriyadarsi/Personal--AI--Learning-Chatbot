# Phase 7.5.15.1 — Pre-Edit Repository Audit

Branch: phase7.5.15/notes-studio-rich
Audit point: 1f40ca95da6d241a4e250275d253531c05ff19de
Parent plan: PHASE7_5_15_1_CANONICAL_READ_MODEL_PLAN.md

## Result

AUDIT PASS — implementation may proceed within the bounded 15.1 scope.

No repository contradiction was found that requires changing the master authority model. No schema migration is required for the 15.1 read-model foundation. Tutor 2.0 code does not need to be touched.

## 1. Current /notes path

The operational /notes page is still a legacy-JSON web surface.

Flow:
routes.py -> NotesResourcesWebService -> NotesService -> LegacyJsonNoteRepository -> data/notes.json.

Current legacy fields remain title, topic, difficulty and content. The web service preserves 1-based positions for duplicate-title-safe editing. The current notes.html template renders the complete content directly in each library card and includes create/edit forms.

Implication: this is not the correct rich-note authority. 15.1 must not extend its JSON record shape with rich metadata. It should remain a compatibility source until a later explicit cutover/reconciliation unit.

## 2. Current Obsidian browse/search path

The rich Markdown read path already exists:

routes.py /obsidian -> ObsidianWorkspaceService -> ObsidianWorkspaceReader -> ObsidianVaultScanner -> configured vault Markdown.

The scanner already derives title, tags, note_type, revision_status, confidence, assistant_id, source hash, mtime, links and normalized path identity from Markdown/frontmatter without writing the vault.

The workspace browse row currently exposes relative_path, title, tags, note_type, revision_status and source_hash. Search is case-insensitive through casefold and searches title, path, tags and body.

Implication: 15.1 should compose/reuse this scan/read path rather than introduce another Markdown scanner.

## 3. Current safe note-detail path

The safe file reader is ObsidianWorkspaceReader.read_note(). It:
- normalizes vault-relative paths;
- rejects absolute paths and traversal;
- accepts Markdown only;
- rejects symlink components;
- resolves the target inside the configured vault;
- verifies file stability across stat/read/stat;
- computes SHA-256;
- optionally verifies the expected scan hash;
- requires UTF-8.

The browser reader is /obsidian/note. Current reader composition already renders safe Markdown and supplies backlinks/wikilinks. The Markdown renderer uses Mistune with escaping enabled and table support; leading frontmatter is hidden in reading mode while remaining visible in source mode.

Implication: NoteDetail must reuse this protection chain and must not open Markdown directly from routes or a new ad-hoc filesystem helper.

## 4. Existing Notes Studio write foundation

Phase 5.4 remains the correct mutation foundation.

NotesStudioService uses AtomicMarkdownNoteStore plus SQLiteNotesStudioRepository and OperationCoordinationService. It already provides create, update, pin, archive, trash and restore.

Create/update generate controlled frontmatter containing assistant_id, title, note_type, revision_status, optional confidence and tags. File-changing operations use operation coordination and note.saved events. Update verifies the expected hash before writing.

SQLiteNotesStudioRepository stores note identity, path, title, note_type, confidence, revision status, lifecycle timestamps, source hash and tags.

Important limitation for 15.1: existing NoteStudioView has no course, topic, note_date or card_summary fields.

Ruling: do NOT add those fields to SQLite in 15.1. Read richer optional fields from Markdown frontmatter into the new read model first. A later write/template unit can decide how controlled metadata should be persisted after compatibility behavior is proven.

## 5. Link graph and backlinks

Two mechanisms exist.

Phase 5.3 SQLiteObsidianVaultRepository has note_links and get_backlinks(), but that graph is registry-derived and is not automatically refreshed by ordinary browser reads.

The current live Obsidian workspace also computes link context from the current vault scan and safe reads. Phase 7.5.12.3 already exposes wikilinks/backlinks in the live reader.

Ruling: 15.1 may expose live relationship information only through existing read-safe workspace behavior. It must not call registry apply/refresh on GET and must not treat stale SQLite link graph state as fresher than the live vault.

## 6. Knowledge Reader

KnowledgeReaderService is a separate source-reader/study-memory path over indexed knowledge documents in SQLite. It provides source content and study interactions but is not the authority for Obsidian note bodies.

Ruling: do not make Notes Studio depend on KnowledgeReaderService in 15.1. Reusable study-memory concepts can be integrated later through explicit contracts.

## 7. Existing study companion

The Obsidian Reader already has reading history, user-authored key points and doubts. These are study-interaction data, not Markdown card metadata.

Ruling: do not silently reuse Companion key points as card_summary in 15.1. card_summary means author-controlled note metadata. Companion key points remain a separate study-memory concept unless a later product decision explicitly bridges them.

## 8. UI audit

notes.html is legacy operational UI and currently violates the desired future card behavior by rendering the whole content in every card.

obsidian.html already provides a safe live vault browser with title/path/tags/type/status and Open note.

obsidian_note.html already provides a full rendered note, backlinks, source view and study companion.

Therefore the safest product convergence is:
- create a new Notes Studio read model by composing existing Obsidian scan/read capabilities;
- keep the current legacy Notes service available as compatibility;
- in 15.2 make /notes consume the canonical card model;
- in 15.3 converge the full Notes Studio reader on the existing safe Obsidian reader capabilities.

15.1 should not perform the polished template/CSS redesign.

## 9. Identity ruling

Managed notes already have assistant_id UUID identity. Unmanaged Markdown may not.

For 15.1:
- managed identity: assistant_id when valid;
- unmanaged navigation identity: normalized vault-relative path plus current source hash where freshness is required;
- legacy JSON compatibility identity: explicit legacy source kind plus stable current position only within the compatibility adapter.

Do not invent/write UUIDs into unmanaged notes during reads. Duplicate titles therefore remain safe because navigation is not title-based.

## 10. Card metadata ruling

15.1 should introduce read-only logical NoteCard/NoteDetail models without a migration.

Recommended optional frontmatter keys for read recognition:
- title (already supported)
- topic
- course
- note_type (already supported)
- note_date, with date as a compatibility alias if deliberately documented
- card_summary
- tags (already supported)
- assistant_id (already supported)

The existing scanner's simple frontmatter parser does not currently expose arbitrary metadata in its VaultNoteFingerprint read row. 15.1 therefore needs a bounded metadata parser/composer at the Notes Studio read boundary or a safe extension of scanner output. It must not introduce a general YAML dependency merely for these fields.

card_summary rules:
- accept an explicit frontmatter list;
- trim blank entries;
- cap displayed items at 5;
- require at least 2 only for newly created future templates, not for old notes;
- no AI generation;
- if absent, return an empty tuple in 15.1 rather than mislabel a body excerpt as authored key points.

## 11. Date ruling

Precedence for 15.1:
1. explicit note_date metadata;
2. documented date alias if supported by tests;
3. no semantic note date.

Do not use filesystem mtime as if it were the authored note date. A UI may later show updated_at/file modification separately, clearly labeled.

This avoids silently changing the meaning of the requested Date field.

## 12. Read-purity boundary

15.1 reads must not mutate:
- configured vault Markdown;
- data/learning_assistant.db;
- data/*.json including notes.json and obsidian_config.json;
- .phase5_retrieval;
- authority-control files;
- registry/link graph;
- outbox/events.

No GET may call NotesStudioService mutation methods, ObsidianVaultRegistryService.apply(), indexing/rebuild operations or Companion write methods.

## 13. Required implementation shape

Recommended new files:
- personal_learning_assistant/domain/notes_studio_read_models.py
- personal_learning_assistant/services/notes_studio_read_service.py
- tests/test_phase7_5_15_1_notes_studio_read_model.py
- phase7_5_15_1_gate.ps1
- PHASE7_5_15_1_IMPLEMENTATION_REPORT.md after the implementation is green

Minimal existing-file changes are permitted only where required to expose/inject the new read service. Avoid changing notes.html styling in 15.1.

The read service should compose ObsidianWorkspaceService/Reader behavior instead of importing Tutor, KnowledgeReader, legacy CLI code or direct repository writes.

## 14. Legacy compatibility decision

For 15.1, keep legacy /notes create/edit behavior intact. Build the new canonical rich-note read boundary alongside it and test it independently.

Do not redirect /notes to the new cards yet; that belongs to 15.2.

This gives 15.1 a low-risk architecture seam and prevents a half-completed UI cutover.

## 15. Existing regression/gate dependencies

Relevant focused suites:
- tests/test_phase5_notes_studio_foundation.py
- tests/test_phase7_5_notes_resources.py
- tests/test_phase7_5_operational_notes_resources.py
- tests/test_phase7_5_obsidian_workspace.py
- tests/test_phase7_5_obsidian_markdown_renderer.py
- tests/test_phase7_5_obsidian_reader_routes.py
- tests/test_phase7_5_obsidian_study_companion.py
- tests/test_phase7_5_obsidian_study_repository.py
- tests/test_phase7_5_12_2_recovery.py
- tests/test_phase7_5_12_2_web.py
- tests/test_phase7_5_12_3_live_ux_fix.py

Relevant historical gate patterns:
- phase5_fix4_gate.ps1 protects production SQLite, authority data, legacy JSON and real vault Markdown.
- phase7_5_fix11_gate.ps1 protects Tutor/retrieval/other backend boundaries and legacy operational Notes.
- phase7_5_fix12_gate.ps1 and later gates protect Obsidian configuration, retrieval state and vault Markdown.
- phase7_5_fix12_3_live_ux_gate.ps1 hashes data, retrieval state and configured vault Markdown around regressions.

The new 15.1 gate should combine these protections while expecting branch phase7.5.15/notes-studio-rich and the committed 15.1 planning/audit baseline.

## 16. Tutor overlap audit

personal_learning_assistant/tutor is a distinct tree and is not required for the proposed read-model implementation.

15.1 allowed diff must explicitly exclude:
- personal_learning_assistant/tutor/**
- tutor-specific services/tests
- Tutor templates/prompts/session logic.

If implementation discovers a required shared-file collision with the parallel Tutor branch, stop rather than edit across ownership.

## 17. Migration decision

No SQLite migration is justified for 15.1.

Reason:
- required rich fields can initially be optional read metadata;
- existing SQLite already contains managed identity/lifecycle metadata;
- adding storage before read semantics are proven would unnecessarily expand the authority surface.

Any future schema change must belong to a later explicitly approved unit.

## 18. Stop-condition review

No stop condition is currently triggered:
- authority assumptions match current code;
- unmanaged notes can use path identity without write adoption;
- legacy compatibility can remain intact;
- security protections can be reused;
- Tutor code need not change;
- no destructive migration is required.

## 19. Implementation authorization boundary

The next implementation may add the typed read models, canonical read service, focused tests and strict gate only. It may minimally extend existing read-only metadata extraction if required.

It must NOT yet:
- redesign /notes;
- change legacy note writes;
- add templates;
- upload images;
- add editor writes;
- add lifecycle UI;
- modify Tutor 2.0;
- migrate production data.

Conclusion: Phase 7.5.15.1 is architecturally feasible as a read-only additive seam. Proceed test-first and require the strict gate before the implementation commit.
