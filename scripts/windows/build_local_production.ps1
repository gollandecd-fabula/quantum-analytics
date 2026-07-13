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

function Test-CommitSha {
    param([AllowNull()][object]$Value)
    if ($null -eq $Value) {
        return $false
    }
    return ([string]$Value).Trim() -match "^[0-9a-fA-F]{40}$"
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
$deferredOzonAdapter = Join-Path $stageRoot "src\quantum\adapters\ozon"
if (Test-Path -LiteralPath $deferredOzonAdapter) {
    Remove-Item -LiteralPath $deferredOzonAdapter -Recurse -Force
}
if (Test-Path -LiteralPath $deferredOzonAdapter) {
    throw "Deferred Ozon adapter remained in the WB-only release package."
}
Copy-Item -LiteralPath (Join-Path $repositoryRoot "scripts\windows\import_source.ps1") -Destination (Join-Path $stageRoot "scripts\import_source.ps1") -Force
Copy-Item -LiteralPath (Join-Path $repositoryRoot "scripts\windows\install_home_local.ps1") -Destination (Join-Path $stageRoot "scripts\install_home_local.ps1") -Force
Copy-Item -LiteralPath (Join-Path $repositoryRoot "scripts\windows\configure_home_local.ps1") -Destination (Join-Path $stageRoot "scripts\configure_home_local.ps1") -Force
Copy-Item -LiteralPath (Join-Path $repositoryRoot "scripts\windows\one_click_home_local.ps1") -Destination (Join-Path $stageRoot "scripts\one_click_home_local.ps1") -Force
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
    "--no-compile",
    "--target", (Join-Path $stageRoot "src"),
    "-r", $requirementsPath
)
& $pythonCommand.Executable @pipArguments | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Failed to vendor hash-pinned Windows dependencies. Exit code: $LASTEXITCODE"
}

$bytecodeFiles = @(
    Get-ChildItem -LiteralPath $stageRoot -Recurse -File -Force |
        Where-Object { $_.Extension -in @(".pyc", ".pyo") }
)
foreach ($file in $bytecodeFiles) {
    Remove-Item -LiteralPath $file.FullName -Force
}
$bytecodeDirectories = @(
    Get-ChildItem -LiteralPath $stageRoot -Recurse -Directory -Force |
        Where-Object { $_.Name -eq "__pycache__" } |
        Sort-Object { $_.FullName.Length } -Descending
)
foreach ($directory in $bytecodeDirectories) {
    Remove-Item -LiteralPath $directory.FullName -Recurse -Force
}
$remainingBytecode = @(
    Get-ChildItem -LiteralPath $stageRoot -Recurse -Force |
        Where-Object {
            ($_.PSIsContainer -and $_.Name -eq "__pycache__") -or
            (-not $_.PSIsContainer -and $_.Extension -in @(".pyc", ".pyo"))
        }
)
if ($remainingBytecode.Count -ne 0) {
    throw "Python bytecode contamination remained in the staged package."
}

$moscowZone = Join-Path $stageRoot "src\tzdata\zoneinfo\Europe\Moscow"
if (-not (Test-Path -LiteralPath $moscowZone -PathType Leaf)) {
    throw "Vendored timezone database is incomplete: $moscowZone"
}

$documentation = Join-Path $repositoryRoot "docs\pilot\WINDOWS_HOME_LOCAL_PACKAGE.md"
if (Test-Path -LiteralPath $documentation -PathType Leaf) {
    Copy-Item -LiteralPath $documentation -Destination (Join-Path $stageRoot "docs\WINDOWS_HOME_LOCAL_PACKAGE.md") -Force
}

$startCommand = @'
@echo off
setlocal
title Quantum HOME_LOCAL
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\one_click_home_local.ps1" -PackageRoot "%~dp0"
set "quantum_exit=%errorlevel%"
if not "%quantum_exit%"=="0" pause
exit /b %quantum_exit%
'@
Set-Content -LiteralPath (Join-Path $stageRoot "START_QUANTUM.cmd") -Value $startCommand -Encoding ASCII

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
QUANTUM HOME_LOCAL WINDOWS PACKAGE - ONE-CLICK LOCAL PILOT

RELEASE SCOPE
- This local release supports WILDBERRIES only.
- Ozon is deferred and is not included in the default registry or user package.

PRIMARY ACTION
1. Extract the ZIP outside OneDrive, Dropbox, Google Drive and other synchronized folders.
2. Double-click START_QUANTUM.cmd.
3. On the first run, the same window verifies and installs the package, creates a safe ADMISSION_ONLY configuration when required, opens XLSX selection, performs the local scan and continues automatically.
4. Type AUTHORIZE to confirm lawful authority, then review the displayed schema and reporting period and type REVIEWED.
5. After a successful run, Quantum opens the local dashboard/output directory.

SAFETY
- Launchers never attest on your behalf. Processing continues only after explicit AUTHORIZE and REVIEWED confirmations.
- Microsoft Defender scanning remains enabled during normal use.
- The installer verifies every packaged file against manifest.sha256.json before changing the installation.
- Existing config, data and output directories are preserved.
- Cost, tax and expense values are never invented. FULL financial calculation still requires an explicit valid finance_request.
- Marketplace writes, public/LAN exposure and production release remain disabled.
- Real reports, configs, storage data and outputs must not be uploaded to GitHub or cloud-synchronized folders.

RECOVERY TOOLS
- INSTALL_HOME_LOCAL.cmd - installation/repair only.
- CONFIGURE_HOME_LOCAL.cmd - configuration only.
- IMPORT_XLSX.cmd - import with explicit AUTHORIZE and REVIEWED confirmations.

DEFAULT INSTALLATION
%LOCALAPPDATA%\QuantumLocalProduction
A desktop shortcut named "Quantum HOME_LOCAL" is created when Windows permits it.
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

$sourceBranch = $env:GITHUB_HEAD_REF
$gitCommit = $null
$git = Get-Command git.exe -ErrorAction SilentlyContinue
if ($git) {
    $gitCommit = (& $git.Source -C $repositoryRoot rev-parse HEAD 2>$null | Select-Object -First 1)
    if ($LASTEXITCODE -ne 0 -or -not (Test-CommitSha $gitCommit)) {
        $gitCommit = $null
    }
    if ([string]::IsNullOrWhiteSpace($sourceBranch)) {
        $sourceBranch = (& $git.Source -C $repositoryRoot branch --show-current 2>$null | Select-Object -First 1)
        if ($LASTEXITCODE -ne 0) {
            $sourceBranch = $null
        }
    }
}

$eventCommit = $null
if (-not [string]::IsNullOrWhiteSpace($env:GITHUB_EVENT_PATH) -and (Test-Path -LiteralPath $env:GITHUB_EVENT_PATH -PathType Leaf)) {
    try {
        $event = Get-Content -LiteralPath $env:GITHUB_EVENT_PATH -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($event.pull_request -and $event.pull_request.head -and (Test-CommitSha $event.pull_request.head.sha)) {
            $eventCommit = ([string]$event.pull_request.head.sha).Trim()
        }
        elseif (Test-CommitSha $event.after) {
            $eventCommit = ([string]$event.after).Trim()
        }
    }
    catch {
        $eventCommit = $null
    }
}

$targetCommit = $env:TARGET_SHA
$sourceCommit = $gitCommit
if (-not (Test-CommitSha $sourceCommit)) {
    $sourceCommit = $targetCommit
}
if (-not (Test-CommitSha $sourceCommit)) {
    $sourceCommit = $eventCommit
}
if (-not (Test-CommitSha $sourceCommit)) {
    $sourceCommit = $env:GITHUB_SHA
}
if (-not (Test-CommitSha $sourceCommit)) {
    throw "A valid exact source commit is required to build the HOME_LOCAL package."
}
$sourceCommit = ([string]$sourceCommit).Trim().ToLowerInvariant()
foreach ($candidate in @($gitCommit, $targetCommit, $eventCommit)) {
    if ((Test-CommitSha $candidate) -and ([string]$candidate).Trim().ToLowerInvariant() -ne $sourceCommit) {
        throw "Exact source commit metadata does not match the checked-out source."
    }
}
if ([string]::IsNullOrWhiteSpace($sourceBranch)) {
    $sourceBranch = $env:GITHUB_REF_NAME
}
if ([string]::IsNullOrWhiteSpace($sourceBranch)) {
    $sourceBranch = "unknown"
}

$manifest = [ordered]@{
    package = "QuantumLocalProduction_HOME_LOCAL"
    package_version = "R3_ONE_CLICK"
    source_branch = $sourceBranch
    source_commit = $sourceCommit
    release_scope = "WB_ONLY"
    enabled_marketplaces = @("WILDBERRIES")
    deferred_marketplaces = @("OZON")
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
