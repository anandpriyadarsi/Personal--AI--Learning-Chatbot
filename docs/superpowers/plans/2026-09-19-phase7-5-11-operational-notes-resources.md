# Phase 7.5.11 Operational Notes + Resources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn ANVAYA Notes and Resources from read-only dashboard pages into safe daily-use workspaces for create/search/edit-status workflows while preserving the current authoritative storage models and existing CLI behavior.

**Architecture:** Add a web-facing operational service that wraps the existing non-interactive `NotesService` and `ResourceService`; web routes use GET for side-effect-free queries and POST + 303 redirect for safe writes. Notes gain a backward-compatible 1-based position for web editing and an atomic `replace_note` repository command while keeping the stored V1 four-field JSON shape; Resources reuse the existing position/update-status service. No SQLite/schema/RAG/Obsidian authority change occurs in this phase.

**Tech Stack:** Python 3.8+ compatible application code, Flask/Jinja, existing JSON repositories/services, pytest, PowerShell gates, local ANVAYA CSS only.

**Spec:** `docs/superpowers/specs/2026-09-17-anvaya-operational-dashboard-design.md`

## Global Constraints

- Repository authority is now `main`; do not recreate old phase branches unless the user explicitly asks.
- Start only after the Phase 7.5.10 UX refinement commit is clean and pushed.
- Preserve `data/notes.json` and `data/resources.json` as the authoritative stores used by the current Notes/Resources services during this phase.
- Do not write note bodies or resources into SQLite.
- Do not invoke `main.py`, CLI `input()`/`print()` functions, or terminal menus from Flask routes.
- GET requests remain side-effect free.
- Safe writes use POST and redirect with HTTP 303 after success.
- Do not add delete, trash, archive, bulk mutation, Obsidian write, RAG re-index, or external-calendar behavior in Phase 7.5.11.
- Preserve the legacy note JSON body shape exactly: `title`, `topic`, `difficulty`, `content`.
- Preserve the legacy resource JSON body shape exactly: `title`, `type`, `link`, `status`.
- Resource statuses remain exactly `Not Started`, `In Progress`, `Completed`.
- All write tests use temporary stores or injected fake services; the gate must prove production academic data and retrieval indexes are unchanged by tests.
- Browser errors expose safe messages only; raw paths, tracebacks, storage exceptions, and provider details remain server-side.
- Keep all UI dependencies local; no CDN/framework addition.
- This phase intentionally delivers the compatibility-safe operational core. Persistent note archive/trash, stable UUID note identity, Obsidian canonical bodies, and richer course/topic relations remain for the later Notes Studio/Obsidian modernization because the current four-field JSON authority has no lifecycle/identity fields.

## Review Focus

1. **Duplicate note titles:** editing must target a 1-based note position, not title text, so two notes with the same title cannot overwrite each other.
2. **Stale/out-of-range positions:** invalid note/resource positions must return a safe validation/not-found response and leave the store byte-for-byte unchanged.
3. **Malformed or zero-byte legacy JSON:** reads stay non-mutating; explicit create may initialize the legacy list exactly as existing services already do.
4. **Unsafe resource links:** `javascript:`/local paths stay plain text; only explicit HTTP(S) links become active anchors.
5. **Write failure during atomic replacement:** temporary files are cleaned up and the web layer must not claim success when the repository/service raises.

---

## File Structure

### Create

- `personal_learning_assistant/services/notes_resources_web_service.py` — operational web boundary, validation, workspace queries, safe write commands, lazy construction of existing services.
- `tests/test_phase7_5_operational_notes_resources.py` — Phase 7.5.11 service + route + persistence-safety contract.
- `PHASE7_5_FIX11_OPERATIONAL_NOTES_RESOURCES.md` — operator/completion record.
- `phase7_5_fix11_gate.ps1` — scoped completion gate.

### Modify

- `personal_learning_assistant/domain/note_models.py` — optional non-persisted `position` view field + update command/result.
- `personal_learning_assistant/repositories/interfaces.py` — `NoteRepository.replace_note(position, note)` protocol.
- `personal_learning_assistant/repositories/json/note_repository.py` — atomic replace operation preserving V1 shape.
- `personal_learning_assistant/services/notes_service.py` — list/search positions, `get_note`, `update_note`.
- `personal_learning_assistant/services/notes_resources_dashboard_service.py` — normalize note position and filtered operational result shapes without taking write responsibility.
- `personal_learning_assistant/ui/web/routes.py` — GET filters/search + explicit POST command routes.
- `personal_learning_assistant/ui/web/templates/notes.html` — create/search/edit workspace.
- `personal_learning_assistant/ui/web/templates/resources.html` — add/search/filter/status workspace.
- `personal_learning_assistant/ui/web/static/css/app.css` — shared operational form/action styles only.
- `tests/test_phase2_notes_service.py` — backward-compatible position/get/update coverage.
- `tests/test_phase2_notes_write_adapter.py` — repository replace-note persistence/atomicity coverage.
- `tests/test_phase7_5_notes_resources.py` — update prior read-only assumptions to preserve read safety while allowing explicit POSTs.

---

### Task 1: Add backward-compatible note identity-by-position and edit command

**Files:**
- Modify: `personal_learning_assistant/domain/note_models.py`
- Modify: `personal_learning_assistant/repositories/interfaces.py`
- Modify: `personal_learning_assistant/repositories/json/note_repository.py`
- Modify: `personal_learning_assistant/services/notes_service.py`
- Modify/Test: `tests/test_phase2_notes_service.py`
- Modify/Test: `tests/test_phase2_notes_write_adapter.py`

**Interfaces:**
- Consumes: existing `NoteView`, `CreateNoteCommand`, `NotesService`, `LegacyJsonNoteRepository`.
- Produces: `NoteView.position: int`, `UpdateNoteCommand(position, title, topic, difficulty, content)`, `NoteUpdateResult`, `NotesService.get_note(position)`, `NotesService.update_note(command)`, `NoteRepository.replace_note(position, note)`.

- [ ] **Step 1: Write failing tests for stable position on list/search/get**

Add tests asserting:

```python
result = service.list_notes()
assert [note.position for note in result.notes] == [1, 2, 3]
assert service.get_note(2).title == "Vector Spaces"
assert service.get_note(0) is None
assert service.get_note(99) is None

matches = service.search_notes(SearchNotesQuery(text="linear algebra"))
assert [note.position for note in matches.notes] == [1, 2]
```

Also keep the existing `note.to_legacy_dict()` equality assertions to prove `position` is never persisted.

- [ ] **Step 2: Run the focused tests and verify RED**

```powershell
python -m pytest -q `
  tests\test_phase2_notes_service.py::test_list_notes_exposes_nonpersisted_one_based_positions `
  tests\test_phase2_notes_service.py::test_get_note_uses_position_without_mutating_store `
  tests\test_phase2_notes_service.py::test_search_preserves_original_positions
```

Expected: fail because `NoteView.position` / `get_note` do not exist.

- [ ] **Step 3: Implement the minimal model/service position support**

Use this compatible shape:

```python
@dataclass(frozen=True)
class NoteView:
    title: str
    topic: str
    difficulty: str
    content: str
    position: int = 0

    @classmethod
    def from_legacy(cls, data, position=0):
        return cls(
            title=str(data.get("title", "")),
            topic=str(data.get("topic", "")),
            difficulty=str(data.get("difficulty", "")),
            content=str(data.get("content", "")),
            position=int(position or 0),
        )

    def to_legacy_dict(self):
        return {
            "title": self.title,
            "topic": self.topic,
            "difficulty": self.difficulty,
            "content": self.content,
        }
```

Change `list_notes()` to enumerate legacy rows starting at 1 before filtering. Add:

```python
def get_note(self, position: int):
    if position < 1:
        return None
    notes = self.list_notes().notes
    if position > len(notes):
        return None
    return notes[position - 1]
```

- [ ] **Step 4: Run focused position tests and verify GREEN**

Run the three tests above plus the full `tests/test_phase2_notes_service.py`.

- [ ] **Step 5: Write failing update/atomicity tests**

Add:

```python
def test_update_note_replaces_exact_position_and_preserves_v1_shape(tmp_path):
    ...
    result = service.update_note(UpdateNoteCommand(
        position=2,
        title="Vector Spaces revised",
        topic="Linear Algebra",
        difficulty="Medium",
        content="Updated body",
    ))
    assert result.note.position == 2
    assert json.loads(path.read_text(encoding="utf-8"))[1] == {
        "title": "Vector Spaces revised",
        "topic": "Linear Algebra",
        "difficulty": "Medium",
        "content": "Updated body",
    }
```

Also test duplicate titles, invalid positions preserving the file hash, and no leftover `.tmp` file.

- [ ] **Step 6: Run update tests and verify RED**

Expected: fail because update command/repository replacement do not exist.

- [ ] **Step 7: Implement atomic `replace_note` and service update**

Add `UpdateNoteCommand` and `NoteUpdateResult`. Add `replace_note(position, note)` to the protocol/repository using the same atomic temporary-file + `os.replace` strategy already used by `append_note`; factor a private save helper only if it reduces duplication without changing read behavior.

`NotesService.update_note()` must call `get_note(position)` first and raise:

```python
IndexError("Note position is out of range.")
```

before any write when invalid.

- [ ] **Step 8: Run all Phase 2 Notes tests**

```powershell
python -m pytest -q `
  tests\test_phase2_notes_service.py `
  tests\test_phase2_notes_write_adapter.py `
  tests\test_phase2_notes_cli_adapter.py `
  tests\test_phase2_repository_protocols.py
```

Expected: PASS with legacy CLI/create/list/search behavior unchanged.

---

### Task 2: Create the operational Notes + Resources web service boundary

**Files:**
- Create: `personal_learning_assistant/services/notes_resources_web_service.py`
- Modify: `personal_learning_assistant/services/notes_resources_dashboard_service.py`
- Test: `tests/test_phase7_5_operational_notes_resources.py`

**Interfaces:**
- Consumes: `NotesService`, `ResourceService`, current legacy repositories and typed command/query models.
- Produces: `NotesResourcesWebService`, `NotesResourcesWebValidationError`, `NotesResourcesWebUnavailableError`, and workspace/write methods used by Flask routes.

- [ ] **Step 1: Write failing tests for query workspaces**

Define the desired API:

```python
service.notes_workspace(search="lu", topic="", difficulty="")
service.resources_workspace(search="mit", resource_type="Course", status="")
```

Expected notes workspace keys:

```python
{
  "available": True,
  "query": {"search": "lu", "topic": "", "difficulty": ""},
  "summary": ...,
  "notes": [...],
}
```

Each note contains `position`; each resource retains `position` and safe `link_url` normalization.

Add a test proving blank Notes search lists all notes while an explicit nonblank search uses `NotesService.search_notes`; do not reuse the legacy CLI behavior of blank search returning zero results as the default Notes page behavior.

- [ ] **Step 2: Run focused tests and verify RED**

Expected: module/class not found.

- [ ] **Step 3: Implement lazy service construction + query normalization**

The factory must import these only when used:

```python
personal_learning_assistant.services.notes_service
personal_learning_assistant.services.resource_service
personal_learning_assistant.repositories.json.note_repository
personal_learning_assistant.repositories.json.resource_repository
```

Do not import `notes.py`, `resources.py`, `main.py`, RAG, or Obsidian modules.

- [ ] **Step 4: Write failing tests for safe write validation**

Desired methods:

```python
create_note(title, topic, difficulty, content)
update_note(position, title, topic, difficulty, content)
create_resource(title, resource_type, link)
update_resource_status(position, status)
```

Web validation rules:

- note title must contain non-whitespace;
- topic defaults to `Uncategorized` when blank;
- difficulty defaults to `Unspecified` when blank;
- note content may be blank;
- resource title must contain non-whitespace;
- resource type defaults to `Resource` when blank;
- resource link may be blank;
- status must be one of the existing canonical/alias values accepted by `ResourceService`;
- positive integer position required for updates.

Validation failures raise `NotesResourcesWebValidationError` before repository mutation.

- [ ] **Step 5: Implement minimal write methods and safe exception mapping**

Return the service results; do not duplicate repository logic. Map expected validation/index errors to web validation/not-found errors, and unexpected storage exceptions to `NotesResourcesWebUnavailableError` without exposing raw details.

- [ ] **Step 6: Run the full new service test block**

Expected: PASS, with temporary JSON hashes proving failed commands do not mutate stores.

---

### Task 3: Make Notes operational in Flask + Jinja

**Files:**
- Modify: `personal_learning_assistant/ui/web/routes.py`
- Modify: `personal_learning_assistant/ui/web/templates/notes.html`
- Modify: `personal_learning_assistant/ui/web/static/css/app.css`
- Test: `tests/test_phase7_5_operational_notes_resources.py`
- Modify/Test: `tests/test_phase7_5_notes_resources.py`

**Interfaces:**
- Consumes: `NotesResourcesWebService.notes_workspace`, `.create_note`, `.update_note`.
- Produces: GET `/notes`, POST `/notes`, POST `/notes/<int:position>`.

- [ ] **Step 1: Write failing route tests for GET search/filter**

Test:

```text
GET /notes?q=lu
GET /notes?topic=Linear+Algebra&difficulty=Hard
```

Assert the route passes exact query values to the injected web-service factory and renders selected filter values; GET must not call any write method.

- [ ] **Step 2: Implement query-aware GET `/notes`**

Keep `active_page="notes"`. Use request args `q`, `topic`, `difficulty` and render the returned workspace.

- [ ] **Step 3: Write failing POST create tests**

Assert:

- valid form calls `create_note` once and returns `303` to `/notes?created=1`;
- blank title returns `400` with a safe visible message and no redirect;
- raw injected backend exception text never appears in the response.

- [ ] **Step 4: Implement POST `/notes`**

Use exact form names:

```text
title
topic
difficulty
content
```

Do not use GET writes. Do not call the repository directly.

- [ ] **Step 5: Write failing POST edit tests**

Assert `POST /notes/2` calls `update_note(position=2, ...)`, returns 303 on success, and invalid/out-of-range position yields a safe 400/404 response without mutation.

- [ ] **Step 6: Implement edit route**

Do not add delete/archive routes in this phase.

- [ ] **Step 7: Replace the read-only Notes template with action-first UX**

Required UI:

```text
Notes                                      + New Note
Search [_________________] [Topic] [Difficulty] [Search]

<details New Note>
  title / topic / difficulty / content
  Save note
</details>

Note cards
  position badge / topic / difficulty
  content preview
  <details Edit> form prefilled from current note
```

Remove `Read only` and “This page does not create or edit notes.” copy.

Do not render an Archive/Delete button yet; the current authority has no compatible lifecycle field.

- [ ] **Step 8: Run Notes route/template tests**

Expected: create/search/edit behavior green and existing GET failure-degrade behavior preserved.

---

### Task 4: Make Resources operational in Flask + Jinja

**Files:**
- Modify: `personal_learning_assistant/ui/web/routes.py`
- Modify: `personal_learning_assistant/ui/web/templates/resources.html`
- Modify: `personal_learning_assistant/ui/web/static/css/app.css`
- Test: `tests/test_phase7_5_operational_notes_resources.py`
- Modify/Test: `tests/test_phase7_5_notes_resources.py`

**Interfaces:**
- Consumes: `NotesResourcesWebService.resources_workspace`, `.create_resource`, `.update_resource_status`.
- Produces: GET `/resources`, POST `/resources`, POST `/resources/<int:position>/status`.

- [ ] **Step 1: Write failing GET search/filter tests**

Use request args:

```text
q
type
status
```

Assert status/type filters survive rendering and GET never invokes create/update.

- [ ] **Step 2: Implement query-aware GET `/resources`**

Only HTTP(S) `link_url` values become anchors; local paths and unsafe schemes remain visible text.

- [ ] **Step 3: Write failing create/status POST tests**

Valid create:

```text
POST /resources
  title=MIT 18.06
  resource_type=Course
  link=https://ocw.mit.edu/
=> 303 /resources?created=1
```

Valid status update:

```text
POST /resources/1/status
  status=Completed
=> 303 /resources?updated=1
```

Invalid status/position returns safe 400/404 and does not mutate the temporary store.

- [ ] **Step 4: Implement resource POST routes**

Route code calls only the web service boundary, never `LegacyJsonResourceRepository` directly.

- [ ] **Step 5: Replace read-only Resources template with operational workspace**

Required UX:

```text
Resources                                  + Add Resource
Search [________] [Type] [Status] [Search]

<details Add Resource>
  title / type / link
  Add resource
</details>

Resource rows/cards
  title / type / status / safe open link
  status form: Not Started | In Progress | Completed
```

Remove `Read only` copy. Do not pretend a resource is indexed or tutor-grounded unless that evidence exists in the current model.

- [ ] **Step 6: Run Resources route/template tests**

Expected: PASS.

---

### Task 5: Regression, safety, UX, and lazy-startup compatibility

**Files:**
- Modify/Test: `tests/test_phase7_5_notes_resources.py`
- Test: `tests/test_phase7_5_operational_notes_resources.py`
- Production changes only if a real regression is discovered.

**Interfaces:**
- Consumes: operational services/routes/templates from Tasks 1-4.
- Produces: proof that explicit writes were added without turning reads/startup into mutation/eager import.

- [ ] **Step 1: Replace obsolete read-only assertions with explicit read/write boundary assertions**

Remove only assertions such as:

```python
assert '<form' not in text.lower()
assert '@web_blueprint.post("/notes")' not in source
```

Replace them with stronger contracts:

```python
assert client.get("/notes").status_code == 200
assert client.post("/notes", data=valid_note).status_code == 303
assert client.get("/notes", ... ) does not mutate temp file hash
assert routes source contains no direct repository imports
```

Keep existing safe-link, failure-degrade, lazy-startup and read-query purity tests.

- [ ] **Step 2: Add Review Focus tests**

Cover all five Review Focus items: duplicate titles, stale positions, malformed stores, unsafe links, repository write failures.

- [ ] **Step 3: Run all Notes/Resources + web regressions**

```powershell
python -m pytest -q `
  tests\test_phase2_notes_service.py `
  tests\test_phase2_notes_write_adapter.py `
  tests\test_phase2_notes_cli_adapter.py `
  tests\test_phase2_resources_service.py `
  tests\test_phase2_resources_cli_adapter.py `
  tests\test_phase7_5_notes_resources.py `
  tests\test_phase7_5_operational_notes_resources.py `
  tests\test_phase7_5_anvaya_shell.py `
  tests\test_phase7_5_anvaya_ux_refinement.py `
  tests\test_phase7_5_web_foundation.py
```

Expected: PASS.

- [ ] **Step 4: Manual local smoke test using disposable stores only**

Do not create test records in the production `data/notes.json` / `data/resources.json` merely to prove the phase. Use a test/injected app or copy the files to a temporary fixture when manual mutation proof is needed.

Then launch normal ANVAYA and verify existing production data renders correctly without automatic writes.

---

### Task 6: Add operator documentation and strict Phase 7.5.11 gate

**Files:**
- Create: `PHASE7_5_FIX11_OPERATIONAL_NOTES_RESOURCES.md`
- Create: `phase7_5_fix11_gate.ps1`

**Interfaces:**
- Consumes: completed Tasks 1-5.
- Produces: auditable phase closure and safe implementation commit boundary.

- [ ] **Step 1: Write operator documentation**

Document:

```text
Phase: 7.5.11 — Operational Notes + Resources
Branch: main
Notes operations: list/search/filter/create/edit by 1-based position
Resources operations: list/search/filter/create/update status
Safe writes: POST + 303
Authority: existing legacy Notes/Resources JSON services/repositories
No archive/delete/Obsidian/RAG/schema change
Next phase: 7.5.12 Obsidian Workspace + Search
```

Explicitly explain why note archive/trash is deferred: no stable lifecycle field exists in the current legacy note authority and inventing a parallel store would violate the approved storage-direction rules.

- [ ] **Step 2: Create the gate with a strict whitelist**

The gate runs on `main` and derives its base from the Phase 7.5.11 plan commit:

```powershell
$ExpectedBranch = "main"
$PlanPath = "docs/superpowers/plans/2026-09-19-phase7-5-11-operational-notes-resources.md"
$BaseCommit = (git log -1 --format=%H -- $PlanPath).Trim()
```

Whitelist only the files listed in this plan plus the operator doc/gate. Treat `__pycache__`, `.pyc`, `.pyo` as runtime artifacts and exclude them from protected-tree hashing.

- [ ] **Step 3: Gate stages**

Use ten stages:

```text
[1/10] Phase 7.5.11 focused operational tests
[2/10] Phase 2 Notes + Resources service/repository regressions
[3/10] All Phase 7.5 web regressions
[4/10] GET read-purity tests against temporary stores
[5/10] POST write tests against temporary stores + PRG/status validation
[6/10] Phase 7.1-7.4 regressions
[7/10] Complete pytest suite using the established Phase 2 legacy deselection/rehearsal pattern
[8/10] Python compile + pip check + SQLite integrity/FK checks
[9/10] Protected backend/authority/retrieval hashes + forbidden dependency-direction scan
[10/10] Scoped git diff + production data/retrieval-index hash reconciliation
```

Production-data hashes must include at least:

```text
data/learning_assistant.db
.phase4_authority.json when present
data/*.json
.phase5_retrieval/**
```

The gate must verify these are unchanged by the test run, even though the shipped web app now has explicit write endpoints.

Success banner:

```text
PHASE 7.5.11 OPERATIONAL NOTES + RESOURCES: PASS
```

- [ ] **Step 4: Run the complete gate from start to finish**

```powershell
powershell -ExecutionPolicy Bypass -File .\phase7_5_fix11_gate.ps1
```

If any stage fails, fix the root cause and rerun the whole gate. Do not commit on a partial pass.

---

### Task 7: Final review and one implementation commit

**Files:**
- Review all Phase 7.5.11 allowed files.
- No extra feature work.

**Interfaces:**
- Consumes: fully green Phase 7.5.11 gate.
- Produces: one scoped implementation commit on `main`.

- [ ] **Step 1: Verify clean starting commit relationship and scoped working tree**

```powershell
git status --short
git branch --show-current
git log --oneline -8
git diff --check
git diff --stat
```

Expected branch: `main`; only plan-approved Phase 7.5.11 files changed.

- [ ] **Step 2: Review the full diff for hidden scope expansion**

Confirm no changes to:

```text
SQLite migrations/schema
tutor/RAG/retrieval logic
Obsidian files
assessment/planning/calendar engines
main.py/CLI semantics except protocol compatibility required by note replace
production data files
```

- [ ] **Step 3: Create the single implementation commit**

After the plan itself has already been committed separately, stage only the allowed implementation files and commit:

```powershell
git commit -m "feat: add Phase 7.5.11 operational notes and resources"
```

- [ ] **Step 4: Push `main` and verify local/remote alignment**

```powershell
git push origin main
git status
git log --oneline --decorate -5
```

Do not start Phase 7.5.12 until the pushed commit is visible and the tree is clean.

---

## Self-Review Against the Approved Spec

- **Daily-use Notes/Resources:** create/search/edit/status operations are exposed through the browser.
- **Same service boundary:** Flask does not call CLI menus or repositories directly; operational web service delegates to existing application services.
- **Safe writes:** explicit POST only; 303 redirect after success; no destructive operation added.
- **Storage authority:** no second note/resource body store and no SQLite authority change.
- **Search:** Notes and Resources expose working filters/search using existing service semantics.
- **Edit:** Notes gain compatibility-safe replacement by 1-based position without persisting that position into the V1 note shape.
- **Archive/trash:** intentionally not faked; deferred because the present authority cannot represent lifecycle state safely.
- **Resources:** add/status/open/search are operational; unsafe links remain inactive.
- **Tutor integration:** no fake contextual grounding is added in this phase; unified tutor actions remain for the later action-layer/tutor phases.
- **Optional systems:** no Obsidian/RAG/provider dependency is introduced.
- **Review Focus:** all five risk cases are assigned concrete tests.
- **No placeholders:** implementation signatures, route names, form names, error behavior, gate stages, and commit boundaries are explicit.
