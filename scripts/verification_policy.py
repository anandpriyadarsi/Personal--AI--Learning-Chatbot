"""Central conservative component graph. Edges point from provider to consumers.

Mappings are an explicit maintenance contract, not a claim of complete static
dependency analysis. Unknown files expand to every component. Full acceptance
always tests the frozen integrated tree, regardless of this selection.
"""
from __future__ import annotations

import fnmatch
from pathlib import Path

COMPONENTS = ('core', 'learning', 'library', 'media', 'assessment', 'tutor',
              'planning', 'android', 'security', 'persistence', 'ui', 'ci')
DEPENDENTS = {
    'core': set(COMPONENTS) - {'core', 'ci'},
    'persistence': {'core'}, 'security': {'core'}, 'ci': {'core'},
    'library': {'learning', 'tutor'}, 'media': {'library', 'android'},
    'android': {'media', 'library', 'ui'}, 'ui': set(),
    'learning': set(), 'assessment': set(), 'tutor': set(), 'planning': set(),
}
SOURCE = {
    'core': ('personal_learning_assistant/ui/web/routes.py', 'personal_learning_assistant/ui/web/__init__.py',
             'personal_learning_assistant/domain/**', 'personal_learning_assistant/config*', 'app.py'),
    'learning': ('personal_learning_assistant/learning_studio/**', '**/learning_*.py', '**/*reader*', '**/note_draft*.py'),
    'library': ('**/*library*', '**/*knowledge*', '**/*document*', '**/*retrieval*', '**/resources2*', '**/notes_*.py',
                'personal_learning_assistant/retrieval/**'),
    'media': ('**/*notes_media*', '**/*media_intent*', '**/*media_handoff*', '**/*attachment*', '**/*FileProvider*', '**/*file_provider*'),
    'assessment': ('**/*assessment*', '**/*cbt*', '**/*grading*', '**/*rubric*', '**/*question_quality*',
                   'ANVAYA_ASSESSMENT*PROMPT.md'),
    'tutor': ('personal_learning_assistant/tutor/**', '**/*tutor*', '**/*coding_helper*', '**/*grounded*'),
    'planning': ('**/*planning*', '**/*planner*', '**/*analysis*', '**/*daily_agenda*', '**/*study_plan*', '**/*topic_intelligence*'),
    'android': ('android/**', '**/android_*', '**/*android*'),
    'security': ('**/*security*', '**/*auth*', '**/*csrf*'),
    'persistence': ('**/migrations/**', '**/*migration*', '**/connection.py', '**/*schema*', '**/*academic_source*', '**/*source_identity*'),
    'ui': ('personal_learning_assistant/ui/web/**',),
    'ci': ('.github/**', 'scripts/*verif*', 'scripts/validation_guard/**', 'scripts/architecture_*',
           'requirements*.txt', '*lock*', 'pytest.ini', 'pyproject.toml', 'setup.cfg', '.gitattributes',
           'tests/conftest.py', 'tests/**/conftest.py', 'tests/fixtures/**', 'tests/*verif*'),
}
TEST = {
    'core': ('tests/test_phase2*.py', 'tests/test_main*.py', 'tests/test_architecture*.py'),
    'learning': ('tests/learning_studio/test_*.py', 'tests/test_learning*.py', 'tests/test_reader*.py', 'tests/test_note_draft*.py', 'tests/test_reviewed_conversion*.py'),
    'library': ('tests/test_*library*.py', 'tests/test_*document*.py', 'tests/test_*knowledge*.py', 'tests/test_*retrieval*.py', 'tests/test_*resource*.py', 'tests/test_*notes*.py'),
    'media': ('tests/test_*media*.py', 'tests/test_*attachment*.py', 'tests/test_*notes*.py'),
    'assessment': ('tests/test_*assessment*.py', 'tests/test_*grading*.py', 'tests/test_*topic_read_safety*.py'),
    'tutor': ('tests/test_*tutor*.py', 'tests/test_*coding_helper*.py', 'tests/test_phase6_grounded*.py', 'tests/learning_studio/test_*tutor*.py'),
    'planning': ('tests/test_*planning*.py', 'tests/test_*planner*.py', 'tests/test_*analysis*.py', 'tests/test_*topic_intelligence*.py', 'tests/test_*academic*.py'),
    'android': ('tests/test_*android*.py', 'tests/test_*mobile*.py', 'tests/test_*media*.py', 'tests/test_*document*.py'),
    'security': ('tests/test_*security*.py', 'tests/test_*auth*.py', 'tests/test_*csrf*.py', 'tests/test_*topic_read_safety*.py'),
    'persistence': ('tests/test_*migration*.py', 'tests/test_*schema*.py', 'tests/test_*persistence*.py', 'tests/test_*wal*.py', 'tests/test_*source*.py'),
    'ui': ('tests/test_*browser.py', 'tests/learning_studio/test_*browser.py', 'tests/test_ui*.py', 'tests/learning_studio/test_mobile*.py'),
    'ci': ('tests/test_*verif*.py', 'tests/test_architecture_gate*.py'),
}
# Mandatory existing tests for essential public synthetic academic/security
# invariants. Original private fixtures remain a separate strict release gate.
INVARIANTS = ('tests/test_topic_read_safety.py', 'tests/test_architecture_characterization.py')
SMOKE = {
    'core': ('tests/test_main_startup_isolation.py',),
    'learning': ('tests/test_reader_v24.py', 'tests/learning_studio/test_mobile_reader_delivery.py'),
    'library': ('tests/test_learning_library_read_model.py', 'tests/test_learning_library_routes.py', 'tests/test_library_document_rename.py'),
    'media': ('tests/test_learning_library_read_model.py',),
    'assessment': ('tests/test_assessment_pause_paper.py', 'tests/test_assessment_studio_phase_e.py'),
    'tutor': ('tests/test_tutor_grounding_v24.py',),
    'planning': ('tests/test_architecture_planning_context.py',),
    'android': ('tests/test_ui_v2_contract.py',),
    'security': ('tests/test_topic_read_safety.py',),
    'persistence': ('tests/test_learning_library_wal_bridge.py',),
    'ui': ('tests/test_ui_v2_contract.py', 'tests/test_library_rename_browser.py'),
    'ci': ('tests/test_smart_verify.py', 'tests/test_verification_v2.py'),
}


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def closure(seeds):
    result = set(seeds)
    while True:
        expanded = result | set().union(*(DEPENDENTS[x] for x in result))
        if result == expanded:
            return sorted(result)
        result = expanded


def affected(paths):
    seeds, reasons = set(), []
    broad = not paths
    for raw in paths:
        path = raw.replace('\\', '/')
        if not path or path.startswith('/') or '..' in Path(path).parts:
            broad = True
            reasons.append('Unsafe path; all components required')
            continue
        ordinary_documentation = (path.startswith('docs/') and Path(path).suffix.lower() in (
            '.md','.rst','.png','.jpg','.jpeg','.svg','.webp') and not any(
            term in path.lower() for term in ('academic_source','source_identity','assessment','authoring','prompt')))
        if ordinary_documentation or path in ('README.md', 'LICENSE', '.gitignore'):
            continue
        found = {c for c in COMPONENTS if matches(path, SOURCE[c]) or matches(path, TEST[c])}
        # Assessment presentation requires both secrecy and persistence, even
        # when only CSS/JS/templates were modified.
        if 'assessment' in found:
            found.update(('security', 'persistence', 'ui'))
        if not found:
            broad = True
            reasons.append('Unclassified file requires full validation: ' + path)
        else:
            seeds.update(found)
            reasons.append(path + ': ' + ', '.join(sorted(found)))
    if broad:
        seeds.update(COMPONENTS)
        reasons.append('Unknown, unsafe or empty diff: full validation required')
    return {'components': closure(seeds), 'direct_components': sorted(seeds),
            'broad': broad or bool(seeds & {'core','ci','persistence','security'}), 'reasons': reasons}


def selection(paths, root, stage='fast'):
    if stage not in ('fast', 'feature', 'integration', 'release'):
        raise ValueError('Unsupported verification stage')
    root = Path(root)
    impact = affected(paths)
    inventory = sorted(p.relative_to(root).as_posix() for p in (root/'tests').rglob('test_*.py'))
    js_inventory = sorted(p.relative_to(root).as_posix() for p in (root/'tests/js').glob('*.test.cjs'))
    blockers, selected = [], set()
    if impact['components']:
        if not inventory:
            blockers.append('Missing Python test inventory')
        for name in INVARIANTS:
            if not (root/name).is_file():
                blockers.append('Missing mandatory invariant: ' + name)
            else:
                selected.add(name)
        if stage != 'fast' and (impact['broad'] or stage in ('integration','release')):
            selected.update(inventory)
        else:
            for component in impact['components']:
                candidates = (SMOKE[component] if stage == 'fast' else
                              [p for p in inventory if matches(p, TEST[component])])
                if not candidates:
                    blockers.append('Missing affected feature inventory: ' + component)
                for p in candidates:
                    if (root/p).is_file():
                        selected.add(p)
                    else:
                        blockers.append('Missing required smoke: ' + p)
        # New feature contracts become mandatory once they exist in this tree;
        # they are never synthesized on main where the feature is unmerged.
        selected.update(p for p in inventory if matches(p, ('tests/test_*media*.py', 'tests/test_native*.py'))
                        and matches(p, tuple(pattern for c in impact['components'] for pattern in TEST[c])))
    for p in paths:
        if p.startswith('tests/') and p.endswith('.py'):
            if p in inventory:
                selected.add(p)
            else:
                blockers.append('Deleted or missing changed test: ' + p)
        if p.startswith('tests/js/') and p.endswith('.test.cjs') and p not in js_inventory:
            blockers.append('Deleted or missing changed JavaScript test: ' + p)
    js = js_inventory if impact['components'] and (stage != 'fast' or set(impact['components']) & {'assessment','ui','core','ci','security'}) else []
    if impact['components'] and set(impact['components']) & {'ui','assessment','ci'} and not js:
        blockers.append('Missing JavaScript test inventory')
    return {**impact, 'stage':stage, 'python_tests':sorted(selected), 'javascript_tests':js,
            'skipped_by_design':sorted(set(inventory)-selected),
            'browser_needed':any('browser' in p or 'mobile_reader' in p for p in selected),
            'requires_full_regression':True, 'blockers':blockers,
            'outcome':'BLOCKED' if blockers else 'PLAN_ONLY'}
