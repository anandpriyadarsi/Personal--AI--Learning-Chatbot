from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import textwrap
from copy import deepcopy
from pathlib import Path

import pytest
from markupsafe import Markup

from personal_learning_assistant.repositories.filesystem.obsidian_workspace_reader import (
    ObsidianWorkspaceReader,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import (
    apply_migrations,
)
from personal_learning_assistant.repositories.sqlite.obsidian_study_repository import (
    SQLiteObsidianStudyRepository,
)
from personal_learning_assistant.services.obsidian_study_companion_service import (
    ObsidianStudyCompanionService,
    ObsidianStudyConflictError,
    ObsidianStudyNotFoundError,
    ObsidianStudyUnavailableError,
    ObsidianStudyValidationError,
)
from personal_learning_assistant.services.obsidian_workspace_service import (
    ObsidianWorkspaceNotFoundError,
    ObsidianWorkspaceService,
    ObsidianWorkspaceUnavailableError,
    ObsidianWorkspaceValidationError,
)
from personal_learning_assistant.ui.web import create_app


ROOT = Path(__file__).resolve().parents[1]
SOURCE_HASH = "b" * 64


def _reader_view(**changes):
    view = {
        "title": "LU Factorization",
        "relative_path": "Math/LU.md",
        "assistant_id": "11111111-1111-4111-8111-111111111111",
        "vault_name": "My Vault",
        "vault_identity": "vault:" + "a" * 64,
        "note_identity": "assistant:11111111-1111-4111-8111-111111111111",
        "tags": ["linear-algebra"],
        "note_type": "concept",
        "revision_status": "needs_practice",
        "source_hash": SOURCE_HASH,
        "size_bytes": 321,
        "text": '# Raw\n<script>alert("x")</script>\n**source**',
        "rendered_html": Markup(
            '<h1>Rendered LU</h1><p><strong>Readable</strong> note.</p>'
        ),
        "open_in_obsidian_url": (
            "obsidian://open?vault=My+Vault&file=Math%2FLU.md"
        ),
        "history": {
            "times_opened": 2,
            "last_read_at": "2026-09-19T14:00:00Z",
            "total_active_seconds": 125,
            "last_session_active_seconds": 35,
            "max_scroll_bps": 7300,
            "recent_sessions": (
                {
                    "id": "44444444-4444-4444-8444-444444444444",
                    "started_at": "2026-09-19T14:00:00Z",
                    "ended_at": "2026-09-19T14:00:35Z",
                    "active_seconds": 35,
                    "max_scroll_bps": 7300,
                },
            ),
        },
        "companion": {
            "available": True,
            "message": "",
            "key_points": (
                {
                    "id": "55555555-5555-4555-8555-555555555555",
                    "entry_text": "L is lower triangular.",
                    "created_at": "2026-09-19T14:10:00Z",
                },
            ),
            "doubts": (
                {
                    "id": "66666666-6666-4666-8666-666666666666",
                    "entry_text": "Why pivot?",
                    "created_at": "2026-09-19T14:11:00Z",
                },
            ),
        },
    }
    view.update(changes)
    return view


class FakeStudyService:
    def __init__(self):
        self.calls = []
        self.view = _reader_view()

    def reader_view(self, relative_path):
        self.calls.append(("reader", relative_path))
        return deepcopy(self.view)

    def start_reading(self, **values):
        self.calls.append(("start", values))
        return {
            "session_id": "44444444-4444-4444-8444-444444444444",
            "active_seconds": 0,
            "max_scroll_bps": 0,
            "accepted": True,
            "ended_at": None,
        }

    def heartbeat(self, **values):
        self.calls.append(("heartbeat", values))
        return {
            "session_id": values["session_id"],
            "active_seconds": 30,
            "max_scroll_bps": values["scroll_bps"],
            "accepted": True,
            "ended_at": None,
        }

    def end_reading(self, **values):
        self.calls.append(("end", values))
        return {
            "session_id": values["session_id"],
            "active_seconds": values["delta_seconds"],
            "max_scroll_bps": values["scroll_bps"],
            "accepted": True,
            "ended_at": "2026-09-19T15:00:00Z",
        }

    def add_companion_entry(self, **values):
        self.calls.append(("add", values))
        return {"id": "77777777-7777-4777-8777-777777777777"}

    def archive_companion_entry(self, **values):
        self.calls.append(("archive", values))
        return {"id": values["entry_id"]}


def _client(service):
    app = create_app(
        {
            "TESTING": True,
            "OBSIDIAN_STUDY_SERVICE_FACTORY": lambda: service,
        }
    )
    return app.test_client()


def _client_with_study_factory(factory):
    app = create_app(
        {
            "TESTING": True,
            "OBSIDIAN_STUDY_SERVICE_FACTORY": factory,
        }
    )
    return app.test_client()


def test_reader_get_renders_markdown_by_default_and_escaped_collapsed_source():
    service = FakeStudyService()
    response = _client(service).get("/obsidian/note?path=Math%2FLU.md")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert service.calls == [("reader", "Math/LU.md")]
    assert "<h1>Rendered LU</h1>" in html
    assert "<strong>Readable</strong>" in html
    assert '<script>alert("x")</script>' not in html
    assert "&lt;script&gt;alert" in html
    assert '<details class="obsidian-source"' in html
    source_opening = html.split('<details class="obsidian-source"', 1)[1].split(
        ">", 1
    )[0]
    assert "open" not in source_opening
    assert "Open in Obsidian" in html
    assert "obsidian://open?vault=My+Vault&amp;file=Math%2FLU.md" in html
    assert "ANVAYA Companion" in html
    assert "L is lower triangular." in html
    assert "Why pivot?" in html
    assert "125 seconds" in html
    assert "73%" in html
    assert 'maxlength="2000"' in html
    assert "obsidian_reader.js" in html
    assert "Reading-time tracking requires JavaScript" in html


def test_reader_get_still_renders_when_companion_database_is_unavailable():
    service = FakeStudyService()
    service.view = _reader_view(
        history={
            "times_opened": 0,
            "last_read_at": None,
            "total_active_seconds": 0,
            "last_session_active_seconds": 0,
            "max_scroll_bps": 0,
            "recent_sessions": (),
        },
        companion={
            "available": False,
            "message": "Study history and Companion are temporarily unavailable.",
            "key_points": (),
            "doubts": (),
        },
    )

    response = _client(service).get("/obsidian/note?path=Math%2FLU.md")

    assert response.status_code == 200
    assert "<h1>Rendered LU</h1>" in response.get_data(as_text=True)
    assert "Study history and Companion are temporarily unavailable." in response.get_data(
        as_text=True
    )


@pytest.mark.parametrize(
    ("error", "status"),
    (
        (ObsidianWorkspaceValidationError("SECRET"), 400),
        (ObsidianWorkspaceNotFoundError("SECRET"), 404),
        (ObsidianWorkspaceUnavailableError("SECRET"), 503),
        (ObsidianStudyValidationError("SECRET"), 400),
        (ObsidianStudyNotFoundError("SECRET"), 404),
        (ObsidianStudyConflictError("SECRET"), 409),
        (ObsidianStudyUnavailableError("SECRET"), 503),
    ),
)
def test_reader_get_maps_safe_errors_without_backend_details(error, status):
    class BrokenService(FakeStudyService):
        def reader_view(self, _relative_path):
            raise error

    response = _client(BrokenService()).get("/obsidian/note?path=Math%2FLU.md")

    assert response.status_code == status
    assert "SECRET" not in response.get_data(as_text=True)


def test_reader_get_maps_service_factory_failure_to_safe_503():
    def broken_factory():
        raise RuntimeError("C:/SECRET/backend initialization")

    response = _client_with_study_factory(broken_factory).get(
        "/obsidian/note?path=Math%2FLU.md"
    )

    assert response.status_code == 503
    assert "SECRET" not in response.get_data(as_text=True)


def test_tracking_json_routes_call_service_and_return_small_contracts():
    service = FakeStudyService()
    client = _client(service)
    start = client.post(
        "/obsidian/note/reading/start",
        json={"path": "Math/LU.md", "source_hash": SOURCE_HASH},
    )
    heartbeat = client.post(
        "/obsidian/note/reading/heartbeat",
        json={
            "path": "Math/LU.md",
            "source_hash": SOURCE_HASH,
            "session_id": "44444444-4444-4444-8444-444444444444",
            "sequence": 1,
            "delta_seconds": 30,
            "scroll_bps": 4200,
        },
    )
    end = client.post(
        "/obsidian/note/reading/end",
        json={
            "path": "Math/LU.md",
            "source_hash": SOURCE_HASH,
            "session_id": "44444444-4444-4444-8444-444444444444",
            "sequence": 2,
            "delta_seconds": 35,
            "replayed_delta_seconds": 30,
            "scroll_bps": 5000,
        },
    )

    assert start.status_code == 201
    assert start.get_json()["ok"] is True
    assert start.get_json()["session_id"].startswith("44444444")
    assert heartbeat.status_code == 200
    assert heartbeat.get_json() == {
        "ok": True,
        "session_id": "44444444-4444-4444-8444-444444444444",
        "active_seconds": 30,
        "max_scroll_bps": 4200,
        "accepted": True,
        "ended_at": None,
    }
    assert end.status_code == 200
    assert end.get_json()["ended_at"] == "2026-09-19T15:00:00Z"
    assert [item[0] for item in service.calls] == ["start", "heartbeat", "end"]
    assert service.calls[-1][1]["replayed_delta_seconds"] == 30


@pytest.mark.parametrize(
    ("payload", "content_type"),
    ((None, None), ({"path": "Math/LU.md"}, "application/json")),
)
def test_tracking_route_rejects_missing_or_malformed_json(payload, content_type):
    service = FakeStudyService()
    client = _client(service)
    if payload is None:
        response = client.post(
            "/obsidian/note/reading/start",
            data="not-json",
            content_type="text/plain",
        )
    else:
        response = client.post(
            "/obsidian/note/reading/start",
            data=json.dumps(payload),
            content_type=content_type,
        )

    assert response.status_code == 400
    assert response.get_json() == {"ok": False, "error": "invalid_request"}


@pytest.mark.parametrize(
    ("error", "status", "code"),
    (
        (ObsidianStudyValidationError("C:/SECRET"), 400, "invalid_request"),
        (ObsidianStudyNotFoundError("C:/SECRET"), 404, "not_found"),
        (ObsidianStudyConflictError("C:/SECRET"), 409, "conflict"),
        (ObsidianStudyUnavailableError("C:/SECRET"), 503, "unavailable"),
    ),
)
def test_tracking_route_maps_service_errors_to_redacted_json(error, status, code):
    class BrokenService(FakeStudyService):
        def heartbeat(self, **values):
            raise error

    response = _client(BrokenService()).post(
        "/obsidian/note/reading/heartbeat",
        json={
            "path": "Math/LU.md",
            "source_hash": SOURCE_HASH,
            "session_id": "44444444-4444-4444-8444-444444444444",
            "sequence": 1,
            "delta_seconds": 30,
            "scroll_bps": 1,
        },
    )

    assert response.status_code == status
    assert response.get_json() == {"ok": False, "error": code}
    assert "SECRET" not in response.get_data(as_text=True)


@pytest.mark.parametrize(
    ("endpoint", "payload"),
    (
        (
            "/obsidian/note/reading/start",
            {"path": "Math/LU.md", "source_hash": SOURCE_HASH},
        ),
        (
            "/obsidian/note/reading/heartbeat",
            {
                "path": "Math/LU.md",
                "source_hash": SOURCE_HASH,
                "session_id": "44444444-4444-4444-8444-444444444444",
                "sequence": 1,
                "delta_seconds": 30,
                "scroll_bps": 100,
            },
        ),
        (
            "/obsidian/note/reading/end",
            {
                "path": "Math/LU.md",
                "source_hash": SOURCE_HASH,
                "session_id": "44444444-4444-4444-8444-444444444444",
                "sequence": 2,
                "delta_seconds": 0,
                "scroll_bps": 100,
            },
        ),
    ),
)
def test_tracking_routes_map_service_factory_failure_to_safe_json(endpoint, payload):
    def broken_factory():
        raise RuntimeError("C:/SECRET/backend initialization")

    response = _client_with_study_factory(broken_factory).post(
        endpoint,
        json=payload,
    )

    assert response.status_code == 503
    assert response.get_json() == {"ok": False, "error": "unavailable"}
    assert "SECRET" not in response.get_data(as_text=True)


def test_companion_forms_use_post_303_and_preserve_note_path():
    service = FakeStudyService()
    client = _client(service)
    key_point = client.post(
        "/obsidian/note/companion/key-points",
        data={
            "path": "Math/LU.md",
            "source_hash": SOURCE_HASH,
            "entry_text": "L is triangular.",
        },
    )
    doubt = client.post(
        "/obsidian/note/companion/doubts",
        data={
            "path": "Math/LU.md",
            "source_hash": SOURCE_HASH,
            "entry_text": "Why pivot?",
        },
    )
    archived = client.post(
        "/obsidian/note/companion/55555555-5555-4555-8555-555555555555/archive",
        data={"path": "Math/LU.md", "source_hash": SOURCE_HASH},
    )

    assert [key_point.status_code, doubt.status_code, archived.status_code] == [
        303,
        303,
        303,
    ]
    assert "path=Math/LU.md" in key_point.headers["Location"]
    assert "companion_saved=key_point" in key_point.headers["Location"]
    assert "companion_saved=doubt" in doubt.headers["Location"]
    assert "companion_saved=archived" in archived.headers["Location"]
    assert [item[0] for item in service.calls] == ["add", "add", "archive"]
    assert service.calls[0][1]["entry_type"] == "key_point"
    assert service.calls[1][1]["entry_type"] == "doubt"


def test_companion_form_error_is_safe_and_does_not_redirect_raw_text():
    class BrokenService(FakeStudyService):
        def add_companion_entry(self, **values):
            raise ObsidianStudyValidationError("C:/SECRET " + values["entry_text"])

    response = _client(BrokenService()).post(
        "/obsidian/note/companion/doubts",
        data={
            "path": "Math/LU.md",
            "source_hash": SOURCE_HASH,
            "entry_text": "private submitted doubt",
        },
    )

    assert response.status_code == 400
    assert "SECRET" not in response.get_data(as_text=True)
    assert "private submitted doubt" not in response.get_data(as_text=True)


def test_companion_form_maps_service_factory_failure_to_safe_503():
    def broken_factory():
        raise RuntimeError("C:/SECRET/backend initialization")

    response = _client_with_study_factory(broken_factory).post(
        "/obsidian/note/companion/doubts",
        data={
            "path": "Math/LU.md",
            "source_hash": SOURCE_HASH,
            "entry_text": "private submitted doubt",
        },
    )

    assert response.status_code == 503
    assert "SECRET" not in response.get_data(as_text=True)
    assert "private submitted doubt" not in response.get_data(as_text=True)


class TempConfig:
    def __init__(self, vault):
        self.config = {"vault_path": str(vault), "enabled": True}

    def load_config(self):
        return dict(self.config)

    def validate_vault_path(self, value):
        path = Path(value)
        return path.is_dir() and (path / ".obsidian").is_dir(), "validation"


def _real_client(tmp_path, markdown):
    vault = tmp_path / "Vault"
    (vault / ".obsidian").mkdir(parents=True)
    note_path = vault / "Math" / "LU.md"
    note_path.parent.mkdir()
    note_path.write_text(markdown, encoding="utf-8", newline="\n")
    database_path = tmp_path / "learning_assistant.db"
    apply_migrations(database_path)
    config = TempConfig(vault)
    workspace = ObsidianWorkspaceService(config, ObsidianWorkspaceReader)
    study = ObsidianStudyCompanionService(
        workspace,
        SQLiteObsidianStudyRepository(database_path),
        now=lambda: "2026-09-19T15:00:00Z",
    )
    app = create_app(
        {
            "TESTING": True,
            "OBSIDIAN_STUDY_SERVICE_FACTORY": lambda: study,
        }
    )
    return app.test_client(), note_path, database_path, config


def test_real_reader_get_is_pure_and_xss_safe(tmp_path):
    client, note_path, database_path, config = _real_client(
        tmp_path,
        "# LU\n\n**Bold**\n\n<script>alert(1)</script>\n"
        "<img src=x onerror=alert(2)>\n",
    )
    markdown_before = hashlib.sha256(note_path.read_bytes()).hexdigest()
    database_before = hashlib.sha256(database_path.read_bytes()).hexdigest()
    config_before = dict(config.config)

    response = client.get("/obsidian/note?path=Math%2FLU.md")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "<h1>LU</h1>" in html
    assert "<strong>Bold</strong>" in html
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<img src=x" not in html
    assert hashlib.sha256(note_path.read_bytes()).hexdigest() == markdown_before
    assert hashlib.sha256(database_path.read_bytes()).hexdigest() == database_before
    assert config.config == config_before


def test_real_no_js_companion_forms_persist_refresh_and_archive(tmp_path):
    client, _note_path, _database_path, _config = _real_client(
        tmp_path,
        "# LU\n\nFactorization.\n",
    )
    initial = client.get("/obsidian/note?path=Math%2FLU.md")
    source_hash = initial.get_data(as_text=True).split(
        'data-source-hash="', 1
    )[1].split('"', 1)[0]

    key_response = client.post(
        "/obsidian/note/companion/key-points",
        data={
            "path": "Math/LU.md",
            "source_hash": source_hash,
            "entry_text": "L is lower triangular.",
        },
    )
    doubt_response = client.post(
        "/obsidian/note/companion/doubts",
        data={
            "path": "Math/LU.md",
            "source_hash": source_hash,
            "entry_text": "Why pivot?",
        },
    )
    assert key_response.status_code == 303
    assert doubt_response.status_code == 303

    refreshed = client.get("/obsidian/note?path=Math%2FLU.md")
    html = refreshed.get_data(as_text=True)
    assert "L is lower triangular." in html
    assert "Why pivot?" in html
    entry_id = html.split(
        "/obsidian/note/companion/", 1
    )[1].split("/archive", 1)[0]
    archive = client.post(
        "/obsidian/note/companion/{}/archive".format(entry_id),
        data={"path": "Math/LU.md", "source_hash": source_hash},
    )
    assert archive.status_code == 303
    after_archive = client.get("/obsidian/note?path=Math%2FLU.md").get_data(
        as_text=True
    )
    assert "L is lower triangular." not in after_archive
    assert "Why pivot?" in after_archive


def test_reader_template_and_route_dependency_contracts():
    base = (ROOT / "personal_learning_assistant/ui/web/templates/base.html").read_text(
        encoding="utf-8"
    )
    note = (
        ROOT / "personal_learning_assistant/ui/web/templates/obsidian_note.html"
    ).read_text(encoding="utf-8")
    routes = (ROOT / "personal_learning_assistant/ui/web/routes.py").read_text(
        encoding="utf-8"
    )

    assert "{% block page_scripts %}" in base
    assert "obsidian_reader.js" not in base
    assert "obsidian_reader.js" in note
    assert "<details" in note and "obsidian-source" in note
    assert "<noscript>" in note
    assert "maxlength=\"2000\"" in note
    for forbidden in (
        "import sqlite3",
        "sqlite3.",
        ".execute(",
        ".read_bytes(",
        ".read_text(",
        "ObsidianVaultRegistryService.apply",
        "NotesStudioService",
    ):
        assert forbidden not in routes


def test_reader_css_has_desktop_grid_and_narrow_stacked_layout():
    css = (ROOT / "personal_learning_assistant/ui/web/static/css/app.css").read_text(
        encoding="utf-8"
    )

    assert ".obsidian-reader-layout" in css
    assert "grid-template-columns" in css
    assert "@media (max-width: 900px)" in css
    assert ".obsidian-reading-view" in css
    assert ".obsidian-companion" in css
    assert ".obsidian-source" in css


def test_reader_script_has_bounded_active_time_and_safe_transport_contracts():
    script = (
        ROOT
        / "personal_learning_assistant/ui/web/static/js/obsidian_reader.js"
    ).read_text(encoding="utf-8")

    for contract in (
        "const HEARTBEAT_MS = 30000;",
        "const TICK_MS = 1000;",
        "const IDLE_MS = 90000;",
        "const MAX_EVENT_SECONDS = 60;",
        'document.visibilityState === "visible"',
        "document.hasFocus()",
        "performance.now()",
        'credentials: "same-origin"',
        '"Content-Type": "application/json"',
        "navigator.sendBeacon",
        'type: "application/json"',
        "keepalive: true",
    ):
        assert contract in script

    for event_name in (
        '"scroll"',
        '"keydown"',
        '"pointerdown"',
        '"touchstart"',
        '"focus"',
        '"visibilitychange"',
        '"pagehide"',
    ):
        assert event_name in script

    assert "sendChain" in script
    assert "sequence += 1" in script
    assert "Math.min(MAX_EVENT_SECONDS" in script
    assert "Math.min(10000" in script
    assert "Math.max(0" in script
    assert "innerHTML" not in script
    assert "note.text" not in script
    assert "rendered_html" not in script
    assert "replayed_delta_seconds" in script
    assert "finalTransport(payload);" in script
    assert "sendChain = sendChain.then(finalTransport" not in script


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
def test_reader_script_final_flush_includes_time_accrued_during_in_flight_heartbeat():
    script_path = (
        ROOT
        / "personal_learning_assistant/ui/web/static/js/obsidian_reader.js"
    )
    harness = textwrap.dedent(
        r"""
        const assert = require("assert");
        const fs = require("fs");
        const vm = require("vm");

        (async function () {
          let now = 0;
          const intervals = [];
          const windowListeners = {};
          const documentListeners = {};
          const beacons = [];
          let heartbeatRequest = null;

          const data = {
            dataset: {
              path: "Math/LU.md",
              sourceHash: "b".repeat(64),
              startUrl: "/obsidian/note/reading/start",
              heartbeatUrl: "/obsidian/note/reading/heartbeat",
              endUrl: "/obsidian/note/reading/end",
            },
          };
          const document = {
            readyState: "complete",
            visibilityState: "visible",
            hasFocus: () => true,
            getElementById: (id) => id === "obsidian-reader-data" ? data : null,
            addEventListener: (name, callback) => {
              documentListeners[name] = callback;
            },
            documentElement: {clientHeight: 1000, scrollHeight: 2000, scrollTop: 0},
            body: {scrollHeight: 2000},
          };
          const window = {
            location: {
              href: "http://localhost/obsidian/note?path=Math%2FLU.md",
              origin: "http://localhost",
            },
            innerHeight: 1000,
            scrollY: 0,
            addEventListener: (name, callback) => {
              windowListeners[name] = callback;
            },
            setInterval: (callback, milliseconds) => {
              intervals.push({callback, milliseconds, cleared: false});
              return intervals.length - 1;
            },
            clearInterval: (identifier) => {
              intervals[identifier].cleared = true;
            },
          };
          class FakeBlob {
            constructor(parts, options) {
              this.parts = parts;
              this.options = options;
            }
          }
          const navigator = {
            sendBeacon: (url, blob) => {
              beacons.push({url, payload: JSON.parse(blob.parts.join(""))});
              return true;
            },
          };
          const fetch = (url, options) => {
            const payload = JSON.parse(options.body);
            if (url.endsWith("/start")) {
              return Promise.resolve({
                ok: true,
                json: () => Promise.resolve({
                  ok: true,
                  session_id: "44444444-4444-4444-8444-444444444444",
                }),
              });
            }
            if (url.endsWith("/heartbeat")) {
              heartbeatRequest = payload;
              return new Promise(() => {});
            }
            throw new Error("unexpected fetch " + url);
          };

          const context = {
            Blob: FakeBlob,
            URL,
            document,
            fetch,
            navigator,
            performance: {now: () => now},
            Promise,
            window,
          };
          vm.runInNewContext(
            fs.readFileSync(process.env.OBSIDIAN_READER_SCRIPT, "utf8"),
            context,
            {filename: "obsidian_reader.js"}
          );
          await new Promise((resolve) => setImmediate(resolve));

          const tick = intervals.find((item) => item.milliseconds === 1000);
          const heartbeat = intervals.find((item) => item.milliseconds === 30000);
          assert(tick, "one-second timer was not installed");
          assert(heartbeat, "heartbeat timer was not installed");
          for (let second = 0; second < 30; second += 1) {
            now += 1000;
            tick.callback();
          }
          heartbeat.callback();
          await new Promise((resolve) => setImmediate(resolve));
          assert.strictEqual(heartbeatRequest.delta_seconds, 30);
          assert.strictEqual(heartbeatRequest.sequence, 1);

          for (let second = 0; second < 5; second += 1) {
            now += 1000;
            tick.callback();
          }
          windowListeners.pagehide();

          assert.strictEqual(beacons.length, 1);
          assert.strictEqual(beacons[0].url, "/obsidian/note/reading/end");
          assert.strictEqual(beacons[0].payload.sequence, 1);
          assert.strictEqual(beacons[0].payload.delta_seconds, 35);
          assert.strictEqual(beacons[0].payload.replayed_delta_seconds, 30);
        })().catch((error) => {
          console.error(error.stack || error);
          process.exitCode = 1;
        });
        """
    )
    environment = dict(os.environ)
    environment["OBSIDIAN_READER_SCRIPT"] = str(script_path)

    result = subprocess.run(
        [shutil.which("node"), "-e", harness],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
