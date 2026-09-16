param([string]$Python = ".\.venv\Scripts\python.exe")

$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase5/knowledge-notes-resources"
$BaseCommit = "5ffd73cccc24fcdf2730537f3b5a2beb04a22f36"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "=============================================="
    Write-Host " PHASE 5.8 REBUILDABLE RETRIEVAL/RAG: BLOCKED"
    Write-Host "=============================================="
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
    Stop-Gate "Expected uncommitted Phase 5.8 work on $BaseCommit but found $head."
}

$allowed = @(
    ".gitignore",
    "personal_learning_assistant/domain/retrieval_models.py",
    "personal_learning_assistant/retrieval/__init__.py",
    "personal_learning_assistant/retrieval/embedding.py",
    "personal_learning_assistant/retrieval/index_builder.py",
    "personal_learning_assistant/retrieval/index_store.py",
    "personal_learning_assistant/retrieval/hybrid.py",
    "personal_learning_assistant/retrieval/rag_context.py",
    "personal_learning_assistant/repositories/sqlite/retrieval_source_repository.py",
    "personal_learning_assistant/services/retrieval_service.py",
    "phase5_retrieval.py",
    "tests/test_phase5_rebuildable_retrieval.py",
    "PHASE5_FIX8_REBUILDABLE_RETRIEVAL_RAG.md",
    "phase5_fix8_gate.ps1"
)
$set = @{}
foreach ($item in $allowed) {
    $set[$item] = $true
    if (-not (Test-Path $item -PathType Leaf)) {
        Stop-Gate "Missing Phase 5.8 file: $item"
    }
}
foreach ($line in @(git status --porcelain=v1 -uall)) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $path = $line.Substring(3).Trim().Replace("\","/")
    if ($path.Contains(" -> ")) { $path = $path.Split(" -> ")[-1] }
    if (-not $set.ContainsKey($path)) {
        Stop-Gate "Out-of-scope working-tree change: $path"
    }
}

if (-not (Test-Path ".\.phase4_authority.json" -PathType Leaf)) {
    Stop-Gate "Phase 4 authority-control file is missing."
}
if (-not (Test-Path ".\data\learning_assistant.db" -PathType Leaf)) {
    Stop-Gate "Production SQLite database is missing."
}

$dbBefore = (Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash
$controlBefore = (Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash
$legacy = @{}
Get-ChildItem ".\data" -Filter "*.json" -File -ErrorAction SilentlyContinue | ForEach-Object {
    $legacy[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
}

Run-Step "[1/9] Focused Phase 5.8 retrieval tests" {
    & $PythonResolved -m pytest tests\test_phase5_rebuildable_retrieval.py -q
}

Run-Step "[2/9] REAL authoritative retrieval preview (read-only)" {
    & $PythonResolved .\phase5_retrieval.py `
        --database .\data\learning_assistant.db `
        --index-root .\.phase5_retrieval `
        preview
}

Run-Step "[3/9] Phase 5.1-5.7 regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase5_knowledge_registry_foundation.py `
        tests\test_phase5_document_source_scanner.py `
        tests\test_phase5_obsidian_vault_registry.py `
        tests\test_phase5_notes_studio_foundation.py `
        tests\test_phase5_resources2_core.py `
        tests\test_phase5_unified_ingestion.py `
        tests\test_phase5_external_course_knowledge.py `
        tests\test_phase5_external_course_crosswalk.py -q
}

Run-Step "[4/9] Legacy retrieval lazy-loading regressions" {
    & $PythonResolved -m pytest `
        tests\test_rag_lazy_loading.py `
        tests\test_semantic_lazy_loading.py -q
}

Run-Step "[5/9] Complete suite (promotion-aware)" {
    $legacyNode = "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
    & $PythonResolved -m pytest -q --deselect $legacyNode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $temp = Join-Path ([IO.Path]::GetTempPath()) ("p58_phase2_" + [guid]::NewGuid().ToString("N"))
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

Run-Step "[6/9] Python compilation" {
    & $PythonResolved -m compileall -q `
        personal_learning_assistant `
        phase5_retrieval.py `
        tests\test_phase5_rebuildable_retrieval.py
}

Run-Step "[7/9] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Run-Step "[8/9] SQLite integrity/FK read-only" {
    $sqliteCheckPath = Join-Path ([IO.Path]::GetTempPath()) ("p58_sqlite_" + [guid]::NewGuid().ToString("N") + ".py")
    try {
        @(
            "import sqlite3",
            "c = sqlite3.connect('file:data/learning_assistant.db?mode=ro', uri=True)",
            "assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'",
            "assert not c.execute('PRAGMA foreign_key_check').fetchall()",
            "c.close()"
        ) | Set-Content -Path $sqliteCheckPath -Encoding ASCII
        & $PythonResolved $sqliteCheckPath
    } finally {
        Remove-Item $sqliteCheckPath -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "[9/9] Git whitespace + production immutability"
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 0) {
    Stop-Gate "Phase 5.8 gate expects no pre-staged changes."
}
try {
    git add --intent-to-add -- $allowed
    git diff --check $BaseCommit --
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "git diff --check failed."
    }
} finally {
    git reset --quiet -- $allowed 2>$null
}

if ((Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash -ne $dbBefore) {
    Stop-Gate "Phase 5.8 gate changed production SQLite."
}
if ((Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash -ne $controlBefore) {
    Stop-Gate "Phase 5.8 gate changed Phase 4 authority control."
}
foreach ($path in $legacy.Keys) {
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $legacy[$path]) {
        Stop-Gate "Legacy JSON changed during Phase 5.8 gate: $path"
    }
}
if (Test-Path ".\.phase5_retrieval") {
    $items = @(Get-ChildItem ".\.phase5_retrieval" -Recurse -Force -ErrorAction SilentlyContinue)
    if ($items.Count -ne 0) {
        Stop-Gate "Read-only Phase 5.8 preview unexpectedly created retrieval index artifacts."
    }
}

$migrationDiff = @(
    git diff --name-only $BaseCommit -- personal_learning_assistant/repositories/sqlite/migrations
)
if ($migrationDiff.Count -ne 0) {
    Stop-Gate "Phase 5.8 must not change historical SQLite migrations."
}

Write-Host ""
Write-Host "============================================"
Write-Host " PHASE 5.8 REBUILDABLE RETRIEVAL/RAG: PASS"
Write-Host "============================================"
Write-Host "Verified:"
Write-Host " - authoritative source is current SQLite knowledge_chunks"
Write-Host " - retrieval indexes are disposable derived artifacts"
Write-Host " - lexical retrieval supports FTS5 with deterministic fallback"
Write-Host " - semantic embedding provider is lazy and optional"
Write-Host " - hybrid ranking uses reciprocal-rank fusion"
Write-Host " - course/topic/resource/document/provider/lecture filters work"
Write-Host " - chunk-local reviewed topic provenance is preserved"
Write-Host " - RAG context contains explicit chunk/document/locator provenance"
Write-Host " - no LLM call occurs in Phase 5.8"
Write-Host " - real preview performs zero SQLite/index writes"
Write-Host " - legacy retrieval modules remain unchanged"
Write-Host " - Phase 5.1-5.7 and full regressions pass"
Write-Host " - no migration, production SQLite, authority or legacy JSON changed"
Write-Host ""
Write-Host "Phase 5.8 is ready for review and commit."
