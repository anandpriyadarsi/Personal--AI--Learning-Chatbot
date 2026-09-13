"""Terminal adapter for legacy Resource read commands.

Phase 2 Fix 10 moves terminal input/output for resource reads behind the
non-interactive ResourceService.  JSON remains the structured authority.
Resource writes stay on their existing compatibility path until the next fix.
"""

from typing import Callable

from personal_learning_assistant.domain.resource_models import (
    SearchResourcesQuery,
)


class ResourcesCLI:
    """Interactive renderer/controller for legacy resource read commands."""

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
