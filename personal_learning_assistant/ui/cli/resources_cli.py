"""Terminal adapter for the legacy Resources commands.

Phase 2 Fix 11 routes both reads and writes through the non-interactive
ResourceService. ``input``/``print`` stay in this adapter while JSON remains
the structured authority.
"""

from typing import Callable

from personal_learning_assistant.domain.resource_models import (
    CreateResourceCommand,
    SearchResourcesQuery,
    UpdateResourceStatusCommand,
)


class ResourcesCLI:
    """Interactive renderer/controller for legacy Resource commands."""

    def __init__(
        self,
        service,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
    ):
        self.service = service
        self.input = input_fn
        self.output = output_fn

    @staticmethod
    def _legacy_dict(resource):
        return resource.to_legacy_dict()

    def add_resource(self):
        self.output(
            "\n========== ADD NEW RESOURCE ==========\n"
        )

        title = self.input(
            "Title : "
        )
        resource_type = self.input(
            "Type (YouTube/Book/Website/GitHub/Course): "
        )
        link = self.input(
            "Link : "
        )

        result = self.service.create_resource(
            CreateResourceCommand(
                title=title,
                resource_type=resource_type,
                link=link,
            )
        )

        self.output(
            "\n✅ Resource added successfully!"
        )

        return self._legacy_dict(
            result.resource
        )

    def view_resources(self):
        result = self.service.list_resources()

        if not result.resources:
            self.output(
                "\nNo resources found."
            )
            return []

        self.output(
            "\n========== MY LEARNING RESOURCES =========="
        )

        for number, resource in enumerate(
            result.resources,
            start=1,
        ):
            self.output(
                "\n----------------------------"
            )
            self.output(
                f"Resource {number}"
            )
            self.output(
                "----------------------------"
            )
            self.output(
                f"Title  : {resource.title}"
            )
            self.output(
                f"Type   : {resource.resource_type}"
            )
            self.output(
                f"Link   : {resource.link}"
            )
            self.output(
                f"Status : {resource.status}"
            )

        return [
            self._legacy_dict(resource)
            for resource in result.resources
        ]

    def search_resources(self):
        keyword = self.input(
            "\nEnter keyword : "
        ).lower()

        result = self.service.search_resources(
            SearchResourcesQuery(
                text=keyword
            )
        )

        if not result.resources:
            self.output(
                "\n❌ No matching resource found."
            )
            return []

        for resource in result.resources:
            self.output(
                "\n----------------------------"
            )
            self.output(
                f"Title  : {resource.title}"
            )
            self.output(
                f"Type   : {resource.resource_type}"
            )
            self.output(
                f"Link   : {resource.link}"
            )
            self.output(
                f"Status : {resource.status}"
            )

        return [
            self._legacy_dict(resource)
            for resource in result.resources
        ]

    def count_resources(self):
        result = self.service.count_resources()

        self.output(
            "\n========== RESOURCE SUMMARY =========="
        )
        self.output(
            f"\n📚 Total Resources : {result.count}"
        )

        return result.count

    def update_status(self):
        result = self.service.list_resources()

        if not result.resources:
            self.output(
                "\nNo resources found."
            )
            return None

        self.output(
            "\n========== UPDATE STATUS ==========\n"
        )

        for resource in result.resources:
            self.output(
                f"{resource.position}. "
                f"{resource.title} "
                f"({resource.status})"
            )

        try:
            choice = int(
                self.input(
                    "\nEnter resource number: "
                )
            )
        except ValueError:
            self.output(
                "\nPlease enter a valid number."
            )
            return None

        if (
            choice < 1
            or choice > len(result.resources)
        ):
            self.output(
                "Invalid choice."
            )
            return None

        self.output(
            "\nChoose Status"
        )
        self.output(
            "1. Not Started"
        )
        self.output(
            "2. In Progress"
        )
        self.output(
            "3. Completed"
        )

        status_choice = self.input(
            "Enter choice: "
        )

        status_by_choice = {
            "1": "Not Started",
            "2": "In Progress",
            "3": "Completed",
        }

        status = status_by_choice.get(
            status_choice
        )

        if status is None:
            self.output(
                "Invalid status."
            )
            return None

        updated = self.service.update_status(
            UpdateResourceStatusCommand(
                position=choice,
                status=status,
            )
        )

        self.output(
            "\n✅ Status updated successfully!"
        )

        return self._legacy_dict(
            updated.resource
        )
