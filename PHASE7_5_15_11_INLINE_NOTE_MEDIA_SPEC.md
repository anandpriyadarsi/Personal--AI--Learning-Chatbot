# Phase 7.5.15.11 — Inline Note Media + ZIP Import

Status: APPROVED CORRECTIVE FEATURE SPEC
Branch: `phase7.5.15.11/inline-note-media`
Base: `phase7.5.15.10/notes-obsidian-separation`

## Purpose

Extend independent ANVAYA personal Notes so one typed note can contain multiple images placed between paragraphs instead of showing every image only at the end.

The user must also be able to import a ZIP containing note images/PDFs and control image presentation without destructively modifying the original uploaded bytes.

## Product behavior

### Multiple media per note

A typed or handwritten note may contain multiple uploaded files.

Supported direct uploads:

- PDF
- PNG
- JPG / JPEG
- ZIP

A ZIP is treated as a batch import container. ANVAYA extracts only supported PDF/JPG/JPEG/PNG entries and rejects unsafe archive paths, encrypted entries, nested ZIPs, oversized entries and excessive expansion.

### Inline image placement

Typed notes support inline image blocks inside the note body.

An image can be inserted at the current text cursor. The rendered image appears exactly between the surrounding paragraphs/sections rather than being duplicated at the bottom.

Images that are used inline are omitted from the generic attachment section. Non-inline files remain available as attachments.

### Non-destructive image presentation

The original uploaded image bytes remain unchanged.

Each inline image block may store presentation metadata:

- width: 25%, 40%, 55%, 70%, 85%, 100%
- rotation: 0°, 90°, 180°, 270°
- crop/aspect mode:
  - original
  - square (1:1)
  - 4:3
  - 3:4
  - 16:9
- optional caption

Cropping is presentation-only. It changes the rendered viewport using CSS/object-fit and never rewrites the source pixels.

### Editor UX

The typed-note editor contains a Media section.

For newly selected files:

- each selected image has an Insert at cursor control;
- size, rotation, crop and caption are selectable before insertion;
- a ZIP has an Insert ZIP images here control which expands all safe image entries at that location after save.

For an existing note:

- existing image assets are shown in the media tray;
- each may be inserted again at the cursor with new presentation settings;
- existing inline blocks remain editable as text directives so their width/rotation/crop values can be adjusted later.

This phase does not require a full WYSIWYG canvas or destructive pixel editor.

### Inline syntax

The persisted typed-note body uses deterministic local-only directives:

`[[anvaya-image:<asset_id>|width=70|rotate=90|crop=4:3|caption=Example]]`

New unsaved uploads temporarily use:

`[[anvaya-upload:<selection_index>|width=70|rotate=0|crop=original|caption=Example]]`

Before persistence, upload directives are resolved to real asset IDs. ZIP upload directives expand into one inline image directive per safe image extracted from that archive.

The reader never trusts arbitrary IDs or CSS values. It validates that the image belongs to the current note and clamps presentation options to the approved set.

## Security

ZIP import must:

- cap archive input size;
- cap expanded file count;
- cap each expanded entry size;
- cap total expanded bytes;
- reject absolute paths;
- reject `..` path traversal;
- reject encrypted entries;
- reject nested archives;
- ignore directory entries;
- reject unsupported file types;
- validate file signatures after extraction.

No archive entry is written using its archive path.

## Authority

This phase stays inside independent ANVAYA Notes:

- `data/anvaya_notes.json`
- `data/anvaya_notes_assets/`

No Obsidian write/read authority is introduced.
No Tutor code is modified.
No SQLite migration is introduced.

## Acceptance

Phase 7.5.15.11 passes only if:

1. one note accepts multiple images;
2. ZIP batch import safely expands supported note files;
3. typed notes can place images between text blocks;
4. inline images are not duplicated in the bottom attachment list;
5. width settings render safely;
6. 90/180/270-degree rotation renders safely;
7. original/square/4:3/3:4/16:9 crop modes render safely;
8. original image bytes remain unchanged;
9. unsafe ZIPs fail closed;
10. the editor exposes media placement controls;
11. existing image assets can be reinserted into edited notes;
12. handwritten notes continue to support multiple pages;
13. Obsidian remains separate;
14. Tutor remains untouched;
15. full project regression remains green.
