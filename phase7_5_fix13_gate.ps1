param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "================================================================"
    Write-Host " PHASE 7.5.13 OPERATIONAL PLANNER + TASKS + CALENDAR: BLOCKED"
    Write-Host "================================================================"
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

function Hash-Tree {
    param([string]$Root,[string[]]$RelativeExcludes=@())
    $excluded = @{}
    foreach ($item in $RelativeExcludes) {
        $excluded[$item.Replace("\","/")] = $true
    }
    $result = @{}
    if (-not (Test-Path $Root -PathType Container)) {
        return $result
    }
    $resolved = (Resolve-Path $Root).Path
    Get-ChildItem $Root -File -Recurse -Force |
        Sort-Object FullName |
        ForEach-Object {
            $relative = $_.FullName.Substring($resolved.Length).TrimStart("\","/").Replace("\","/")
            if ($relative -match '(^|/)__pycache__(/|$)' -or $relative -match '\.(pyc|pyo)$') {
                return
            }
            if (-not $excluded.ContainsKey($relative)) {
                $result[$relative] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
            }
        }
    return $result
}

function Assert-Hash-Map-Unchanged {
    param([hashtable]$Before,[hashtable]$After,[string]$Label)
    if ($Before.Count -ne $After.Count) {
        Stop-Gate "$Label file count changed."
    }
    foreach ($key in $Before.Keys) {
        if (-not $After.ContainsKey($key)) {
            Stop-Gate "$Label removed file: $key"
        }
        if ($Before[$key] -ne $After[$key]) {
            Stop-Gate "$Label changed file: $key"
        }
    }
}

if (-not (Test-Path $Python -PathType Leaf)) {
    $resolvedCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $resolvedCommand) {
        Stop-Gate "Python interpreter was not found."
    }
    $PythonResolved = $resolvedCommand.Source
} else {
    $PythonResolved = (Resolve-Path $Python).Path
}

$ExpectedBranch = "main"
$branch = (git branch --show-current).Trim()
if ($branch -ne $ExpectedBranch) {
    Stop-Gate "Expected branch main but found $branch."
}

$PlanPath = "docs/superpowers/plans/2026-09-20-phase7-5-13-operational-planner.md"
if (-not (Test-Path $PlanPath -PathType Leaf)) {
    Stop-Gate "Phase 7.5.13 implementation plan is missing."
}
$BaseCommit = (git log -1 --format=%H -- $PlanPath).Trim()
if ([string]::IsNullOrWhiteSpace($BaseCommit)) {
    Stop-Gate "Could not derive the Phase 7.5.13 plan commit."
}
$HeadCommit = (git rev-parse HEAD).Trim()
if ($HeadCommit -ne $BaseCommit) {
    Stop-Gate "Expected uncommitted implementation on plan commit $BaseCommit but found $HeadCommit."
}

$allowed = @(
    "requirements.txt",
    "personal_learning_assistant/repositories/sqlite/migrations/0006_operational_planner.sql",
    "personal_learning_assistant/repositories/sqlite/month_plan_import_repository.py",
    "personal_learning_assistant/repositories/sqlite/planner_task_repository.py",
    "personal_learning_assistant/repositories/sqlite/daily_agenda_repository.py",
    "personal_learning_assistant/repositories/sqlite/weekly_review_repository.py",
    "personal_learning_assistant/repositories/sqlite/operational_calendar_repository.py",
    "personal_learning_assistant/services/month_plan_import_service.py",
    "personal_learning_assistant/services/operational_task_service.py",
    "personal_learning_assistant/services/operational_calendar_service.py",
    "personal_learning_assistant/services/daily_agenda_service.py",
    "personal_learning_assistant/services/weekly_review_service.py",
    "personal_learning_assistant/services/operational_planner_web_service.py",
    "personal_learning_assistant/ui/web/routes.py",
    "personal_learning_assistant/ui/web/templates/planning.html",
    "personal_learning_assistant/ui/web/templates/calendar.html",
    "personal_learning_assistant/ui/web/templates/home.html",
    "personal_learning_assistant/ui/web/templates/_planning_operational.html",
    "personal_learning_assistant/ui/web/templates/_calendar_operational.html",
    "personal_learning_assistant/ui/web/templates/_home_operational_today.html",
    "personal_learning_assistant/ui/web/templates/planning_tasks.html",
    "personal_learning_assistant/ui/web/templates/planning_month_plan.html",
    "personal_learning_assistant/ui/web/templates/planning_day.html",
    "personal_learning_assistant/ui/web/templates/planning_weekly_review.html",
    "personal_learning_assistant/ui/web/static/css/app.css",
    "tests/fixtures/phase7_5/month_plan_minimal.yaml",
    "tests/fixtures/phase7_5/month_plan_october_shape.yaml",
    "tests/test_phase7_5_month_plan_import.py",
    "tests/test_phase7_5_operational_tasks.py",
    "tests/test_phase7_5_operational_calendar.py",
    "tests/test_phase7_5_daily_agenda.py",
    "tests/test_phase7_5_weekly_review.py",
    "tests/test_phase7_5_operational_planner_routes.py",
    "tests/test_phase7_5_calendar_grades.py",
    "tests/test_phase7_5_obsidian_study_repository.py",
    "PHASE7_5_FIX13_OPERATIONAL_PLANNER.md",
    "phase7_5_fix13_gate.ps1"
)
$allowedSet = @{}
foreach ($item in $allowed) { $allowedSet[$item] = $true }

$working = @(git status --porcelain=v1 -uall)
if ($working.Count -eq 0) {
    Stop-Gate "Phase 7.5.13 implementation is not present in the working tree."
}
foreach ($line in $working) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $path = $line.Substring(3).Trim().Replace("\","/")
    if ($path.Contains(" -> ")) { $path = $path.Split(" -> ")[-1] }
    if ($path -match '(^|/)__pycache__(/|$)' -or $path -match '\.(pyc|pyo)$') { continue }
    if (-not $allowedSet.ContainsKey($path)) {
        Stop-Gate "Out-of-scope working-tree change: $path"
    }
}

$stagedBefore = @(git diff --cached --name-only)
if ($stagedBefore.Count -ne 0) {
    Stop-Gate "Implementation files must remain unstaged while the gate runs."
}

if (-not (Test-Path "./data/learning_assistant.db" -PathType Leaf)) {
    Stop-Gate "Production SQLite database is missing."
}
$dbBefore = (Get-FileHash "./data/learning_assistant.db" -Algorithm SHA256).Hash
$authorityBefore = $null
$authorityExistedBefore = Test-Path "./.phase4_authority.json" -PathType Leaf
if ($authorityExistedBefore) {
    $authorityBefore = (Get-FileHash "./.phase4_authority.json" -Algorithm SHA256).Hash
}
$jsonBefore = Hash-Tree "./data" @("learning_assistant.db")
$retrievalBefore = Hash-Tree "./.phase5_retrieval"
$obsidianBefore = Hash-Tree "./personal_learning_assistant" @(
    "repositories/sqlite/migrations/0006_operational_planner.sql",
    "repositories/sqlite/month_plan_import_repository.py",
    "repositories/sqlite/planner_task_repository.py",
    "repositories/sqlite/daily_agenda_repository.py",
    "repositories/sqlite/weekly_review_repository.py",
    "repositories/sqlite/operational_calendar_repository.py",
    "services/month_plan_import_service.py",
    "services/operational_task_service.py",
    "services/operational_calendar_service.py",
    "services/daily_agenda_service.py",
    "services/weekly_review_service.py",
    "services/operational_planner_web_service.py",
    "ui/web/routes.py",
    "ui/web/templates/planning.html",
    "ui/web/templates/calendar.html",
    "ui/web/templates/home.html",
    "ui/web/templates/_planning_operational.html",
    "ui/web/templates/_calendar_operational.html",
    "ui/web/templates/_home_operational_today.html",
    "ui/web/templates/planning_tasks.html",
    "ui/web/templates/planning_month_plan.html",
    "ui/web/templates/planning_day.html",
    "ui/web/templates/planning_weekly_review.html",
    "ui/web/static/css/app.css"
)

$vaultHashScript = @'
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from obsidian_integration import get_vault_path

EXCLUDED = {".obsidian", ".trash", ".git", "node_modules"}
root_value = get_vault_path()
if not root_value:
    print("SKIP")
    raise SystemExit(0)
root = Path(root_value)
if root.is_symlink() or not root.is_dir():
    print("INVALID")
    raise SystemExit(0)
digest = hashlib.sha256()
for current_root, dir_names, file_names in os.walk(str(root), topdown=True, followlinks=False):
    current = Path(current_root)
    dir_names[:] = [
        name for name in sorted(dir_names)
        if name not in EXCLUDED and not (current / name).is_symlink()
    ]
    for name in sorted(file_names):
        if not name.lower().endswith(".md"):
            continue
        path = current / name
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\n")
print("OK:" + digest.hexdigest())
'@

function Get-Vault-Manifest {
    $temp = Join-Path ([IO.Path]::GetTempPath()) ("p7513_vault_" + [guid]::NewGuid().ToString("N") + ".py")
    try {
        Set-Content -LiteralPath $temp -Value $vaultHashScript -Encoding UTF8
        $value = (& $PythonResolved $temp).Trim()
        if ($LASTEXITCODE -ne 0) {
            Stop-Gate "Could not hash configured Obsidian vault."
        }
        return $value
    } finally {
        Remove-Item $temp -Force -ErrorAction SilentlyContinue
    }
}
$vaultBefore = Get-Vault-Manifest

Run-Step "[1/20] Migration/schema/constraints" {
    & $PythonResolved -m pytest -q `
        tests/test_phase7_5_month_plan_import.py `
        -k "0006 or schema or integrity"
}

Run-Step "[2/20] Month YAML safe parser + semantic validation" {
    & $PythonResolved -m pytest -q `
        tests/test_phase7_5_month_plan_import.py `
        -k "preview or unsafe or datesheet"
}

Run-Step "[3/20] Import preview purity + exact course resolution" {
    & $PythonResolved -m pytest -q `
        tests/test_phase7_5_month_plan_import.py `
        -k "write_free or unknown or preview"
}

Run-Step "[4/20] Import approval/idempotency/provenance" {
    & $PythonResolved -m pytest -q `
        tests/test_phase7_5_month_plan_import.py `
        -k "approval or idempotent or provenanced"
}

Run-Step "[5/20] Import reconciliation/manual-edit conflicts" {
    & $PythonResolved -m pytest -q `
        tests/test_phase7_5_month_plan_import.py `
        -k "manually or changed_import or conflict"
}

Run-Step "[6/20] Task lifecycle/validation" {
    & $PythonResolved -m pytest -q tests/test_phase7_5_operational_tasks.py
}

Run-Step "[7/20] Recurrence materialization" {
    & $PythonResolved -m pytest -q `
        tests/test_phase7_5_operational_calendar.py `
        -k "recurrence or materializes"
}

Run-Step "[8/20] Calendar Month/Week/Day + confirmed exam scheduling" {
    & $PythonResolved -m pytest -q tests/test_phase7_5_operational_calendar.py
}

Run-Step "[9/20] Daily agenda GET purity + deterministic selection" {
    & $PythonResolved -m pytest -q `
        tests/test_phase7_5_daily_agenda.py `
        -k "preview or generate"
}

Run-Step "[10/20] Agenda placement/capacity/shutdown" {
    & $PythonResolved -m pytest -q tests/test_phase7_5_daily_agenda.py
}

Run-Step "[11/20] Daily review + rollover + tomorrow draft" {
    & $PythonResolved -m pytest -q `
        tests/test_phase7_5_daily_agenda.py `
        -k "close or rollover"
}

Run-Step "[12/20] Weekly review aggregation/persistence" {
    & $PythonResolved -m pytest -q tests/test_phase7_5_weekly_review.py
}

Run-Step "[13/20] Operational planner web routes + POST/PRG" {
    & $PythonResolved -m pytest -q tests/test_phase7_5_operational_planner_routes.py
}

Run-Step "[14/20] Existing Planning/Calendar/Home regressions" {
    & $PythonResolved -m pytest -q `
        tests/test_phase7_5_progress_planning.py `
        tests/test_phase7_5_calendar_grades.py `
        tests/test_phase7_5_home_dashboard.py `
        tests/test_phase7_5_anvaya_shell.py
}

Run-Step "[15/20] Complete Phase 7.5 web regressions" {
    $tests = @(
        Get-ChildItem "./tests" -Filter "test_phase7_5_*.py" -File |
            Sort-Object Name |
            ForEach-Object { $_.FullName }
    )
    & $PythonResolved -m pytest -q @tests
}

Run-Step "[16/20] Phase 7.1-7.4 recovery/runtime regressions" {
    & $PythonResolved -m pytest -q `
        tests/test_phase7_runtime_inventory.py `
        tests/test_phase7_recovery_bundle.py `
        tests/test_phase7_restore_rehearsal.py `
        tests/test_phase7_consumer_watch.py
}

Run-Step "[17/20] Complete pytest suite" {
    $legacyNode = "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
    & $PythonResolved -m pytest -q --deselect $legacyNode
}

Run-Step "[18/20] Python compile + exact PyYAML pin + pip check" {
    & $PythonResolved -m compileall -q `
        personal_learning_assistant/repositories/sqlite/month_plan_import_repository.py `
        personal_learning_assistant/repositories/sqlite/planner_task_repository.py `
        personal_learning_assistant/repositories/sqlite/daily_agenda_repository.py `
        personal_learning_assistant/repositories/sqlite/weekly_review_repository.py `
        personal_learning_assistant/repositories/sqlite/operational_calendar_repository.py `
        personal_learning_assistant/services/month_plan_import_service.py `
        personal_learning_assistant/services/operational_task_service.py `
        personal_learning_assistant/services/operational_calendar_service.py `
        personal_learning_assistant/services/daily_agenda_service.py `
        personal_learning_assistant/services/weekly_review_service.py `
        personal_learning_assistant/services/operational_planner_web_service.py `
        personal_learning_assistant/ui/web/routes.py
    if ($LASTEXITCODE -ne 0) { Stop-Gate "Python compilation failed." }
    & $PythonResolved -c "import yaml; assert yaml.__version__ == '6.0.3', yaml.__version__"
    if ($LASTEXITCODE -ne 0) { Stop-Gate "Installed PyYAML does not match 6.0.3." }
    & $PythonResolved -m pip check
}

Write-Host ""
Write-Host "[19/20] Fresh/production SQLite integrity + protected hashes"
$tempDb = Join-Path ([IO.Path]::GetTempPath()) ("p7513_" + [guid]::NewGuid().ToString("N") + ".db")
$freshScript = @'
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
path = sys.argv[1]
assert apply_migrations(path) == (1,2,3,4,5,6)
c = sqlite3.connect(path)
assert tuple(row[0] for row in c.execute("SELECT version FROM schema_migrations ORDER BY version")) == (1,2,3,4,5,6)
assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
assert c.execute("PRAGMA foreign_key_check").fetchall() == []
c.close()
'@
$freshScriptPath = Join-Path ([IO.Path]::GetTempPath()) ("p7513_fresh_check_" + [guid]::NewGuid().ToString("N") + ".py")
try {
    Set-Content -LiteralPath $freshScriptPath -Value $freshScript -Encoding UTF8
    & $PythonResolved $freshScriptPath $tempDb
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Fresh migration/integrity verification failed."
    }
} finally {
    Remove-Item $freshScriptPath -Force -ErrorAction SilentlyContinue
    Remove-Item $tempDb -Force -ErrorAction SilentlyContinue
}
& $PythonResolved -c "import sqlite3; c=sqlite3.connect('file:data/learning_assistant.db?mode=ro',uri=True); assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; assert c.execute('PRAGMA foreign_key_check').fetchall()==[]; c.close()"
if ($LASTEXITCODE -ne 0) { Stop-Gate "Production SQLite integrity/FK check failed." }
if ((Get-FileHash "./data/learning_assistant.db" -Algorithm SHA256).Hash -ne $dbBefore) {
    Stop-Gate "Tests changed production SQLite."
}
$authorityExistsAfter = Test-Path "./.phase4_authority.json" -PathType Leaf
if ($authorityExistsAfter -ne $authorityExistedBefore) {
    Stop-Gate "Authority-control file existence changed."
}
if ($authorityExistedBefore -and (Get-FileHash "./.phase4_authority.json" -Algorithm SHA256).Hash -ne $authorityBefore) {
    Stop-Gate "Authority-control file changed."
}
Assert-Hash-Map-Unchanged $jsonBefore (Hash-Tree "./data" @("learning_assistant.db")) "Production JSON/data files"
Assert-Hash-Map-Unchanged $retrievalBefore (Hash-Tree "./.phase5_retrieval") "Retrieval index"
Assert-Hash-Map-Unchanged $obsidianBefore (Hash-Tree "./personal_learning_assistant" @(
    "repositories/sqlite/migrations/0006_operational_planner.sql",
    "repositories/sqlite/month_plan_import_repository.py",
    "repositories/sqlite/planner_task_repository.py",
    "repositories/sqlite/daily_agenda_repository.py",
    "repositories/sqlite/weekly_review_repository.py",
    "repositories/sqlite/operational_calendar_repository.py",
    "services/month_plan_import_service.py",
    "services/operational_task_service.py",
    "services/operational_calendar_service.py",
    "services/daily_agenda_service.py",
    "services/weekly_review_service.py",
    "services/operational_planner_web_service.py",
    "ui/web/routes.py",
    "ui/web/templates/planning.html",
    "ui/web/templates/calendar.html",
    "ui/web/templates/home.html",
    "ui/web/templates/_planning_operational.html",
    "ui/web/templates/_calendar_operational.html",
    "ui/web/templates/_home_operational_today.html",
    "ui/web/templates/planning_tasks.html",
    "ui/web/templates/planning_month_plan.html",
    "ui/web/templates/planning_day.html",
    "ui/web/templates/planning_weekly_review.html",
    "ui/web/static/css/app.css"
)) "Protected application code"
if ((Get-Vault-Manifest) -ne $vaultBefore) {
    Stop-Gate "Configured Obsidian vault Markdown changed during the gate."
}

Write-Host ""
Write-Host "[20/20] Scoped git diff + forbidden dependencies + runtime-artifact exclusion"
$routeSource = Get-Content "./personal_learning_assistant/ui/web/routes.py" -Raw
foreach ($token in @("import sqlite3", "sqlite3.", "yaml.safe_load", "yaml.load", ".execute(")) {
    if ($routeSource.Contains($token)) {
        Stop-Gate "Forbidden route dependency found: $token"
    }
}
$importSource = Get-Content "./personal_learning_assistant/services/month_plan_import_service.py" -Raw
if ($importSource.Contains("yaml.load(")) {
    Stop-Gate "Unsafe yaml.load found in month-plan import service."
}
if (-not $importSource.Contains("yaml.safe_load(")) {
    Stop-Gate "Safe YAML loader is missing."
}

try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Could not mark Phase 7.5.13 files intent-to-add for scope validation."
    }
    git diff --check $BaseCommit --
    if ($LASTEXITCODE -ne 0) { Stop-Gate "git diff --check failed." }
    $changes = @(git diff --name-only $BaseCommit --)
    foreach ($path in $changes) {
        $normalized = $path.Trim().Replace("\","/")
        if ($normalized -match '(^|/)__pycache__(/|$)' -or $normalized -match '\.(pyc|pyo)$') {
            continue
        }
        if (-not $allowedSet.ContainsKey($normalized)) {
            Stop-Gate "Phase 7.5.13 changed an out-of-scope file: $normalized"
        }
    }
    foreach ($item in $allowed) {
        if (-not ($changes -contains $item)) {
            Stop-Gate "Required Phase 7.5.13 file is absent from scoped diff: $item"
        }
    }
} finally {
    git reset --quiet -- $allowed 2>$null
}

Write-Host ""
Write-Host "================================================================"
Write-Host " PHASE 7.5.13 OPERATIONAL PLANNER + TASKS + CALENDAR: PASS"
Write-Host "================================================================"
Write-Host "Month-plan preview remained side-effect free and approval is explicit."
Write-Host "Unknown subject mid-sem slots remained null until confirmed."
Write-Host "Tasks, calendar views, daily agendas, bounded rollover, and weekly reviews are operational."
Write-Host "Production SQLite, JSON/config, retrieval index, Obsidian Markdown, and protected code remained unchanged by the gate."
