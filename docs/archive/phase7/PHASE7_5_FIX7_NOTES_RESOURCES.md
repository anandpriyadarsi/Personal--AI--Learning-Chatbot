# Phase 7.5.7 — Notes & Resources

## Objective

Expose the existing Notes and Resources subsystems through the local Flask UI without introducing browser writes, changing persistence authority, or coupling the web application to RAG/ingestion.

Base commit: `22da7ccc1661d0d8e81c4856a43b1fbfab642b9f`

## Scope

Phase 7.5.7 adds two GET-only pages:

- `/notes` — existing note title, topic, difficulty, and content.
- `/resources` — existing resource title, type, status, and stored link/path text.

The sidebar Notes and Resources entries become active navigation links.

## Read boundaries

Notes are read through `NotesService.list_notes()` backed by the existing `LegacyJsonNoteRepository`. Resources are read through `ResourceService.list_resources()` backed by the existing `LegacyJsonResourceRepository`.

The dashboard adapter imports those subsystems lazily only after `/notes` or `/resources` is requested. Web-app creation does not eagerly import legacy Notes/Resources modules.

## Safety constraints

- no note/resource create, edit, delete, or status-update browser operation;
- no POST route for `/notes` or `/resources`;
- no SQLite migration or authority change;
- no direct JSON write from the web layer;
- no RAG indexing, crawling, downloading, or ingestion;
- HTTP(S) stored links may be active browser links; other stored values remain visible as plain text rather than executable links;
- read failures render safe degraded states without exception contents;
- production SQLite, authority control, legacy JSON, and retrieval-index files must remain byte-for-byte unchanged by the gate.

## Gate

`phase7_5_fix7_gate.ps1` verifies focused Phase 7.5.7 tests, real service-backed reads, GET-only route smoke tests, all completed Phase 7.5 and Phase 7 regressions, the complete suite, compilation, dependency consistency, SQLite integrity/FKs, completed-phase immutability, and production/runtime data immutability.
