# Phase 2 Fix 20 — Clean-Clone & Repository Hygiene Gate

## Purpose

Fix 20 closes the repository/reproducibility items that remained after the
Phase 2 Fix 19 architecture gate passed.

It does not add SQLite and does not migrate or rewrite the user's private data.

## Controlled changes

Fix 20 adds or updates:

- `.gitattributes`
- `tests/fixtures/phase1/README.md`
- ten sanitized legacy fixture stores under `tests/fixtures/phase1/`
- `tests/test_phase1_fixture_integrity.py`
- `fix20_clean_clone_gate.ps1`
- this document

The real local `data/` directory is not copied, edited, or committed.

## Sanitized fixture policy

The tracked fixture set exists only for automated tests. It uses synthetic
course/note/assessment values and contains no real vault path, credentials, or
private academic records.

The ten stores are:

1. `notes.json`
2. `resources.json` — deliberately zero bytes
3. `courses.json`
4. `learning_memory.json`
5. `course_progress_history.json`
6. `weekly_study_plans.json`
7. `multi_course_weekly_plans.json`
8. `assessments.json`
9. `assessment_workspace.json`
10. `obsidian_config.json`

The fixtures preserve representative legacy edge cases while remaining safe to
track publicly.

## Updated fixture-integrity test

`tests/test_phase1_fixture_integrity.py` no longer assumes the developer's
private `data/` directory exists.

For every legacy loader it:

1. copies the sanitized fixture folder to `tmp_path/data`;
2. redirects config/module file constants to that temporary copy;
3. blocks writes/replaces/removes/renames under both the temporary copy and the
   developer's real configured data directory;
4. runs the legacy loader;
5. verifies both manifests remain byte-for-byte unchanged.

This makes the test meaningful in a clean clone/archive.

## Line-ending policy

`.gitattributes` establishes deterministic line endings:

- Python/Markdown/JSON and other source text: LF
- PowerShell/BAT/CMD: CRLF
- PDFs, images, databases, pickle files, office files and ZIPs: binary

This prevents Windows line-ending conversion from creating misleading diffs.

## Clean-clone gate

After Fix 20 is committed and the tree is clean, run:

```powershell
.\fix20_clean_clone_gate.ps1
```

The gate:

- runs the sanitized fixture test locally;
- runs the full local regression suite;
- checks `git diff --check`;
- rejects tracked `.env`, production DB, pickle caches, or `data/**/*.json`;
- requires all Fix 20 fixture/gate files to be tracked;
- creates a temporary `git archive HEAD`;
- verifies the archive excludes private/runtime state;
- runs the full regression suite from the clean export;
- compiles the clean export;
- starts V13 and exits through menu option 40;
- removes the temporary export;
- checks that the current branch has a synchronized upstream.

## Exit codes

- `0` — clean export and upstream recoverability both pass.
- `1` — a real hygiene/test/reproducibility blocker failed.
- `2` — local code/export is good, but the tree is not committed yet or remote
  recoverability/upstream synchronization is still pending.

## Phase boundary

Do not begin Phase 3 SQLite migration tooling until:

1. Fix 19 remains green;
2. Fix 20 passes from a clean committed tree;
3. the modernization branch has a verified synchronized upstream;
4. the existing verified private backup remains available separately from Git.
