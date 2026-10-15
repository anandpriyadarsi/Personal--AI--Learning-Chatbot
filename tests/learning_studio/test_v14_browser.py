"""V1.4 functional reading/revision acceptance on both hosted OSes."""
import os
import pytest
from .test_browser import browser, screenshot, no_overflow
from .test_v13_browser import quality_live

pytestmark=pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS')!='1',reason='Explicit browser gate flag required.')


@pytest.mark.parametrize('width',[360,390,768,1024,1366,1536,1920])
def test_selected_source_related_exercise_full_revision_and_omissions(browser,quality_live,width):
    from playwright.sync_api import expect
    url,s,p=quality_live;page=browser.new_page(viewport={'width':width,'height':900})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    base=url+'/learning/modules/synthetic/1'
    page.goto(base+'?view=learn&section=lesson-13')
    preview=page.locator('.ls-selected-original');expect(preview).to_have_count(1)
    expect(preview.locator('img')).to_have_count(1)
    preview.locator('summary').click();expect(preview.locator('img')).to_be_visible()
    expect(page.locator('.ls-related-exercise')).to_have_count(1)
    page.locator('.ls-related-exercise a').click()
    expect(page.locator('.ls-question')).to_have_attribute('data-question-id','q13')
    expect(page.locator('.ls-question')).not_to_contain_text('Compare the original source.')
    page.goto(base+'?view=revision&budget=5&section=lesson-13')
    expect(page.locator('.ls-revision-scope')).to_contain_text('omitted')
    expect(page.locator('.ls-revision-priority')).to_have_count(4)
    page.get_by_role('link',name='Full exam revision · Full revision',exact=True).click()
    expect(page.locator('.ls-full-lessons > details')).to_have_count(20)
    page.locator('.ls-full-lessons > details').nth(19).locator('summary').click()
    expect(page.locator('.ls-full-lessons')).to_contain_text('Core concept 20')
    # The print DOM includes all lesson concepts and preserved companion notes.
    page.emulate_media(media='print')
    expect(page.locator('.ls-full-lessons > details').first.locator('.ls-block-teaching')).to_be_visible()
    expect(page.locator('.ls-revision > .ls-block-teaching')).to_contain_text('list members 20')
    no_overflow(page);page.emulate_media(media='screen')
    screenshot(page,f'v14-full-revision-{width}.png')
    assert not errors
    page.close()


def test_pending_question_survives_revision_budget_source_and_lesson_detour(browser,quality_live):
    from playwright.sync_api import expect
    url,s,p=quality_live;page=browser.new_page(viewport={'width':390,'height':844})
    page.goto(url+'/learning/modules/synthetic/1?view=practice&section=lesson-13&question=q13')
    page.get_by_role('link',name='Day-before-exam Revision',exact=True).click()
    page.get_by_role('link',name='Quick 5 min · 5-minute recall',exact=True).click()
    assert 'question=q13' in page.url
    page.get_by_role('link',name='Full exam revision · Full revision',exact=True).click()
    card=page.locator('.ls-revision > .ls-block-recall').nth(5)
    card.locator('.ls-source-chips a').click()
    assert 'page=6' in page.url and 'section=lesson-06' in page.url and 'question=q13' in page.url
    page.get_by_role('link',name='Learn',exact=True).click()
    expect(page.locator('.ls-lesson > h2')).to_contain_text('Lesson 6')
    page.locator('#ls-return-question').click()
    expect(page.locator('.ls-question')).to_have_attribute('data-question-id','q13')
    page.close()


def test_full_notes_work_without_javascript_and_already_loaded_offline(browser,quality_live):
    from playwright.sync_api import expect
    url,s,p=quality_live;context=browser.new_context(java_script_enabled=False,viewport={'width':390,'height':844})
    page=context.new_page();page.goto(url+'/learning/modules/synthetic/1?view=revision&budget=full')
    context.set_offline(True)
    lesson=page.locator('.ls-full-lessons > details').nth(12);lesson.locator(':scope > summary').click()
    expect(lesson).to_contain_text('Common trap 13');expect(lesson.locator('.ls-block-teaching')).to_be_visible()
    no_overflow(page);context.close()
