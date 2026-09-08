import json
import os
import shutil

from config import (
    NOTES_FILE,
    RESOURCES_FILE,
    NOTES_BACKUP_FILE,
    RESOURCES_BACKUP_FILE
)




# -------------------------
# Backup Database
# -------------------------
def backup_database():


    shutil.copy(NOTES_FILE, NOTES_BACKUP_FILE)
    shutil.copy(RESOURCES_FILE, RESOURCES_BACKUP_FILE)

    print("\n✅ Backup created successfully!")


# -------------------------
# Restore Database
# -------------------------
def restore_database():

    if not os.path.exists(NOTES_BACKUP_FILE):
        print("\n❌ No backup found.")
        return

    shutil.copy(NOTES_BACKUP_FILE, NOTES_FILE)
    shutil.copy(RESOURCES_BACKUP_FILE, RESOURCES_FILE)

    print("\n✅ Database restored successfully!")


# -------------------------
# Export Notes
# -------------------------
def export_notes():

    try:

        with open(NOTES_FILE, "r") as file:
            notes = json.load(file)

        with open("notes_export.txt", "w") as file:

            file.write("========== MY NOTES ==========\n\n")

            for i, note in enumerate(notes, start=1):

                file.write(f"Note {i}\n")
                file.write(f"Title : {note['title']}\n")
                file.write(f"Topic : {note['topic']}\n")
                file.write(f"Difficulty : {note['difficulty']}\n")
                file.write(f"Content :\n{note['content']}\n")
                file.write("-"*40 + "\n")

        print("\n✅ Notes exported successfully!")

    except:
        print("\nNo notes found.")


# -------------------------
# Export Resources
# -------------------------
def export_resources():

    try:

        with open(RESOURCES_FILE, "r") as file:
            resources = json.load(file)

        with open("resources_export.txt", "w") as file:

            file.write("========== LEARNING RESOURCES ==========\n\n")

            for i, resource in enumerate(resources, start=1):

                file.write(f"Resource {i}\n")
                file.write(f"Title : {resource['title']}\n")
                file.write(f"Type : {resource['type']}\n")
                file.write(f"Link : {resource['link']}\n")
                file.write(f"Status : {resource['status']}\n")
                file.write("-"*40 + "\n")

        print("\n✅ Resources exported successfully!")

    except:
        print("\nNo resources found.")
