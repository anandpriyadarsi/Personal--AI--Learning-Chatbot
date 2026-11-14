# Explicit Windows fallback. No install, provider call, CI dispatch, or personal migration.
[CmdletBinding()]
param(
    [string]$Python = '',
    [string]$OutputDirectory = '',
    [int]$SuiteTimeout = 600
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $Root 'verification/phase15-windows' }
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$Report = Join-Path $OutputDirectory 'report.json'
$ExitCode = 1
$Reason = ''
# A failed interpreter startup must never reuse a previous successful report
# or screenshots. These names are owned solely by this validator invocation.
if (Test-Path -LiteralPath $Report) { Remove-Item -LiteralPath $Report -Force }
$PriorArtifacts = Join-Path $OutputDirectory 'report-artifacts'
if (Test-Path -LiteralPath $PriorArtifacts) { Remove-Item -LiteralPath $PriorArtifacts -Recurse -Force }
if (-not $Python) {
    foreach ($Candidate in @((Join-Path $Root '.venv/Scripts/python.exe'), (Join-Path $Root 'venv/Scripts/python.exe'))) {
        if (Test-Path -LiteralPath $Candidate -PathType Leaf) { $Python = $Candidate; break }
    }
    if (-not $Python) {
        $Command = Get-Command python -ErrorAction SilentlyContinue
        if ($Command) { $Python = $Command.Source }
    }
}
if (-not $Python) { $Reason = 'Python unavailable. Prepare the pinned environment explicitly; no installation was attempted.' }
else {
    Push-Location $Root
    try {
        # The Python validator clears inherited credentials and budgets, enforces
        # subprocess deadlines and denies outbound network while permitting localhost.
        & $Python -m scripts.multimodal_validate --full-offline --output $Report --suite-timeout $SuiteTimeout
        $ExitCode = $LASTEXITCODE
    } catch { $Reason = 'Validator could not execute. Check the explicitly selected Python and installed pinned dependencies.' }
    finally { Pop-Location }
}
if ($Reason -or -not (Test-Path -LiteralPath $Report)) {
    if (-not $Reason) { $Reason = 'Validator exited without a report. No gate has been verified.' }
    $Gates = @{}
    foreach ($Name in @('unit','browser','restore','integrity','windows_runtime')) {
        $Gates[$Name] = @{ requested = $true; executed = $false; status = 'BLOCKED_ENVIRONMENT'; reason = $Reason }
    }
    $Gates['live_model'] = @{ requested = $false; executed = $false; status = 'NOT_AUTHORIZED' }
    $Fallback = @{
        report_version = 2; platform = [Environment]::OSVersion.Platform.ToString();
        passed = $false; offline_passed = $false; windows_runtime_verified = $false;
        release_readiness = 'not_ready'; live_model_quality = 'unverified';
        source_sha = $null; working_tree_dirty = $null; suites = @(); gates = $Gates;
        personal_activation = $false; live_calls = $false
    }
    $Fallback | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Report -Encoding UTF8
    $ExitCode = 1
}
# Package only synthetic report, JUnit/logs and screenshots. Never include owner DBs,
# environment variables, caches, originals, credentials, or personal configuration.
$BundleRoot = Join-Path $OutputDirectory 'redacted-bundle'
if (Test-Path -LiteralPath $BundleRoot) { Remove-Item -LiteralPath $BundleRoot -Recurse -Force }
New-Item -ItemType Directory -Path $BundleRoot | Out-Null
Copy-Item -LiteralPath $Report -Destination (Join-Path $BundleRoot 'report.json')
$Artifacts = Join-Path $OutputDirectory 'report-artifacts'
if (Test-Path -LiteralPath $Artifacts) {
    foreach ($File in (Get-ChildItem -LiteralPath $Artifacts -File -Recurse)) {
        if ($File.Extension -notin @('.json','.xml','.log','.png') -or $File.Name.EndsWith('.raw.log')) { continue }
        $Relative = $File.FullName.Substring($Artifacts.Length).TrimStart([char[]]'\/')
        $Destination = Join-Path (Join-Path $BundleRoot 'report-artifacts') $Relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
        Copy-Item -LiteralPath $File.FullName -Destination $Destination
    }
}
foreach ($File in (Get-ChildItem -LiteralPath $BundleRoot -File -Recurse)) {
    if ($File.Extension -notin @('.json','.xml','.log')) { continue }
    $Text = [IO.File]::ReadAllText($File.FullName)
    foreach ($PrivatePath in @($env:USERPROFILE, $Root, $OutputDirectory)) {
        if ($PrivatePath) {
            $Text = $Text.Replace($PrivatePath, '<LOCAL_PATH>').Replace($PrivatePath.Replace('\','\\'), '<LOCAL_PATH>')
        }
    }
    [IO.File]::WriteAllText($File.FullName, $Text, (New-Object Text.UTF8Encoding($false)))
}
$Zip = Join-Path $OutputDirectory 'phase15-redacted-evidence.zip'
Compress-Archive -Path (Join-Path $BundleRoot '*') -DestinationPath $Zip -Force
Write-Output "Report: $Report"
Write-Output "Redacted synthetic evidence: $Zip"
exit $ExitCode
