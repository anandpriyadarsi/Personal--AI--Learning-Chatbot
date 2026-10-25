import pytest
from tests.test_nested_notes import notes
from personal_learning_assistant.ui.web import create_app

@pytest.fixture
def client(notes):
    repo,native,s,note=notes
    app=create_app({'TESTING':True,'ANVAYA_NOTES_SERVICE_FACTORY':lambda:native})
    return app.test_client(),app,repo,s,note

def test_lazy_sections_csrf_and_stale(client):
    c,app,repo,s,note=client
    base=f'/notes/sections/{note}'
    result=c.get(base)
    assert result.status_code==200
    assert 'body' not in result.json['sections'][0]
    data={'action':'add','title':'Speaking','body':'Secret section text','expected_updated_at':repo.get_note(note)['updated_at']}
    assert c.post(base,json=data).status_code==403
    headers={'X-Notes-CSRF':app.extensions['notes_media_csrf']}
    created=c.post(base,json=data,headers=headers)
    assert created.status_code==200
    assert c.post(base,json=data,headers=headers).status_code==409
    detail=c.get(base+'/'+created.json['section_id'])
    assert detail.json['body']=='Secret section text'
    html=c.get(f'/notes/view/{note}').text
    assert 'Secret section text' not in html
    assert 'data-sections-url' in html
    assert 'notes-media-upload' in html

def test_section_xss_sanitized(client):
    c,app,repo,s,note=client
    added=s.change(note,'add',expected_updated_at=repo.get_note(note)['updated_at'],title='<script>x</script>',body='<script>alert(1)</script> [x](javascript:alert(2))')
    html=c.get(f'/notes/sections/{note}/'+added['section_id']).json['html']
    assert '<script>' not in html and 'href="javascript:' not in html

def test_malformed_mutations_return_validation_error(client):
    c,app,repo,s,note=client
    h={'X-Notes-CSRF':app.extensions['notes_media_csrf']}
    for data in [{'action':'add','title':'Missing version'}, {'action':'reorder','expected_updated_at':repo.get_note(note)['updated_at'],'order':[{}]}]:
        assert c.post(f'/notes/sections/{note}',json=data,headers=h).status_code==400
