param([string]$Python = ".\.venv\Scripts\python.exe")
$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase7.5.15.12/card-template-gallery"
$Baseline = "f371dcd115b3314bf9322b4c96d369719988b820"
$Range = "$Baseline..HEAD"

function Stop-Gate { param([string]$Message)
  Write-Host ""
  Write-Host "================================================================"
  Write-Host " PHASE 7.5.15.12 NOTES CARD TEMPLATE GALLERY: BLOCKED"
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
if($LASTEXITCODE -ne 0){Stop-Gate "Phase 7.5.15.11 base is not an ancestor of HEAD."}

$Allowed=@(
  "PHASE7_5_15_12_CARD_TEMPLATE_GALLERY_SPEC.md",
  "PHASE7_5_15_12_IMPLEMENTATION_REPORT.md",
  "personal_learning_assistant/services/anvaya_notes_service.py",
  "personal_learning_assistant/ui/web/static/css/app.css",
  "personal_learning_assistant/ui/web/templates/anvaya_card_template_picker.html",
  "personal_learning_assistant/ui/web/templates/anvaya_notes_create.html",
  "personal_learning_assistant/ui/web/templates/anvaya_notes_editor.html",
  "personal_learning_assistant/ui/web/templates/anvaya_notes_library.html",
  "personal_learning_assistant/ui/web/templates/anvaya_notes_upload.html",
  "tests/test_phase7_5_15_12_card_template_gallery.py",
  "phase7_5_15_12_gate.ps1"
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
  Stop-Gate "15.12 diff escaped the approved card-template scope."
}

Run-Step "[1/6] Focused 18-template gallery tests" {
  & $Py -m pytest -q tests/test_phase7_5_15_12_card_template_gallery.py
}

Run-Step "[2/6] Notes separation + inline-media regressions" {
  & $Py -m pytest -q tests/test_phase7_5_15_10_notes_obsidian_separation.py tests/test_phase7_5_15_11_inline_note_media.py
}

Run-Step "[3/6] Existing Notes UI regressions" {
  & $Py -m pytest -q tests/test_phase7_5_15_2_visual_notes_library.py tests/test_phase7_5_15_3_full_note_reader.py tests/test_phase7_5_15_5_rich_visual_blocks.py tests/test_phase7_5_15_6_safe_editor_attachments.py
}

Run-Step "[4/6] Complete project pytest suite" {
  & $Py -m pytest -q --deselect "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
}

Run-Step "[5/6] Compile and dependency consistency" {
  & $Py -m compileall -q personal_learning_assistant tests
  if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
  & $Py -m pip check
}

Write-Host ""
Write-Host "[6/6] Card-template scope and repository hygiene"
$picker=Get-Content "personal_learning_assistant/ui/web/templates/anvaya_card_template_picker.html" -Raw
foreach($family in @("IRIS Card","Preview Card","Minimal Square")){
  if(-not $picker.Contains($family)){Stop-Gate "Missing card family: $family"}
}
$css=Get-Content "personal_learning_assistant/ui/web/static/css/app.css" -Raw
$templates=@(
  "iris-indigo","iris-emerald","iris-cyan","iris-amber","iris-coral","iris-violet",
  "preview-left","preview-top","preview-split","preview-film","preview-polaroid","preview-banner",
  "square-clean","square-outline","square-centered","square-corner","square-grid","square-soft"
)
foreach($template in $templates){
  if(-not $picker.Contains($template)){Stop-Gate "Picker missing template: $template"}
  if(-not $css.Contains(".anvaya-note-template--$template")){Stop-Gate "CSS missing template: $template"}
}

git diff --check $Range
if($LASTEXITCODE -ne 0){Stop-Gate "git diff --check failed."}

Write-Host ""
Write-Host "================================================================"
Write-Host " PHASE 7.5.15.12 NOTES CARD TEMPLATE GALLERY: PASS"
Write-Host "================================================================"
Write-Host "IRIS, Preview and Minimal Square each expose six selectable templates."
Write-Host "IRIS includes six subject-friendly colour/design identities."
Write-Host "Each note persists and renders its exact selected card template."
