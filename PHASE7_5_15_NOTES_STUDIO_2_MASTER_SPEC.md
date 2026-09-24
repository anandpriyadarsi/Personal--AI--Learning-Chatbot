# Phase 7.5.15 — Notes Studio 2.0 Master Specification

Status: APPROVED DEVELOPMENT SPECIFICATION
Branch: phase7.5.15/notes-studio-rich
Baseline: main@f8590aca82b586e5e21b980f7e720040bb55b963
Product area: Notes Studio only. Tutor 2.0 is explicitly out of scope.

## Purpose
Turn ANVAYA Notes from a basic content list into a durable, visual, Obsidian-compatible academic Notes Studio. The product has two distinct experiences: a compact Notes Library of front-page cards and a full Note Reader/Editor. The front page must never dump the full note body.

## Existing-system audit
The repository already has three relevant layers:
- Phase 5.4 Notes Studio Foundation: Markdown mutation commands, UUID identity, frontmatter, SHA-256 conflict protection, atomic replacement, lifecycle operations, operation journal and note.saved outbox event.
- Phase 7.5.11 Notes + Resources: legacy data/notes.json notes with title, topic, difficulty and content.
- Phase 7.5.12+ Obsidian workspace: configured-vault browse/search/reader behavior with path, symlink and fingerprint protections.

Phase 7.5.15 MUST converge the rich-note experience on the existing Obsidian/Notes Studio architecture. It MUST NOT create a third note-body authority.

## Authority rules
1. Obsidian Markdown is authoritative for rich note bodies.
2. SQLite may own stable structured metadata, identity, lifecycle state, relationships and operational coordination where the existing architecture permits it.
3. Retrieval/search indexes are derived and rebuildable.
4. Legacy data/notes.json remains compatible until an explicit tested migration/cutover is approved.
5. Browser writes must reuse the existing Notes Studio command/service safety protocol.
6. Unknown frontmatter and user-authored Markdown must not be destructively normalized.
7. Read operations are side-effect free.

## Tutor isolation
This branch owns Notes Studio only. Do not modify Tutor reasoning, prompts, Socratic behavior, prerequisite reasoning, practice sequencing, understanding checks or tutor session state. Tutor 2.0 must not own Notes Studio templates, rendering, Markdown writes, attachment storage or lifecycle behavior. Future integration must use a narrow explicit contract such as a structured note draft or stable note identifier.

## Notes Library
The default /notes experience becomes a visual library of compact cards. Each rich card can show title/topic, course, note/template type, date, 2–5 short key points, tags, pinned/lifecycle state, visual count and related-note count when safely available, plus an Open full note action.

The card MUST NOT render the complete Markdown body. Key points are explicit metadata for deterministic rendering. Ordinary library reads must not invoke AI.

## Full Note Reader
Opening a card displays the complete note in a readable academic layout, progressively supporting headings, paragraphs, lists, math, code, tables, callouts, images, flowcharts, concept maps, worked examples, common mistakes, summaries, source references, backlinks and related notes. Rendering must not permit arbitrary HTML/script execution.

## Initial templates
1. Concept Note — Key Points, Intuition, Core Explanation, Visual, Example, Common Mistakes, Summary, Related Notes.
2. Lecture Note — date/source, topics covered, notes, diagrams, questions/doubts, takeaways.
3. Revision Note — must remember, formulas/facts, common traps, quick examples, self-test.
4. Formula Sheet — definitions, formulas, conditions, compact examples.
5. Problem-Solving Note — problem, concepts needed, approach, working, solution, mistakes, alternative method.

Templates are scaffolds, not separate storage formats. Saved notes remain Obsidian-compatible Markdown plus controlled metadata.

## Card metadata contract
Target logical fields: assistant_id, title, course, topic, note_type, note_date, card_summary (2–5 points), tags, revision_status, confidence, and lifecycle/pin state where already owned by structured storage.

Absent metadata must degrade gracefully. Unmanaged vault notes remain readable. Unsupported metadata must not hide a note. This phase must not bulk-rewrite the vault.

## Visual content model
First-class blocks:
1. Image — uploaded/imported diagrams, screenshots or figures.
2. Flowchart — algorithms, procedures, derivations and workflows.
3. Concept map/diagram — conceptual relationships.
4. Callout — Key Idea, Important, Warning, Exam Tip, Common Mistake.
5. Math — equations and derivations.
6. Comparison/table — structured comparisons.

Visuals must communicate meaning rather than decoration. Where practical, flowcharts/diagrams retain editable source representation.

## Attachments
A later unit defines a safe vault-relative attachment policy: choose/add image, store under an approved vault attachment location, insert portable reference, resolve only approved local paths, reject traversal/absolute escape/unsafe types, preserve Obsidian compatibility. No attachment writes occur in 15.1.

## Search and organization
Eventually support case-insensitive title/topic/tag/body search; course, note-type, tag, pinned and lifecycle filters; recent ordering; backlinks and related notes. Reuse existing safe vault/search infrastructure rather than creating another search authority.

## Lifecycle
Existing Notes Studio capabilities remain the base: create, update with expected-hash protection, pin, archive, trash and restore. Web exposure occurs only after read architecture and rendering are stable.

## UX principles
Library first. Progressive disclosure: card -> full reader -> editor/actions. Academic, calm and visually structured. Dark-theme compatible. Laptop friendly. Keyboard-accessible primary actions. Safe degraded states. Visual richness must not sacrifice readability or Obsidian portability.

## Development sequence
- 7.5.15.1 Canonical Read Model + Card Architecture: audit current note paths, typed card/detail models, side-effect-free Obsidian-backed read composition, legacy compatibility and authority tests.
- 7.5.15.2 Visual Notes Library: compact cards, filters and responsive layout.
- 7.5.15.3 Full Note Reader: safe structured Markdown reader and academic layout.
- 7.5.15.4 Templates: registry and five academic templates.
- 7.5.15.5 Rich Visual Blocks: images, flowcharts, diagrams, callouts, math and tables.
- 7.5.15.6 Safe Editor + Attachments: controlled create/update through existing write protocol, template selection, attachments and conflict UX.
- 7.5.15.7 Knowledge Connections: backlinks, related notes and course/topic/source relationships.
- 7.5.15.8 Lifecycle + Study Actions: pin/archive/trash/restore and bounded note-level study actions, with no Tutor 2.0 implementation.
- 7.5.15.9 Reconciliation + Final Gate: compatibility/cutover decision, regression coverage, migration evidence if separately approved, docs and final gate.

Each unit must be green before the next begins.

## Non-goals
No Tutor 2.0 implementation; no proprietary duplicate note database; no duplicate authoritative body in SQLite; no silent legacy JSON migration/deletion; no bulk vault rewrite; no RAG rebuild on ordinary reads; no generative AI during ordinary card rendering; no arbitrary HTML/JavaScript; no cloud sync; no collaborative editing; no implied permanent delete.

## Cross-unit safety invariants
Preserve vault integrity unless an authorized write unit owns the change; SQLite integrity/FKs; legacy JSON until migration approval; retrieval-index integrity; path/symlink protections; expected-hash conflict protection; lazy Flask startup; no hidden network dependency for local browsing; all completed-phase regressions.

## Completion definition
Complete only when the user can scan attractive front cards showing topic/title, date and concise key points; click through to full notes; use five templates; include safe images and visual blocks; create/edit through Notes Studio safety; navigate backlinks/related notes; use lifecycle actions; retain Obsidian portability; preserve legacy compatibility according to the final reconciliation decision; and pass the complete gate.

## Approval boundary
This specification authorizes staged development only. It does not authorize skipping gates, modifying Tutor 2.0, bulk-migrating user data or merging into main before final integration.
