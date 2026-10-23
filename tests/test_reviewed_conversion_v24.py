"""The real module owner retains source bytes/history and separately stages reviews."""
from copy import deepcopy
import hashlib
import pytest
from tests.academic_evidence_v23_fixtures import uc_owners
from tests.test_academic_evidence_v23_web import app, token
from tests.test_academic_evidence_v23 import inventory
from personal_learning_assistant.learning_studio.reviewed_conversion import prepare, stage_review, HEADERS
from personal_learning_assistant.learning_studio.validation import PackageError

BASE = '/learning/modules/uc100n-demo/1/conversion'


def client(owners):
    application = app(owners)
    assert 'learning_conversion' in application.view_functions
    return application.test_client()


def review(c):
    landing = c.get(BASE)
    csrf = token(landing, 'csrf_token')
    preview = c.post(BASE + '/preview', data={'csrf_token': csrf})
    assert preview.status_code == 200
    return csrf, token(preview, 'review_token'), preview


def payload(csrf, signed):
    return {'review_token': signed, 'csrf_token': csrf, 'notes': ['Reviewed page one.', 'Mean score = 7.', 'Review cases before averaging.'],
        'reviewed_pages': [1, 2, 3], 'approve': True}


def test_review_get_and_extraction_are_read_only_and_original_is_accessible(uc_owners, tmp_path):
    c = client(uc_owners); before = inventory(tmp_path)
    csrf, signed, response = review(c)
    html = response.get_data(as_text=True)
    assert 'Reviewed notes for original page 2' in html and 'Mean score' in html
    assert 'needs review' in html and 'not verbatim source text' in html
    assert html.count('name="notes"') == html.count('name="reviewed_pages"') == 3
    assert 'separate publication review' in html
    raw = c.get(BASE + '/original.pdf')
    assert raw.status_code == 200 and 'inline' in raw.headers['Content-Disposition']
    assert hashlib.sha256(raw.data).hexdigest() == uc_owners[2]['source']['sha256']
    assert inventory(tmp_path) == before


def test_reviewed_stage_preserves_every_original_record_and_retry_receipt(uc_owners):
    c = client(uc_owners); csrf, signed, _ = review(c); data = payload(csrf, signed)
    one = c.post(BASE + '/stage', json=data, headers={'X-Learning-CSRF': csrf})
    two = c.post(BASE + '/stage', json=data, headers={'X-Learning-CSRF': csrf})
    assert one.status_code == two.status_code == 201
    assert one.json == two.json and one.json['published'] is False
    studio = uc_owners[1]
    old = studio.module('uc100n-demo', 1, public=False)
    new = studio.module('uc100n-demo', 2, staged=True, public=False)
    assert new['pages'] == old['pages'] and new['questions'] == old['questions']
    assert new['revision'] == old['revision'] and new['mapping'] == old['mapping']
    assert new['sections'][:-1] == old['sections'] and new['history'] == [1]
    assert studio.source('uc100n-demo', 2, staged=True) == studio.source('uc100n-demo', 1)
    assert studio.asset('uc100n-demo', 2, 'assets/cases.png', staged=True) == studio.asset('uc100n-demo', 1, 'assets/cases.png')
    source_map = new['sections'][-1]['blocks'][0]
    assert source_map['headers'] == HEADERS
    assert source_map['rows'][1][3] == hashlib.sha256(data['notes'][1].encode()).hexdigest()
    assert source_map['rows'][1][-2:] == ['unknown', 'needs_review']
    with pytest.raises(PackageError):
        studio.module('uc100n-demo', 2)
    data['notes'][1] = 'A changed retry must conflict.'
    assert c.post(BASE + '/stage', json=data, headers={'X-Learning-CSRF': csrf}).status_code == 409


@pytest.mark.parametrize('change', ['forged', 'wrong_route', 'missing_review', 'boolean_review', 'unsafe_note', 'missing_approval', 'cross_site', 'missing_csrf'])
def test_guards_prevent_unreviewed_or_foreign_stage(uc_owners, change):
    c = client(uc_owners); csrf, signed, _ = review(c); data = payload(csrf, signed)
    route = BASE + '/stage'; headers = {'X-Learning-CSRF': csrf}
    if change == 'forged': data['review_token'] += 'bad'
    if change == 'wrong_route': route = route.replace('/1/', '/2/')
    if change == 'missing_review': data['reviewed_pages'] = [1, 3]
    if change == 'boolean_review': data['reviewed_pages'] = [True, 2, 3]
    if change == 'unsafe_note': data['notes'][0] = '<script>active markup</script>'
    if change == 'missing_approval': data['approve'] = False
    if change == 'cross_site': headers['Origin'] = 'https://foreign.invalid'
    if change == 'missing_csrf': headers = {}; data.pop('csrf_token')
    response = c.post(route, json=data, headers=headers)
    assert response.status_code in {400, 403, 409}
    with pytest.raises(PackageError): uc_owners[1].module('uc100n-demo', 2, staged=True)


def test_stale_active_parent_source_and_mapping_are_rejected(uc_owners):
    studio = uc_owners[1]; context = prepare(studio, 'uc100n-demo', 1)
    notes = [p['text'] for p in context['draft']['pages']]
    package = deepcopy(uc_owners[2]); package['module_revision'] = 2
    assets = {'assets/cases.png': studio.asset('uc100n-demo', 1, 'assets/cases.png')}
    studio.stage(package, assets); studio.publish('uc100n-demo', 2)
    with pytest.raises(PackageError, match='parent|stale|active|changed'):
        stage_review(studio, 'uc100n-demo', 1, context['binding'], notes, [1, 2, 3], approved=True)
    # Original-source preview is read-only, but never treats an old revision as current.
    with pytest.raises(PackageError): prepare(studio, 'uc100n-demo', 1)


def test_registry_and_catalogue_changes_invalidate_review(uc_owners):
    studio = uc_owners[1]; context = prepare(studio, 'uc100n-demo', 1)
    notes = [p['text'] for p in context['draft']['pages']]
    old_loader = studio.source_loader
    studio.source_loader = lambda _: b'%PDF-changed'
    with pytest.raises(PackageError, match='source changed'):
        stage_review(studio, 'uc100n-demo', 1, context['binding'], notes, [1, 2, 3], approved=True)
    studio.source_loader = old_loader
    studio.catalogue_loader = lambda: {'available': True, 'courses': []}
    with pytest.raises(PackageError, match='catalogue'):
        stage_review(studio, 'uc100n-demo', 1, context['binding'], notes, [1, 2, 3], approved=True)


def test_transformed_projections_never_inherit_verified_original_status(uc_owners):
    studio = uc_owners[1]
    # Verify original page metadata in a separate immutable parent revision.
    p = deepcopy(uc_owners[2]); p['module_revision'] = 2
    for page in p['pages']: page['status'] = 'verified'; page['review_flags'] = []
    assets = {'assets/cases.png': studio.asset('uc100n-demo', 1, 'assets/cases.png')}
    studio.stage(p, assets); studio.publish('uc100n-demo', 2)
    context = prepare(studio, 'uc100n-demo', 2)
    result = stage_review(studio, 'uc100n-demo', 2, context['binding'], [p['text'] for p in context['draft']['pages']], [1, 2, 3], approved=True)
    studio.publish('uc100n-demo', result['revision'])
    from personal_learning_assistant.learning_studio.educational_projection import build_preview
    preview = build_preview(studio, 'uc100n-demo', 3, catalogue=studio.catalogue_loader())
    assert preview['sections'][0]['blocks'][0]['source_refs'][0]['semantic_status'] == 'verified'
    transformed = preview['sections'][-1]['blocks'][1]
    assert transformed['authority'] == 'reviewed_transformed_notes'
    assert transformed['source_refs'][0]['semantic_status'] == 'needs_review'
    assert transformed['source_refs'][0]['semantic_confidence'] == 'unknown'


def test_review_tokens_expire_and_do_not_survive_app_restart(uc_owners, monkeypatch):
    c = client(uc_owners); csrf, signed, _ = review(c); data = payload(csrf, signed)
    other = client(uc_owners); other_csrf = token(other.get(BASE), 'csrf_token')
    assert other.post(BASE + '/stage', json=data, headers={'X-Learning-CSRF': other_csrf}).status_code == 400
    import itsdangerous.timed
    original_time = itsdangerous.timed.time.time
    monkeypatch.setattr(itsdangerous.timed.time, 'time', lambda: original_time() + 1900)
    assert c.post(BASE + '/stage', json=data, headers={'X-Learning-CSRF': csrf}).status_code == 400


def test_exact_review_retry_after_separate_publication_returns_original_receipt(uc_owners):
    c = client(uc_owners); csrf, signed, _ = review(c); data = payload(csrf, signed)
    one = c.post(BASE + '/stage', json=data, headers={'X-Learning-CSRF': csrf})
    assert one.status_code == 201
    uc_owners[1].publish('uc100n-demo', 2)
    two = c.post(BASE + '/stage', json=data, headers={'X-Learning-CSRF': csrf})
    assert two.status_code == 201 and two.json == one.json
    data['notes'][0] += ' Changed replay.'
    assert c.post(BASE + '/stage', json=data, headers={'X-Learning-CSRF': csrf}).status_code == 409


def test_next_existing_revision_and_uploads_do_not_start_a_new_conversion(uc_owners):
    from io import BytesIO
    c = client(uc_owners); csrf, signed, _ = review(c)
    response = c.post(BASE + '/preview', data={'csrf_token': csrf, 'source': (BytesIO(b'fake'), 'new.pdf')})
    assert response.status_code == 400
    assert c.post(BASE + '/stage', json=payload(csrf, signed), headers={'X-Learning-CSRF': csrf}).status_code == 201
    assert c.post(BASE + '/preview', data={'csrf_token': csrf}).status_code == 409


def test_browser_visible_csrf_token_cannot_forge_a_review_signature(uc_owners):
    from itsdangerous import URLSafeTimedSerializer
    c = client(uc_owners); csrf, _, _ = review(c)
    binding = prepare(uc_owners[1], 'uc100n-demo', 1)['binding']
    binding['csrf_digest'] = hashlib.sha256(csrf.encode()).hexdigest()
    forged = URLSafeTimedSerializer(csrf, salt='reviewed-conversion-v24').dumps(binding)
    assert c.post(BASE + '/stage', json=payload(csrf, forged), headers={'X-Learning-CSRF': csrf}).status_code == 400


@pytest.mark.parametrize('suffix', ['', '/original.pdf', '/preview', '/stage'])
def test_conversion_rejects_every_query_field(uc_owners, suffix):
    c = client(uc_owners)
    response = c.get(BASE + suffix + '?forged=1') if suffix in ('', '/original.pdf') else c.post(BASE + suffix + '?forged=1')
    assert response.status_code == 400


@pytest.mark.parametrize('key', ['csrf_token', 'review_token', 'approve', 'unexpected'])
def test_form_scalars_are_unique_and_unknown_fields_rejected(uc_owners, key):
    from werkzeug.datastructures import MultiDict
    c = client(uc_owners); csrf, signed, _ = review(c)
    data = MultiDict([('csrf_token', csrf), ('review_token', signed), ('approve', 'stage'),
        ('notes', 'Page one'), ('notes', 'Page two'), ('notes', 'Page three'),
        ('reviewed_pages', '1'), ('reviewed_pages', '2'), ('reviewed_pages', '3')])
    data.add(key, 'duplicate-or-unsupported')
    assert c.post(BASE + '/stage', data=data).status_code == 400
    with pytest.raises(PackageError): uc_owners[1].module('uc100n-demo', 2, staged=True)


def test_strict_json_rejects_duplicates_unknown_fields_and_malformed_scalars(uc_owners):
    import json
    c = client(uc_owners); csrf, signed, _ = review(c)
    data = payload(csrf, signed)
    duplicate = json.dumps(data)[:-1] + ',"approve":true}'
    assert c.post(BASE + '/stage', data=duplicate, content_type='application/json', headers={'X-Learning-CSRF': csrf}).status_code == 400
    for key, value in [('extra', 'unsupported'), ('review_token', []), ('csrf_token', {}), ('approve', 'true')]:
        malformed = {**data, key: value}
        assert c.post(BASE + '/stage', json=malformed, headers={'X-Learning-CSRF': csrf}).status_code == 400


@pytest.mark.parametrize('suffix,limit', [('/preview', 20000), ('/stage', 450000)])
def test_route_size_bound_applies_before_csrf_and_owner_work(uc_owners, monkeypatch, suffix, limit):
    from urllib.parse import urlencode
    import personal_learning_assistant.ui.web.learning_conversion_v24 as routes
    c = client(uc_owners); csrf = token(c.get(BASE), 'csrf_token')
    def forbidden(*args, **kwargs):
        raise AssertionError('Oversized HTTP body reached conversion/owner work')
    monkeypatch.setattr(routes, 'prepare', forbidden)
    monkeypatch.setattr(routes, 'stage_review', forbidden)
    # Valid browser-visible CSRF ensures this tests the parser bound, not a token failure.
    body = urlencode({'csrf_token': csrf, 'notes': 'x' * limit})
    assert c.post(BASE + suffix, data=body, content_type='application/x-www-form-urlencoded').status_code == 413
    # The same bound applies before strict JSON parsing.
    assert c.post(BASE + suffix, data='{"notes":"' + 'x' * limit + '"}',
        content_type='application/json', headers={'X-Learning-CSRF': csrf}).status_code == 413
