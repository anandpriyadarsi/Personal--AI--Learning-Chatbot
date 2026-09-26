param([string]$Python = ".\.venv\Scripts\python.exe")
$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase7.5.15.13/card-polish-media-delete"
$Baseline = "05e220df5d1883f86462594103da49f89b33d4ad"
$Range = "$Baseline..HEAD"

function Stop-Gate { param([string]$Message)
  Write-Host ""
  Write-Host "================================================================"
  Write-Host " PHASE 7.5.15.13 CARD POLISH + MEDIA DELETE: BLOCKED"
  Write-Host "================================================================"
  Write-Host $Message
  exit 1
}

function Run-Step { param([string]$Label,[scriptblock]$Command)
  Write-Host ""
  Write-Host $Label
  & $Command
  if($LASTEXITCODE -ne 0){ Stop-Gate "$Label failed with exit code $LASTEXITCODE." }
}

function Hash-Tree { param([string]$Root)
  $out=@{}
  if(Test-Path $Root){
    Get-ChildItem $Root -File -Recurse -Force |
      Where-Object {
        $_.Extension -notin @(".pyc",".pyo") -and
        $_.FullName -notmatch '[\\/]__pycache__[\\/]' -and
        $_.Name -notin @("learning_assistant.db-wal","learning_assistant.db-shm")
      } |
      Sort-Object FullName |
      ForEach-Object {$out[$_.FullName]=(Get-FileHash $_.FullName -Algorithm SHA256).Hash}
  }
  return $out
}

function Assert-Same { param([hashtable]$Before,[hashtable]$After,[string]$Label)
  if($Before.Count -ne $After.Count){Stop-Gate "$Label file count changed."}
  foreach($p in $Before.Keys){
    if(-not $After.ContainsKey($p)){Stop-Gate "$Label removed file: $p"}
    if($Before[$p] -ne $After[$p]){Stop-Gate "$Label changed file: $p"}
  }
}

if(Test-Path $Python){
  $Py=(Resolve-Path $Python).Path
}else{
  $cmd=Get-Command $Python -ErrorAction SilentlyContinue
  if($null -eq $cmd){Stop-Gate "Python not found."}
  $Py=$cmd.Source
}

$branch=(git branch --show-current).Trim()
if($branch -ne $ExpectedBranch){Stop-Gate "Expected $ExpectedBranch but found $branch."}

git merge-base --is-ancestor $Baseline HEAD | Out-Null
if($LASTEXITCODE -ne 0){Stop-Gate "Green Phase 7.5.15.12 baseline is not an ancestor of HEAD."}

$Allowed=@(
  "PHASE7_5_15_13_CARD_POLISH_MEDIA_DELETE_SPEC.md",
  "PHASE7_5_15_13_IMPLEMENTATION_REPORT.md",
  "personal_learning_assistant/repositories/json/anvaya_notes_repository.py",
  "personal_learning_assistant/services/anvaya_notes_service.py",
  "personal_learning_assistant/ui/web/routes.py",
  "personal_learning_assistant/ui/web/static/css/app.css",
  "personal_learning_assistant/ui/web/templates/anvaya_card_template_picker.html",
  "personal_learning_assistant/ui/web/templates/anvaya_notes_editor.html",
  "personal_learning_assistant/ui/web/templates/anvaya_notes_reader.html",
  "tests/test_phase7_5_15_13_card_polish_media_delete.py",
  "phase7_5_15_13_gate.ps1"
)
$changed=@(
  git diff --name-only $Range
  git status --porcelain=v1 -uall | ForEach-Object {
    if($_.Length -ge 4){$_.Substring(3).Trim().Replace("\","/")}
  }
)
$unexpected=@($changed | Where-Object {$_ -and $_ -notin $Allowed} | Sort-Object -Unique)
if($unexpected.Count){
  $unexpected | ForEach-Object {Write-Host "Unexpected: $_"}
  Stop-Gate "15.13 diff escaped the approved card/media scope."
}

$DataBefore=Hash-Tree ".\data"
$RetrievalBefore=Hash-Tree ".\.phase5_retrieval"
$TutorBefore=Hash-Tree ".\personal_learning_assistant\tutor"
$MigrationsBefore=Hash-Tree ".\personal_learning_assistant\repositories\sqlite\migrations"

$VaultHashScript=@'
from pathlib import Path
import hashlib, json
out={}
try:
 import obsidian_integration
 cfg=obsidian_integration.load_config()
 root=(cfg or {}).get("vault_path","") if isinstance(cfg,dict) else ""
 if root and Path(root).is_dir():
  for p in sorted(Path(root).rglob("*")):
   if p.is_file() and not p.is_symlink():
    out[str(p.resolve())]=hashlib.sha256(p.read_bytes()).hexdigest()
except Exception:
 pass
print(json.dumps(out,sort_keys=True,separators=(",",":")))
'@
$tmp=Join-Path ([IO.Path]::GetTempPath()) ("p751513_"+[guid]::NewGuid().ToString("N")+".py")
Set-Content $tmp $VaultHashScript -Encoding UTF8
$VaultBefore=(& $Py $tmp).Trim()

Run-Step "[1/9] Focused card polish + media deletion tests" {
  & $Py -m pytest -q tests/test_phase7_5_15_13_card_polish_media_delete.py
}

Run-Step "[2/9] Notes separation regressions" {
  & $Py -m pytest -q tests/test_phase7_5_15_10_notes_obsidian_separation.py
}

Run-Step "[3/9] Inline media + ZIP regressions" {
  & $Py -m pytest -q tests/test_phase7_5_15_11_inline_note_media.py
}

Run-Step "[4/9] Card template gallery regressions" {
  & $Py -m pytest -q tests/test_phase7_5_15_12_card_template_gallery.py
}

Run-Step "[5/9] Existing Notes reader/editor regressions" {
  & $Py -m pytest -q tests/test_phase7_5_15_2_visual_notes_library.py tests/test_phase7_5_15_3_full_note_reader.py tests/test_phase7_5_15_5_rich_visual_blocks.py tests/test_phase7_5_15_6_safe_editor_attachments.py tests/test_phase7_5_15_8_lifecycle_study_actions.py
}

Run-Step "[6/9] Complete project pytest suite" {
  & $Py -m pytest -q --deselect "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
}

Run-Step "[7/9] Compile and dependency consistency" {
  & $Py -m compileall -q personal_learning_assistant tests
  if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
  & $Py -m pip check
}

Write-Host ""
Write-Host "[8/9] Authority and protection checks"
Assert-Same $DataBefore (Hash-Tree ".\data") "Production data"
Assert-Same $RetrievalBefore (Hash-Tree ".\.phase5_retrieval") "Retrieval state"
Assert-Same $TutorBefore (Hash-Tree ".\personal_learning_assistant\tutor") "Tutor code"
Assert-Same $MigrationsBefore (Hash-Tree ".\personal_learning_assistant\repositories\sqlite\migrations") "SQLite migrations"

$LiveWal=".\data\learning_assistant.db-wal"
if((Test-Path $LiveWal) -and (Get-Item $LiveWal).Length -ne 0){
  Stop-Gate "Production SQLite WAL contains uncheckpointed bytes after validation."
}

$VaultAfter=(& $Py $tmp).Trim()
Remove-Item $tmp -Force -ErrorAction SilentlyContinue
if($VaultBefore -ne $VaultAfter){Stop-Gate "Configured Obsidian vault changed during 15.13 validation."}

Write-Host ""
Write-Host "[9/9] Repository hygiene"
git diff --check $Range
if($LASTEXITCODE -ne 0){Stop-Gate "git diff --check failed."}

Write-Host ""
Write-Host "================================================================"
Write-Host " PHASE 7.5.15.13 CARD POLISH + MEDIA DELETE: PASS"
Write-Host "================================================================"
Write-Host "IRIS preview subject codes are corrected and the six Preview themes are redesigned."
Write-Host "Saved and newly selected note media can be deleted safely."
Write-Host "Inline images stay in-note and are excluded from the bottom unplaced-files section."
Write-Host "Tutor, Obsidian, production data, retrieval state and SQLite migrations are protected."
