"""Explicit review workflow for MIT 18.06 ↔ MA103N topic reconciliation.

Suggestions are review-only. No fuzzy candidate is ever applied automatically.
"""

from __future__ import annotations

import hashlib
import json
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple

from personal_learning_assistant.domain.external_course_crosswalk_models import (
    CrosswalkPreview,
    CrosswalkSuggestion,
    ReviewedCrosswalk,
    TopicCatalogEntry,
)


CROSSWALK_SCHEMA_VERSION = 1


class ExternalCourseCrosswalkError(RuntimeError):
    pass


def _normalize(value: str) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _manifest_hash(package) -> str:
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


def _canonical_json_sha(value) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def package_labels(package) -> Tuple[str, ...]:
    labels = set()
    for lecture in package.lectures:
        labels.update(lecture.major_concepts)
    for chunk in package.chunks:
        if chunk.topic:
            labels.add(chunk.topic)
        labels.update(chunk.concepts)
    return tuple(sorted((str(item) for item in labels if str(item).strip()), key=str.casefold))


def labels_by_lecture(package):
    result = {lecture.lecture_number: set(lecture.major_concepts) for lecture in package.lectures}
    for chunk in package.chunks:
        refs = set(chunk.lecture_numbers)
        if chunk.lecture_number:
            refs.add(chunk.lecture_number)
        for lecture_number in refs:
            bucket = result.setdefault(lecture_number, set())
            if chunk.topic:
                bucket.add(chunk.topic)
            bucket.update(chunk.concepts)
    return {
        lecture_number: tuple(sorted(labels, key=str.casefold))
        for lecture_number, labels in result.items()
    }


def _score(external_label: str, topic: TopicCatalogEntry):
    source = _normalize(external_label)
    candidates = [(topic.name, "name"), (topic.normalized_name, "normalized_name")]
    candidates.extend((alias, "alias") for alias in topic.aliases)
    best = 0.0
    reasons = []
    source_tokens = set(source.replace("-", " ").split())
    for candidate, kind in candidates:
        target = _normalize(candidate)
        if not target:
            continue
        if source == target:
            return 1.0, ("exact_{}".format(kind),)
        ratio = SequenceMatcher(None, source, target).ratio()
        target_tokens = set(target.replace("-", " ").split())
        union = source_tokens | target_tokens
        jaccard = (len(source_tokens & target_tokens) / len(union)) if union else 0.0
        score = max(ratio, (ratio + jaccard) / 2.0)
        if score > best:
            best = score
            reasons = ["string_similarity"]
            if jaccard >= 0.5:
                reasons.append("token_overlap")
    return round(best, 4), tuple(reasons)


class ExternalCourseCrosswalkService:
    def __init__(self, repository):
        self.repository = repository

    def topic_catalog(self, local_course_code: str):
        course_id = self.repository.course_id_for_code(local_course_code)
        return course_id, self.repository.topic_catalog(course_id)

    def suggestions(
        self,
        external_label: str,
        catalog: Sequence[TopicCatalogEntry],
        *,
        limit: int = 5,
    ) -> Tuple[CrosswalkSuggestion, ...]:
        suggestions = []
        for topic in catalog:
            score, reasons = _score(external_label, topic)
            if score < 0.30:
                continue
            suggestions.append(
                CrosswalkSuggestion(
                    topic_id=topic.topic_id,
                    topic_name=topic.name,
                    score=score,
                    reasons=reasons,
                )
            )
        suggestions.sort(key=lambda item: (-item.score, item.topic_name.casefold(), item.topic_id))
        return tuple(suggestions[:limit])

    def build_template(self, package, *, local_course_code: str):
        local_course_id, catalog = self.topic_catalog(local_course_code)
        topic_index = self.repository.topic_index(local_course_id)
        rows = []
        for label in package_labels(package):
            exact = topic_index.get(_normalize(label), ())
            if len(exact) == 1:
                entry = next(item for item in catalog if item.topic_id == exact[0])
                decision = {
                    "external_label": label,
                    "current_state": "exact_mapped",
                    "decision": "keep_exact",
                    "reviewed": True,
                    "target_topic_id": entry.topic_id,
                    "target_topic_name": entry.name,
                    "review_note": "Exact existing topic/name/alias match.",
                    "suggestions": [],
                }
            else:
                state = "ambiguous_exact" if len(exact) > 1 else "pending_review"
                decision = {
                    "external_label": label,
                    "current_state": state,
                    "decision": "pending",
                    "reviewed": False,
                    "target_topic_id": None,
                    "target_topic_name": None,
                    "review_note": "",
                    "suggestions": [
                        {
                            "topic_id": item.topic_id,
                            "topic_name": item.topic_name,
                            "score": item.score,
                            "reasons": list(item.reasons),
                        }
                        for item in self.suggestions(label, catalog)
                    ],
                }
            rows.append(decision)

        return {
            "schema_version": CROSSWALK_SCHEMA_VERSION,
            "external_course_id": package.course_id,
            "package_version": package.version,
            "source_manifest_hash": _manifest_hash(package),
            "local_course_code": local_course_code,
            "local_course_id": local_course_id,
            "review_instructions": {
                "map": "Set decision='map', reviewed=true, and choose one current target_topic_id/name.",
                "leave_unresolved": "Set decision='leave_unresolved', reviewed=true when the MIT label is out-of-scope or not equivalent.",
                "pending": "Pending entries block real Phase 5.7 apply.",
                "safety": "Suggestions are never auto-applied.",
            },
            "local_topics": [
                {
                    "topic_id": item.topic_id,
                    "name": item.name,
                    "normalized_name": item.normalized_name,
                    "aliases": list(item.aliases),
                }
                for item in catalog
            ],
            "mappings": rows,
        }

    def load_reviewed(
        self,
        path,
        package,
        *,
        local_course_code: str,
        require_complete: bool = False,
    ) -> ReviewedCrosswalk:
        crosswalk_path = Path(path)
        if not crosswalk_path.is_file() or crosswalk_path.is_symlink():
            raise ExternalCourseCrosswalkError(
                "reviewed crosswalk must be an existing regular JSON file"
            )
        raw = crosswalk_path.read_bytes()
        try:
            value = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ExternalCourseCrosswalkError("crosswalk is not valid UTF-8 JSON") from error
        if not isinstance(value, dict):
            raise ExternalCourseCrosswalkError("crosswalk root must be an object")

        local_course_id, catalog = self.topic_catalog(local_course_code)
        catalog_by_id = {item.topic_id: item for item in catalog}
        labels = package_labels(package)
        label_by_norm = {_normalize(label): label for label in labels}

        expected = {
            "schema_version": CROSSWALK_SCHEMA_VERSION,
            "external_course_id": package.course_id,
            "package_version": package.version,
            "source_manifest_hash": _manifest_hash(package),
            "local_course_code": local_course_code,
            "local_course_id": local_course_id,
        }
        for key, expected_value in expected.items():
            if value.get(key) != expected_value:
                raise ExternalCourseCrosswalkError(
                    "crosswalk {} does not match current package/course".format(key)
                )

        rows = value.get("mappings")
        if not isinstance(rows, list):
            raise ExternalCourseCrosswalkError("crosswalk mappings must be a list")

        seen = set()
        reviewed_mappings = {}
        reviewed_unresolved = set()
        topic_index = self.repository.topic_index(local_course_id)
        pending = set()
        ambiguous = set()

        for row in rows:
            if not isinstance(row, dict):
                raise ExternalCourseCrosswalkError("crosswalk mapping row must be an object")
            external_label = str(row.get("external_label") or "").strip()
            norm = _normalize(external_label)
            if norm not in label_by_norm:
                raise ExternalCourseCrosswalkError(
                    "crosswalk contains stale/unknown external label: {}".format(external_label)
                )
            if norm in seen:
                raise ExternalCourseCrosswalkError(
                    "crosswalk contains duplicate external label: {}".format(external_label)
                )
            seen.add(norm)
            exact = topic_index.get(norm, ())
            decision = str(row.get("decision") or "pending")
            reviewed = bool(row.get("reviewed"))

            if len(exact) == 1:
                # Exact known identity cannot be overridden by a review file.
                if decision not in {"keep_exact", "pending"}:
                    raise ExternalCourseCrosswalkError(
                        "exact match cannot be overridden: {}".format(external_label)
                    )
                continue
            if len(exact) > 1:
                ambiguous.add(norm)

            if not reviewed or decision == "pending":
                pending.add(norm)
                continue

            if decision == "leave_unresolved":
                reviewed_unresolved.add(norm)
                continue
            if decision != "map":
                raise ExternalCourseCrosswalkError(
                    "unsupported crosswalk decision {!r}".format(decision)
                )

            topic_id = str(row.get("target_topic_id") or "").strip()
            if topic_id not in catalog_by_id:
                raise ExternalCourseCrosswalkError(
                    "target topic is absent/not active in current course: {}".format(topic_id)
                )
            expected_name = catalog_by_id[topic_id].name
            target_name = str(row.get("target_topic_name") or "").strip()
            if target_name != expected_name:
                raise ExternalCourseCrosswalkError(
                    "target_topic_name drift for {}: expected {!r}".format(
                        external_label, expected_name
                    )
                )
            reviewed_mappings[norm] = topic_id

        missing_rows = set(label_by_norm) - seen
        pending.update(missing_rows)

        canonical_decisions = {
            "schema_version": CROSSWALK_SCHEMA_VERSION,
            "external_course_id": package.course_id,
            "package_version": package.version,
            "source_manifest_hash": _manifest_hash(package),
            "local_course_code": local_course_code,
            "local_course_id": local_course_id,
            "mapped": sorted(reviewed_mappings.items()),
            "reviewed_unresolved": sorted(reviewed_unresolved),
        }
        digest = _canonical_json_sha(canonical_decisions)
        complete = not pending
        if require_complete and not complete:
            raise ExternalCourseCrosswalkError(
                "reviewed crosswalk is incomplete; {} label(s) remain pending".format(
                    len(pending)
                )
            )
        return ReviewedCrosswalk(
            schema_version=CROSSWALK_SCHEMA_VERSION,
            external_course_id=package.course_id,
            package_version=package.version,
            source_manifest_hash=_manifest_hash(package),
            local_course_code=local_course_code,
            local_course_id=local_course_id,
            mappings=dict(reviewed_mappings),
            reviewed_unresolved=tuple(sorted(reviewed_unresolved)),
            crosswalk_sha256=digest,
            complete=complete,
        )

    def preview(
        self,
        package,
        *,
        local_course_code: str,
        reviewed_crosswalk: Optional[ReviewedCrosswalk] = None,
    ) -> CrosswalkPreview:
        local_course_id, _catalog = self.topic_catalog(local_course_code)
        topic_index = self.repository.topic_index(local_course_id)
        exact = 0
        reviewed = 0
        reviewed_unresolved = 0
        pending = 0
        ambiguous = 0
        for label in package_labels(package):
            norm = _normalize(label)
            matches = topic_index.get(norm, ())
            if len(matches) == 1:
                exact += 1
                continue
            if len(matches) > 1:
                ambiguous += 1
            if reviewed_crosswalk and norm in reviewed_crosswalk.mappings:
                reviewed += 1
            elif reviewed_crosswalk and norm in set(reviewed_crosswalk.reviewed_unresolved):
                reviewed_unresolved += 1
            else:
                pending += 1
        return CrosswalkPreview(
            external_course_id=package.course_id,
            package_version=package.version,
            local_course_code=local_course_code,
            local_course_id=local_course_id,
            unique_external_label_count=len(package_labels(package)),
            exact_mapped_label_count=exact,
            reviewed_mapped_label_count=reviewed,
            reviewed_unresolved_label_count=reviewed_unresolved,
            pending_review_label_count=pending,
            ambiguous_exact_label_count=ambiguous,
            crosswalk_complete=(pending == 0),
            crosswalk_sha256=(
                "" if reviewed_crosswalk is None else reviewed_crosswalk.crosswalk_sha256
            ),
        )

    def resolve_all(
        self,
        package,
        *,
        local_course_code: str,
        reviewed_crosswalk: Optional[ReviewedCrosswalk] = None,
    ):
        local_course_id = self.repository.course_id_for_code(local_course_code)
        topic_index = self.repository.topic_index(local_course_id)
        label_topic_ids = {}
        for label in package_labels(package):
            norm = _normalize(label)
            exact = topic_index.get(norm, ())
            if len(exact) == 1:
                label_topic_ids[norm] = exact[0]
            elif reviewed_crosswalk and norm in reviewed_crosswalk.mappings:
                label_topic_ids[norm] = reviewed_crosswalk.mappings[norm]

        lecture_topic_ids = {}
        for lecture_number, labels in labels_by_lecture(package).items():
            ids = {
                label_topic_ids[_normalize(label)]
                for label in labels
                if _normalize(label) in label_topic_ids
            }
            lecture_topic_ids[lecture_number] = tuple(sorted(ids))

        course_topic_ids = tuple(sorted(set(label_topic_ids.values())))
        return local_course_id, label_topic_ids, lecture_topic_ids, course_topic_ids
