# Phase 7.5.15.12 — Notes Card Template Gallery Implementation Report

Status: PASS  
Branch: `phase7.5.15.12/card-template-gallery`

## Delivered

ANVAYA Notes now uses a two-level visual card selector:

1. choose a family;
2. choose one of six templates inside that family.

The three families are:

- IRIS Card
- Preview Card
- Minimal Square

Each family exposes six selectable templates, for a total of 18 designs.

### IRIS Card

The IRIS family keeps one academic visual language while offering six subject-friendly identities:

- Indigo Matrix — Math / Linear Algebra
- Emerald Lab — Engineering Chemistry
- Cyan Data — Data Science / AI
- Amber Heritage — Indian Knowledge System
- Coral Sketch — Design Thinking
- Violet Code — CSE / General

### Preview Card

Six image-first compositions are available:

- Left Preview
- Top Preview
- Balanced Split
- Film Strip
- Polaroid
- Banner

### Minimal Square

Six compact layouts are available:

- Clean
- Outline
- Centered
- Corner Accent
- Grid
- Soft Tile

## Persistence and compatibility

The exact selected template is stored per note.

Legacy values remain compatible:

- `iris`
- `preview`
- `square`

They are preserved in storage for older callers/tests and mapped to the new default visual templates at render time.

## Validation

User-executed strict gate result on 2026-09-26:

- focused card-template gallery tests: PASS
- Notes/Obsidian separation regressions: PASS
- inline-media regressions: PASS
- existing Notes UI regressions: PASS
- complete pytest suite: **1436 passed, 6 skipped, 1 deselected**
- compile/dependency consistency: PASS
- `pip check`: **No broken requirements found**
- card-template scope and repository hygiene: PASS

Final banner:

`PHASE 7.5.15.12 NOTES CARD TEMPLATE GALLERY: PASS`

## Next step

Before merging, visually validate all three card families in the running ANVAYA UI, especially the six IRIS subject identities. This is a product-design check rather than a code-correctness check.
