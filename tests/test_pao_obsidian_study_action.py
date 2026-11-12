import re
import sqlite3
import pytest
from tests.test_pao_obsidian_identity import workspace
from tests.test_phase7_5_operational_tasks import _service
from personal_learning_assistant.ui.web import create_app
from personal_learning_assistant.services.operational_planner_web_service import build_operational_planner_web_service
from scripts.pao_migrate import migrate


def test_obsidian_study_preview_is_stale_safe_and_one_intent_one_task(tmp_path):
    source=workspace(tmp_path/'vault',{'A.md':'# Matrix source'})
    source.refresh_manifest()
    _,path=_service(tmp_path);migrate(path,apply=True)
    app=create_app({'TESTING':True,'PAO_V3_ENABLED':True,'OBSIDIAN_WORKSPACE_SERVICE_FACTORY':lambda:source,
        'OPERATIONAL_PLANNER_WEB_SERVICE_FACTORY':lambda:build_operational_planner_web_service(path)})
    client=app.test_client()
    preview=client.get('/planning/source/obsidian/preview?path=A.md')
    assert preview.status_code == 200
    fields=dict(re.findall(r'name="([^"]+)" value="([^"]*)"',preview.text))
    payload={**fields,'title':'Read and question the matrix example','estimated_minutes':'20','due_on':'2026-12-01'}
    assert client.post('/planning/source/obsidian/accept',data=payload).status_code == 303
    assert client.post('/planning/source/obsidian/accept',data=payload).status_code == 303
    assert client.post('/planning/source/obsidian/accept',data={**payload,'estimated_minutes':'30'}).status_code == 409
    with sqlite3.connect(path) as c:
        assert c.execute('SELECT COUNT(*) FROM planner_tasks').fetchone()[0] == 1
        assert c.execute('SELECT owner,kind,mapping_status FROM planner_task_sources').fetchone() == ('obsidian','markdown','unreviewed')
    (tmp_path/'vault'/'A.md').write_text('# Changed source')
    assert client.post('/planning/source/obsidian/accept',data=payload).status_code == 409
