"""Real Keep-style note capture, lifecycle and read-only reader journeys."""
import os
from pathlib import Path
import pytest
from playwright.sync_api import expect
from tests.test_ui_v2_protected_browser import protected_browser
from tests.test_nested_notes_browser import live
from personal_learning_assistant.services.anvaya_notes_service import AnvayaNotesService

pytestmark = pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS') != '1', reason='Real Chromium opt-in')
EVIDENCE = Path('docs/mobile/smart-notes/screenshots')


def menu_action(page, name):
    page.locator('#notes-reader-menu>summary').click()
    page.get_by_role('button', name=name, exact=True).click()


@pytest.mark.parametrize('width', [360,390,430,1366])
def test_library_grid_list_pin_and_six_capture_paths(protected_browser, live, width):
    base, repo, note = live
    native = AnvayaNotesService(repo)
    for title in ['Lecture ideas', 'Revision checklist', 'Lab observations']:
        native.create_typed_note({'title':title, 'body':'Review this idea', 'key_points':'A useful detail\nReturn tomorrow'})
    native.change_note(note, 'pin', {'expected_updated_at':repo.get_note(note)['updated_at']})
    with protected_browser.new_context(viewport={'width':width,'height':844}) as context:
        page = context.new_page(); errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base+'/notes')
        expect(page.get_by_role('heading',name='Pinned',exact=True)).to_be_visible()
        assert page.locator('.notes-card-group').first.locator('.anvaya-note-card-link').count() == 1
        expect(page.get_by_role('button',name='Grid view')).to_have_attribute('aria-pressed','true')
        columns = page.locator('[data-notes-grid]').last.evaluate('e => getComputedStyle(e).gridTemplateColumns.split(" ").length')
        assert columns == 2
        page.get_by_role('button',name='List view').click(); page.reload()
        expect(page.get_by_role('button',name='List view')).to_have_attribute('aria-pressed','true')
        assert page.locator('[data-notes-grid]').last.evaluate('e => getComputedStyle(e).gridTemplateColumns.split(" ").length') == 1
        page.get_by_role('button',name='Grid view').click()
        fab = page.locator('#notes-create-menu>summary'); fab.click()
        for label in ['Text Note','Handwritten Note','Checklist','Image Note','Audio Note','Import Document']:
            expect(page.get_by_role('link',name=label,exact=True)).to_be_visible()
        if width == 390:
            EVIDENCE.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(EVIDENCE/'keep-fab-menu-390.png'))
        box=fab.bounding_box(); nav=page.locator('.mobile-dock')
        if nav.count() and nav.is_visible(): assert box['y']+box['height'] <= nav.bounding_box()['y']
        page.get_by_role('heading',name='My Notes',exact=True).click(); expect(page.locator('#notes-create-menu')).not_to_have_attribute('open','')
        if width == 390: page.screenshot(path=str(EVIDENCE/'keep-main-390.png'))
        if width == 1366: page.screenshot(path=str(EVIDENCE/'keep-main-1366.png'))
        fab.click(); page.get_by_role('link',name='Checklist',exact=True).click()
        expect(page.locator('#anvaya-note-body')).to_have_value('- [ ] First item\n- [ ] Next item\n')
        page.wait_for_load_state('load')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors, errors


def test_reader_main_independent_sections_focus_and_lifecycle(protected_browser, live):
    base,repo,note = live
    with protected_browser.new_context(viewport={'width':390,'height':844}) as context:
        page=context.new_page(); errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(f'{base}/notes/view/{note}')
        expect(page.get_by_text('Read clearly.',exact=True)).to_be_visible()
        expect(page.locator('.mini-note[open]')).to_have_count(1)
        first=page.locator('.mini-note').nth(1); first.locator('summary').first.click()
        second=page.locator('.mini-note').nth(2); second.locator('summary').first.click()
        expect(page.locator('.mini-note[open]')).to_have_count(3)
        expect(page.get_by_text('Speak clearly',exact=True)).to_be_visible()
        EVIDENCE.mkdir(parents=True,exist_ok=True); page.screenshot(path=str(EVIDENCE/'keep-reader-390.png'))
        page.locator('#notes-reader-menu>summary').click(); page.screenshot(path=str(EVIDENCE/'keep-reader-overflow-390.png'))
        page.get_by_role('button',name='Manage Sections',exact=True).click()
        page.locator('#section-search').fill('resilient'); expect(page.locator('.mini-note')).to_have_count(1)
        menu_action(page,'Focus Reading')
        expect(page.get_by_role('button',name='Exit focus',exact=True)).to_be_visible()
        expect(page.locator('.mini-note[open]')).to_have_count(4)
        expect(page.get_by_text('Read clearly.',exact=True)).to_be_visible()
        expect(page.locator('#notes-reader-menu')).to_be_hidden()
        expect(page.locator('.topbar')).to_be_hidden()
        expect(page.locator('#notes-media-management')).to_be_hidden()
        expect(page.locator('.mini-note-actions').first).to_be_hidden()
        page.screenshot(path=str(EVIDENCE/'keep-focus-390.png'))
        page.get_by_role('button',name='Exit focus',exact=True).click()
        expect(page.locator('#section-search')).to_have_value('resilient')
        expect(page.locator('.mini-note')).to_have_count(1)
        menu_action(page,'Add Section'); page.locator('#section-title').fill('New independent section');page.locator('#section-body').fill('New section text')
        page.get_by_role('button',name='Save section',exact=True).click();expect(page.locator('#section-editor')).to_be_hidden()
        menu_action(page,'Rename');page.locator('#note-action-value').fill('My renamed note');page.get_by_role('button',name='Save',exact=True).click()
        expect(page.get_by_role('heading',name='My renamed note',exact=True)).to_be_visible()
        menu_action(page,'Pin');expect(page.locator('#notes-reader-menu [data-note-action=pin]')).to_have_text('Unpin')
        menu_action(page,'Move to Course');page.locator('#note-action-value').fill('CS101');page.get_by_role('button',name='Save',exact=True).click()
        expect(page.locator('.anvaya-native-reader-meta')).to_contain_text('CS101')
        menu_action(page,'Delete');expect(page.locator('#note-action-dialog')).to_be_visible()
        page.get_by_role('button',name='Cancel',exact=True).click();assert repo.get_note(note)['status']=='active'
        menu_action(page,'Archive');page.locator('#note-action-save').click();expect(page).to_have_url(base+'/notes')
        page.goto(base+'/notes?view=archived');page.get_by_role('link',name='Open My renamed note',exact=True).click()
        menu_action(page,'Restore to Notes');expect(page.locator('#notes-reader-menu [data-note-action=restore]')).to_have_count(0)
        menu_action(page,'Delete');page.get_by_role('button',name='Move to Trash',exact=True).click();expect(page).to_have_url(base+'/notes')
        assert repo.get_note(note)['status']=='deleted'
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors, errors


@pytest.mark.parametrize(('kind','label','filename','mime','raw'), [
    ('audio','Audio Note','Lecture.mp3','audio/mpeg',b'ID3'+b'x'*40),
    ('image','Image Note','Diagram.png','image/png',b'\x89PNG\r\n\x1a\n'+b'x'*40),
    ('document','Import Document','Reading.txt','text/plain',b'Original reading document'),
])
def test_fab_capture_saves_original_file(protected_browser,live,kind,label,filename,mime,raw):
    base,repo,_ = live
    with protected_browser.new_context(viewport={'width':390,'height':844},accept_downloads=True) as context:
        page=context.new_page(); page.goto(base+'/notes')
        page.locator('#notes-create-menu>summary').click();page.get_by_role('link',name=label,exact=True).click()
        expect(page.get_by_role('heading',name=label,exact=True)).to_be_visible()
        page.get_by_label('Note name',exact=True).fill('Captured '+kind)
        page.locator('input[type=file]').set_input_files({'name':filename,'mimeType':mime,'buffer':raw})
        page.get_by_role('button',name='Create note',exact=True).click()
        expect(page.get_by_role('heading',name='Captured '+kind,exact=True)).to_be_visible()
        expect(page.locator('.notes-media-open')).to_have_text(filename)
        with page.expect_download() as downloaded:
            page.locator('.notes-media-open').click()
        assert Path(downloaded.value.path()).read_bytes()==raw
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('width',[360,390,430])
def test_mobile_action_shelf_keeps_visible_cards_clear_of_fab(protected_browser,live,width):
    base,repo,_ = live
    native=AnvayaNotesService(repo)
    for index in range(8):
        native.create_typed_note({'title':f'Revision {index}', 'body':'A complete note preview to read without an action button covering any text.'})
    with protected_browser.new_context(viewport={'width':width,'height':844}) as context:
        page=context.new_page();page.goto(base+'/notes')
        expect(page.locator('.global-search')).to_have_count(0)
        scroller=page.locator('#notes-library-scroll')
        expect(scroller).to_be_visible()
        for fraction in (0,.5,1):
            result=scroller.evaluate('''(e,fraction)=>{
              e.scrollTop=(e.scrollHeight-e.clientHeight)*fraction;
              const clip=e.getBoundingClientRect(),fab=document.querySelector('#notes-create-menu>summary').getBoundingClientRect();
              const visible=Array.from(e.querySelectorAll('.anvaya-note-card')).map(card=>card.getBoundingClientRect()).filter(r=>r.bottom>clip.top&&r.top<clip.bottom);
              return {clipBottom:clip.bottom,fabTop:fab.top,overlap:visible.some(r=>Math.max(r.top,clip.top)<fab.bottom&&Math.min(r.bottom,clip.bottom)>fab.top&&r.left<fab.right&&r.right>fab.left),atEnd:e.scrollTop+e.clientHeight>=e.scrollHeight-1,lastBottom:e.querySelector('.anvaya-note-card-link:last-child').getBoundingClientRect().bottom};
            }''',fraction)
            assert result['clipBottom'] <= result['fabTop']
            assert not result['overlap']
            if fraction==1:
                assert result['atEnd'] and result['lastBottom'] <= result['clipBottom']+1


@pytest.mark.parametrize('action',['Pin','Rename','Move to Course','Archive','Delete','Restore to Notes'])
def test_metadata_actions_do_not_silently_discard_dirty_section_draft(protected_browser,live,action):
    base,repo,note=live
    if action=='Restore to Notes':
        AnvayaNotesService(repo).change_note(note,'archive',{'expected_updated_at':repo.get_note(note)['updated_at']})
    with protected_browser.new_context(viewport={'width':390,'height':844}) as context:
        page=context.new_page();page.goto(f'{base}/notes/view/{note}')
        menu_action(page,'Add Section')
        page.locator('#section-title').fill('Unsaved section title')
        page.locator('#section-body').fill('Unsaved section content must survive')
        before=repo.get_note(note)
        prompts=[]
        def keep_draft(dialog):
            prompts.append(dialog.message);dialog.dismiss()
        page.on('dialog',keep_draft)
        menu_action(page,action)
        if action in ['Rename','Move to Course']:
            page.locator('#note-action-value').fill('Metadata change')
            page.get_by_role('button',name='Save',exact=True).click()
        elif action in ['Archive','Delete']:
            page.locator('#note-action-save').click()
        page.wait_for_timeout(100)
        assert prompts and 'unsaved section' in prompts[0].lower()
        expect(page.locator('#section-title')).to_have_value('Unsaved section title')
        expect(page.locator('#section-body')).to_have_value('Unsaved section content must survive')
        assert repo.get_note(note)==before


def test_dirty_section_guard_covers_navigation_and_explicit_discard(protected_browser,live):
    base,repo,note=live
    with protected_browser.new_context(viewport={'width':390,'height':844}) as context:
        page=context.new_page();page.goto(f'{base}/notes/view/{note}')
        menu_action(page,'Add Section');page.locator('#section-title').fill('Keep this draft');page.locator('#section-body').fill('Unsaved body')
        prompts=[]
        def keep_draft(dialog):
            prompts.append(dialog.type);dialog.dismiss()
        page.on('dialog',keep_draft)
        page.get_by_role('link',name='← Back to My Notes',exact=True).click()
        assert prompts==['beforeunload']
        expect(page.locator('#section-title')).to_have_value('Keep this draft')
        page.remove_listener('dialog',keep_draft)
        def discard_draft(dialog):
            prompts.append(dialog.type);dialog.accept()
        page.on('dialog',discard_draft)
        menu_action(page,'Pin')
        expect(page.locator('#notes-reader-menu [data-note-action=pin]')).to_have_text('Unpin')
        assert prompts==['beforeunload','confirm']
        assert repo.get_note(note)['pinned'] is True
        assert not any(row['title']=='Keep this draft' for row in repo.get_note(note)['sections'])


@pytest.mark.parametrize(('width','height','filters_open'),[(844,390,False),(390,530,True)])
def test_short_mobile_viewport_can_scroll_headers_filters_and_cards(protected_browser,live,width,height,filters_open):
    base,repo,_=live
    native=AnvayaNotesService(repo)
    for index in range(6): native.create_typed_note({'title':f'Short viewport {index}','body':'Reach this complete note'})
    with protected_browser.new_context(viewport={'width':width,'height':height}) as context:
        page=context.new_page();page.goto(base+'/notes')
        if filters_open: page.locator('.notes-filters>summary').click()
        scroll=page.locator('#notes-library-scroll')
        assert scroll.evaluate('e=>e.clientHeight')>=100
        scroll.evaluate('e=>e.scrollTop=e.scrollHeight')
        last=page.locator('.anvaya-note-card-link').last
        expect(last).to_be_visible()
        assert last.bounding_box()['y']+last.bounding_box()['height']<=scroll.bounding_box()['y']+scroll.bounding_box()['height']+1
        fab=page.locator('#notes-create-menu>summary');expect(fab).to_be_visible()
        assert fab.bounding_box()['y']>=scroll.bounding_box()['y']+scroll.bounding_box()['height']
        fab.click()
        menu=page.locator('#notes-create-menu nav')
        assert menu.bounding_box()['y']>=0
        page.get_by_role('link',name='Import Document',exact=True).scroll_into_view_if_needed()
        page.get_by_role('link',name='Import Document',exact=True).click()
        expect(page.get_by_role('heading',name='Import Document',exact=True)).to_be_visible()


def test_desktop_fab_has_reserved_gutter_clear_of_cards(protected_browser,live):
    base,repo,_=live
    native=AnvayaNotesService(repo)
    for index in range(6): native.create_typed_note({'title':f'Desktop note {index}','body':'Do not cover any of this content'})
    with protected_browser.new_context(viewport={'width':1366,'height':844}) as context:
        page=context.new_page();page.goto(base+'/notes')
        assert page.locator('.anvaya-note-card').evaluate_all('(cards)=>{const fab=document.querySelector("#notes-create-menu>summary").getBoundingClientRect();return cards.every(card=>card.getBoundingClientRect().right<=fab.left)}')
