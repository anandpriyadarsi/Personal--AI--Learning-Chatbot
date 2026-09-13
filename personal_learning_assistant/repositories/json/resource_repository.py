"""Legacy JSON adapter for ``data/resources.json``.

Reads are deliberately side-effect free.  In particular, the supplied legacy
``resources.json`` may be a zero-byte file; reading it must represent zero
resources without rewriting the source as ``[]``.

Explicit write commands use atomic replacement and keep the V1 JSON list shape.
"""

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Optional

from config import RESOURCES_FILE


class LegacyJsonResourceRepository:
    """Repository over the current V1 resources JSON store."""

    def __init__(
        self,
        path: Optional[str] = None,
    ):
        self.path = Path(
            path
            if path is not None
            else RESOURCES_FILE
        )

    def load_resources(self):
        if not self.path.exists():
            return []

        try:
            raw_text = self.path.read_text(
                encoding="utf-8"
            )
        except OSError:
            return []

        if not raw_text.strip():
            return []

        try:
            data = json.loads(
                raw_text
            )
        except json.JSONDecodeError:
            return []

        if not isinstance(
            data,
            list,
        ):
            return []

        resources = []

        for item in data:
            if isinstance(
                item,
                dict,
            ):
                resources.append(
                    deepcopy(item)
                )

        return resources

    def save_resources(
        self,
        resources,
    ):
        """Atomically replace the legacy list after an explicit command."""
        payload = [
            deepcopy(
                dict(resource)
            )
            for resource in resources
        ]

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = self.path.with_name(
            self.path.name + ".tmp"
        )

        try:
            text = json.dumps(
                payload,
                indent=4,
                ensure_ascii=False,
            )

            temporary_path.write_text(
                text,
                encoding="utf-8",
            )

            os.replace(
                temporary_path,
                self.path,
            )
        finally:
            if temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

        return [
            deepcopy(item)
            for item in payload
        ]

    def append_resource(
        self,
        resource,
    ):
        resources = self.load_resources()

        stored_resource = deepcopy(
            dict(resource)
        )

        resources.append(
            stored_resource
        )

        self.save_resources(
            resources
        )

        return deepcopy(
            stored_resource
        )

    def replace_resource(
        self,
        position: int,
        resource,
    ):
        """Replace one 1-based legacy row through an explicit command."""
        resources = self.load_resources()

        if (
            position < 1
            or position > len(resources)
        ):
            raise IndexError(
                "Resource position is out of range."
            )

        stored_resource = deepcopy(
            dict(resource)
        )

        resources[
            position - 1
        ] = stored_resource

        self.save_resources(
            resources
        )

        return deepcopy(
            stored_resource
        )
