from __future__ import annotations

import json
from pathlib import Path

import pytest

from personal_learning_assistant.domain.canonical_topic_catalogues import (
    CANONICAL_TOPIC_CATALOGUES,
    UC103N_CANONICAL_TOPICS,
)
from personal_learning_assistant.services.canonical_topic_catalogue_service import (
    CanonicalTopicCatalogueService,
)


COURSES = (
    ("MA103N", "Linear Algebra"),
    ("UC100N", "Data Science and Artificial Intelligence"),
    ("CY100N", "Engineering Chemistry"),
    ("DE100N", "Design Thinking and Prototyping"),
    ("UC103N", "Indian Knowledge System"),
)


def _write_courses(path: Path):
    payload = {
        "version": 1,
        "active_course_id": "ma103n",
        "courses": [],
        "document_links": {},
    }
    for code, name in COURSES:
        topics = []
        if code == "MA103N":
            topics = [
                {
                    "name": "System of Linear Equations",
                    "status": "weak",
                    "confidence": 2,
                    "last_updated": "2026-09-20T10:00:00",
                },
                {
                    "name": "LU Factorization",
                    "status": "learning",
                    "confidence": 1,
                    "last_updated": "2026-09-21T10:00:00",
                },
            ]
        payload["courses"].append(
            {
                "id": code.casefold(),
                "code": code,
                "name": name,
                "semester": "1",
                "status": "active",
                "topics": topics,
                "created_at": "2026-08-20T00:00:00",
                "updated_at": "2026-08-20T00:00:00",
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_catalogue_has_unique_names_and_unambiguous_aliases():
    for code, catalogue in CANONICAL_TOPIC_CATALOGUES.items():
        canonical = {}
        alias_owner = {}
        for item in catalogue:
            name = str(item["name"]).strip()
            key = name.casefold()
            assert name
            assert key not in canonical, (code, name)
            canonical[key] = name
        for item in catalogue:
            name = str(item["name"]).strip()
            for alias in item.get("aliases", ()):
                key = str(alias).strip().casefold()
                assert key
                assert canonical.get(key, name) == name, (code, alias)
                assert alias_owner.get(key, name) == name, (code, alias)
                alias_owner[key] = name


def test_uc103n_catalogue_covers_every_current_90q_raw_topic_label():
    # Exact unique raw labels from UC103N.iks.90q.practice-test.001 rev-1 handoff.
    raw_labels = {
        "Introduction to the Vedas", "Genesis of Vedic literature", "Oral transmission",
        "Organisation of Vedic knowledge", "Four divisions of each Veda", "Saṃhitā",
        "Brāhmaṇa", "Āraṇyaka", "Upaniṣad", "Rigveda", "Yajurveda", "Sāmaveda",
        "Atharvaveda", "Notable Rigvedic hymns", "Notable Atharvavedic hymns",
        "Upavedas", "Vedāṅgas", "Vedāṅgas - Chandas", "Classification of darśanas",
        "Āstika and nāstika", "Goal of philosophy", "Sāṃkhya", "Sāṃkhya liberation",
        "Puruṣa and Prakṛti", "Pramāṇas", "Eight limbs of Yoga", "Five states of mind",
        "Nyāya and Vaiśeṣika", "Nyāya bondage", "Vaiśeṣika system",
        "Vaiśeṣika atomic theory", "Pūrva Mīmāṃsā", "Vedānta", "Pāṇini background",
        "Aṣṭādhyāyī", "Trimuni Vyākaraṇa", "Śiva-sūtras", "Qualities of sūtras",
        "Sanskrit vocabulary", "Word formation", "Word generation", "Phonetics",
        "Pāṇini's contributions", "Sanskrit and NLP", "Why Sanskrit for NLP",
        "Handling ambiguity", "Key linguistic principles", "Text and context",
        "Bhāskarācārya's life", "About Lilāvatī", "Methods of finding squares",
        "Worked square example", "Squaring identity", "Square-root extraction",
        "Methods of finding cubes", "Cube-root extraction", "Fractions",
        "Completing the square", "Difference of squares", "Combinations", "Permutations",
        "Permutations with repetition", "Progressions", "Mensuration - right triangles",
        "Mensuration - quadrilaterals", "Mensuration - circle", "Shared concepts", "Origins",
        "Jain theology", "Buddhist metaphysics", "Jain metaphysics", "Advaita Vedānta",
        "Viśiṣṭādvaita", "Dvaita", "Mahāvākyas", "Buddhist schools", "Four Noble Truths",
        "Three Marks of Existence", "Buddhist path", "Jain path", "Jain Tīrthaṅkaras",
    }
    canonical = {str(item["name"]) for item in UC103N_CANONICAL_TOPICS}
    assert len(raw_labels) == 81
    assert raw_labels == canonical


def test_reconcile_all_courses_preserves_existing_progress_and_is_idempotent(tmp_path):
    path = tmp_path / "data" / "courses.json"
    _write_courses(path)
    service = CanonicalTopicCatalogueService(
        path,
        now=lambda: "2026-09-28T19:00:00",
    )

    first = service.reconcile()
    assert first.missing_courses == ()
    assert first.added_topic_count > 0
    assert {item.course_code for item in first.courses} == {code for code, _ in COURSES}

    payload = json.loads(path.read_text(encoding="utf-8"))
    ma = next(item for item in payload["courses"] if item["code"] == "MA103N")
    system = next(item for item in ma["topics"] if item["name"] == "System of Linear Equations")
    assert system["status"] == "weak"
    assert system["confidence"] == 2
    # Existing legacy spelling is preserved instead of duplicating a semantic topic.
    assert any(item["name"] == "LU Factorization" for item in ma["topics"])
    assert not any(item["name"] == "LU Factorisation" for item in ma["topics"])

    for code, catalogue in CANONICAL_TOPIC_CATALOGUES.items():
        course = next(item for item in payload["courses"] if item["code"] == code)
        names = {item["name"].casefold() for item in course["topics"]}
        for topic in catalogue:
            candidates = {str(topic["name"]).casefold()} | {
                str(alias).casefold() for alias in topic.get("aliases", ())
            }
            assert candidates & names, (code, topic["name"])

    before = path.read_bytes()
    second = service.reconcile()
    after = path.read_bytes()
    assert second.added_topic_count == 0
    assert before == after


def test_reconcile_does_not_create_missing_courses(tmp_path):
    path = tmp_path / "data" / "courses.json"
    _write_courses(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["courses"] = [
        item for item in payload["courses"] if item["code"] != "DE100N"
    ]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    result = CanonicalTopicCatalogueService(path).reconcile(["DE100N", "UC103N"])
    assert result.missing_courses == ("DE100N",)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert not any(item["code"] == "DE100N" for item in saved["courses"])


def test_unknown_course_code_is_rejected(tmp_path):
    path = tmp_path / "data" / "courses.json"
    _write_courses(path)
    with pytest.raises(ValueError, match="No source-backed"):
        CanonicalTopicCatalogueService(path).reconcile(["FAKE100"])
