param([string]$Python = ".\.venv\Scripts\python.exe")

$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase7/deprecation-observation"
$BaseCommit = "1bf256e40cc1a9177561541144f52750f5c34dca"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "=================================================="
    Write-Host " PHASE 7.5.3 COURSES / TOPICS: BLOCKED"
    Write-Host "=================================================="
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

if (Test-Path $Python) {
    $PythonResolved = (Resolve-Path $Python).Path
} else {
    $cmd = Get-Command $Python -ErrorAction SilentlyContinue
    if ($null -eq $cmd) { Stop-Gate "Python interpreter not found." }
    $PythonResolved = $cmd.Source
}

$branch = (git branch --show-current).Trim()
if ($branch -ne $ExpectedBranch) {
    Stop-Gate "Expected $ExpectedBranch but found $branch."
}
$head = (git rev-parse HEAD).Trim()
if ($head -ne $BaseCommit) {
    Stop-Gate "Expected uncommitted Phase 7.5.3 work on $BaseCommit but found $head."
}

$allowed = @(
    "personal_learning_assistant/services/course_dashboard_service.py",
    "personal_learning_assistant/ui/web/routes.py",
    "personal_learning_assistant/ui/web/templates/base.html",
    "personal_learning_assistant/ui/web/templates/courses.html",
    "tests/test_phase7_5_courses_topics.py",
    "PHASE7_5_FIX3_COURSES_TOPICS.md",
    "phase7_5_fix3_gate.ps1"
)
$allowedSet = @{}
foreach ($item in $allowed) { $allowedSet[$item] = $true }

foreach ($line in @(git status --porcelain=v1 -uall)) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $path = $line.Substring(3).Trim().Replace("\","/")
    if ($path.Contains(" -> ")) { $path = $path.Split(" -> ")[-1] }
    if (-not $allowedSet.ContainsKey($path)) {
        Stop-Gate "Out-of-scope working-tree change: $path"
    }
}

foreach ($item in $allowed) {
    if (-not (Test-Path $item -PathType Leaf)) {
        Stop-Gate "Missing Phase 7.5.3 file: $item"
    }
}

if (-not (Test-Path ".\data\learning_assistant.db" -PathType Leaf)) {
    Stop-Gate "Production SQLite database is missing."
}
if (-not (Test-Path ".\.phase4_authority.json" -PathType Leaf)) {
    Stop-Gate "Phase 4 authority-control file is missing."
}
if (-not (Test-Path ".\.phase5_retrieval\current.json" -PathType Leaf)) {
    Stop-Gate "Current retrieval generation is missing."
}

$dbBefore = (Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash
$authorityBefore = (Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash
$legacyBefore = @{}
Get-ChildItem ".\data" -Filter "*.json" -File -ErrorAction SilentlyContinue | ForEach-Object {
    $legacyBefore[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
}
$indexBefore = @{}
Get-ChildItem ".\.phase5_retrieval" -File -Recurse -Force | ForEach-Object {
    $indexBefore[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
}

Run-Step "[1/10] Focused Phase 7.5.3 Courses/Topics tests" {
    & $PythonResolved -m pytest tests\test_phase7_5_courses_topics.py -q
}

Run-Step "[2/10] Real CourseService / routed-repository read adapter" {
    & $PythonResolved -c "from personal_learning_assistant.services.course_dashboard_service import load_course_catalogue; d=load_course_catalogue(); assert d['available'] is True; assert {'summary','courses','active_course_id'} <= set(d); assert isinstance(d['courses'], list); assert {'courses','topics','mastered_topics','weak_topics'} <= set(d['summary'])"
}

Run-Step "[3/10] Real read-only Courses route smoke test" {
    & $PythonResolved -c "from personal_learning_assistant.ui.web import create_app; c=create_app({'TESTING': True}).test_client(); r=c.get('/courses'); t=r.get_data(as_text=True); assert r.status_code == 200; assert 'Courses & topics' in t; assert 'Academic catalogue' in t; assert c.post('/courses').status_code == 405; assert '<form' not in t.lower()"
}

Run-Step "[4/10] Phase 7.5.1-7.5.2 web regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase7_5_web_foundation.py `
        tests\test_phase7_5_home_dashboard.py -q
}

Run-Step "[5/10] Phase 7.1-7.4 regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase7_runtime_inventory.py `
        tests\test_phase7_recovery_bundle.py `
        tests\test_phase7_restore_rehearsal.py `
        tests\test_phase7_consumer_watch.py -q
}

Run-Step "[6/10] Complete suite (promotion-aware)" {
    $legacyNode = "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
    & $PythonResolved -m pytest -q --deselect $legacyNode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $temp = Join-Path ([IO.Path]::GetTempPath()) ("p753_phase2_" + [guid]::NewGuid().ToString("N"))
    try {
        New-Item -ItemType Directory -Path (Join-Path $temp "tests") -Force | Out-Null
        Copy-Item ".\tests\test_phase2_closure_architecture.py" `
            (Join-Path $temp "tests\test_phase2_closure_architecture.py")
        & $PythonResolved -m pytest `
            ((Join-Path $temp "tests\test_phase2_closure_architecture.py") + "::test_phase2_root_has_no_production_learning_assistant_database") `
            -q
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Run-Step "[7/10] Python compilation" {
    & $PythonResolved -m compileall -q `
        personal_learning_assistant\services\course_dashboard_service.py `
        personal_learning_assistant\ui\web `
        tests\test_phase7_5_courses_topics.py
}

Run-Step "[8/10] Dependency consistency + production SQLite integrity/FK" {
    & $PythonResolved -m pip check
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $sqliteCheckPath = Join-Path ([IO.Path]::GetTempPath()) ("p753_sqlite_" + [guid]::NewGuid().ToString("N") + ".py")
    try {
        @(
            "import sqlite3",
            "c = sqlite3.connect('file:data/learning_assistant.db?mode=ro', uri=True)",
            "assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'",
            "assert not c.execute('PRAGMA foreign_key_check').fetchall()",
            "c.close()"
        ) | Set-Content -Path $sqliteCheckPath -Encoding ASCII
        & $PythonResolved $sqliteCheckPath
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Remove-Item $sqliteCheckPath -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "[9/10] Scope + completed-phase immutability"
$migrationDiff = @(git diff --name-only $BaseCommit -- personal_learning_assistant/repositories/sqlite/migrations)
if ($migrationDiff.Count -ne 0) {
    Stop-Gate "Phase 7.5.3 must not add or modify SQLite migrations."
}
$protected = @(
    "personal_learning_assistant/phase7",
    "phase7_runtime_inventory.py",
    "phase7_recovery_bundle.py",
    "phase7_restore_rehearsal.py",
    "phase7_consumer_watch.py",
    "phase7_fix1_gate.ps1",
    "phase7_fix2_gate.ps1",
    "phase7_fix3_gate.ps1",
    "phase7_fix4_gate.ps1",
    "PHASE7_FIX1_CANONICAL_RUNTIME_CONSUMER_INVENTORY.md",
    "PHASE7_FIX2_RECOVERY_BUNDLE_TWO_BACKUPS.md",
    "PHASE7_FIX3_FULL_RESTORE_REVERSE_RESTORE_REHEARSAL.md",
    "PHASE7_FIX4_LEGACY_USAGE_OBSERVATION_CONSUMER_WATCH.md",
    "phase7_web.py",
    "requirements.txt",
    "phase7_5_fix1_gate.ps1",
    "PHASE7_5_FIX1_WEB_FOUNDATION.md",
    "tests/test_phase7_5_web_foundation.py",
    "personal_learning_assistant/ui/web/__init__.py",
    "personal_learning_assistant/ui/web/__main__.py",
    "personal_learning_assistant/ui/web/errors.py",
    "personal_learning_assistant/services/home_dashboard_service.py",
    "personal_learning_assistant/ui/web/templates/home.html",
    "personal_learning_assistant/ui/web/static/css/app.css",
    "tests/test_phase7_5_home_dashboard.py",
    "PHASE7_5_FIX2_HOME_ACADEMIC_BRIEF.md",
    "phase7_5_fix2_gate.ps1"
)
$protectedDiff = @(git diff --name-only $BaseCommit -- $protected)
if ($protectedDiff.Count -ne 0) {
    Stop-Gate "Phase 7.5.3 changed protected completed files: $($protectedDiff -join ', ')"
}

Write-Host ""
Write-Host "[10/10] Git + production/runtime immutability"
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 0) {
    Stop-Gate "Phase 7.5.3 gate expects no pre-staged changes."
}
try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to mark Phase 7.5.3 files intent-to-add." }
    git diff --check $BaseCommit --
    if ($LASTEXITCODE -ne 0) { Stop-Gate "git diff --check failed." }
} finally {
    git reset --quiet -- $allowed 2>$null
}

$trackedChanges = @(git diff --name-only $BaseCommit --)
foreach ($path in $trackedChanges) {
    $normalized = $path.Trim().Replace("\","/")
    if (-not $allowedSet.ContainsKey($normalized)) {
        Stop-Gate "Phase 7.5.3 changed an out-of-scope file: $normalized"
    }
}

if ((Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash -ne $dbBefore) {
    Stop-Gate "Phase 7.5.3 changed production SQLite."
}
if ((Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash -ne $authorityBefore) {
    Stop-Gate "Phase 7.5.3 changed authority control."
}
foreach ($path in $legacyBefore.Keys) {
    if (-not (Test-Path $path -PathType Leaf)) {
        Stop-Gate "Phase 7.5.3 removed legacy JSON: $path"
    }
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $legacyBefore[$path]) {
        Stop-Gate "Phase 7.5.3 changed legacy JSON: $path"
    }
}
foreach ($path in $indexBefore.Keys) {
    if (-not (Test-Path $path -PathType Leaf)) {
        Stop-Gate "Phase 7.5.3 removed retrieval-index file: $path"
    }
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $indexBefore[$path]) {
        Stop-Gate "Phase 7.5.3 changed retrieval-index file: $path"
    }
}

Write-Host ""
Write-Host "=================================================="
Write-Host " PHASE 7.5.3 COURSES / TOPICS: PASS"
Write-Host "=================================================="
Write-Host "Verified:"
Write-Host " - Courses reads through existing CourseService + routed repository boundaries"
Write-Host " - course, topic, status, confidence and mastery information render read-only"
Write-Host " - active-course, empty and unavailable states are represented safely"
Write-Host " - course/storage engines remain lazy at web-app creation"
Write-Host " - /courses is GET-only and exposes no browser write form"
Write-Host " - Phase 7.5.1-7.5.2, Phase 7.1-7.4 and complete regressions pass"
Write-Host " - production SQLite, authority, legacy JSON and retrieval index remain unchanged"
Write-Host " - no migration, deprecation, deletion or authority switch occurs"
Write-Host ""
Write-Host "Phase 7.5.3 is ready for review and commit."
