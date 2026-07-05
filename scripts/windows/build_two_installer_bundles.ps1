[CmdletBinding()]
param(
    [string]$OutputDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Write-AsciiFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )
    [IO.File]::WriteAllText($Path, $Content, [Text.Encoding]::ASCII)
}

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $repositoryRoot "dist\installer-bundles-r2"
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
Remove-Item -LiteralPath $OutputDirectory -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

$workRoot = Join-Path $env:RUNNER_TEMP ("quantum-installer-bundles-{0}" -f [guid]::NewGuid().ToString("N"))
$quantumBuildRoot = Join-Path $workRoot "quantum-build"
$continueRoot = Join-Path $workRoot "1_QUANTUM_CONTINUE_AND_FINISH"
$fullRoot = Join-Path $workRoot "2_QUANTUM_FULL_OFFLINE_INSTALLER"
foreach ($path in @($workRoot, $quantumBuildRoot, $continueRoot, $fullRoot)) {
    New-Item -ItemType Directory -Path $path -Force | Out-Null
}

try {
    $builder = Join-Path $PSScriptRoot "build_local_production.ps1"
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File $builder -OutputDirectory $quantumBuildRoot | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Quantum HOME_LOCAL package build failed with exit code $LASTEXITCODE"
    }
    $quantumPackage = Join-Path $quantumBuildRoot "QuantumLocalProduction_HOME_LOCAL.zip"
    if (-not (Test-Path -LiteralPath $quantumPackage -PathType Leaf)) {
        throw "Quantum package was not produced: $quantumPackage"
    }
    $quantumHash = Get-Sha256 -Path $quantumPackage

    $pythonVersion = "3.12.10"
    $pythonInstallerName = "python-$pythonVersion-amd64.exe"
    $pythonUrl = "https://www.python.org/ftp/python/$pythonVersion/$pythonInstallerName"
    $pythonExpectedSha256 = "67b5635e80ea51072b87941312d00ec8927c4db9ba18938f7ad2d27b328b95fb"
    $pythonInstaller = Join-Path $workRoot $pythonInstallerName
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonInstaller -UseBasicParsing
    $pythonActualSha256 = Get-Sha256 -Path $pythonInstaller
    if ($pythonActualSha256 -ne $pythonExpectedSha256) {
        throw "Official Python installer SHA-256 mismatch. Expected $pythonExpectedSha256, got $pythonActualSha256"
    }

    Copy-Item -LiteralPath $quantumPackage -Destination (Join-Path $continueRoot "QuantumLocalProduction_HOME_LOCAL.zip") -Force
    Copy-Item -LiteralPath $quantumPackage -Destination (Join-Path $fullRoot "QuantumLocalProduction_HOME_LOCAL.zip") -Force
    Copy-Item -LiteralPath $pythonInstaller -Destination (Join-Path $fullRoot $pythonInstallerName) -Force

    $continueCmd = @'
@echo off
setlocal EnableExtensions
title Quantum - Continue and finish installation
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0CONTINUE_AND_FINISH.ps1"
set "Q_EXIT=%ERRORLEVEL%"
if not "%Q_EXIT%"=="0" (
  echo.
  echo Quantum installation did not complete. Error code: %Q_EXIT%
  echo Use package 2 if Python is not installed or the current installation is damaged.
  pause
)
exit /b %Q_EXIT%
'@
    Write-AsciiFile -Path (Join-Path $continueRoot "CONTINUE_AND_FINISH.cmd") -Content $continueCmd

    $continuePs1 = @'
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Test-Python312 {
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python) {
        & $python.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 17)" | Out-Null
        if ($LASTEXITCODE -eq 0) { return $true }
    }
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) {
        & $py.Source -3.12 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 17)" | Out-Null
        if ($LASTEXITCODE -eq 0) { return $true }
    }
    return $false
}

if (-not [Environment]::Is64BitOperatingSystem) {
    throw "This installer supports only 64-bit Windows 10 or Windows 11."
}
if (-not (Test-Python312)) {
    throw "Python 3.12 or newer was not found. Run package 2: QUANTUM_FULL_OFFLINE_INSTALLER."
}

$bundle = Join-Path $PSScriptRoot "QuantumLocalProduction_HOME_LOCAL.zip"
$expectedHash = "__QUANTUM_HASH__"
$actualHash = (Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $expectedHash) {
    throw "Quantum package SHA-256 mismatch."
}

$temporaryRoot = Join-Path $env:TEMP ("QuantumContinue_{0}" -f [guid]::NewGuid().ToString("N"))
$targetRoot = Join-Path $env:LOCALAPPDATA "QuantumLocalProduction"
try {
    New-Item -ItemType Directory -Path $temporaryRoot -Force | Out-Null
    Expand-Archive -LiteralPath $bundle -DestinationPath $temporaryRoot -Force
    $launcher = Join-Path $temporaryRoot "scripts\one_click_home_local.ps1"
    if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
        throw "One-click launcher is missing from the Quantum package."
    }
    Write-Host "Continuing and repairing Quantum HOME_LOCAL..." -ForegroundColor Cyan
    & $launcher -PackageRoot $temporaryRoot -TargetRoot $targetRoot
    Write-Host "Quantum installation and first-run workflow completed." -ForegroundColor Green
}
finally {
    Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
}
'@
    $continuePs1 = $continuePs1.Replace("__QUANTUM_HASH__", $quantumHash)
    Write-AsciiFile -Path (Join-Path $continueRoot "CONTINUE_AND_FINISH.ps1") -Content $continuePs1

    $continueReadme = @"
QUANTUM PACKAGE 1 - CONTINUE AND FINISH

Use this package when installation was already started and Python 3.12+ is present.

1. Extract the ZIP to a normal local folder.
2. Double-click CONTINUE_AND_FINISH.cmd.
3. Existing config, data and output are preserved.
4. The package repairs/reinstalls the managed Quantum runtime and continues configuration/import.
5. If Python is missing, use package 2 instead.

Quantum package SHA-256: $quantumHash
"@
    [IO.File]::WriteAllText((Join-Path $continueRoot "README_FIRST.txt"), $continueReadme, [Text.UTF8Encoding]::new($false))

    $fullCmd = @'
@echo off
setlocal EnableExtensions
title Quantum - Full offline installation for a clean PC
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALL_QUANTUM_FULL_OFFLINE.ps1"
set "Q_EXIT=%ERRORLEVEL%"
if not "%Q_EXIT%"=="0" (
  echo.
  echo Quantum full installation did not complete. Error code: %Q_EXIT%
  pause
)
exit /b %Q_EXIT%
'@
    Write-AsciiFile -Path (Join-Path $fullRoot "INSTALL_QUANTUM_FULL_OFFLINE.cmd") -Content $fullCmd

    $fullPs1 = @'
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Test-Python312 {
    $candidates = @()
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python) { $candidates += [pscustomobject]@{ Exe = $python.Source; Prefix = @() } }
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) { $candidates += [pscustomobject]@{ Exe = $py.Source; Prefix = @("-3.12") } }
    $localPython = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    if (Test-Path -LiteralPath $localPython -PathType Leaf) {
        $candidates += [pscustomobject]@{ Exe = $localPython; Prefix = @() }
    }
    foreach ($candidate in $candidates) {
        $arguments = @()
        $arguments += $candidate.Prefix
        $arguments += @("-c", "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 17)")
        & $candidate.Exe @arguments | Out-Null
        if ($LASTEXITCODE -eq 0) { return $candidate.Exe }
    }
    return $null
}

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $parts = @($machinePath, $userPath, $env:PATH) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    $env:PATH = $parts -join ";"
}

if (-not [Environment]::Is64BitOperatingSystem) {
    throw "This installer supports only 64-bit Windows 10 or Windows 11."
}

$pythonInstaller = Join-Path $PSScriptRoot "__PYTHON_INSTALLER_NAME__"
$pythonExpectedHash = "__PYTHON_HASH__"
$pythonActualHash = (Get-FileHash -LiteralPath $pythonInstaller -Algorithm SHA256).Hash.ToLowerInvariant()
if ($pythonActualHash -ne $pythonExpectedHash) {
    throw "Bundled Python installer SHA-256 mismatch."
}

$pythonExecutable = Test-Python312
if (-not $pythonExecutable) {
    Write-Host "Installing bundled Python 3.12.10 for the current Windows user..." -ForegroundColor Cyan
    $arguments = @(
        "/quiet",
        "InstallAllUsers=0",
        "PrependPath=1",
        "Include_launcher=1",
        "Include_pip=1",
        "Include_test=0",
        "Include_doc=0",
        "Shortcuts=0",
        "AssociateFiles=0"
    )
    $process = Start-Process -FilePath $pythonInstaller -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -notin @(0, 3010)) {
        throw "Python installer failed with exit code $($process.ExitCode)."
    }
    Refresh-ProcessPath
    $localPythonRoot = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312"
    if (Test-Path -LiteralPath $localPythonRoot -PathType Container) {
        $env:PATH = "$localPythonRoot;$(Join-Path $localPythonRoot 'Scripts');$env:PATH"
    }
    $pythonExecutable = Test-Python312
    if (-not $pythonExecutable) {
        throw "Python 3.12 was installed but could not be started. Restart Windows and run this installer again."
    }
}
else {
    Write-Host "Compatible Python already exists: $pythonExecutable" -ForegroundColor Green
}

$bundle = Join-Path $PSScriptRoot "QuantumLocalProduction_HOME_LOCAL.zip"
$quantumExpectedHash = "__QUANTUM_HASH__"
$quantumActualHash = (Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash.ToLowerInvariant()
if ($quantumActualHash -ne $quantumExpectedHash) {
    throw "Bundled Quantum package SHA-256 mismatch."
}

$temporaryRoot = Join-Path $env:TEMP ("QuantumFullInstall_{0}" -f [guid]::NewGuid().ToString("N"))
$targetRoot = Join-Path $env:LOCALAPPDATA "QuantumLocalProduction"
try {
    New-Item -ItemType Directory -Path $temporaryRoot -Force | Out-Null
    Expand-Archive -LiteralPath $bundle -DestinationPath $temporaryRoot -Force
    $launcher = Join-Path $temporaryRoot "scripts\one_click_home_local.ps1"
    if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
        throw "One-click launcher is missing from the Quantum package."
    }
    Write-Host "Installing Quantum and starting the first-run workflow..." -ForegroundColor Cyan
    & $launcher -PackageRoot $temporaryRoot -TargetRoot $targetRoot
    Write-Host "Quantum full installation completed." -ForegroundColor Green
    Write-Host "Installed launcher: $(Join-Path $targetRoot 'START_QUANTUM.cmd')"
}
finally {
    Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
}
'@
    $fullPs1 = $fullPs1.Replace("__PYTHON_INSTALLER_NAME__", $pythonInstallerName)
    $fullPs1 = $fullPs1.Replace("__PYTHON_HASH__", $pythonActualSha256)
    $fullPs1 = $fullPs1.Replace("__QUANTUM_HASH__", $quantumHash)
    Write-AsciiFile -Path (Join-Path $fullRoot "INSTALL_QUANTUM_FULL_OFFLINE.ps1") -Content $fullPs1

    $fullReadme = @"
QUANTUM PACKAGE 2 - FULL OFFLINE INSTALLER FOR A CLEAN PC

This package contains:
- official Python $pythonVersion 64-bit installer from python.org;
- verified Quantum HOME_LOCAL R3 package;
- one full installation launcher.

Supported system: 64-bit Windows 10 or Windows 11.
Internet is not required after this ZIP has been downloaded.
Administrator rights are not required for the default per-user installation.

1. Extract the ZIP to a normal local folder outside OneDrive, Dropbox or Google Drive.
2. Double-click INSTALL_QUANTUM_FULL_OFFLINE.cmd.
3. Python is installed only when Python 3.12+ is absent.
4. Quantum is installed to %LOCALAPPDATA%\QuantumLocalProduction.
5. Continue with the displayed configuration and XLSX review prompts.

Python installer URL: $pythonUrl
Python installer SHA-256: $pythonActualSha256
Quantum package SHA-256: $quantumHash
"@
    [IO.File]::WriteAllText((Join-Path $fullRoot "README_FIRST.txt"), $fullReadme, [Text.UTF8Encoding]::new($false))

    $sourceCommit = (& git -C $repositoryRoot rev-parse HEAD).Trim()
    $continueManifest = [ordered]@{
        bundle = "QUANTUM_CONTINUE_AND_FINISH"
        bundle_version = "R2"
        source_commit = $sourceCommit
        quantum_package_sha256 = $quantumHash
        requires_python_312_or_newer = $true
    }
    $fullManifest = [ordered]@{
        bundle = "QUANTUM_FULL_OFFLINE_INSTALLER"
        bundle_version = "R2"
        source_commit = $sourceCommit
        quantum_package_sha256 = $quantumHash
        python_version = $pythonVersion
        python_installer_sha256 = $pythonActualSha256
        python_source_url = $pythonUrl
        offline_after_download = $true
    }
    $continueManifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $continueRoot "BUNDLE_MANIFEST.json") -Encoding UTF8
    $fullManifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $fullRoot "BUNDLE_MANIFEST.json") -Encoding UTF8

    $continueZip = Join-Path $OutputDirectory "1_QUANTUM_CONTINUE_AND_FINISH.zip"
    $fullZip = Join-Path $OutputDirectory "2_QUANTUM_FULL_OFFLINE_INSTALLER.zip"
    Compress-Archive -Path (Join-Path $continueRoot "*") -DestinationPath $continueZip -CompressionLevel Optimal
    Compress-Archive -Path (Join-Path $fullRoot "*") -DestinationPath $fullZip -CompressionLevel Optimal

    $result = [ordered]@{
        source_commit = $sourceCommit
        continue_bundle = [ordered]@{
            path = $continueZip
            size_bytes = (Get-Item -LiteralPath $continueZip).Length
            sha256 = Get-Sha256 -Path $continueZip
        }
        full_offline_bundle = [ordered]@{
            path = $fullZip
            size_bytes = (Get-Item -LiteralPath $fullZip).Length
            sha256 = Get-Sha256 -Path $fullZip
        }
        python_installer_sha256 = $pythonActualSha256
        quantum_package_sha256 = $quantumHash
    }
    $result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $OutputDirectory "installer-bundles-result.json") -Encoding UTF8
    $result | ConvertTo-Json -Depth 6 | Write-Output
}
finally {
    Remove-Item -LiteralPath $workRoot -Recurse -Force -ErrorAction SilentlyContinue
}
