"""Read-only exact-version producer; automatic Tutor consumer is deliberately blocked.

The current web Tutor creates course-scoped sessions. It cannot bind an immutable
Learning Studio source snapshot/question revision. No Tutor service is imported.
"""
from __future__ import annotations
import json
from .validation import PackageError, identity, integer, require

MAX_CONTEXT_BYTES = 24_000
MAX_MISSES = 20
BLOCKER = ('Automatic Tutor review is unavailable: the existing Tutor session path '
           'does not bind a Learning Studio module revision and immutable source snapshot. '
           'Copy or download the manual review brief instead.')


def compatibility():
    return {'status': 'blocked', 'automatic_tutor_consumption': False,
            'reason': BLOCKER, 'consumer_contract': 'not-supported'}


def prepare_review(studio, payload, *, explicit_action=False):
    """Validate a guarded action payload and produce bounded server evidence only.

    Calling code owns HTTP CSRF/origin checks. Duplicate actions are deterministic,
    read-only projections, never session writes. No caller context is accepted.
    """
    require(explicit_action is True, 'An explicit guarded learner action is required.', 405)
    require(isinstance(payload, dict) and set(payload) == {'module_id', 'module_revision'},
            'Supply only module_id and module_revision.')
    module_id = payload['module_id']; revision = payload['module_revision']
    identity(module_id); integer(revision, 1, 1_000_000)
    context = studio.review_context(module_id, revision)
    require(context['module_id'] == module_id and context['module_revision'] == revision,
            'Server review identity mismatch.', 409)
    require(context['schema'] == 'anvaya.learning-review-context.v1', 'Unsupported review context.')
    # Allowlist every nested projection: future producer additions cannot leak keys.
    source = context['source']
    result = {**compatibility(), 'schema': 'anvaya.learning-tutor-boundary.v1',
              'module_id': module_id, 'module_revision': revision,
              'source': {k: source[k] for k in ('source_id', 'sha256', 'page_count')},
              'authority': 'low-stakes-practice', 'mapping_status': context['mapping_status'],
              'evidence_label': context['evidence_label'], 'attempts': context['attempts'],
              'semantic_review_pages': context['semantic_review_pages'], 'missed_questions': [],
              'omitted_misses': 0, 'manual_brief_url': f'/learning/modules/{module_id}/{revision}/review-brief'}
    fields = ('question_id', 'question_revision', 'pages', 'incorrect_count', 'last_incorrect',
              'latest_selection', 'latest_correct', 'attempt_count', 'status',
              'lesson_url', 'source_urls', 'question_url')
    for miss in context['missed_questions']:
        item = {key: miss[key] for key in fields}
        require(all(type(page) is int and 1 <= page <= source['page_count'] for page in item['pages']),
                'Invalid source page locator.')
        if len(result['missed_questions']) >= MAX_MISSES:
            result['omitted_misses'] += 1
            continue
        result['missed_questions'].append(item)
        if len(json.dumps(result, ensure_ascii=False).encode()) > MAX_CONTEXT_BYTES:
            result['missed_questions'].pop()
            result['omitted_misses'] += 1
    require(len(json.dumps(result, ensure_ascii=False).encode()) <= MAX_CONTEXT_BYTES,
            'Review identity exceeds the bounded context limit.')
    return result
