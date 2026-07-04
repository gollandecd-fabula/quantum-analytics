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
Copy-Item -LiteralPath (Join-Path $repositoryRoot "scripts\windows\configure_home_local.ps1") -Destination (Join-Path $stageRoot "scripts\configure_home_local.ps1") -Force
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

$configureCommand = @'
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\configure_home_local.ps1"
if errorlevel 1 pause
'@
Set-Content -LiteralPath (Join-Path $stageRoot "CONFIGURE_HOME_LOCAL.cmd") -Value $configureCommand -Encoding ASCII

$installCommand = @'
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_home_local.ps1"
if errorlevel 1 pause
'@
Set-Content -LiteralPath (Join-Path $stageRoot "INSTALL_HOME_LOCAL.cmd") -Value $installCommand -Encoding ASCII

$readme = @'
QUANTUM HOME_LOCAL WINDOWS PACKAGE — RED TEAM HARDENED

1. Extract the package outside cloud-synchronized folders.
2. Run INSTALL_HOME_LOCAL.cmd.
3. If no ready config exists, run CONFIGURE_HOME_LOCAL.cmd and enter the report period and retention deadline.
4. Run IMPORT_XLSX.cmd and select the authorized XLSX report.
5. Quantum displays the discovered sheet, header row and headers before REVIEWED can be confirmed.
6. ADMISSION_ONLY validates and admits the report without inventing cost, tax or expense values.
7. FULL financial calculation requires an explicit valid finance_request.
8. The installer verifies every packaged file against manifest.sha256.json before changing the installation.
9. Existing config, data and output directories are preserved.
10. HOME_LOCAL does not require BitLocker; the result records the unencrypted-storage limitation.
11. No marketplace writes, deploy, public/LAN exposure or production release are enabled.
12. Do not upload real reports, configs, data or output to GitHub or cloud-sync folders.
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
if ([string]::IsNullOrWhiteSpace($sourceCommit) -or $sourceCommit -notmatch "^[0-9a-fA-F]{40}$") {
    throw "A valid exact source commit is required to build the HOME_LOCAL package."
}
$manifest = [ordered]@{
    package = "QuantumLocalProduction_HOME_LOCAL"
    package_version = "R2_REDTEAM"
    source_branch = $sourceBranch
    source_commit = $sourceCommit.ToLowerInvariant()
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
