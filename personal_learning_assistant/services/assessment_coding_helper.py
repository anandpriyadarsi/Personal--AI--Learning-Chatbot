"""Bounded UC100N teaching through the existing provider interface.

No Tutor orchestration, RAG, memory, grading, code execution or evidence writes.
"""
from __future__ import annotations

import json
from urllib.parse import urlsplit

from personal_learning_assistant.domain.tutor_models import TutorProviderRequest
from personal_learning_assistant.services.coding_operations import OPERATION_CARDS, recommend_cards


# Restricted exams accept only these identifiers, never free-text tasks or code.
GENERIC_TOPICS = {"loops": "Python loops", **{
    card["id"]: f'{card["category"]}: {card["what"]}' for card in OPERATION_CARDS
}}


from personal_learning_assistant.services.coding_teaching import (
    ACTIONS, ACTION_GUIDANCE, SOLUTION_ACTIONS, EXAM_ACTIONS, EXPLANATION_DEPTHS,
    TeachingPolicy, teaching_system,
)


class CodingHelperError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def helper_policy(mode, settings):
    if settings.get("ASSESSMENT_CODING_HELPER_ENABLED", True) is not True:
        return "disabled"
    if mode in {"practice", "assignment"}:
        return "full"
    if mode == "exam" and settings.get("ASSESSMENT_CODING_HELPER_EXAM_POLICY") == "concepts":
        return "concepts"
    return "disabled"


def tool_options(context, settings):
    eligible = context.get("course_code") == "UC100N"
    mode = context.get("mode")
    destination = str(settings.get("ASSESSMENT_COLAB_URL") or "").strip()
    try:
        url = urlsplit(destination)
        valid = (url.scheme == "https" and url.hostname == "colab.research.google.com"
                 and not url.username and not url.password and url.port in {None, 443}
                 and not any(c.isspace() for c in destination))
    except ValueError:
        valid = False
    policy = helper_policy(mode, settings) if eligible else "disabled"
    return {
        "coding_helper_available": policy != "disabled",
        "colab_available": eligible and mode in {"practice", "assignment", "exam"},
        "colab_url": destination if valid else "https://colab.research.google.com/",
        "policy": policy,
        "generic_topics": GENERIC_TOPICS,
        "actions": {key: value[0] for key, value in ACTIONS.items()
                    if policy == "full" or key in EXAM_ACTIONS},
        "action_details": {key: {"allows_solution": key in SOLUTION_ACTIONS, "guidance": ACTION_GUIDANCE[key]}
                           for key, value in ACTIONS.items()},
        "explanation_depths": EXPLANATION_DEPTHS,
    }


def build_request(session_id, context, payload, settings):
    policy = tool_options(context, settings)["policy"]
    if policy == "disabled":
        raise CodingHelperError("Coding Helper is unavailable in this assessment mode.", 403)
    if not isinstance(payload, dict):
        raise CodingHelperError("Enter a valid help request.")
    action = payload.get("action")
    if not isinstance(action, str) or action not in ACTIONS:
        raise CodingHelperError("Choose a Coding Helper action.")
    data = {"action": action}
    for key, maximum in (("topic", 200), ("message", 2000), ("code", 12000), ("error", 3000), ("attempt", 2000)):
        value = payload.get(key, "")
        if not isinstance(value, str) or len(value) > maximum:
            raise CodingHelperError(f"{key.title()} must be text of at most {maximum} characters.")
        data[key] = value.strip()
    for key in ("include_question", "full_solution"):
        value = payload.get(key, False)
        if not isinstance(value, bool):
            raise CodingHelperError("Choose a valid context or solution option.")
        data[key] = value
    level = payload.get("hint_level", 1)
    if type(level) is not int or level not in (1, 2, 3):
        raise CodingHelperError("Hint level must be 1, 2 or 3.")
    data["hint_level"] = level
    depth = payload.get("explanation_depth", "overview")
    if not isinstance(depth, str) or depth not in EXPLANATION_DEPTHS:
        raise CodingHelperError("Choose a valid explanation depth.")
    data["explanation_depth"] = depth
    card_id = payload.get("card_id", "")
    if not isinstance(card_id, str) or (card_id and card_id not in GENERIC_TOPICS):
        if policy == "concepts":
            raise CodingHelperError("Choose a predefined concept for this exam.", 403)
        raise CodingHelperError("Choose a valid operation card.")
    token = payload.get("context_token", "")
    if not isinstance(token, str) or len(token) > 36000:
        raise CodingHelperError("Reset the helper context and try again.")
    if policy == "concepts":
        if (action not in EXAM_ACTIONS or data["include_question"] or data["full_solution"]
                or any(data[key] for key in ("code", "error", "message", "attempt"))
                or data["topic"] not in GENERIC_TOPICS or token or card_id or depth != "overview"):
            raise CodingHelperError("Only general concept or memory help is enabled for this exam.", 403)
        card_id = data["topic"]
        data["topic"] = GENERIC_TOPICS[data["topic"]]
        data["visible_context"] = {}
    else:
        if not any(data[key] for key in ("topic", "message", "code", "error", "attempt")) and not data["include_question"] and not card_id:
            raise CodingHelperError("Add a topic, question, code or your attempt first.")
        data["visible_context"] = {key: context[key] for key in ("course_code", "assessment_title")}
        if data["include_question"]:
            data["visible_context"]["question_text"] = context["question_text"][:12000]
    # Only an explicit switch permits a full solution, only in suitable practice actions.
    data["full_solution"] = bool(data["full_solution"] and policy == "full"
                                  and action in SOLUTION_ACTIONS)
    data["reference_cards"] = recommend_cards(data["topic"] + " " + data["message"], card_id=card_id)
    data["previous_exchanges"] = []
    system = teaching_system(action, TeachingPolicy(
        restricted_exam=policy == "concepts", allow_solution=policy == "full"),
        solution=data["full_solution"])
    return TutorProviderRequest(
        session_id=str(session_id), mode="coding_helper", source_policy="visible_only",
        messages=({"role": "system", "content": system},
                  {"role": "user", "content": json.dumps(data, ensure_ascii=False)}),
        metadata={"surface": "assessment_coding_helper", "policy": policy},
    )
