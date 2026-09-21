param(
    [string]$PythonPath = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$ExpectedBranch = "anvaya/operational-ux-integrations"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "======================================================================="
    Write-Host " ANVAYA OPERATIONAL UX + INTEGRATIONS: BLOCKED"
    Write-Host "======================================================================="
    Write-Host $Message
    exit 1
}

function Run-Step {
    param([string]$Label,[scriptblock]$Command)
    Write-Host ""
    Write-Host $Label
    & $Command
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "$Label failed with exit code $LASTEXITCODE."
    }
}

if (-not (Test-Path $PythonPath -PathType Leaf)) {
    Stop-Gate "Project virtual-environment Python was not found at $PythonPath."
}
$PythonResolved = (Resolve-Path $PythonPath).Path

$branch = (git branch --show-current).Trim()
if ($branch -ne $ExpectedBranch) {
    Stop-Gate "Expected branch $ExpectedBranch but found $branch."
}

$status = @(git status --porcelain=v1 -uall)
if ($status.Count -ne 0) {
    Write-Host "Working-tree changes:"
    $status | ForEach-Object { Write-Host $_ }
    Stop-Gate "Working tree must be clean before the integration gate."
}

$HashScript = @'
from __future__ import annotations
from pathlib import Path
import hashlib, json

def hash_file(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()

def tree(root, suffix=None):
    root=Path(root)
    out={}
    if not root.exists():
        return out
    if root.is_file():
        out[str(root).replace("\\","/")]=hash_file(root)
        return out
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if "__pycache__" in p.parts or p.suffix in {".pyc",".pyo"}:
            continue
        if suffix and p.suffix.lower()!=suffix:
            continue
        out[str(p).replace("\\","/")]=hash_file(p)
    return out

result={}
result.update(tree("data"))
result.update(tree(".phase5_retrieval"))
try:
    import obsidian_integration
    vault=obsidian_integration.get_vault_path()
    if vault:
        result.update(tree(vault, ".md"))
except Exception:
    pass
print(json.dumps(result,sort_keys=True,separators=(",",":")))
'@

$HashScriptPath = Join-Path ([IO.Path]::GetTempPath()) ("anvaya_ux_hash_" + [guid]::NewGuid().ToString("N") + ".py")
Set-Content -LiteralPath $HashScriptPath -Value $HashScript -Encoding UTF8
$BeforeHashes = (& $PythonResolved $HashScriptPath).Trim()
if ($LASTEXITCODE -ne 0) { Stop-Gate "Could not capture protected hashes." }

Run-Step "[1/9] Focused new-feature tests" {
    & $PythonResolved -m pytest -q tests/test_operational_schedule_ux.py tests/test_alex_handoff.py tests/test_moodle_integration.py
}

Run-Step "[2/9] Existing search + live UX regressions" {
    & $PythonResolved -m pytest -q tests/test_phase7_5_12_3_live_ux_fix.py tests/test_phase7_5_12_2_recovery.py tests/test_phase7_5_12_2_web.py
}

Run-Step "[3/9] Planner regressions" {
    & $PythonResolved -m pytest -q tests/test_phase7_5_operational_calendar.py tests/test_phase7_5_operational_tasks.py tests/test_phase7_5_daily_agenda.py tests/test_phase7_5_month_plan_import.py tests/test_phase7_5_operational_planner_routes.py tests/test_phase7_5_weekly_review.py
}

Run-Step "[4/9] Obsidian + Tutor regressions" {
    & $PythonResolved -m pytest -q tests/test_phase7_5_obsidian_workspace.py tests/test_phase7_5_obsidian_reader_routes.py tests/test_phase7_5_obsidian_study_companion.py tests/test_phase7_5_academic_agent_web.py tests/test_phase6_grounded_tutor_engine.py
}

Run-Step "[5/9] Complete pytest regression" {
    & $PythonResolved -m pytest -q --deselect "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
}

Run-Step "[6/9] Compile + dependency check" {
    & $PythonResolved -m compileall -q personal_learning_assistant tests
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonResolved -m pip check
}

$FreshScript = @'
from pathlib import Path
import sqlite3, sys, tempfile
sys.path.insert(0, str(Path.cwd()))
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations

root=Path(tempfile.mkdtemp(prefix="anvaya_ux_"))
path=root/"fresh.db"
applied=apply_migrations(path)
assert applied == (1,2,3,4,5,6,7,8), applied
c=sqlite3.connect(path)
versions=tuple(row[0] for row in c.execute(
    "SELECT version FROM schema_migrations ORDER BY version"
))
assert versions == (1,2,3,4,5,6,7,8), versions
assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
assert c.execute("PRAGMA foreign_key_check").fetchall() == []
tables={row[0] for row in c.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
)}
assert {
    "routine_templates",
    "daily_agendas",
    "daily_agenda_items",
    "moodle_sync_files",
} <= tables
c.close()
print("fresh migration 0001-0008: PASS")
'@

$FreshScriptPath = Join-Path ([IO.Path]::GetTempPath()) ("anvaya_ux_fresh_" + [guid]::NewGuid().ToString("N") + ".py")
Set-Content -LiteralPath $FreshScriptPath -Value $FreshScript -Encoding UTF8
Run-Step "[7/9] Fresh migration 0001-0008 + SQLite integrity/FK" {
    & $PythonResolved $FreshScriptPath
}

Write-Host ""
Write-Host "[8/9] Protected production/index/vault hashes"
$AfterHashes = (& $PythonResolved $HashScriptPath).Trim()
if ($LASTEXITCODE -ne 0) { Stop-Gate "Could not re-capture protected hashes." }
if ($BeforeHashes -ne $AfterHashes) {
    Stop-Gate "Tests changed production data, retrieval indexes, or configured vault Markdown."
}

Write-Host ""
Write-Host "[9/9] Repository hygiene + web-boundary checks"
git diff --check
if ($LASTEXITCODE -ne 0) { Stop-Gate "git diff --check failed." }

$RouteText = Get-Content "personal_learning_assistant/ui/web/routes.py" -Raw
foreach ($token in @("import sqlite3", "sqlite3.connect(", "yaml.safe_load(", "yaml.load(")) {
    if ($RouteText.Contains($token)) {
        Stop-Gate "Forbidden route-layer dependency found: $token"
    }
}

$statusAfter = @(git status --porcelain=v1 -uall | Where-Object {
    $_ -notmatch "__pycache__" -and $_ -notmatch "\.pyc$"
})
if ($statusAfter.Count -ne 0) {
    Write-Host "Unexpected working-tree changes:"
    $statusAfter | ForEach-Object { Write-Host $_ }
    Stop-Gate "Tests left repository changes behind."
}

Remove-Item $HashScriptPath -Force -ErrorAction SilentlyContinue
Remove-Item $FreshScriptPath -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "======================================================================="
Write-Host " ANVAYA OPERATIONAL UX + INTEGRATIONS: PASS"
Write-Host "======================================================================="
Write-Host "Recurring schedule editor, daily-agenda calendar visibility,"
Write-Host "Alex ZIP handoff, Tutor chat UX, and read-only Moodle connector are green."
Write-Host "Existing search/backlinks/task workflows remain covered by regressions."
Write-Host "Production data, retrieval indexes, and configured vault Markdown were unchanged."
