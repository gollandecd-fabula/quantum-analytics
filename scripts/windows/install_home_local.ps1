[CmdletBinding()]
param(
    [string]$SourceRoot,
    [string]$TargetRoot = (Join-Path $env:LOCALAPPDATA "QuantumLocalProduction")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Icacls {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Operation
    )
    & icacls.exe $Path @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed for $Path with exit code $LASTEXITCODE"
    }
}

function Reset-ManagedAcl {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [switch]$Recursive
    )
    if (-not (Test-Path -LiteralPath $Path -ErrorAction SilentlyContinue)) {
        return
    }
    $inheritanceArguments = @("/inheritance:e", "/C")
    $resetArguments = @("/reset", "/C")
    if ($Recursive) {
        $inheritanceArguments += "/T"
        $resetArguments += "/T"
    }
    Invoke-Icacls -Path $Path -Arguments $inheritanceArguments -Operation "ACL inheritance repair"
    Invoke-Icacls -Path $Path -Arguments $resetArguments -Operation "Explicit ACL reset"
}

function New-QuantumShortcut {
    param(
        [Parameter(Mandatory = $true)][string]$Launcher,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory
    )
    try {
        $desktop = [Environment]::GetFolderPath("Desktop")
        if ([string]::IsNullOrWhiteSpace($desktop)) {
            return
        }
        $shortcutPath = Join-Path $desktop "Quantum HOME_LOCAL.lnk"
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $Launcher
        $shortcut.WorkingDirectory = $WorkingDirectory
        $shortcut.Description = "Quantum HOME_LOCAL - local pilot launcher"
        $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,167"
        $shortcut.Save()
        Write-Host "Desktop shortcut created: $shortcutPath"
    }
    catch {
        Write-Warning "Desktop shortcut could not be created: $($_.Exception.GetType().Name)"
    }
}

function Assert-PackageManifest {
    param([Parameter(Mandatory = $true)][string]$Root)

    $manifestPath = Join-Path $Root "manifest.sha256.json"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "Package manifest is missing: $manifestPath"
    }
    try {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        throw "Package manifest is not valid JSON: $manifestPath"
    }
    if ([string]$manifest.package -ne "QuantumLocalProduction_HOME_LOCAL") {
        throw "Unexpected package identity in manifest."
    }
    if ([string]$manifest.release_state -ne "RELEASE_BLOCKED") {
        throw "Unexpected package release state."
    }
    if ($manifest.marketplace_write_enabled -ne $false) {
        throw "Marketplace writes must remain disabled in HOME_LOCAL."
    }
    if ($manifest.manifest_excludes_self -ne $true) {
        throw "Package manifest self-exclusion contract is invalid."
    }
    if ([string]$manifest.source_commit -notmatch "^[0-9a-fA-F]{40}$") {
        throw "Package source commit is missing or malformed."
    }
    $entries = @($manifest.files)
    if ($entries.Count -lt 1) {
        throw "Package manifest contains no files."
    }

    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd([char[]]"\/")
    $rootPrefix = $rootFull + [IO.Path]::DirectorySeparatorChar
    $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($entry in $entries) {
        $relative = [string]$entry.path
        if ([string]::IsNullOrWhiteSpace($relative)) {
            throw "Package manifest contains an empty path."
        }
        $normalized = $relative.Replace("/", "\")
        if ([IO.Path]::IsPathRooted($normalized)) {
            throw "Package manifest contains a rooted path: $relative"
        }
        $parts = @($normalized.Split("\"))
        $unsafeParts = @(
            $parts | Where-Object {
                [string]::IsNullOrWhiteSpace($_) -or $_ -in @(".", "..")
            }
        )
        if ($parts.Count -eq 0 -or $unsafeParts.Count -gt 0) {
            throw "Package manifest contains an unsafe path: $relative"
        }
        $full = [IO.Path]::GetFullPath((Join-Path $rootFull $normalized))
        if (-not $full.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Package manifest path escaped the package root: $relative"
        }
        $portable = $full.Substring($rootPrefix.Length).Replace("\", "/")
        if (-not $seen.Add($portable)) {
            throw "Package manifest contains a duplicate path: $portable"
        }
        if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
            throw "Manifest file is missing: $portable"
        }
        $item = Get-Item -LiteralPath $full
        if ([int64]$entry.size_bytes -ne [int64]$item.Length) {
            throw "Manifest size mismatch: $portable"
        }
        $actual = (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne ([string]$entry.sha256).ToLowerInvariant()) {
            throw "Manifest hash mismatch: $portable"
        }
    }

    $actualFiles = @(
        Get-ChildItem -LiteralPath $rootFull -Recurse -File |
            Where-Object { $_.FullName -ne $manifestPath } |
            ForEach-Object {
                $_.FullName.Substring($rootPrefix.Length).Replace("\", "/")
            }
    )
    if ($actualFiles.Count -ne $seen.Count) {
        throw "Package file count does not match the manifest."
    }
    foreach ($relative in $actualFiles) {
        if (-not $seen.Contains($relative)) {
            throw "Package contains an unmanifested file: $relative"
        }
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
        if (-not $seen.Contains($required)) {
            throw "Required package entry is not covered by the manifest: $required"
        }
    }
    return $manifest
}

if ([string]::IsNullOrWhiteSpace($SourceRoot)) {
    $SourceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
}
else {
    $SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
}
$TargetRoot = [IO.Path]::GetFullPath($TargetRoot)

$packageManifest = Assert-PackageManifest -Root $SourceRoot
$sourceRuntime = [IO.Path]::GetFullPath((Join-Path $SourceRoot "src"))
$sourceLauncher = Join-Path $SourceRoot "scripts\import_source.ps1"
$sourceConfigurator = Join-Path $SourceRoot "scripts\configure_home_local.ps1"
$sourceOneClick = Join-Path $SourceRoot "scripts\one_click_home_local.ps1"
if (-not (Test-Path -LiteralPath $sourceRuntime -PathType Container)) {
    throw "Package runtime directory is missing: $sourceRuntime"
}
if (-not (Test-Path -LiteralPath $sourceLauncher -PathType Leaf)) {
    throw "Package launcher is missing: $sourceLauncher"
}
if (-not (Test-Path -LiteralPath $sourceConfigurator -PathType Leaf)) {
    throw "Package configurator is missing: $sourceConfigurator"
}
if (-not (Test-Path -LiteralPath $sourceOneClick -PathType Leaf)) {
    throw "Package one-click launcher is missing: $sourceOneClick"
}

$runtimeTarget = [IO.Path]::GetFullPath((Join-Path $TargetRoot "src"))
if ($sourceRuntime.TrimEnd("\", "/") -ieq $runtimeTarget.TrimEnd("\", "/")) {
    throw "Installer must be run from an extracted package, not from the already installed runtime."
}

New-Item -ItemType Directory -Path $TargetRoot -Force | Out-Null
Reset-ManagedAcl -Path $TargetRoot
foreach ($name in @("config", "data", "output", "scripts")) {
    New-Item -ItemType Directory -Path (Join-Path $TargetRoot $name) -Force | Out-Null
}

$scriptsTarget = [IO.Path]::GetFullPath((Join-Path $TargetRoot "scripts"))
$launcherTarget = Join-Path $scriptsTarget "import_source.ps1"
$configuratorTarget = Join-Path $scriptsTarget "configure_home_local.ps1"
$oneClickTarget = Join-Path $scriptsTarget "one_click_home_local.ps1"
$obsoleteCommon = Join-Path $scriptsTarget "common.ps1"

Reset-ManagedAcl -Path $scriptsTarget -Recursive
Reset-ManagedAcl -Path $runtimeTarget -Recursive
if (Test-Path -LiteralPath $obsoleteCommon -ErrorAction SilentlyContinue) {
    Remove-Item -LiteralPath $obsoleteCommon -Force
}

$installId = "{0}_{1}" -f (Get-Date -Format "yyyyMMdd_HHmmss"), ([guid]::NewGuid().ToString("N").Substring(0, 8))
$runtimeStage = Join-Path $TargetRoot ("src.installing_{0}" -f $installId)
$runtimeBackup = Join-Path $TargetRoot ("src.backup_{0}" -f $installId)

try {
    Copy-Item -LiteralPath $sourceRuntime -Destination $runtimeStage -Recurse -Force
    $stagedRunner = Join-Path $runtimeStage "quantum\pilot\windows_runner.py"
    if (-not (Test-Path -LiteralPath $stagedRunner -PathType Leaf)) {
        throw "Staged runtime verification failed: $stagedRunner"
    }

    $hadPreviousRuntime = Test-Path -LiteralPath $runtimeTarget -PathType Container
    if ($hadPreviousRuntime) {
        Move-Item -LiteralPath $runtimeTarget -Destination $runtimeBackup
        Write-Host "Previous runtime backed up to: $runtimeBackup"
    }

    try {
        Move-Item -LiteralPath $runtimeStage -Destination $runtimeTarget
    }
    catch {
        if ((-not (Test-Path -LiteralPath $runtimeTarget)) -and (Test-Path -LiteralPath $runtimeBackup)) {
            Move-Item -LiteralPath $runtimeBackup -Destination $runtimeTarget
        }
        throw
    }
}
catch {
    if (Test-Path -LiteralPath $runtimeStage) {
        Remove-Item -LiteralPath $runtimeStage -Recurse -Force -ErrorAction SilentlyContinue
    }
    throw
}

$launcherBackup = $null
if (Test-Path -LiteralPath $launcherTarget -PathType Leaf) {
    $launcherBackup = "{0}.backup_{1}" -f $launcherTarget, $installId
    try {
        Copy-Item -LiteralPath $launcherTarget -Destination $launcherBackup -Force
    }
    catch {
        Write-Warning "Existing launcher could not be backed up after ACL repair and will be replaced: $($_.Exception.GetType().Name)"
        $launcherBackup = $null
    }
}
try {
    Copy-Item -LiteralPath $sourceLauncher -Destination $launcherTarget -Force
}
catch {
    if ($launcherBackup -and (Test-Path -LiteralPath $launcherBackup -PathType Leaf)) {
        Copy-Item -LiteralPath $launcherBackup -Destination $launcherTarget -Force
    }
    throw
}

Copy-Item -LiteralPath $sourceConfigurator -Destination $configuratorTarget -Force
Copy-Item -LiteralPath $sourceOneClick -Destination $oneClickTarget -Force

$templateSource = Join-Path $SourceRoot "config\home-local.template.json"
$templateTarget = Join-Path $TargetRoot "config\home-local.template.json"
if ((Test-Path -LiteralPath $templateSource -PathType Leaf) -and -not (Test-Path -LiteralPath $templateTarget)) {
    Copy-Item -LiteralPath $templateSource -Destination $templateTarget
}

$cmd = @'
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\import_source.ps1"
if errorlevel 1 pause
'@
$commandTarget = Join-Path $TargetRoot "IMPORT_XLSX.cmd"
Set-Content -LiteralPath $commandTarget -Value $cmd -Encoding ASCII

$configureCmd = @'
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\configure_home_local.ps1"
if errorlevel 1 pause
'@
$configureCommandTarget = Join-Path $TargetRoot "CONFIGURE_HOME_LOCAL.cmd"
Set-Content -LiteralPath $configureCommandTarget -Value $configureCmd -Encoding ASCII

$startCmd = @'
@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\one_click_home_local.ps1" -InstalledRoot "%~dp0" -SkipInstall
set "quantum_exit=%errorlevel%"
if not "%quantum_exit%"=="0" pause
exit /b %quantum_exit%
'@
$startCommandTarget = Join-Path $TargetRoot "START_QUANTUM.cmd"
Set-Content -LiteralPath $startCommandTarget -Value $startCmd -Encoding ASCII

$readmeSource = Join-Path $SourceRoot "README_FIRST.txt"
$readmeTarget = Join-Path $TargetRoot "README_FIRST.txt"
if (Test-Path -LiteralPath $readmeSource -PathType Leaf) {
    Copy-Item -LiteralPath $readmeSource -Destination $readmeTarget -Force
}

Reset-ManagedAcl -Path $runtimeTarget -Recursive
Reset-ManagedAcl -Path $scriptsTarget -Recursive
Reset-ManagedAcl -Path $commandTarget
Reset-ManagedAcl -Path $configureCommandTarget
Reset-ManagedAcl -Path $startCommandTarget
if (Test-Path -LiteralPath $readmeTarget -PathType Leaf) {
    Reset-ManagedAcl -Path $readmeTarget
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
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Installation verification failed: $required"
    }
    $stream = [IO.File]::Open($required, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    $stream.Dispose()
}
if (Test-Path -LiteralPath $obsoleteCommon -ErrorAction SilentlyContinue) {
    throw "Obsolete managed script was not removed: $obsoleteCommon"
}

New-QuantumShortcut -Launcher $startCommandTarget -WorkingDirectory $TargetRoot

Write-Host "Quantum HOME_LOCAL runtime installed." -ForegroundColor Green
Write-Host "Target: $TargetRoot"
Write-Host "Existing config, data and output directories were preserved."
Write-Host "One-click launch: $startCommandTarget"
Write-Host "Recovery import launcher: $commandTarget"
