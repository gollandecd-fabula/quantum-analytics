[CmdletBinding()]
param(
    [string]$OutputDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $repositoryRoot "dist"
}
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$OutputDirectory = (Resolve-Path -LiteralPath $OutputDirectory).Path

$stageRoot = Join-Path $OutputDirectory "QuantumLocalProduction"
$archivePath = Join-Path $OutputDirectory "QuantumLocalProduction_HOME_LOCAL.zip"
if (Test-Path -LiteralPath $stageRoot) {
    Remove-Item -LiteralPath $stageRoot -Recurse -Force
}
if (Test-Path -LiteralPath $archivePath) {
    Remove-Item -LiteralPath $archivePath -Force
}

New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $stageRoot "scripts") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $stageRoot "config") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $stageRoot "docs") -Force | Out-Null

Copy-Item -LiteralPath (Join-Path $repositoryRoot "src") -Destination (Join-Path $stageRoot "src") -Recurse -Force
Copy-Item -LiteralPath (Join-Path $repositoryRoot "scripts\windows\import_source.ps1") -Destination (Join-Path $stageRoot "scripts\import_source.ps1") -Force
Copy-Item -LiteralPath (Join-Path $repositoryRoot "scripts\windows\install_home_local.ps1") -Destination (Join-Path $stageRoot "scripts\install_home_local.ps1") -Force
Copy-Item -LiteralPath (Join-Path $repositoryRoot "config\home-local.template.json") -Destination (Join-Path $stageRoot "config\home-local.template.json") -Force

$documentation = Join-Path $repositoryRoot "docs\pilot\WINDOWS_HOME_LOCAL_PACKAGE.md"
if (Test-Path -LiteralPath $documentation -PathType Leaf) {
    Copy-Item -LiteralPath $documentation -Destination (Join-Path $stageRoot "docs\WINDOWS_HOME_LOCAL_PACKAGE.md") -Force
}

$importCommand = @'
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\import_source.ps1"
if errorlevel 1 pause
'@
Set-Content -LiteralPath (Join-Path $stageRoot "IMPORT_XLSX.cmd") -Value $importCommand -Encoding ASCII

$installCommand = @'
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_home_local.ps1"
if errorlevel 1 pause
'@
Set-Content -LiteralPath (Join-Path $stageRoot "INSTALL_HOME_LOCAL.cmd") -Value $installCommand -Encoding ASCII

$readme = @'
QUANTUM HOME_LOCAL WINDOWS PACKAGE

1. Existing installation: run INSTALL_HOME_LOCAL.cmd once.
2. Complete config\home-local.template.json and save it as config\default-home-local.json if no ready local config exists.
3. Import a report: run IMPORT_XLSX.cmd.
4. The installer preserves config, data and output directories.
5. HOME_LOCAL does not require BitLocker. The report records this limitation.
6. No marketplace writes, deploy, public/LAN exposure or production release are enabled.
7. Do not upload real reports, configs, data or output to GitHub or cloud-sync folders.
'@
Set-Content -LiteralPath (Join-Path $stageRoot "README_FIRST.txt") -Value $readme -Encoding UTF8

$stageFullPath = [IO.Path]::GetFullPath($stageRoot).TrimEnd("\", "/")
$stagePrefix = $stageFullPath + [IO.Path]::DirectorySeparatorChar
$manifestEntries = Get-ChildItem -LiteralPath $stageRoot -Recurse -File | Sort-Object FullName | ForEach-Object {
    $fullPath = [IO.Path]::GetFullPath($_.FullName)
    if (-not $fullPath.StartsWith($stagePrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Package file escaped staging root: $fullPath"
    }
    $relativePath = $fullPath.Substring($stagePrefix.Length).Replace("\", "/")
    [pscustomobject]@{
        path = $relativePath
        size_bytes = $_.Length
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}

$sourceCommit = $null
$git = Get-Command git.exe -ErrorAction SilentlyContinue
if ($git) {
    $sourceCommit = (& $git.Source -C $repositoryRoot rev-parse HEAD 2>$null | Select-Object -First 1)
    if ($LASTEXITCODE -ne 0) {
        $sourceCommit = $null
    }
}
$manifest = [ordered]@{
    package = "QuantumLocalProduction_HOME_LOCAL"
    package_version = "R1"
    source_branch = "local-pilot-windows-repair-r1"
    source_commit = $sourceCommit
    release_state = "RELEASE_BLOCKED"
    marketplace_write_enabled = $false
    manifest_excludes_self = $true
    files = @($manifestEntries)
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $stageRoot "manifest.sha256.json") -Encoding UTF8

Compress-Archive -Path (Join-Path $stageRoot "*") -DestinationPath $archivePath -CompressionLevel Optimal

if (-not (Test-Path -LiteralPath $archivePath -PathType Leaf)) {
    throw "Package archive was not produced: $archivePath"
}
$archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "Package built." -ForegroundColor Green
Write-Host "Archive: $archivePath"
Write-Host "SHA-256: $archiveHash"
Write-Output $archivePath
