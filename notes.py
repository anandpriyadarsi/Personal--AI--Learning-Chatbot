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
def view_notes():

    notes = load_notes()

    if len(notes) == 0:
        print("\nNo notes found.")
        return

    print("\n========== MY NOTES ==========")

    for i, note in enumerate(notes, start=1):

        print("\n----------------------------")
        print(f"Note {i}")
        print("----------------------------")
        print("Title      :", note["title"])
        print("Topic      :", note["topic"])
        print("Difficulty :", note["difficulty"])
        print("Content :")
        print(note["content"])


# -------------------------
# Count Notes
# -------------------------
def count_notes():

    notes = load_notes()

    print("\n========== NOTES SUMMARY ==========")
    print(f"\n📝 Total Notes : {len(notes)}")


# -------------------------
# Search Notes
# -------------------------
def search_notes():

    keyword = input("\nEnter keyword to search : ").lower()

    notes = load_notes()

    found = False

    for note in notes:

        if (keyword in note["title"].lower() or
                keyword in note["topic"].lower() or
                keyword in note["content"].lower()):

            found = True

            print("\n----------------------------")
            print("Title :", note["title"])
            print("Topic :", note["topic"])
            print("Difficulty :", note["difficulty"])
            print("Content :")
            print(note["content"])

    if not found:
        print("\n❌ No matching notes found.")
