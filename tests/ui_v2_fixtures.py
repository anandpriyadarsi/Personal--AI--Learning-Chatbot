"""Deterministic, disposable UI acceptance data; never reads a user's stores."""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from threading import Thread

from werkzeug.serving import make_server

from tests.test_phase7_5_obsidian_reader_routes import _real_client
from tests.test_phase7_5_15_10_notes_obsidian_separation import _service as notes_service
from tests.test_phase7_5_home_dashboard import _dashboard_fixture
from tests.test_phase7_5_courses_topics import _result_fixture
from tests.test_phase7_5_operational_notes_resources import _service as resources_service
from tests.test_phase7_5_12_2_web import SearchFake, ReaderFake
from personal_learning_assistant.services.course_dashboard_service import build_course_catalogue_from_result

MARKDOWN = '''---
title: LU Factorization
tags: [linear-algebra, revision]
---
# LU Factorization

Elimination records row operations as lower triangular multipliers. This synthetic study note explains **A = LU**.

## Worked example

> [!NOTE] Study checkpoint
> Verify the product before moving to the next topic.

| Step | Operation | Result |
| --- | --- | --- |
| 1 | Eliminate the first column | Upper triangular matrix |
| 2 | Record multipliers | Lower triangular matrix |

```python
matrix = [[2, 4], [1, 3]]
# A deliberately long synthetic code line: ''' + 'matrix_' * 28 + '''
```

## Connections

Continue with [[Rank]] and [[Missing concept]]. Ελληνικά · हिन्दी · 日本語.

<script>window.__unsafeMarkdown = true</script>

''' + '\n\n'.join(f'## Practice checkpoint {i}\n\nExplain why the multipliers belong in L. Check the dimensions and reconstruct the original matrix.' for i in range(1, 7))

class SyntheticKnowledgeReader(ReaderFake):
    def start_reading(self, **values):
        return {"session_id": "synthetic-reading", "accepted": True}
    def heartbeat(self, **values):
        return {"accepted": True}
    def end_reading(self, **values):
        return {"accepted": True}


def build_ui_fixture(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    client, note_path, database_path, config = _real_client(root, MARKDOWN)
    (note_path.parent / 'Rank.md').write_text('# Rank\n\nThe number of independent columns. See [[LU]].\n', encoding='utf-8')
    notes, repository = notes_service(root)
    first = notes.create_typed_note({
        'title': 'Elimination practice', 'course': 'MA103N', 'card_style': 'iris',
        'key_points': 'Record multipliers\nVerify LU equals A\nUse pivoting carefully',
        'body': MARKDOWN,
    })
    notes.create_typed_note({'title': 'Vector space checklist', 'course': 'MA103N', 'body': '# Vector spaces\n\nCheck closure under addition and multiplication.', 'card_style': 'square'})
    notes.create_typed_note({'title': 'Data cleaning notes', 'course': 'UC100N', 'body': '# Data cleaning\n\nInspect missing values first.', 'card_style': 'preview'})
    resources, _, resource_path = resources_service(root)
    app = client.application
    study = app.config['OBSIDIAN_STUDY_SERVICE_FACTORY']()
    app.config.update(
        HOME_DASHBOARD_PROVIDER=_dashboard_fixture,
        COURSE_CATALOGUE_PROVIDER=lambda: build_course_catalogue_from_result(_result_fixture()),
        ANVAYA_NOTES_SERVICE_FACTORY=lambda: notes,
        UNIFIED_SEARCH_SERVICE_FACTORY=SearchFake,
        KNOWLEDGE_READER_SERVICE_FACTORY=SyntheticKnowledgeReader,
    )
    # Legacy /notes treats a Resources factory as an explicit request for the retired
    # notes surface. Keep that compatibility override scoped to Resources requests.
    from flask import request
    @app.before_request
    def configure_resources_only():
        if request.path.startswith('/resources'):
            app.config['NOTES_RESOURCES_WEB_SERVICE_FACTORY'] = lambda: resources
        else:
            app.config.pop('NOTES_RESOURCES_WEB_SERVICE_FACTORY', None)

    # The configured workspace is the same real read-only filesystem adapter used by the study service.
    from personal_learning_assistant.services.obsidian_workspace_service import ObsidianWorkspaceService
    from personal_learning_assistant.repositories.filesystem.obsidian_workspace_reader import ObsidianWorkspaceReader
    workspace = ObsidianWorkspaceService(config, ObsidianWorkspaceReader)
    app.config['OBSIDIAN_WORKSPACE_SERVICE_FACTORY'] = lambda: workspace
    routes = {
        'home': '/', 'vault': '/obsidian', 'obsidian-reader': '/obsidian/note?path=Math%2FLU.md',
        'notes': '/notes', 'notes-reader': '/notes/view/' + first['id'],
        'knowledge': '/knowledge?q=LU', 'knowledge-reader': '/knowledge/item/d-lu',
        'courses': '/courses', 'resources': '/resources',
    }
    return {'app': app, 'routes': routes, 'note_path': note_path, 'database_path': database_path,
            'notes': notes, 'notes_repository': repository, 'note_id': first['id'], 'resources_path': resource_path,
            'config': config, 'workspace': workspace, 'study': study}


@contextmanager
def live_ui(root):
    fixture = build_ui_fixture(Path(root))
    server = make_server('127.0.0.1', 0, fixture['app'], threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    fixture['base'] = f'http://127.0.0.1:{server.server_port}'
    try:
        yield fixture
    finally:
        server.shutdown()
        thread.join(timeout=5)


def fingerprint(path):
    return sha256(Path(path).read_bytes()).hexdigest()
