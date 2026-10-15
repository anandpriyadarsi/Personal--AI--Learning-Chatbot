"""Seed/check only a newly created explicit synthetic fixture directory."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.absolute()
    if any(p.is_symlink() for p in (output, *output.parents)) or output.resolve().is_relative_to(ROOT) or output.exists():
        raise ValueError('Expected new external synthetic fixture directory')
    output.mkdir(parents=True)
    from test_assessment_studio_phase_f import _database
    from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations, discover_migrations
    path = _database(output)
    assert apply_migrations(path) == ()
    with sqlite3.connect(path) as connection:
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute("INSERT INTO planner_tasks(id,title,priority,estimated_minutes,status,created_at,updated_at) VALUES('synthetic-plan','Synthetic study','P1',30,'backlog','2026-10-01T00:30:00Z','2026-10-01T00:30:00Z')")
        expected = [(m.version, m.name, m.checksum) for m in discover_migrations()]
        ledger = connection.execute('SELECT version,name,checksum FROM schema_migrations ORDER BY version').fetchall()
        assert ledger == expected
        assert connection.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
    def files():
        return {p.name: {'size': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                for p in sorted(output.glob('learning_assistant.db*'))}
    before_files = files()
    from personal_learning_assistant.services.assessment_intelligence_service import AssessmentIntelligenceService
    from personal_learning_assistant.services.daily_agenda_service import build_daily_agenda_service
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as c:
        before = '\n'.join(c.iterdump())
    for _ in range(2):
        AssessmentIntelligenceService(path).overview()
        build_daily_agenda_service(path).preview_day('2026-10-01')
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as c:
        after = '\n'.join(c.iterdump())
    assert before == after
    report = {'synthetic': True, 'clock': '2026-10-01T00:30:00Z', 'timezone': 'Asia/Kolkata',
              'ledger': ledger, 'second_apply': [], 'integrity': 'ok', 'foreign_keys': [],
              'logical_state_unchanged': True, 'before_db_files': before_files, 'after_db_files': files(),
              'protected_source_root_database_absent': not (ROOT / 'data/learning_assistant.db').exists()}
    assert report['protected_source_root_database_absent']
    (output / 'manifest.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
