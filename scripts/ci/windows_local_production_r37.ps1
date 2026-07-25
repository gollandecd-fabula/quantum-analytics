[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# === Assert exact head ===
& {
$expected = "$env:TARGET_SHA"
$actual = (& git rev-parse HEAD).Trim()
if ($actual -ne $expected) {
  throw "Exact-head checkout failed. Expected $expected, got $actual"
}
Write-Host "Validated exact head: $actual"
}

# === Install hash-pinned Windows timezone data ===
& {
python -m pip install `
  --disable-pip-version-check `
  --no-deps `
  --only-binary=:all: `
  --require-hashes `
  -r requirements/windows-home-local.txt
if ($LASTEXITCODE -ne 0) {
  throw "Pinned Windows dependency installation failed with exit code $LASTEXITCODE"
}
python -c "from zoneinfo import ZoneInfo; assert str(ZoneInfo('Europe/Moscow')) == 'Europe/Moscow'"
}

# === Compile repaired runner ===
& {
$env:PYTHONPATH = "src"
python -m py_compile `
  src/quantum/pilot/local_runner.py `
  src/quantum/pilot/windows_runner.py `
  src/quantum/pilot/windows_storage_compat.py
}

# === Run Windows red-team regression suite ===
& {
$env:PYTHONPATH = "src"
python -m unittest `
  tests.test_windows_local_runner `
  tests.test_windows_storage_compat `
  tests.test_windows_redteam_hardening `
  tests.test_windows_reviewed_file_hash `
  tests.test_windows_one_click_installer_r1 `
  -v 2>&1 | Tee-Object -FilePath windows-repair-tests.log
if ($LASTEXITCODE -ne 0) {
  throw "Windows red-team regression suite failed with exit code $LASTEXITCODE"
}
}

# === Re-run existing local pilot tests ===
& {
$env:PYTHONPATH = "src"
python -m unittest tests.test_local_pilot_runner -v 2>&1 |
  Tee-Object -FilePath existing-local-pilot-tests.log
if ($LASTEXITCODE -ne 0) {
  throw "Existing local pilot tests failed with exit code $LASTEXITCODE"
}
}

# === Parse PowerShell scripts ===
& {
$files = @(
  "scripts/windows/import_source.ps1",
  "scripts/windows/install_home_local.ps1",
  "scripts/windows/configure_home_local.ps1",
  "scripts/windows/one_click_home_local.ps1",
  "scripts/windows/build_local_production.ps1"
)
foreach ($file in $files) {
  $tokens = $null
  $errors = $null
  [System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path $file),
    [ref]$tokens,
    [ref]$errors
  ) | Out-Null
  if ($errors.Count -gt 0) {
    $errors | Format-List | Out-String | Write-Error
    throw "PowerShell parse failed: $file"
  }
}
}

# === Build HOME_LOCAL package with Windows PowerShell ===
& {
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\windows\build_local_production.ps1 2>&1 |
  Tee-Object -FilePath package-build.log
$buildExitCode = $LASTEXITCODE
if ($buildExitCode -ne 0) {
  throw "Package build failed with exit code $buildExitCode"
}
}

# === Verify archive, manifest, tamper rejection and user workflow ===
& {
$verificationErrorLog = "windows-verification-error.log"
trap {
  $_ | Format-List * -Force | Out-String | Set-Content -LiteralPath $verificationErrorLog -Encoding UTF8
  exit 1
}
$archive = "dist\QuantumLocalProduction_HOME_LOCAL.zip"
if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) {
  throw "Package archive was not produced."
}
$hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
if ($hash -notmatch "^[0-9A-F]{64}$") {
  throw "Package SHA-256 is invalid."
}
Write-Host "Archive SHA-256: $hash"

$extractRoot = Join-Path $env:RUNNER_TEMP "quantum-package"
$tamperedRoot = Join-Path $env:RUNNER_TEMP "quantum-tampered-package"
$tamperedInstall = Join-Path $env:RUNNER_TEMP "quantum-tampered-install"
$installRoot = Join-Path $env:RUNNER_TEMP "quantum-installed"
$oneClickInstall = Join-Path $env:RUNNER_TEMP "quantum-one-click-installed"
foreach ($path in @($extractRoot, $tamperedRoot, $tamperedInstall, $installRoot, $oneClickInstall)) {
  Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue
}
Expand-Archive -LiteralPath $archive -DestinationPath $extractRoot

$manifestPath = Join-Path $extractRoot "manifest.sha256.json"
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.release_state -ne "RELEASE_BLOCKED") {
  throw "Unexpected package release state."
}
if ($manifest.marketplace_write_enabled -ne $false) {
  throw "Marketplace writes must remain disabled."
}
if ([string]$manifest.package_version -ne "R3_ONE_CLICK") {
  throw "Unexpected package version: $($manifest.package_version)"
}
if ([string]$manifest.tzdata_version -ne "2026.2") {
  throw "Unexpected packaged tzdata version: $($manifest.tzdata_version)"
}
if ([string]$manifest.source_commit -ne "$env:TARGET_SHA") {
  throw "Package source commit does not match exact workflow head: $($manifest.source_commit)"
}
foreach ($entry in $manifest.files) {
  $entryPath = Join-Path $extractRoot ([string]$entry.path).Replace("/", "\")
  if (-not (Test-Path -LiteralPath $entryPath -PathType Leaf)) {
    throw "Manifest file is missing: $($entry.path)"
  }
  $actual = (Get-FileHash -LiteralPath $entryPath -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($actual -ne [string]$entry.sha256) {
    throw "Manifest hash mismatch: $($entry.path)"
  }
}
foreach ($requiredPackageFile in @(
  (Join-Path $extractRoot "START_QUANTUM.cmd"),
  (Join-Path $extractRoot "scripts\one_click_home_local.ps1")
)) {
  if (-not (Test-Path -LiteralPath $requiredPackageFile -PathType Leaf)) {
    throw "One-click package entry is missing: $requiredPackageFile"
  }
}

Copy-Item -LiteralPath $extractRoot -Destination $tamperedRoot -Recurse -Force
Add-Content -LiteralPath (Join-Path $tamperedRoot "scripts\import_source.ps1") -Value "# tampered"
$tamperedInstaller = Join-Path $tamperedRoot "scripts\install_home_local.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File $tamperedInstaller -SourceRoot $tamperedRoot -TargetRoot $tamperedInstall *> tamper-rejection.log
if ($LASTEXITCODE -eq 0) {
  throw "Tampered package was accepted by the installer."
}

foreach ($name in @("config", "data", "output")) {
  New-Item -ItemType Directory -Path (Join-Path $installRoot $name) -Force | Out-Null
  Set-Content -LiteralPath (Join-Path $installRoot "$name\sentinel.txt") -Value $name -Encoding ASCII
}

$installer = Join-Path $extractRoot "scripts\install_home_local.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File $installer -SourceRoot $extractRoot -TargetRoot $installRoot
if ($LASTEXITCODE -ne 0) {
  throw "First installer run failed with exit code $LASTEXITCODE"
}
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File $installer -SourceRoot $extractRoot -TargetRoot $installRoot
if ($LASTEXITCODE -ne 0) {
  throw "Second installer run failed with exit code $LASTEXITCODE"
}

foreach ($name in @("config", "data", "output")) {
  $sentinel = Join-Path $installRoot "$name\sentinel.txt"
  if (-not (Test-Path -LiteralPath $sentinel -PathType Leaf)) {
    throw "Installer removed user data sentinel: $sentinel"
  }
}
$backups = @(Get-ChildItem -LiteralPath $installRoot -Directory -Filter "src.backup_*")
if ($backups.Count -lt 1) {
  throw "Second install did not produce a runtime backup."
}
foreach ($required in @(
  (Join-Path $installRoot "src\quantum\pilot\windows_runner.py"),
  (Join-Path $installRoot "src\tzdata\zoneinfo\Europe\Moscow"),
  (Join-Path $installRoot "scripts\import_source.ps1"),
  (Join-Path $installRoot "scripts\configure_home_local.ps1"),
  (Join-Path $installRoot "scripts\one_click_home_local.ps1"),
  (Join-Path $installRoot "START_QUANTUM.cmd"),
  (Join-Path $installRoot "IMPORT_XLSX.cmd"),
  (Join-Path $installRoot "CONFIGURE_HOME_LOCAL.cmd")
)) {
  if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
    throw "Installed file is missing: $required"
  }
}

$configPath = Join-Path $installRoot "config\default-home-local.json"
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File (Join-Path $installRoot "scripts\configure_home_local.ps1") `
  -ConfigPath $configPath `
  -ReportingPeriodStart "2026-07-01" `
  -ReportingPeriodEnd "2026-07-04" `
  -RetentionDeadline "2030-01-01" `
  -SourceInternalId "ci-home-local" `
  -NonInteractive 2>&1 |
  Tee-Object -FilePath configurator.log
$configuratorExitCode = $LASTEXITCODE
if ($configuratorExitCode -ne 0) {
  throw "HOME_LOCAL configurator failed with exit code $configuratorExitCode"
}
$configured = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$configured.execution_mode -ne "ADMISSION_ONLY") {
  throw "Configurator did not create ADMISSION_ONLY config."
}
$configured.attestations.malware_scan_clean = $true
$configuredJson = $configured | ConvertTo-Json -Depth 16
[IO.File]::WriteAllText(
  $configPath,
  $configuredJson,
  ([Text.UTF8Encoding]::new($false))
)

$syntheticXlsx = Join-Path $env:RUNNER_TEMP "quantum-redteam.xlsx"
$env:PYTHONPATH = "src"
python -c "from pathlib import Path; from tests.p16_fixtures import build_xlsx; Path(r'$syntheticXlsx').write_bytes(build_xlsx(headers=('Артикул','Количество продаж','Сумма продаж'), rows=(('SKU-1','1','100.00'),)))"
if ($LASTEXITCODE -ne 0) {
  throw "Synthetic XLSX creation failed."
}
$importOutput = Join-Path $installRoot "output\redteam-import.json"
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File (Join-Path $installRoot "scripts\import_source.ps1") `
  -File $syntheticXlsx `
  -Config $configPath `
  -StorageRoot (Join-Path $installRoot "data") `
  -Output $importOutput `
  -NonInteractive `
  -AuthorityAttested `
  -SchemaReviewed `
  -SkipDefenderScan `
  -DebugErrors 2>&1 |
  Tee-Object -FilePath installed-import.log
$importExitCode = $LASTEXITCODE
if ($importExitCode -ne 0) {
  throw "Installed HOME_LOCAL import failed with exit code $importExitCode"
}
$importReport = Get-Content -LiteralPath $importOutput -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$importReport.status -ne "ADMISSION_COMPLETE") {
  throw "Unexpected installed import status: $($importReport.status)"
}
if ($null -ne $importReport.calculation) {
  throw "ADMISSION_ONLY unexpectedly produced a calculation."
}

$oneClick = Join-Path $extractRoot "scripts\one_click_home_local.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File $oneClick `
  -PackageRoot $extractRoot `
  -TargetRoot $oneClickInstall `
  -Config $configPath `
  -File $syntheticXlsx `
  -ReportingPeriodStart "2026-07-01" `
  -ReportingPeriodEnd "2026-07-04" `
  -RetentionDeadline "2030-01-01" `
  -SourceInternalId "ci-one-click" `
  -NonInteractive `
  -AuthorityAttested `
  -SchemaReviewed `
  -SkipDefenderScan `
  -NoOpenResult 2>&1 |
  Tee-Object -FilePath one-click-pilot.log
$oneClickExitCode = $LASTEXITCODE
if ($oneClickExitCode -ne 0) {
  throw "One-click HOME_LOCAL pilot failed with exit code $oneClickExitCode"
}
foreach ($requiredOneClick in @(
  (Join-Path $oneClickInstall "START_QUANTUM.cmd"),
  (Join-Path $oneClickInstall "scripts\one_click_home_local.ps1"),
  (Join-Path $oneClickInstall "config\default-home-local.json")
)) {
  if (-not (Test-Path -LiteralPath $requiredOneClick -PathType Leaf)) {
    throw "One-click installed file is missing: $requiredOneClick"
  }
}
$pilotOutputs = @(Get-ChildItem -LiteralPath (Join-Path $oneClickInstall "output") -File -Filter "pilot_*.json")
if ($pilotOutputs.Count -ne 1) {
  throw "One-click run produced an unexpected number of pilot results: $($pilotOutputs.Count)"
}
$pilotReport = Get-Content -LiteralPath $pilotOutputs[0].FullName -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$pilotReport.status -ne "ADMISSION_COMPLETE") {
  throw "Unexpected one-click pilot status: $($pilotReport.status)"
}
if ($null -ne $pilotReport.calculation) {
  throw "One-click ADMISSION_ONLY unexpectedly produced a calculation."
}
}

# Explicit script contract: successful completion resets the process exit code.
exit 0
