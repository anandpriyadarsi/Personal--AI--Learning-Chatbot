# Phase 5.3 — Obsidian Vault Registry + Link Graph

## Starting point

Phase 5.3 starts from:

`de509c9549357c77750438c608a4314bb2519357`

on:

`phase5/knowledge-notes-resources`

This is the completed Phase 5.2 Document Registry + Source Scanner checkpoint.

## Objective

Create the read/registration foundation for the configured Obsidian vault without
rewriting Markdown.

Phase 5.3 activates the existing Phase 3 tables:

- `vaults`
- `note_metadata`
- `tags`
- `note_tags`
- `note_links`

No SQLite migration is required.

## Authority boundary

Markdown remains the authoritative note body.

SQLite owns only:

- vault identity/configuration metadata;
- stable note identity;
- title/type/confidence/revision metadata;
- source hash and mtime sync evidence;
- normalized tags;
- note-to-note link graph;
- unresolved/ambiguous link evidence.

Phase 5.3 performs no Markdown writes.

## Stable note identity

Resolution order during registration:

1. an existing note row at the same normalized vault-relative path;
2. a valid frontmatter `assistant_id`;
3. deterministic first-registration UUID derived from vault ID + path key.

If a note already exists at a path, a conflicting frontmatter `assistant_id`
blocks registration rather than changing identity silently.

A valid `assistant_id` can preserve identity across a later move/rename without
requiring filename identity.

Notes without `assistant_id` remain stable while their path is unchanged.
Phase 5.4 may mirror safe stable IDs into frontmatter through the operation
journal; Phase 5.3 does not rewrite notes merely to add IDs.

## Frontmatter

The first scan is deliberately conservative.

A dependency-free subset parser recognizes:

- `assistant_id`
- `title`
- `tags`
- `note_type` / `type`
- `confidence`
- `revision_status` / `status`

Simple scalar and list forms are supported.

Unknown/complex YAML is **not discarded**. The original frontmatter text is
retained as raw evidence in `frontmatter_extra_json`, together with raw invalid
values used for diagnostics. Phase 5.3 does not rewrite or normalize the file.

Known revision-status aliases such as `not-started`, `in-progress`,
`needs-review` and equivalent case/separator forms map to canonical database
states while the raw unsupported value is retained when normalization is not
known.

## Tags

Tags are collected from:

- frontmatter `tags`;
- safe inline `#tag` occurrences outside fenced/inline code.

Identity is case-insensitive. The first display form is retained in the tags
table.

## Wiki links and backlinks

The scanner understands:

- `[[Note]]`
- `[[path/to/Note]]`
- `[[Note#Heading]]`
- `[[Note^block-id]]`
- `[[Note|label]]`
- Markdown links such as `[label](Target.md#Heading)`
- HTTP/HTTPS links

Code fences and inline code are excluded from link/tag parsing.

Wiki resolution order is:

1. exact normalized vault-relative path;
2. stable `assistant_id`;
3. unique basename;
4. unresolved/ambiguous review state.

For ordinary Markdown links, source-relative path resolution is attempted before
vault-relative path and unique basename fallback.

Duplicate basenames are never silently guessed. Ambiguous links are stored with
`target_note_id = NULL`, the raw target, and an explicit
`wiki_ambiguous`/`markdown_ambiguous` type.

Resolved links support `GetBacklinks`-style queries through
`SQLiteObsidianVaultRepository.get_backlinks()`.

## Preview and apply

The operator CLI is:

`phase5_scan_obsidian_vault.py`

Read-only configured-vault preview:

```powershell
python .\phase5_scan_obsidian_vault.py `
  --database .\data\learning_assistant.db `
  --configured `
  --vault-key "nitk-vault"
```

Preview opens SQLite using `mode=ro`.

Registration requires explicit confirmation:

```text
--apply --confirm REGISTER_PHASE5_OBSIDIAN_VAULT
```

Do not perform real registration until the Phase 5.3 gate is green and the
preview counts have been reviewed.

## Safety

Phase 5.3:

- rejects a symlink vault root;
- never follows symlink directories/files;
- hashes exact Markdown bytes;
- validates stat-before/stat-after to detect concurrent edits;
- blocks apply on unreadable/unstable/non-UTF8 notes;
- blocks duplicate stable `assistant_id` values;
- reports invalid confidence/status/assistant ID as metadata warnings;
- does not delete database rows for missing files;
- does not modify Markdown, `.obsidian`, or vault configuration;
- does not create knowledge chunks or semantic indexes;
- does not alter Phase 4 authority control;
- does not add a new schema migration.

## Scope boundary

Phase 5.3 does not yet implement:

- Notes Studio create/update/archive/trash commands;
- frontmatter writes/mirroring;
- legacy `notes.json` reconciliation;
- normalized course/topic note relations;
- Resources 2;
- PDF/PPTX/transcript extraction;
- FTS/embeddings/RAG.

Those remain later Phase 5 units.

## Promotion-aware regression handling

The historical Phase 2 closure suite contains one environment assertion that
`data/learning_assistant.db` must not exist. That assertion was correct only
before Phase 3 began. The real project has now completed the Phase 4 SQLite
authority promotion, so deleting or hiding the production database to satisfy
that old test would be unsafe and incorrect.

The Phase 5.3 gate therefore runs the full suite against the promoted runtime
while deselecting only that exact historical environment assertion, then runs
the assertion separately in an isolated temporary pre-Phase3 root where its
original precondition is valid.

The production SQLite database is never deleted, renamed or hidden.

## Gate

`phase5_fix3_gate.ps1` verifies synthetic parser/link/identity behavior, performs
a **real configured-vault preview only**, and compares Markdown hashes before and
after. It also verifies that production SQLite, Phase 4 authority state and
legacy structured JSON are unchanged.

## Next boundary

Phase 5.4 will build the Notes Studio foundation and safe file-mutation protocol
on top of the Phase 5.1 operation journal and this Phase 5.3 vault registry.
