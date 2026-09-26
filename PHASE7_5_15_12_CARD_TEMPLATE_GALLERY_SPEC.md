# Phase 7.5.15.12 — Notes Card Template Gallery

Status: APPROVED FEATURE SPEC  
Branch: `phase7.5.15.12/card-template-gallery`  
Base: `phase7.5.15.11/inline-note-media`

## Purpose

Replace the old three-option card-style picker with a two-level gallery:

1. choose a card family;
2. choose one of six distinct templates inside that family.

Each note keeps its own selected template.

## Card families

### IRIS Card

Academic, course-first cards inspired by the compact IRIS NITK dashboard language.

Six templates:

1. `iris-indigo` — Linear Algebra / Mathematics
2. `iris-emerald` — Engineering Chemistry
3. `iris-cyan` — Data Science / AI
4. `iris-amber` — Indian Knowledge System
5. `iris-coral` — Design Thinking
6. `iris-violet` — CSE / General

All IRIS templates share the same academic information hierarchy but have different accent colour, motif and edge treatment so the user can visually assign one subject to one card design.

### Preview Card

Media-forward cards for handwritten notes and notes with diagrams/images.

Six templates:

1. `preview-left` — thumbnail left
2. `preview-top` — thumbnail top
3. `preview-split` — balanced half split
4. `preview-film` — wide media strip
5. `preview-polaroid` — framed image treatment
6. `preview-banner` — banner image treatment

### Minimal Square Card

Compact low-noise square cards.

Six templates:

1. `square-clean`
2. `square-outline`
3. `square-centered`
4. `square-corner`
5. `square-grid`
6. `square-soft`

## Picker interaction

The editor and handwritten-upload form show three family buttons:

- IRIS Card
- Preview Card
- Minimal Square Card

Clicking a family reveals exactly six visual template previews belonging to that family.

Clicking a template:

- selects its radio input;
- visibly marks it as selected;
- persists that exact template id in the note;
- uses that template for the note card in My Notes.

Changing family does not silently save anything until the note form is submitted.

## Compatibility

Existing notes using old values continue to work:

- `iris` maps to `iris-indigo`
- `preview` maps to `preview-left`
- `square` maps to `square-clean`

No migration is required.

## Acceptance

1. Three top-level card families remain visible.
2. Each family contains six selectable templates.
3. Only the selected family's six templates are shown at one time.
4. Each template is visually distinct.
5. All six IRIS templates use clearly different subject-friendly colour treatments.
6. The exact selected template persists per note.
7. Old card-style values remain compatible.
8. Library cards render the selected family/template correctly.
9. Card selection works for typed and handwritten notes.
10. Full project regressions remain green.
11. Tutor and Obsidian authority remain untouched.
