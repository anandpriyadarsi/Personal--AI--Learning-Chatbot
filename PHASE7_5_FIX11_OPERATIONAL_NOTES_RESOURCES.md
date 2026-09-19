# Phase 7.5.11 — Operational Notes + Resources

Branch: `main`

## Delivered operations

Notes:
- list/search/filter through GET;
- create through POST + 303 redirect;
- edit by stable 1-based in-memory position through POST + 303 redirect;
- duplicate titles remain safe because edits target position rather than title.

Resources:
- list/search/filter through GET;
- add through POST + 303 redirect;
- update status through POST + 303 redirect;
- only explicit HTTP(S) links render as active anchors.

## Authority and safety

- `data/notes.json` remains the Notes authority.
- `data/resources.json` remains the Resources authority.
- Note bodies retain the exact V1 fields: `title`, `topic`, `difficulty`, `content`.
- Resource rows retain the exact V1 fields: `title`, `type`, `link`, `status`.
- No SQLite authority change, RAG re-index, Obsidian write, delete, archive, trash, or bulk mutation is introduced.
- Flask routes call `NotesResourcesWebService`; the web boundary delegates to the existing non-interactive Notes/Resources services and never calls CLI menus or repositories directly.

## Why archive/trash is deferred

The current legacy note authority has no stable persisted identity or lifecycle field. Adding archive/trash now would require inventing a second state store or altering the legacy record shape. Both would violate the approved authority direction. Archive/trash therefore remains deferred to the later Notes Studio/Obsidian modernization.

## Next phase

Phase 7.5.12 — Obsidian Workspace + Search.
