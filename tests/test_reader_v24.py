"""Reader integration essentials are server-rendered and source-grounded."""
from tests.academic_evidence_v23_fixtures import uc_owners
from tests.test_academic_evidence_v23_web import app
from tests.test_tutor_grounding_v24 import mistake, BASE


def test_reader_has_authored_outline_and_coherent_evidence_navigation(uc_owners):
    c=app(uc_owners).test_client()
    html=c.get('/learning/modules/uc100n-demo/1?view=learn').get_data(as_text=True)
    assert 'On this lesson' in html and 'ls-v24-outline' in html
    assert '#ls-block-data-meaning-1' in html
    assert BASE+'#signals-title' in html
    assert 'Check your understanding' in html
    assert 'Original Source' in html


def test_exact_mistake_exposes_offline_help_and_review_first_conversion(uc_owners):
    mistake(uc_owners);c=app(uc_owners).test_client()
    html=c.get(BASE).get_data(as_text=True)
    assert 'Get a source-grounded hint' in html and BASE+'/tutor-help' in html
    assert 'learning_attempt:wrong-mean' in html
    assert BASE+'/note-draft' in html
    practice=c.get('/learning/modules/uc100n-demo/1?view=practice&question=mean-score').get_data(as_text=True)
    assert 'Review evidence and source-grounded help' in practice


def test_lesson_practice_navigation_explicitly_uses_lesson_mode(uc_owners):
    import re
    html=app(uc_owners).test_client().get('/learning/modules/uc100n-demo/1?view=learn').get_data(as_text=True)
    journey=re.search(r'<nav aria-label="Learning journey".*?</nav>',html,re.S).group(0)
    checkpoint=re.search(r'<section class="ls-v24-checkpoint".*?</section>',html,re.S).group(0)
    practice=[href for href in re.findall(r'href="([^"]+)"',journey+checkpoint) if 'view=practice' in href]
    assert practice and all('mode=lesson' in href for href in practice)
