# Phase 7.5.15.10 — Notes / Obsidian Separation + Card Redesign

Status: CORRECTIVE DESIGN SPEC
Branch: `phase7.5.15.10/notes-obsidian-separation`

## Why this phase exists

Phase 7.5.15 incorrectly made the Notes experience a second view over the Obsidian vault.

That is not the intended product.

The corrected product model is:

- **Notes** = ANVAYA's own personal notes library for handwritten uploads and typed notes.
- **Obsidian** = a separate external Markdown workspace.
- A note must not appear in both places merely because it exists in Obsidian.
- The Notes Library must not scan the Obsidian vault for its cards.

## Product model

### Notes

Notes is an independent first-class store for the student's own study notes.

It supports:

1. handwritten note upload:
   - PDF
   - JPG / JPEG
   - PNG
   - optional multiple page images

2. typed notes:
   - headings
   - paragraphs
   - lists
   - equations
   - images
   - tables
   - diagrams / flowcharts
   - callouts

3. card metadata:
   - topic/title
   - 2–5 key points
   - optional course
   - created_at automatically saved
   - updated_at automatically saved
   - note kind: handwritten / typed
   - optional thumbnail / first-page preview

4. card interaction:
   - the entire square/rectangular card is clickable
   - clicking opens the full note
   - edit action is inside the full-note page, not the card

### Obsidian

Obsidian remains the existing vault browser/reader.

Rules:

- Obsidian Markdown does not populate `/notes`.
- Notes uploads do not get written into the Obsidian vault.
- The Notes page does not contain an "Open Obsidian workspace" dependency.
- Obsidian retains its own search, reader, backlinks and Companion behavior.
- No automatic synchronization between Notes and Obsidian is introduced.

A future explicit "Send/Copy to Obsidian" action may be designed separately, but it is not part of this correction.

## Authority

### Notes authority

Notes are separate entities from Obsidian notes.

Recommended authority:

- SQLite: note identity and metadata
- app-managed note body/storage:
  - typed note body stored under Notes authority
  - uploaded source files preserved under an app-managed notes asset directory
- attached files remain under the Notes note id

The Notes authority must not be the Obsidian vault.

### Obsidian authority

Configured vault Markdown remains authoritative only for the Obsidian product area.

## Notes card design

The default design follows the visual pattern of the IRIS NITK app supplied by the user:

- compact rounded rectangle
- two-column desktop/tablet grid
- responsive single/two-column mobile layout
- dark-theme friendly
- large topic/title
- small optional type/thumbnail marker
- up to 3 visible key points
- automatically recorded date and time at the bottom
- entire card is one click target
- no body text dump
- no "Open note" button required

Example:

~~~
┌─────────────────────────────┐
│ LU FACTORIZATION       ◫    │
│                             │
│ • Elimination multipliers   │
│ • Construction of L and U   │
│ • Verify LU = A             │
│                             │
│ 25 Sep 2026 · 3:28 PM       │
└─────────────────────────────┘
~~~

## Visual card templates

"Template" in the main Notes UI means **card appearance**, not an Obsidian/Markdown academic scaffold.

Initial visual templates:

### 1. IRIS Academic — DEFAULT

- rounded rectangular card
- strong title
- 2–3 key points
- small type icon
- date + time footer
- minimal decoration

### 2. Preview Card

- rectangular card
- uploaded handwritten first-page thumbnail on top/side
- title and 1–2 key points below
- date + time footer

### 3. Minimal Square

- nearly square card
- title centered/top
- compact key points
- clean metadata footer

The first implementation should use **IRIS Academic** as the default.

The user may later choose a different visual template per note.

## Creation flow

### New note

A single "+" / "New Note" action opens:

1. **Upload handwritten note**
2. **Create typed note**

Then ask only for useful metadata:

- Topic / Note name — required
- Key points — optional, up to 5
- Course — optional
- Card style — optional, defaults to IRIS Academic

Do not ask the user to enter created date/time.

The system records creation timestamp automatically.

### Handwritten upload

- accept PDF/JPG/JPEG/PNG
- preserve original upload
- create a first-page/first-image preview when safely possible
- full-note page renders the document/images
- no OCR is required for the base phase
- optional typed key points remain editable metadata

### Typed note

- provide an internal Notes editor
- save inside Notes authority, not Obsidian
- support rich study content and attachments
- full-note page renders the typed note

## Full-note page

Clicking a card opens one full-note page that shows:

- title
- created date/time
- updated date/time
- course if present
- key points
- full handwritten document OR typed body
- images/diagrams/flowcharts
- edit metadata/content
- archive/trash where appropriate

The reader must not redirect to the Obsidian reader.

## Existing Phase 7.5.15 behavior to correct

The following current assumptions are explicitly superseded:

- Notes Library scanning the Obsidian vault
- Notes editor saying Markdown must remain in Obsidian
- Notes cards being generated from Obsidian frontmatter
- Notes lifecycle identity depending on Obsidian `assistant_id`
- "Browse templates" meaning Markdown academic scaffolds as the primary Notes template concept
- "Open Obsidian workspace" as a Notes Library action
- duplicate visibility of the same Obsidian note in both Notes and Obsidian

## Reuse allowed

Safe reusable components from Phase 7.5.15 may be retained where they do not depend on Obsidian authority:

- card styling concepts
- typed-note visual rendering
- safe attachment validation
- lifecycle patterns
- rich visual blocks
- responsive layout
- safe HTML escaping

Do not reuse the Obsidian scanner/read service as Notes authority.

## Data migration / compatibility

Do not delete existing Obsidian files.

Do not automatically copy Obsidian notes into the new Notes store.

The previous Phase 7.5.15 Obsidian-backed Notes view should be treated as an implementation mistake, not as user Notes data requiring duplication.

Legacy `data/notes.json` records should be audited separately before any migration into the new Notes store.

## Tutor isolation

This corrective phase must not modify Tutor 2.3 reasoning, session state, prompts, practice logic, prerequisite logic, understanding checks, or live-validation evidence.

Development should remain on this dedicated correction branch while Tutor live validation continues separately.

## Acceptance criteria

Phase 7.5.15.10 is green only if:

1. `/notes` lists only independent ANVAYA Notes records.
2. `/obsidian` continues to list only Obsidian vault notes.
3. An Obsidian note does not automatically appear in Notes.
4. A newly uploaded Notes document does not appear in Obsidian.
5. A typed Notes note is stored outside the Obsidian vault.
6. handwritten PDF/image upload works.
7. cards show title/topic, key points and automatic date/time.
8. cards are compact square/rectangular click targets inspired by IRIS.
9. clicking a card opens the full Notes reader.
10. the default card style is IRIS Academic.
11. creation does not ask the user to type date/time.
12. no automatic Obsidian synchronization is introduced.
13. current Obsidian regressions stay green.
14. current Tutor code is untouched.
15. full project regression remains green.
