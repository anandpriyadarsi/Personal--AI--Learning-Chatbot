param(
    [string]$Python = 'python',
    [string]$Output = (Join-Path ([IO.Path]::GetTempPath()) ('anvaya-validation-' + [guid]::NewGuid().ToString('N')))
)
$ErrorActionPreference = 'Stop'
& $Python (Join-Path $PSScriptRoot 'architecture_validation.py') --output $Output
exit $LASTEXITCODE
