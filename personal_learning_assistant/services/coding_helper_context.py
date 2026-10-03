"""Signed, expiring continuation data. No database, cookies, or Tutor history."""
from dataclasses import replace
import hashlib
import json

from itsdangerous import BadData, URLSafeTimedSerializer

from personal_learning_assistant.services.assessment_coding_helper import CodingHelperError

MAX_EXCHANGES = 3
MAX_TURN_CHARS = 4000
MAX_AGE_SECONDS = 900


def context_signer(key):
    return URLSafeTimedSerializer(key, salt="assessment-coding-helper-v2")


def _binding(session_id, question_id, context, data, policy):
    fields = [str(session_id), str(question_id), context, policy,
              data["include_question"], data["full_solution"]]
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def continue_request(provider_request, payload, context, question_id, signer):
    """Only this server's bounded history may re-enter an eligible request."""
    data = json.loads(provider_request.messages[-1]["content"])
    binding = _binding(provider_request.session_id, question_id, context, data,
                       provider_request.metadata["policy"])
    token = payload.get("context_token", "")
    turns = []
    if token:
        try:
            saved = signer.loads(token, max_age=MAX_AGE_SECONDS)
            if saved["binding"] != binding:
                raise ValueError("Different task or permissions")
            turns = saved["turns"]
            if not isinstance(turns, list) or len(turns) > MAX_EXCHANGES:
                raise ValueError("Invalid turns")
            if any(set(t) != {"student", "helper"} or any(
                not isinstance(v, str) or len(v) > MAX_TURN_CHARS for v in t.values()
            ) for t in turns):
                raise ValueError("Invalid turn")
        except (BadData, ValueError, KeyError, TypeError):
            raise CodingHelperError("Helper context expired or changed. Reset context and retry.", 409) from None
    data["previous_exchanges"] = turns
    messages = (provider_request.messages[0], {"role": "user", "content": json.dumps(data, ensure_ascii=False)})
    return replace(provider_request, messages=messages), {"binding": binding, "turns": turns}


def next_context(provider_request, state, reply, signer):
    if provider_request.metadata["policy"] != "full":
        return ""
    data = json.loads(provider_request.messages[-1]["content"])
    student = {key: data[key] for key in (
        "action", "topic", "message", "code", "error", "attempt", "hint_level", "explanation_depth"
    )}
    turn = {"student": json.dumps(student, ensure_ascii=False)[:MAX_TURN_CHARS],
            "helper": reply[:MAX_TURN_CHARS]}
    turns = [*state["turns"], turn][-MAX_EXCHANGES:]
    token = signer.dumps({"binding": state["binding"], "turns": turns})
    while len(token) > 36000 and turns:
        turns.pop(0)
        token = signer.dumps({"binding": state["binding"], "turns": turns})
    return token
