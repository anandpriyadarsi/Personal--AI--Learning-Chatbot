"""Phase 5.7 MIT 18.06 / external-course knowledge orchestration."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from personal_learning_assistant.domain.external_course_models import (
    ExternalCourseApplyResult,
    ExternalCoursePreview,
)
from personal_learning_assistant.repositories.sqlite.external_course_knowledge_repository import (
    SQLiteExternalCourseKnowledgeRepository,
    resource_external_id,
)
from personal_learning_assistant.services.external_course_crosswalk_service import (
    ExternalCourseCrosswalkError,
    ExternalCourseCrosswalkService,
)


HANDOFF_INDEX_VERSION = "phase5.8-pending-v1"
PACKAGE_PIPELINE_VERSION = "external-course-package-v2-crosswalk"


def _utc_now():
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


class ExternalCourseKnowledgeService:
    def __init__(
        self,
        repository: SQLiteExternalCourseKnowledgeRepository,
        *,
        now=_utc_now,
    ):
        self.repository = repository
        self.crosswalk = ExternalCourseCrosswalkService(repository)
        self._now = now

    @staticmethod
    def source_manifest_hash(package):
        material = "|".join(
            (
                package.course_id,
                package.version,
                package.manifest_sha256,
                package.inventory_sha256,
                package.schema_sha256,
                package.chunks_sha256,
            )
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    @staticmethod
    def extraction_version(package, reviewed_crosswalk=None):
        crosswalk_hash = (
            "none"
            if reviewed_crosswalk is None
            else reviewed_crosswalk.crosswalk_sha256[:16]
        )
        return "{}|{}|{}|xwalk:{}".format(
            PACKAGE_PIPELINE_VERSION,
            package.version,
            package.chunks_sha256[:16],
            crosswalk_hash,
        )

    @staticmethod
    def handoff_index_version(reviewed_crosswalk=None):
        crosswalk_hash = (
            "none"
            if reviewed_crosswalk is None
            else reviewed_crosswalk.crosswalk_sha256[:16]
        )
        return "{}|xwalk:{}".format(HANDOFF_INDEX_VERSION, crosswalk_hash)

    def preview(
        self,
        package,
        *,
        package_key: str,
        local_course_code: str,
        reviewed_crosswalk=None,
    ):
        crosswalk_preview = self.crosswalk.preview(
            package,
            local_course_code=local_course_code,
            reviewed_crosswalk=reviewed_crosswalk,
        )
        local_course_id = crosswalk_preview.local_course_id

        matched_resources = 0
        if self.repository.find_resource_by_external_identity(
            "mit_ocw", resource_external_id(package.course_id)
        ):
            matched_resources += 1
        for lecture in package.lectures:
            if self.repository.find_resource_by_external_identity(
                "mit_ocw",
                resource_external_id(package.course_id, lecture.lecture_number),
            ):
                matched_resources += 1

        document_specs = (
            ("external_course_manifest", "{}/course_manifest.json".format(package_key)),
            ("external_course_inventory", "{}/lecture_inventory.json".format(package_key)),
            ("external_course_schema", "{}/schema.json".format(package_key)),
            ("external_course_chunks", "{}/chunks.jsonl".format(package_key)),
        )
        matched_documents = sum(
            bool(self.repository.find_document_by_path(path_key))
            for _kind, path_key in document_specs
        )
        chunks_document_id = self.repository.find_document_by_path(
            "{}/chunks.jsonl".format(package_key)
        )
        current = False
        if chunks_document_id:
            current = self.repository.extraction_is_current(
                chunks_document_id,
                self.extraction_version(package, reviewed_crosswalk),
                len(package.chunks),
            )

        lecture_chunks = sum(
            chunk.lecture_number is not None for chunk in package.chunks
        )
        return ExternalCoursePreview(
            course_id=package.course_id,
            package_version=package.version,
            lecture_count=len(package.lectures),
            chunk_count=len(package.chunks),
            lecture_chunk_count=lecture_chunks,
            concept_chunk_count=len(package.chunks) - lecture_chunks,
            local_course_code=local_course_code,
            local_course_id=local_course_id,
            unique_topic_label_count=crosswalk_preview.unique_external_label_count,
            mapped_topic_label_count=(
                crosswalk_preview.exact_mapped_label_count
                + crosswalk_preview.reviewed_mapped_label_count
            ),
            unresolved_topic_label_count=(
                crosswalk_preview.reviewed_unresolved_label_count
                + crosswalk_preview.pending_review_label_count
            ),
            ambiguous_topic_label_count=crosswalk_preview.ambiguous_exact_label_count,
            planned_resource_count=1 + len(package.lectures),
            matched_resource_count=matched_resources,
            planned_document_count=4,
            matched_document_count=matched_documents,
            extraction_current=current,
            source_manifest_hash=self.source_manifest_hash(package),
        )

    def apply(
        self,
        package,
        *,
        package_key: str,
        local_course_code: str,
        reviewed_crosswalk,
        require_complete_crosswalk: bool = True,
    ):
        if reviewed_crosswalk is None:
            raise ExternalCourseCrosswalkError(
                "real external-course apply requires a reviewed crosswalk artifact"
            )
        crosswalk_preview = self.crosswalk.preview(
            package,
            local_course_code=local_course_code,
            reviewed_crosswalk=reviewed_crosswalk,
        )
        if require_complete_crosswalk and not crosswalk_preview.crosswalk_complete:
            raise ExternalCourseCrosswalkError(
                "real external-course apply requires every non-exact label to be "
                "reviewed as map or leave_unresolved"
            )

        (
            local_course_id,
            label_topic_ids,
            lecture_topic_ids,
            course_topic_ids,
        ) = self.crosswalk.resolve_all(
            package,
            local_course_code=local_course_code,
            reviewed_crosswalk=reviewed_crosswalk,
        )
        preview = self.preview(
            package,
            package_key=package_key,
            local_course_code=local_course_code,
            reviewed_crosswalk=reviewed_crosswalk,
        )
        applied = self.repository.apply_package(
            package=package,
            package_key=package_key,
            local_course_id=local_course_id,
            lecture_topic_ids=lecture_topic_ids,
            course_topic_ids=course_topic_ids,
            label_topic_ids=label_topic_ids,
            crosswalk_sha256=reviewed_crosswalk.crosswalk_sha256,
            now=self._now(),
            extraction_version=self.extraction_version(package, reviewed_crosswalk),
            handoff_index_version=self.handoff_index_version(reviewed_crosswalk),
        )
        mapped_links = sum(len(set(ids)) for ids in lecture_topic_ids.values())
        return ExternalCourseApplyResult(
            course_resource_id=applied["course_resource_id"],
            lecture_resource_count=len(applied["lecture_resource_ids"]),
            knowledge_document_count=len(applied["document_ids"]),
            chunk_count=len(package.chunks),
            mapped_topic_link_count=mapped_links,
            unresolved_topic_label_count=preview.unresolved_topic_label_count,
            handoff_job_id=applied["handoff_job_id"],
            extraction_version=self.extraction_version(package, reviewed_crosswalk),
        )
