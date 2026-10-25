from personal_learning_assistant.ui.web import create_app


def test_versioned_static_is_cached_but_academic_pages_are_fresh():
    app = create_app({'TESTING':True})
    with app.test_request_context():
        from flask import url_for
        url = url_for('static',filename='js/app.js')
    assert '?v=' in url
    client = app.test_client()
    response = client.get(url)
    assert response.status_code == 200
    assert response.cache_control.private and response.cache_control.max_age == 300
    assert client.get(url,headers={'If-None-Match':response.headers['ETag']}).status_code == 304
    assert client.get('/static/js/app.js?v=obsolete').cache_control.max_age == 0
    assert client.get('/').cache_control.no_store


def test_changed_asset_bytes_get_a_new_url(tmp_path):
    from flask import url_for
    app = create_app({'TESTING':True})
    app.static_folder = str(tmp_path)
    asset = tmp_path/'app.js'; asset.write_text('first')
    with app.test_request_context():
        first = url_for('static',filename='app.js')
    asset.write_text('changed content')
    with app.test_request_context():
        second = url_for('static',filename='app.js')
    assert first != second
