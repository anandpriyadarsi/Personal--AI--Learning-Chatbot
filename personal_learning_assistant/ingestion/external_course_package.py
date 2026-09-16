"""Read-only MIT 18.06 external-course package reader/validator.

The package is treated as supplied evidence. This module does not fetch MIT
pages, rewrite package files, or relabel the package as MA103N.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Optional, Tuple

from personal_learning_assistant.domain.external_course_models import (
    ExternalCoursePackage,
    ExternalKnowledgeChunk,
    ExternalLecture,
)


EXPECTED_COURSE_ID = "mit-18.06-linear-algebra"
_REQUIRED_FILES = (
    "course_manifest.json",
    "lecture_inventory.json",
    "schema.json",
    "chunks.jsonl",
)
_REQUIRED_CHUNK_FIELDS = {
    "chunk_id",
    "chunk_type",
    "course",
    "course_id",
    "instructor",
    "lecture_number",
    "lecture_numbers",
    "lecture_title",
    "topic",
    "concepts",
    "prerequisites",
    "related_concepts",
    "nitk_weeks",
    "priority",
    "text",
    "source",
    "source_url",
    "supporting_source_urls",
    "retrieval_queries",
    "answer_modes",
    "content_version",
    "content_hash",
}


class ExternalCoursePackageError(RuntimeError):
    pass


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_stable(path: Path) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise ExternalCoursePackageError(
            "required package source is missing/not a regular file: {}".format(path.name)
        )
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise ExternalCoursePackageError(
            "package source changed while being read: {}".format(path.name)
        )
    return raw


def _json(raw: bytes, label: str):
    try:
        value = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExternalCoursePackageError("{} is not valid UTF-8 JSON".format(label)) from error
    return value


def _strings(value, label: str) -> Tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ExternalCoursePackageError("{} must be an array of strings".format(label))
    return tuple(value)


def _official_mit_url(value: str, label: str) -> str:
    text = str(value or "").strip()
    if not text.startswith("https://ocw.mit.edu/"):
        raise ExternalCoursePackageError(
            "{} must preserve an official https://ocw.mit.edu/ URL".format(label)
        )
    return text


class MIT1806PackageReader:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=False)
        if not self.root.is_dir() or self.root.is_symlink():
            raise ExternalCoursePackageError(
                "package root must be an existing non-symlink directory"
            )

    def load(self) -> ExternalCoursePackage:
        raw_files = {
            name: _read_stable(self.root / name)
            for name in _REQUIRED_FILES
        }
        manifest = _json(raw_files["course_manifest.json"], "course_manifest.json")
        inventory = _json(raw_files["lecture_inventory.json"], "lecture_inventory.json")
        schema = _json(raw_files["schema.json"], "schema.json")

        if not isinstance(manifest, dict):
            raise ExternalCoursePackageError("course manifest must be an object")
        if manifest.get("course_id") != EXPECTED_COURSE_ID:
            raise ExternalCoursePackageError(
                "unexpected external course_id: {!r}".format(manifest.get("course_id"))
            )
        if not isinstance(inventory, list):
            raise ExternalCoursePackageError("lecture inventory must be a list")
        if not isinstance(schema, dict):
            raise ExternalCoursePackageError("schema.json must be an object")

        course_title = str(manifest.get("course") or "").strip()
        instructor = str(manifest.get("instructor") or "").strip()
        version = str(manifest.get("version") or "").strip()
        if not course_title or not instructor or not version:
            raise ExternalCoursePackageError(
                "manifest course/instructor/version are required"
            )
        source_policy = _strings(manifest.get("source_policy"), "manifest.source_policy")
        official_hubs = manifest.get("official_hubs")
        if not isinstance(official_hubs, dict):
            raise ExternalCoursePackageError("manifest.official_hubs must be an object")
        for key, url in official_hubs.items():
            _official_mit_url(url, "official_hubs.{}".format(key))

        lectures = []
        lecture_numbers = set()
        for item in inventory:
            if not isinstance(item, dict):
                raise ExternalCoursePackageError("lecture inventory row must be an object")
            number = str(item.get("lecture_number") or "").strip()
            title = str(item.get("lecture_title") or "").strip()
            url = _official_mit_url(
                item.get("official_lecture_url"),
                "lecture {} official_lecture_url".format(number or "?"),
            )
            if not number or not title:
                raise ExternalCoursePackageError(
                    "lecture_number and lecture_title are required"
                )
            if number in lecture_numbers:
                raise ExternalCoursePackageError(
                    "duplicate lecture_number: {}".format(number)
                )
            lecture_numbers.add(number)
            lectures.append(
                ExternalLecture(
                    lecture_number=number,
                    lecture_title=title,
                    official_lecture_url=url,
                    major_concepts=_strings(
                        item.get("major_concepts"), "lecture.major_concepts"
                    ),
                    prerequisites=_strings(
                        item.get("prerequisites"), "lecture.prerequisites"
                    ),
                    nitk_weeks=_strings(item.get("nitk_weeks"), "lecture.nitk_weeks"),
                    nitk_alignment=str(item.get("nitk_alignment") or ""),
                    priority=str(item.get("priority") or ""),
                    raw=dict(item),
                )
            )

        chunks = []
        chunk_ids = set()
        for line_number, raw_line in enumerate(
            raw_files["chunks.jsonl"].decode("utf-8-sig").splitlines(), 1
        ):
            if not raw_line.strip():
                continue
            try:
                item = json.loads(raw_line)
            except json.JSONDecodeError as error:
                raise ExternalCoursePackageError(
                    "chunks.jsonl line {} is invalid JSON".format(line_number)
                ) from error
            if not isinstance(item, dict):
                raise ExternalCoursePackageError(
                    "chunks.jsonl line {} is not an object".format(line_number)
                )
            missing = sorted(_REQUIRED_CHUNK_FIELDS - set(item))
            if missing:
                raise ExternalCoursePackageError(
                    "chunk {} missing fields: {}".format(line_number, ", ".join(missing))
                )
            if item.get("course_id") != EXPECTED_COURSE_ID:
                raise ExternalCoursePackageError(
                    "chunk {} has wrong course_id".format(line_number)
                )
            if str(item.get("course")) != course_title:
                raise ExternalCoursePackageError(
                    "chunk {} course title differs from manifest".format(line_number)
                )
            if str(item.get("instructor")) != instructor:
                raise ExternalCoursePackageError(
                    "chunk {} instructor differs from manifest".format(line_number)
                )
            chunk_id = str(item.get("chunk_id") or "").strip()
            if not chunk_id or chunk_id in chunk_ids:
                raise ExternalCoursePackageError(
                    "chunk_id is empty/duplicated at line {}".format(line_number)
                )
            chunk_ids.add(chunk_id)
            text = str(item.get("text") or "")
            content_hash = str(item.get("content_hash") or "").casefold()
            if _sha256(text.encode("utf-8")) != content_hash:
                raise ExternalCoursePackageError(
                    "chunk {} content_hash does not match exact text".format(chunk_id)
                )
            lecture_number = item.get("lecture_number")
            lecture_number = (
                None if lecture_number is None else str(lecture_number)
            )
            lecture_refs = _strings(
                item.get("lecture_numbers"), "chunk.lecture_numbers"
            )
            for ref in lecture_refs:
                if ref not in lecture_numbers:
                    raise ExternalCoursePackageError(
                        "chunk {} references unknown lecture {}".format(chunk_id, ref)
                    )
            if lecture_number is not None and lecture_number not in lecture_numbers:
                raise ExternalCoursePackageError(
                    "chunk {} references unknown lecture {}".format(
                        chunk_id, lecture_number
                    )
                )
            source = item.get("source")
            if not isinstance(source, dict):
                raise ExternalCoursePackageError(
                    "chunk {} source must be an object".format(chunk_id)
                )
            if source.get("provider") != "MIT OpenCourseWare":
                raise ExternalCoursePackageError(
                    "chunk {} source provider is not MIT OpenCourseWare".format(chunk_id)
                )
            source_url = _official_mit_url(
                item.get("source_url"), "chunk {} source_url".format(chunk_id)
            )
            supporting_urls = _strings(
                item.get("supporting_source_urls"),
                "chunk.supporting_source_urls",
            )
            for index, url in enumerate(supporting_urls):
                _official_mit_url(
                    url,
                    "chunk {} supporting_source_urls[{}]".format(chunk_id, index),
                )
            chunks.append(
                ExternalKnowledgeChunk(
                    chunk_id=chunk_id,
                    chunk_type=str(item.get("chunk_type") or ""),
                    lecture_number=lecture_number,
                    lecture_numbers=lecture_refs,
                    lecture_title=(
                        None
                        if item.get("lecture_title") is None
                        else str(item.get("lecture_title"))
                    ),
                    topic=str(item.get("topic") or ""),
                    concepts=_strings(item.get("concepts"), "chunk.concepts"),
                    prerequisites=_strings(
                        item.get("prerequisites"), "chunk.prerequisites"
                    ),
                    related_concepts=_strings(
                        item.get("related_concepts"), "chunk.related_concepts"
                    ),
                    nitk_weeks=_strings(item.get("nitk_weeks"), "chunk.nitk_weeks"),
                    priority=str(item.get("priority") or ""),
                    text=text,
                    source=dict(source),
                    source_url=source_url,
                    supporting_source_urls=supporting_urls,
                    retrieval_queries=_strings(
                        item.get("retrieval_queries"), "chunk.retrieval_queries"
                    ),
                    answer_modes=_strings(
                        item.get("answer_modes"), "chunk.answer_modes"
                    ),
                    content_version=str(item.get("content_version") or ""),
                    content_hash=content_hash,
                )
            )

        counts = manifest.get("counts")
        if not isinstance(counts, dict):
            raise ExternalCoursePackageError("manifest.counts must be an object")
        expected_lectures = int(counts.get("lecture_inventory_records", -1))
        expected_chunks = int(counts.get("rag_chunks", -1))
        lecture_chunks = sum(chunk.lecture_number is not None for chunk in chunks)
        concept_chunks = len(chunks) - lecture_chunks
        if len(lectures) != expected_lectures:
            raise ExternalCoursePackageError(
                "manifest lecture count {} != actual {}".format(
                    expected_lectures, len(lectures)
                )
            )
        if len(chunks) != expected_chunks:
            raise ExternalCoursePackageError(
                "manifest chunk count {} != actual {}".format(
                    expected_chunks, len(chunks)
                )
            )
        if int(counts.get("lecture_chunks", lecture_chunks)) != lecture_chunks:
            raise ExternalCoursePackageError("manifest lecture_chunks count differs")
        if int(counts.get("concept_chunks", concept_chunks)) != concept_chunks:
            raise ExternalCoursePackageError("manifest concept_chunks count differs")

        return ExternalCoursePackage(
            root=str(self.root),
            course_id=EXPECTED_COURSE_ID,
            course_title=course_title,
            instructor=instructor,
            version=version,
            source_policy=source_policy,
            official_hubs={str(k): str(v) for k, v in official_hubs.items()},
            manifest=dict(manifest),
            lectures=tuple(lectures),
            chunks=tuple(chunks),
            manifest_sha256=_sha256(raw_files["course_manifest.json"]),
            inventory_sha256=_sha256(raw_files["lecture_inventory.json"]),
            schema_sha256=_sha256(raw_files["schema.json"]),
            chunks_sha256=_sha256(raw_files["chunks.jsonl"]),
            manifest_size=len(raw_files["course_manifest.json"]),
            inventory_size=len(raw_files["lecture_inventory.json"]),
            schema_size=len(raw_files["schema.json"]),
            chunks_size=len(raw_files["chunks.jsonl"]),
        )


def discover_mit1806_package(vault_root) -> Path:
    root = Path(vault_root).resolve(strict=False)
    if not root.is_dir() or root.is_symlink():
        raise ExternalCoursePackageError(
            "configured vault root must be an existing non-symlink directory"
        )
    matches = []
    for current_root, dir_names, file_names in os.walk(
        str(root), topdown=True, followlinks=False
    ):
        current = Path(current_root)
        dir_names[:] = [
            name
            for name in dir_names
            if not (current / name).is_symlink()
        ]
        if "course_manifest.json" not in file_names:
            continue
        candidate = current
        try:
            raw = _read_stable(candidate / "course_manifest.json")
            value = _json(raw, "course_manifest.json")
        except ExternalCoursePackageError:
            continue
        if isinstance(value, dict) and value.get("course_id") == EXPECTED_COURSE_ID:
            if all((candidate / name).is_file() for name in _REQUIRED_FILES):
                matches.append(candidate)
    if not matches:
        raise ExternalCoursePackageError(
            "MIT 18.06 Chatbot Knowledge package was not found in the configured vault"
        )
    unique = sorted(set(path.resolve(strict=False) for path in matches))
    if len(unique) != 1:
        raise ExternalCoursePackageError(
            "multiple MIT 18.06 package roots found; pass --package-root explicitly"
        )
    return unique[0]
