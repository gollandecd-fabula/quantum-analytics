[CmdletBinding()]
param(
    [string]$BundleZip,
    [string]$OutputDirectory,
    [string]$OutputName = "Quantum_WB_Offline_Setup.exe"
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

function Test-CommitSha {
    param([AllowNull()][object]$Value)
    if ($null -eq $Value) {
        return $false
    }
    return ([string]$Value).Trim() -match "^[0-9a-fA-F]{40}$"
}

if ($env:OS -ne "Windows_NT") {
    throw "Quantum EXE installer must be built on Windows."
}

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $repositoryRoot "dist\installer-bundles-r2"
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

if ([string]::IsNullOrWhiteSpace($BundleZip)) {
    $BundleZip = Join-Path $OutputDirectory "2_QUANTUM_FULL_OFFLINE_INSTALLER.zip"
}
$BundleZip = [IO.Path]::GetFullPath($BundleZip)
if (-not (Test-Path -LiteralPath $BundleZip -PathType Leaf)) {
    throw "Full offline installer bundle is missing: $BundleZip"
}

$iexpress = Join-Path $env:SystemRoot "System32\iexpress.exe"
if (-not (Test-Path -LiteralPath $iexpress -PathType Leaf)) {
    $iexpressCommand = Get-Command iexpress.exe -ErrorAction SilentlyContinue
    if (-not $iexpressCommand) {
        throw "Windows IExpress was not found."
    }
    $iexpress = $iexpressCommand.Source
}

$sourceCommit = (& git -C $repositoryRoot rev-parse HEAD).Trim()
if (-not (Test-CommitSha $sourceCommit)) {
    throw "A valid exact source commit is required for EXE build."
}
$targetCommit = $env:TARGET_SHA
if ((Test-CommitSha $targetCommit) -and $targetCommit.Trim().ToLowerInvariant() -ne $sourceCommit.ToLowerInvariant()) {
    throw "EXE source commit does not match TARGET_SHA."
}
$sourceCommit = $sourceCommit.ToLowerInvariant()

$bundleHash = Get-Sha256 -Path $BundleZip
$exePath = Join-Path $OutputDirectory $OutputName
$resultPath = Join-Path $OutputDirectory "exe-installer-result.json"
Remove-Item -LiteralPath $exePath -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $resultPath -Force -ErrorAction SilentlyContinue

$workRoot = Join-Path $env:RUNNER_TEMP ("quantum-exe-builder-{0}" -f [guid]::NewGuid().ToString("N"))
$payloadRoot = Join-Path $workRoot "payload"
New-Item -ItemType Directory -Path $payloadRoot -Force | Out-Null

try {
    $payloadBundleName = "2_QUANTUM_FULL_OFFLINE_INSTALLER.zip"
    Copy-Item -LiteralPath $BundleZip -Destination (Join-Path $payloadRoot $payloadBundleName) -Force

    $bootstrapPs1 = @'
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Write-TestResult {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][object]$Payload
    )
    $directory = Split-Path -Parent ([IO.Path]::GetFullPath($Path))
    if (-not [string]::IsNullOrWhiteSpace($directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    $json = $Payload | ConvertTo-Json -Depth 6
    [IO.File]::WriteAllText($Path, $json, [Text.UTF8Encoding]::new($false))
}

$bundle = Join-Path $PSScriptRoot "2_QUANTUM_FULL_OFFLINE_INSTALLER.zip"
$expectedBundleHash = "__BUNDLE_HASH__"
$expectedSourceCommit = "__SOURCE_COMMIT__"
$nativeTestRequestPath = Join-Path $env:TEMP ("QuantumExeNativeTest_{0}.request" -f $expectedSourceCommit)
$defaultTestResultPath = Join-Path $env:TEMP ("QuantumExeNativeTest_{0}.json" -f $expectedSourceCommit)
$nativeTestRequested = $false
$requestedTestResultPath = $null
if (Test-Path -LiteralPath $nativeTestRequestPath -PathType Leaf) {
    try {
        $request = Get-Content -LiteralPath $nativeTestRequestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $requestHash = ([string]$request.payload_sha256).Trim().ToLowerInvariant()
        $requestCommit = ([string]$request.source_commit).Trim().ToLowerInvariant()
        $requestResultPath = [string]$request.result_path
        if (
            $requestHash -eq $expectedBundleHash -and
            $requestCommit -eq $expectedSourceCommit -and
            -not [string]::IsNullOrWhiteSpace($requestResultPath)
        ) {
            $nativeTestRequested = $true
            $requestedTestResultPath = [IO.Path]::GetFullPath($requestResultPath)
            Remove-Item -LiteralPath $nativeTestRequestPath -Force
        }
    }
    catch {
        $nativeTestRequested = $false
        $requestedTestResultPath = $null
    }
}
if (-not (Test-Path -LiteralPath $bundle -PathType Leaf)) {
    throw "Embedded Quantum offline bundle is missing."
}
$actualBundleHash = (Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualBundleHash -ne $expectedBundleHash) {
    throw "Embedded Quantum offline bundle SHA-256 mismatch."
}

$temporaryRoot = Join-Path $env:TEMP ("QuantumExeInstall_{0}" -f [guid]::NewGuid().ToString("N"))
try {
    New-Item -ItemType Directory -Path $temporaryRoot -Force | Out-Null
    Expand-Archive -LiteralPath $bundle -DestinationPath $temporaryRoot -Force

    $manifestPath = Join-Path $temporaryRoot "BUNDLE_MANIFEST.json"
    $installerPath = Join-Path $temporaryRoot "INSTALL_QUANTUM_FULL_OFFLINE.ps1"
    $quantumPackagePath = Join-Path $temporaryRoot "QuantumLocalProduction_HOME_LOCAL.zip"
    foreach ($required in @($manifestPath, $installerPath, $quantumPackagePath)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            throw "Required embedded installer file is missing: $required"
        }
    }

    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([string]$manifest.source_commit -ne $expectedSourceCommit) {
        throw "Embedded installer source commit mismatch."
    }
    $quantumHash = (Get-FileHash -LiteralPath $quantumPackagePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($quantumHash -ne [string]$manifest.quantum_package_sha256) {
        throw "Embedded Quantum package hash does not match its bundle manifest."
    }

    $testOnly = $nativeTestRequested -or $env:QUANTUM_EXE_TEST_ONLY -eq "1"
    if ($testOnly) {
        $testResultPath = $env:QUANTUM_EXE_TEST_RESULT
        if ([string]::IsNullOrWhiteSpace($testResultPath)) {
            $testResultPath = $requestedTestResultPath
        }
        if ([string]::IsNullOrWhiteSpace($testResultPath)) {
            $testResultPath = $defaultTestResultPath
        }
        Write-TestResult -Path $testResultPath -Payload ([ordered]@{
            status = "PASS"
            source_commit = $expectedSourceCommit
            payload_sha256 = $actualBundleHash
            release_scope = "WB_ONLY"
            enabled_marketplaces = @("WILDBERRIES")
            deferred_marketplaces = @("OZON")
            marketplace_write_enabled = $false
            installer_present = $true
            quantum_package_sha256 = $quantumHash
            native_test_request_consumed = $nativeTestRequested
        })
        exit 0
    }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installerPath
    $installerExitCode = $LASTEXITCODE
    if ($installerExitCode -ne 0) {
        throw "Quantum offline installer failed with exit code $installerExitCode."
    }
}
finally {
    Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
}
'@
    $bootstrapPs1 = $bootstrapPs1.Replace("__BUNDLE_HASH__", $bundleHash)
    $bootstrapPs1 = $bootstrapPs1.Replace("__SOURCE_COMMIT__", $sourceCommit)
    Write-AsciiFile -Path (Join-Path $payloadRoot "INSTALL_QUANTUM_EXE.ps1") -Content $bootstrapPs1

    $bootstrapCmd = @'
@echo off
setlocal EnableExtensions
title Quantum WB Offline Setup
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALL_QUANTUM_EXE.ps1"
set "Q_EXIT=%ERRORLEVEL%"
if not "%Q_EXIT%"=="0" (
  echo.
  echo Quantum installation did not complete. Error code: %Q_EXIT%
  if not "%QUANTUM_EXE_TEST_ONLY%"=="1" pause
)
exit /b %Q_EXIT%
'@
    Write-AsciiFile -Path (Join-Path $payloadRoot "INSTALL_QUANTUM_EXE.cmd") -Content $bootstrapCmd

    $sedPath = Join-Path $workRoot "Quantum_WB_Offline_Setup.sed"
    $sourceDirectory = $payloadRoot.TrimEnd([char[]]"\/") + "\"
    $sed = @"
[Version]
Class=IEXPRESS
SEDVersion=3

[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=0
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=%InstallPrompt%
DisplayLicense=%DisplayLicense%
FinishMessage=%FinishMessage%
TargetName=%TargetName%
FriendlyName=%FriendlyName%
AppLaunched=%AppLaunched%
PostInstallCmd=%PostInstallCmd%
AdminQuietInstCmd=%AdminQuietInstCmd%
UserQuietInstCmd=%UserQuietInstCmd%
SourceFiles=SourceFiles

[Strings]
InstallPrompt=
DisplayLicense=
FinishMessage=
TargetName=$exePath
FriendlyName=Quantum WB Offline Setup
AppLaunched=cmd.exe /c INSTALL_QUANTUM_EXE.cmd
PostInstallCmd=<None>
AdminQuietInstCmd=
UserQuietInstCmd=
FILE0="$payloadBundleName"
FILE1="INSTALL_QUANTUM_EXE.cmd"
FILE2="INSTALL_QUANTUM_EXE.ps1"

[SourceFiles]
SourceFiles0=$sourceDirectory

[SourceFiles0]
%FILE0%=
%FILE1%=
%FILE2%=
"@
    Write-AsciiFile -Path $sedPath -Content $sed

    $process = Start-Process -FilePath $iexpress -ArgumentList @("/N", $sedPath) -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "IExpress failed with exit code $($process.ExitCode)."
    }
    if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
        throw "Quantum EXE installer was not produced: $exePath"
    }

    $exeItem = Get-Item -LiteralPath $exePath
    if ($exeItem.Length -le 0) {
        throw "Quantum EXE installer is empty."
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $exePath
    if ([string]$signature.Status -eq "HashMismatch") {
        throw "Quantum EXE Authenticode hash verification failed."
    }

    $nativeTestRequestPath = Join-Path $env:TEMP ("QuantumExeNativeTest_{0}.request" -f $sourceCommit)
    $nativeTestResultPath = Join-Path $env:RUNNER_TEMP "quantum-exe-native-test.json"
    if ($env:GITHUB_ACTIONS -eq "true") {
        $request = [ordered]@{
            payload_sha256 = $bundleHash
            source_commit = $sourceCommit
            result_path = $nativeTestResultPath
        }
        $requestJson = $request | ConvertTo-Json -Depth 3
        [IO.File]::WriteAllText($nativeTestRequestPath, $requestJson, [Text.UTF8Encoding]::new($false))
    }

    $result = [ordered]@{
        installer = "Quantum_WB_Offline_Setup"
        installer_version = "R1"
        source_commit = $sourceCommit
        release_scope = "WB_ONLY"
        enabled_marketplaces = @("WILDBERRIES")
        deferred_marketplaces = @("OZON")
        marketplace_write_enabled = $false
        payload_bundle = [ordered]@{
            path = $BundleZip
            sha256 = $bundleHash
            size_bytes = (Get-Item -LiteralPath $BundleZip).Length
        }
        native_test = [ordered]@{
            request_path = $nativeTestRequestPath
            result_path = $nativeTestResultPath
            request_value = $bundleHash
            prepared = ($env:GITHUB_ACTIONS -eq "true")
        }
        exe = [ordered]@{
            path = $exePath
            sha256 = Get-Sha256 -Path $exePath
            size_bytes = $exeItem.Length
            authenticode_status = [string]$signature.Status
            code_signed = ([string]$signature.Status -eq "Valid")
        }
        builder = "WINDOWS_IEXPRESS_SYSTEM_COMPONENT"
        production_release_authorized = $false
    }
    $result | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $resultPath -Encoding UTF8
    $result | ConvertTo-Json -Depth 7 | Write-Output
}
finally {
    Remove-Item -LiteralPath $workRoot -Recurse -Force -ErrorAction SilentlyContinue
}
