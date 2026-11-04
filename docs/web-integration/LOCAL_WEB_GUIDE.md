# ANVAYA local web application

Use Python 3.12. Keep an existing checkout and its private `data` directory; do not replace or delete study records. These commands bind only to `127.0.0.1`. No public deployment or Android build is required.

## Windows PowerShell

For an existing checkout:

```powershell
cd path\to\Personal--AI--Learning-Chatbot
git switch main
git pull --ff-only
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe phase7_web.py
```

Open **http://127.0.0.1:5000**. Stop with Ctrl+C. To use another port:

```powershell
$env:PLA_WEB_PORT="5001"
.\.venv\Scripts\python.exe phase7_web.py
```

For a new checkout, first run `git clone https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot.git`, then enter that directory. A new checkout does not contain your existing private databases or phone records.

## Linux / macOS

```bash
cd path/to/Personal--AI--Learning-Chatbot
git switch main
git pull --ff-only
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python phase7_web.py
```

Use `PLA_WEB_PORT=5001 .venv/bin/python phase7_web.py` if port 5000 is busy. Keep the terminal running for background processing. Jobs resume on startup; processing does not run while the server is stopped.

## Files and subjects

1. Open Library. Enter the configured semester and subject; create a lecture folder with **+**. Courses remains the course/topic authority. No sixth subject is invented.
2. After adding a course through Courses, open **Library settings → Refresh configured subject folders**. Only explicit startup/settings operations reconcile academic roots and source identities; Library GET requests do not migrate data.
3. Import multiple original files into the selected folder. The checked processing notice enables local preparation for this import. Uncheck it to store without indexing; existing opt-outs remain off.
4. PDFs have a visual same-origin reader. Images display as images; text and Python are inert escaped text. Office files download unchanged for a compatible installed application. No cloud viewer or conversion is assumed.
5. Content search is explicit. Ordinary browsing shows file metadata, not extracted passages. Use Details for simple Tutor status and advanced retry diagnostics.
6. Trash is recoverable and has Undo. There is no automatic purge. Permanent deletion is blocked while a study reference or source pin still needs the original.

## Author a comprehensive topic from 3–4 lectures

1. Choose **Learning Studio → Create a topic from related lectures**. Search and select 3–4 originals belonging to one real course and choose its topic. The bounded workflow accepts 2–8 lectures, up to 4 MB each / 20 MB original snapshots / 120 extracted positions. Library's ordinary per-file limit remains 100 MiB.
2. Select lecture order. **Prepare local source draft** preserves each original and its hash, creates an ordered locator manifest and a clearly labelled derived text companion. It does not claim a faithful visual conversion of PPTX or understanding of diagrams.
3. Use ordinary lesson controls to write objectives/prerequisites, definitions, detailed explanations, worked examples, misconceptions, exercises/solutions, quick checks and revision notes. Change teaching order without changing source IDs. An advanced JSON editor remains available.
4. Optionally request a teaching draft from the existing configured Tutor provider. The form shows provider host/model and requires consent for this exact lecture group. Only selected extracted text and provenance are sent; original bytes are not sent. Changed provider configuration requires renewed review. No provider is required for local manual authoring.
5. Check each QA item against the originals, **Validate and stage preview**, then **Publish this revision**. Structural checks do not certify semantic correctness. Unfinished AUTHOR prompts, incomplete rubric checks, wrong original hashes/locators or inadequate teaching structure block publication.
6. Repeated identical submissions reuse a receipt. Editing a staged/published topic through its retained authoring draft creates a newer immutable revision; changed questions get newer question revisions. Progress does not silently carry into the new revision.
7. Export the topic as one portable ZIP with all exact originals, teaching, checks, provenance and owned media. Import through the existing Learning Studio import action. Legacy V1 packages continue to work.

## Quick checks, formal tests and resume

Inline questions use server-side grading and do not expose answer keys before submission. Their history is informal practice. Formal tests, attempts, timing, grading, reports and analytics remain in Assessment Studio.

**Take a formal subject assessment** opens the canonical course's existing assessment library. If none exists, use its actual create/import/review flow; ANVAYA does not fabricate a ready test.

Under **Assessment feedback and revision**, select the canonical topic and explicitly review its relation to the lesson when the owners have different IDs. Enable read-only feedback separately. Only confirmed canonical topic evidence produces weakness suggestions; reading completion never becomes a grade or mastery update. Consent can be revoked. Source-linked revision suggestions are shown after the main lesson content.

**Finish Lesson** saves before navigating. A native form also supports completion without JavaScript and lets you mark a lesson incomplete. Continue Learning uses the canonical Studio reading-event store across browser/process restarts and is revision-specific.

## Optional AI and honest capability limits

The existing `LLM_API_URL`, `LLM_API_KEY`, `LLM_MODEL` provider configuration is optional. Keep credentials in your local environment or existing private configuration, never in Git. Preparing files for local Tutor retrieval does not transmit them. A provider is needed to generate AI prose; no live paid-provider call is certified by synthetic tests.

Scans/image-only documents and legacy PPT/DOC remain stored originals when local extraction is unavailable. OCR and faithful Office conversion are not certified or advertised as available. Text extraction does not certify diagrams, chemistry structures or mathematical layouts.

Existing external registered originals retain their owning paths. A source root must be configured through the existing `LEARNING_STUDIO_SOURCE_ROOTS` app setting for those legacy files. A missing or changed original produces an explicit repair state; no unrelated file is substituted. The normal launcher recognizes existing `data/documents` originals. Unmounted phone data has not been migrated.

## Reproduce acceptance

```bash
.venv/bin/python -m pip install -r requirements-dev.txt -r requirements-assessment-browser.txt
.venv/bin/python -m playwright install chromium
ANVAYA_BROWSER_TESTS=1 ANVAYA_WEB_ARTIFACTS=/tmp/anvaya-web-screens .venv/bin/python -m pytest tests/learning_studio/test_multilecture_browser.py -q
.venv/bin/python scripts/web_integration_benchmark.py --output /tmp/anvaya-web-benchmark.json
```

PowerShell: set `$env:ANVAYA_BROWSER_TESTS="1"` and `$env:ANVAYA_WEB_ARTIFACTS="$env:TEMP\anvaya-web-screens"`, then use `.\.venv\Scripts\python.exe` for the same pytest command. The synthetic browser journey uploads four originals, uses real local retrieval with a synthetic provider, authors/publishes a module, checks an inline answer, completes a lesson, reopens its saved position, submits a real canonical quiz, evaluates it and reads weak-topic feedback. It never imports a fabricated score.

The existing full canonical gate remains `python scripts/architecture_validation.py --require-clean --output <outside-repository-results>`. Its named private-fixture skips remain a separate unavailable certification boundary, never replaced with synthetic originals.
