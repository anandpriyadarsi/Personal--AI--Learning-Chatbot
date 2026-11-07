"""Strict wire DTOs; no client-supplied policy, history or execution authority."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import re

from personal_learning_assistant.services.coding_teaching import ACTIONS, EXPLANATION_DEPTHS, SOLUTION_ACTIONS

WORKSPACE_KEY = 'coding_workspace_v1'
LANGUAGES = {'python': {'label': 'Python', 'notebook_export': True, 'server_execution': False}}
FIELD_LIMITS = {'topic': 200, 'message': 2000, 'code': 12000, 'error': 3000, 'attempt': 2000}


class CodingError(ValueError):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status


def canonical(value, maximum=65536):
    try:
        result = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
        size = len(result.encode('utf-8'))
    except (TypeError, ValueError, UnicodeError) as exc:
        raise CodingError('invalid_json', 'Use valid UTF-8 JSON values.') from exc
    if size > maximum:
        raise CodingError('too_large', 'This request is too large. Reduce the code or context.', 413)
    return result


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def fields(payload, allowed):
    if not isinstance(payload, dict) or set(payload) - set(allowed):
        raise CodingError('invalid_fields', 'The request contains unsupported fields.')


def text(value, name, maximum, *, required=False):
    if not isinstance(value, str) or len(value) > maximum or '\x00' in value:
        raise CodingError('invalid_field', f'{name} must be text of at most {maximum} characters.')
    if required and not value.strip():
        raise CodingError('invalid_field', f'Enter {name}.')
    # Code is preserved byte-for-byte; do not strip indentation or Unicode.
    canonical(value, maximum * 6 + 2)
    return value


def integer(value, name, minimum=1):
    if type(value) is not int or value < minimum:
        raise CodingError('invalid_field', f'{name} must be a positive integer.')
    return value


def request_identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,80}', value):
        raise CodingError('invalid_request_id', 'Use a valid request identity.')
    return value


@dataclass(frozen=True)
class CodingRequest:
    data: dict

    @classmethod
    def parse(cls, payload):
        fields(payload, {*FIELD_LIMITS, 'request_id', 'expected_task_revision', 'action',
                         'hint_level', 'explanation_depth', 'full_solution', 'source_consent_revision'})
        data = {key: text(payload.get(key, ''), key, maximum) for key, maximum in FIELD_LIMITS.items()}
        data['request_id'] = request_identity(payload.get('request_id'))
        for key in ('expected_task_revision', 'source_consent_revision'):
            data[key] = integer(payload.get(key), key)
        action = payload.get('action')
        depth = payload.get('explanation_depth', 'overview')
        if not isinstance(action, str) or action not in ACTIONS or not isinstance(depth, str) or depth not in EXPLANATION_DEPTHS:
            raise CodingError('invalid_action', 'Choose a teaching action and explanation depth.')
        level = integer(payload.get('hint_level', 1), 'hint_level')
        if level > 3:
            raise CodingError('invalid_hint', 'Hint level must be 1, 2 or 3.')
        solution = payload.get('full_solution', False)
        if type(solution) is not bool or (solution and action not in SOLUTION_ACTIONS):
            raise CodingError('invalid_solution', 'Full solutions require an explicit choice for Debug, Explain code or Pseudocode.')
        if not any(data[key].strip() for key in FIELD_LIMITS):
            raise CodingError('empty_request', 'Add a message, topic, code or attempt.')
        if sum(len(data[key]) for key in FIELD_LIMITS) > 20000:
            raise CodingError('too_large', 'Current coding context exceeds 20,000 characters.', 413)
        data.update(action=action, explanation_depth=depth, hint_level=level, full_solution=solution)
        canonical(data, 24576)
        return cls(data)
