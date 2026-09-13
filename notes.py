"""
==========================================
Personal AI Learning Chatbot v1.0
Developer : Anand Priyadarsi
Language  : Python
Project   : AI Learning Boot Camp

Description:
A personal learning assistant to organize
notes, learning resources, dashboards,
and backups.

==========================================
"""
import json
import os

from config import NOTES_FILE


# -------------------------
# Load Notes
# -------------------------
def load_notes():
    if not os.path.exists(NOTES_FILE):
        return []

    try:
        with open(NOTES_FILE, "r") as file:
            return json.load(file)

    except json.JSONDecodeError:
        return []


# -------------------------
# Save Notes
# -------------------------
def save_notes_to_file(notes):
    with open(NOTES_FILE, "w") as file:
        json.dump(notes, file, indent=4)


# -------------------------
# Add Note
# -------------------------
def add_note():

    print("\n========== ADD NEW NOTE ==========\n")

    title = input("Title : ")
    topic = input("Topic : ")
    difficulty = input("Difficulty (Easy/Medium/Hard): ")

    print("\nEnter your note.")
    print("Type END on a new line when finished.\n")

    lines = []

    while True:
        line = input()

        if line.upper() == "END":
            break

        lines.append(line)

    content = "\n".join(lines)

    note = {
        "title": title,
        "topic": topic,
        "difficulty": difficulty,
        "content": content
    }

    notes = load_notes()

    notes.append(note)

    save_notes_to_file(notes)

    print("\n✅ Note saved successfully!")


# -------------------------
# View Notes
# -------------------------
def _build_notes_service():
    """Build the Phase 2 read-only NotesService lazily."""
    from config import NOTES_FILE as DEFAULT_NOTES_FILE
    from personal_learning_assistant.repositories.json.note_repository import (
        LegacyJsonNoteRepository,
    )
    from personal_learning_assistant.services.notes_service import (
        NotesService,
    )

    note_path = globals().get(
        "NOTES_FILE",
        DEFAULT_NOTES_FILE,
    )

    return NotesService(
        LegacyJsonNoteRepository(
            note_path
        )
    )


def _build_notes_cli():
    """Build the terminal adapter lazily."""
    from personal_learning_assistant.ui.cli.notes_cli import (
        NotesCLI,
    )

    return NotesCLI(
        _build_notes_service()
    )


def view_notes():
    """Compatibility wrapper for the extracted Notes CLI adapter."""
    return _build_notes_cli().view_notes()


# -------------------------
# Count Notes
# -------------------------
def count_notes():
    """Compatibility wrapper for the extracted Notes CLI adapter."""
    return _build_notes_cli().count_notes()


# -------------------------
# Search Notes
# -------------------------
def search_notes():
    """Compatibility wrapper for the extracted Notes CLI adapter."""
    return _build_notes_cli().search_notes()
