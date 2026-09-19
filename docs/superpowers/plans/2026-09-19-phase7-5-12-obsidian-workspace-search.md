# Phase 7.5.12 — Obsidian Workspace + Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Obsidian from a disabled/CLI-only integration into a first-class ANVAYA workspace that can connect/change the configured vault, show safe status, browse Markdown notes, search live vault content, and preview selected notes without modifying Markdown, SQLite authority, or retrieval indexes.

**Architecture:** Add a read-only filesystem adapter over the existing Phase 5.3 `ObsidianVaultScanner`, plus a web-facing `ObsidianWorkspaceService` that lazily wraps the existing non-interactive `obsidian_integration.py` configuration functions. Flask uses GET for status/browse/search/preview and POST + 303 for configuration-only connect/enable/disable commands. Markdown remains authoritative; Phase 5 registry data, Notes Studio mutations, retrieval/RAG, and tutor actions remain untouched.

**Tech Stack:** Python 3.8+ compatible application code, Flask/Jinja, existing Obsidian config + Phase 5.3 scanner, pytest, PowerShell gates, current ANVAYA CSS.

**Spec:** `docs/superpowers/specs/2026-09-17-anvaya-operational-dashboard-design.md`

**Verified starting baseline:** `main` at `1de4c1a1ee23cf1cf0ae37c63c7b3b7695408d59` — `feat: add Phase 7.5.11 operational notes and resources`.

## Global Constraints

- Work only on `main`.
- Start from a clean tree at the pushed Phase 7.5.11 baseline.
- Commit this plan separately before implementation.
- `data/obsidian_config.json` remains the configuration authority.
- Markdown inside the configured vault remains authoritative note-body content.
- GET `/obsidian` and GET note preview are side-effect free.
- POST commands may only connect/change the vault, enable, or disable configuration.
- Do not invoke `obsidian_menu()`, `main.py`, CLI `input()`/`print()`, or operator CLI subprocesses from Flask.
- Do not call `ObsidianVaultRegistryService.apply()` from the web.
- Do not expose Notes Studio `create_note`, `update_note`, `trash`, `restore`, or archive commands.
- Do not mutate `.phase5_retrieval` or claim direct vault search is semantic/RAG search.
- Only `.md` files are browse/search/preview candidates.
- Reject symlink vault roots and never follow symlink files/directories.
- Never allow a requested path to escape the configured vault.
- Never render Markdown with Jinja `|safe`; display escaped text.
- Do not expose raw filesystem/database exception details.
- Keep Flask startup lazy: app creation must not scan/read the vault or configuration.
- No CDN/frontend framework/mandatory Node addition.
- Defer Markdown create/edit/delete, registry refresh, backlinks UI, RAG indexing, tutor source attachment, and “Ask ANVAYA about this note.”

## Scope Ruling

The long-term design includes controlled two-way Obsidian writes, and Phase 5.4 already contains a safer Notes Studio write protocol. Phase 7.5.12 intentionally does not expose those writes.

This milestone is **Obsidian Workspace + Search**. It should first make connection, browsing, search, and preview trustworthy. Controlled Markdown writes will later reuse Notes Studio through the ANVAYA action layer rather than creating a second write path here.

## Review Focus

1. Path traversal, absolute paths, symlink roots/files/directories.
2. External note change between scan and preview.
3. Missing/disabled/invalid/malformed vault configuration.
4. Untrusted Markdown containing HTML/script-like text.
5. Unreadable/non-UTF8/large vault notes and bounded result handling.

---

## File Structure

### Create

- `personal_learning_assistant/repositories/filesystem/obsidian_workspace_reader.py`
- `personal_learning_assistant/services/obsidian_workspace_service.py`
- `personal_learning_assistant/ui/web/templates/obsidian.html`
- `personal_learning_assistant/ui/web/templates/obsidian_note.html`
- `tests/test_phase7_5_obsidian_workspace.py`
- `PHASE7_5_FIX12_OBSIDIAN_WORKSPACE_SEARCH.md`
- `phase7_5_fix12_gate.ps1`

### Modify

- `personal_learning_assistant/ui/web/routes.py`
- `personal_learning_assistant/ui/web/templates/base.html`
- `personal_learning_assistant/ui/web/static/css/app.css`
- `tests/test_phase7_5_anvaya_shell.py`
- `tests/test_phase7_5_web_foundation.py` only if its explicit route contract requires it

### Explicitly unchanged

- `obsidian_integration.py`
- `personal_learning_assistant/repositories/filesystem/obsidian_vault_scanner.py`
- `personal_learning_assistant/services/obsidian_vault_registry_service.py`
- `personal_learning_assistant/repositories/sqlite/obsidian_vault_repository.py`
- `personal_learning_assistant/services/notes_studio_service.py`
- `personal_learning_assistant/repositories/filesystem/markdown_note_store.py`
- `personal_learning_assistant/retrieval/**`

---

## Task 1 — Safe read-only vault reader

**Files**
- Create `personal_learning_assistant/repositories/filesystem/obsidian_workspace_reader.py`
- Test `tests/test_phase7_5_obsidian_workspace.py`

**Produces**
- `ObsidianWorkspaceReader`
- `ObsidianWorkspaceReadError`
- `ObsidianWorkspacePathError`
- `scan()`
- `read_note(relative_path, expected_hash="")`
- `search(scan, query, limit=100)`

- [ ] **1. Write RED browse/symlink tests**

```python
def test_reader_browse_uses_phase53_scanner(tmp_path):
    vault = tmp_path / "Vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / "Math").mkdir()
    (vault / "Math" / "LU.md").write_text("# LU\nA = LU\n", encoding="utf-8")

    reader = ObsidianWorkspaceReader(vault, vault_key="obsidian-vault")
    scan = reader.scan()

    assert [n.relative_path for n in scan.notes] == ["Math/LU.md"]
```

Add platform-conditional tests proving:
- symlink root is rejected;
- symlink file/folder under a real root is not returned;
- `.obsidian`, `.trash`, `.git`, `node_modules` are excluded.

- [ ] **2. Run RED**

```powershell
python -m pytest -q tests/test_phase7_5_obsidian_workspace.py -k "reader_browse or symlink"
```

Expected: fail because the reader module does not exist.

- [ ] **3. Implement minimal scanner-backed reader**

```python
class ObsidianWorkspaceReader:
    def __init__(self, vault_root, *, vault_key="obsidian-vault"):
        self.root = Path(vault_root)
        if self.root.is_symlink():
            raise ObsidianWorkspacePathError(
                "Configured vault cannot be a symlink."
            )
        self.scanner = ObsidianVaultScanner(vault_key, self.root)

    def scan(self):
        try:
            return self.scanner.scan()
        except ObsidianVaultRootError as error:
            raise ObsidianWorkspacePathError(
                "The configured Obsidian vault is unavailable."
            ) from error
        except ObsidianVaultScannerError as error:
            raise ObsidianWorkspaceReadError(
                "The Obsidian vault could not be read safely."
            ) from error
```

- [ ] **4. Run GREEN + Phase 5.3 scanner regression**

```powershell
python -m pytest -q tests/test_phase7_5_obsidian_workspace.py -k "reader_browse or symlink"
python -m pytest -q tests/test_phase5_obsidian_vault_registry.py
```

- [ ] **5. Write RED traversal + stale-hash preview tests**

```python
with pytest.raises(ObsidianWorkspacePathError):
    reader.read_note("../outside.md")

with pytest.raises(ObsidianWorkspacePathError):
    reader.read_note(str((tmp_path / "outside.md").resolve()))
```

External-change test:

```python
scan = reader.scan()
note = scan.notes[0]
(vault / note.relative_path).write_text("# changed\n", encoding="utf-8")

with pytest.raises(ObsidianWorkspaceReadError, match="changed"):
    reader.read_note(note.relative_path, expected_hash=note.source_hash)
```

- [ ] **6. Implement safe Markdown resolution/read**

```python
def _resolve_markdown(self, relative_path):
    normalized = normalize_relative_path(relative_path)
    if not normalized.lower().endswith(".md"):
        raise ObsidianWorkspacePathError("Only Markdown notes can be opened.")

    root = self.root.resolve(strict=False)
    target = (self.root / Path(normalized)).resolve(strict=False)

    if target == root or root not in target.parents:
        raise ObsidianWorkspacePathError("Note path must stay inside the vault.")
    if target.is_symlink() or not target.is_file():
        raise ObsidianWorkspacePathError("The selected note is unavailable.")
    return target, normalized
```

Read bytes, SHA-256 them, compare to `expected_hash` when supplied, decode `utf-8-sig`, and return:

```python
{
    "relative_path": normalized,
    "text": decoded_text,
    "source_hash": source_hash,
    "size_bytes": len(raw),
}
```

Map `OSError`/`UnicodeDecodeError` to safe read errors.

- [ ] **7. Write RED lexical search tests**

Test title, relative path, tag, and body matching, deterministic ordering, and result cap:

```python
results = reader.search(scan, "factorization", limit=100)
assert results[0]["relative_path"] == "Math/LU.md"
assert "factorization" in results[0]["excerpt"].casefold()

assert len(reader.search(scan, "note", limit=2)) == 2
```

Blank query must not body-scan the vault.

- [ ] **8. Implement deterministic lexical search**

Case-insensitive substring match over:
- title
- relative path
- tags
- body

Result shape:

```python
{
    "relative_path": note.relative_path,
    "title": note.title,
    "tags": list(note.tags),
    "note_type": note.note_type,
    "revision_status": note.revision_status,
    "source_hash": note.source_hash,
    "excerpt": bounded_plain_text,
    "match_scope": "title" | "path" | "tag" | "body",
}
```

Bound excerpt to ~360 characters and results to maximum 100. Skip unreadable/non-UTF8 bodies with safe warning counts rather than aborting the whole search.

- [ ] **9. Run reader block**

```powershell
python -m pytest -q tests/test_phase7_5_obsidian_workspace.py -k "reader"
```

---

## Task 2 — Lazy web-service boundary

**Files**
- Create `personal_learning_assistant/services/obsidian_workspace_service.py`
- Test `tests/test_phase7_5_obsidian_workspace.py`

**Produces**
- `ObsidianWorkspaceService`
- `ObsidianWorkspaceValidationError`
- `ObsidianWorkspaceNotFoundError`
- `ObsidianWorkspaceUnavailableError`
- `workspace(search="")`
- `note_preview(relative_path)`
- `connect_vault(vault_path)`
- `enable_vault()`
- `disable_vault()`
- `build_obsidian_workspace_service()`

- [ ] **1. Write RED disconnected/disabled/connected workspace tests**

Disconnected:

```python
workspace = service.workspace()
assert workspace["configured"] is False
assert workspace["enabled"] is False
assert workspace["notes"] == []
assert workspace["summary"]["markdown_files"] == 0
```

Connected:

```python
assert workspace["configured"] is True
assert workspace["enabled"] is True
assert workspace["valid"] is True
assert workspace["vault_name"] == "Vault"
assert workspace["summary"]["markdown_files"] == 2
```

Disabled configuration must show status/path without scanning.

- [ ] **2. Run RED**

```powershell
python -m pytest -q tests/test_phase7_5_obsidian_workspace.py -k "workspace_status"
```

- [ ] **3. Implement lazy service construction**

```python
class ObsidianWorkspaceService:
    def __init__(self, config_api, reader_factory):
        self.config_api = config_api
        self.reader_factory = reader_factory
```

`build_obsidian_workspace_service()` lazily imports `obsidian_integration` and the new reader only when the route asks for the service.

Set:
- `MAX_QUERY_CHARS = 300`
- `MAX_BROWSE_NOTES = 500`
- `MAX_SEARCH_RESULTS = 100`

- [ ] **4. Write RED search workspace tests**

```python
workspace = service.workspace(search="LU")
assert workspace["query"] == "LU"
assert workspace["searched"] is True
assert workspace["summary"]["result_count"] == 1
assert workspace["notes"][0]["relative_path"] == "Math/LU.md"
```

Blank search returns browse metadata only, sorted by relative path.

- [ ] **5. Implement workspace normalization**

Browse rows:

```python
{
    "relative_path": note.relative_path,
    "title": note.title,
    "tags": list(note.tags),
    "note_type": note.note_type,
    "revision_status": note.revision_status,
    "source_hash": note.source_hash,
}
```

Search rows add `excerpt` and `match_scope`. Scanner issues become safe counts/categories only.

- [ ] **6. Write RED preview-service tests**

```python
preview = service.note_preview("Math/LU.md")
assert preview["relative_path"] == "Math/LU.md"
assert preview["title"] == "LU"
assert "A = LU" in preview["text"]
```

Mapping:
- traversal/bad path -> validation error
- missing note -> not-found
- scan/read failure -> unavailable

Preview must scan first and then call `read_note(..., expected_hash=note.source_hash)`.

- [ ] **7. Write RED configuration-write tests**

Test:
- connect valid vault
- blank path
- missing `.obsidian`
- symlink root
- enable invalid configuration
- disable
- backend exception hides secret path/detail

- [ ] **8. Implement connect/enable/disable**

Validate blank/symlink path before delegating to existing non-interactive config functions.

Safe validation message:

```text
Choose an existing Obsidian vault folder containing a .obsidian directory.
```

Successful config commands do not scan/register/index automatically.

- [ ] **9. Run service block**

```powershell
python -m pytest -q tests/test_phase7_5_obsidian_workspace.py -k "service or workspace or config or preview"
```

---

## Task 3 — Routes + navigation

**Files**
- Modify `personal_learning_assistant/ui/web/routes.py`
- Modify `personal_learning_assistant/ui/web/templates/base.html`
- Modify/test `tests/test_phase7_5_anvaya_shell.py`
- Modify/test `tests/test_phase7_5_web_foundation.py` only if required
- Test `tests/test_phase7_5_obsidian_workspace.py`

**Produces**
- GET `/obsidian`
- GET `/obsidian/note`
- POST `/obsidian/connect`
- POST `/obsidian/enable`
- POST `/obsidian/disable`

- [ ] **1. Write RED navigation + GET tests**

```python
assert "url_for('web.obsidian')" in base_source
assert "active_page == 'obsidian'" in base_source
assert "Obsidian</span><span class=\"nav-status\">Soon" not in base_source
```

Route:

```python
response = client.get("/obsidian?q=LU")
assert response.status_code == 200
assert service.workspace_calls == ["LU"]
```

- [ ] **2. Implement lazy route service helper**

```python
def _obsidian_workspace_service():
    factory = (
        current_app.config.get("OBSIDIAN_WORKSPACE_SERVICE_FACTORY")
        or build_obsidian_workspace_service
    )
    return factory()
```

GET `/obsidian` reads only `q`.

- [ ] **3. Write RED preview route tests**

Expected:
- `/obsidian/note?path=Math%2FLU.md` -> 200
- traversal -> 400
- missing -> 404
- backend unavailable -> 503
- raw backend secret never appears

- [ ] **4. Implement preview GET**

Call only `service.note_preview()` and map safe service errors.

- [ ] **5. Write RED POST + PRG tests**

Expected:
- POST `/obsidian/connect` -> 303 `/obsidian?connected=1`
- POST `/obsidian/enable` -> 303 `/obsidian?enabled=1`
- POST `/obsidian/disable` -> 303 `/obsidian?disabled=1`

Validation failure -> safe 400 workspace. Unexpected backend/config failure -> safe 503.

- [ ] **6. Implement POST routes**

Routes call only service methods; no direct JSON, filesystem, scanner, registry, or Notes Studio calls.

- [ ] **7. Activate Obsidian navigation**

Replace disabled `Soon` item with:

```html
<a class="nav-item{% if active_page == 'obsidian' %} is-active{% endif %}"
   href="{{ url_for('web.obsidian') }}"
   {% if active_page == 'obsidian' %}aria-current="page"{% endif %}>
  Obsidian
</a>
```

Include `obsidian` in the “More” open condition.

- [ ] **8. Run route/shell tests**

```powershell
python -m pytest -q `
  tests/test_phase7_5_obsidian_workspace.py -k "route or navigation" `
  tests/test_phase7_5_anvaya_shell.py `
  tests/test_phase7_5_web_foundation.py
```

---

## Task 4 — Obsidian workspace UI

**Files**
- Create `personal_learning_assistant/ui/web/templates/obsidian.html`
- Create `personal_learning_assistant/ui/web/templates/obsidian_note.html`
- Modify `personal_learning_assistant/ui/web/static/css/app.css`
- Test `tests/test_phase7_5_obsidian_workspace.py`

- [ ] **1. Write RED template-content tests**

Disconnected page must contain:

```text
Obsidian
No vault connected
Connect Vault
```

Connected page must contain:

```text
Connected
Markdown notes
Search vault
Browse notes
```

Search result includes title, relative path, tags, excerpt, match scope, and Open note.

- [ ] **2. Implement status/connect UI**

Disconnected:

```text
Vault folder
[ C:/.../NIT KARNATAKA 2026-30 ]
[Connect Vault]
```

Connected:
- vault name
- configured path
- Markdown note count
- Enable/Disable
- Change vault

All config changes use POST forms.

- [ ] **3. Implement browse/search UI**

```text
Search your Obsidian vault
[ query ] [Search] [Clear]

Live vault search
Searches Markdown directly. It does not rebuild or change the ANVAYA knowledge index.
```

Rows show metadata and Open note.

- [ ] **4. Write RED XSS escaping test**

Seed:

```markdown
<script>alert("x")</script>
<img src=x onerror=alert(1)>
```

Rendered preview must contain escaped markup, not executable HTML.

- [ ] **5. Implement safe preview template**

Show title, relative path, tags/type/status, and:

```html
<pre class="obsidian-preview">{{ note.text }}</pre>
```

Never `|safe`. No edit/delete/create controls.

- [ ] **6. Add scoped CSS**

Add only Obsidian selectors such as:

```text
.obsidian-status
.obsidian-search
.obsidian-note-list
.obsidian-note-row
.obsidian-path
.obsidian-preview
.obsidian-warning
```

Reuse current ANVAYA tokens/components.

- [ ] **7. Run UI tests**

```powershell
python -m pytest -q tests/test_phase7_5_obsidian_workspace.py
```

---

## Task 5 — Read purity, lazy startup, security regression

**Files**
- Test `tests/test_phase7_5_obsidian_workspace.py`
- Modify existing Phase 7.5 tests only where endpoint/navigation assumptions changed

- [ ] **1. GET read-purity test**

Hash temporary:
- vault Markdown
- config JSON
- optional temp SQLite

Run:
- GET `/obsidian`
- GET `/obsidian?q=LU`
- GET `/obsidian/note?path=Math/LU.md`

All hashes must remain unchanged.

- [ ] **2. POST config-only mutation test**

Connect/enable/disable may change only temporary config. Markdown hashes unchanged. No SQLite/retrieval files created.

- [ ] **3. Lazy-startup subprocess test**

After `create_app({"TESTING": True})`, these must remain unloaded:

```python
for name in (
    "obsidian_integration",
    "personal_learning_assistant.repositories.filesystem.obsidian_workspace_reader",
    "personal_learning_assistant.repositories.filesystem.obsidian_vault_scanner",
):
    assert name not in sys.modules
```

The thin web-service module may be imported by routes only if it does not import config/scanner/reader eagerly.

- [ ] **4. Dependency-direction source scan**

`routes.py` must not directly contain:
- `obsidian_integration`
- `ObsidianVaultScanner`
- `SQLiteObsidianVaultRepository`
- `NotesStudioService`
- `AtomicMarkdownNoteStore`
- direct file reads

`obsidian_workspace_service.py` must not contain:
- `obsidian_menu`
- `input(`
- `print(`
- `ObsidianVaultRegistryService.apply`
- retrieval index builder calls
- Markdown write primitives

- [ ] **5. Explicit Review Focus tests**

Cover:
- traversal/absolute paths
- symlinks
- stale hash
- invalid/deleted vault
- unsafe HTML
- non-UTF8/unreadable note
- result caps
- safe error redaction

- [ ] **6. Run combined regression block**

```powershell
python -m pytest -q `
  tests/test_phase7_5_obsidian_workspace.py `
  tests/test_phase5_obsidian_vault_registry.py `
  tests/test_phase5_notes_studio_foundation.py `
  tests/test_phase7_5_web_foundation.py `
  tests/test_phase7_5_anvaya_shell.py `
  tests/test_phase7_5_anvaya_ux_refinement.py `
  tests/test_phase7_5_notes_resources.py `
  tests/test_phase7_5_operational_notes_resources.py `
  tests/test_phase7_5_knowledge_rag.py `
  tests/test_phase7_5_academic_agent_web.py
```

---

## Task 6 — Operator record + strict gate

**Files**
- Create `PHASE7_5_FIX12_OBSIDIAN_WORKSPACE_SEARCH.md`
- Create `phase7_5_fix12_gate.ps1`

- [ ] **1. Operator record**

Document:

```text
Phase: 7.5.12 — Obsidian Workspace + Search
Branch: main
Configuration authority: data/obsidian_config.json
Markdown authority: configured Obsidian vault
GET: status, browse, lexical search, preview
POST: connect/change, enable, disable
No Markdown writes
No registry apply
No Notes Studio command exposure
No RAG/index rebuild
No tutor source attachment
Next: 7.5.13 Tasks + Calendar Operations
```

- [ ] **2. Plan-derived baseline**

```powershell
$ExpectedBranch = "main"
$PlanPath = "docs/superpowers/plans/2026-09-19-phase7-5-12-obsidian-workspace-search.md"
$BaseCommitRaw = git log -1 --format=%H -- $PlanPath
if ([string]::IsNullOrWhiteSpace($BaseCommitRaw)) {
    Stop-Gate "The Phase 7.5.12 plan must be committed separately before the implementation gate runs."
}
$BaseCommit = $BaseCommitRaw.Trim()
```

Plan commit message:

```text
docs: add Phase 7.5.12 Obsidian workspace plan
```

- [ ] **3. Strict whitelist**

Allow only actual Phase 7.5.12 files:

```text
personal_learning_assistant/repositories/filesystem/obsidian_workspace_reader.py
personal_learning_assistant/services/obsidian_workspace_service.py
personal_learning_assistant/ui/web/routes.py
personal_learning_assistant/ui/web/templates/base.html
personal_learning_assistant/ui/web/templates/obsidian.html
personal_learning_assistant/ui/web/templates/obsidian_note.html
personal_learning_assistant/ui/web/static/css/app.css
tests/test_phase7_5_obsidian_workspace.py
tests/test_phase7_5_anvaya_shell.py
tests/test_phase7_5_web_foundation.py  # only if modified
PHASE7_5_FIX12_OBSIDIAN_WORKSPACE_SEARCH.md
phase7_5_fix12_gate.ps1
```

Exclude `__pycache__`, `.pyc`, `.pyo` from runtime tree hashes.

- [ ] **4. Capture production safety state**

Before tests hash:
- `data/learning_assistant.db`
- `.phase4_authority.json` if present
- all `data/*.json`, including `obsidian_config.json` if present
- `.phase5_retrieval/**`
- configured vault Markdown files when an enabled valid vault exists

The vault hash helper must exclude `.obsidian`, `.trash`, `.git`, `node_modules`, skip symlinks, and write any manifest only to a temp directory.

- [ ] **5. Ten gate stages**

```text
[1/10] Phase 7.5.12 focused Obsidian workspace tests
[2/10] Phase 5.3 Obsidian registry + Phase 5.4 Notes Studio regressions
[3/10] All Phase 7.5 web regressions
[4/10] Temporary-vault GET purity + traversal/symlink/XSS tests
[5/10] Temporary-config POST connect/enable/disable + PRG tests
[6/10] Phase 7.1–7.4 regressions
[7/10] Complete pytest suite with established historical Phase 2 deselection/rehearsal
[8/10] Python compile + pip check + SQLite integrity/FK checks
[9/10] Protected registry/Notes-Studio/retrieval/tutor hashes + dependency scan
[10/10] Scoped git diff + production JSON/SQLite/retrieval/vault Markdown reconciliation
```

- [ ] **6. Hash-protect existing foundations**

Protect:
- `obsidian_integration.py`
- Phase 5.3 scanner/service/SQLite repo
- Phase 5.4 Notes Studio service/store/repo
- retrieval tree
- tutor tree

- [ ] **7. Forbidden service scan**

`obsidian_workspace_service.py` must not contain direct Markdown write primitives such as:

```text
.write_text(
.write_bytes(
os.replace(
atomic_write(
move(
create_note(
update_note(
trash(
restore(
```

Reader may use `.read_bytes()` only.

- [ ] **8. Run full gate**

```powershell
powershell -ExecutionPolicy Bypass -File ./phase7_5_fix12_gate.ps1
```

Required final banner:

```text
PHASE 7.5.12 OBSIDIAN WORKSPACE + SEARCH: PASS
```

Do not commit on a partial pass.

---

## Task 7 — Final review + one implementation commit

- [ ] **1. Verify branch/scope**

```powershell
git status --short
git branch --show-current
git log --oneline -8
git diff --check
git diff --stat
```

Expected: `main`, HEAD is the separately committed Phase 7.5.12 plan, only whitelisted implementation files changed.

- [ ] **2. Review for hidden scope expansion**

No changes to:
- legacy Obsidian integration behavior
- Phase 5 scanner/registry
- Notes Studio mutation code
- SQLite migration/schema
- retrieval/RAG
- tutor actions
- Phase 7.5.11 Notes/Resources
- planning/assessment/calendar engines
- `main.py`
- production vault/data/config files

- [ ] **3. Rerun the full gate immediately before commit**

```powershell
powershell -ExecutionPolicy Bypass -File ./phase7_5_fix12_gate.ps1
```

Required:

```text
PHASE 7.5.12 OBSIDIAN WORKSPACE + SEARCH: PASS
```

- [ ] **4. Single implementation commit**

```powershell
git commit -m "feat: add Phase 7.5.12 Obsidian workspace and search"
```

- [ ] **5. Push + verify**

```powershell
git push origin main
git status
git log --oneline --decorate -6
```

Do not start Phase 7.5.13 until local/remote are aligned and the tree is clean.

---

## Expected User Experience

### Disconnected

```text
Obsidian

No vault connected.

Connect your Obsidian vault to browse and search Markdown inside ANVAYA.

Vault folder
[ C:/.../NIT KARNATAKA 2026-30 ]

[Connect Vault]
```

### Connected

```text
Obsidian                                      Connected

NIT KARNATAKA 2026-30
1,284 Markdown notes

[ Search your vault...                         ] [Search]

Live vault search
Searches Markdown directly. It does not rebuild the ANVAYA knowledge index.

Browse notes

LU Factorization
MA103N/Week 03/LU Factorization.md
#linear-algebra  #lu
[Open note]
```

### Search

```text
Search: LU factorization

2 matches

LU Factorization
MA103N/Week 03/LU Factorization.md
...elimination steps used in LU factorization...

MIT Lecture 4
MA103N/MIT 18.06/Lecture 04.md
...factorization A = LU...
```

### Preview

```text
← Back to Obsidian

LU Factorization
MA103N/Week 03/LU Factorization.md

Tags: #linear-algebra #lu
Type: concept
Status: needs practice

Markdown source
────────────────────────────────
# LU Factorization

A = LU
...
```

There is intentionally no Edit/Delete/Create control in this phase.

---

## Self-Review

- First-class Obsidian page: covered.
- Connect/change/enable/disable/status: covered.
- Browse/search/preview: covered.
- Direct live lexical search clearly separated from indexed RAG: covered.
- Path/symlink/XSS/stale-hash/unreadable safety: covered.
- Startup laziness: covered.
- Markdown authority unchanged: covered.
- SQLite registry unchanged: covered.
- Retrieval index unchanged: covered.
- Tutor integration deliberately deferred: explicit.
- Controlled Markdown writes deliberately deferred to Notes Studio/action layer: explicit.
- No placeholders or unspecified route/service signatures remain.

## Recommended Execution

Use **inline/native execution** again, matching Phase 7.5.11.

The work is sequential around one safety boundary (reader → service → routes → templates → gate), and strict temporary-vault tests plus production-vault hash reconciliation are more important here than splitting the implementation among multiple workers.
