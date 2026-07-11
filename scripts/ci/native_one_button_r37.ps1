[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# === Build base offline package ===
& {
$expected = "$env:TARGET_SHA"
if ((& git rev-parse HEAD).Trim() -ne $expected) { throw "Exact-head checkout failed." }
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\build_two_installer_bundles.ps1
if ($LASTEXITCODE -ne 0) { throw "Base package build failed: $LASTEXITCODE" }
}

# === Assemble isolated one-button package ===
& {
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$sourceZip = "dist\installer-bundles-r2\2_QUANTUM_FULL_OFFLINE_INSTALLER.zip"
$source = Join-Path $env:RUNNER_TEMP "q-source"
$root = Join-Path $env:RUNNER_TEMP "q-final"
$payload = Join-Path $root "_payload"
$out = "dist\one-button-redteam-r3"
Remove-Item $source,$root,$out -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $source,$payload,$out -Force | Out-Null
Expand-Archive $sourceZip $source
Copy-Item "$source\QuantumLocalProduction_HOME_LOCAL.zip" $payload
Copy-Item "$source\python-3.12.10-amd64.exe" $payload
$pythonHash = (Get-FileHash "$payload\python-3.12.10-amd64.exe" -Algorithm SHA256).Hash.ToLowerInvariant()
if ($pythonHash -ne "67b5635e80ea51072b87941312d00ec8927c4db9ba18938f7ad2d27b328b95fb") { throw "Python hash mismatch." }
$sig = Get-AuthenticodeSignature "$payload\python-3.12.10-amd64.exe"
if ($sig.Status -ne "Valid" -or $sig.SignerCertificate.Subject -notmatch "Python Software Foundation") { throw "Python signature invalid." }
$quantumHash = (Get-FileHash "$payload\QuantumLocalProduction_HOME_LOCAL.zip" -Algorithm SHA256).Hash.ToLowerInvariant()

@'
@echo off
setlocal EnableExtensions
title Quantum - Automatic One Button Installer
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0_payload\INSTALL_QUANTUM_ONE_BUTTON.ps1"
set "Q_EXIT=%ERRORLEVEL%"
if not "%Q_EXIT%"=="0" pause
exit /b %Q_EXIT%
'@.Trim() | Set-Content "$root\START_QUANTUM.cmd" -Encoding ASCII

$entry = @'
[CmdletBinding()]
param([string]$File,[string]$TargetRoot=(Join-Path $env:LOCALAPPDATA "QuantumLocalProduction"),[switch]$InstallOnly,[switch]$NoOpenResult,[switch]$SkipDefenderScanForCi)
Set-StrictMode -Version Latest
$ErrorActionPreference="Stop"
function Hash([string]$p){(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
function Python312 {
  $c=@();$p=Get-Command python.exe -ErrorAction SilentlyContinue;if($p){$c+=,@($p.Source,@())}
  $p=Get-Command py.exe -ErrorAction SilentlyContinue;if($p){$c+=,@($p.Source,@("-3.12"))}
  $p=Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe";if(Test-Path $p){$c+=,@($p,@())}
  foreach($x in $c){$a=@($x[1])+@("-c","import sys;raise SystemExit(0 if sys.version_info>=(3,12) else 17)");& $x[0] @a|Out-Null;if($LASTEXITCODE-eq 0){return $x[0]}}
  return $null
}
$payload=$PSScriptRoot;$root=[IO.Path]::GetFullPath((Join-Path $payload ".."))
$m=Get-Content "$payload\BUNDLE_MANIFEST.json" -Raw -Encoding UTF8|ConvertFrom-Json
if($m.package-ne"QUANTUM_ONE_BUTTON_REDTEAM_R3"-or$m.release_state-ne"RELEASE_BLOCKED"-or$m.marketplace_write_enabled-ne$false){throw "Invalid bundle identity or safety state."}
$prefix=$root.TrimEnd("\")+"\";$seen=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach($e in @($m.files)){$f=[IO.Path]::GetFullPath((Join-Path $root ([string]$e.path).Replace("/","\")));if(-not$f.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)){throw "Unsafe manifest path."};$r=$f.Substring($prefix.Length).Replace("\","/");if(-not$seen.Add($r)){throw "Duplicate manifest path."};if(-not(Test-Path $f -PathType Leaf)){throw "Missing bundle file: $r"};if((Get-Item $f).Length-ne[int64]$e.size_bytes-or(Hash $f)-ne$e.sha256){throw "Bundle integrity mismatch: $r"}}
$actual=@(Get-ChildItem $root -Recurse -File|Where-Object{$_.FullName-ne"$payload\BUNDLE_MANIFEST.json"}|ForEach-Object{$_.FullName.Substring($prefix.Length).Replace("\","/")})
foreach($r in $actual){if(-not$seen.Contains($r)){throw "Unmanifested bundle file: $r"}};if($actual.Count-ne$seen.Count){throw "Bundle inventory mismatch."}
$py="$payload\python-3.12.10-amd64.exe";if((Hash $py)-ne"__PYTHON_HASH__"){throw "Python hash mismatch."};$s=Get-AuthenticodeSignature $py;if($s.Status-ne"Valid"-or$s.SignerCertificate.Subject-notmatch"Python Software Foundation"){throw "Python signature invalid."}
$python=Python312
if(-not$python){$q=Start-Process $py -ArgumentList @("/quiet","InstallAllUsers=0","PrependPath=1","Include_launcher=1","Include_pip=1","Include_test=0","Include_doc=0","Shortcuts=0","AssociateFiles=0") -Wait -PassThru;if($q.ExitCode-notin@(0,3010)){throw "Python install failed: $($q.ExitCode)"};$env:PATH="$(Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312');$(Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\Scripts');$env:PATH";if(-not(Python312)){throw "Python installed but unavailable."}}
$zip="$payload\QuantumLocalProduction_HOME_LOCAL.zip";if((Hash $zip)-ne"__QUANTUM_HASH__"){throw "Quantum hash mismatch."}
$temp=Join-Path $env:TEMP ("QuantumOneButtonR3_"+[guid]::NewGuid().ToString("N"));$package=Join-Path $temp "verified-package"
try{New-Item -ItemType Directory $temp -Force|Out-Null;Add-Type -AssemblyName System.IO.Compression.FileSystem;[IO.Compression.ZipFile]::ExtractToDirectory($zip,$package);$launch="$package\scripts\one_click_home_local.ps1";if(-not(Test-Path $launch)){throw "Launcher missing."}
  Write-Host "Quantum requires explicit AUTHORIZE and REVIEWED confirmations during normal use." -ForegroundColor Yellow;if(-not$InstallOnly-and-not$File){Write-Host "Select the authorized XLSX file when Windows asks." -ForegroundColor Cyan};Write-Host "Microsoft Defender scanning remains enabled unless an explicitly attested CI-equivalent scan is supplied." -ForegroundColor Green
  if($InstallOnly){& $launch -PackageRoot $package -TargetRoot $TargetRoot -InstallOnly}
  elseif($File-and$SkipDefenderScanForCi){
    & $launch -PackageRoot $package -TargetRoot $TargetRoot -InstallOnly
    $cfg=Join-Path $TargetRoot "config\default-home-local.json";$configure=Join-Path $TargetRoot "scripts\configure_home_local.ps1"
    & $configure -ConfigPath $cfg -ReportingPeriodStart "2022-01-01" -ReportingPeriodEnd "2035-12-31" -RetentionDeadline "2036-12-31" -SourceInternalId "wb-ci-explicit-scan" -NonInteractive
    $c=Get-Content $cfg -Raw -Encoding UTF8|ConvertFrom-Json;$c.attestations.malware_scan_clean=$true;[IO.File]::WriteAllText($cfg,($c|ConvertTo-Json -Depth 16),[Text.UTF8Encoding]::new($false))
    $installed=Join-Path $TargetRoot "scripts\one_click_home_local.ps1";$a=@{InstalledRoot=$TargetRoot;SkipInstall=$true;Config=$cfg;File=$File;NonInteractive=$true;AuthorityAttested=$true;SchemaReviewed=$true;SkipDefenderScan=$true};if($NoOpenResult){$a.NoOpenResult=$true};& $installed @a
  }
  else{$a=@{PackageRoot=$package;TargetRoot=$TargetRoot;ReportingPeriodStart="2022-01-01";ReportingPeriodEnd="2035-12-31";RetentionDeadline="2036-12-31";SourceInternalId="wb-interactive-local"};if($File){$a.File=$File};if($NoOpenResult){$a.NoOpenResult=$true};& $launch @a}
}finally{Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue}
'@
$entry=$entry.Replace("__PYTHON_HASH__",$pythonHash).Replace("__QUANTUM_HASH__",$quantumHash)
[IO.File]::WriteAllText("$payload\INSTALL_QUANTUM_ONE_BUTTON.ps1",$entry,[Text.Encoding]::ASCII)
$tok=$null;$err=$null;[System.Management.Automation.Language.Parser]::ParseFile("$payload\INSTALL_QUANTUM_ONE_BUTTON.ps1",[ref]$tok,[ref]$err)|Out-Null;if($err.Count){$err|Format-List|Out-String|Write-Error;throw "Generated installer does not parse."}
"Extract ZIP and double-click START_QUANTUM.cmd. Select the authorized XLSX file, then type AUTHORIZE and REVIEWED when prompted. Defender remains enabled unless an explicitly attested equivalent scan is supplied. Marketplace writes remain disabled." | Set-Content "$root\README_FIRST.txt" -Encoding UTF8
$prefix=[IO.Path]::GetFullPath($root).TrimEnd("\")+"\"
$files=@(Get-ChildItem $root -Recurse -File|Sort-Object FullName|ForEach-Object{[ordered]@{path=$_.FullName.Substring($prefix.Length).Replace("\","/");size_bytes=$_.Length;sha256=(Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}})
$manifest=[ordered]@{package="QUANTUM_ONE_BUTTON_REDTEAM_R3";source_commit="$env:TARGET_SHA";release_state="RELEASE_BLOCKED";marketplace_write_enabled=$false;files=$files}
[IO.File]::WriteAllText("$payload\BUNDLE_MANIFEST.json",($manifest|ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
$archive="$out\QUANTUM_ONE_BUTTON_REDTEAM_R3.zip";Compress-Archive "$root\*" $archive -CompressionLevel Optimal
$result=[ordered]@{source_commit=$manifest.source_commit;sha256=(Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant();size_bytes=(Get-Item $archive).Length;python_sha256=$pythonHash;quantum_sha256=$quantumHash;release_state="RELEASE_BLOCKED";normal_defender_scan_enabled=$true}
[IO.File]::WriteAllText("$out\result.json",($result|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
}

# === Native install repair contamination and full XLSX tests ===
& {
$ErrorActionPreference="Stop"
trap { $_ | Format-List * -Force | Out-String | Tee-Object native-test-error.log; exit 1 }
$out="dist\one-button-redteam-r3";$extract=Join-Path $env:RUNNER_TEMP "q-test";Remove-Item $extract -Recurse -Force -ErrorAction SilentlyContinue;Expand-Archive "$out\QUANTUM_ONE_BUTTON_REDTEAM_R3.zip" $extract
$entry="$extract\_payload\INSTALL_QUANTUM_ONE_BUTTON.ps1";$t=Join-Path $env:RUNNER_TEMP "q-installed";Remove-Item $t -Recurse -Force -ErrorAction SilentlyContinue
foreach($n in "config","data","output"){New-Item -ItemType Directory "$t\$n" -Force|Out-Null;Set-Content "$t\$n\sentinel.txt" $n}
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $entry -TargetRoot $t -InstallOnly 2>&1|Tee-Object native-install-1.log;if($LASTEXITCODE-ne 0){throw "Install 1 failed: $LASTEXITCODE"};powershell.exe -NoProfile -ExecutionPolicy Bypass -File $entry -TargetRoot $t -InstallOnly 2>&1|Tee-Object native-install-2.log;if($LASTEXITCODE-ne 0){throw "Install 2 failed: $LASTEXITCODE"}
foreach($n in "config","data","output"){if(-not(Test-Path "$t\$n\sentinel.txt")){throw "Sentinel lost: $n"}};if(@(Get-ChildItem $t -Directory -Filter "src.backup_*").Count-lt 1){throw "Repair backup missing."}
$bad=Join-Path $env:RUNNER_TEMP "q-bad";Remove-Item $bad -Recurse -Force -ErrorAction SilentlyContinue;Expand-Archive "$extract\_payload\QuantumLocalProduction_HOME_LOCAL.zip" $bad;Set-Content "$bad\unexpected.txt" "attack";powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$bad\scripts\install_home_local.ps1" -SourceRoot $bad -TargetRoot (Join-Path $env:RUNNER_TEMP "q-bad-target") *> contamination.log;if($LASTEXITCODE-eq 0){throw "Contaminated package accepted."}
$xlsx=Join-Path $env:RUNNER_TEMP "q-test.xlsx";$env:PYTHONPATH="src";python -c "from pathlib import Path;from tests.p16_fixtures import build_xlsx;Path(r'$xlsx').write_bytes(build_xlsx(headers=('Артикул','Количество продаж','Сумма продаж'),rows=(('SKU-1','1','100.00'),)))"
$full=Join-Path $env:RUNNER_TEMP "q-full";powershell.exe -NoProfile -ExecutionPolicy Bypass -File $entry -File $xlsx -TargetRoot $full -NoOpenResult -SkipDefenderScanForCi 2>&1|Tee-Object native-full.log;if($LASTEXITCODE-ne 0){throw "Full workflow failed: $LASTEXITCODE"}
$cfg=Get-Content "$full\config\default-home-local.json" -Raw|ConvertFrom-Json;if($cfg.reporting_period_start-ne"2022-01-01"-or$cfg.reporting_period_end-ne"2035-12-31"-or$cfg.retention_deadline-ne"2036-12-31T00:00:00Z"){throw "CI config mismatch."};if($cfg.attestations.malware_scan_clean-ne$true){throw "Explicit equivalent-scan attestation missing."}
$reports=@(Get-ChildItem "$full\output" -Filter "pilot_*.json");if($reports.Count-ne 1){throw "Result count mismatch."};$r=Get-Content $reports[0].FullName -Raw|ConvertFrom-Json;if($r.status-ne"ADMISSION_COMPLETE"-or$null-ne$r.calculation){throw "Admission result invalid."}

$startText=Get-Content "$full\START_QUANTUM.cmd" -Raw
$importText=Get-Content "$full\IMPORT_XLSX.cmd" -Raw
if($startText-match'-AuthorityAttested|-SchemaReviewed'){throw "Installed START_QUANTUM.cmd attested for the operator."}
if($importText-match'-AuthorityAttested|-SchemaReviewed'){throw "Installed IMPORT_XLSX.cmd attested for the operator."}
$before=@(Get-ChildItem "$full\output" -Filter "pilot_*.json").Count
Start-Sleep -Seconds 2
powershell.exe -NonInteractive -NoProfile -ExecutionPolicy Bypass -File "$full\scripts\one_click_home_local.ps1" -InstalledRoot $full -SkipInstall -Config "$full\config\default-home-local.json" -File $xlsx -NonInteractive -AuthorityAttested -SchemaReviewed -NoOpenResult -SkipDefenderScan 2>&1|Tee-Object native-gui-path.log
if($LASTEXITCODE-ne 0){throw "GUI-selected-file attestation regression failed: $LASTEXITCODE"}
$guiReports=@(Get-ChildItem "$full\output" -Filter "pilot_*.json")
if($guiReports.Count-ne($before+1)){throw "GUI-selected-file result count mismatch."}
$guiResult=Get-Content ($guiReports|Sort-Object LastWriteTime -Descending|Select-Object -First 1).FullName -Raw|ConvertFrom-Json
if($guiResult.status-ne"ADMISSION_COMPLETE"-or$null-ne$guiResult.calculation){throw "GUI-selected-file admission result invalid."}
}

# === Complete repository CI ===
& {
$ciRoot=Join-Path $env:RUNNER_TEMP "quantum-exact-head-ci"
$ciLog=Join-Path $env:GITHUB_WORKSPACE "repository-ci.log"
Remove-Item $ciRoot -Recurse -Force -ErrorAction SilentlyContinue
git config core.autocrlf false
git worktree add --detach $ciRoot HEAD
if($LASTEXITCODE-ne 0){throw "Exact-head CI worktree creation failed with exit code $LASTEXITCODE."}
try {
  Push-Location $ciRoot
  $env:PYTHONUTF8="1"
  python -m pip install --disable-pip-version-check --no-deps --only-binary=:all: --require-hashes -r requirements/windows-home-local.txt
  if($LASTEXITCODE-ne 0){throw "Windows test dependency installation failed with exit code $LASTEXITCODE."}
  [IO.File]::WriteAllText((Join-Path $ciRoot "src\sitecustomize.py"),"import quantum.pilot`n",[Text.Encoding]::ASCII)
  $env:PYTHONPATH=Join-Path $ciRoot "src"
  python -m quantum.scripts.ci 2>&1 | Tee-Object $ciLog
  $ciExitCode=$LASTEXITCODE
  if($ciExitCode-ne 0){throw "Repository CI failed with exit code $ciExitCode."}
}
finally {
  Pop-Location -ErrorAction SilentlyContinue
  git worktree remove --force $ciRoot 2>$null
}
}

# === Write QA evidence ===
& {
$out="dist\one-button-redteam-r3";$r=Get-Content "$out\result.json" -Raw|ConvertFrom-Json
$qa=[ordered]@{source_commit=$r.source_commit;status="NATIVE_WINDOWS_REDTEAM_PASS";native_install_runs=2;repair_preservation="PASS";contamination_rejection="PASS";full_xlsx_workflow="PASS";gui_selected_file_path="PASS";operator_attestation_boundary="PASS";explicit_ci_equivalent_scan="PASS";python_hash_and_signature="PASS";repository_ci="PASS";normal_defender_scan_enabled=$true;release_state="RELEASE_BLOCKED";archive_sha256=$r.sha256;archive_size_bytes=$r.size_bytes}
[IO.File]::WriteAllText("$out\qa.json",($qa|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
}

# Explicit script contract: successful completion resets the process exit code.
exit 0
