# Deterministic Learning Studio handoff

Use a separate checkout. Do not switch or reset an active Tutor worktree. No merge into main is authorised. Feature branch: `feature/learning-studio-v1`. Verified base: main `f859a3c7cdf44baadc17d9bd1a6c656530c1b5bf`.

## Five-to-ten minute disposable demo (PowerShell)

Run from a parent folder where `ANVAYA-Learning-Studio` does not already exist:

```powershell
git clone --branch feature/learning-studio-v1 --single-branch https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot.git ANVAYA-Learning-Studio
Set-Location ANVAYA-Learning-Studio
git branch --show-current
git rev-parse HEAD
git status --short
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-learning-studio.txt
$demoPath = Join-Path $env:TEMP ("anvaya-learning-studio-" + [guid]::NewGuid().ToString("N"))
.\.venv\Scripts\python.exe -m personal_learning_assistant.learning_studio.demo --directory $demoPath --port 5091
```

Open `http://127.0.0.1:5091/learning`. The demo contains six explicitly synthetic registered-course fixtures ×12 modules and a separate unmapped 20-page synthetic reader. It does not read/write your real academic data. Open **Unmapped / needs review → Synthetic Learning Studio demonstration**. Use Learn, Visualise, Practice, Revision, Weak Questions and Original Source. Answer incorrectly, then retry correctly; reopen Weak Questions to see the retained mistake. Try Collapse navigation and Focus Reading. All 20 synthetic original page identities, source bytes and preview images remain available.

Ctrl+C stops the server. Reuse the printed demoPath with the same command to reopen its practice history. Choose a new path for a fresh demo. The CLI refuses unrelated existing directories; `--prepare-only` builds fixtures without starting a server.

## Automated layout gate (PowerShell)

Run in a second terminal inside the clean feature checkout:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
$env:ANVAYA_BROWSER_TESTS = "1"
$env:ANVAYA_BROWSER_ARTIFACTS = "learning-studio-evidence/browser"
.\.venv\Scripts\python.exe -m pytest -q tests/learning_studio
.\.venv\Scripts\python.exe -m pytest -q tests/test_phase7_5_web_foundation.py tests/test_phase7_5_courses_topics.py tests/test_main_startup_isolation.py tests/test_phase7_5_15_10_notes_obsidian_separation.py tests/test_phase7_5_15_14_focus_companion_analysis.py
.\.venv\Scripts\python.exe scripts/learning_studio_regression_gate.py --output learning-studio-evidence/full-suite
```

The browser tests assert desktop 1440px and mobile390px layout, actual content-width expansion, focus restoration, Contents/Escape, fullscreen denial, keyboard access, storage denial, real logo loading, source links, revision print and wrong/correct retries. Automated Windows CI uses the same tests; manual layout approval is not a substitute for a failed automated gate. Production-dependent legacy Tutor failures remain separate and are reported by the full-suite comparison.

## Supplied pilot: stop at the source-integrity gate

Do not claim the Hinduism/Buddhism/Jainism pilot was imported. The attached JSON/report hash does not match the enclosed PDF. The strict converter blocks before creating a demo directory. A matching authoritative source or reviewed corrected manifest is required; no automatic checksum rewrite is supplied.

After resolving that integrity issue, `demo --directory NEW_PATH --pilot-zip PATH` can validate and convert a consistent V3 archive in a disposable fixture. Production conversion/import still requires its actual pre-existing Knowledge source ID and canonical course mapping review; the adapter defaults to unmapped.

## Existing application configuration

Importing production-authored packages requires existing registry source roots. Configure `LEARNING_STUDIO_SOURCE_DATABASE` to the current academic registry DB and `LEARNING_STUDIO_SOURCE_ROOTS` to its logical-root mapping in create_app(config). Set `LEARNING_STUDIO_DATABASE` to a separate path ending `learning_studio.sqlite3` (default data/learning_studio.sqlite3). No DB or directory is created at startup/GET; first valid explicit stage initializes only the feature store. Do not substitute the academic DB. No academic migration, Moodle scraping, Tutor rewrite or automatic personal Notes operation is needed.
