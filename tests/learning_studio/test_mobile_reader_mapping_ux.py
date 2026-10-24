"""Mobile source visuals, Android fullscreen fallback and reviewed mapping journey.

Opt-in browser tests, synthetic academic content only. No device or real private
academic database is claimed. CI runs with ANVAYA_BROWSER_TESTS=1.
"""
import os
import pytest

from .test_browser import browser, no_overflow
from .test_v13_browser import quality_live

pytestmark = pytest.mark.skipif(
    os.environ.get("ANVAYA_BROWSER_TESTS") != "1",
    reason="Explicit Chromium browser gate required.",
)


def test_phone_visual_source_preview_wide_graph_and_full_view(browser, quality_live):
    from playwright.sync_api import expect
    url, _, _ = quality_live
    page = browser.new_page(viewport={"width": 390, "height": 844})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url + "/learning/modules/synthetic/1?view=learn&section=lesson-13")
    expect(page.locator(".ls-graph-advanced summary")).to_have_text("Explore relationships in detail")
    expect(page.locator(".ls-source-peek summary")).to_be_visible()
    page.locator(".ls-source-peek summary").click()
    image = page.locator(".ls-source-peek img")
    expect(image).to_be_visible()
    assert image.evaluate("(im) => im.complete && im.naturalWidth > 0")
    page.locator(".ls-graph-advanced summary").click()
    expect(page.locator(".ls-graph-advanced .ls-table-scroll")).to_be_visible()
    no_overflow(page)

    # Simulate Android WebView denial; the button must be usable, not a dead end.
    page.evaluate("() => {document.documentElement.requestFullscreen=()=>Promise.reject(new Error('denied'))}")
    page.click("#ls-fullscreen")
    expect(page.locator("#ls-fullscreen")).to_have_text("Exit full view")
    expect(page.locator("#ls-fullscreen")).to_have_attribute("aria-pressed", "true")
    assert page.locator("body").evaluate("(el) => el.classList.contains('ls-focus')")
    page.click("#ls-fullscreen")
    expect(page.locator("#ls-fullscreen")).to_have_text("Fullscreen")
    expect(page.locator("#ls-fullscreen")).to_have_attribute("aria-pressed", "false")
    assert not page.locator("body").evaluate("(el) => el.classList.contains('ls-focus')")
    no_overflow(page)
    assert not errors
    page.close()


def test_unmapped_module_link_preserves_original_revision(browser, quality_live):
    from playwright.sync_api import expect
    url, service, _ = quality_live
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(url + "/learning/modules/synthetic/1?view=learn")
    expect(page.get_by_role("link", name="Link to subject and topic")).to_be_visible()
    page.get_by_role("link", name="Link to subject and topic").click()
    expect(page.get_by_role("heading", name="Link this module to a subject")).to_be_visible()
    page.locator("#ls-candidate").select_option("0")
    page.locator("#ls-mapping-confirm").check()
    page.locator("#ls-mapping-apply").click()
    expect(page.locator("#ls-mapping-result")).to_contain_text("revision 2")
    page.get_by_role("link", name="Open staged revision").click()
    expect(page.get_by_role("button", name="Publish this revision")).to_be_visible()
    assert service.module("synthetic", 1)["mapping"] is None
    assert service.module("synthetic", 2, staged=True)["mapping"]["course_id"] == "c0"
    assert service.module("synthetic", 2, staged=True)["mapping"]["reviewed"] is True
    no_overflow(page)
    page.close()
