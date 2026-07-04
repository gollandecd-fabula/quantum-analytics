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

$sourceRuntime = Join-Path $SourceRoot "src"
$sourceLauncher = Join-Path $SourceRoot "scripts\import_source.ps1"
if (-not (Test-Path -LiteralPath $sourceRuntime -PathType Container)) {
    throw "Package runtime directory is missing: $sourceRuntime"
}
if (-not (Test-Path -LiteralPath $sourceLauncher -PathType Leaf)) {
    throw "Package launcher is missing: $sourceLauncher"
}

New-Item -ItemType Directory -Path $TargetRoot -Force | Out-Null
foreach ($name in @("config", "data", "output", "scripts")) {
    New-Item -ItemType Directory -Path (Join-Path $TargetRoot $name) -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$runtimeTarget = Join-Path $TargetRoot "src"
if (Test-Path -LiteralPath $runtimeTarget) {
    $runtimeBackup = Join-Path $TargetRoot ("src.backup_{0}" -f $timestamp)
    Move-Item -LiteralPath $runtimeTarget -Destination $runtimeBackup
    Write-Host "Previous runtime backed up to: $runtimeBackup"
}
Copy-Item -LiteralPath $sourceRuntime -Destination $runtimeTarget -Recurse -Force

$launcherTarget = Join-Path $TargetRoot "scripts\import_source.ps1"
if (Test-Path -LiteralPath $launcherTarget -PathType Leaf) {
    Copy-Item -LiteralPath $launcherTarget -Destination ("{0}.backup_{1}" -f $launcherTarget, $timestamp) -Force
}
Copy-Item -LiteralPath $sourceLauncher -Destination $launcherTarget -Force

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
