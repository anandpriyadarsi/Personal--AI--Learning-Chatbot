param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

function Stop-Gate {
    param(
        [string]$Message,
        [int]$Code = 1
    )

    Write-Host ""
    Write-Host "========================================="
    Write-Host " FIX 20 CLEAN-CLONE GATE: BLOCKED"
    Write-Host "========================================="
    Write-Host $Message
    exit $Code
}

function Run-Step {
    param(
        [string]$Label,
        [scriptblock]$Command
    )

    Write-Host ""
    Write-Host $Label
    & $Command

    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "$Label failed with exit code $LASTEXITCODE."
    }
}

Write-Host ""
Write-Host "========================================="
Write-Host " FIX 20 - CLEAN-CLONE & REPOSITORY HYGIENE"
Write-Host "========================================="

if (-not (Test-Path $Python)) {
    Stop-Gate "Python virtual environment not found at $Python"
}

$PythonResolved = (Resolve-Path $Python).Path

$required = @(
    ".gitattributes",
    "tests\test_phase1_fixture_integrity.py",
    "tests\fixtures\phase1\README.md",
    "tests\fixtures\phase1\notes.json",
    "tests\fixtures\phase1\resources.json",
    "tests\fixtures\phase1\courses.json",
    "tests\fixtures\phase1\learning_memory.json",
    "tests\fixtures\phase1\course_progress_history.json",
    "tests\fixtures\phase1\weekly_study_plans.json",
    "tests\fixtures\phase1\multi_course_weekly_plans.json",
    "tests\fixtures\phase1\assessments.json",
    "tests\fixtures\phase1\assessment_workspace.json",
    "tests\fixtures\phase1\obsidian_config.json"
)

foreach ($path in $required) {
    if (-not (Test-Path $path)) {
        Stop-Gate "Required Fix 20 file is missing: $path"
    }
}

$resourcesSize = (
    Get-Item "tests\fixtures\phase1\resources.json"
).Length

if ($resourcesSize -ne 0) {
    Stop-Gate (
        "tests\fixtures\phase1\resources.json must remain exactly zero bytes."
    )
}

Run-Step "[1/7] Local sanitized fixture test" {
    & $PythonResolved -m pytest `
        tests\test_phase1_fixture_integrity.py `
        -q
}

Run-Step "[2/7] Full local regression suite" {
    & $PythonResolved -m pytest -q
}

Run-Step "[3/7] Git whitespace/error check" {
    git diff --check
}

# No secret/runtime/private authority should be tracked.
$forbiddenTracked = @()

$trackedEnv = git ls-files -- ".env"
if ($trackedEnv) {
    $forbiddenTracked += ".env"
}

$trackedDb = git ls-files -- "data/learning_assistant.db"
if ($trackedDb) {
    $forbiddenTracked += "data/learning_assistant.db"
}

$trackedPickles = git ls-files -- "*.pkl" "*.pickle"
foreach ($item in $trackedPickles) {
    if ($item) {
        $forbiddenTracked += $item
    }
}

$trackedPrivateJson = git ls-files -- "data/*.json" "data/**/*.json"
foreach ($item in $trackedPrivateJson) {
    if ($item) {
        $forbiddenTracked += $item
    }
}

if ($forbiddenTracked.Count -gt 0) {
    Write-Host ""
    Write-Host "Forbidden/private runtime files are tracked:"
    $forbiddenTracked |
        Sort-Object -Unique |
        ForEach-Object {
            Write-Host "  - $_"
        }

    Stop-Gate (
        "Clean-clone policy failed. Keep private/runtime authority out of Git."
    )
}

Write-Host ""
Write-Host "Tracked-private/runtime file check: PASS"

# The clean-export proof must use committed content, so require a clean tree.
$workingTree = git status --short

if ($workingTree) {
    Write-Host ""
    Write-Host "Current working tree:"
    Write-Host $workingTree
    Write-Host ""

    Stop-Gate (
        "Local tests passed, but clean-export verification requires a clean " +
        "committed tree. Review/commit the intended Fix 20 files, then rerun."
    ) 2
}

# Required fixtures must be committed, not merely present locally.
foreach ($path in $required) {
    git ls-files --error-unmatch -- $path *> $null

    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Required Fix 20 file is not tracked by Git: $path"
    }
}

Write-Host ""
Write-Host "Tracked Fix 20 file check: PASS"

$tempRoot = Join-Path (
    [System.IO.Path]::GetTempPath()
) (
    "personal-ai-fix20-" +
    [guid]::NewGuid().ToString("N")
)

$archive = Join-Path $tempRoot "source.zip"
$export = Join-Path $tempRoot "export"

New-Item `
    -ItemType Directory `
    -Path $tempRoot `
    -Force | Out-Null

try {
    Write-Host ""
    Write-Host "[4/7] Build clean Git export"
    git archive `
        --format=zip `
        --output="$archive" `
        HEAD

    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "git archive HEAD failed."
    }

    Expand-Archive `
        -Path $archive `
        -DestinationPath $export `
        -Force

    $forbiddenExportPaths = @(
        ".env",
        ".venv",
        ".git",
        "data\learning_assistant.db",
        "semantic_index.pkl"
    )

    foreach ($relative in $forbiddenExportPaths) {
        if (Test-Path (Join-Path $export $relative)) {
            Stop-Gate "Forbidden runtime/private path appeared in clean export: $relative"
        }
    }

    if (Test-Path (Join-Path $export "data")) {
        $exportDataFiles = @(
            Get-ChildItem `
                (Join-Path $export "data") `
                -Recurse `
                -File `
                -ErrorAction SilentlyContinue
        )

        if ($exportDataFiles.Count -gt 0) {
            Write-Host ""
            Write-Host "Files unexpectedly present under exported data/:"
            $exportDataFiles | ForEach-Object {
                Write-Host "  - $($_.FullName)"
            }

            Stop-Gate (
                "Clean export contains data/ files. " +
                "Private legacy authority must not be required by source tests."
            )
        }
    }

    Push-Location $export

    try {
        Run-Step "[5/7] Clean-export full regression suite" {
            & $PythonResolved -m pytest -q
        }

        Run-Step "[6/7] Clean-export compile check" {
            & $PythonResolved -m compileall -q .
        }

        Run-Step "[7/7] Clean-export V13 startup smoke test" {
            "40" | & $PythonResolved main.py
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    if (Test-Path $tempRoot) {
        Remove-Item `
            $tempRoot `
            -Recurse `
            -Force `
            -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "========================================="
Write-Host " FIX 20 CLEAN-CLONE GATE: PASS"
Write-Host "========================================="
Write-Host ""
Write-Host "Verified:"
Write-Host "  - deterministic .gitattributes policy exists"
Write-Host "  - ten sanitized legacy fixture stores are tracked"
Write-Host "  - zero-byte resources edge case is preserved"
Write-Host "  - local full suite passes"
Write-Host "  - git archive contains no private data/.env/.venv/.git"
Write-Host "  - clean export passes the full suite"
Write-Host "  - clean export compiles"
Write-Host "  - clean export starts/exits V13 successfully"
Write-Host ""

$upstream = $null
try {
    $upstream = (
        git rev-parse `
            --abbrev-ref `
            --symbolic-full-name `
            "@{u}" 2>$null
    )
}
catch {
    $upstream = $null
}

if (-not $upstream) {
    Write-Host "========================================="
    Write-Host " REMOTE RECOVERABILITY: PENDING"
    Write-Host "========================================="
    Write-Host (
        "The local clean-clone gate passed, but the current branch has no " +
        "verified upstream yet. Push the modernization branch before Phase 3."
    )
    exit 2
}

Run-Step "Remote divergence check" {
    git rev-list --left-right --count "HEAD...$upstream"
}

$counts = (
    git rev-list `
        --left-right `
        --count `
        "HEAD...$upstream"
).Trim() -split "\s+"

if (
    ($counts.Count -ne 2) -or
    ($counts[0] -ne "0") -or
    ($counts[1] -ne "0")
) {
    Write-Host ""
    Write-Host "HEAD/upstream divergence: $($counts -join ' ')"
    Write-Host "Expected: 0 0"
    Write-Host ""
    Write-Host "========================================="
    Write-Host " REMOTE RECOVERABILITY: PENDING"
    Write-Host "========================================="
    Write-Host "Push/pull/reconcile the branch before Phase 3."
    exit 2
}

Write-Host ""
Write-Host "========================================="
Write-Host " PRE-PHASE 3 REPOSITORY READINESS: PASS"
Write-Host "========================================="
Write-Host "Local clean export and remote upstream are both verified."
exit 0
