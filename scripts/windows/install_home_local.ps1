[CmdletBinding()]
param(
    [string]$SourceRoot,
    [string]$TargetRoot = (Join-Path $env:LOCALAPPDATA "QuantumLocalProduction")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Icacls {
    param([string]$Path, [string[]]$Arguments, [string]$Operation)
    & icacls.exe $Path @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed for $Path with exit code $LASTEXITCODE"
    }
}

function Reset-ManagedAcl {
    param([string]$Path, [switch]$Recursive)
    if (-not (Test-Path -LiteralPath $Path -ErrorAction SilentlyContinue)) { return }
    $inherit = @("/inheritance:e", "/C")
    $reset = @("/reset", "/C")
    if ($Recursive) { $inherit += "/T"; $reset += "/T" }
    Invoke-Icacls -Path $Path -Arguments $inherit -Operation "ACL inheritance repair"
    Invoke-Icacls -Path $Path -Arguments $reset -Operation "Explicit ACL reset"
}

function New-QuantumShortcut {
    param([string]$Launcher, [string]$WorkingDirectory)
    try {
        $desktop = [Environment]::GetFolderPath("Desktop")
        if ([string]::IsNullOrWhiteSpace($desktop)) { return }
        $path = Join-Path $desktop "Quantum HOME_LOCAL.lnk"
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($path)
        $shortcut.TargetPath = $Launcher
        $shortcut.WorkingDirectory = $WorkingDirectory
        $shortcut.Description = "Quantum HOME_LOCAL - local pilot launcher"
        $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,167"
        $shortcut.Save()
        Write-Host "Desktop shortcut created: $path"
    }
    catch {
        Write-Warning "Desktop shortcut could not be created: $($_.Exception.GetType().Name)"
    }
}

function Get-PortablePath {
    param([string]$FullPath, [string]$RootPrefix)
    if (-not $FullPath.StartsWith($RootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Package path escaped the package root: $FullPath"
    }
    return $FullPath.Substring($RootPrefix.Length).Replace("\", "/")
}

function Assert-PackageManifest {
    param([string]$Root)
    $manifestPath = Join-Path $Root "manifest.sha256.json"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "Package manifest is missing: $manifestPath"
    }
    try { $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json }
    catch { throw "Package manifest is not valid JSON: $manifestPath" }

    if ([string]$manifest.package -ne "QuantumLocalProduction_HOME_LOCAL") { throw "Unexpected package identity in manifest." }
    if ([string]$manifest.release_state -ne "RELEASE_BLOCKED") { throw "Unexpected package release state." }
    if ($manifest.marketplace_write_enabled -ne $false) { throw "Marketplace writes must remain disabled in HOME_LOCAL." }
    if ($manifest.manifest_excludes_self -ne $true) { throw "Package manifest self-exclusion contract is invalid." }
    if ([string]$manifest.source_commit -notmatch "^[0-9a-fA-F]{40}$") { throw "Package source commit is missing or malformed." }

    $entries = @($manifest.files)
    if ($entries.Count -lt 1) { throw "Package manifest contains no files." }
    $rootFull = (Get-Item -LiteralPath $Root).FullName.TrimEnd([char[]]"\/")
    $prefix = $rootFull + [IO.Path]::DirectorySeparatorChar
    $manifestFull = (Get-Item -LiteralPath $manifestPath).FullName
    $declared = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)

    foreach ($entry in $entries) {
        $relative = [string]$entry.path
        if ([string]::IsNullOrWhiteSpace($relative)) { throw "Package manifest contains an empty path." }
        $normalized = $relative.Replace("/", "\")
        if ([IO.Path]::IsPathRooted($normalized)) { throw "Package manifest contains a rooted path: $relative" }
        $parts = @($normalized.Split("\"))
        if (@($parts | Where-Object { [string]::IsNullOrWhiteSpace($_) -or $_ -in @(".", "..") }).Count -gt 0) {
            throw "Package manifest contains an unsafe path: $relative"
        }
        $full = [IO.Path]::GetFullPath((Join-Path $rootFull $normalized))
        $portable = Get-PortablePath -FullPath $full -RootPrefix $prefix
        if (-not $declared.Add($portable)) { throw "Package manifest contains a duplicate path: $portable" }
        if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { throw "Manifest file is missing: $portable" }
        $item = Get-Item -LiteralPath $full
        if ([int64]$entry.size_bytes -ne [int64]$item.Length) { throw "Manifest size mismatch: $portable" }
        $hash = (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -ne ([string]$entry.sha256).ToLowerInvariant()) { throw "Manifest hash mismatch: $portable" }
    }

    $actual = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($item in @(Get-ChildItem -LiteralPath $rootFull -Recurse -File)) {
        $full = [IO.Path]::GetFullPath($item.FullName)
        if ($full.Equals($manifestFull, [StringComparison]::OrdinalIgnoreCase)) { continue }
        $portable = Get-PortablePath -FullPath $full -RootPrefix $prefix
        if (-not $actual.Add($portable)) { throw "Package contains a duplicate filesystem path: $portable" }
        if (-not $declared.Contains($portable)) { throw "Package contains an unmanifested file: $portable" }
    }
    foreach ($portable in $declared) {
        if (-not $actual.Contains($portable)) { throw "Manifest-covered package file was not enumerated: $portable" }
    }
    if ($actual.Count -ne $declared.Count) {
        throw "Package inventory count mismatch after exact path comparison: actual=$($actual.Count), manifest=$($declared.Count)."
    }
    foreach ($required in @(
        "src/quantum/pilot/windows_runner.py",
        "scripts/import_source.ps1",
        "scripts/configure_home_local.ps1",
        "scripts/one_click_home_local.ps1",
        "IMPORT_XLSX.cmd",
        "CONFIGURE_HOME_LOCAL.cmd",
        "START_QUANTUM.cmd"
    )) {
        if (-not $declared.Contains($required)) { throw "Required package entry is not covered by the manifest: $required" }
    }
    return $manifest
}

if ([string]::IsNullOrWhiteSpace($SourceRoot)) {
    $SourceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
}
else { $SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path }
$TargetRoot = [IO.Path]::GetFullPath($TargetRoot)

$packageManifest = Assert-PackageManifest -Root $SourceRoot
$sourceRuntime = [IO.Path]::GetFullPath((Join-Path $SourceRoot "src"))
$sourceLauncher = Join-Path $SourceRoot "scripts\import_source.ps1"
$sourceConfigurator = Join-Path $SourceRoot "scripts\configure_home_local.ps1"
$sourceOneClick = Join-Path $SourceRoot "scripts\one_click_home_local.ps1"
foreach ($required in @($sourceLauncher, $sourceConfigurator, $sourceOneClick)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Package script is missing: $required" }
}
if (-not (Test-Path -LiteralPath $sourceRuntime -PathType Container)) { throw "Package runtime directory is missing: $sourceRuntime" }

$runtimeTarget = [IO.Path]::GetFullPath((Join-Path $TargetRoot "src"))
if ($sourceRuntime.TrimEnd("\", "/") -ieq $runtimeTarget.TrimEnd("\", "/")) {
    throw "Installer must be run from an extracted package, not from the already installed runtime."
}

New-Item -ItemType Directory -Path $TargetRoot -Force | Out-Null
Reset-ManagedAcl -Path $TargetRoot
foreach ($name in @("config", "data", "output", "scripts")) {
    New-Item -ItemType Directory -Path (Join-Path $TargetRoot $name) -Force | Out-Null
}

$scriptsTarget = Join-Path $TargetRoot "scripts"
$launcherTarget = Join-Path $scriptsTarget "import_source.ps1"
$configuratorTarget = Join-Path $scriptsTarget "configure_home_local.ps1"
$oneClickTarget = Join-Path $scriptsTarget "one_click_home_local.ps1"
$obsoleteCommon = Join-Path $scriptsTarget "common.ps1"
$commandTarget = Join-Path $TargetRoot "IMPORT_XLSX.cmd"
$configureCommandTarget = Join-Path $TargetRoot "CONFIGURE_HOME_LOCAL.cmd"
$startCommandTarget = Join-Path $TargetRoot "START_QUANTUM.cmd"
$readmeSource = Join-Path $SourceRoot "README_FIRST.txt"
$readmeTarget = Join-Path $TargetRoot "README_FIRST.txt"
$templateSource = Join-Path $SourceRoot "config\home-local.template.json"
$templateTarget = Join-Path $TargetRoot "config\home-local.template.json"

Reset-ManagedAcl -Path $scriptsTarget -Recursive
Reset-ManagedAcl -Path $runtimeTarget -Recursive

$installId = "{0}_{1}" -f (Get-Date -Format "yyyyMMdd_HHmmss"), ([guid]::NewGuid().ToString("N").Substring(0, 8))
$transactionRoot = Join-Path $TargetRoot (".installing_{0}" -f $installId)
$runtimeStage = Join-Path $transactionRoot "src"
$fileStageRoot = Join-Path $transactionRoot "files"
$fileRollbackRoot = Join-Path $transactionRoot "rollback"
$runtimeBackup = Join-Path $TargetRoot ("src.backup_{0}" -f $installId)
$fileRollback = @()
$hadRuntime = $false
$runtimeActivated = $false

try {
    New-Item -ItemType Directory -Path $fileStageRoot,$fileRollbackRoot -Force | Out-Null
    Copy-Item -LiteralPath $sourceRuntime -Destination $runtimeStage -Recurse -Force
    if (-not (Test-Path -LiteralPath (Join-Path $runtimeStage "quantum\pilot\windows_runner.py") -PathType Leaf)) {
        throw "Staged runtime verification failed."
    }

    $stagedLauncher = Join-Path $fileStageRoot "import_source.ps1"
    $stagedConfigurator = Join-Path $fileStageRoot "configure_home_local.ps1"
    $stagedOneClick = Join-Path $fileStageRoot "one_click_home_local.ps1"
    Copy-Item -LiteralPath $sourceLauncher -Destination $stagedLauncher -Force
    Copy-Item -LiteralPath $sourceConfigurator -Destination $stagedConfigurator -Force
    Copy-Item -LiteralPath $sourceOneClick -Destination $stagedOneClick -Force

    $stagedImportCommand = Join-Path $fileStageRoot "IMPORT_XLSX.cmd"
    @'
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\import_source.ps1" -AuthorityAttested -SchemaReviewed
if errorlevel 1 pause
'@ | Set-Content -LiteralPath $stagedImportCommand -Encoding ASCII

    $stagedConfigureCommand = Join-Path $fileStageRoot "CONFIGURE_HOME_LOCAL.cmd"
    @'
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\configure_home_local.ps1"
if errorlevel 1 pause
'@ | Set-Content -LiteralPath $stagedConfigureCommand -Encoding ASCII

    $stagedStartCommand = Join-Path $fileStageRoot "START_QUANTUM.cmd"
    @'
@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\one_click_home_local.ps1" -InstalledRoot "%~dp0" -SkipInstall -AuthorityAttested -SchemaReviewed
set "quantum_exit=%errorlevel%"
if not "%quantum_exit%"=="0" pause
exit /b %quantum_exit%
'@ | Set-Content -LiteralPath $stagedStartCommand -Encoding ASCII

    $replacements = @(
        [pscustomobject]@{ Stage = $stagedLauncher; Target = $launcherTarget; Key = "scripts_import_source.ps1" },
        [pscustomobject]@{ Stage = $stagedConfigurator; Target = $configuratorTarget; Key = "scripts_configure_home_local.ps1" },
        [pscustomobject]@{ Stage = $stagedOneClick; Target = $oneClickTarget; Key = "scripts_one_click_home_local.ps1" },
        [pscustomobject]@{ Stage = $stagedImportCommand; Target = $commandTarget; Key = "IMPORT_XLSX.cmd" },
        [pscustomobject]@{ Stage = $stagedConfigureCommand; Target = $configureCommandTarget; Key = "CONFIGURE_HOME_LOCAL.cmd" },
        [pscustomobject]@{ Stage = $stagedStartCommand; Target = $startCommandTarget; Key = "START_QUANTUM.cmd" }
    )

    if (Test-Path -LiteralPath $readmeSource -PathType Leaf) {
        $stagedReadme = Join-Path $fileStageRoot "README_FIRST.txt"
        Copy-Item -LiteralPath $readmeSource -Destination $stagedReadme -Force
        $replacements += [pscustomobject]@{ Stage = $stagedReadme; Target = $readmeTarget; Key = "README_FIRST.txt" }
    }
    if ((Test-Path -LiteralPath $templateSource -PathType Leaf) -and -not (Test-Path -LiteralPath $templateTarget)) {
        $stagedTemplate = Join-Path $fileStageRoot "home-local.template.json"
        Copy-Item -LiteralPath $templateSource -Destination $stagedTemplate -Force
        $replacements += [pscustomobject]@{ Stage = $stagedTemplate; Target = $templateTarget; Key = "home-local.template.json" }
    }

    foreach ($replacement in $replacements) {
        if (-not (Test-Path -LiteralPath $replacement.Stage -PathType Leaf)) {
            throw "Staged managed file is missing: $($replacement.Stage)"
        }
        if ((Test-Path -LiteralPath $replacement.Target) -and -not (Test-Path -LiteralPath $replacement.Target -PathType Leaf)) {
            throw "Managed installation target is not a file: $($replacement.Target)"
        }
    }

    $hadRuntime = Test-Path -LiteralPath $runtimeTarget -PathType Container
    if ($hadRuntime) { Move-Item -LiteralPath $runtimeTarget -Destination $runtimeBackup }
    Move-Item -LiteralPath $runtimeStage -Destination $runtimeTarget
    $runtimeActivated = $true

    foreach ($replacement in $replacements) {
        $backupFile = Join-Path $fileRollbackRoot $replacement.Key
        $hadOriginal = Test-Path -LiteralPath $replacement.Target -PathType Leaf
        if ($hadOriginal) {
            Move-Item -LiteralPath $replacement.Target -Destination $backupFile
        }
        $fileRollback += [pscustomobject]@{
            Target = $replacement.Target
            Backup = $backupFile
            HadOriginal = $hadOriginal
        }
        Move-Item -LiteralPath $replacement.Stage -Destination $replacement.Target
    }

    $obsoleteBackup = Join-Path $fileRollbackRoot "obsolete_common.ps1"
    $hadObsoleteCommon = Test-Path -LiteralPath $obsoleteCommon -PathType Leaf
    if ($hadObsoleteCommon) {
        Move-Item -LiteralPath $obsoleteCommon -Destination $obsoleteBackup
        $fileRollback += [pscustomobject]@{
            Target = $obsoleteCommon
            Backup = $obsoleteBackup
            HadOriginal = $true
        }
    }

    Reset-ManagedAcl -Path $runtimeTarget -Recursive
    Reset-ManagedAcl -Path $scriptsTarget -Recursive
    foreach ($path in @($commandTarget, $configureCommandTarget, $startCommandTarget, $readmeTarget)) {
        if (Test-Path -LiteralPath $path) { Reset-ManagedAcl -Path $path }
    }

    foreach ($required in @(
        (Join-Path $runtimeTarget "quantum\pilot\windows_runner.py"),
        $launcherTarget,
        $configuratorTarget,
        $oneClickTarget,
        $commandTarget,
        $configureCommandTarget,
        $startCommandTarget
    )) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Installation verification failed: $required" }
        $stream = [IO.File]::Open($required, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
        $stream.Dispose()
    }
    if (Test-Path -LiteralPath $obsoleteCommon) { throw "Obsolete managed script was not removed: $obsoleteCommon" }
}
catch {
    $failure = $_
    $rollbackErrors = @()

    for ($index = $fileRollback.Count - 1; $index -ge 0; $index--) {
        $record = $fileRollback[$index]
        try {
            if (Test-Path -LiteralPath $record.Target) {
                Remove-Item -LiteralPath $record.Target -Recurse -Force
            }
            if ($record.HadOriginal -and (Test-Path -LiteralPath $record.Backup)) {
                Move-Item -LiteralPath $record.Backup -Destination $record.Target
            }
        }
        catch { $rollbackErrors += $_.Exception.Message }
    }

    try {
        if ($runtimeActivated -and (Test-Path -LiteralPath $runtimeTarget)) {
            Remove-Item -LiteralPath $runtimeTarget -Recurse -Force
        }
        if ($hadRuntime -and (Test-Path -LiteralPath $runtimeBackup)) {
            Move-Item -LiteralPath $runtimeBackup -Destination $runtimeTarget
        }
    }
    catch { $rollbackErrors += $_.Exception.Message }

    Remove-Item -LiteralPath $transactionRoot -Recurse -Force -ErrorAction SilentlyContinue
    if ($rollbackErrors.Count -gt 0) {
        throw "Installation failed: $($failure.Exception.Message). Rollback also failed: $($rollbackErrors -join '; ')"
    }
    throw $failure
}

Remove-Item -LiteralPath $transactionRoot -Recurse -Force -ErrorAction SilentlyContinue
New-QuantumShortcut -Launcher $startCommandTarget -WorkingDirectory $TargetRoot
Write-Host "Quantum HOME_LOCAL runtime installed." -ForegroundColor Green
Write-Host "Target: $TargetRoot"
Write-Host "Existing config, data and output directories were preserved."
Write-Host "One-click launch: $startCommandTarget"
Write-Host "Recovery import launcher: $commandTarget"
