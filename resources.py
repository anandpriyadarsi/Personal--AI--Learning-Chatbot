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
    """Compatibility wrapper for the extracted Resources CLI adapter."""
    return _build_resources_cli().add_resource()


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
    """Compatibility wrapper for the extracted Resources CLI adapter."""
    return _build_resources_cli().update_status()
