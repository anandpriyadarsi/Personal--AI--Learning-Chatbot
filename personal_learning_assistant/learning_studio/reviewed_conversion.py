"""Review-first conversion into the existing immutable module owner; never publish.

The source map is an ordinary canonical table in an appended section, so old
readers and exports retain it without a new database or package schema.
"""
from copy import deepcopy
import hashlib
from .note_draft import convert
from .service import canonical
from .validation import require, text, validate_mapping

PREFIX = 'reviewed-conversion-r'
HEADERS = ['Page', 'Method', 'Extracted text SHA-256', 'Reviewed note SHA-256',
           'Source SHA-256', 'Semantic confidence', 'Review status']
METHOD = 'pypdf.extract_text followed by explicit human review/edit; transformed notes, not verbatim source'


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _snapshot(studio, module_id, revision, *, require_active=True):
    with studio.store.connection() as con:
        row, package = studio._row(con, module_id, revision, include_source=True)
        active = con.execute('SELECT revision FROM active_modules WHERE module_id=?', (module_id,)).fetchone()
        require(not require_active or (active is not None and active['revision'] == revision), 'Conversion requires the active published revision. Reload the current lesson.', 409)
        assets = {r['name']: r['bytes'] for r in con.execute('SELECT name,bytes FROM assets WHERE module_id=? AND revision=?', (module_id, revision))}
        target = revision + 1
        raw = row['source_blob']
        require(hashlib.sha256(raw).hexdigest() == package['source']['sha256'], 'Source snapshot integrity failure.', 409)
        parent_digest = row['digest']
    try:
        registered = studio.source_loader(package['source']['source_id'])
    except Exception as error:
        from .validation import PackageError
        raise PackageError('Registered source unavailable; no conversion was staged.', 503) from error
    require(registered == raw, 'Registered source changed. Reload after source review.', 409)
    validate_mapping(package['mapping'], studio.catalogue_loader())
    return package, raw, assets, target, parent_digest


def prepare(studio, module_id, revision):
    package, raw, _, target, parent_digest = _snapshot(studio, module_id, revision)
    with studio.store.connection() as con:
        require(not con.execute('SELECT 1 FROM modules WHERE module_id=? AND revision=?', (module_id, target)).fetchone(),
            'The next revision already exists. Review that staged revision before starting another conversion.', 409)
    draft = convert(raw, media_type=package['source']['media_type'])
    require(len(draft['pages']) == package['source']['page_count'], 'Extraction page identities changed.', 409)
    binding = {'schema': 'anvaya.reviewed-conversion.v1', 'module_id': module_id,
        'parent_revision': revision, 'parent_digest': parent_digest, 'target_revision': target,
        'source_sha256': package['source']['sha256'], 'mapping_digest': digest(package['mapping']),
        'extracted_hashes': [p['text_sha256'] for p in draft['pages']],
        'parser_version': draft['parser_version']}
    return {'module': package, 'draft': draft, 'binding': binding}


def stage_review(studio, module_id, revision, binding, notes, reviewed_pages, *, approved=False):
    require(approved is True, 'Explicit approval to stage reviewed notes is required.')
    require(isinstance(binding, dict) and binding.get('schema') == 'anvaya.reviewed-conversion.v1' and
        binding.get('module_id') == module_id and binding.get('parent_revision') == revision,
        'Conversion review identity changed.', 409)
    package, _, assets, _, parent_digest = _snapshot(studio, module_id, revision, require_active=False)
    require(binding['parent_digest'] == parent_digest and binding['source_sha256'] == package['source']['sha256']
        and binding['mapping_digest'] == digest(package['mapping']), 'Conversion source, parent or mapping changed. Reload the review.', 409)
    count = package['source']['page_count']
    require(isinstance(notes, list) and len(notes) == count and sum(len(n) for n in notes if isinstance(n, str)) <= 100000,
        'Provide one bounded reviewed note for every source page.')
    require(isinstance(reviewed_pages, list) and all(type(page) is int for page in reviewed_pages) and
        reviewed_pages == list(range(1, count + 1)), 'Compare and confirm every original source page before staging.')
    require(len(binding['extracted_hashes']) == count, 'Extraction page map changed.', 409)
    target = binding['target_revision']
    require(type(target) is int and revision < target <= 1000000, 'Invalid target revision.', 409)
    for note in notes:
        text(note, 30000)
    out = deepcopy(package)
    section_id = PREFIX + str(target)
    require(not any(s['id'] == section_id for s in out['sections']), 'Conversion section already exists.', 409)
    rows = []
    blocks = []
    for page, note in enumerate(notes, 1):
        rows.append([str(page), METHOD + '; parser ' + binding['parser_version'], binding['extracted_hashes'][page-1],
            hashlib.sha256(note.encode()).hexdigest(), binding['source_sha256'], 'unknown', 'needs_review'])
        blocks.append({'kind': 'teaching', 'pages': [page], 'text': note})
    out['sections'].append({'id': section_id, 'title': 'Reviewed transformed notes · source fidelity needs review',
        'pages': list(range(1, count+1)), 'blocks': [{'kind': 'table', 'pages': list(range(1, count+1)),
            'headers': HEADERS, 'rows': rows}] + blocks})
    out['module_revision'] = target
    receipt = studio.stage(out, assets, expected_parent={'revision': revision, 'digest': parent_digest})
    return {**receipt, 'schema': 'anvaya.reviewed-conversion-receipt.v1', 'parent_revision': revision,
        'source_sha256': binding['source_sha256'], 'review_digest': digest(out),
        'published': False, 'semantic_confidence': 'unknown', 'source_fidelity': 'needs_review'}


def transformed_section(section):
    """A reserved section can only lower semantic authority, never certify it."""
    return section.get('id', '').startswith(PREFIX)
