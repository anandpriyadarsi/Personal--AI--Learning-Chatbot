# Phase 7.5.15.13 — Card Polish + Media Deletion

Status: APPROVED FEATURE SPEC  
Branch: `phase7.5.15.13/card-polish-media-delete`  
Base: `phase7.5.15.12/card-template-gallery`

## Purpose

Polish the visual Notes experience after manual review.

This phase addresses three concrete issues:

1. IRIS template previews must show the correct subject code rather than MA103N on every card.
2. Preview Card templates need substantially stronger visual differentiation and theme quality.
3. Notes media must support safe deletion, including duplicate uploads, while the reader footer shows only files that are not placed inline.

## IRIS template preview codes

The six IRIS templates use these preview labels:

- Indigo Matrix — MA103N
- Emerald Lab — CY100N
- Cyan Data — UC100N
- Amber Heritage — UC103N
- Coral Sketch — DE100N
- Violet Code — no course code

These are preview labels only. A saved note card continues to show the note's own course field.

## Preview Card redesign

Keep the existing six template IDs for compatibility, but redesign their visual language:

- preview-left — Lecture Split
- preview-top — Notebook Hero
- preview-split — Diagram Focus
- preview-film — Study Strip
- preview-polaroid — Paper Snapshot
- preview-banner — Glass Banner

Each must have:
- a distinct accent colour;
- a distinct composition;
- stronger media framing;
- clearer hierarchy;
- a coherent shared Preview family identity.

## Media deletion

### Newly selected, unsaved files

The editor must allow removing an individual selected file before save.

When a selected file is removed:
- it is removed from the browser FileList;
- any temporary inline directive pointing to that upload index is removed;
- remaining upload indices are renumbered so no directive points at the wrong file.

### Existing saved files

The editor must show a Delete file control for every existing asset, including PDF and image assets.

Deletion is staged until Save changes.

When deleting a saved image:
- all inline directives referencing that asset are removed from the typed body;
- the asset metadata is removed from the note;
- the stored source file is removed safely;
- unrelated assets are untouched.

Deletion uses the note's existing optimistic updated_at check.

## Reader footer

For typed notes:
- images used inline never appear again in the bottom attachment section;
- PDFs or images not referenced inline remain visible in the bottom attachment section.

For handwritten notes:
- all original pages/files continue to appear in the reader.

## Safety

No Obsidian authority changes.
No Tutor changes.
No SQLite migration.
No destructive image transformations.

## Acceptance

1. IRIS preview course codes are correct.
2. Violet Code has no preview course code.
3. All six Preview templates are visually distinct.
4. New unsaved files can be removed individually before save.
5. Existing saved files can be staged for deletion.
6. Deleting an inline image removes its body directive.
7. Repository deletion is optimistic and rollback-safe.
8. Deleted asset bytes are removed from the note asset directory.
9. Inline images are never duplicated in the reader footer.
10. Non-inline attachments remain in the reader footer.
11. Existing 15.10–15.12 behavior remains green.
12. Full project regression remains green.
