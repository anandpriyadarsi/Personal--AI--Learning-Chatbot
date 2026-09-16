# Phase 7.5.9 Academic Agent Web Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local Flask Academic Agent workspace that shows read-only Adaptive Mentor advice and supports persistent, source-grounded tutor conversations without exposing Phase 6.8 action execution.

**Architecture:** Add one browser-facing `AcademicAgentWebService` that composes existing Phase 6 mentor, tutor-session, grounded-tutor, retrieval, and provider boundaries. Flask routes depend only on this adapter. The only permitted writes are existing tutor session/turn/evidence rows, and all write-path tests run against isolated temporary database copies.

**Tech Stack:** Python 3.8-compatible code, Flask/Jinja2, SQLite, existing Phase 5.8 retrieval stack, existing Phase 6 tutor/mentor services, pytest, PowerShell gate scripts.

**Spec:** `docs/superpowers/specs/2026-09-17-phase7-5-9-academic-agent-web-design.md`

## Global Constraints

- Continue on branch `phase7/deprecation-observation` from the commit containing this plan; verify the exact HEAD before any implementation edit.
- Do not modify `main`.
- Do not expose or call `AcademicAgentService.execute()` from web production code.
- Mentor advice is advisory/read-only only; there is no browser action execution in Phase 7.5.9.
- Permitted production writes are restricted to `tutor_sessions`, `tutor_turns`, and `tutor_evidence_links`.
- Do not mutate mastery/progress, learning memory, study plans, grades, assessments, notes, resources, lecture state, practice state, retrieval indexes, or authority configuration.
- New tutor sessions default to `mode="concept"` and `source_policy="source_only"`; `source_first` is an explicit creation-time alternative.
- Course, mode, and source policy are fixed after session creation.
- `GET /agent`, `GET /agent?course=...`, and `GET /agent/sessions/<session_id>` are side-effect free and must not invoke the LLM.
- Only `POST /agent/sessions/<session_id>/ask` may invoke the tutor provider.
- Provider configuration remains `LLM_API_URL`, `LLM_API_KEY`, and `LLM_MODEL`; secrets must never be rendered or logged by the web adapter.
- The retrieval index is read-only; no indexing, ingestion, generation switch, or rebuild is allowed.
- Flask app creation remains lazy: importing/creating the app must not open SQLite, load retrieval indexes, or perform a network request.
- No WebSockets, streaming-token UI, SPA framework, background jobs, session delete/rename/complete/abandon controls, or tutor feedback controls in this phase.
- No implementation commit until the complete `phase7_5_fix9_gate.ps1` gate is green. Keep implementation changes uncommitted until the final gate passes; the final task performs the single scoped implementation commit.

---

## File Structure

**Create**
- `personal_learning_assistant/services/academic_agent_web_service.py` — lazy browser-facing orchestration, safe view models, read/write connection lifecycle, mentor/tutor composition.
- `personal_learning_assistant/ui/web/templates/agent.html` — Academic Agent landing page, mentor advice, recent sessions, provider status, session-creation form.
- `personal_learning_assistant/ui/web/templates/agent_session.html` — persisted transcript, support/evidence rendering, explicit ask form.
- `tests/test_phase7_5_academic_agent_web.py` — focused repository/service/route/security tests.
- `PHASE7_5_FIX9_ACADEMIC_AGENT_WEB.md` — implementation boundary and operator notes.
- `phase7_5_fix9_gate.ps1` — Windows completion gate.

**Modify**
- `personal_learning_assistant/repositories/sqlite/tutor_repository.py` — add bounded read-only `list_sessions(limit=20)`.
- `personal_learning_assistant/ui/web/routes.py` — add `/agent` routes behind one service factory boundary.
- `personal_learning_assistant/ui/web/templates/base.html` — activate Academic Agent navigation only.

**Protected**
- `personal_learning_assistant/services/grounded_tutor_service.py`
- `personal_learning_assistant/services/academic_agent_cutover_service.py`
- `personal_learning_assistant/services/adaptive_mentor_service.py`
- `personal_learning_assistant/tutor/*`
- `personal_learning_assistant/retrieval/*`
- `phase6_academic_agent.py`
- `phase6_grounded_tutor.py`
- `.phase5_retrieval/*`
- all prior Phase 7/7.5 completed artifacts except the explicitly modified shared web files above.

---

### Task 1: Add bounded recent-session reads to the tutor repository

**Files:**
- Modify: `personal_learning_assistant/repositories/sqlite/tutor_repository.py`
- Create/Test: `tests/test_phase7_5_academic_agent_web.py`

**Interfaces:**
- Consumes: existing `SQLiteTutorRepository.get_session(session_id: str) -> TutorSession`.
- Produces: `SQLiteTutorRepository.list_sessions(limit: int = 20) -> tuple[TutorSession, ...]`.

- [ ] **Step 1: Write the failing repository tests**

Add focused tests that create three tutor sessions with controlled timestamps using the existing repository/service and assert newest-first ordering and a hard bound:

```python
def test_tutor_repository_lists_recent_sessions_newest_first(tmp_path):
    connection = copied_learning_database(tmp_path)
    repo = SQLiteTutorRepository(connection)
    service = TutorSessionService(
        repo,
        now=iter([
            "2026-09-17T08:00:00Z",
            "2026-09-17T09:00:00Z",
            "2026-09-17T10:00:00Z",
        ]).__next__,
        id_factory=sequential_id_factory(),
    )
    course_id = first_course_id(connection)
    first = service.create_session(TutorSessionSpec(mode="concept", source_policy="source_only", course_id=course_id, title="First"))
    second = service.create_session(TutorSessionSpec(mode="doubt", source_policy="source_only", course_id=course_id, title="Second"))
    third = service.create_session(TutorSessionSpec(mode="exam", source_policy="source_first", course_id=course_id, title="Third"))

    rows = repo.list_sessions(limit=2)

    assert [row.session_id for row in rows] == [third.session_id, second.session_id]
    connection.close()


def test_tutor_repository_rejects_unbounded_session_limit(tmp_path):
    connection = copied_learning_database(tmp_path)
    repo = SQLiteTutorRepository(connection)
    with pytest.raises(ValueError, match="between 1 and 100"):
        repo.list_sessions(limit=101)
    connection.close()
```

The test module must define concrete helpers at the top:

```python
def copied_learning_database(tmp_path):
    source = Path("data/learning_assistant.db")
    target = tmp_path / "learning_assistant.db"
    shutil.copy2(source, target)
    connection = sqlite3.connect(str(target), isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def first_course_id(connection):
    row = connection.execute(
        "SELECT id FROM courses WHERE deleted_at IS NULL ORDER BY code, id LIMIT 1"
    ).fetchone()
    assert row is not None
    return str(row[0])


def sequential_id_factory():
    counter = itertools.count(1)
    return lambda prefix: "{}-{}".format(prefix, next(counter))
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_phase7_5_academic_agent_web.py::test_tutor_repository_lists_recent_sessions_newest_first `
  tests/test_phase7_5_academic_agent_web.py::test_tutor_repository_rejects_unbounded_session_limit
```

Expected: FAIL because `SQLiteTutorRepository` has no `list_sessions` method.

- [ ] **Step 3: Implement the minimal repository method**

Add this method next to `get_session`/`list_turns` without changing existing persistence behavior:

```python
def list_sessions(self, limit: int = 20):
    limit = int(limit)
    if limit < 1 or limit > 100:
        raise ValueError("session limit must be between 1 and 100")
    rows = self.connection.execute(
        "SELECT id FROM tutor_sessions "
        "ORDER BY updated_at DESC, created_at DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return tuple(self.get_session(str(row[0])) for row in rows)
```

- [ ] **Step 4: Run the two repository tests and verify GREEN**

Run the same command from Step 2.

Expected: `2 passed`.

- [ ] **Step 5: Checkpoint without committing**

Run:

```powershell
git diff -- personal_learning_assistant/repositories/sqlite/tutor_repository.py tests/test_phase7_5_academic_agent_web.py
```

Expected: only the new read method and its focused tests. Do not commit yet.

---

### Task 2: Build the lazy Academic Agent web orchestration boundary

**Files:**
- Create: `personal_learning_assistant/services/academic_agent_web_service.py`
- Modify/Test: `tests/test_phase7_5_academic_agent_web.py`

**Interfaces:**
- Consumes: `SQLiteTutorRepository`, `TutorSessionService`, `AdaptiveMentorService`, `KnowledgeNavigatorService`, `ExamIntelligenceService`, `RetrievalService`, `RetrievalIndexStore`, `OpenAICompatibleTutorProvider`, and the existing read-only course catalogue loader.
- Produces:
  - `AcademicAgentWebService.workspace(course_code: str = "") -> dict`
  - `AcademicAgentWebService.create_session(*, course_id: str, mode: str = "concept", source_policy: str = "source_only", title: str = "") -> str`
  - `AcademicAgentWebService.session_view(session_id: str) -> dict`
  - `AcademicAgentWebService.ask(session_id: str, question: str) -> dict`
  - `build_academic_agent_web_service() -> AcademicAgentWebService`
  - safe exceptions `AcademicAgentWebValidationError`, `AcademicAgentWebNotFoundError`, `AcademicAgentWebUnavailableError`.

- [ ] **Step 1: Write failing service tests for lazy startup and workspace reads**

Add tests with dependency injection so the test does not make a network request:

```python
def test_web_service_module_is_lazy_at_import():
    code = """
import sys
import personal_learning_assistant.services.academic_agent_web_service
for name in (
    'personal_learning_assistant.services.grounded_tutor_service',
    'personal_learning_assistant.services.adaptive_mentor_service',
    'personal_learning_assistant.retrieval.index_store',
    'personal_learning_assistant.tutor.http_provider',
):
    assert name not in sys.modules, name
"""
    completed = subprocess.run([sys.executable, "-c", code], check=False)
    assert completed.returncode == 0


def test_workspace_lists_courses_sessions_and_provider_status(tmp_path):
    service = build_test_web_service(tmp_path, provider=FakeProvider(configured=False))
    view = service.workspace("")
    assert view["available"] is True
    assert view["provider_configured"] is False
    assert view["courses"]
    assert isinstance(view["sessions"], list)
    assert view["mentor"] is None
```

`build_test_web_service` must point `database_path` at a copied temporary DB, accept a fake provider factory, and use the real course catalogue loader only when the test explicitly wants it; otherwise inject a deterministic course loader returning one known course.

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_phase7_5_academic_agent_web.py::test_web_service_module_is_lazy_at_import `
  tests/test_phase7_5_academic_agent_web.py::test_workspace_lists_courses_sessions_and_provider_status
```

Expected: FAIL because `academic_agent_web_service.py` does not exist.

- [ ] **Step 3: Implement a stdlib-only import surface and explicit database opener**

At module import time use only standard-library imports (`import_module`, `Path`, `sqlite3`, `quote`). Heavy project modules must be imported inside methods/builders.

Use a no-create SQLite opener copied from the established Phase 6 pattern rather than `connect_database()` because GETs must not change journal configuration:

```python
def _open_database(path, *, writable):
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise AcademicAgentWebUnavailableError(
            "Academic Agent storage is temporarily unavailable."
        )
    uri = "file:{}?mode={}".format(
        quote(str(path.resolve(strict=False)).replace("\\", "/"), safe="/:"),
        "rw" if writable else "ro",
    )
    connection = sqlite3.connect(
        uri,
        uri=True,
        isolation_level=None,
        timeout=5.0,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection
```

Do not use `mode=rwc` and do not create directories/files.

- [ ] **Step 4: Implement constructor and course/session view helpers**

Use explicit injectable factories:

```python
class AcademicAgentWebService:
    def __init__(
        self,
        *,
        database_path="data/learning_assistant.db",
        index_root=".phase5_retrieval",
        course_catalogue_loader=None,
        provider_factory=None,
    ):
        self.database_path = Path(database_path)
        self.index_root = Path(index_root)
        self._course_catalogue_loader = course_catalogue_loader
        self._provider_factory = provider_factory
```

Default dependencies are resolved lazily inside private methods. `workspace()` must:

1. read courses through the existing course catalogue boundary;
2. open the tutor DB in `mode=ro`;
3. read `SQLiteTutorRepository.list_sessions(limit=20)`;
4. instantiate the provider only to read `.configured` (no `.complete()` call);
5. if `course_code` is non-empty, construct the existing mentor graph over the same read-only connection and call `AdaptiveMentorService.advise(course_code)`;
6. normalize results to dictionaries for Jinja;
7. close the connection in `finally`.

Mentor construction must match existing Phase 6 wiring:

```python
navigator = KnowledgeNavigatorService(SQLiteKnowledgeNavigatorRepository(connection))
exam = ExamIntelligenceService(SQLiteExamIntelligenceRepository(connection))
mentor = AdaptiveMentorService(
    navigator_service=navigator,
    exam_intelligence_service=exam,
    evidence_repository=SQLiteAdaptiveMentorRepository(connection),
)
```

The returned workspace model must contain exactly these top-level keys:

```python
{
    "available": True,
    "message": "",
    "provider_configured": bool,
    "courses": [...],
    "selected_course_code": str,
    "mentor": None | {...},
    "sessions": [...],
    "modes": ["concept", "doubt", "summary", "exam", "lecture", "revision", "guidance", "free"],
    "source_policies": ["source_only", "source_first"],
}
```

- [ ] **Step 5: Implement session creation and session reads**

`create_session()` must open the DB writable, instantiate `SQLiteTutorRepository` + `TutorSessionService`, and call only:

```python
TutorSessionSpec(
    mode=str(mode or "concept").strip().casefold(),
    source_policy=str(source_policy or "source_only").strip().casefold(),
    course_id=str(course_id or "").strip() or None,
    title=str(title or "").strip(),
    metadata={"origin": "phase7.5.9_web"},
)
```

Return `session.session_id`. Translate `ValueError`, `TutorSessionError`, and repository validation errors into `AcademicAgentWebValidationError` with a safe message; do not include SQL or secret data.

`session_view(session_id)` must open read-only, call `get_session` and `transcript`, and normalize evidence to:

```python
{
    "citation_label": evidence.citation_label,
    "chunk_id": evidence.chunk_id,
    "document_id": evidence.document_id,
    "relation_type": evidence.relation_type,
    "retrieval_score": evidence.retrieval_score,
}
```

Translate a missing session into `AcademicAgentWebNotFoundError("Tutor session was not found.")`.

- [ ] **Step 6: Run the service read/create tests and verify GREEN**

Add and run tests covering `source_only` default, explicit `source_first`, invalid mode/policy/course, session history reopening, and mentor read-only output:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_phase7_5_academic_agent_web.py -k "repository or workspace or create_session or session_view or mentor"
```

Expected: all selected tests pass.

- [ ] **Step 7: Checkpoint without committing**

Run:

```powershell
git diff -- personal_learning_assistant/services/academic_agent_web_service.py personal_learning_assistant/repositories/sqlite/tutor_repository.py tests/test_phase7_5_academic_agent_web.py
```

Confirm there is no import/reference to `AcademicAgentService` or `academic_agent_cutover_service` in the new web service. Do not commit.

---

### Task 3: Add the grounded ask path with safe provider/retrieval failure mapping

**Files:**
- Modify: `personal_learning_assistant/services/academic_agent_web_service.py`
- Modify/Test: `tests/test_phase7_5_academic_agent_web.py`

**Interfaces:**
- Consumes: `GroundedTutorService.answer(session_id, question, top_k=None, max_chars=None)` and existing provider/retrieval classes.
- Produces: `AcademicAgentWebService.ask(session_id: str, question: str) -> dict` returning the refreshed session view after a successful or persisted insufficient-evidence answer.

- [ ] **Step 1: Write a failing fake-provider grounded-answer test**

Use an isolated copied DB and a deterministic retrieval double that returns at least one real `RetrievalHit`/evidence-compatible chunk ID present in that copied DB. Use a fake provider response containing `[S1]`:

```python
class FakeProvider:
    configured = True
    calls = 0

    def complete(self, request):
        self.calls += 1
        return TutorProviderResponse(
            content="LU factorization separates elimination into lower and upper triangular factors. [S1]",
            provider_name="fake-provider",
            provider_model="fake-model",
            request_id="fake-request-1",
        )
```

The test must assert after one `ask()`:

```python
assert fake_provider.calls == 1
roles = [turn["role"] for turn in view["turns"]]
assert roles[-2:] == ["user", "assistant"]
assert view["turns"][-1]["support_level"] == "grounded"
assert view["turns"][-1]["evidence"][0]["citation_label"] == "S1"
```

Also query the temporary DB directly and assert only tutor tables changed compared with a pre-call snapshot of per-table row counts.

- [ ] **Step 2: Write failing error-path tests before implementation**

Cover:

```python
def test_ask_rejects_blank_question(...): ...
def test_provider_unavailable_is_safe_and_does_not_persist_normal_turns(...): ...
def test_provider_request_failure_is_safe_and_does_not_persist_normal_turns(...): ...
def test_insufficient_evidence_persists_bounded_response_without_provider_call(...): ...
```

The safe messages must be exact:

- `AI tutor is not configured on this machine.`
- `The AI tutor could not complete this request. Your academic data was not changed.`
- `Grounded academic sources are temporarily unavailable.`

- [ ] **Step 3: Run the ask/error tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_phase7_5_academic_agent_web.py -k "ask or provider or insufficient"
```

Expected: FAIL because `ask()` is not implemented.

- [ ] **Step 4: Implement `ask()` by composing existing Phase 6 services**

Implementation sequence:

```python
question = str(question or "").strip()
if not question:
    raise AcademicAgentWebValidationError("Question cannot be empty.")

connection = _open_database(self.database_path, writable=True)
store = None
try:
    repository = SQLiteTutorRepository(connection)
    sessions = TutorSessionService(repository)
    session = repository.get_session(session_id)
    if session.status != "active":
        raise AcademicAgentWebValidationError("Tutor session is not active.")

    store = RetrievalIndexStore(self.index_root)
    retrieval = RetrievalService(store)
    provider = self._provider()
    engine = GroundedTutorService(
        tutor_session_service=sessions,
        retrieval_service=retrieval,
        provider=provider,
    )
    engine.answer(session_id, question)
finally:
    if store is not None:
        store.close()
    connection.close()
```

After the write connection closes, call `session_view(session_id)` to return a clean read-model.

For testability, permit an injected retrieval-service factory/provider factory, but keep the production default as the real `RetrievalIndexStore` + `RetrievalService` and `OpenAICompatibleTutorProvider`.

- [ ] **Step 5: Map known failures without leaking exception details**

Catch provider/retrieval classes only at the adapter boundary and rethrow safe web exceptions:

```python
except TutorProviderUnavailableError as error:
    raise AcademicAgentWebUnavailableError(
        "AI tutor is not configured on this machine."
    ) from error
except TutorProviderRequestError as error:
    raise AcademicAgentWebUnavailableError(
        "The AI tutor could not complete this request. Your academic data was not changed."
    ) from error
except (FileNotFoundError, RetrievalIndexError) as error:
    raise AcademicAgentWebUnavailableError(
        "Grounded academic sources are temporarily unavailable."
    ) from error
```

If the exact retrieval exception class differs, use the concrete existing Phase 5.8 exception class discovered during implementation; do not catch-and-display its message.

Do not catch the existing insufficient-evidence result as an error: `GroundedTutorService.answer()` already persists a safe assistant response without calling the provider when no evidence exists.

- [ ] **Step 6: Run the ask/error tests and verify GREEN**

Run the command from Step 3.

Expected: all selected tests pass and fake provider call counts match expectations.

- [ ] **Step 7: Verify the production DB and retrieval index were untouched by tests**

Run:

```powershell
git status --short
```

There must be no changes under `data/` or `.phase5_retrieval/`. Do not commit.

---

### Task 4: Add Flask routes and server-rendered Academic Agent pages

**Files:**
- Modify: `personal_learning_assistant/ui/web/routes.py`
- Modify: `personal_learning_assistant/ui/web/templates/base.html`
- Create: `personal_learning_assistant/ui/web/templates/agent.html`
- Create: `personal_learning_assistant/ui/web/templates/agent_session.html`
- Modify/Test: `tests/test_phase7_5_academic_agent_web.py`

**Interfaces:**
- Consumes: `build_academic_agent_web_service()` and the four public adapter methods from Tasks 2-3.
- Produces routes:
  - `GET /agent`
  - `POST /agent/sessions`
  - `GET /agent/sessions/<session_id>`
  - `POST /agent/sessions/<session_id>/ask`

- [ ] **Step 1: Write failing route tests with an injected fake web service**

Add a test service implementing the same four methods and set it through Flask config:

```python
app = create_app({
    "TESTING": True,
    "ACADEMIC_AGENT_WEB_SERVICE_FACTORY": lambda: fake_service,
})
client = app.test_client()
```

Tests must prove:

```python
assert client.get("/agent").status_code == 200
assert fake_service.llm_calls == 0
assert client.get("/agent?course=MA103N").status_code == 200
assert fake_service.llm_calls == 0

created = client.post("/agent/sessions", data={
    "course_id": "course-1",
    "mode": "concept",
    "source_policy": "source_only",
    "title": "LU Doubts",
})
assert created.status_code in {302, 303}

session_page = client.get("/agent/sessions/session-1")
assert session_page.status_code == 200

asked = client.post(
    "/agent/sessions/session-1/ask",
    data={"question": "Why does elimination produce L and U?"},
)
assert asked.status_code in {302, 303}
assert fake_service.ask_calls == 1
```

Also assert there is no `/agent/execute` route and `POST /agent` is 405.

- [ ] **Step 2: Run route tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_phase7_5_academic_agent_web.py -k "route or page or navigation"
```

Expected: FAIL because routes/templates do not exist and Academic Agent navigation is disabled.

- [ ] **Step 3: Add one lazy service factory helper to `routes.py`**

Import only the lightweight web adapter builder and add:

```python
def _academic_agent_service():
    factory = (
        current_app.config.get("ACADEMIC_AGENT_WEB_SERVICE_FACTORY")
        or build_academic_agent_web_service
    )
    return factory()
```

Never import `AcademicAgentService` or `academic_agent_cutover_service` here.

- [ ] **Step 4: Implement the four routes**

Use POST-Redirect-GET after successful writes:

```python
@web_blueprint.get("/agent")
def academic_agent():
    course_code = request.args.get("course", "", type=str)
    service = _academic_agent_service()
    try:
        workspace = service.workspace(course_code)
        return render_template("agent.html", active_page="agent", workspace=workspace)
    except Exception as error:
        current_app.logger.warning(
            "Academic Agent workspace unavailable (%s).", type(error).__name__
        )
        return render_template(
            "agent.html",
            active_page="agent",
            workspace={"available": False, "message": "Academic Agent is temporarily unavailable.", "courses": [], "sessions": [], "mentor": None, "provider_configured": False, "modes": [], "source_policies": []},
        ), 503
```

For creation and ask routes, catch the adapter's safe exception classes explicitly, render a safe message without the raw exception, and return `400`, `404`, or `503` as appropriate. On success redirect with `url_for("web.academic_agent_session", session_id=...)`.

- [ ] **Step 5: Build `agent.html`**

The page must contain:

- heading `Academic Agent`;
- provider status badge (`Configured` / `Not configured`);
- GET course selector for mentor advice;
- mentor topic/action cards with `Advisory only` text and no execute buttons/forms;
- recent sessions linking to `web.academic_agent_session`;
- new-session POST form with course, mode, source policy, optional title;
- `source_only` selected by default in the server-provided model/form fallback;
- explanatory text that creating a session does not call the LLM.

Do not render hidden fingerprint/confirmation fields.

- [ ] **Step 6: Build `agent_session.html`**

Render:

```jinja2
{% for turn in session.turns %}
  <article class="agent-turn agent-turn-{{ turn.role }}">
    <p class="eyebrow">{{ turn.role|capitalize }}</p>
    <div class="agent-message">{{ turn.content }}</div>
    {% if turn.role == 'assistant' %}
      <p>Support: {{ turn.support_level }}</p>
      {% if turn.provider_model %}<p>{{ turn.provider_name }} · {{ turn.provider_model }}</p>{% endif %}
      {% if turn.evidence %}
        <ul>
        {% for evidence in turn.evidence %}
          <li>{{ evidence.citation_label }} · document {{ evidence.document_id }} · chunk {{ evidence.chunk_id }}</li>
        {% endfor %}
        </ul>
      {% endif %}
    {% endif %}
  </article>
{% endfor %}
```

The ask form must be POST-only and available only for `session.status == "active"`.

- [ ] **Step 7: Activate sidebar navigation**

Replace the disabled span with:

```jinja2
<a class="nav-item{% if active_page == 'agent' %} is-active{% endif %}" href="{{ url_for('web.academic_agent') }}">Academic Agent</a>
```

No other navigation item changes.

- [ ] **Step 8: Run route/template tests and verify GREEN**

Run the command from Step 2.

Expected: all selected tests pass.

- [ ] **Step 9: Checkpoint without committing**

Run:

```powershell
git diff -- `
  personal_learning_assistant/ui/web/routes.py `
  personal_learning_assistant/ui/web/templates/base.html `
  personal_learning_assistant/ui/web/templates/agent.html `
  personal_learning_assistant/ui/web/templates/agent_session.html
```

Confirm there is no browser execution control and no secret-bearing HTML. Do not commit.

---

### Task 5: Complete focused safety/integration tests

**Files:**
- Modify/Test: `tests/test_phase7_5_academic_agent_web.py`
- Modify if required by a demonstrated test defect only: the Task 1-4 scoped production files.

**Interfaces:**
- Verifies all public behavior from Tasks 1-4.

- [ ] **Step 1: Add source-policy immutability and session-reopen tests**

Create a session as `source_first`, reopen it, and assert stored mode/policy/course are unchanged. Attempting to POST altered mode/policy fields to the ask route must have no effect because the ask route accepts only `question`.

- [ ] **Step 2: Add explicit no-execution source inspection test**

Read production web source files and assert they do not contain forbidden execution APIs:

```python
def test_web_production_code_has_no_phase68_execution_path():
    sources = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in (
            "personal_learning_assistant/services/academic_agent_web_service.py",
            "personal_learning_assistant/ui/web/routes.py",
            "personal_learning_assistant/ui/web/templates/agent.html",
            "personal_learning_assistant/ui/web/templates/agent_session.html",
        )
    )
    forbidden = (
        "AcademicAgentService",
        ".execute(",
        "EXECUTE_ACADEMIC_AGENT_ACTION",
        "practice_quiz",
        "lecture_learning",
        "/execute",
    )
    for token in forbidden:
        assert token not in sources
```

If a harmless explanatory string would trip this test, remove the ambiguous string from production UI rather than weakening the execution boundary assertion.

- [ ] **Step 3: Add app-startup isolation test**

Use a subprocess to create the Flask app and assert Phase 6 tutor/provider/retrieval modules are still absent from `sys.modules`, no files appear in an empty temporary current directory, and no environment-dependent provider call occurs.

- [ ] **Step 4: Add production-data immutability tests around GET routes**

Hash `data/learning_assistant.db` and all files below `.phase5_retrieval` before and after real `GET /agent` and a read-only real session GET. Assert hashes are identical.

- [ ] **Step 5: Add isolated mutation-table accounting test**

On a copied temporary DB, snapshot row counts for every non-SQLite table before and after session creation + one fake-provider grounded answer. Assert the changed-table set is a subset of:

```python
{"tutor_sessions", "tutor_turns", "tutor_evidence_links"}
```

and assert at least the expected tutor tables changed. `tutor_feedback` must not change.

- [ ] **Step 6: Run the full focused file**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_phase7_5_academic_agent_web.py
```

Expected: all Phase 7.5.9 focused tests pass.

- [ ] **Step 7: Run relevant Phase 6 regression tests**

Run the repository's existing Phase 6 tutor, mentor, and Academic Agent tests discovered by filename during execution, plus:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests -k "phase6 and (tutor or mentor or academic_agent)"
```

Expected: all selected existing tests pass. If `-k` selects nothing because filenames/ids differ, run the exact discovered Phase 6 test files instead; do not treat zero collected tests as success.

- [ ] **Step 8: Checkpoint without committing**

Run:

```powershell
git status --short
```

Only the Phase 7.5.9 scoped files may be modified/untracked. Do not commit.

---

### Task 6: Write Phase 7.5.9 implementation notes and Windows completion gate

**Files:**
- Create: `PHASE7_5_FIX9_ACADEMIC_AGENT_WEB.md`
- Create: `phase7_5_fix9_gate.ps1`
- Modify/Test if necessary: `tests/test_phase7_5_academic_agent_web.py`

**Interfaces:**
- Produces the operator-facing completion contract and authoritative Windows gate.

- [ ] **Step 1: Write the implementation note**

Document these exact sections:

```markdown
# Phase 7.5.9 — Academic Agent Web Interface

## Objective
## Browser surface
## Architecture boundary
## Tutor persistence boundary
## Source policy
## Provider behavior
## Explicitly excluded Phase 6.8 execution
## Failure behavior
## Verification gate
```

State explicitly that only tutor session/turn/evidence state may be written, the Adaptive Mentor is advisory only, Source Only is the default, Source First is opt-in at session creation, and action execution is deferred.

- [ ] **Step 2: Create the gate header and scope checks**

`phase7_5_fix9_gate.ps1` must:

- require branch `phase7/deprecation-observation`;
- capture the implementation starting commit as the exact HEAD that contains this plan and no production implementation edits;
- allow changes only in these nine implementation files:

```text
personal_learning_assistant/services/academic_agent_web_service.py
personal_learning_assistant/repositories/sqlite/tutor_repository.py
personal_learning_assistant/ui/web/routes.py
personal_learning_assistant/ui/web/templates/base.html
personal_learning_assistant/ui/web/templates/agent.html
personal_learning_assistant/ui/web/templates/agent_session.html
tests/test_phase7_5_academic_agent_web.py
PHASE7_5_FIX9_ACADEMIC_AGENT_WEB.md
phase7_5_fix9_gate.ps1
```

The already committed spec and plan files are part of the base and must not appear as implementation changes.

- [ ] **Step 3: Add production immutability hashing**

Before tests, hash:

- `data/learning_assistant.db`;
- `.phase4_authority.json` if present;
- every file below `.phase5_retrieval`;
- existing legacy `data/*.json` files.

After all tests, recompute hashes and fail if any differ. Tests that validate writes must use a temporary copied DB only.

- [ ] **Step 4: Add the ten gate stages**

Use these stages and fail-fast behavior:

```text
[1/10] Phase 7.5.9 focused tests
[2/10] Lazy app startup + provider-unconfigured smoke test
[3/10] Real GET-only Academic Agent/session read smoke tests
[4/10] Isolated tutor-session + fake-provider grounded-answer persistence
[5/10] Phase 7.5.1-7.5.8 web regressions
[6/10] Phase 7.1-7.4 regressions
[7/10] Complete pytest suite
[8/10] Python compilation + pip check + SQLite integrity/FK checks
[9/10] Protected execution/retrieval/Phase 6 file hashes + forbidden source scan
[10/10] Scoped Git diff + production-data hash reconciliation
```

The stage 4 temporary DB check must compare table counts and reject any changed table outside `tutor_sessions`, `tutor_turns`, and `tutor_evidence_links`.

The stage 9 forbidden source scan must reject `AcademicAgentService`, `EXECUTE_ACADEMIC_AGENT_ACTION`, and a callable `.execute(` reference in the new web production files.

- [ ] **Step 5: Define exact PASS output**

The successful gate must end with:

```text
==================================================
 PHASE 7.5.9 ACADEMIC AGENT WEB: PASS
==================================================
Mentor advice is advisory/read-only.
Tutor conversations persist only in tutor session/turn/evidence state.
Source Only is the default; Source First is explicit opt-in.
No Phase 6.8 action execution is exposed in the browser.
Production academic data and retrieval indexes were unchanged by the gate.
Phase 7.5.9 is ready for review and commit.
```

- [ ] **Step 6: Run the focused gate once**

Run:

```powershell
.\phase7_5_fix9_gate.ps1
```

Expected: if any stage fails, stop and fix only that demonstrated failure. Do not commit.

---

### Task 7: Full verification and the single scoped implementation commit

**Files:**
- Verify all nine implementation-scope files from Task 6.
- Do not change the committed spec/plan unless implementation reveals a genuine design contradiction requiring explicit review.

**Interfaces:**
- Produces the gate-green Phase 7.5.9 implementation commit.

- [ ] **Step 1: Run the complete Phase 7.5.9 gate from a clean staging area**

Run:

```powershell
git reset
.\phase7_5_fix9_gate.ps1
```

Expected: all ten stages pass and the exact PASS banner appears.

- [ ] **Step 2: Inspect final scope before staging**

Run:

```powershell
git status --short
git diff --check
```

Expected: only the nine implementation files listed in Task 6 are changed/untracked; no whitespace errors.

- [ ] **Step 3: Stage only the Phase 7.5.9 implementation scope**

Run:

```powershell
git add `
  personal_learning_assistant/services/academic_agent_web_service.py `
  personal_learning_assistant/repositories/sqlite/tutor_repository.py `
  personal_learning_assistant/ui/web/routes.py `
  personal_learning_assistant/ui/web/templates/base.html `
  personal_learning_assistant/ui/web/templates/agent.html `
  personal_learning_assistant/ui/web/templates/agent_session.html `
  tests/test_phase7_5_academic_agent_web.py `
  PHASE7_5_FIX9_ACADEMIC_AGENT_WEB.md `
  phase7_5_fix9_gate.ps1

git diff --cached --name-only
git diff --cached --check
```

Expected: exactly nine paths, no diff-check output.

- [ ] **Step 4: Re-run the gate if staging changes gate assumptions**

If the gate requires no staged changes, unstage, rerun, then restage exactly as Step 3. Do not weaken the gate to accommodate staging.

- [ ] **Step 5: Commit once**

Run:

```powershell
git commit -m "feat: add Phase 7.5.9 Academic Agent web interface"
```

- [ ] **Step 6: Push and verify remote synchronization**

Run:

```powershell
git push origin phase7/deprecation-observation
git status --short
git rev-parse HEAD
git ls-remote origin refs/heads/phase7/deprecation-observation
```

Expected: working tree clean and local/remote SHAs identical.

---

## Self-Review Record

- **Spec coverage:** every approved design section maps to Tasks 1-7: session history, lazy web orchestration, persistent grounding, source-policy defaults, mentor advice, web UI, safe failures, no Phase 6.8 execution, isolated write testing, documentation, and final gate.
- **Placeholder scan:** no `TBD`, `TODO`, or deferred implementation placeholder remains. The gate captures its implementation-base SHA from the verified plan-containing HEAD at execution time because the SHA cannot be known before this plan commit exists; the final handoff supplies that concrete SHA.
- **Type consistency:** repository output is `TutorSession`; service methods consistently expose dictionary view models; Flask routes consume only `AcademicAgentWebService.workspace/create_session/session_view/ask`; source policies and tutor modes match the existing domain constants.
- **Scope check:** this plan remains one coherent subsystem—the Phase 7.5.9 browser surface over existing Phase 5/6 services. Confirmed action execution remains explicitly deferred and is not part of this plan.
