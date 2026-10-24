"""Learning Studio reading-quality visual acceptance without touching assessment data."""
import os

import pytest

from .test_browser import browser, no_overflow, screenshot
from .test_v13_browser import quality_live

pytestmark=pytest.mark.skipif(
    os.environ.get('ANVAYA_BROWSER_TESTS') != '1',
    reason='Run the explicit Chromium browser gate in CI.',
)


@pytest.mark.parametrize('width',[390,768,1366,1920])
def test_source_linked_lesson_visual_hierarchy(browser,quality_live,width):
    from playwright.sync_api import expect
    url,service,module = quality_live
    page=browser.new_page(viewport={'width':width,'height':900})
    failures=[]
    page.on('pageerror',lambda error:failures.append(str(error)))
    base=url+'/learning/modules/synthetic/1'
    page.goto(base+'?view=learn&section=lesson-13')
    expect(page.locator('.ls-lesson > h2')).to_contain_text('Lesson 13')
    expect(page.locator('.ls-lesson-banner')).to_be_visible()
    expect(page.locator('.ls-lesson-thumbnail img')).to_have_count(1)
    expect(page.locator('.ls-content-label')).not_to_have_count(0)
    expect(page.locator('.ls-reflection-intro')).to_be_visible()
    expect(page.locator('.ls-reflection-grid')).to_be_visible()
    assert page.locator('.ls-reflection-grid').evaluate('(el)=>getComputedStyle(el).gridTemplateColumns.split(" ").length') == (1 if width <= 860 else 2)
    expect(page.locator('.ls-lesson-progress')).to_have_attribute('aria-valuenow','13')
    expect(page.locator('.ls-lesson-progress')).to_have_attribute('aria-valuemax','20')
    assert page.locator('.ls-lesson-thumbnail img').evaluate('(img)=>img.complete && img.naturalWidth > 0')
    assert page.locator('.ls-lesson-banner').evaluate('(el)=>getComputedStyle(el).display') == 'flex'
    assert page.locator('.ls-block-teaching h2').count() >= 1
    source_href=page.locator('.ls-lesson-thumbnail').get_attribute('href')
    assert 'view=source' in source_href and 'page=13' in source_href
    no_overflow(page)
    screenshot(page,f'reader-refresh-learn-{width}.png')
    page.locator('.ls-teachback-input').fill('Both source claims remain separate.')
    page.locator('.ls-save-teachback').click()
    expect(page.locator('.ls-teachback-status')).to_contain_text('Self-report saved')
    assert not failures
    page.close()


@pytest.mark.parametrize('width',[390,1366])
def test_practice_revision_and_source_hierarchy(browser,quality_live,width):
    from playwright.sync_api import expect
    url,service,module=quality_live
    page=browser.new_page(viewport={'width':width,'height':900})
    base=url+'/learning/modules/synthetic/1'
    page.goto(base+'?view=practice&question=q13')
    expect(page.locator('.ls-practice-header h2')).to_contain_text('Practice')
    expect(page.locator('.ls-practice-navigation')).to_be_visible()
    form=page.locator('.ls-question')
    expect(form.locator('legend')).to_contain_text('Synthetic question 13')
    assert form.locator('fieldset>legend').count() == 1
    form.locator('input[value="0"]').check()
    assert form.locator('label:has(input:checked)').count() == 1
    no_overflow(page)
    screenshot(page,f'reader-refresh-practice-{width}.png')
    page.goto(base+'?view=revision&budget=full')
    expect(page.locator('.ls-revision-header h2')).to_contain_text('Day-before-exam')
    expect(page.locator('.ls-budget-nav a[aria-current="page"]')).to_have_count(1)
    expect(page.locator('.ls-review-stats')).to_be_visible()
    expect(page.locator('.ls-review-method').first).to_be_visible()
    assert page.locator('.ls-review-method').first.evaluate('(el)=>el.open') is False
    expect(page.locator('.ls-revision>.ls-block-teaching')).not_to_have_count(0)
    no_overflow(page)
    screenshot(page,f'reader-refresh-revision-{width}.png')
    page.goto(base+'?view=source&page=13')
    expect(page.locator('.ls-source-header h2')).to_contain_text('Original Source')
    expect(page.locator('#source-page-13 img')).to_have_count(1)
    no_overflow(page)
    page.close()


def test_review_dashboard_keeps_denominator_and_read_only_contract(browser,quality_live):
    from playwright.sync_api import expect
    url,service,module=quality_live
    before=service.store.path.read_bytes()
    page=browser.new_page(viewport={'width':390,'height':844})
    page.goto(url+'/learning/modules/synthetic/1/quality?format=html')
    expect(page.locator('.ls-evidence-metrics>div')).to_have_count(4)
    expect(page.locator('.ls-evidence-method')).to_be_visible()
    expect(page.locator('.ls-evidence-metrics')).to_contain_text('31')
    expect(page.locator('.ls-quality-item')).to_have_count(31)
    no_overflow(page)
    assert service.store.path.read_bytes()==before
    page.close()


def test_no_javascript_learn_and_revision_remain_readable(browser,quality_live):
    from playwright.sync_api import expect
    url,service,module=quality_live
    context=browser.new_context(java_script_enabled=False,viewport={'width':390,'height':844})
    page=context.new_page()
    page.goto(url+'/learning/modules/synthetic/1?view=learn&section=lesson-13')
    expect(page.locator('.ls-lesson > h2')).to_contain_text('Lesson 13')
    expect(page.locator('.ls-block-teaching')).to_contain_text('Core concept 13')
    expect(page.locator('.ls-lesson-thumbnail')).to_be_visible()
    no_overflow(page)
    page.goto(url+'/learning/modules/synthetic/1?view=revision&budget=full')
    expect(page.locator('.ls-revision-guide')).to_be_visible()
    expect(page.locator('.ls-revision>.ls-block-teaching')).to_contain_text('Concept 20')
    no_overflow(page)
    context.close()
