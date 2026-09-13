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

from config import RESOURCES_FILE


# -------------------------
# Load Resources
# -------------------------
def load_resources():
    if not os.path.exists(RESOURCES_FILE):
        return []

    try:
        with open(RESOURCES_FILE, "r") as file:
            return json.load(file)

    except json.JSONDecodeError:
        return []


# -------------------------
# Save Resources
# -------------------------
def save_resources(resources):
    with open(RESOURCES_FILE, "w") as file:
        json.dump(resources, file, indent=4)


# -------------------------
# Phase 2 service/CLI builders
# -------------------------
def _build_resources_service():
    """Build the Phase 2 ResourceService lazily."""
    from config import RESOURCES_FILE as DEFAULT_RESOURCES_FILE
    from personal_learning_assistant.repositories.json.resource_repository import (
        LegacyJsonResourceRepository,
    )
    from personal_learning_assistant.services.resource_service import (
        ResourceService,
    )

    resource_path = globals().get(
        "RESOURCES_FILE",
        DEFAULT_RESOURCES_FILE,
    )

    return ResourceService(
        LegacyJsonResourceRepository(
            resource_path
        )
    )


def _build_resources_cli():
    """Build the terminal adapter lazily."""
    from personal_learning_assistant.ui.cli.resources_cli import (
        ResourcesCLI,
    )

    return ResourcesCLI(
        _build_resources_service()
    )


# -------------------------
# Add Resource
# -------------------------
def add_resource():

    print("\n========== ADD NEW RESOURCE ==========\n")

    title = input("Title : ")
    resource_type = input("Type (YouTube/Book/Website/GitHub/Course): ")
    link = input("Link : ")

    resource = {
        "title": title,
        "type": resource_type,
        "link": link,
        "status": "Not Started"
    }

    resources = load_resources()
    resources.append(resource)
    save_resources(resources)

    print("\n✅ Resource added successfully!")


# -------------------------
# View Resources
# -------------------------
def view_resources():
    """Compatibility wrapper for the extracted Resources CLI adapter."""
    return _build_resources_cli().view_resources()


# -------------------------
# Search Resources
# -------------------------
def search_resources():
    """Compatibility wrapper for the extracted Resources CLI adapter."""
    return _build_resources_cli().search_resources()


# -------------------------
# Count Resources
# -------------------------
def count_resources():
    """Compatibility wrapper for the extracted Resources CLI adapter."""
    return _build_resources_cli().count_resources()


# -------------------------
# Update Resource Status
# -------------------------
def update_status():

    resources = load_resources()

    if len(resources) == 0:
        print("\nNo resources found.")
        return

    print("\n========== UPDATE STATUS ==========\n")

    for i, resource in enumerate(resources, start=1):
        print(f"{i}. {resource['title']} ({resource['status']})")

    try:
        choice = int(input("\nEnter resource number: "))

        if choice < 1 or choice > len(resources):
            print("Invalid choice.")
            return

        print("\nChoose Status")
        print("1. Not Started")
        print("2. In Progress")
        print("3. Completed")

        status_choice = input("Enter choice: ")

        if status_choice == "1":
            resources[choice-1]["status"] = "Not Started"

        elif status_choice == "2":
            resources[choice-1]["status"] = "In Progress"

        elif status_choice == "3":
            resources[choice-1]["status"] = "Completed"

        else:
            print("Invalid status.")
            return

        save_resources(resources)

        print("\n✅ Status updated successfully!")

    except ValueError:
        print("\nPlease enter a valid number.")
