"""Legacy JSON course repository.

This adapter intentionally reuses the current V8 course normalization logic so
Phase 2 can introduce services without changing the JSON schema or authority.
"""

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Optional

import personal_learning_assistant.domain.course_normalization as course_manager

from personal_learning_assistant.repositories.authority_guard import (
    guard_legacy_structured_write,
    infer_authority_control_path,
)
from personal_learning_assistant.repositories.interfaces import CourseState


class LegacyJsonCourseRepository:
    """Read/write adapter for the existing ``data/courses.json`` store."""

    def __init__(
        self,
        path: Optional[os.PathLike] = None,
        *,
        authority_control_path: Optional[os.PathLike] = None,
    ):
        self.path = Path(
            path
            if path is not None
            else course_manager.COURSES_FILE
        )
        self.authority_control_path = Path(
            authority_control_path
            if authority_control_path is not None
            else infer_authority_control_path(self.path)
        )

    def load_state(self) -> CourseState:
        """
        Load and normalize existing state without creating a missing file.

        Existing JSON remains the structured authority throughout Phase 2.
        """
        if not self.path.exists():
            return deepcopy(
                course_manager.default_course_data()
            )

        try:
            with self.path.open(
                "r",
                encoding="utf-8",
            ) as file:
                raw = json.load(file)
        except (json.JSONDecodeError, OSError):
            return deepcopy(
                course_manager.default_course_data()
            )

        return deepcopy(
            course_manager._normalise_data(raw)
        )

    def save_state(
        self,
        state: CourseState,
    ) -> CourseState:
        """Explicitly persist using the current legacy normalization rules."""
        guard_legacy_structured_write(self.authority_control_path)
        normalized = course_manager._normalise_data(
            state
        )

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = self.path.with_name(
            self.path.name + ".tmp"
        )

        with temporary_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                normalized,
                file,
                indent=2,
                ensure_ascii=False,
            )

        os.replace(
            temporary_path,
            self.path,
        )

        return deepcopy(normalized)

    def get_document_link(
        self,
        document_key: str,
    ):
        state = self.load_state()
        link = state.get(
            "document_links",
            {},
        ).get(
            document_key
        )

        if link is None:
            return None

        return deepcopy(link)

    def list_document_links(self):
        state = self.load_state()

        return deepcopy(
            state.get(
                "document_links",
                {},
            )
        )

    def upsert_document_link(
        self,
        document_key: str,
        link,
    ):
        state = self.load_state()
        state.setdefault(
            "document_links",
            {},
        )[document_key] = dict(link)

        saved = self.save_state(
            state
        )

        return deepcopy(
            saved["document_links"][
                document_key
            ]
        )

    def delete_document_link(
        self,
        document_key: str,
    ) -> bool:
        state = self.load_state()
        links = state.setdefault(
            "document_links",
            {},
        )

        if document_key not in links:
            return False

        del links[document_key]
        self.save_state(
            state
        )
        return True

