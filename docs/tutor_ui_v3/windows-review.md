# Windows PowerShell review

Windows itself was not available in the implementation environment. These commands use your existing virtual environment and installed data. Stop ANVAYA first. A dirty checkout is deliberately left untouched; do not reset or stash private records automatically.

```powershell
cd C:\path\to\Personal--AI--Learning-Chatbot
if (git status --porcelain) { throw 'Commit or separately preserve your local code edits before switching branches.' }
git fetch origin
git switch --track origin/feature/tutor-3-v2-ui
# For a later review, use: git switch feature/tutor-3-v2-ui

# The existing launcher can apply a pending restore. Refuse it for this UI review.
$anvayaReviewRoot = if ($env:ANVAYA_ANDROID_DATA_ROOT) { $env:ANVAYA_ANDROID_DATA_ROOT } else { (Get-Location).Path }
if ((Test-Path (Join-Path $anvayaReviewRoot 'restore-pending.zip')) -or (Test-Path (Join-Path $anvayaReviewRoot 'restore-journal.json'))) {
    throw 'Pending restore found. Resolve that separately; the UI review must not apply it.'
}
# Disable automatic optional Assessment activation for this launch only.
$anvayaPreviousAssessment = $env:ANVAYA_ASSESSMENT_EXTENDED
$env:ANVAYA_ASSESSMENT_EXTENDED = 'false'
try {
    .\.venv\Scripts\python.exe phase7_web.py
} finally {
    $env:ANVAYA_ASSESSMENT_EXTENDED = $anvayaPreviousAssessment
}
```

Open http://127.0.0.1:5000/agent (or the loopback port printed by the launcher). This review invocation does not activate Assessment's optional extension; existing academic records remain in place. Optional Coding remains unavailable if its previously approved schema is missing. Do not run activation or restore commands to review this UI.

Creating/opening sessions, filtering history, opening evidence, drafting prompts and saving local Coding tasks do not require paid AI. Sending to a configured real provider can cost money; use the saved transcripts and screenshots for visual review without sending.

All routine checks were performed by the implementer. Optional repeat of the focused synthetic checks:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_tutor3_v2.py tests/test_tutor_ui_v3.py tests/test_tutor_session_history_lifecycle.py tests/test_phase7_5_academic_agent_web.py tests/test_tutor_coding.py
```

Return to your previous code branch after stopping the server with Ctrl+C. Keep data files and any newly created study records; rollback is a code revert, never a database restore.
