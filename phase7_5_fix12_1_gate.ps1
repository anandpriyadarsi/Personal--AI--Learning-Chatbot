param([string]$Python = "./.venv/Scripts/python.exe")

$ErrorActionPreference = "Stop"
$ExpectedBranch = "main"
$PlanPath = "docs/superpowers/plans/2026-09-19-phase7-5-12-1-obsidian-reader-study-companion.md"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "================================================================"
    Write-Host " PHASE 7.5.12.1 OBSIDIAN READER + STUDY COMPANION: BLOCKED"
    Write-Host "================================================================"
    Write-Host $Message
    exit 1
}

function Run-Step {
    param([string]$Label, [scriptblock]$Command)
    Write-Host ""
    Write-Host $Label
    & $Command
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "$Label failed with exit code $LASTEXITCODE."
    }
}

function Hash-Tree {
    param([string]$Root)
    $result = @{}
    if (Test-Path $Root -PathType Container) {
        Get-ChildItem $Root -File -Recurse -Force |
            Where-Object {
                $_.Extension -notin @(".pyc", ".pyo") -and
                $_.FullName -notmatch '[\\/]__pycache__[\\/]'
            } |
            Sort-Object FullName |
            ForEach-Object {
                $result[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
            }
    }
    return $result
}

function Hash-Tree-Except {
    param([string]$Root, [string[]]$RelativeExcludes)
    $excluded = @{}
    foreach ($item in $RelativeExcludes) {
        $excluded[$item.Replace("\", "/")] = $true
    }
    $result = @{}
    if (Test-Path $Root -PathType Container) {
        $resolvedRoot = (Resolve-Path $Root).Path
        Get-ChildItem $Root -File -Recurse -Force |
            Where-Object {
                $_.Extension -notin @(".pyc", ".pyo") -and
                $_.FullName -notmatch '[\\/]__pycache__[\\/]'
            } |
            Sort-Object FullName |
            ForEach-Object {
                $relative = $_.FullName.Substring($resolvedRoot.Length).TrimStart("\", "/").Replace("\", "/")
                if (-not $excluded.ContainsKey($relative)) {
                    $result[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
                }
            }
    }
    return $result
}

function Assert-Hash-Map-Unchanged {
    param([hashtable]$Before, [hashtable]$After, [string]$Label)
    if ($After.Count -ne $Before.Count) {
        Stop-Gate "$Label file count changed."
    }
    foreach ($path in $Before.Keys) {
        if (-not $After.ContainsKey($path)) {
            Stop-Gate "$Label removed file: $path"
        }
        if ($After[$path] -ne $Before[$path]) {
            Stop-Gate "$Label changed file: $path"
        }
    }
}

function Hash-RequiredFile {
    param([string]$Path, [string]$Label)
    if (-not (Test-Path $Path -PathType Leaf)) {
        Stop-Gate "$Label is missing: $Path"
    }
    return (Get-FileHash $Path -Algorithm SHA256).Hash
}

$planBaseRaw = git log -1 --format=%H -- $PlanPath
if ([string]::IsNullOrWhiteSpace($planBaseRaw)) {
    Stop-Gate "The Phase 7.5.12.1 plan must be committed separately before this gate runs."
}
$BaseCommit = $planBaseRaw.Trim()

if (Test-Path $Python -PathType Leaf) {
    $PythonResolved = (Resolve-Path $Python).Path
} else {
    $pythonCommand = Get-Command $Python -ErrorAction SilentlyContinue
    if ($null -eq $pythonCommand) {
        Stop-Gate "Python interpreter not found: $Python"
    }
    $PythonResolved = $pythonCommand.Source
}

$branch = (git branch --show-current).Trim()
if ($branch -ne $ExpectedBranch) {
    Stop-Gate "Expected branch $ExpectedBranch but found $branch."
}
$head = (git rev-parse HEAD).Trim()
if ($head -ne $BaseCommit) {
    Stop-Gate "Expected uncommitted implementation on plan commit $BaseCommit but found $head."
}

$allowed = @(
    "requirements.txt",
    "personal_learning_assistant/repositories/sqlite/migrations/0005_obsidian_study_companion.sql",
    "personal_learning_assistant/repositories/sqlite/obsidian_study_repository.py",
    "personal_learning_assistant/services/obsidian_markdown_renderer.py",
    "personal_learning_assistant/services/obsidian_study_companion_service.py",
    "personal_learning_assistant/services/obsidian_workspace_service.py",
    "personal_learning_assistant/ui/web/routes.py",
    "personal_learning_assistant/ui/web/templates/base.html",
    "personal_learning_assistant/ui/web/templates/obsidian_note.html",
    "personal_learning_assistant/ui/web/static/css/app.css",
    "personal_learning_assistant/ui/web/static/js/obsidian_reader.js",
    "tests/test_phase6_active_recall_quiz.py",
    "tests/test_phase7_5_obsidian_workspace.py",
    "tests/test_phase7_5_obsidian_markdown_renderer.py",
    "tests/test_phase7_5_obsidian_study_repository.py",
    "tests/test_phase7_5_obsidian_study_companion.py",
    "tests/test_phase7_5_obsidian_reader_routes.py",
    "phase7_5_fix12_1_gate.ps1"
)
$allowedSet = @{}
foreach ($item in $allowed) {
    $allowedSet[$item] = $true
}

$workingChanges = @(git status --porcelain=v1 -uall)
if ($workingChanges.Count -eq 0) {
    Stop-Gate "The Phase 7.5.12.1 implementation must remain uncommitted while the gate runs."
}
foreach ($line in $workingChanges) {
    if ([string]::IsNullOrWhiteSpace($line)) {
        continue
    }
    $path = $line.Substring(3).Trim().Replace("\", "/")
    if ($path.Contains(" -> ")) {
        $path = $path.Split(" -> ")[-1]
    }
    if (-not $allowedSet.ContainsKey($path)) {
        Stop-Gate "Out-of-scope working-tree change: $path"
    }
}
foreach ($item in $allowed) {
    if (-not (Test-Path $item -PathType Leaf)) {
        Stop-Gate "Required Phase 7.5.12.1 file is missing: $item"
    }
}

$stagedBefore = @(git diff --cached --name-only)
if ($stagedBefore.Count -ne 0) {
    Stop-Gate "The implementation gate requires every implementation file to remain unstaged."
}
if (-not (Test-Path "./data/learning_assistant.db" -PathType Leaf)) {
    Stop-Gate "Production SQLite database is missing."
}
if (-not (Test-Path "./.phase5_retrieval/current.json" -PathType Leaf)) {
    Stop-Gate "Current Phase 5 retrieval generation is missing."
}

$dbBefore = (Get-FileHash "./data/learning_assistant.db" -Algorithm SHA256).Hash
$authorityExistedBefore = Test-Path "./.phase4_authority.json" -PathType Leaf
$authorityBefore = $null
if ($authorityExistedBefore) {
    $authorityBefore = (Get-FileHash "./.phase4_authority.json" -Algorithm SHA256).Hash
}
$jsonBefore = @{}
Get-ChildItem "./data" -Filter "*.json" -File -ErrorAction SilentlyContinue |
    Sort-Object FullName |
    ForEach-Object {
        $jsonBefore[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
    }
$indexBefore = Hash-Tree "./.phase5_retrieval"

$vaultHashScript = @'
import hashlib
import os
from pathlib import Path
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
$vaultBefore = (& $PythonResolved -c $vaultHashScript).Trim()
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Could not capture the configured-vault Markdown manifest."
}

$protectedObsidianIntegration = Hash-RequiredFile "./obsidian_integration.py" "Legacy Obsidian integration"
$protectedVaultScanner = Hash-RequiredFile "./personal_learning_assistant/repositories/filesystem/obsidian_vault_scanner.py" "Phase 5.3 scanner"
$protectedVaultReader = Hash-RequiredFile "./personal_learning_assistant/repositories/filesystem/obsidian_workspace_reader.py" "Phase 7.5.12 Reader"
$protectedVaultRegistryService = Hash-RequiredFile "./personal_learning_assistant/services/obsidian_vault_registry_service.py" "Phase 5.3 registry service"
$protectedVaultRepository = Hash-RequiredFile "./personal_learning_assistant/repositories/sqlite/obsidian_vault_repository.py" "Phase 5.3 registry repository"
$protectedNotesStudioService = Hash-RequiredFile "./personal_learning_assistant/services/notes_studio_service.py" "Phase 5.4 Notes Studio service"
$protectedMarkdownStore = Hash-RequiredFile "./personal_learning_assistant/repositories/filesystem/markdown_note_store.py" "Phase 5.4 Markdown store"
$protectedNotesStudioRepository = Hash-RequiredFile "./personal_learning_assistant/repositories/sqlite/notes_studio_repository.py" "Phase 5.4 Notes Studio repository"
$protectedPriorMigrations = Hash-Tree-Except "./personal_learning_assistant/repositories/sqlite/migrations" @("0005_obsidian_study_companion.sql")
$protectedSqlite = Hash-Tree-Except "./personal_learning_assistant/repositories/sqlite" @("obsidian_study_repository.py", "migrations/0005_obsidian_study_companion.sql")
$protectedRetrieval = Hash-Tree "./personal_learning_assistant/retrieval"
$protectedTutor = Hash-Tree "./personal_learning_assistant/tutor"
$protectedServices = Hash-Tree-Except "./personal_learning_assistant/services" @("obsidian_markdown_renderer.py", "obsidian_study_companion_service.py", "obsidian_workspace_service.py")
$protectedFilesystemRepositories = Hash-Tree "./personal_learning_assistant/repositories/filesystem"
$protectedTemplates = Hash-Tree-Except "./personal_learning_assistant/ui/web/templates" @("base.html", "obsidian_note.html")
$protectedStatic = Hash-Tree-Except "./personal_learning_assistant/ui/web/static" @("css/app.css", "js/obsidian_reader.js")

Run-Step "[1/18] Markdown renderer + raw-HTML/XSS safety" {
    & $PythonResolved -m pytest -q tests/test_phase7_5_obsidian_markdown_renderer.py
}

Run-Step "[2/18] SQLite migration, schema, integrity, and read-only history" {
    & $PythonResolved -m pytest -q tests/test_phase7_5_obsidian_study_repository.py -k "0005 or history or unmigrated or schema_validation or pragma"
}

Run-Step "[3/18] Reading sessions, heartbeat bounds, aggregation, and replay" {
    & $PythonResolved -m pytest -q `
        tests/test_phase7_5_obsidian_study_repository.py `
        tests/test_phase7_5_obsidian_study_companion.py `
        -k "session or heartbeat or tracking or start_reading or end_reading or replay"
}

Run-Step "[4/18] Companion persistence, isolation, text bounds, and archive" {
    & $PythonResolved -m pytest -q `
        tests/test_phase7_5_obsidian_study_repository.py `
        tests/test_phase7_5_obsidian_study_companion.py `
        -k "companion or archive or isolation or overlong"
}

Run-Step "[5/18] Reader routes, templates, CSS, JavaScript, POST, and PRG" {
    & $PythonResolved -m pytest -q tests/test_phase7_5_obsidian_reader_routes.py
}

Run-Step "[6/18] Reader GET purity and failure-safety matrix" {
    & $PythonResolved -m pytest -q `
        tests/test_phase7_5_obsidian_reader_routes.py `
        tests/test_phase7_5_obsidian_study_companion.py `
        tests/test_phase7_5_obsidian_workspace.py `
        -k "pure or traversal or absolute or symlink or non_utf8 or changed or missing or unavailable or xss or escapes or failure"
}

Run-Step "[7/18] Phase 7.5.12 Obsidian workspace regressions" {
    & $PythonResolved -m pytest -q tests/test_phase7_5_obsidian_workspace.py
}

Run-Step "[8/18] Phase 5.3 scanner/registry + Phase 5.4 Notes Studio regressions" {
    & $PythonResolved -m pytest -q `
        tests/test_phase5_obsidian_vault_registry.py `
        tests/test_phase5_notes_studio_foundation.py
}

Run-Step "[9/18] Complete Phase 7.5 web regressions" {
    $phase75Tests = @(
        Get-ChildItem "./tests" -Filter "test_phase7_5_*.py" -File |
            Sort-Object Name |
            ForEach-Object { $_.FullName }
    )
    & $PythonResolved -m pytest -q @phase75Tests
}

Run-Step "[10/18] Phase 7.1-7.4 runtime/recovery regressions" {
    & $PythonResolved -m pytest -q `
        tests/test_phase7_runtime_inventory.py `
        tests/test_phase7_recovery_bundle.py `
        tests/test_phase7_restore_rehearsal.py `
        tests/test_phase7_consumer_watch.py
}

Run-Step "[11/18] Complete pytest suite" {
    $legacyNode = "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
    & $PythonResolved -m pytest -q --deselect $legacyNode
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Complete pytest suite failed."
    }
    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("p75121_phase2_" + [guid]::NewGuid().ToString("N"))
    try {
        New-Item -ItemType Directory -Path (Join-Path $tempRoot "tests") -Force | Out-Null
        Copy-Item "./tests/test_phase2_closure_architecture.py" (Join-Path $tempRoot "tests/test_phase2_closure_architecture.py")
        $tempNode = (Join-Path $tempRoot "tests/test_phase2_closure_architecture.py") + "::test_phase2_root_has_no_production_learning_assistant_database"
        & $PythonResolved -m pytest $tempNode -q
        if ($LASTEXITCODE -ne 0) {
            Stop-Gate "Isolated Phase 2 root-layout assertion failed."
        }
    } finally {
        Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Run-Step "[12/18] Python compile, exact dependency pin, and pip check" {
    & $PythonResolved -m compileall -q `
        personal_learning_assistant/repositories/sqlite/obsidian_study_repository.py `
        personal_learning_assistant/services/obsidian_markdown_renderer.py `
        personal_learning_assistant/services/obsidian_study_companion_service.py `
        personal_learning_assistant/services/obsidian_workspace_service.py `
        personal_learning_assistant/ui/web/routes.py `
        tests/test_phase7_5_obsidian_markdown_renderer.py `
        tests/test_phase7_5_obsidian_study_repository.py `
        tests/test_phase7_5_obsidian_study_companion.py `
        tests/test_phase7_5_obsidian_reader_routes.py
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Python compile failed."
    }
    & $PythonResolved -c "import mistune; assert mistune.__version__ == '3.3.4', mistune.__version__"
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Installed Mistune version does not match the approved pin."
    }
    & $PythonResolved -m pip check
}

Run-Step "[13/18] Fresh + production SQLite integrity and foreign-key checks" {
    $tempDb = Join-Path ([IO.Path]::GetTempPath()) ("p75121_" + [guid]::NewGuid().ToString("N") + ".db")
    $sqliteCheck = @'
import sqlite3
import sys
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations

path = sys.argv[1]
assert apply_migrations(path) == (1, 2, 3, 4, 5)
connection = sqlite3.connect(path)
versions = tuple(row[0] for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version"))
assert versions == (1, 2, 3, 4, 5)
tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
assert {"obsidian_reading_sessions", "obsidian_companion_entries"} <= tables
assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
connection.close()
'@
    try {
        & $PythonResolved -c $sqliteCheck $tempDb
        if ($LASTEXITCODE -ne 0) {
            Stop-Gate "Fresh SQLite migration/integrity check failed."
        }
    } finally {
        Remove-Item $tempDb -Force -ErrorAction SilentlyContinue
    }
    & $PythonResolved -c "import sqlite3; c=sqlite3.connect('file:data/learning_assistant.db?mode=ro',uri=True); assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; assert c.execute('PRAGMA foreign_key_check').fetchall()==[]; c.close()"
}

Write-Host ""
Write-Host "[14/18] Protected code hashes + forbidden dependency/write scans"
if ((Hash-RequiredFile "./obsidian_integration.py" "Legacy Obsidian integration") -ne $protectedObsidianIntegration) { Stop-Gate "obsidian_integration.py changed during the gate." }
if ((Hash-RequiredFile "./personal_learning_assistant/repositories/filesystem/obsidian_vault_scanner.py" "Phase 5.3 scanner") -ne $protectedVaultScanner) { Stop-Gate "Phase 5.3 scanner changed during the gate." }
if ((Hash-RequiredFile "./personal_learning_assistant/repositories/filesystem/obsidian_workspace_reader.py" "Phase 7.5.12 Reader") -ne $protectedVaultReader) { Stop-Gate "Phase 7.5.12 Reader changed during the gate." }
if ((Hash-RequiredFile "./personal_learning_assistant/services/obsidian_vault_registry_service.py" "Phase 5.3 registry service") -ne $protectedVaultRegistryService) { Stop-Gate "Phase 5.3 registry service changed during the gate." }
if ((Hash-RequiredFile "./personal_learning_assistant/repositories/sqlite/obsidian_vault_repository.py" "Phase 5.3 registry repository") -ne $protectedVaultRepository) { Stop-Gate "Phase 5.3 registry repository changed during the gate." }
if ((Hash-RequiredFile "./personal_learning_assistant/services/notes_studio_service.py" "Phase 5.4 Notes Studio service") -ne $protectedNotesStudioService) { Stop-Gate "Phase 5.4 Notes Studio service changed during the gate." }
if ((Hash-RequiredFile "./personal_learning_assistant/repositories/filesystem/markdown_note_store.py" "Phase 5.4 Markdown store") -ne $protectedMarkdownStore) { Stop-Gate "Phase 5.4 Markdown store changed during the gate." }
if ((Hash-RequiredFile "./personal_learning_assistant/repositories/sqlite/notes_studio_repository.py" "Phase 5.4 Notes Studio repository") -ne $protectedNotesStudioRepository) { Stop-Gate "Phase 5.4 Notes Studio repository changed during the gate." }
Assert-Hash-Map-Unchanged $protectedPriorMigrations (Hash-Tree-Except "./personal_learning_assistant/repositories/sqlite/migrations" @("0005_obsidian_study_companion.sql")) "Prior SQLite migrations"
Assert-Hash-Map-Unchanged $protectedSqlite (Hash-Tree-Except "./personal_learning_assistant/repositories/sqlite" @("obsidian_study_repository.py", "migrations/0005_obsidian_study_companion.sql")) "Other SQLite repositories"
Assert-Hash-Map-Unchanged $protectedRetrieval (Hash-Tree "./personal_learning_assistant/retrieval") "Retrieval code"
Assert-Hash-Map-Unchanged $protectedTutor (Hash-Tree "./personal_learning_assistant/tutor") "Tutor code"
Assert-Hash-Map-Unchanged $protectedServices (Hash-Tree-Except "./personal_learning_assistant/services" @("obsidian_markdown_renderer.py", "obsidian_study_companion_service.py", "obsidian_workspace_service.py")) "Other services"
Assert-Hash-Map-Unchanged $protectedFilesystemRepositories (Hash-Tree "./personal_learning_assistant/repositories/filesystem") "Filesystem repositories"
Assert-Hash-Map-Unchanged $protectedTemplates (Hash-Tree-Except "./personal_learning_assistant/ui/web/templates" @("base.html", "obsidian_note.html")) "Other web templates"
Assert-Hash-Map-Unchanged $protectedStatic (Hash-Tree-Except "./personal_learning_assistant/ui/web/static" @("css/app.css", "js/obsidian_reader.js")) "Other web static assets"

$routeSource = Get-Content "./personal_learning_assistant/ui/web/routes.py" -Raw
foreach ($token in @("import sqlite3", "sqlite3.", ".execute(", ".read_bytes(", ".read_text(", "ObsidianVaultRegistryService.apply", "NotesStudioService")) {
    if ($routeSource.Contains($token)) {
        Stop-Gate "Forbidden route dependency or direct I/O primitive found: $token"
    }
}
$studySource = Get-Content "./personal_learning_assistant/services/obsidian_study_companion_service.py" -Raw
foreach ($token in @("import sqlite3", ".execute(", ".read_bytes(", ".read_text(", ".write_text(", ".write_bytes(", "ObsidianVaultRegistryService.apply", "NotesStudioService", "learning_memory", "IndexBuilder")) {
    if ($studySource.Contains($token)) {
        Stop-Gate "Forbidden study-service dependency or I/O primitive found: $token"
    }
}

Write-Host ""
Write-Host "[15/18] Configured-vault Markdown hashes unchanged"
$vaultAfter = (& $PythonResolved -c $vaultHashScript).Trim()
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Could not recapture the configured-vault Markdown manifest."
}
if ($vaultAfter -ne $vaultBefore) {
    Stop-Gate "Configured Obsidian vault Markdown changed during the gate."
}
Write-Host "Vault Markdown manifest: $vaultAfter"

Write-Host ""
Write-Host "[16/18] Production SQLite, authority, and JSON/config hashes unchanged"
if ((Get-FileHash "./data/learning_assistant.db" -Algorithm SHA256).Hash -ne $dbBefore) {
    Stop-Gate "Tests changed production SQLite."
}
$authorityExistsAfter = Test-Path "./.phase4_authority.json" -PathType Leaf
if ($authorityExistsAfter -ne $authorityExistedBefore) {
    Stop-Gate "Tests changed authority-control file existence."
}
if ($authorityExistedBefore -and (Get-FileHash "./.phase4_authority.json" -Algorithm SHA256).Hash -ne $authorityBefore) {
    Stop-Gate "Tests changed authority control."
}
$jsonAfter = @{}
Get-ChildItem "./data" -Filter "*.json" -File -ErrorAction SilentlyContinue |
    Sort-Object FullName |
    ForEach-Object {
        $jsonAfter[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
    }
Assert-Hash-Map-Unchanged $jsonBefore $jsonAfter "Production JSON configuration"
Write-Host "Production SQLite SHA256: $dbBefore"

Write-Host ""
Write-Host "[17/18] Retrieval-index path set and hashes unchanged"
$indexAfter = Hash-Tree "./.phase5_retrieval"
Assert-Hash-Map-Unchanged $indexBefore $indexAfter "Retrieval index"
Write-Host "Retrieval index files verified: $($indexBefore.Count)"

Write-Host ""
Write-Host "[18/18] Scoped unstaged git diff, required files, and runtime-artifact exclusion"
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 0) {
    Stop-Gate "The gate expects no pre-staged implementation changes."
}
try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Unable to mark untracked implementation files intent-to-add for scope validation."
    }
    git diff --check $BaseCommit --
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "git diff --check failed."
    }
    $allChanges = @(git diff --name-only $BaseCommit --)
    foreach ($path in $allChanges) {
        $normalized = $path.Trim().Replace("\", "/")
        if ($normalized -match '(^|/)__pycache__(/|$)' -or $normalized -match '\.(pyc|pyo)$') {
            continue
        }
        if (-not $allowedSet.ContainsKey($normalized)) {
            Stop-Gate "Phase 7.5.12.1 changed an out-of-scope file: $normalized"
        }
    }
    foreach ($item in $allowed) {
        if (-not ($allChanges -contains $item)) {
            Stop-Gate "Required implementation file is absent from the scoped diff: $item"
        }
    }
} finally {
    git reset --quiet -- $allowed 2>$null
}

Write-Host ""
Write-Host "================================================================"
Write-Host " PHASE 7.5.12.1 OBSIDIAN READER + STUDY COMPANION: PASS"
Write-Host "================================================================"
Write-Host "Rendered Markdown remained escaped and server-rendered; raw source remained optional and read-only."
Write-Host "Reading history counted only bounded client activity deltas owned and aggregated by SQLite."
Write-Host "Companion key points and doubts persisted without changing Markdown, config, or retrieval indexes."
Write-Host "Production SQLite, configured-vault Markdown, JSON configuration, and protected code remained unchanged."
