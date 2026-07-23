import json
import os

NOTES_FILE = "data/notes.json"
RESOURCES_FILE = "data/resources.json"


# -------------------------
# Load Notes
# -------------------------
def load_notes():

    if not os.path.exists(NOTES_FILE):
        return []

    try:
        with open(NOTES_FILE, "r") as file:
            return json.load(file)

    except:
        return []


# -------------------------
# Load Resources
# -------------------------
def load_resources():

    if not os.path.exists(RESOURCES_FILE):
        return []

    try:
        with open(RESOURCES_FILE, "r") as file:
            return json.load(file)

    except:
        return []


# -------------------------
# Show Dashboard
# -------------------------
def show_dashboard():

    notes = load_notes()
    resources = load_resources()

    total_notes = len(notes)
    total_resources = len(resources)

    completed = 0
    in_progress = 0
    not_started = 0

    for resource in resources:

        status = resource["status"]

        if status == "Completed":
            completed += 1

        elif status == "In Progress":
            in_progress += 1

        elif status == "Not Started":
            not_started += 1

    if total_resources == 0:
        completion_rate = 0
    else:
        completion_rate = (completed / total_resources) * 100

    print("\n==========================================")
    print("      PERSONAL LEARNING DASHBOARD")
    print("==========================================")

    print(f"\n📝 Total Notes          : {total_notes}")
    print(f"📚 Total Resources      : {total_resources}")

    print("\n---------- Resource Status ----------")

    print(f"✅ Completed            : {completed}")
    print(f"🟡 In Progress          : {in_progress}")
    print(f"⚪ Not Started          : {not_started}")

    print(f"\n📈 Completion Rate      : {completion_rate:.1f}%")

    print("\n==========================================")
