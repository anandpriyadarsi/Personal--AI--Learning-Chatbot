import re
import pytest
import yaml
from personal_learning_assistant.ui.web import create_app
from personal_learning_assistant.services.month_plan_import_service import build_month_plan_import_service, MonthPlanImportValidationError
from tests.test_phase7_5_month_plan_import import _db, FIXTURE

@pytest.mark.parametrize('path', ['/planning/tasks', '/obsidian/disable', '/obsidian/enable', '/obsidian/connect', '/library/connected-sources/obsidian/disconnect'])
def test_unguarded_and_cross_origin_commands_rejected_before_factory(path):
    def forbidden():
        raise AssertionError('Writer reached')
    app = create_app({'TESTING': True, 'OPERATIONAL_PLANNER_WEB_SERVICE_FACTORY': forbidden,
                      'OBSIDIAN_WORKSPACE_SERVICE_FACTORY': forbidden, 'OBSIDIAN_CONNECTION_SERVICE_FACTORY': forbidden})
    client = app.test_client()
    assert client.post(path).status_code == 403
    assert client.post(path, headers={'Origin': 'https://evil.example'}).status_code == 403

@pytest.mark.parametrize('count', [999, 1000, 1001])
def test_import_cardinality_before_normalization(tmp_path, count):
    doc = yaml.safe_load(FIXTURE.read_text())
    doc['weekly_reviews'] = {}
    doc['assessments'] = []
    doc['fixed_events'] = []
    doc['recurring_routines'] = {}
    doc['planned_blocks'] = []
    doc['flexible_tasks'] = {'tasks': [{'id': str(i), 'title': 'Read'} for i in range(count)]}
    service = build_month_plan_import_service(_db(tmp_path))
    if count > 1000:
        with pytest.raises(MonthPlanImportValidationError, match='many'):
            service.preview('plan.yaml', yaml.safe_dump(doc).encode())
    else:
        result = service.preview('plan.yaml', yaml.safe_dump(doc).encode())
        assert result['valid']
        assert len(result['plan']['tasks']) == count

@pytest.mark.parametrize('key,value', [('flexible_tasks', []), ('planned_blocks', {}), ('recurring_routines', []), ('assessments', {})])
def test_invalid_collection_shapes_fail(tmp_path, key, value):
    doc = yaml.safe_load(FIXTURE.read_text())
    doc[key] = value
    with pytest.raises(MonthPlanImportValidationError):
        build_month_plan_import_service(_db(tmp_path)).preview('plan.yaml', yaml.safe_dump(doc).encode())


def test_valid_purpose_token_works_and_other_purpose_host_expiry_fail(monkeypatch):
    from tests.test_phase7_5_operational_planner_routes import FakePlanner
    from personal_learning_assistant.ui.web.pao_commands import command_token
    fake = FakePlanner()
    app = create_app({'TESTING': True, 'OPERATIONAL_PLANNER_WEB_SERVICE_FACTORY': lambda: fake})
    client = app.test_client()
    with app.test_request_context():
        token = command_token('planning')
        wrong = command_token('obsidian')
    assert client.post('/planning/tasks', data={'title': 'Read', 'pao_token': token}).status_code == 303
    assert len(fake.calls) == 1
    for headers, value in [({}, wrong), ({'Origin': 'http://evil.example'}, token), ({'Sec-Fetch-Site': 'cross-site'}, token)]:
        assert client.post('/planning/tasks', data={'title': 'Read', 'pao_token': value}, headers=headers).status_code == 403
    assert client.post('/planning/tasks', base_url='http://evil.example', data={'pao_token': token}).status_code == 403
    import itsdangerous.timed
    now = itsdangerous.timed.time.time()
    monkeypatch.setattr(itsdangerous.timed.time, 'time', lambda: now + 1900)
    assert client.post('/planning/tasks', data={'pao_token': token}).status_code == 403
    assert len(fake.calls) == 1


def test_ingestion_refuses_root_and_file_symlinks(tmp_path):
    from personal_learning_assistant.ingestion.source_resolver import SourceRootResolver, SourceUnsafePathError
    root = tmp_path/'vault'; root.mkdir()
    (root/'A.md').write_text('safe')
    linked = tmp_path/'linked'; linked.symlink_to(root, target_is_directory=True)
    with pytest.raises(SourceUnsafePathError):
        SourceRootResolver({'vault': linked})
    (root/'B.md').symlink_to(root/'A.md')
    with pytest.raises(SourceUnsafePathError):
        SourceRootResolver({'vault': root}).resolve('vault/B.md')


def test_json_array_command_is_rejected_without_writer():
    app = create_app({'TESTING':True})
    assert app.test_client().post('/obsidian/note/reading/start',json=[1]).status_code == 403
