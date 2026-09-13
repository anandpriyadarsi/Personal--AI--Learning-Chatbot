"""V10.3 Automatic Topic Mapping.

Maps imported assessment questions to topics in the selected course catalogue.
The mapper is transparent and conservative:
- it never changes course progress/mastery;
- it preserves manual topic tags unless the user explicitly overwrites them;
- it stores a confidence score and alternative topic candidates;
- low-confidence matches remain suggestions instead of being silently accepted.
"""

import re
from difflib import SequenceMatcher
from datetime import datetime

from course_manager import find_course
from assignment_exam_assistant import choose_assessment
from assessment_question_workspace import (
    get_workspace,
    save_workspace,
    choose_question,
    list_questions,
)


HIGH_CONFIDENCE = 0.62
MEDIUM_CONFIDENCE = 0.38
MAX_ALTERNATIVES = 3

STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were",
    "be", "been", "being", "of", "to", "in", "on",
    "for", "with", "and", "or", "as", "at", "by",
    "from", "this", "that", "these", "those",
    "find", "calculate", "determine", "show", "prove",
    "solve", "using", "given", "following", "question",
    "write", "explain", "what", "why", "how",
}


def _now():
    return datetime.now().isoformat(timespec="seconds")


def normalize_text(text):
    text = str(text or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def tokenize(text):
    return [
        token
        for token in normalize_text(text).split()
        if token not in STOP_WORDS and len(token) > 1
    ]


def _acronym(text):
    tokens = tokenize(text)
    if len(tokens) < 2:
        return ""
    return "".join(token[0] for token in tokens)


def topic_similarity(question_text, topic_name):
    """Return a 0..1 topic-match score with interpretable components."""
    q_norm = normalize_text(question_text)
    t_norm = normalize_text(topic_name)

    if not q_norm or not t_norm:
        return 0.0, {}

    q_tokens = set(tokenize(question_text))
    t_tokens = set(tokenize(topic_name))

    exact_phrase = 1.0 if t_norm in q_norm else 0.0

    if t_tokens:
        overlap = len(q_tokens & t_tokens) / len(t_tokens)
    else:
        overlap = 0.0

    union = q_tokens | t_tokens
    jaccard = (
        len(q_tokens & t_tokens) / len(union)
        if union
        else 0.0
    )

    fuzzy = SequenceMatcher(
        None,
        q_norm,
        t_norm
    ).ratio()

    acronym_score = 0.0
    topic_acronym = _acronym(topic_name)
    if topic_acronym and topic_acronym in q_tokens:
        acronym_score = 1.0

    # Strongly reward explicit topic wording, but still allow
    # shorter/related wording to produce a suggestion.
    score = (
        0.40 * exact_phrase
        + 0.32 * overlap
        + 0.13 * jaccard
        + 0.10 * fuzzy
        + 0.05 * acronym_score
    )

    # A single distinctive shared token can be meaningful for course topics
    # such as "eigenvalues", "rank", "determinant", "pandas", etc.
    if (
        len(q_tokens & t_tokens) == 1
        and len(t_tokens) == 1
    ):
        score = max(score, 0.58)

    score = min(1.0, max(0.0, score))

    return score, {
        "exact_phrase": round(exact_phrase, 3),
        "topic_word_coverage": round(overlap, 3),
        "jaccard": round(jaccard, 3),
        "fuzzy": round(fuzzy, 3),
        "acronym": round(acronym_score, 3),
    }


def get_course_topics(course):
    topics = []

    for item in course.get("topics", []):
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
        else:
            name = str(item).strip()

        if name:
            topics.append(name)

    return topics


def rank_topic_candidates(question_text, course, limit=MAX_ALTERNATIVES):
    candidates = []

    for topic_name in get_course_topics(course):
        score, components = topic_similarity(
            question_text,
            topic_name
        )

        candidates.append({
            "topic": topic_name,
            "score": round(score, 3),
            "components": components,
        })

    candidates.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return candidates[:limit]


def mapping_label(score):
    if score >= HIGH_CONFIDENCE:
        return "high"
    if score >= MEDIUM_CONFIDENCE:
        return "medium"
    return "low"


def build_mapping(question, course):
    candidates = rank_topic_candidates(
        question.get("text", ""),
        course,
        limit=MAX_ALTERNATIVES
    )

    if not candidates:
        return {
            "suggested_topic": None,
            "score": 0.0,
            "confidence": "low",
            "alternatives": [],
        }

    best = candidates[0]

    return {
        "suggested_topic": best["topic"],
        "score": best["score"],
        "confidence": mapping_label(best["score"]),
        "alternatives": candidates,
    }


def apply_mapping(
    question,
    mapping,
    accepted=False,
    method="automatic"
):
    question["topic_mapping"] = {
        "method": method,
        "suggested_topic": mapping.get("suggested_topic"),
        "score": mapping.get("score", 0.0),
        "confidence": mapping.get("confidence", "low"),
        "alternatives": mapping.get("alternatives", []),
        "accepted": bool(accepted),
        "mapped_at": _now(),
    }

    if accepted and mapping.get("suggested_topic"):
        question["topic"] = mapping["suggested_topic"]

    question["updated_at"] = _now()


def _question_preview(question, max_chars=115):
    preview = str(question.get("text", "")).replace(
        "\n",
        " "
    )

    if len(preview) > max_chars:
        return preview[:max_chars - 3] + "..."

    return preview


def print_candidates(mapping):
    alternatives = mapping.get(
        "alternatives",
        []
    )

    if not alternatives:
        print("No course-topic candidates found.")
        return

    for index, candidate in enumerate(
        alternatives,
        start=1
    ):
        print(
            f"{index}. {candidate['topic']} "
            f"| score {candidate['score']:.3f}"
        )


def map_one_question(
    assessment,
    workspace
):
    course = find_course(
        assessment.get("course_id")
    )

    if not course:
        print("\nCourse not found.")
        return

    if not get_course_topics(course):
        print(
            "\nThis course has no topics yet. "
            "Add syllabus topics in Course Manager first."
        )
        return

    question = choose_question(
        workspace
    )

    if not question:
        return

    mapping = build_mapping(
        question,
        course
    )

    print(
        "\n========== TOPIC MAPPING SUGGESTION =========="
    )
    print(
        f"Question: {_question_preview(question, 180)}"
    )
    print(
        f"\nSuggested topic : "
        f"{mapping.get('suggested_topic') or 'None'}"
    )
    print(
        f"Confidence      : "
        f"{mapping['confidence']}"
    )
    print(
        f"Score           : "
        f"{mapping['score']:.3f}"
    )

    print("\nTop candidates:")
    print_candidates(mapping)

    if mapping["confidence"] == "low":
        print(
            "\nLow confidence: the mapper will not "
            "silently assign this topic."
        )

    print(
        "\n1. Accept suggested topic"
    )
    print(
        "2. Choose another candidate"
    )
    print(
        "3. Save suggestion only"
    )
    print(
        "4. Cancel"
    )

    choice = input(
        "\nChoose (1-4): "
    ).strip()

    if choice == "1":
        if not mapping.get(
            "suggested_topic"
        ):
            print("\nNo topic available.")
            return

        apply_mapping(
            question,
            mapping,
            accepted=True,
            method="automatic_confirmed"
        )

        save_workspace(
            workspace
        )

        print(
            f"\nTopic saved: "
            f"{question['topic']}"
        )

    elif choice == "2":
        alternatives = mapping.get(
            "alternatives",
            []
        )

        if not alternatives:
            print("\nNo alternatives available.")
            return

        try:
            selected = int(
                input(
                    "Candidate number: "
                ).strip()
            )
        except ValueError:
            print("\nInvalid number.")
            return

        if (
            selected < 1
            or selected > len(alternatives)
        ):
            print("\nInvalid candidate.")
            return

        chosen = alternatives[
            selected - 1
        ]

        custom_mapping = dict(
            mapping
        )

        custom_mapping[
            "suggested_topic"
        ] = chosen["topic"]

        custom_mapping[
            "score"
        ] = chosen["score"]

        custom_mapping[
            "confidence"
        ] = mapping_label(
            chosen["score"]
        )

        apply_mapping(
            question,
            custom_mapping,
            accepted=True,
            method="candidate_confirmed"
        )

        save_workspace(
            workspace
        )

        print(
            f"\nTopic saved: "
            f"{question['topic']}"
        )

    elif choice == "3":
        apply_mapping(
            question,
            mapping,
            accepted=False,
            method="automatic_suggestion"
        )

        save_workspace(
            workspace
        )

        print(
            "\nSuggestion saved without changing "
            "the question's topic."
        )

    elif choice == "4":
        print("\nMapping cancelled.")

    else:
        print("\nInvalid choice.")


def auto_map_all(
    assessment,
    workspace
):
    course = find_course(
        assessment.get("course_id")
    )

    if not course:
        print("\nCourse not found.")
        return

    topics = get_course_topics(
        course
    )

    if not topics:
        print(
            "\nThis course has no topics. "
            "Add syllabus topics in Course Manager first."
        )
        return

    questions = workspace.get(
        "questions",
        []
    )

    if not questions:
        print("\nNo questions exist yet.")
        return

    print(
        "\n========== AUTOMATIC TOPIC MAPPING =========="
    )
    print(
        f"Course: {course['code']} - "
        f"{course['name']}"
    )
    print(
        f"Course topics available: {len(topics)}"
    )
    print(
        f"Questions: {len(questions)}"
    )

    overwrite = input(
        "\nOverwrite existing manual topic tags? "
        "Type yes only if you want this: "
    ).strip().lower() == "yes"

    high = 0
    medium = 0
    low = 0
    skipped = 0

    for question in questions:
        existing_topic = str(
            question.get(
                "topic",
                ""
            )
        ).strip()

        if existing_topic and not overwrite:
            skipped += 1
            continue

        mapping = build_mapping(
            question,
            course
        )

        confidence = mapping[
            "confidence"
        ]

        if confidence == "high":
            apply_mapping(
                question,
                mapping,
                accepted=True,
                method="automatic_high_confidence"
            )
            high += 1

        elif confidence == "medium":
            # Store suggestion, but require human confirmation.
            apply_mapping(
                question,
                mapping,
                accepted=False,
                method="automatic_medium_suggestion"
            )
            medium += 1

        else:
            apply_mapping(
                question,
                mapping,
                accepted=False,
                method="automatic_low_suggestion"
            )
            low += 1

    save_workspace(
        workspace
    )

    print(
        "\nAutomatic mapping complete."
    )
    print(
        f"High confidence auto-tagged : {high}"
    )
    print(
        f"Medium confidence suggestions: {medium}"
    )
    print(
        f"Low confidence suggestions   : {low}"
    )
    print(
        f"Existing tags preserved      : {skipped}"
    )
    print(
        "\nReview medium/low confidence mappings "
        "before relying on them."
    )


def mapping_report(
    assessment,
    workspace
):
    course = find_course(
        assessment.get("course_id")
    )

    print(
        "\n========== V10.3 TOPIC MAPPING REPORT =========="
    )

    if course:
        print(
            f"Course: {course['code']} - "
            f"{course['name']}"
        )

    questions = workspace.get(
        "questions",
        []
    )

    if not questions:
        print("\nNo questions exist.")
        return

    mapped = 0
    suggested = 0
    unmapped = 0

    for index, question in enumerate(
        questions,
        start=1
    ):
        topic = str(
            question.get(
                "topic",
                ""
            )
        ).strip()

        mapping = question.get(
            "topic_mapping",
            {}
        )

        suggestion = mapping.get(
            "suggested_topic"
        )

        score = mapping.get(
            "score",
            0.0
        )

        confidence = mapping.get(
            "confidence",
            "none"
        )

        print(
            f"\n{index}. "
            f"{_question_preview(question)}"
        )

        if topic:
            mapped += 1
            print(
                f"   Topic      : {topic}"
            )

            if mapping:
                print(
                    f"   Mapping    : "
                    f"{confidence} "
                    f"({score:.3f})"
                )

        elif suggestion:
            suggested += 1
            print(
                f"   Suggested  : {suggestion}"
            )
            print(
                f"   Confidence : "
                f"{confidence} "
                f"({score:.3f})"
            )

        else:
            unmapped += 1
            print(
                "   Topic      : UNMAPPED"
            )

    print(
        "\nSUMMARY"
    )
    print(
        f"Accepted topic tags : {mapped}"
    )
    print(
        f"Suggestions pending : {suggested}"
    )
    print(
        f"Unmapped            : {unmapped}"
    )


def review_pending_suggestions(
    assessment,
    workspace
):
    pending = []

    for question in workspace.get(
        "questions",
        []
    ):
        mapping = question.get(
            "topic_mapping",
            {}
        )

        if (
            not question.get("topic")
            and mapping.get(
                "suggested_topic"
            )
        ):
            pending.append(
                question
            )

    if not pending:
        print(
            "\nNo pending topic suggestions."
        )
        return

    for number, question in enumerate(
        pending,
        start=1
    ):
        mapping = question[
            "topic_mapping"
        ]

        print(
            "\n" + "-" * 65
        )
        print(
            f"Pending {number}/{len(pending)}"
        )
        print(
            _question_preview(
                question,
                200
            )
        )
        print(
            f"\nSuggested: "
            f"{mapping.get('suggested_topic')}"
        )
        print(
            f"Confidence: "
            f"{mapping.get('confidence')} "
            f"({mapping.get('score', 0.0):.3f})"
        )

        print(
            "\na = accept | s = skip | "
            "q = stop review"
        )

        action = input(
            "Choice: "
        ).strip().lower()

        if action == "a":
            mapping_copy = {
                "suggested_topic": (
                    mapping.get(
                        "suggested_topic"
                    )
                ),
                "score": mapping.get(
                    "score",
                    0.0
                ),
                "confidence": (
                    mapping.get(
                        "confidence",
                        "low"
                    )
                ),
                "alternatives": (
                    mapping.get(
                        "alternatives",
                        []
                    )
                ),
            }

            apply_mapping(
                question,
                mapping_copy,
                accepted=True,
                method="review_confirmed"
            )

            save_workspace(
                workspace
            )

            print(
                f"Accepted: "
                f"{question['topic']}"
            )

        elif action == "q":
            break


def clear_mapping_for_question(
    workspace
):
    question = choose_question(
        workspace
    )

    if not question:
        return

    print(
        "\n1. Clear automatic mapping metadata only"
    )
    print(
        "2. Clear topic tag AND mapping metadata"
    )
    print(
        "3. Cancel"
    )

    choice = input(
        "\nChoose (1-3): "
    ).strip()

    if choice == "1":
        question.pop(
            "topic_mapping",
            None
        )

    elif choice == "2":
        question["topic"] = ""
        question.pop(
            "topic_mapping",
            None
        )

    elif choice == "3":
        return

    else:
        print("\nInvalid choice.")
        return

    question["updated_at"] = _now()

    save_workspace(
        workspace
    )

    print("\nMapping cleared.")


def automatic_topic_mapping_menu():
    assessment = choose_assessment(
        include_completed=True
    )

    if not assessment:
        return

    workspace = get_workspace(
        assessment["id"],
        create=True
    )

    course = find_course(
        assessment.get(
            "course_id"
        )
    )

    if not course:
        print(
            "\nThe assessment course could not be found."
        )
        return

    while True:
        print(
            "\n========== V10.3 AUTOMATIC TOPIC MAPPING =========="
        )

        print(
            f"Assessment: "
            f"{assessment['title']}"
        )

        print(
            f"Course: "
            f"{course['code']} - "
            f"{course['name']}"
        )

        print(
            "\n1. Auto-Map All Questions"
        )
        print(
            "2. Map / Review One Question"
        )
        print(
            "3. Review Pending Suggestions"
        )
        print(
            "4. View Topic Mapping Report"
        )
        print(
            "5. View Questions"
        )
        print(
            "6. Clear a Question Mapping"
        )
        print(
            "7. Change Assessment"
        )
        print(
            "8. Back"
        )

        choice = input(
            "\nEnter your choice (1-8): "
        ).strip()

        if choice == "1":
            auto_map_all(
                assessment,
                workspace
            )

        elif choice == "2":
            map_one_question(
                assessment,
                workspace
            )

        elif choice == "3":
            review_pending_suggestions(
                assessment,
                workspace
            )

        elif choice == "4":
            mapping_report(
                assessment,
                workspace
            )

        elif choice == "5":
            list_questions(
                workspace
            )

        elif choice == "6":
            clear_mapping_for_question(
                workspace
            )

        elif choice == "7":
            selected = choose_assessment(
                include_completed=True
            )

            if selected:
                assessment = selected

                workspace = get_workspace(
                    assessment["id"],
                    create=True
                )

                course = find_course(
                    assessment.get(
                        "course_id"
                    )
                )

                if not course:
                    print(
                        "\nThe selected assessment "
                        "has no valid course."
                    )
                    return

        elif choice == "8":
            break

        else:
            print(
                "\nInvalid choice. "
                "Please enter 1 to 8."
            )


if __name__ == "__main__":
    automatic_topic_mapping_menu()
