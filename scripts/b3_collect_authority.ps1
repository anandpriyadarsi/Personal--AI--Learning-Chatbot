# Tools-only collection. The installed application and its data are unchanged.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ToolsRef,
    [string]$Repo = (Get-Location).Path,
    [string]$Output = (Join-Path $env:TEMP ('ANVAYA-B3-authority-' + [guid]::NewGuid().ToString('N') + '.json')),
    [switch]$ClosedNoWriters
)
$ErrorActionPreference = 'Stop'
$toolsDirectory = Join-Path $env:TEMP ('ANVAYA-B3-tools-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $toolsDirectory -ErrorAction Stop | Out-Null
try {
    # Source-only paths: no data, vault, config, .env or authority control.
    $entries = & git -C $Repo ls-tree -r $ToolsRef -- scripts/architecture_local_collector.py personal_learning_assistant
    if ($LASTEXITCODE -ne 0) { throw 'Reviewed tools ref unavailable' }
    if (@($entries | Where-Object { $_ -notmatch '^(100644|100755) blob ' }).Count -ne 0) {
        throw 'Unsafe tools inventory'
    }
    $archive = Join-Path $toolsDirectory 'tools.zip'
    & git -C $Repo archive --format=zip --output=$archive $ToolsRef scripts/architecture_local_collector.py personal_learning_assistant
    if ($LASTEXITCODE -ne 0) { throw 'Tools archive failed' }
    Expand-Archive -LiteralPath $archive -DestinationPath $toolsDirectory -ErrorAction Stop
    $collector = Join-Path $toolsDirectory 'scripts/architecture_local_collector.py'
    $arguments = @($collector, '--repo', $Repo, '--output', $Output)
    if ($ClosedNoWriters) { $arguments += '--closed-no-writers' }
    $previousBytecode = $env:PYTHONDONTWRITEBYTECODE
    try {
        $env:PYTHONDONTWRITEBYTECODE = '1'
        & $Python @arguments
        if ($LASTEXITCODE -ne 0) { throw 'Collector failed; review locally' }
    } finally {
        $env:PYTHONDONTWRITEBYTECODE = $previousBytecode
    }
    Write-Output ('Redacted report: ' + $Output)
} finally {
    # Dispose only this invocation's uniquely created private tools directory.
    Remove-Item -LiteralPath $toolsDirectory -Recurse -Force -ErrorAction Stop
}
