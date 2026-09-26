# Phase 7.5.15.14 — Focus Mode + Notes Companion + Analysis Hub

Status: APPROVED FEATURE SPEC  
Branch: `phase7.5.15.14/focus-companion-analysis`  
Base: `phase7.5.15.13/card-polish-media-delete`

## Purpose

Improve reading space and move supporting study tools out of the main content area.

## 1. Collapsible navigation

The left ANVAYA navigation must be collapsible on desktop.

- the existing top-left navigation button is visible on desktop;
- one click slides the sidebar completely left;
- the main content expands to the available width;
- the preference is remembered locally in the browser;
- mobile keeps the existing overlay navigation behavior;
- no page loses keyboard navigation or Escape handling.

## 2. Notes Study Tools drawer

Independent ANVAYA Notes receive the same two study-capture ideas already useful in the Obsidian Companion:

- Saved notes
- Doubts

They remain independent from Obsidian data.

The Note reader itself stays full width. A small movable floating Study Tools launcher opens a compact overlay drawer instead of permanently occupying roughly one quarter of the screen.

The launcher:
- is draggable inside the viewport;
- remembers its position locally;
- opens/closes the drawer;
- never changes note content width while closed.

The drawer:
- slides in over the page;
- is narrow and responsive;
- shows active saved notes and doubts;
- supports adding and archiving entries;
- uses optimistic note updated_at protection.

## 3. Dedicated Analysis Hub

Detailed analysis must not be permanently shown on Home.

Home keeps operational information and exposes a clear **Check your analysis** action.

`/analysis` becomes the dedicated read-only Analysis Hub.

It combines existing academic brief evidence with independent Notes statistics and visualizes:

- urgent deadlines;
- scheduled study minutes;
- priority topics;
- course risk signals;
- study-time allocation by course;
- typed vs handwritten Notes;
- Notes by course;
- saved-note and doubt counts;
- media/attachment usage.

Visualizations are local HTML/CSS/SVG only. No external chart service or network dependency is introduced.

## Authority

- Notes Companion data stays inside independent `data/anvaya_notes.json`.
- Obsidian Companion remains separate.
- Analysis is derived read-only from existing academic dashboard data and personal Notes metadata.
- Tutor code is untouched.
- No SQLite migration is introduced.

## Acceptance

1. Desktop sidebar can slide fully left and restore.
2. Collapsed navigation allows full-width content.
3. Mobile navigation behavior remains intact.
4. Notes reader has a compact draggable Study Tools launcher.
5. Study Tools contains Saved notes and Doubts.
6. Entries can be added and archived with conflict protection.
7. Notes Companion does not read/write Obsidian.
8. Detailed priority/risk analysis is removed from Home.
9. Home exposes Check your analysis.
10. Dedicated Analysis page renders detailed visualizations.
11. Analysis uses existing evidence only and performs no writes.
12. Notes analysis includes note types, courses, saved notes, doubts and media.
13. Full project regressions remain green.
