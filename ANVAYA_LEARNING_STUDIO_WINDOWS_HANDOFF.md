# Learning Studio V1.1 optional Windows demo

Automated Ubuntu/Windows Chromium CI handles layout and test verification. No manual screenshot/checklist approval is required. This optional five-to-ten minute demo uses a separate checkout and disposable fixtures; it never registers a course/source in your academic database. Do not switch an active Tutor worktree or merge to main.

```powershell
git clone --branch feature/learning-studio-v1-1 --single-branch https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot.git ANVAYA-Learning-Studio-V11
Set-Location ANVAYA-Learning-Studio-V11
git rev-parse HEAD
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-learning-studio.txt
$demoPath = Join-Path $env:TEMP ("anvaya-learning-studio-v11-" + [guid]::NewGuid().ToString("N"))
.\.venv\Scripts\python.exe -m personal_learning_assistant.learning_studio.demo --directory $demoPath --port 5091
```

Open `http://127.0.0.1:5091/learning`. Without an attachment the demo is explicitly synthetic: six courses ×12 modules plus an unmapped 20-page reader. To see the recovered real pilot, stop with Ctrl+C, choose a fresh `$demoPath`, and run:

```powershell
$pilotZip = "C:\path\to\05_RECONCILED_PILOT_CANDIDATE.zip"
.\.venv\Scripts\python.exe -m personal_learning_assistant.learning_studio.demo --directory $demoPath --pilot-zip $pilotZip --port 5091
```

Use the candidate inside the supplied V1.1 ZIP. Its SHA-256 must be `e26d03de4a300dda0186ee005745d98afa41f0a23d12d6612965079e995f6923`. The real demo has one unmapped module, 20 lessons/previews and 31 questions. Open Unmapped → Learn, enter Focus Reading, use Contents to switch views, answer wrong then correctly, and revisit Weak Questions. Copy/download its manual review brief. Revision supports Print. Semantic review and canonical course mapping remain pending. The old inconsistent V3 still fails closed.

Reuse the same disposable path to retain its history. A new path starts fresh; unrelated existing directories are refused. Original PDF bytes and a synthetic Knowledge registry live only under the demo path. Ctrl+C stops the local server. Automatic Tutor transfer is disabled.

Optional attachment validation (PowerShell, no production data):

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
$env:ANVAYA_BROWSER_TESTS = "1"
$env:ANVAYA_TEST_RECOVERED_PILOT_ZIP = $pilotZip
$env:ANVAYA_TEST_BAD_V3_ZIP = "C:\path\to\ANVAYA_Interactive_Learning_Pilot_Complete_v3.zip"
.\.venv\Scripts\python.exe -m pytest -q tests/learning_studio --junitxml=learning-studio-evidence/isolated.xml
.\.venv\Scripts\python.exe scripts/learning_studio_junit_gate.py learning-studio-evidence/isolated.xml
```

Public CI deliberately omits lecture attachments and reports four external skips; built-in browser tests must execute. Full-suite baseline failures are reported separately. See the automated validation report for exact counts and CI links. Production imports need the existing source identity and separately reviewed canonical mapping; no production conversion or migration was performed here.
