from __future__ import annotations

import sqlite3
import pytest
from test_learning_library_read_model import library_db, fingerprint
from personal_learning_assistant.ui.web import create_app


def client(path, **config):
    return create_app({'TESTING': True, 'LEARNING_LIBRARY_DATABASE_PATH': path, **config}).test_client()


def test_list_and_detail_render_safe_links_and_keep_all_destinations(library_db):
    c = client(library_db)
    page = c.get('/library')
    assert page.status_code == 200
    text = page.get_data(as_text=True)
    for target in ('/notes', '/resources', '/knowledge', '/obsidian', '/agent', '/assessments', '/planning', '/calendar'):
        assert 'href="' + target + '"' in text
    assert 'href="/library" aria-current="page"' in text
    assert text.count('Lecture collection') == 1
    assert 'C:\\private' not in text
    assert 'retrieval availability is not checked' in text.lower()
    detail = c.get('/library/resources/r1')
    assert detail.status_code == 200
    body = detail.get_data(as_text=True)
    assert '/knowledge/item/d1' in body and '/knowledge/item/d2' in body
    assert 'View source' in body
    assert 'My LU explanation' in body
    assert '/private/vault' not in body
    assert '<form' not in body
    assert 'reading/heartbeat' not in body


@pytest.mark.parametrize('suffix', ['page=0', 'page=x', 'page=1.2', 'page_size=101', 'page_size=0', 'item_kind=notes', 'page=' , 'page=99999999999999999999999999', 'page=1&page=2'])
def test_bad_queries_are_safe_400(library_db, suffix):
    response = client(library_db).get('/library?' + suffix)
    assert response.status_code == 400
    assert 'Traceback' not in response.get_data(as_text=True)


@pytest.mark.parametrize('rid', ['missing', 'ra', 'rd'])
def test_missing_or_hidden_detail_404(library_db, rid):
    assert client(library_db).get('/library/resources/' + rid).status_code == 404


def test_unavailable_503_empty_and_no_matches_are_different(library_db, tmp_path):
    from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
    missing = tmp_path / 'secret-parent' / 'missing.db'
    c = client(missing)
    for route in ('/library', '/library/resources/r1'):
        response = c.get(route)
        assert response.status_code == 503
        assert 'Library is temporarily unavailable' in response.get_data(as_text=True)
        assert 'secret-parent' not in response.get_data(as_text=True)
    assert not missing.parent.exists()
    empty = tmp_path / 'empty.db'
    apply_migrations(empty)
    assert 'No registered material yet' in client(empty).get('/library').get_data(as_text=True)
    assert 'No matching material' in client(library_db).get('/library?course_id=absent').get_data(as_text=True)


def test_disabled_never_constructs_service_and_hides_link(tmp_path):
    def forbidden():
        raise AssertionError('disabled Library constructed service')
    c = client(tmp_path / 'absent.db', LEARNING_LIBRARY_ENABLED=False,
               LEARNING_LIBRARY_SERVICE_FACTORY=forbidden)
    assert c.get('/library').status_code == 404
    assert c.get('/library/resources/r1').status_code == 404
    assert 'href="/library"' not in c.get('/resources').get_data(as_text=True)
    assert not (tmp_path / 'absent.db').exists()


def test_factory_injection_and_gets_are_read_only(library_db):
    from personal_learning_assistant.services.learning_library_service import LearningLibraryService
    c = client('unused.db', LEARNING_LIBRARY_SERVICE_FACTORY=lambda: LearningLibraryService(database_path=library_db))
    before = fingerprint(library_db)
    assert c.get('/library').status_code == 200
    assert c.get('/library/resources/r1').status_code == 200
    assert c.post('/library').status_code == 405
    assert fingerprint(library_db) == before


def test_untrusted_title_and_url_never_become_html(library_db):
    with sqlite3.connect(library_db) as con:
        con.execute("UPDATE resources SET title=?,canonical_uri=? WHERE id='r1'",
                    ('<script>alert(1)</script>', 'javascript:alert(2)'))
    for route in ('/library', '/library/resources/r1'):
        text = client(library_db).get(route).get_data(as_text=True)
        assert '<script>alert(1)</script>' not in text
        assert '&lt;script&gt;' in text
        assert 'javascript:alert(2)' not in text


def test_pagination_preserves_filters(library_db):
    body = client(library_db).get('/library?course_id=c2&item_kind=resource&page_size=1').get_data(as_text=True)
    assert 'page=2' in body and 'page_size=1' in body and 'course_id=c2' in body
    assert 'item_kind=resource' in body
