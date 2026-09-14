"""Read-only course context used by the Phase 2 knowledge compatibility layer.

JSON remains authoritative during Phase 2.  This adapter intentionally reads
the existing courses.json state without importing the legacy course_manager
facade and without creating or rewriting any file.
"""

from __future__ import annotations

import json
import os
import re
from typing import Callable, Optional


class LegacyJsonCourseKnowledgeContext:
    """Read-only course/document metadata view over legacy courses.json."""

    def __init__(
        self,
        courses_file,
        base_dir,
        vault_path_provider: Optional[Callable[[], Optional[str]]] = None,
    ):
        self.courses_file = os.path.abspath(
            os.fspath(courses_file)
        )
        self.base_dir = os.path.abspath(
            os.fspath(base_dir)
        )
        self.vault_path_provider = vault_path_provider

    @staticmethod
    def _clean_text(value):
        return " ".join(
            str(value or "")
            .strip()
            .split()
        )

    @staticmethod
    def _slug(value):
        value = re.sub(
            r"[^a-z0-9]+",
            "-",
            str(value or "").lower(),
        ).strip("-")
        return value or "course"

    def _load_state(self):
        if not os.path.exists(
            self.courses_file
        ):
            return {
                "courses": [],
                "document_links": {},
            }

        try:
            with open(
                self.courses_file,
                "r",
                encoding="utf-8",
            ) as file:
                payload = json.load(file)
        except (
            OSError,
            json.JSONDecodeError,
        ):
            return {
                "courses": [],
                "document_links": {},
            }

        if not isinstance(
            payload,
            dict,
        ):
            return {
                "courses": [],
                "document_links": {},
            }

        raw_courses = payload.get(
            "courses",
            [],
        )
        if not isinstance(
            raw_courses,
            list,
        ):
            raw_courses = []

        courses = []
        used_ids = set()

        for raw in raw_courses:
            if not isinstance(
                raw,
                dict,
            ):
                continue

            code = self._clean_text(
                raw.get("code")
            ).upper()
            name = self._clean_text(
                raw.get("name")
            )
            course_id = self._clean_text(
                raw.get("id")
            )

            if not course_id:
                course_id = self._slug(
                    code or name
                )

            base_id = course_id
            suffix = 2

            while course_id in used_ids:
                course_id = (
                    f"{base_id}-{suffix}"
                )
                suffix += 1

            if not (
                code
                or name
            ):
                continue

            used_ids.add(
                course_id
            )

            course = dict(raw)
            course["id"] = course_id
            course["code"] = code
            course["name"] = name
            courses.append(
                course
            )

        links = payload.get(
            "document_links",
            {},
        )
        if not isinstance(
            links,
            dict,
        ):
            links = {}

        clean_links = {
            str(key): dict(value)
            for key, value in links.items()
            if isinstance(
                value,
                dict,
            )
        }

        return {
            "courses": courses,
            "document_links": clean_links,
        }

    def find_course(
        self,
        identifier,
    ):
        wanted = self._clean_text(
            identifier
        ).casefold()

        if not wanted:
            return None

        for course in (
            self._load_state()[
                "courses"
            ]
        ):
            candidates = {
                self._clean_text(
                    course.get("id")
                ).casefold(),
                self._clean_text(
                    course.get("code")
                ).casefold(),
                self._clean_text(
                    course.get("name")
                ).casefold(),
            }

            if wanted in candidates:
                return dict(
                    course
                )

        return None

    @staticmethod
    def _is_inside(
        path,
        parent,
    ):
        try:
            return os.path.commonpath(
                [
                    os.path.abspath(path),
                    os.path.abspath(parent),
                ]
            ) == os.path.abspath(
                parent
            )
        except (
            ValueError,
            OSError,
        ):
            return False

    def _vault_path(self):
        if (
            self.vault_path_provider
            is None
        ):
            return None

        try:
            value = (
                self.vault_path_provider()
            )
        except OSError:
            return None

        if not value:
            return None

        return os.path.abspath(
            os.fspath(value)
        )

    def canonical_document_key(
        self,
        file_path,
    ):
        absolute = os.path.abspath(
            os.fspath(file_path)
        )
        vault = self._vault_path()

        if (
            vault
            and self._is_inside(
                absolute,
                vault,
            )
        ):
            relative = os.path.relpath(
                absolute,
                vault,
            )
            return (
                "obsidian:"
                + relative.replace(
                    "\\",
                    "/",
                )
            )

        if self._is_inside(
            absolute,
            self.base_dir,
        ):
            relative = os.path.relpath(
                absolute,
                self.base_dir,
            )
            return (
                "base:"
                + relative.replace(
                    "\\",
                    "/",
                )
            )

        return (
            "external:"
            + os.path.normcase(
                absolute
            ).replace(
                "\\",
                "/",
            )
        )

    def _document_link(
        self,
        file_path,
    ):
        state = self._load_state()
        key = self.canonical_document_key(
            file_path
        )
        value = state[
            "document_links"
        ].get(
            key
        )

        if not isinstance(
            value,
            dict,
        ):
            return None

        return dict(
            value
        )

    @staticmethod
    def _read_tag_header(
        file_path,
    ):
        extension = os.path.splitext(
            str(file_path)
        )[1].lower()

        if extension not in {
            ".md",
            ".txt",
        }:
            return ""

        for encoding in (
            "utf-8",
            "latin-1",
        ):
            try:
                with open(
                    file_path,
                    "r",
                    encoding=encoding,
                ) as file:
                    return file.read(
                        5000
                    )
            except UnicodeDecodeError:
                continue
            except OSError:
                return ""

        return ""

    def _tagged_course_from_content(
        self,
        content,
        courses,
    ):
        header = (
            content
            or ""
        )[:5000]

        values = []
        patterns = (
            r'(?im)^\s*(?:course|course_code)\s*:\s*["\']?([^\n"\']+)',
            r"(?i)\[\s*course\s*:\s*([^\]]+)\]",
        )

        for pattern in patterns:
            values.extend(
                re.findall(
                    pattern,
                    header,
                )
            )

        for value in values:
            wanted = self._clean_text(
                value
            ).casefold()

            for course in courses:
                if wanted in {
                    self._clean_text(
                        course.get(
                            "id"
                        )
                    ).casefold(),
                    self._clean_text(
                        course.get(
                            "code"
                        )
                    ).casefold(),
                    self._clean_text(
                        course.get(
                            "name"
                        )
                    ).casefold(),
                }:
                    return dict(
                        course
                    )

        return None

    def _tagged_topic_from_content(
        self,
        content,
    ):
        header = (
            content
            or ""
        )[:5000]

        patterns = (
            r'(?im)^\s*topic\s*:\s*["\']?([^\n"\']+)',
            r"(?i)\[\s*topic\s*:\s*([^\]]+)\]",
        )

        for pattern in patterns:
            match = re.search(
                pattern,
                header,
            )
            if match:
                return self._clean_text(
                    match.group(1)
                )

        return ""

    @staticmethod
    def _infer_source_type(
        file_path,
    ):
        path = (
            str(file_path)
            .lower()
            .replace(
                "\\",
                "/",
            )
        )
        extension = os.path.splitext(
            path
        )[1]

        if (
            "youtube" in path
            or "transcript" in path
        ):
            return "youtube_lecture"

        if (
            "obsidian" in path
            or path.endswith(".md")
        ):
            return "obsidian_note"

        if extension == ".pdf":
            return "course_pdf"

        if extension == ".txt":
            return "text_note"

        return "document"

    def identify_course_for_document(
        self,
        file_path,
        content=None,
    ):
        state = self._load_state()
        courses = state[
            "courses"
        ]

        link = self._document_link(
            file_path
        )

        if link:
            linked = self.find_course(
                link.get(
                    "course_id"
                )
            )
            if linked:
                return linked

        if content is None:
            content = self._read_tag_header(
                file_path
            )

        tagged = (
            self._tagged_course_from_content(
                content,
                courses,
            )
        )

        if tagged:
            return tagged

        searchable_path = re.sub(
            r"[^a-z0-9]+",
            " ",
            str(
                file_path
            ).lower(),
        )
        padded_path = (
            " "
            + searchable_path
            + " "
        )

        for course in courses:
            code = re.sub(
                r"[^a-z0-9]+",
                " ",
                self._clean_text(
                    course.get(
                        "code"
                    )
                ).lower(),
            ).strip()

            name = re.sub(
                r"[^a-z0-9]+",
                " ",
                self._clean_text(
                    course.get(
                        "name"
                    )
                ).lower(),
            ).strip()

            if (
                code
                and f" {code} "
                in padded_path
            ):
                return dict(
                    course
                )

            if (
                name
                and f" {name} "
                in padded_path
            ):
                return dict(
                    course
                )

        return None

    def get_document_metadata(
        self,
        file_path,
        content=None,
    ):
        link = self._document_link(
            file_path
        )

        if content is None:
            content = self._read_tag_header(
                file_path
            )

        course = (
            self.identify_course_for_document(
                file_path,
                content,
            )
        )

        return {
            "course_id": (
                course.get("id")
                if course
                else None
            ),
            "course_code": (
                course.get("code")
                if course
                else None
            ),
            "course_name": (
                course.get("name")
                if course
                else None
            ),
            "topic": (
                link.get("topic")
                if (
                    link
                    and link.get(
                        "topic"
                    )
                )
                else (
                    self
                    ._tagged_topic_from_content(
                        content
                    )
                )
            ),
            "source_type": (
                link.get(
                    "source_type"
                )
                if link
                else (
                    self
                    ._infer_source_type(
                        file_path
                    )
                )
            ),
            "document_key": (
                self
                .canonical_document_key(
                    file_path
                )
            ),
        }
