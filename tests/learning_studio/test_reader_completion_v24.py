"""Reader essentials work through HTML and reject ungrounded feedback/math."""
from html.parser import HTMLParser
import pytest

from .test_routes import client
from .test_service import publish, event
from .helpers import package
from personal_learning_assistant.learning_studio.rendering import markdown
from personal_learning_assistant.learning_studio.validation import PackageError


class PracticeForm(HTMLParser):
    def __init__(self, text):
        super().__init__(); self.fields = {}; self.action = None; self.active = False
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form' and attrs.get('id') == 'question-q1':
            self.active = True; self.action = attrs['action']; self.method = attrs.get('method')
        if self.active and tag == 'input' and attrs.get('type') == 'hidden':
            self.fields[attrs['name']] = attrs['value']

    def handle_endtag(self, tag):
        if tag == 'form': self.active = False


def native_form(c):
    return PracticeForm(c.get('/learning/modules/synthetic/1?view=practice&mode=lesson&section=lesson-1').text)


def test_native_post_redirect_feedback_is_retry_safe_and_get_is_read_only(client):
    c, s, app = client; publish(s)
    form = native_form(c)
    assert form.method == 'post'
    assert form.fields['source_sha256'] and form.fields['event_id']
    assert 'correct_index' not in form.fields and 'explanation' not in form.fields
    fields = dict(form.fields, selection='0')
    response = c.post(form.action, data=fields)
    assert response.status_code == 303
    assert 'mode=lesson' in response.location and 'section=lesson-1' in response.location
    before = s.store.path.read_bytes()
    feedback = c.get(response.location)
    assert feedback.status_code == 200
    assert 'Incorrect · attempt 1.' in feedback.text
    assert 'Compare the original source.' in feedback.text
    assert 'Authored answer: Correct' in feedback.text
    assert 'Source p1' in feedback.text and 'not proof of mastery' in feedback.text
    assert s.store.path.read_bytes() == before
    assert c.post(form.action, data=fields).status_code == 303
    assert len(s.export()['events']) == 1
    assert c.post(form.action, data=dict(fields, selection='1')).status_code == 409
    retry = native_form(c)
    assert retry.fields['event_id'] != fields['event_id']
    response = c.post(retry.action, data=dict(retry.fields, selection='1'))
    assert 'Correct · attempt 2.' in c.get(response.location).text
    assert s.practice_state('synthetic', 1)['q1']['status'] == 'recovered_needs_recheck'


def test_native_form_preserves_csrf_and_rejects_bad_context_before_writing(client):
    c, s, app = client; publish(s); form = native_form(c)
    for changes, status in [({'csrf_token': ''}, 403), ({'module_revision': '2'}, 409),
                            ({'source_sha256': '0' * 64}, 409), ({'question_revision': '2'}, 409),
                            ({'selection': '-1'}, 400), ({'mode': 'other'}, 404),
                            ({'section': 'foreign'}, 404), ({'owner': 'someone'}, 400)]:
        fields = {**form.fields, 'selection': '0', **changes}
        assert c.post(form.action, data=fields).status_code == status
    assert not s.export()['events']
    assert c.post(form.action, data=dict(form.fields, selection='0'),
                  headers={'Origin': 'https://foreign.example'}).status_code == 403


def test_feedback_requires_real_exact_owner_revision_question_and_source(client):
    c, s, app = client; p = publish(s)
    path = '/learning/modules/synthetic/1?view=practice&question=q1&attempt=recorded'
    assert 'Compare the original source.' not in c.get('/learning/modules/synthetic/1?view=practice').text
    assert c.get(path).status_code == 404
    s.attempt('synthetic', event(p, 'recorded', 0))
    assert c.get(path).status_code == 200
    p2 = package(revision=2); s.stage(p2); s.publish('synthetic', 2)
    assert c.get(path.replace('/1?', '/2?')).status_code == 404
    assert c.get(path.replace('question=q1', 'question=foreign')).status_code == 409
    assert c.get(path.replace('view=practice', 'view=learn')).status_code == 404
    for index, (column, value) in enumerate([('owner', 'foreign'), ('source_hash', '0' * 64),
                           ('question_revision', 2), ('question_id', 'foreign'),
                           ('selection', 99), ('correct', 1)]):
        # Append forged records to exercise defensive reads without weakening immutable-history triggers.
        forged_id = 'forged-' + str(index)
        with s.store.connection(write=True) as con:
            row = dict(con.execute('SELECT * FROM attempts WHERE event_id=?', ('recorded',)).fetchone())
            row.pop('seq'); row.update(event_id=forged_id, attempt_number=10 + index); row[column] = value
            con.execute('INSERT INTO attempts (' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')', tuple(row.values()))
        with pytest.raises(PackageError):
            s.attempt_feedback('synthetic', 1, forged_id, question_id='q1')
        assert c.get(path.replace('attempt=recorded', 'attempt=' + forged_id)).status_code in (404, 409)



@pytest.mark.parametrize('delimiters', [(r'\(', r'\)'), (r'\[', r'\]'), ('$$', '$$')])
def test_local_explicit_math_has_accessible_safe_fraction_root_scripts_and_greek(delimiters):
    start, end = delimiters
    rendered = str(markdown('Before ' + start + r'\frac{1}{2}+\sqrt{x_1^2}\leq\pi' + end + ' after'))
    for tag in ('<math ', '<mfrac>', '<msqrt>', '<msubsup>', '<mo>≤</mo>', '<mi>π</mi>', 'tabindex="0"'):
        assert tag in rendered
    assert 'Math needs review' not in rendered
    assert '<script' not in rendered and 'cdn' not in rendered


@pytest.mark.parametrize('formula', [r'\href{https://evil.test}{x}', r'\html{<img src=x onerror=alert(1)>}',
                                      r'\frac{1}', '{{{{{{{{{{{{{{{{{{x}}}}}}}}}}}}}}}}}}',
                                      'x' * 2200, 'x+' * 200, r'x^2^3'])
def test_unsupported_and_hostile_math_is_escaped_and_marked_for_review(formula):
    rendered = str(markdown(r'\(' + formula + r'\)'))
    assert 'Math needs review' in rendered
    assert '<img ' not in rendered and '<script' not in rendered and '<math ' not in rendered


def test_plain_currency_code_raw_html_and_unclosed_delimiters_remain_safe():
    rendered = str(markdown('Costs $5 and $10. `\\(x^2\\)`\n\n```\n$$x^2$$\n```\n\n<script>alert(1)</script>'))
    assert '<math ' not in rendered and '<script>' not in rendered
    assert '$5 and $10' in rendered and '$$x^2$$' in rendered
    assert 'Math needs review' in str(markdown(r'\(unclosed'))


def test_authored_question_math_is_readable_before_and_after_native_submission(client):
    c, s, app = client; p = package()
    p['questions'][0]['prompt'] = r'Compare \(x^2\) with the source.'
    p['questions'][0]['options'][1] = r'\(\frac{1}{2}\)'
    p['questions'][0]['explanation'] = r'Check \(\sqrt{x}\) on the cited page.'
    publish(s, p)
    html = c.get('/learning/modules/synthetic/1?view=practice').text
    assert '<msup>' in html and '<mfrac>' in html
    assert '<msqrt>' not in html
    form = native_form(c)
    response = c.post(form.action, data=dict(form.fields, selection='0'))
    assert response.status_code == 303
    assert '<msqrt>' in c.get(response.location).text
