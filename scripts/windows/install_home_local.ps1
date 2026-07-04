[CmdletBinding()]
param(
    [string]$SourceRoot,
    [string]$TargetRoot = (Join-Path $env:LOCALAPPDATA "QuantumLocalProduction")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($SourceRoot)) {
    $SourceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
}
else {
    $SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
}
$TargetRoot = [IO.Path]::GetFullPath($TargetRoot)

$sourceRuntime = [IO.Path]::GetFullPath((Join-Path $SourceRoot "src"))
$sourceLauncher = Join-Path $SourceRoot "scripts\import_source.ps1"
if (-not (Test-Path -LiteralPath $sourceRuntime -PathType Container)) {
    throw "Package runtime directory is missing: $sourceRuntime"
}
if (-not (Test-Path -LiteralPath $sourceLauncher -PathType Leaf)) {
    throw "Package launcher is missing: $sourceLauncher"
}

New-Item -ItemType Directory -Path $TargetRoot -Force | Out-Null
$runtimeTarget = [IO.Path]::GetFullPath((Join-Path $TargetRoot "src"))
if ($sourceRuntime.TrimEnd("\", "/") -ieq $runtimeTarget.TrimEnd("\", "/")) {
    throw "Installer must be run from an extracted package, not from the already installed runtime."
}

foreach ($name in @("config", "data", "output", "scripts")) {
    New-Item -ItemType Directory -Path (Join-Path $TargetRoot $name) -Force | Out-Null
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

$launcherTarget = Join-Path $TargetRoot "scripts\import_source.ps1"
$launcherBackup = $null
if (Test-Path -LiteralPath $launcherTarget -PathType Leaf) {
    $launcherBackup = "{0}.backup_{1}" -f $launcherTarget, $installId
    Copy-Item -LiteralPath $launcherTarget -Destination $launcherBackup -Force
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
Set-Content -LiteralPath (Join-Path $TargetRoot "IMPORT_XLSX.cmd") -Value $cmd -Encoding ASCII

$readmeSource = Join-Path $SourceRoot "README_FIRST.txt"
if (Test-Path -LiteralPath $readmeSource -PathType Leaf) {
    Copy-Item -LiteralPath $readmeSource -Destination (Join-Path $TargetRoot "README_FIRST.txt") -Force
}

& icacls.exe $TargetRoot /inheritance:e /T /C | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Failed to restore inherited ACLs under $TargetRoot"
}

foreach ($required in @(
    (Join-Path $TargetRoot "src\quantum\pilot\windows_runner.py"),
    $launcherTarget,
    (Join-Path $TargetRoot "IMPORT_XLSX.cmd")
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Installation verification failed: $required"
    }
}

Write-Host "Quantum HOME_LOCAL runtime installed." -ForegroundColor Green
Write-Host "Target: $TargetRoot"
Write-Host "Existing config, data and output directories were preserved."
Write-Host "Launch: $(Join-Path $TargetRoot 'IMPORT_XLSX.cmd')"
