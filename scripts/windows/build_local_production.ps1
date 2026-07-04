[CmdletBinding()]
param(
    [string]$OutputDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-PythonVersion {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$Prefix
    )
    $probe = @()
    $probe += $Prefix
    $probe += @("-c", "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 17)")
    & $Executable @probe | Out-Null
    return $LASTEXITCODE -eq 0
}

function Resolve-PythonCommand {
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python -and (Test-PythonVersion -Executable $python.Source -Prefix @())) {
        return [pscustomobject]@{ Executable = $python.Source; Prefix = @() }
    }
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py -and (Test-PythonVersion -Executable $py.Source -Prefix @("-3.12"))) {
        return [pscustomobject]@{ Executable = $py.Source; Prefix = @("-3.12") }
    }
    throw "Python 3.12 or newer was not found."
}

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
foreach ($directory in @("scripts", "config", "docs", "requirements")) {
    New-Item -ItemType Directory -Path (Join-Path $stageRoot $directory) -Force | Out-Null
}

Copy-Item -LiteralPath (Join-Path $repositoryRoot "src") -Destination (Join-Path $stageRoot "src") -Recurse -Force
Copy-Item -LiteralPath (Join-Path $repositoryRoot "scripts\windows\import_source.ps1") -Destination (Join-Path $stageRoot "scripts\import_source.ps1") -Force
Copy-Item -LiteralPath (Join-Path $repositoryRoot "scripts\windows\install_home_local.ps1") -Destination (Join-Path $stageRoot "scripts\install_home_local.ps1") -Force
Copy-Item -LiteralPath (Join-Path $repositoryRoot "config\home-local.template.json") -Destination (Join-Path $stageRoot "config\home-local.template.json") -Force

$requirementsPath = Join-Path $repositoryRoot "requirements\windows-home-local.txt"
if (-not (Test-Path -LiteralPath $requirementsPath -PathType Leaf)) {
    throw "Windows dependency lock is missing: $requirementsPath"
}
Copy-Item -LiteralPath $requirementsPath -Destination (Join-Path $stageRoot "requirements\windows-home-local.txt") -Force

$pythonCommand = Resolve-PythonCommand
$pipArguments = @()
$pipArguments += $pythonCommand.Prefix
$pipArguments += @(
    "-m", "pip", "install",
    "--disable-pip-version-check",
    "--no-deps",
    "--only-binary=:all:",
    "--require-hashes",
    "--target", (Join-Path $stageRoot "src"),
    "-r", $requirementsPath
)
& $pythonCommand.Executable @pipArguments | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Failed to vendor hash-pinned Windows dependencies. Exit code: $LASTEXITCODE"
}
$moscowZone = Join-Path $stageRoot "src\tzdata\zoneinfo\Europe\Moscow"
if (-not (Test-Path -LiteralPath $moscowZone -PathType Leaf)) {
    throw "Vendored timezone database is incomplete: $moscowZone"
}

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
6. The package includes the hash-pinned IANA timezone database required by Windows Python.
7. No marketplace writes, deploy, public/LAN exposure or production release are enabled.
8. Do not upload real reports, configs, data or output to GitHub or cloud-sync folders.
'@
Set-Content -LiteralPath (Join-Path $stageRoot "README_FIRST.txt") -Value $readme -Encoding UTF8

$stageFullPath = [IO.Path]::GetFullPath($stageRoot).TrimEnd([char[]]"\/")
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
$sourceBranch = $env:GITHUB_HEAD_REF
$git = Get-Command git.exe -ErrorAction SilentlyContinue
if ($git) {
    $sourceCommit = (& $git.Source -C $repositoryRoot rev-parse HEAD 2>$null | Select-Object -First 1)
    if ($LASTEXITCODE -ne 0) {
        $sourceCommit = $null
    }
    if ([string]::IsNullOrWhiteSpace($sourceBranch)) {
        $sourceBranch = (& $git.Source -C $repositoryRoot branch --show-current 2>$null | Select-Object -First 1)
        if ($LASTEXITCODE -ne 0) {
            $sourceBranch = $null
        }
    }
}
if ([string]::IsNullOrWhiteSpace($sourceBranch)) {
    $sourceBranch = "unknown"
}
$manifest = [ordered]@{
    package = "QuantumLocalProduction_HOME_LOCAL"
    package_version = "R1"
    source_branch = $sourceBranch
    source_commit = $sourceCommit
    release_state = "RELEASE_BLOCKED"
    marketplace_write_enabled = $false
    tzdata_version = "2026.2"
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
