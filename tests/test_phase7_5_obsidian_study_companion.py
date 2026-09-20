from __future__ import annotations

import hashlib
import uuid
from copy import deepcopy

import pytest
from markupsafe import Markup

from personal_learning_assistant.repositories.filesystem.obsidian_vault_scanner import (
    normalized_note_path_key,
)
from personal_learning_assistant.repositories.sqlite.obsidian_study_repository import (
    ObsidianStudyRepositoryConflictError,
    ObsidianStudyRepositoryError,
    ObsidianStudyRepositoryNotFoundError,
    SQLiteObsidianStudyRepository,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
from personal_learning_assistant.services.obsidian_study_companion_service import (
    ObsidianStudyCompanionService,
    ObsidianStudyConflictError,
    ObsidianStudyNotFoundError,
    ObsidianStudyUnavailableError,
    ObsidianStudyValidationError,
)
from personal_learning_assistant.services.obsidian_workspace_service import (
    ObsidianWorkspaceNotFoundError,
    ObsidianWorkspaceUnavailableError,
    ObsidianWorkspaceValidationError,
)


ASSISTANT_ID = "11111111-1111-4111-8111-111111111111"
VAULT_IDENTITY = "vault:" + "a" * 64
SOURCE_HASH = "b" * 64
NOW = "2026-09-19T15:00:00Z"


def _note(**changes):
    note = {
        "title": "LU Factorization",
        "relative_path": "Math/LU Factorization.md",
        "assistant_id": ASSISTANT_ID,
        "vault_name": "My Vault",
        "vault_identity": VAULT_IDENTITY,
        "tags": ["linear-algebra"],
        "note_type": "concept",
        "revision_status": "needs_practice",
        "source_hash": SOURCE_HASH,
        "size_bytes": 123,
        "text": "---\ntitle: LU Factorization\n---\n# LU\n\n**Factorization** body.\n",
    }
    note.update(changes)
    return note


class FakeWorkspace:
    def __init__(self, note=None):
        self.note = _note() if note is None else note
        self.preview_calls = []

    def note_preview(self, relative_path):
        self.preview_calls.append(relative_path)
        result = deepcopy(self.note)
        result["relative_path"] = str(relative_path)
        return result


class FakeRepository:
    def __init__(self):
        self.read_calls = []
        self.write_calls = []
        self.history = {
            "times_opened": 2,
            "last_read_at": "2026-09-19T14:00:00Z",
            "total_active_seconds": 125,
            "last_session_active_seconds": 35,
            "max_scroll_bps": 7300,
            "recent_sessions": (
                {
                    "id": "session-2",
                    "started_at": "2026-09-19T14:00:00Z",
                    "ended_at": "2026-09-19T14:00:35Z",
                    "active_seconds": 35,
                    "max_scroll_bps": 7300,
                },
            ),
        }
        self.entries = (
            {
                "id": "22222222-2222-4222-8222-222222222222",
                "entry_type": "key_point",
                "entry_text": "Doolittle uses a unit diagonal in L.",
                "created_at": "2026-09-19T14:10:00Z",
                "updated_at": "2026-09-19T14:10:00Z",
                "archived_at": None,
            },
            {
                "id": "33333333-3333-4333-8333-333333333333",
                "entry_type": "doubt",
                "entry_text": "When is pivoting mandatory?",
                "created_at": "2026-09-19T14:11:00Z",
                "updated_at": "2026-09-19T14:11:00Z",
                "archived_at": None,
            },
        )

    def reading_history(self, **scope):
        self.read_calls.append(("history", scope))
        return deepcopy(self.history)

    def list_entries(self, **scope):
        self.read_calls.append(("entries", scope))
        return deepcopy(self.entries)

    def create_session(self, **values):
        self.write_calls.append(("create_session", values))
        raise AssertionError("Reader GET must not start a session")


class CommandRepository(FakeRepository):
    def create_session(self, **values):
        self.write_calls.append(("create_session", values))
        return {
            "id": values["session_id"],
            "active_seconds": 0,
            "max_scroll_bps": 0,
            "accepted": True,
            "ended_at": None,
        }

    def heartbeat(self, **values):
        self.write_calls.append(("heartbeat", values))
        return {
            "id": values["session_id"],
            "active_seconds": values["delta_seconds"],
            "max_scroll_bps": values["scroll_bps"],
            "accepted": True,
            "ended_at": None,
        }

    def end_session(self, **values):
        self.write_calls.append(("end_session", values))
        return {
            "id": values["session_id"],
            "active_seconds": values["delta_seconds"],
            "max_scroll_bps": values["scroll_bps"],
            "accepted": True,
            "ended_at": values["now"],
        }

    def add_entry(self, **values):
        self.write_calls.append(("add_entry", values))
        return {
            "id": values["entry_id"],
            "entry_type": values["entry_type"],
            "entry_text": values["entry_text"],
            "created_at": values["now"],
            "updated_at": values["now"],
            "archived_at": None,
        }

    def archive_entry(self, **values):
        self.write_calls.append(("archive_entry", values))
        return {
            "id": values["entry_id"],
            "entry_type": "key_point",
            "entry_text": "Archived",
            "created_at": NOW,
            "updated_at": values["now"],
            "archived_at": values["now"],
        }


def test_reader_view_uses_assistant_identity_safe_rendering_and_deep_link():
    workspace = FakeWorkspace()
    repository = FakeRepository()
    service = ObsidianStudyCompanionService(workspace, repository)

    view = service.reader_view("Math/LU Factorization.md")

    assert workspace.preview_calls == ["Math/LU Factorization.md"]
    assert view["note_identity"] == "assistant:" + ASSISTANT_ID
    assert isinstance(view["rendered_html"], Markup)
    assert "<h1>LU</h1>" in str(view["rendered_html"])
    assert "<strong>Factorization</strong>" in str(view["rendered_html"])
    assert "title: LU Factorization" not in str(view["rendered_html"])
    assert view["text"].startswith("---\ntitle:")
    assert view["open_in_obsidian_url"].startswith("obsidian://open?")
    assert "vault=My%20Vault" in view["open_in_obsidian_url"]
    assert "file=Math%2FLU%20Factorization.md" in view["open_in_obsidian_url"]
    assert "/home/" not in view["open_in_obsidian_url"]
    assert view["history"]["times_opened"] == 2
    assert view["history"]["total_active_seconds"] == 125
    assert [item["entry_text"] for item in view["companion"]["key_points"]] == [
        "Doolittle uses a unit diagonal in L."
    ]
    assert [item["entry_text"] for item in view["companion"]["doubts"]] == [
        "When is pivoting mandatory?"
    ]
    assert view["companion"]["available"] is True
    assert repository.write_calls == []


def test_reader_view_path_identity_is_deterministic_and_note_isolated():
    relative_path = "Math/External.md"
    workspace = FakeWorkspace(_note(assistant_id=None, relative_path=relative_path))
    repository = FakeRepository()
    service = ObsidianStudyCompanionService(workspace, repository)

    first = service.reader_view(relative_path)
    second = service.reader_view(relative_path)
    material = VAULT_IDENTITY + "\0" + normalized_note_path_key(relative_path)
    expected = "path:" + hashlib.sha256(material.encode("utf-8")).hexdigest()

    assert first["note_identity"] == expected
    assert second["note_identity"] == expected
    scopes = [scope for _kind, scope in repository.read_calls]
    assert all(scope["vault_identity"] == VAULT_IDENTITY for scope in scopes)
    assert all(scope["note_identity"] == expected for scope in scopes)


def test_reader_view_survives_history_database_unavailable():
    class BrokenRepository(FakeRepository):
        def reading_history(self, **scope):
            raise ObsidianStudyRepositoryError(
                "C:/SECRET/learning_assistant.db is locked"
            )

    service = ObsidianStudyCompanionService(FakeWorkspace(), BrokenRepository())

    view = service.reader_view("Math/LU Factorization.md")

    assert "<h1>LU</h1>" in str(view["rendered_html"])
    assert view["companion"] == {
        "available": False,
        "message": "Study history and Companion are temporarily unavailable.",
        "key_points": (),
        "doubts": (),
    }
    assert view["history"]["times_opened"] == 0
    assert "SECRET" not in str(view)


def test_reader_view_uses_escaped_fallback_when_injected_renderer_fails():
    def broken_renderer(_source):
        raise RuntimeError("parser internal path C:/SECRET")

    workspace = FakeWorkspace(
        _note(text='<script>alert("reader")</script>\n**readable source**')
    )
    service = ObsidianStudyCompanionService(
        workspace,
        FakeRepository(),
        renderer=broken_renderer,
    )

    view = service.reader_view("Math/LU Factorization.md")
    html = str(view["rendered_html"])

    assert html.startswith('<pre class="obsidian-render-fallback">')
    assert "<script" not in html
    assert "&lt;script&gt;alert" in html
    assert "**readable source**" in html
    assert "SECRET" not in html


def test_reader_view_never_trusts_plain_string_from_injected_renderer():
    workspace = FakeWorkspace(_note(text="# Safe source"))
    service = ObsidianStudyCompanionService(
        workspace,
        FakeRepository(),
        renderer=lambda _source: '<img src=x onerror=alert("renderer")>',
    )

    html = str(service.reader_view("Math/LU Factorization.md")["rendered_html"])

    assert "<img" not in html
    assert "&lt;img src=x onerror=alert" in html


def test_start_reading_revalidates_note_and_creates_zero_total_session():
    repository = CommandRepository()
    session_uuid = uuid.UUID("44444444-4444-4444-8444-444444444444")
    workspace = FakeWorkspace()
    service = ObsidianStudyCompanionService(
        workspace,
        repository,
        now=lambda: NOW,
        id_factory=lambda: session_uuid,
    )

    result = service.start_reading(
        relative_path="Math/LU Factorization.md",
        source_hash=SOURCE_HASH,
    )

    assert workspace.preview_calls == ["Math/LU Factorization.md"]
    assert result == {
        "session_id": str(session_uuid),
        "active_seconds": 0,
        "max_scroll_bps": 0,
        "accepted": True,
        "ended_at": None,
    }
    kind, values = repository.write_calls[-1]
    assert kind == "create_session"
    assert values["vault_identity"] == VAULT_IDENTITY
    assert values["note_identity"] == "assistant:" + ASSISTANT_ID
    assert values["relative_path"] == "Math/LU Factorization.md"
    assert values["source_hash"] == SOURCE_HASH
    assert values["now"] == NOW


@pytest.mark.parametrize(
    ("delta_seconds", "scroll_bps"),
    ((1, 0), (60, 10000)),
)
def test_heartbeat_accepts_only_bounded_server_deltas(delta_seconds, scroll_bps):
    repository = CommandRepository()
    service = ObsidianStudyCompanionService(
        FakeWorkspace(), repository, now=lambda: NOW
    )
    session_id = "44444444-4444-4444-8444-444444444444"

    result = service.heartbeat(
        relative_path="Math/LU Factorization.md",
        source_hash=SOURCE_HASH,
        session_id=session_id,
        sequence=2,
        delta_seconds=delta_seconds,
        scroll_bps=scroll_bps,
    )

    assert result["session_id"] == session_id
    assert result["active_seconds"] == delta_seconds
    assert result["max_scroll_bps"] == scroll_bps
    assert repository.write_calls[-1][0] == "heartbeat"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("sequence", 0),
        ("sequence", True),
        ("sequence", "1"),
        ("delta_seconds", 0),
        ("delta_seconds", 61),
        ("delta_seconds", 1.5),
        ("scroll_bps", -1),
        ("scroll_bps", 10001),
        ("scroll_bps", "100"),
    ),
)
def test_heartbeat_rejects_malformed_or_out_of_range_values_before_write(
    field, value
):
    repository = CommandRepository()
    service = ObsidianStudyCompanionService(FakeWorkspace(), repository)
    values = {
        "relative_path": "Math/LU Factorization.md",
        "source_hash": SOURCE_HASH,
        "session_id": "44444444-4444-4444-8444-444444444444",
        "sequence": 1,
        "delta_seconds": 30,
        "scroll_bps": 5000,
    }
    values[field] = value

    with pytest.raises(ObsidianStudyValidationError):
        service.heartbeat(**values)

    assert repository.write_calls == []


@pytest.mark.parametrize("delta_seconds", (0, 60))
def test_end_reading_accepts_zero_or_bounded_final_delta(delta_seconds):
    repository = CommandRepository()
    service = ObsidianStudyCompanionService(
        FakeWorkspace(), repository, now=lambda: NOW
    )

    result = service.end_reading(
        relative_path="Math/LU Factorization.md",
        source_hash=SOURCE_HASH,
        session_id="44444444-4444-4444-8444-444444444444",
        sequence=3,
        delta_seconds=delta_seconds,
        scroll_bps=9000,
    )

    assert result["ended_at"] == NOW
    assert repository.write_calls[-1][0] == "end_session"


def test_end_reading_delegates_bounded_replayed_delta():
    repository = CommandRepository()
    service = ObsidianStudyCompanionService(
        FakeWorkspace(), repository, now=lambda: NOW
    )

    service.end_reading(
        relative_path="Math/LU Factorization.md",
        source_hash=SOURCE_HASH,
        session_id="44444444-4444-4444-8444-444444444444",
        sequence=3,
        delta_seconds=35,
        replayed_delta_seconds=30,
        scroll_bps=9000,
    )

    command, values = repository.write_calls[-1]
    assert command == "end_session"
    assert values["delta_seconds"] == 35
    assert values["replayed_delta_seconds"] == 30


@pytest.mark.parametrize("replayed_delta_seconds", (-1, 36, True, 1.5, "30"))
def test_end_reading_rejects_invalid_replayed_delta_before_write(
    replayed_delta_seconds,
):
    repository = CommandRepository()
    service = ObsidianStudyCompanionService(FakeWorkspace(), repository)

    with pytest.raises(ObsidianStudyValidationError):
        service.end_reading(
            relative_path="Math/LU Factorization.md",
            source_hash=SOURCE_HASH,
            session_id="44444444-4444-4444-8444-444444444444",
            sequence=3,
            delta_seconds=35,
            replayed_delta_seconds=replayed_delta_seconds,
            scroll_bps=9000,
        )

    assert repository.write_calls == []


@pytest.mark.parametrize("delta_seconds", (-1, 61))
def test_end_reading_rejects_out_of_range_final_delta(delta_seconds):
    repository = CommandRepository()
    service = ObsidianStudyCompanionService(FakeWorkspace(), repository)

    with pytest.raises(ObsidianStudyValidationError):
        service.end_reading(
            relative_path="Math/LU Factorization.md",
            source_hash=SOURCE_HASH,
            session_id="44444444-4444-4444-8444-444444444444",
            sequence=3,
            delta_seconds=delta_seconds,
            scroll_bps=9000,
        )
    assert repository.write_calls == []


@pytest.mark.parametrize(
    "session_id",
    ("", "not-a-uuid", "../../session", "44444444-4444-4444-4444"),
)
def test_tracking_rejects_malformed_session_id(session_id):
    repository = CommandRepository()
    service = ObsidianStudyCompanionService(FakeWorkspace(), repository)

    with pytest.raises(ObsidianStudyValidationError):
        service.heartbeat(
            relative_path="Math/LU Factorization.md",
            source_hash=SOURCE_HASH,
            session_id=session_id,
            sequence=1,
            delta_seconds=30,
            scroll_bps=100,
        )
    assert repository.write_calls == []


@pytest.mark.parametrize(
    "source_hash",
    ("", "a" * 63, "A" * 64, "z" * 64, "../" + "a" * 64),
)
def test_tracking_rejects_malformed_source_hash(source_hash):
    repository = CommandRepository()
    service = ObsidianStudyCompanionService(FakeWorkspace(), repository)

    with pytest.raises(ObsidianStudyValidationError):
        service.start_reading(
            relative_path="Math/LU Factorization.md",
            source_hash=source_hash,
        )
    assert repository.write_calls == []


def test_tracking_rejects_note_changed_since_reader_render():
    repository = CommandRepository()
    workspace = FakeWorkspace(_note(source_hash="c" * 64))
    service = ObsidianStudyCompanionService(workspace, repository)

    with pytest.raises(ObsidianStudyConflictError):
        service.start_reading(
            relative_path="Math/LU Factorization.md",
            source_hash=SOURCE_HASH,
        )
    assert repository.write_calls == []


@pytest.mark.parametrize(
    ("workspace_error", "expected"),
    (
        (ObsidianWorkspaceValidationError("C:/SECRET"), ObsidianStudyValidationError),
        (ObsidianWorkspaceNotFoundError("C:/SECRET"), ObsidianStudyNotFoundError),
        (ObsidianWorkspaceUnavailableError("C:/SECRET"), ObsidianStudyUnavailableError),
    ),
)
def test_tracking_maps_current_note_failures_without_leaking_details(
    workspace_error, expected
):
    class BrokenWorkspace:
        def note_preview(self, _relative_path):
            raise workspace_error

    service = ObsidianStudyCompanionService(BrokenWorkspace(), CommandRepository())

    with pytest.raises(expected) as error:
        service.start_reading(
            relative_path="../secret.md",
            source_hash=SOURCE_HASH,
        )
    assert "SECRET" not in str(error.value)


@pytest.mark.parametrize(
    ("repository_error", "expected"),
    (
        (ObsidianStudyRepositoryNotFoundError("SECRET"), ObsidianStudyNotFoundError),
        (ObsidianStudyRepositoryConflictError("SECRET"), ObsidianStudyConflictError),
        (ObsidianStudyRepositoryError("SECRET"), ObsidianStudyUnavailableError),
    ),
)
def test_heartbeat_maps_repository_failures_safely(repository_error, expected):
    class BrokenRepository(CommandRepository):
        def heartbeat(self, **values):
            raise repository_error

    service = ObsidianStudyCompanionService(FakeWorkspace(), BrokenRepository())

    with pytest.raises(expected) as error:
        service.heartbeat(
            relative_path="Math/LU Factorization.md",
            source_hash=SOURCE_HASH,
            session_id="44444444-4444-4444-8444-444444444444",
            sequence=1,
            delta_seconds=30,
            scroll_bps=100,
        )
    assert "SECRET" not in str(error.value)


@pytest.mark.parametrize("entry_type", ("key_point", "doubt"))
def test_add_companion_entry_validates_current_note_and_normalizes_text(entry_type):
    repository = CommandRepository()
    entry_uuid = uuid.UUID("55555555-5555-4555-8555-555555555555")
    service = ObsidianStudyCompanionService(
        FakeWorkspace(),
        repository,
        now=lambda: NOW,
        id_factory=lambda: entry_uuid,
    )

    result = service.add_companion_entry(
        relative_path="Math/LU Factorization.md",
        source_hash=SOURCE_HASH,
        entry_type=entry_type,
        entry_text="  First line\r\nSecond line  ",
    )

    assert result["id"] == str(entry_uuid)
    assert result["entry_type"] == entry_type
    assert result["entry_text"] == "First line\nSecond line"
    kind, values = repository.write_calls[-1]
    assert kind == "add_entry"
    assert values["vault_identity"] == VAULT_IDENTITY
    assert values["note_identity"] == "assistant:" + ASSISTANT_ID
    assert values["relative_path"] == "Math/LU Factorization.md"
    assert values["now"] == NOW


@pytest.mark.parametrize(
    ("entry_type", "entry_text"),
    (
        ("answer", "Unsupported type"),
        ("key_point", ""),
        ("doubt", "   \r\n  "),
        ("key_point", "x" * 2001),
    ),
)
def test_add_companion_entry_rejects_invalid_or_overlong_text_before_write(
    entry_type, entry_text
):
    repository = CommandRepository()
    service = ObsidianStudyCompanionService(FakeWorkspace(), repository)

    with pytest.raises(ObsidianStudyValidationError):
        service.add_companion_entry(
            relative_path="Math/LU Factorization.md",
            source_hash=SOURCE_HASH,
            entry_type=entry_type,
            entry_text=entry_text,
        )
    assert repository.write_calls == []


def test_companion_entries_persist_after_service_reconstruction_and_archive(tmp_path):
    database_path = tmp_path / "learning_assistant.db"
    apply_migrations(database_path)
    workspace = FakeWorkspace()
    first_service = ObsidianStudyCompanionService(
        workspace,
        SQLiteObsidianStudyRepository(database_path),
        now=lambda: NOW,
    )
    key_point = first_service.add_companion_entry(
        relative_path="Math/LU Factorization.md",
        source_hash=SOURCE_HASH,
        entry_type="key_point",
        entry_text="L is lower triangular.",
    )
    doubt = first_service.add_companion_entry(
        relative_path="Math/LU Factorization.md",
        source_hash=SOURCE_HASH,
        entry_type="doubt",
        entry_text="Why does pivoting improve stability?",
    )

    reopened = ObsidianStudyCompanionService(
        FakeWorkspace(),
        SQLiteObsidianStudyRepository(database_path),
        now=lambda: "2026-09-19T16:00:00Z",
    )
    view = reopened.reader_view("Math/LU Factorization.md")
    assert [item["id"] for item in view["companion"]["key_points"]] == [
        key_point["id"]
    ]
    assert [item["id"] for item in view["companion"]["doubts"]] == [doubt["id"]]

    archived = reopened.archive_companion_entry(
        relative_path="Math/LU Factorization.md",
        source_hash=SOURCE_HASH,
        entry_id=key_point["id"],
    )
    assert archived["archived_at"] == "2026-09-19T16:00:00Z"
    refreshed = reopened.reader_view("Math/LU Factorization.md")
    assert refreshed["companion"]["key_points"] == ()
    assert len(refreshed["companion"]["doubts"]) == 1


@pytest.mark.parametrize(
    "entry_id",
    ("", "not-a-uuid", "../../entry", "55555555-5555-5555-5555"),
)
def test_archive_rejects_malformed_entry_id(entry_id):
    repository = CommandRepository()
    service = ObsidianStudyCompanionService(FakeWorkspace(), repository)

    with pytest.raises(ObsidianStudyValidationError):
        service.archive_companion_entry(
            relative_path="Math/LU Factorization.md",
            source_hash=SOURCE_HASH,
            entry_id=entry_id,
        )
    assert repository.write_calls == []


@pytest.mark.parametrize(
    ("repository_error", "expected"),
    (
        (ObsidianStudyRepositoryNotFoundError("SECRET"), ObsidianStudyNotFoundError),
        (ObsidianStudyRepositoryConflictError("SECRET"), ObsidianStudyConflictError),
        (ObsidianStudyRepositoryError("SECRET"), ObsidianStudyUnavailableError),
    ),
)
def test_companion_commands_map_repository_failures_safely(
    repository_error, expected
):
    class BrokenRepository(CommandRepository):
        def add_entry(self, **values):
            raise repository_error

    service = ObsidianStudyCompanionService(FakeWorkspace(), BrokenRepository())

    with pytest.raises(expected) as error:
        service.add_companion_entry(
            relative_path="Math/LU Factorization.md",
            source_hash=SOURCE_HASH,
            entry_type="doubt",
            entry_text="Safe question",
        )
    assert "SECRET" not in str(error.value)


def test_companion_write_rejects_note_changed_since_reader_render():
    repository = CommandRepository()
    service = ObsidianStudyCompanionService(
        FakeWorkspace(_note(source_hash="c" * 64)), repository
    )

    with pytest.raises(ObsidianStudyConflictError):
        service.add_companion_entry(
            relative_path="Math/LU Factorization.md",
            source_hash=SOURCE_HASH,
            entry_type="key_point",
            entry_text="Stale note point",
        )
    assert repository.write_calls == []
