from personal_learning_assistant.domain.note_models import CreateNoteCommand
from personal_learning_assistant.domain.resource_models import (
    CreateResourceCommand,
    UpdateResourceStatusCommand,
)
from personal_learning_assistant.repositories.interfaces import (
    NoteRepository,
    ResourceRepository,
)
from personal_learning_assistant.repositories.json.note_repository import (
    LegacyJsonNoteRepository,
)
from personal_learning_assistant.repositories.json.resource_repository import (
    LegacyJsonResourceRepository,
)
from personal_learning_assistant.services.notes_service import NotesService
from personal_learning_assistant.services.resource_service import ResourceService


def _protocol_methods(protocol):
    return {
        name
        for name, value in vars(protocol).items()
        if callable(value) and not name.startswith("_")
    }


def test_note_repository_protocol_covers_reads_and_explicit_create():
    assert {"load_notes", "append_note"}.issubset(
        _protocol_methods(NoteRepository)
    )


def test_resource_repository_protocol_covers_service_persistence_contract():
    assert {
        "load_resources",
        "append_resource",
        "replace_resource",
    }.issubset(
        _protocol_methods(ResourceRepository)
    )


def test_concrete_note_repository_satisfies_declared_protocol_surface():
    for method_name in ("load_notes", "append_note"):
        assert callable(
            getattr(
                LegacyJsonNoteRepository,
                method_name,
                None,
            )
        )


def test_concrete_resource_repository_satisfies_declared_protocol_surface():
    for method_name in (
        "load_resources",
        "append_resource",
        "replace_resource",
    ):
        assert callable(
            getattr(
                LegacyJsonResourceRepository,
                method_name,
                None,
            )
        )


def test_notes_service_works_with_structural_repository_without_json():
    class MemoryNoteRepository:
        def __init__(self):
            self.items = []

        def load_notes(self):
            return [dict(item) for item in self.items]

        def append_note(self, note):
            stored = dict(note)
            self.items.append(stored)
            return dict(stored)

    service = NotesService(
        MemoryNoteRepository()
    )

    result = service.create_note(
        CreateNoteCommand(
            title="LU",
            topic="Linear Algebra",
            difficulty="Medium",
            content="A = LU",
        )
    )

    assert result.note.title == "LU"
    assert service.count_notes().count == 1


def test_resource_service_works_with_structural_repository_without_json():
    class MemoryResourceRepository:
        def __init__(self):
            self.items = []

        def load_resources(self):
            return [dict(item) for item in self.items]

        def append_resource(self, resource):
            stored = dict(resource)
            self.items.append(stored)
            return dict(stored)

        def replace_resource(self, position, resource):
            stored = dict(resource)
            self.items[position - 1] = stored
            return dict(stored)

    service = ResourceService(
        MemoryResourceRepository()
    )

    created = service.create_resource(
        CreateResourceCommand(
            title="MIT 18.06",
            resource_type="Course",
            link="https://example.test/18.06",
        )
    )
    assert created.resource.status == "Not Started"

    updated = service.update_status(
        UpdateResourceStatusCommand(
            position=1,
            status="Completed",
        )
    )
    assert updated.resource.status == "Completed"
    assert service.count_resources().count == 1


def test_services_depend_on_repository_protocols_not_json_adapters():
    note_annotation = NotesService.__init__.__annotations__.get(
        "repository"
    )
    resource_annotation = ResourceService.__init__.__annotations__.get(
        "repository"
    )

    assert note_annotation is NoteRepository
    assert resource_annotation is ResourceRepository
