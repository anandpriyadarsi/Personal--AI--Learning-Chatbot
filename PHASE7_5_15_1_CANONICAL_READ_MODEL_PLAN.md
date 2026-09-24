# Phase 7.5.15.1 — Canonical Read Model + Card Architecture

Parent: PHASE7_5_15_NOTES_STUDIO_2_MASTER_SPEC.md
Branch: phase7.5.15/notes-studio-rich
Original baseline: f8590aca82b586e5e21b980f7e720040bb55b963

## Objective
Create the read-only architectural foundation for Notes Studio 2.0. Later phases must be able to render compact cards and full details without creating a second note authority, bypassing Obsidian protections, mutating user data during reads, or depending on Tutor 2.0. This unit is architecture/read-model work, not the final visual redesign.

## Mandatory pre-edit audit
Before implementation, inspect and record exact current paths for:
- /notes GET behavior and service/repository dependencies;
- /obsidian browse/search behavior;
- /obsidian/note safe reader behavior;
- Phase 5.4 Notes Studio commands/services and managed-note metadata;
- Obsidian scanner/configuration service;
- backlink/link-graph data currently available;
- existing knowledge reader/source attachment code if relevant;
- templates/CSS used by Notes and Obsidian;
- tests/gates protecting Phase 5.4, 7.5.11, 7.5.12 and 7.5.12.1/2/3;
- production data/directories the gate must hash before/after.

Do not guess module names. Current code and tests are authoritative.

## Required read boundary
Implement or define one Notes Studio read boundary with two explicit logical views.

### NoteCard
Minimum logical fields:
- stable source-appropriate identity;
- title;
- topic;
- course when available;
- note/template type when available;
- note date when available;
- 2–5 explicit card-summary/key-point strings when available;
- tags;
- pinned/lifecycle state when available;
- safe relative path when applicable;
- managed/unmanaged or source-kind compatibility information;
- optional visual/relationship counts only if cheaply and safely derivable.

NoteCard MUST NOT expose the complete body.

### NoteDetail
Minimum logical fields:
- identity matching the card;
- full Markdown body;
- parsed safe metadata;
- source-relative path;
- current fingerprint/hash when available;
- tags;
- relationship/backlink information only when safely available from current architecture.

The web layer should not need to know whether fields came from frontmatter, structured metadata or a compatibility adapter.

## Card-summary rules
1. Prefer explicit controlled card_summary/key-point metadata.
2. Expose only 2–5 card points.
3. Never invoke an LLM while listing notes.
4. Never write generated summaries during GET.
5. If explicit points are absent, use a documented compatibility fallback or no points. Do not pretend an arbitrary body slice is authored metadata.
6. Full body is detail-only.

The fallback must be tested and documented.

## Date rules
Use explicit deterministic precedence. Prefer controlled note metadata. Any filesystem timestamp fallback must remain fallback data and must never be written back during reads. Do not bulk-add dates in 15.1.

## Compatibility model
Managed Obsidian/Notes Studio notes use existing safe identity/metadata. Unmanaged Obsidian Markdown remains readable without forced adoption or rewrite. Legacy JSON notes must not be silently deleted or mutated. Either adapt legacy rows into compatibility card/detail data or preserve their existing behavior while introducing the canonical rich-note path. Document and test the choice.

No legacy-to-Markdown migration is authorized.

## Read purity
Listing, searching and detail reading must not edit Markdown, add frontmatter, create attachment folders, update SQLite, alter data/notes.json, apply/refresh registry state, rebuild retrieval indexes, enqueue save events, alter Obsidian config or write caches into the vault.

Derived data must be in memory or read from already-authoritative/derived state.

## Security
Preserve configured-vault boundary, symlink rejection, absolute/path-traversal rejection, Markdown-only body opening, fingerprint/stale-file protection where applicable, safe HTML/script handling and degraded errors without raw exception leakage. Do not weaken Phase 7.5.12 protections.

## Performance
Design card listing so later UI does not need full-body rendering/parsing for every note. Avoid LLM calls, retrieval rebuilds, repeated full-vault scans within one request where safely reusable, and N+1 structured queries. Do not introduce an unmeasured write cache.

## Web scope
Allowed: internal service/model additions, compatibility adapters, minimal route/view-model wiring needed to prove architecture, tests/fixtures, docs and metadata display needed for characterization.

Deferred to later units: polished card grid, final styling, template creation UI, editor, uploads, visual-block authoring, lifecycle buttons and AI actions.

## Tutor isolation
Do not change Tutor reasoning/session/prompt/practice code. If a shared-file collision is discovered, stop and document an interface rather than coupling branches. No Tutor 2.0 dependency may be imported into Notes Studio reads.

## Focused tests
Cover at least:
- managed Markdown -> NoteCard;
- unmanaged Markdown with missing rich metadata;
- explicit 2–5 key-point behavior;
- full body absent from card;
- full body present in detail;
- date precedence/fallback;
- tags/frontmatter parsing;
- malformed/unsupported metadata degrades safely;
- duplicate titles keep stable navigation;
- Unicode;
- case-insensitive behavior if search is touched;
- traversal rejection;
- symlink rejection;
- stale/fingerprint protection where applicable;
- safe content/metadata escaping;
- legacy JSON compatibility;
- missing/disabled Obsidian degraded state;
- read purity for vault;
- read purity for SQLite;
- read purity for legacy JSON;
- read purity for retrieval index;
- lazy Flask app creation;
- existing Notes/Obsidian regressions.

## Strict gate
Create a dedicated gate consistent with repository conventions, expected name phase7_5_15_1_gate.ps1.

The gate must run deterministically:
1. focused 15.1 tests;
2. Phase 5.4 Notes Studio regressions;
3. Phase 7.5.11 Notes/Resources regressions;
4. relevant Phase 7.5.12/12.1/12.2/12.3 Obsidian/search/reader regressions;
5. current Phase 7.5 web regressions;
6. complete pytest suite;
7. current compile/import checks;
8. current dependency consistency checks;
9. SQLite integrity;
10. SQLite foreign-key check;
11. protected-file/diff-scope checks;
12. before/after hashes for production vault Markdown, SQLite, legacy JSON, Obsidian config and retrieval index as appropriate;
13. git diff --check.

Required final banner:
PHASE 7.5.15.1 NOTES STUDIO CANONICAL READ MODEL: PASS

Fail closed if a protected production artifact changes.

## Diff scope
Expected scope: Notes Studio/read-model service/domain files; existing Notes/Obsidian adapter/route only where necessary; focused tests/fixtures; dedicated gate; 15.1 audit/report documentation.

Avoid unrelated refactors. No database migration is expected. If audit proves one necessary, stop and amend the plan before creating it.

## Commit discipline
Do not commit implementation until the strict gate is green. Before implementation commit run git status --short, git diff --check, git diff --stat, and inspect the full diff for Tutor overlap/unrelated files. Specification/plan commits are separate from implementation.

## Acceptance criteria
15.1 is complete only when:
1. one documented read boundary produces compact card data and full detail data;
2. card data does not dump the full body;
3. title/topic/date/key-points semantics are deterministic;
4. managed/unmanaged Markdown degrade safely;
5. legacy JSON compatibility is explicit and non-destructive;
6. GET/read operations mutate no vault, SQLite, JSON, config or retrieval state;
7. Obsidian path/fingerprint protections remain intact;
8. Tutor 2.0 code is untouched;
9. focused and complete regressions pass;
10. the dedicated gate prints the required PASS banner.

## Stop conditions
Stop without implementation commit if repository reality contradicts authority assumptions; stable identity requires an unapproved schema migration; compatibility requires destructive migration; security protections would be weakened; Tutor overlap cannot be isolated; production data changes during read tests; or the full regression suite is not green. Report the exact conflict and amend this plan first.

## Next boundary
Only after 15.1 is green and committed may 15.2 build the visual Notes Library/card UI on this canonical read model. 15.2 must not bypass it.
