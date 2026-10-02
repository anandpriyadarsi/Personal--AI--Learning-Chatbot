# Coding Helper 2 — deterministic Windows validation

Feature branch: `anvaya/assessment-uc100n-coding-helper-2`.
Base main: `5916483b7c0e3af165c397faea657ed8bec5dd1d`.
Compare the fetched feature SHA with the final delivery message before proceeding.
Do not merge or change your normal working copy. The fixture creates temporary
synthetic data and deletes only that temporary fixture when stopped. It applies
existing migrations only to that disposable database, never production.

## 1. Fetch and open an isolated validation checkout (PowerShell)

```powershell
$Repo = 'C:\Users\91994\Downloads\AI chatbot'
$Validation = 'C:\Users\91994\Downloads\ANVAYA-UC100N-Helper2-validation'
$Feature = 'anvaya/assessment-uc100n-coding-helper-2'
Set-Location $Repo
git worktree list --porcelain
git status --short
git fetch origin
if ($LASTEXITCODE -ne 0) { throw 'Fetch failed; stop.' }
$Expected = (git rev-parse "origin/$Feature").Trim()
git show -s --format='%H %s' $Expected
# Compare $Expected with Alex's delivered commit SHA now.
if (Test-Path $Validation) { throw 'Validation path already exists. Reuse only after checking its HEAD and status; do not delete it.' }
git worktree add --detach $Validation $Expected
if ($LASTEXITCODE -ne 0) { throw 'Worktree creation failed; stop.' }
Set-Location $Validation
if ((git rev-parse HEAD).Trim() -ne $Expected) { throw 'Wrong checkout.' }
git status --short
git diff --check
```

Detached HEAD is intentional: this is an exact validation snapshot, not a merge.
If status reports only backup.py/dashboard.py, the repository contains legacy
CRLF blobs conflicting with its attributes. Do not commit line-ending changes.
Use the exact-byte accommodation below ONLY if this is the untouched new checkout:

```powershell
$InfoAttributes = (git rev-parse --git-path info/attributes).Trim()
Add-Content -Encoding ascii $InfoAttributes "`nbackup.py -text`ndashboard.py -text"
git status --short
```

Any remaining tracked changes need inspection; do not reset or overwrite them.

## 2. Disposable test runtime

Use Python 3.12+ and Node 22+ (the Work checks used Python 3.12.14 / Node 24.19.0).
This installs validation dependencies into this checkout only.

```powershell
py -3 -m venv .venv
$Py = Join-Path $Validation '.venv\Scripts\python.exe'
& $Py -m pip install pytest==9.1.1 Flask==3.1.3 requests==2.34.2 python-dotenv==1.2.4 mistune==3.3.4 PyYAML==6.0.3 numpy==2.5.3 pandas==3.0.6 matplotlib==3.11.2 -r requirements-assessment-browser.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency setup failed; stop.' }
& $Py -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw 'Chromium setup failed; stop.' }
$env:ANVAYA_CODING_HELPER_ENABLED = 'true'
$env:ANVAYA_CODING_HELPER_EXAM_POLICY = 'disabled'
```

These are isolated test-runtime versions; application requirements were not changed.

## 3. Automated validation

```powershell
& $Py -m pytest tests/test_assessment_coding_helper.py tests/test_assessment_coding_helper_2.py tests/test_assessment_studio_phase_c.py tests/test_assessment_studio_next_level_runner.py tests/test_assessment_runner_math_fill_ux.py -q
& $Py -m pytest tests/test_assessment_live_browser.py -q
node --test --test-isolation=none tests/js/*.test.cjs
& $Py -m compileall -q personal_learning_assistant/services/assessment_coding_helper.py personal_learning_assistant/services/coding_helper_context.py personal_learning_assistant/services/coding_operations.py personal_learning_assistant/services/assessment_runner_service.py personal_learning_assistant/repositories/sqlite/assessment_runner_repository.py personal_learning_assistant/ui/web scripts/assessment_live_acceptance.py
node --check personal_learning_assistant/ui/web/static/js/assessment_coding_helper.js
node --check personal_learning_assistant/ui/web/static/js/assessment_runner.js
git diff --check
```

Expected focused Python: 125 passed. Expected browser: 34 passed. Expected JS: 20 passed.
If a command fails, preserve its output and report it; do not weaken the gate.
Optional full regression: `& $Py -m pytest -q`. An isolated checkout has no production
`data/learning_assistant.db`; the 16 known main-baseline failures are listed in the
validation report. Do not copy or create production state to manufacture green.

## 4. Course visibility and existing Runner behaviour

Run ONE server at a time. Each command prints a unique `OPEN:` URL. Open that exact
URL; `/` deliberately returns 404. Stop with Ctrl+C before the next command.

```powershell
& $Py scripts/assessment_live_acceptance.py --course MA103N
& $Py scripts/assessment_live_acceptance.py --course CY100N
& $Py scripts/assessment_live_acceptance.py --course UC103N
& $Py scripts/assessment_live_acceptance.py --course DE100N
& $Py scripts/assessment_live_acceptance.py --course UC100N --mode practice
& $Py scripts/assessment_live_acceptance.py --course UC100N --mode assignment
```

| Case | Expected |
| --- | --- |
| MA103N / CY100N / UC103N / DE100N | No Coding Helper, no Colab, no empty tools row |
| UC100N practice / assignment | Coding Helper and Colab visible |
| Selected answer → Save & Next → Previous → refresh | Same saved answer; timer continues |
| Change answer → Mark for Review & Next → Previous | New answer and review flag retained |
| Clear Response → refresh | Response cleared |
| Last question → Save & Next | Remains on last question; no unintended final submission |
| Open/close helper or reset helper | Answer, review flag, palette and question unchanged |
| Open Google Colab | Separate tab; original assessment intact |

Assignment is an assessment type running in practice mode; no new DB mode was added.
The synthetic fixture is for UI/state verification. Its DEMO RESPONSE is deliberately
static; it does not prove the AI's teaching quality.

## 5. Helper, Operations Map and responsive checks

In UC100N, inspect all twelve actions: Hint (levels 1–3), Explain concept,
Which operation, Explain my code (four depths), Debug, Remember, Pseudocode,
Rebuild, Viva, Predict output, Compare operations and Check understanding.

- Operations Map: choose Pandas, search groupby, expand card, Copy syntax/example,
  Learn this operation. Also inspect NumPy shape/axis/reshape, EDA and z-score cards.
- Check output rendering with live provider: code and predicted output are separate;
  copy works. No code runs inside ANVAYA.
- Ask a follow-up; Reset helper clears inputs, response and short-lived context.
  Refresh/navigation also clear context; nothing is saved as Tutor history.
- Escape and Close return focus to Coding Helper. Reset/close while loading cannot
  show a late answer or error. Failed requests preserve your typed inputs.
- At 1920×1080, 1536×864, 1366×768, 1024×768, 768 width and 390 width:
  question/options readable, no letter-by-letter wrapping, no page horizontal
  overflow, navigation reachable. The right drawer overlays rather than shrinking
  the question; phone drawer fills the screen and scrolls vertically.

## 6. Exam/global policy

Restart the fixture after changing an environment value.

```powershell
$env:ANVAYA_CODING_HELPER_ENABLED = 'false'
& $Py scripts/assessment_live_acceptance.py --course UC100N
# No helper; Colab remains (global flag governs helper only).
$env:ANVAYA_CODING_HELPER_ENABLED = 'true'
$env:ANVAYA_CODING_HELPER_EXAM_POLICY = 'disabled'
& $Py scripts/assessment_live_acceptance.py --course UC100N --mode exam
# No helper; UC100N Colab retained as in the existing exam workflow.
$env:ANVAYA_CODING_HELPER_EXAM_POLICY = 'concepts'
& $Py scripts/assessment_live_acceptance.py --course UC100N --mode exam
# Only Concept/Remember and predefined topics; no arbitrary code/question/history.
$env:ANVAYA_CODING_HELPER_EXAM_POLICY = 'unknown'
& $Py scripts/assessment_live_acceptance.py --course UC100N --mode exam
# Helper disabled (fail closed).
$env:ANVAYA_CODING_HELPER_EXAM_POLICY = 'disabled'
```

## 7. Bounded live-provider quality check

LIVE PROVIDER QUALITY: NOT VERIFIED in Work (no configured credentials).
Use your existing LLM_API_URL, LLM_API_KEY and LLM_MODEL privately. No key is printed.
If these are already in this PowerShell environment:

```powershell
& $Py scripts/assessment_live_acceptance.py --course UC100N --live-helper
```

If they are in your normal repository's `.env`, load ONLY those three fields:

```powershell
& $Py -c "import os,runpy,sys; from dotenv import dotenv_values; d=dotenv_values(sys.argv[1]); os.environ.update({k:d[k] for k in ('LLM_API_URL','LLM_API_KEY','LLM_MODEL') if d.get(k)}); sys.argv=['scripts/assessment_live_acceptance.py','--course','UC100N','--live-helper']; runpy.run_path(sys.argv[0],run_name='__main__')" "$Repo\.env"
```

Use at most five small calls initially:

1. Concept: what does groupby return? Then one follow-up: why use agg after it?
2. Operation: a numeric column contains missing values; what should I inspect before choosing fillna/dropna?
3. Predict: `a = np.arange(6).reshape(2, 3); print(a.shape)`; submit your own prediction first.
4. Debug/Viva: choose one. For debug, use a small loc/iloc mistake. For Viva, paste
   that tiny reshape and check that it asks ONE unanswered follow-up question.

Judge: simple correct teaching, why/input/output, smallest debugging correction,
student attempt before answer, explicit predicted output, no claim of execution.
For full solution, use only the explicit switch on permitted actions, then rebuild.
Do not paste real assessment keys, secrets or production data.

## 8. Return your result, then wait

Send the delivered commit SHA, course visibility results, runner persistence result,
screen widths checked, live-provider result and any screenshot/error. No merge is
part of this handoff. Leave the validation worktree and feature branch in place.
