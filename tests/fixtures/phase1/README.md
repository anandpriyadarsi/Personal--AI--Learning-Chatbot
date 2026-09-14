# Sanitized Phase 1 fixtures

These files are synthetic test data. They intentionally contain no personal
academic records, vault paths, credentials, or private documents.

They exist so the repository can prove that legacy loaders start and read
without depending on the developer's ignored `data/` directory.

The fixture set mirrors the ten legacy stores exercised by
`tests/test_phase1_fixture_integrity.py`.

Important preserved edge cases:

- `resources.json` is deliberately **zero bytes**.
- `notes.json` contains one note with blank content.
- `courses.json` includes two courses, an active course, topics, and a document link.
- `learning_memory.json` represents weak/mastered memory plus notes and no activities.
- `course_progress_history.json` contains history for two courses.
- `weekly_study_plans.json` contains a 240-minute synthetic V9.1 plan.
- `multi_course_weekly_plans.json` deliberately records the historical-style
  requested/stored mismatch (120 requested, 108 stored).
- assessment/workspace fixtures are synthetic and intentionally small.
- `obsidian_config.json` contains no machine-specific vault path.

These fixtures are not production data and must never replace the user's real
local `data/` directory.
