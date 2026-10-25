"""Real Chromium V1.5 acceptance; public synthetic sources only."""
import os
import pytest
from .test_browser import browser,no_overflow,screenshot
from .test_v13_browser import quality_live

pytestmark=pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS')!='1',reason='Explicit browser gate flag required.')

@pytest.mark.parametrize('width',[360,390,768,1024,1366,1536,1920])
def test_mistake_recheck_fresh_question_source_and_print(browser,quality_live,width):
    from playwright.sync_api import expect
    url,s,p=quality_live;page=browser.new_page(viewport={'width':width,'height':900});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)));base=url+'/learning/modules/synthetic/1'
    page.goto(base+'?view=practice&question=q31');form=page.locator('.ls-question')
    assert 'correct_index' not in page.content() and 'Compare the original source.' not in page.content()
    page.locator('.ls-neutral-hint > summary').focus();page.keyboard.press('Enter');expect(page.locator('.ls-neutral-hint p')).to_be_visible()
    form.locator('input[type=radio][value="0"]').check();form.locator('button[type=submit]').click();expect(page.locator('.ls-feedback')).to_contain_text('Incorrect')
    form.locator('input[type=radio][value="1"]').check();form.locator('button[type=submit]').click();expect(page.locator('.ls-question-state')).to_contain_text('recovered needs recheck')
    page.locator('.ls-deliberate-recheck').focus();page.keyboard.press('Space');expect(page.locator('.ls-feedback')).to_contain_text('Deliberate recheck')
    assert s.evidence()['attempts']==2
    page.reload();expect(page.locator('.ls-recheck-evidence')).to_contain_text('unverified / insufficient evidence')
    page.locator('.ls-fresh-question').click();expect(form).to_have_attribute('data-question-id','q11')
    form.locator('.ls-source-chips a').click();assert 'page=11' in page.url and 'question=q11' in page.url
    page.locator('#ls-return-question').click();expect(form).to_have_attribute('data-question-id','q11')
    page.get_by_role('link',name='What still needs revision? · question denominators and rechecks',exact=True).click()
    # The old practice counter also contains "1 of 31" (question 11 of 31).
    # Require the actual evidence destination before starting another navigation.
    page.wait_for_url('**/quality?format=html')
    page.wait_for_load_state('load')
    expect(page.locator('main')).to_contain_text('1 of 31')
    no_overflow(page);screenshot(page,f'v15-evidence-{width}.png')
    page.goto(base+'?view=revision&budget=full');page.emulate_media(media='print')
    expect(page.locator('.ls-page-review-flags li')).to_have_count(20);expect(page.locator('.ls-page-review-flags li').last).to_be_visible()
    no_overflow(page);assert not errors;page.close()

def test_no_js_correction_stays_staged_and_old_notes_survive(browser,quality_live):
    from playwright.sync_api import expect
    from personal_learning_assistant.learning_studio.validation import PackageError
    url,s,p=quality_live;context=browser.new_context(java_script_enabled=False,viewport={'width':390,'height':844});page=context.new_page()
    base=url+'/learning/modules/synthetic/1';page.goto(base+'/coverage?issue=synthetic-issue&state=unresolved')
    expect(page.locator('.ls-review-dimensions')).to_contain_text('Source visually checked');page.locator('#ls-candidate-target').select_option('lesson-13:1')
    page.locator('#ls-candidate-text').fill('## Concept relationship\n∑ᵢ xᵢ² ≥ 0 for the stated assumptions. Compare the original diagram.\n\n'+'Long formula caption preserving every qualification. '*30)
    page.locator('#ls-candidate-reason').fill('Synthetic diagram qualification; semantic review pending.')
    page.get_by_role('button',name='Stage candidate revision 2 for review',exact=True).click();assert '/learning/staged/synthetic/2' in page.url
    expect(page.locator('.ls-lesson')).to_contain_text('Concept relationship');no_overflow(page);screenshot(page,'v15-no-js-candidate.png')
    with pytest.raises(PackageError):s.module('synthetic',2)
    page.goto(base+'?view=learn&section=lesson-13');expect(page.locator('.ls-lesson')).to_contain_text('Core concept 13')
    context.set_offline(True);page.locator('.ls-selected-original summary').click();expect(page.locator('.ls-selected-original pre')).to_be_visible();context.close()

def test_storage_denial_and_missing_selection_recovery(browser,quality_live):
    from playwright.sync_api import expect
    url,s,p=quality_live;context=browser.new_context(viewport={'width':360,'height':800})
    context.add_init_script("Object.defineProperty(window,'sessionStorage',{get(){throw new Error('denied')}})")
    page=context.new_page();base=url+'/learning/modules/synthetic/1';page.goto(base+'?view=practice&question=q31');page.click('#ls-focus')
    expect(page.locator('#ls-focus')).to_have_attribute('aria-pressed','true');page.locator('.ls-fresh-question').click();assert 'focus=1' in page.url
    page.keyboard.press('Escape');page.goto(base+'?view=source&page=999');expect(page.locator('main')).to_contain_text('does not exist')
    page.goto(base+'?view=practice&mode=recheck');expect(page.locator('main')).to_contain_text('No practice questions');no_overflow(page);context.close()
