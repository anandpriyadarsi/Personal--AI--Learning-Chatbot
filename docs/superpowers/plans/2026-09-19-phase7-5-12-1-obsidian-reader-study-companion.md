# Phase 7.5.12.1 — Obsidian Reader + ANVAYA Study Companion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Use strict RED → GREEN → regression cycles, and do not commit implementation until the complete gate passes.

**Goal:** Replace the raw-source-only Obsidian preview with a safe rendered Reader, explicit native-Obsidian handoff, active browser-reading history, and persistent note-scoped key points and doubts without modifying Markdown, Obsidian configuration, registry state, or retrieval indexes.

**Architecture:** Preserve the Phase 7.5.12 `ObsidianWorkspaceReader` as the only vault-byte reader. Extend its web service view model with validated vault/note identity evidence, then compose it with a new `ObsidianStudyCompanionService`. That service owns identity, rendering, deep links, validation, history aggregation, and Companion operations while delegating all SQL to one feature-owned SQLite repository. Flask remains an adapter only. A page-local script sends bounded, sequenced active-time deltas; the server atomically owns totals.

**Tech Stack:** Python 3.8+ compatible application code; Flask 3.1/Jinja/MarkupSafe; `mistune==3.3.4` with `escape=True` and the built-in `table` plugin; SQLite migration 0005; plain local JavaScript; pytest; PowerShell gate; current ANVAYA CSS.

**Approved spec:** attached `2026-09-19-phase7-5-12-1-obsidian-reader-study-companion-design.md`

**Verified starting baseline:** `main` at `7895d464420265ec62ac8d827e526a3bcb764014` — `feat: add Phase 7.5.12 Obsidian workspace and search`; local `main` and `origin/main` match and the tracked worktree is clean.

## Scope and non-negotiable boundaries

- Work only on `main`; do not create historical phase branches.
- Commit this plan by itself before implementation.
- Keep GET `/obsidian/note?path=...` side-effect free: no session insert, no Companion write, no migration application, and no database creation.
- Keep Markdown authoritative. Store neither Markdown bodies nor rendered HTML in SQLite.
- Do not write, rename, create, delete, archive, or move vault Markdown.
- Do not call `NotesStudioService`, `AtomicMarkdownNoteStore`, `ObsidianVaultRegistryService.apply()`, retrieval builders, tutor providers, or learning-memory writes.
- Do not change `obsidian_integration.py`, the Phase 5.3 scanner, Phase 5.4 Notes Studio implementation, tutor code, or retrieval code.
- Reject path traversal, absolute note paths, symlink roots/files/folders, missing notes, changed notes, and non-UTF8 note bytes through the existing safe workspace boundary before any study write.
- Do not add a CDN, frontend framework, Node requirement, Obsidian plugin, native-Obsidian tracking, backlinks UI, RAG indexing, summaries, generated key points, doubt answering, note editing, or Phase 7.5.13 work.
- Route modules must contain no `sqlite3` import, SQL statement, `Path.read_*`, or vault/config integration call.
- The new Reader script must be loaded only by `obsidian_note.html`; global `static/js/app.js` remains unchanged.
- Browser responses must not disclose absolute vault paths, database paths, SQL, exception strings, or tracebacks.

## Design rulings established by repository inspection

1. Migration `0005_obsidian_study_companion.sql` follows current contiguous migrations 0001–0004. It creates two feature-owned tables and does not alter the pre-existing general `study_sessions` table.
2. `VaultNoteFingerprint.assistant_id`, `relative_path`, and `source_hash` already come from the Phase 5.3 scanner. No second frontmatter parser is introduced.
3. `ObsidianWorkspaceService.note_preview()` remains the filesystem-facing validation boundary. It will add safe identity evidence to its returned dictionary, but it will not write or expose the configured root.
4. Mistune 3.3.4 is a small pure-Python package, supports Python 3.8+, provides fenced code/lists/quotes/links and a built-in table plugin, escapes raw HTML through `create_markdown(escape=True, plugins=["table"])`, and rejects harmful URL protocols by default. The wrapper still tests and enforces that contract before returning `Markup`.
5. YAML-style frontmatter is omitted only from the rendered reading body when it has a valid closing delimiter. The unmodified full Markdown remains in the collapsed Source view.
6. The migration adds `last_event_sequence INTEGER NOT NULL DEFAULT 0` to `obsidian_reading_sessions`. This is the minimal storage needed to make heartbeat/end events replay-safe without a third event table. It does not duplicate note content.
7. Companion text is normalized to LF, stripped, and bounded to 2,000 Unicode characters in both service validation and a database constraint.
8. Tracking rejects, rather than silently clamps, out-of-range deltas or scroll values. Heartbeats accept 1–60 seconds; end accepts a final 0–60 seconds; scroll is 0–10000 basis points; event sequence is a positive integer.

## Exact file scope

### Create

- `personal_learning_assistant/repositories/sqlite/migrations/0005_obsidian_study_companion.sql`
- `personal_learning_assistant/repositories/sqlite/obsidian_study_repository.py`
- `personal_learning_assistant/services/obsidian_markdown_renderer.py`
- `personal_learning_assistant/services/obsidian_study_companion_service.py`
- `personal_learning_assistant/ui/web/static/js/obsidian_reader.js`
- `tests/test_phase7_5_obsidian_markdown_renderer.py`
- `tests/test_phase7_5_obsidian_study_repository.py`
- `tests/test_phase7_5_obsidian_study_companion.py`
- `tests/test_phase7_5_obsidian_reader_routes.py`
- `phase7_5_fix12_1_gate.ps1`

### Modify

- `requirements.txt`
- `personal_learning_assistant/services/obsidian_workspace_service.py`
- `personal_learning_assistant/ui/web/routes.py`
- `personal_learning_assistant/ui/web/templates/base.html`
- `personal_learning_assistant/ui/web/templates/obsidian_note.html`
- `personal_learning_assistant/ui/web/static/css/app.css`
- `tests/test_phase7_5_obsidian_workspace.py` only where the enriched note view model or new default rendered view changes an existing contract
- `tests/test_phase6_active_recall_quiz.py` only to change exact whole-history assertions from `(1, 2, 3, 4)` to the preserved 0001–0004 prefix, because migration 0005 is now legitimately present

### Protected and unchanged

- `obsidian_integration.py`
- `personal_learning_assistant/repositories/filesystem/obsidian_workspace_reader.py`
- `personal_learning_assistant/repositories/filesystem/obsidian_vault_scanner.py`
- `personal_learning_assistant/services/obsidian_vault_registry_service.py`
- `personal_learning_assistant/repositories/sqlite/obsidian_vault_repository.py`
- `personal_learning_assistant/services/notes_studio_service.py`
- `personal_learning_assistant/repositories/sqlite/notes_studio_repository.py`
- `personal_learning_assistant/repositories/filesystem/markdown_note_store.py`
- `personal_learning_assistant/retrieval/**`
- `personal_learning_assistant/tutor/**`
- `personal_learning_assistant/ui/web/static/js/app.js`
- migrations `0001_foundation.sql` through `0004_practice_recall.sql`
- all configured-vault Markdown
- `data/obsidian_config.json` and every other existing `data/*.json`
- `.phase4_authority.json`
- `.phase5_retrieval/**`

## Persistence contract

Migration `0005_obsidian_study_companion.sql` creates exactly these feature tables and indexes:

```sql
CREATE TABLE obsidian_reading_sessions (
    id TEXT PRIMARY KEY,
    vault_identity TEXT NOT NULL CHECK (length(trim(vault_identity)) > 0),
    note_identity TEXT NOT NULL CHECK (length(trim(note_identity)) > 0),
    relative_path TEXT NOT NULL CHECK (length(trim(relative_path)) > 0),
    source_hash TEXT NOT NULL CHECK (length(source_hash) = 64),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    active_seconds INTEGER NOT NULL DEFAULT 0 CHECK (active_seconds >= 0),
    max_scroll_bps INTEGER NOT NULL DEFAULT 0
        CHECK (max_scroll_bps BETWEEN 0 AND 10000),
    last_event_sequence INTEGER NOT NULL DEFAULT 0
        CHECK (last_event_sequence >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (ended_at IS NULL OR ended_at >= started_at)
);

CREATE INDEX obsidian_reading_sessions_note_time_ix
    ON obsidian_reading_sessions
       (vault_identity, note_identity, started_at DESC);

CREATE INDEX obsidian_reading_sessions_updated_ix
    ON obsidian_reading_sessions (updated_at DESC);

CREATE TABLE obsidian_companion_entries (
    id TEXT PRIMARY KEY,
    vault_identity TEXT NOT NULL CHECK (length(trim(vault_identity)) > 0),
    note_identity TEXT NOT NULL CHECK (length(trim(note_identity)) > 0),
    relative_path TEXT NOT NULL CHECK (length(trim(relative_path)) > 0),
    entry_type TEXT NOT NULL CHECK (entry_type IN ('key_point', 'doubt')),
    entry_text TEXT NOT NULL
        CHECK (length(trim(entry_text)) BETWEEN 1 AND 2000),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT
);

CREATE INDEX obsidian_companion_entries_note_type_time_ix
    ON obsidian_companion_entries
       (vault_identity, note_identity, entry_type, created_at DESC);
```

The tables intentionally have no foreign key to registry `vaults` or `note_metadata`: the Reader works from the currently configured live vault without requiring registry apply. SQLite integrity and foreign-key checks must still be clean.

## Identity and note-validation contract

`ObsidianWorkspaceService.note_preview(relative_path)` continues to normalize, scan, locate, and hash-verify the selected note. Its safe result gains:

```python
{
    # existing keys remain
    "assistant_id": note.assistant_id,       # canonical UUID or None
    "vault_name": str(scan.vault_name),
    "vault_identity": "vault:" + sha256(normalized_root.encode("utf-8")).hexdigest(),
}
```

`normalized_root` is `unicodedata.normalize("NFC", os.path.normcase(str(Path(vault_path).resolve(strict=False))))`, with backslashes converted to `/` and trailing separators removed except for a filesystem root. It is hashed immediately and is never returned separately.

The study service derives:

```python
if assistant_id:
    note_identity = "assistant:" + assistant_id
else:
    material = vault_identity + "\0" + normalized_note_path_key(relative_path)
    note_identity = "path:" + sha256(material.encode("utf-8")).hexdigest()
```

Every start, heartbeat, end, add, and archive operation calls the current workspace note validation again. The submitted `source_hash` must be 64 lowercase hexadecimal characters and must equal the current note hash; a changed note produces a safe conflict and no database mutation.

## Repository interface

Create `SQLiteObsidianStudyRepository(database_path, *, connection_factory=None)`. It opens a fresh read-only URI connection for reads and a fresh read/write connection for writes, enables foreign keys, validates that both 0005 tables and required columns exist, uses `BEGIN IMMEDIATE` for atomic updates, closes every connection, and maps `sqlite3.Error` to safe repository errors.

Public interface:

```python
class ObsidianStudyRepositoryError(RuntimeError): ...
class ObsidianStudyRepositoryNotFoundError(ObsidianStudyRepositoryError): ...
class ObsidianStudyRepositoryConflictError(ObsidianStudyRepositoryError): ...

class SQLiteObsidianStudyRepository:
    def reading_history(
        self, *, vault_identity: str, note_identity: str, recent_limit: int = 5
    ) -> dict: ...

    def create_session(
        self, *, session_id: str, vault_identity: str, note_identity: str,
        relative_path: str, source_hash: str, now: str
    ) -> dict: ...

    def heartbeat(
        self, *, session_id: str, vault_identity: str, note_identity: str,
        source_hash: str, sequence: int, delta_seconds: int,
        scroll_bps: int, now: str
    ) -> dict: ...

    def end_session(
        self, *, session_id: str, vault_identity: str, note_identity: str,
        source_hash: str, sequence: int, delta_seconds: int,
        scroll_bps: int, now: str
    ) -> dict: ...

    def list_entries(
        self, *, vault_identity: str, note_identity: str
    ) -> tuple[dict, ...]: ...

    def add_entry(
        self, *, entry_id: str, vault_identity: str, note_identity: str,
        relative_path: str, entry_type: str, entry_text: str, now: str
    ) -> dict: ...

    def archive_entry(
        self, *, entry_id: str, vault_identity: str, note_identity: str,
        now: str
    ) -> dict: ...
```

Repository rules:

- `reading_history()` returns `times_opened`, `last_read_at`, `total_active_seconds`, `last_session_active_seconds`, `max_scroll_bps`, and no more than five newest sessions.
- Session lookup is scoped by `session_id + vault_identity + note_identity + source_hash`.
- `heartbeat()` atomically adds `delta_seconds` and raises stored progress to `max(old, scroll_bps)` only when `sequence > last_event_sequence` and `ended_at IS NULL`.
- A heartbeat replay with the same or lower sequence returns the unchanged row with `accepted=False`; it never increments totals.
- `end_session()` atomically applies one final bounded delta/progress update and sets `ended_at`. Replaying the already accepted end returns `accepted=False` and does not change totals.
- A heartbeat after a completed session is a conflict.
- `list_entries()` returns only `archived_at IS NULL`, deterministically ordered by type, creation time, and ID.
- `archive_entry()` includes vault/note predicates, so an entry ID from another note cannot be archived.
- All SQL parameterizes values. Dynamic SQL is limited to fixed internal schema-inspection names.

## Renderer interface and safety contract

Create `render_markdown(markdown_text: str) -> Markup` in `obsidian_markdown_renderer.py`.

Implementation contract:

```python
_MARKDOWN = mistune.create_markdown(
    escape=True,
    hard_wrap=False,
    plugins=["table"],
)
```

- Strip a valid leading YAML-style frontmatter block only for rendering.
- Support headings, paragraphs, emphasis/strong, lists, block quotes, fenced/inline code, tables, and links.
- Raw `<script>` and `<img onerror>` strings must remain visible as text and never become elements.
- Harmful protocols including `javascript:`, `vbscript:`, `file:`, and unsafe `data:` must never appear in generated `href`/`src` attributes.
- Return `Markup` only around output from this configured renderer.
- If parsing raises, return `Markup('<pre class="obsidian-render-fallback">' + escape(original_text) + '</pre>')`; never return unescaped input.
- Do not use Jinja `|safe`, a browser parser, a CDN, or a general HTML sanitizer with a broad allowlist.

## Study-service interface

Create `ObsidianStudyCompanionService(workspace_service, repository, *, renderer=render_markdown, now=_utc_now, id_factory=uuid.uuid4)` plus `build_obsidian_study_companion_service(workspace_service=None, database_path="data/learning_assistant.db")`.

Public interface:

```python
class ObsidianStudyValidationError(RuntimeError): ...
class ObsidianStudyNotFoundError(RuntimeError): ...
class ObsidianStudyConflictError(RuntimeError): ...
class ObsidianStudyUnavailableError(RuntimeError): ...

def reader_view(self, relative_path) -> dict: ...

def start_reading(self, *, relative_path, source_hash) -> dict: ...

def heartbeat(
    self, *, relative_path, source_hash, session_id,
    sequence, delta_seconds, scroll_bps
) -> dict: ...

def end_reading(
    self, *, relative_path, source_hash, session_id,
    sequence, delta_seconds, scroll_bps
) -> dict: ...

def add_companion_entry(
    self, *, relative_path, source_hash, entry_type, entry_text
) -> dict: ...

def archive_companion_entry(
    self, *, relative_path, source_hash, entry_id
) -> dict: ...
```

`reader_view()`:

1. Calls `workspace_service.note_preview()` once for current bytes and scanner evidence.
2. Derives note identity and a deep link with `urlencode({"vault": vault_name, "file": relative_path})` as `obsidian://open?...`; it never uses the root path.
3. Renders Markdown safely while retaining the exact source text separately.
4. Reads history and active Companion entries.
5. If repository/history access fails, still returns the rendered note with `companion.available=False`, empty history/entries, and `"Study history and Companion are temporarily unavailable."`.
6. Does not start a session or write anything.

Write methods:

- Revalidate the current note and exact source hash before repository calls.
- Validate UUID session/entry IDs, integral bounds, entry type, and text length before database access.
- Translate repository/database failures into safe service errors without preserving raw exception text in user-facing messages.
- Never call the renderer with database content and never call any Markdown write service.

## Route signatures and response contracts

Preserve:

```text
GET /obsidian
GET /obsidian/note?path=<vault-relative-markdown-path>
```

The Reader GET calls `reader_view(path)` and renders status 200. Existing invalid-path, missing-note, and unsafe-read mappings remain 400, 404, and 503. An unavailable Companion/history database alone does not change the Reader's 200 response.

Add JSON tracking routes:

| Route | JSON request | Success |
|---|---|---|
| `POST /obsidian/note/reading/start` | `{"path": str, "source_hash": str}` | 201 JSON with `ok`, `session_id`, `active_seconds`, `max_scroll_bps` |
| `POST /obsidian/note/reading/heartbeat` | `{"path": str, "source_hash": str, "session_id": uuid, "sequence": int, "delta_seconds": 1..60, "scroll_bps": 0..10000}` | 200 JSON with `ok`, `accepted`, `active_seconds`, `max_scroll_bps` |
| `POST /obsidian/note/reading/end` | same as heartbeat, but `delta_seconds`: 0..60 | 200 JSON with `ok`, `accepted`, `active_seconds`, `max_scroll_bps`, `ended_at` |

Tracking errors are small same-origin JSON only:

- malformed JSON/input/path/ID/range: 400 `{"ok": false, "error": "invalid_request"}`;
- missing current note/session: 404 `error="not_found"`;
- changed source or ended-session conflict: 409 `error="conflict"`;
- database/backend unavailable: 503 `error="unavailable"`.

No JSON response includes exception text, absolute paths, SQL, note bodies, or rendered HTML.

Add form routes:

```text
POST /obsidian/note/companion/key-points
POST /obsidian/note/companion/doubts
POST /obsidian/note/companion/<entry_id>/archive
```

Forms submit `path`, `source_hash`, and `entry_text` where applicable. Successful writes return 303 to `url_for("web.obsidian_note", path=relative_path, companion_saved="key_point"|"doubt"|"archived")`. Invalid/missing/conflicting/unavailable operations render or redirect with a fixed safe message and the appropriate 400/404/409/503 status; raw submitted text is not placed into query strings. Archive is scoped to the current note.

`routes.py` gains `OBSIDIAN_STUDY_SERVICE_FACTORY` injection for tests. When absent, it composes the existing `_obsidian_workspace_service()` with the default SQLite study repository. The route layer calls service methods only.

## Template and CSS contract

`base.html` adds a page-local `{% block page_scripts %}{% endblock %}` after the global `app.js` include. Only `obsidian_note.html` fills it with deferred `js/obsidian_reader.js`.

`obsidian_note.html` must render, in order:

1. Back navigation and Reader header.
2. Note title/path/tags and a secondary `Open in Obsidian ↗` anchor.
3. A two-column `.obsidian-reader-layout` with:
   - `<article class="obsidian-reading-view">{{ note.rendered_html }}</article>` where the value is already `Markup`;
   - an `<aside class="obsidian-companion">` with history, key points, doubts, add forms, and archive forms.
4. A collapsed `<details class="obsidian-source">` containing `<pre>{{ note.text }}</pre>` with ordinary Jinja escaping.
5. A no-script notice stating that reading-time tracking requires JavaScript while reading and Companion forms remain usable.
6. A data element containing only same-origin endpoint URLs, relative path, and source hash for the tracking script.

Desktop uses a content-first two-column grid; at `max-width: 900px` the aside moves below the article. Reading typography covers headings, paragraphs, lists, quotes, tables with horizontal overflow, inline/fenced code, and safe long-word wrapping. Buttons/forms retain current ANVAYA tokens and accessible labels. Source remains collapsed by default.

## Reader JavaScript contract

`obsidian_reader.js` is an IIFE with no dependencies and exits unless the Reader data element exists.

Constants:

```javascript
const HEARTBEAT_MS = 30000;
const TICK_MS = 1000;
const IDLE_MS = 90000;
const MAX_EVENT_SECONDS = 60;
```

Behavior:

- POST start once after DOM readiness; tracking begins only after a valid `session_id` response.
- Maintain a strictly increasing integer `sequence`; each heartbeat/end uses the next value.
- Treat the Reader as active only when `document.visibilityState === "visible"`, `document.hasFocus()`, and the most recent activity is within 90 seconds.
- Refresh activity on throttled `scroll`, `keydown`, `pointerdown`, `touchstart`, `focus`, and `visibilitychange` events.
- A one-second monotonic tick accrues only active elapsed time and resets its time origin on focus/visibility transitions so background suspension is never counted.
- Calculate document scroll progress in basis points. A fully visible/non-scrollable document reports 10000; otherwise clamp the ratio to 0–10000 and retain the maximum.
- Every 30 seconds, send at most 60 whole pending seconds through same-origin `fetch` with JSON and `credentials: "same-origin"`; retain unsent seconds after a network failure.
- Serialize sends so concurrent timers cannot reuse sequence numbers or deltas.
- On `visibilitychange` to hidden or `pagehide`, send one end payload containing the final 0–60 second delta and maximum progress with `navigator.sendBeacon` and an `application/json` Blob when available; use `fetch(..., {keepalive: true})` as fallback.
- Never send note text, rendered HTML, absolute paths, Companion content, cookies explicitly, or any external request.
- If start/tracking fails, stop automatic tracking without affecting Reader or form usability.

## TDD execution tasks

### Task 1 — Migration and compatibility prefix

**Files:** create migration; create/update repository tests; minimally adjust the two Phase 6 exact-history assertions.

- [ ] Write a failing migration test that applies all migrations to a temporary database and asserts version 5/name/checksum, both table schemas, constraints, indexes, idempotence, integrity `ok`, and no FK violations.
- [ ] Run `python -m pytest -q tests/test_phase7_5_obsidian_study_repository.py -k migration` and capture the expected missing-0005 failure.
- [ ] Add `0005_obsidian_study_companion.sql` exactly as specified.
- [ ] Change the Phase 6.5 test's whole-history assertions to `applied[:4] == (1, 2, 3, 4)` and `versions[:4] == (1, 2, 3, 4)` while retaining its 0004 table assertions.
- [ ] Run the migration test and `python -m pytest -q tests/test_phase6_active_recall_quiz.py` to GREEN.

### Task 2 — Safe Markdown rendering

**Files:** add requirement, renderer, renderer tests.

- [ ] Write failing tests for headings, paragraphs, strong/emphasis, ordered/unordered lists, quotes, fenced/inline code, tables, HTTPS/relative links, frontmatter omission, and retained raw source input.
- [ ] Write failing XSS tests for raw `<script>`, raw `<img onerror>`, attribute-breaking text, and Markdown links/images using harmful protocols. Assert no executable tag/attribute/protocol is emitted and the raw tag strings remain readable.
- [ ] Write a failing forced-parser-error test asserting the escaped `<pre>` fallback.
- [ ] Run `python -m pytest -q tests/test_phase7_5_obsidian_markdown_renderer.py` and capture the missing-module failure.
- [ ] Add `mistune==3.3.4` to `requirements.txt`, install that exact pin, and implement only the renderer contract.
- [ ] Rerun the renderer module to GREEN, then run `python -m pip check`.

### Task 3 — Repository sessions, aggregation, and replay safety

**Files:** repository and repository tests.

- [ ] Write failing tests for schema validation and read-only history on an empty migrated database.
- [ ] Write failing tests for create → heartbeat → heartbeat → end, total aggregation, times opened, last-session time, maximum progress, and a five-row recent history cap.
- [ ] Write failing tests for 1- and 60-second accepted heartbeats, replayed sequence not double-counting, heartbeat after end, wrong note/vault/source scope, missing/malformed IDs, and atomic rollback on database errors.
- [ ] Run focused tests and capture the missing-repository failure.
- [ ] Implement connection lifecycle, parameterized SQL, transactions, repository errors, and session methods.
- [ ] Rerun session tests to GREEN and execute migration tests as regression.

### Task 4 — Repository Companion persistence and isolation

**Files:** repository and repository tests.

- [ ] Write failing tests for add/list key points and doubts, deterministic ordering, persistence after repository reconstruction, note/vault isolation, archive behavior, cross-note archive refusal, empty/invalid/overlong database constraints, and raw text preservation without Markdown writes.
- [ ] Run the Companion subset and capture failures.
- [ ] Implement `list_entries`, `add_entry`, and scoped `archive_entry`.
- [ ] Rerun repository tests to GREEN and assert temporary vault Markdown hashes remain identical.

### Task 5 — Safe workspace identity enrichment

**Files:** workspace service and Phase 7.5.12/new service tests.

- [ ] Write failing tests proving a valid scanner `assistant_id` is returned, vault identity is deterministic, different roots differ, path normalization is stable on the host, and no absolute root appears in the public preview dictionary or serialized response.
- [ ] Run `python -m pytest -q tests/test_phase7_5_obsidian_workspace.py -k "identity or note_preview"` and capture failure.
- [ ] Add only `assistant_id`, `vault_name`, and hashed `vault_identity` to `note_preview()`.
- [ ] Rerun focused tests plus the entire existing Phase 7.5.12 module.

### Task 6 — Study service Reader, identity, and failure fallback

**Files:** study service and service tests.

- [ ] Write failing tests for `assistant:<uuid>` identity, fallback `path:<sha256>` identity, stable reopen, safe deep-link encoding, no absolute path in the link/view model, and safe rendered/source split.
- [ ] Write failing tests proving `reader_view()` performs no repository write and no session creation.
- [ ] Write failing tests where history/list raises a database error but the note still returns rendered safely with `companion.available=False`.
- [ ] Write a renderer-failure service test that still returns escaped output.
- [ ] Implement `reader_view()` and the lazy factory.
- [ ] Rerun service + renderer tests to GREEN and the Phase 7.5.12 service regressions.

### Task 7 — Study service tracking commands

**Files:** study service and service tests.

- [ ] Write failing tests for start, heartbeat, end, active-total delegation, source-change conflict, current-note deletion, traversal, non-UTF8/symlink failures, malformed UUID, non-integral values, heartbeat delta 0/61, end delta -1/61, scroll -1/10001, and replay behavior.
- [ ] Confirm the focused service subset is RED.
- [ ] Implement validators and safe error translation; every command must revalidate the current note before calling the repository.
- [ ] Rerun the tracking subset to GREEN and repository regressions.

### Task 8 — Study service Companion commands

**Files:** study service and service tests.

- [ ] Write failing tests for key point/doubt add, persistence across service reconstruction, note isolation, archive, cross-note archive denial, whitespace-only input, 2,001-character input, note/source changes, and database unavailable.
- [ ] Confirm RED, implement the minimum add/archive behavior, and rerun to GREEN.
- [ ] Run all new repository/service/renderer tests together.

### Task 9 — Reader routes, templates, CSS, and no-JS contract

**Files:** routes, base/note templates, CSS, route tests.

- [ ] Write failing GET tests for rendered mode default, collapsed escaped Source, Open in Obsidian, Companion history/entries, no session mutation, DB-unavailable Reader fallback, traversal/absolute/missing/symlink/non-UTF8/source-change status mapping, and raw HTML XSS.
- [ ] Write failing POST route tests for JSON status/payload contracts, malformed JSON/session IDs, heartbeat bounds, replay, backend redaction, Companion POST + 303, persistence after refresh, archive PRG, wrong-note entry isolation, and overlong text.
- [ ] Write static contract tests proving the dedicated script is referenced only from `obsidian_note.html`, the global script is unchanged, required activity/visibility/beacon constants exist, forms work without script, raw source is in a closed `<details>`, desktop grid/mobile breakpoint classes exist, and routes contain no SQL/direct file reads.
- [ ] Confirm route/template tests are RED.
- [ ] Add the page-script block, implement route adapters, replace the note template, and add scoped CSS.
- [ ] Rerun route tests to GREEN, then run the existing Phase 7.5.12 Obsidian tests.

### Task 10 — Dedicated active-time script

**Files:** Reader JS and route/static contract tests.

- [ ] Add failing assertions for 30-second heartbeat, 90-second idle cutoff, 60-second outbound maximum, visible/focused/recent activity gates, monotonic sequence, bounded progress, serialized sends, JSON same-origin fetch, and beacon/keepalive final end.
- [ ] Implement the IIFE behavior exactly as specified.
- [ ] Rerun the static contract and route modules to GREEN.
- [ ] During browser validation, verify real focus/background/scroll activity changes persisted totals while idle/background waiting does not.

### Task 11 — Strict gate

**File:** `phase7_5_fix12_1_gate.ps1`.

- [ ] Write the gate so `$PlanPath` is this file and `$BaseCommit = git log -1 --format=%H -- $PlanPath`; block unless current `HEAD` exactly equals that separately committed plan commit.
- [ ] Require branch `main`, an unstaged implementation, all allowed files present, and no path outside the whitelist.
- [ ] Capture hashes/existence before test execution for production SQLite, authority control, all `data/*.json`, configured vault Markdown, retrieval index, protected code, prior migrations, and global JS.
- [ ] Exclude `__pycache__`, `*.pyc`, and `*.pyo` from tree hashes and scope checks.
- [ ] Implement all 18 gate stages below and the exact PASS banner.

## Exact gate stages

`phase7_5_fix12_1_gate.ps1` runs these stages in order and stops on the first failure:

1. `tests/test_phase7_5_obsidian_markdown_renderer.py`.
2. Migration and repository module, filtered to schema/integrity/history.
3. Repository/service module subsets for session start/heartbeat/end, aggregation, bounds, and replay.
4. Repository/service module subsets for Companion persistence, note isolation, text bounds, and archive.
5. Reader route/template/JS module.
6. Reader GET-purity and failure-safety subset across all new and Phase 7.5.12 tests.
7. Entire `tests/test_phase7_5_obsidian_workspace.py` Phase 7.5.12 regression.
8. Entire `tests/test_phase5_obsidian_vault_registry.py` and `tests/test_phase5_notes_studio_foundation.py` regressions.
9. Every `tests/test_phase7_5_*.py` web regression module, including the four new modules.
10. `test_phase7_runtime_inventory.py`, `test_phase7_recovery_bundle.py`, `test_phase7_restore_rehearsal.py`, and `test_phase7_consumer_watch.py`.
11. Complete pytest suite, using the established temporary-copy exception only for `test_phase2_root_has_no_production_learning_assistant_database` because the gate fixture database exists locally.
12. `compileall` for all created/modified Python modules/tests, exact installed Mistune version 3.3.4, and `pip check`.
13. Fresh temporary database migration through 0005, schema assertions, `PRAGMA integrity_check`, and `PRAGMA foreign_key_check`; also read-only integrity/FK checks for `data/learning_assistant.db`.
14. Protected code hashes and forbidden dependency/write-primitive scans.
15. Configured vault Markdown manifest unchanged.
16. `data/obsidian_config.json`, all other `data/*.json`, `.phase4_authority.json`, and production SQLite unchanged during the gate.
17. `.phase5_retrieval/**` path set and hashes unchanged.
18. No staged files, `git diff --check`, allowed-whitelist-only diff from the plan baseline, required files present, and no runtime artifacts counted.

Final output must be exactly headed:

```text
================================================================
 PHASE 7.5.12.1 OBSIDIAN READER + STUDY COMPANION: PASS
================================================================
```

## Gate allowed-file whitelist

```text
requirements.txt
personal_learning_assistant/repositories/sqlite/migrations/0005_obsidian_study_companion.sql
personal_learning_assistant/repositories/sqlite/obsidian_study_repository.py
personal_learning_assistant/services/obsidian_markdown_renderer.py
personal_learning_assistant/services/obsidian_study_companion_service.py
personal_learning_assistant/services/obsidian_workspace_service.py
personal_learning_assistant/ui/web/routes.py
personal_learning_assistant/ui/web/templates/base.html
personal_learning_assistant/ui/web/templates/obsidian_note.html
personal_learning_assistant/ui/web/static/css/app.css
personal_learning_assistant/ui/web/static/js/obsidian_reader.js
tests/test_phase6_active_recall_quiz.py
tests/test_phase7_5_obsidian_workspace.py
tests/test_phase7_5_obsidian_markdown_renderer.py
tests/test_phase7_5_obsidian_study_repository.py
tests/test_phase7_5_obsidian_study_companion.py
tests/test_phase7_5_obsidian_reader_routes.py
phase7_5_fix12_1_gate.ps1
```

If an implementation need appears outside this list, stop and compare it to the approved design instead of expanding scope silently.

## Visual/browser verification after the gate

Run ANVAYA on loopback against a disposable migrated SQLite database and disposable configured vault containing a normal long note and a dedicated XSS note. Record screenshots or direct visual observations for:

1. workspace list and default in-ANVAYA note click;
2. rendered headings, paragraphs, emphasis, lists, table, quote, fenced code, inline code, and link;
3. collapsed Source revealing exact raw Markdown;
4. Open in Obsidian link containing vault name/relative file but no absolute path;
5. desktop side-by-side layout;
6. narrow/mobile stacked layout with no horizontal page overflow;
7. long-note scrolling and progress increase;
8. key point save, doubt save, refresh persistence, and archive;
9. history values after a short active session;
10. no increase while the page is hidden/idle;
11. safe visible raw `<script>`/`<img onerror>` strings with no execution;
12. Reader usability and Companion form usability when JavaScript is disabled.

Do not use a production vault note as the XSS fixture and do not leave browser-validation rows in production SQLite.

## Commit and push boundary

1. Commit and push this plan alone as:

   ```text
   docs: add Phase 7.5.12.1 Obsidian Reader companion plan
   ```

2. Implement with the worktree at that plan commit. Leave every implementation file uncommitted throughout RED/GREEN work.
3. Run the complete gate after every implementation fix that follows a gate failure.
4. After the exact PASS banner, perform browser validation, then rerun the complete gate so the final evidence is fresh.
5. Run `git diff --check`, `git status --short`, and `git diff --stat`; inspect every changed path against the whitelist.
6. Create one implementation commit only:

   ```text
   feat: add Phase 7.5.12.1 Obsidian Reader study companion
   ```

7. Push `main`, verify local `main` and `origin/main` are the same commit, and verify the tracked worktree is clean.
8. Stop. Phase 7.5.13 is outside this plan.
