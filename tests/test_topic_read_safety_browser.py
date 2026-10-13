"""Real browser navigation through default B2 read paths on exported source."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from tests.test_topic_read_safety import exported, inventory
from tests.test_assessment_live_browser import browser, playwright

SERVER = r'''
import sys
sys.dont_write_bytecode=True
from personal_learning_assistant.ui.web import create_app
from werkzeug.serving import make_server
server=make_server('127.0.0.1',0,create_app({'TESTING':True}))
print(server.server_port,flush=True)
server.serve_forever()
'''


@pytest.mark.parametrize('width',[390,768,1366,1920])
def test_planning_analysis_browser_reads_do_not_initialize(exported,tmp_path,browser,width):
    source=tmp_path/'source'
    shutil.copytree(exported,source)
    data=source/'data';data.mkdir()
    (data/'courses.json').write_text(json.dumps({'version':1,'active_course_id':'ma103n','courses':[{'id':'ma103n','code':'MA103N','name':'Linear Algebra','status':'active','topics':[{'id':'rank','name':'Matrix Rank','status':'weak','confidence':1}]}],'document_links':{}}))
    before=inventory(data)
    with (tmp_path/'server.log').open('w') as log:
        server=subprocess.Popen([sys.executable,'-u','-c',SERVER],cwd=source,stdout=subprocess.PIPE,stderr=log,text=True,
                                env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
        context=browser.new_context(viewport={'width':width,'height':900})
        try:
            port=int(server.stdout.readline().strip())
            url=f'http://127.0.0.1:{port}'
            external=[]
            def local_only(route):
                if not route.request.url.startswith(url+'/'):
                    external.append(route.request.url);route.abort()
                else:route.continue_()
            context.route('**/*',local_only)
            page=context.new_page()
            for route in ['/planning','/analysis']:
                assert page.goto(url+route).status==200
                assert page.locator('main').is_visible()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                toggle=page.locator('#nav-toggle')
                if toggle.is_visible() and toggle.get_attribute('aria-expanded')=='false':
                    toggle.focus();page.keyboard.press('Enter')
                more=page.locator('details.nav-more')
                if more.get_attribute('open') is None:
                    more.locator('summary').focus();page.keyboard.press('Enter')
                link=page.locator('a[href="/planning"]').first
                link.focus()
                assert link.evaluate('el => el === document.activeElement')
                page.reload()
            assert external==[]
        finally:
            context.close();server.terminate();server.wait(timeout=10)
            server.stdout.close()
    assert inventory(data)==before
    assert not (data/'learning_memory.json').exists()
