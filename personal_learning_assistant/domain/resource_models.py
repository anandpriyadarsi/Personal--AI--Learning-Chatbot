"""Typed models for the legacy JSON Resources subsystem.

Phase 2 keeps ``data/resources.json`` as the only structured authority.
These dataclasses provide a non-interactive service boundary without changing
the legacy resource record shape.
"""

from dataclasses import dataclass
from typing import Optional, Tuple


LEGACY_RESOURCE_STATUSES = (
    "Not Started",
    "In Progress",
    "Completed",
)

_STATUS_ALIASES = {
    "not started": "Not Started",
    "not_started": "Not Started",
    "not-started": "Not Started",
    "in progress": "In Progress",
    "in_progress": "In Progress",
    "in-progress": "In Progress",
    "completed": "Completed",
}


def normalise_legacy_resource_status(value: str) -> str:
    """Return one of the exact V1 status labels accepted for mutations."""
    normalised = " ".join(
        str(value or "").strip().split()
    ).casefold()

    try:
        return _STATUS_ALIASES[normalised]
    except KeyError as error:
        raise ValueError(
            "Status must be Not Started, In Progress, or Completed."
        ) from error


@dataclass(frozen=True)
class ResourceView:
    """Typed view of one legacy resource row."""

    position: int
    title: str
    resource_type: str
    link: str
    status: str

    @classmethod
    def from_legacy(cls, position: int, data):
        return cls(
            position=int(position),
            title=str(data.get("title", "")),
            resource_type=str(data.get("type", "")),
            link=str(data.get("link", "")),
            status=str(
                data.get(
                    "status",
                    "Not Started",
                )
            ),
        )

    def to_legacy_dict(self):
        return {
            "title": self.title,
            "type": self.resource_type,
            "link": self.link,
            "status": self.status,
        }


@dataclass(frozen=True)
class CreateResourceCommand:
    title: str
    resource_type: str
    link: str


@dataclass(frozen=True)
class UpdateResourceStatusCommand:
    position: int
    status: str


@dataclass(frozen=True)
class ListResourcesQuery:
    resource_type: Optional[str] = None
    status: Optional[str] = None


@dataclass(frozen=True)
class SearchResourcesQuery:
    text: str
    resource_type: Optional[str] = None
    status: Optional[str] = None


@dataclass(frozen=True)
class ResourceCreateResult:
    resource: ResourceView


@dataclass(frozen=True)
class ResourceUpdateResult:
    resource: ResourceView


@dataclass(frozen=True)
class ResourceListResult:
    resources: Tuple[ResourceView, ...]


@dataclass(frozen=True)
class ResourceCountResult:
    count: int


@dataclass(frozen=True)
class ResourceSearchResult:
    query: str
    resources: Tuple[ResourceView, ...]
