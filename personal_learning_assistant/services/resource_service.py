"""Non-interactive service for the legacy Resources subsystem.

Phase 2 keeps JSON authoritative.  This service separates resource behavior
from terminal input/output and direct file access while preserving the V1
record shape and status labels.
"""

from typing import Optional

from personal_learning_assistant.repositories.interfaces import (
    ResourceRepository,
)

from personal_learning_assistant.domain.resource_models import (
    CreateResourceCommand,
    ListResourcesQuery,
    ResourceCountResult,
    ResourceCreateResult,
    ResourceListResult,
    ResourceSearchResult,
    ResourceUpdateResult,
    ResourceView,
    SearchResourcesQuery,
    UpdateResourceStatusCommand,
    normalise_legacy_resource_status,
)


class ResourceService:
    """Application service over a legacy-compatible resource repository."""

    def __init__(
        self,
        repository: ResourceRepository,
    ):
        self.repository = repository

    def create_resource(
        self,
        command: CreateResourceCommand,
    ) -> ResourceCreateResult:
        # Preserve Phase 2 parity: do not introduce new validation rules that
        # were not part of the legacy V1 resource command.
        existing = self.repository.load_resources()

        resource = ResourceView(
            position=len(existing) + 1,
            title=str(command.title),
            resource_type=str(
                command.resource_type
            ),
            link=str(command.link),
            status="Not Started",
        )

        stored = self.repository.append_resource(
            resource.to_legacy_dict()
        )

        return ResourceCreateResult(
            resource=ResourceView.from_legacy(
                len(existing) + 1,
                stored,
            )
        )

    def list_resources(
        self,
        query: Optional[ListResourcesQuery] = None,
    ) -> ResourceListResult:
        query = query or ListResourcesQuery()

        resources = [
            ResourceView.from_legacy(
                position,
                item,
            )
            for position, item in enumerate(
                self.repository.load_resources(),
                start=1,
            )
        ]

        resources = self._apply_filters(
            resources,
            resource_type=query.resource_type,
            status=query.status,
        )

        return ResourceListResult(
            resources=tuple(resources)
        )

    def get_resource(
        self,
        position: int,
    ) -> Optional[ResourceView]:
        if position < 1:
            return None

        resources = (
            self.list_resources().resources
        )

        if position > len(resources):
            return None

        return resources[
            position - 1
        ]

    def count_resources(
        self,
        query: Optional[ListResourcesQuery] = None,
    ) -> ResourceCountResult:
        result = self.list_resources(
            query
        )

        return ResourceCountResult(
            count=len(
                result.resources
            )
        )

    def search_resources(
        self,
        query: SearchResourcesQuery,
    ) -> ResourceSearchResult:
        search_text = (
            str(query.text)
            .strip()
            .casefold()
        )

        candidates = list(
            self.list_resources(
                ListResourcesQuery(
                    resource_type=(
                        query.resource_type
                    ),
                    status=query.status,
                )
            ).resources
        )

        # Legacy substring behavior naturally returns every row for an empty
        # search string, so preserve that behavior during Phase 2.
        if not search_text:
            return ResourceSearchResult(
                query=str(query.text),
                resources=tuple(
                    candidates
                ),
            )

        matches = []

        for resource in candidates:
            searchable = "\n".join(
                (
                    resource.title,
                    resource.resource_type,
                )
            ).casefold()

            if search_text in searchable:
                matches.append(
                    resource
                )

        return ResourceSearchResult(
            query=str(query.text),
            resources=tuple(matches),
        )

    def update_status(
        self,
        command: UpdateResourceStatusCommand,
    ) -> ResourceUpdateResult:
        status = (
            normalise_legacy_resource_status(
                command.status
            )
        )

        current = self.get_resource(
            int(command.position)
        )

        if current is None:
            raise IndexError(
                "Resource position is out of range."
            )

        updated = ResourceView(
            position=current.position,
            title=current.title,
            resource_type=(
                current.resource_type
            ),
            link=current.link,
            status=status,
        )

        stored = (
            self.repository.replace_resource(
                current.position,
                updated.to_legacy_dict(),
            )
        )

        return ResourceUpdateResult(
            resource=ResourceView.from_legacy(
                current.position,
                stored,
            )
        )

    @staticmethod
    def _apply_filters(
        resources,
        resource_type=None,
        status=None,
    ):
        filtered = list(
            resources
        )

        if resource_type is not None:
            wanted_type = (
                str(resource_type)
                .strip()
                .casefold()
            )

            filtered = [
                resource
                for resource in filtered
                if (
                    resource.resource_type
                    .strip()
                    .casefold()
                    == wanted_type
                )
            ]

        if status is not None:
            wanted_status = (
                str(status)
                .strip()
                .casefold()
            )

            filtered = [
                resource
                for resource in filtered
                if (
                    resource.status
                    .strip()
                    .casefold()
                    == wanted_status
                )
            ]

        return filtered
