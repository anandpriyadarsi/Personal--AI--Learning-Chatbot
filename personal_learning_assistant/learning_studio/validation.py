"""Strict, bounded canonical V1 validation; proposed pilot JSON needs an adapter."""
from __future__ import annotations
import copy
import hashlib
import io
import json
import re

SCHEMA = 'anvaya.learning-module.v1'
MAX_JSON = 2_000_000
MAX_SOURCE = 20_000_000
MAX_ASSETS = 20_000_000
IDENTITY = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$')
HASH = re.compile(r'^[0-9a-f]{64}$')
UNSAFE = re.compile(r'<\s*/?\s*[a-zA-Z!]|(?:javascript|vbscript|data)\s*:', re.I)


class PackageError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def require(condition, message, status=400):
    if not condition:
        raise PackageError(message, status)


def shape(value, required, optional=()):
    require(isinstance(value, dict), 'Expected a structured object.')
    require(set(required) <= value.keys() and not value.keys() - set(required) - set(optional),
            'Missing or unsupported fields: ' + ', '.join(sorted(set(required) - value.keys() | value.keys() - set(required) - set(optional))))


def text(value, limit=30000, *, empty=False):
    require(isinstance(value, str) and len(value) <= limit and (empty or bool(value.strip())), 'Invalid or oversized text.')
    require(not UNSAFE.search(value) and '\x00' not in value, 'Active markup or unsafe URL scheme is not supported.')
    return value


def identity(value):
    require(isinstance(value, str) and IDENTITY.fullmatch(value), 'Invalid stable identifier.')
    return value


def integer(value, minimum=1, maximum=500):
    require(type(value) is int and minimum <= value <= maximum, 'Invalid integer or locator.')
    return value


def items(value, maximum=500, *, nonempty=False):
    require(isinstance(value, list) and len(value) <= maximum and (not nonempty or len(value)), 'Invalid or oversized collection.')
    return value


def locators(value, count):
    items(value, count, nonempty=True)
    for page in value:
        integer(page, 1, count)
    require(len(set(value)) == len(value), 'Duplicate page references.')


def validate_mapping(mapping, catalogue):
    if mapping is None:
        return
    shape(mapping, {'course_id', 'topic_name', 'reviewed', 'confidence'}, {'topic_id'})
    identity(mapping['course_id']); text(mapping['topic_name'], 500)
    if mapping.get('topic_id') is not None: identity(mapping['topic_id'])
    confidence = mapping['confidence']
    require(mapping['reviewed'] is True and type(confidence) in (int, float) and .9 <= confidence <= 1,
            'Canonical mapping requires review and confidence >= 0.90.')
    course = next((c for c in catalogue.get('courses', []) if c['id'] == mapping['course_id']), None)
    require(catalogue.get('available') and course is not None, 'Course is not in the current registered catalogue.')
    topic = next((t for t in course['topics'] if t['name'] == mapping['topic_name']), None)
    require(topic is not None, 'Topic name must exactly match the canonical course catalogue.')
    if mapping.get('topic_id') is not None:
        require(topic.get('id') == mapping['topic_id'], 'Topic ID does not match its registered course and name.')


def validate_block(block, count, assets):
    shape(block, {'kind', 'pages'}, {'text', 'nodes', 'alt', 'headers', 'rows', 'asset', 'caption', 'answer'})
    locators(block['pages'], count)
    kind = block['kind']
    require(isinstance(kind, str), 'Block kind must be a string.')
    allowed = {
        'source': {'text'}, 'teaching': {'text'}, 'definition': {'text'}, 'example': {'text'},
        'objectives': {'text'}, 'misconception': {'text'}, 'recall': {'text', 'answer'},
        'flowchart': {'nodes', 'alt'}, 'mindmap': {'nodes', 'alt'},
        'table': {'headers', 'rows'}, 'image': {'asset', 'alt', 'caption'},
    }
    require(kind in allowed and set(block) == {'kind', 'pages'} | allowed[kind], 'Unsupported or malformed visual/content block.')
    for key in ('text', 'alt', 'caption', 'answer'):
        if key in block:
            text(block[key], empty=key == 'caption')
    if kind in {'flowchart', 'mindmap'}:
        for node in items(block['nodes'], 40, nonempty=True): text(node, 500)
    if kind == 'table':
        for header in items(block['headers'], 12, nonempty=True): text(header, 500)
        for row in items(block['rows'], 100):
            require(isinstance(row, list) and len(row) == len(block['headers']), 'Table row width mismatch.')
            for cell in row: text(cell, 3000, empty=True)
    if kind == 'image':
        text(block['asset'], 240)
        require(block['asset'] in assets, 'Missing owned image asset.')


def validate_package(package, catalogue, source, assets=None):
    assets = assets or {}
    try:
        encoded = json.dumps(package, ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, RecursionError) as error:
        raise PackageError('Package must be bounded JSON data.') from error
    require(len(encoded) <= MAX_JSON, 'Package JSON exceeds 2 MB.', 413)
    shape(package, {'schema', 'module_id', 'module_revision', 'title', 'unit', 'source', 'mapping', 'pages', 'sections', 'revision', 'questions'})
    require(package['schema'] == SCHEMA, 'Unsupported learning-module schema.')
    identity(package['module_id']); integer(package['module_revision'], 1, 1000000)
    text(package['title'], 500); text(package['unit'], 200)
    validate_mapping(package['mapping'], catalogue)
    s = package['source']
    shape(s, {'source_id', 'sha256', 'filename', 'media_type', 'page_count'})
    identity(s['source_id']); text(s['filename'], 240)
    require('/' not in s['filename'] and '\\' not in s['filename'] and s['filename'].lower().endswith('.pdf'), 'Only a PDF basename is supported in V1.')
    require(s['media_type'] == 'application/pdf', 'Only source PDF evidence is supported in V1.')
    require(isinstance(s['sha256'], str) and HASH.fullmatch(s['sha256']), 'Invalid source hash.')
    count = integer(s['page_count'])
    require(isinstance(source, bytes) and 0 < len(source) <= MAX_SOURCE and source.startswith(b'%PDF-'), 'Original registered PDF is missing or oversized.')
    require(hashlib.sha256(source).hexdigest() == s['sha256'], 'Registered source hash mismatch.', 409)
    from pypdf import PdfReader
    try:
        pdf = PdfReader(io.BytesIO(source), strict=True)
        require(not pdf.is_encrypted and len(pdf.pages) == count, 'Original page identities do not match the manifest.')
    except PackageError:
        raise
    except Exception as error:
        raise PackageError('Original PDF cannot be validated.') from error
    validate_assets(assets)
    pages = items(package['pages'], count, nonempty=True)
    require([p.get('page') for p in pages if isinstance(p, dict)] == list(range(1, count + 1)), 'Every original page identity must appear exactly once in order.')
    for p in pages:
        shape(p, {'page', 'status', 'text', 'review_flags'}, {'preview'})
        require(isinstance(p['status'], str) and p['status'] in {'verified', 'needs_review', 'unavailable'}, 'Invalid semantic fidelity state.')
        text(p['text'], empty=True)
        for flag in items(p['review_flags'], 30): text(flag, 1000)
        require(p['status'] == 'verified' or bool(p['review_flags']), 'Unverified pages need an explicit review reason.')
        if 'preview' in p:
            text(p['preview'], 240)
            require(p['preview'] in assets, 'Page preview is not an owned asset.')
    section_ids = set()
    for section in items(package['sections'], 500, nonempty=True):
        shape(section, {'id', 'title', 'pages', 'blocks'})
        identity(section['id']); text(section['title'], 500); locators(section['pages'], count)
        require(section['id'] not in section_ids, 'Duplicate section ID.'); section_ids.add(section['id'])
        for block in items(section['blocks'], 100, nonempty=True): validate_block(block, count, assets)
    for block in items(package['revision'], 200, nonempty=True): validate_block(block, count, assets)
    question_ids = set()
    for q in items(package['questions'], 500):
        shape(q, {'id', 'revision', 'kind', 'prompt', 'options', 'correct_index', 'explanation', 'pages', 'difficulty', 'low_stakes'})
        identity(q['id']); integer(q['revision'], 1, 1000000)
        require(q['id'] not in question_ids, 'Duplicate question ID.'); question_ids.add(q['id'])
        require(q['kind'] == 'mcq' and q['low_stakes'] is True, 'V1 accepts low-stakes MCQ practice only.')
        text(q['prompt'], 5000); text(q['explanation'], 10000)
        options = items(q['options'], 12, nonempty=True)
        for option in options: text(option, 3000)
        require(len(options) >= 2 and len(set(options)) == len(options), 'Question needs distinct options.')
        integer(q['correct_index'], 0, len(options) - 1)
        require(isinstance(q['difficulty'], str) and q['difficulty'] in {'easy', 'normal', 'hard'}, 'Unsupported difficulty.')
        locators(q['pages'], count)
    return copy.deepcopy(package)


def validate_assets(assets):
    require(isinstance(assets, dict) and len(assets) <= 500, 'Invalid assets.')
    require(sum(len(v) for v in assets.values() if isinstance(v, bytes)) <= MAX_ASSETS, 'Assets exceed 20 MB.', 413)
    from PIL import Image
    for name, raw in assets.items():
        require(isinstance(name, str) and re.fullmatch(r'assets/[A-Za-z0-9_.-]+\.(png|jpg|jpeg|webp)', name), 'Unsafe asset path/type.')
        require(isinstance(raw, bytes) and 0 < len(raw) <= 2_000_000, 'Image exceeds 2 MB.', 413)
        try:
            with Image.open(io.BytesIO(raw)) as image:
                require(image.format in {'PNG', 'JPEG', 'WEBP'} and image.width * image.height <= 16_000_000, 'Unsupported or oversized image.')
                expected = {'png': 'PNG', 'jpg': 'JPEG', 'jpeg': 'JPEG', 'webp': 'WEBP'}[name.rsplit('.', 1)[-1]]
                require(image.format == expected, 'Image content type does not match its extension.')
                image.verify()
        except PackageError:
            raise
        except Exception as error:
            raise PackageError('Invalid image bytes.') from error
