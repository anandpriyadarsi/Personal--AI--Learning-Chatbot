"""Conversion previews retain originals and cannot publish or import anything."""
import hashlib
import pytest
from tests.academic_evidence_v23_fixtures import uc_owners, source_pdf, PAGE_TEXT
from tests.test_academic_evidence_v23 import inventory
from tests.test_academic_evidence_v23_web import app, token
from personal_learning_assistant.learning_studio.validation import PackageError

BASE='/academic-evidence/learning/uc100n-demo/1'

def test_pdf_draft_keeps_page_order_hash_and_review_boundaries():
    from personal_learning_assistant.learning_studio import note_draft
    raw=source_pdf();draft=note_draft.convert(raw,media_type='application/pdf')
    assert draft['schema']=='anvaya.note-draft.v1'
    assert draft['source_sha256']==hashlib.sha256(raw).hexdigest()
    assert [p['page'] for p in draft['pages']]==[1,2,3]
    assert 'observation is one case' in draft['pages'][0]['text']
    assert 'Mean score' in draft['pages'][1]['text']
    assert draft['publishable'] is False and draft['review_status']=='needs_review'
    assert all(p['semantic_confidence']=='unknown' and p['review_flags'] for p in draft['pages'])
    assert all(p['text_sha256']==hashlib.sha256(p['text'].encode()).hexdigest() for p in draft['pages'])

@pytest.mark.parametrize('raw,media',[(b'not pdf','application/pdf'),(b'%PDF-'+b'x'*8_000_000,'application/pdf'),
    (b'PK fake','application/vnd.openxmlformats-officedocument.presentationml.presentation')], ids=['invalid-pdf','oversized-pdf','unsupported-pptx'])
def test_unsupported_inputs_never_produce_publishable_drafts(raw,media):
    from personal_learning_assistant.learning_studio import note_draft
    with pytest.raises(PackageError):note_draft.convert(raw,media_type=media)


def test_explicit_review_uses_published_original_without_writing(uc_owners,tmp_path):
    c=app(uc_owners).test_client();t=token(c.get(BASE),'review_token');before=inventory(tmp_path)
    assert c.get(BASE+'/note-draft').status_code==405
    r=c.post(BASE+'/note-draft',data={'review_token':t})
    assert r.status_code==200
    html=r.get_data(as_text=True)
    assert 'Review extracted draft' in html and 'Original page 2' in html
    assert 'not published' in html and 'Mean score' in html
    assert uc_owners[2]['source']['sha256'] in html
    assert inventory(tmp_path)==before
    assert c.post(BASE+'/note-draft',data={'review_token':'forged'}).status_code==400
