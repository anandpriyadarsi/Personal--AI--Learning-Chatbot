param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "========================================="
Write-Host " PHASE 1 FINAL GATE VERIFICATION"
Write-Host "========================================="

if (-not (Test-Path $Python)) {
    throw "Python venv not found at $Python"
}

Write-Host ""
Write-Host "[1/6] Dependency integrity"
& $Python -m pip check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "[2/6] Full regression + read-only fixture suite"
& $Python -m pytest -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "[3/6] Python compile check"
& $Python -m compileall -q .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "[4/6] V13 startup smoke test"
"40" | & $Python main.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "[5/6] Git whitespace/error check"
git diff --check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "[6/6] Git working tree"
$status = git status --short
if ($status) {
    Write-Host $status
    Write-Host ""
    Write-Host "Gate checks passed, but Git is not clean."
    Write-Host "Review/commit intended gate files and rerun."
    exit 2
}

Write-Host ""
Write-Host "========================================="
Write-Host " PHASE 1 GATE: PASS"
Write-Host "========================================="
