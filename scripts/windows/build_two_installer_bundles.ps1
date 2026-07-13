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
title Quantum
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0CONTINUE_AND_FINISH.ps1"
set "Q_EXIT=%ERRORLEVEL%"
if not "%Q_EXIT%"=="0" (
  echo.
  powershell.exe -NoProfile -Command "$m=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('0KPRgdGC0LDQvdC+0LLQutCwIFF1YW50dW0g0L3QtSDQt9Cw0LLQtdGA0YjQtdC90LAuINCa0L7QtCDQvtGI0LjQsdC60Lg6IHswfS4g0JjRgdC/0L7Qu9GM0LfRg9C50YLQtSDQv9Cw0LrQtdGCIDIsINC10YHQu9C4IFB5dGhvbiDQvdC1INGD0YHRgtCw0L3QvtCy0LvQtdC9INC40LvQuCDRgtC10LrRg9GJ0LDRjyDRg9GB0YLQsNC90L7QstC60LAg0L/QvtCy0YDQtdC20LTQtdC90LAu')); Write-Host ([string]::Format($m, '%Q_EXIT%'))"
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

function Get-QuantumRussianText {
    param(
        [Parameter(Mandatory = $true)][string]$Encoded,
        [object[]]$Arguments = @()
    )
    $text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Encoded))
    if ($Arguments.Count -gt 0) {
        return [string]::Format([Globalization.CultureInfo]::InvariantCulture, $text, $Arguments)
    }
    return $text
}

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
    throw (Get-QuantumRussianText -Encoded "0KPRgdGC0LDQvdC+0LLRidC40Log0L/QvtC00LTQtdGA0LbQuNCy0LDQtdGCINGC0L7Qu9GM0LrQviA2NC3RgNCw0LfRgNGP0LTQvdGL0LUgV2luZG93cyAxMCDQuCBXaW5kb3dzIDExLg==")
}
if (-not (Test-Python312)) {
    throw (Get-QuantumRussianText -Encoded "UHl0aG9uIDMuMTIg0LjQu9C4INC90L7QstC10LUg0L3QtSDQvdCw0LnQtNC10L0uINCX0LDQv9GD0YHRgtC40YLQtSDQv9Cw0LrQtdGCIDI6IFFVQU5UVU1fRlVMTF9PRkZMSU5FX0lOU1RBTExFUi4=")
}

$bundle = Join-Path $PSScriptRoot "QuantumLocalProduction_HOME_LOCAL.zip"
$expectedHash = "__QUANTUM_HASH__"
$actualHash = (Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $expectedHash) {
    throw (Get-QuantumRussianText -Encoded "U0hBLTI1NiDQv9Cw0LrQtdGC0LAgUXVhbnR1bSDQvdC1INGB0L7QstC/0LDQtNCw0LXRgiDRgSDQvtC20LjQtNCw0LXQvNGL0Lwg0LfQvdCw0YfQtdC90LjQtdC8Lg==")
}

$temporaryRoot = Join-Path $env:TEMP ("QuantumContinue_{0}" -f [guid]::NewGuid().ToString("N"))
$targetRoot = Join-Path $env:LOCALAPPDATA "QuantumLocalProduction"
try {
    New-Item -ItemType Directory -Path $temporaryRoot -Force | Out-Null
    Expand-Archive -LiteralPath $bundle -DestinationPath $temporaryRoot -Force
    $launcher = Join-Path $temporaryRoot "scripts\one_click_home_local.ps1"
    if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
        throw (Get-QuantumRussianText -Encoded "0JIg0L/QsNC60LXRgtC1IFF1YW50dW0g0L7RgtGB0YPRgtGB0YLQstGD0LXRgiDQv9GA0L7Qs9GA0LDQvNC80LAg0LfQsNC/0YPRgdC60LAg0L7QtNC90L7QuSDQutC90L7Qv9C60L7QuS4=")
    }
    Write-Host (Get-QuantumRussianText -Encoded "0J/RgNC+0LTQvtC70LbQtdC90LjQtSDRg9GB0YLQsNC90L7QstC60Lgg0Lgg0LLQvtGB0YHRgtCw0L3QvtCy0LvQtdC90LjQtSBRdWFudHVtIEhPTUVfTE9DQUwuLi4=") -ForegroundColor Cyan
    & $launcher -PackageRoot $temporaryRoot -TargetRoot $targetRoot
    Write-Host (Get-QuantumRussianText -Encoded "0KPRgdGC0LDQvdC+0LLQutCwIFF1YW50dW0g0Lgg0L/QtdGA0LLRi9C5INC30LDQv9GD0YHQuiDQt9Cw0LLQtdGA0YjQtdC90Ysu") -ForegroundColor Green
}
finally {
    Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
}
'@
    $continuePs1 = $continuePs1.Replace("__QUANTUM_HASH__", $quantumHash)
    Write-AsciiFile -Path (Join-Path $continueRoot "CONTINUE_AND_FINISH.ps1") -Content $continuePs1

    $continueReadme = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("0J/QkNCa0JXQoiBRVUFOVFVNIDEg4oCUINCf0KDQntCU0J7Qm9CW0JXQndCY0JUg0Jgg0JLQntCh0KHQotCQ0J3QntCS0JvQldCd0JjQlQoK0JjRgdC/0L7Qu9GM0LfRg9C50YLQtSDRjdGC0L7RgiDQv9Cw0LrQtdGCLCDQutC+0LPQtNCwINGD0YHRgtCw0L3QvtCy0LrQsCDRg9C20LUg0L3QsNGH0LjQvdCw0LvQsNGB0Ywg0LggUHl0aG9uIDMuMTIrINGD0YHRgtCw0L3QvtCy0LvQtdC9LgoKMS4g0KDQsNGB0L/QsNC60YPQudGC0LUgWklQINCyINC+0LHRi9GH0L3Rg9GOINC70L7QutCw0LvRjNC90YPRjiDQv9Cw0L/QutGDLgoyLiDQl9Cw0L/Rg9GB0YLQuNGC0LUgQ09OVElOVUVfQU5EX0ZJTklTSC5jbWQuCjMuINCh0YPRidC10YHRgtCy0YPRjtGJ0LjQtSBjb25maWcsIGRhdGEg0Lggb3V0cHV0INGB0L7RhdGA0LDQvdGP0Y7RgtGB0Y8uCjQuINCf0LDQutC10YIg0LLQvtGB0YHRgtCw0L3QvtCy0LjRgiDRg9C/0YDQsNCy0LvRj9C10LzRg9GOINGB0YDQtdC00YMgUXVhbnR1bSDQuCDQv9GA0L7QtNC+0LvQttC40YIg0L3QsNGB0YLRgNC+0LnQutGDINC4INC40LzQv9C+0YDRgi4KNS4g0JXRgdC70LggUHl0aG9uINC+0YLRgdGD0YLRgdGC0LLRg9C10YIsINC40YHQv9C+0LvRjNC30YPQudGC0LUg0L/QsNC60LXRgiAyLgoKU0hBLTI1NiDQv9Cw0LrQtdGC0LAgUXVhbnR1bTogX19RVUFOVFVNX0hBU0hfXwo="))
    $continueReadme = $continueReadme.Replace("__QUANTUM_HASH__", $quantumHash)
    [IO.File]::WriteAllText((Join-Path $continueRoot "README_FIRST.txt"), $continueReadme, [Text.UTF8Encoding]::new($false))

    $fullCmd = @'
@echo off
setlocal EnableExtensions
title Quantum
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALL_QUANTUM_FULL_OFFLINE.ps1"
set "Q_EXIT=%ERRORLEVEL%"
if not "%Q_EXIT%"=="0" (
  echo.
  powershell.exe -NoProfile -Command "$m=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('0J/QvtC70L3QsNGPINGD0YHRgtCw0L3QvtCy0LrQsCBRdWFudHVtINC90LUg0LfQsNCy0LXRgNGI0LXQvdCwLiDQmtC+0LQg0L7RiNC40LHQutC4OiB7MH0u')); Write-Host ([string]::Format($m, '%Q_EXIT%'))"
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

function Get-QuantumRussianText {
    param(
        [Parameter(Mandatory = $true)][string]$Encoded,
        [object[]]$Arguments = @()
    )
    $text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Encoded))
    if ($Arguments.Count -gt 0) {
        return [string]::Format([Globalization.CultureInfo]::InvariantCulture, $text, $Arguments)
    }
    return $text
}

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
    throw (Get-QuantumRussianText -Encoded "0KPRgdGC0LDQvdC+0LLRidC40Log0L/QvtC00LTQtdGA0LbQuNCy0LDQtdGCINGC0L7Qu9GM0LrQviA2NC3RgNCw0LfRgNGP0LTQvdGL0LUgV2luZG93cyAxMCDQuCBXaW5kb3dzIDExLg==")
}

$pythonInstaller = Join-Path $PSScriptRoot "__PYTHON_INSTALLER_NAME__"
$pythonExpectedHash = "__PYTHON_HASH__"
$pythonActualHash = (Get-FileHash -LiteralPath $pythonInstaller -Algorithm SHA256).Hash.ToLowerInvariant()
if ($pythonActualHash -ne $pythonExpectedHash) {
    throw (Get-QuantumRussianText -Encoded "U0hBLTI1NiDQstGB0YLRgNC+0LXQvdC90L7Qs9C+INGD0YHRgtCw0L3QvtCy0YnQuNC60LAgUHl0aG9uINC90LUg0YHQvtCy0L/QsNC00LDQtdGCINGBINC+0LbQuNC00LDQtdC80YvQvCDQt9C90LDRh9C10L3QuNC10Lwu")
}

$pythonExecutable = Test-Python312
if (-not $pythonExecutable) {
    Write-Host (Get-QuantumRussianText -Encoded "0KPRgdGC0LDQvdC+0LLQutCwINCy0YHRgtGA0L7QtdC90L3QvtCz0L4gUHl0aG9uIDMuMTIuMTAg0LTQu9GPINGC0LXQutGD0YnQtdCz0L4g0L/QvtC70YzQt9C+0LLQsNGC0LXQu9GPIFdpbmRvd3MuLi4=") -ForegroundColor Cyan
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
        throw (Get-QuantumRussianText -Encoded "0KPRgdGC0LDQvdC+0LLRidC40LogUHl0aG9uINC30LDQstC10YDRiNC40LvRgdGPINC+0YjQuNCx0LrQvtC5LiDQmtC+0LQg0LLRi9GF0L7QtNCwOiB7MH0u" -Arguments @($($process.ExitCode)))
    }
    Refresh-ProcessPath
    $localPythonRoot = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312"
    if (Test-Path -LiteralPath $localPythonRoot -PathType Container) {
        $env:PATH = "$localPythonRoot;$(Join-Path $localPythonRoot 'Scripts');$env:PATH"
    }
    $pythonExecutable = Test-Python312
    if (-not $pythonExecutable) {
        throw (Get-QuantumRussianText -Encoded "UHl0aG9uIDMuMTIg0YPRgdGC0LDQvdC+0LLQu9C10L0sINC90L4g0L3QtSDQt9Cw0L/Rg9GB0LrQsNC10YLRgdGPLiDQn9C10YDQtdC30LDQv9GD0YHRgtC40YLQtSBXaW5kb3dzINC4INGB0L3QvtCy0LAg0LfQsNC/0YPRgdGC0LjRgtC1INGD0YHRgtCw0L3QvtCy0YnQuNC6Lg==")
    }
}
else {
    Write-Host (Get-QuantumRussianText -Encoded "0KHQvtCy0LzQtdGB0YLQuNC80LDRjyDQstC10YDRgdC40Y8gUHl0aG9uINGD0LbQtSDRg9GB0YLQsNC90L7QstC70LXQvdCwOiB7MH0=" -Arguments @($pythonExecutable)) -ForegroundColor Green
}

$bundle = Join-Path $PSScriptRoot "QuantumLocalProduction_HOME_LOCAL.zip"
$quantumExpectedHash = "__QUANTUM_HASH__"
$quantumActualHash = (Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash.ToLowerInvariant()
if ($quantumActualHash -ne $quantumExpectedHash) {
    throw (Get-QuantumRussianText -Encoded "U0hBLTI1NiDQstGB0YLRgNC+0LXQvdC90L7Qs9C+INC/0LDQutC10YLQsCBRdWFudHVtINC90LUg0YHQvtCy0L/QsNC00LDQtdGCINGBINC+0LbQuNC00LDQtdC80YvQvCDQt9C90LDRh9C10L3QuNC10Lwu")
}

$temporaryRoot = Join-Path $env:TEMP ("QuantumFullInstall_{0}" -f [guid]::NewGuid().ToString("N"))
$targetRoot = Join-Path $env:LOCALAPPDATA "QuantumLocalProduction"
try {
    New-Item -ItemType Directory -Path $temporaryRoot -Force | Out-Null
    Expand-Archive -LiteralPath $bundle -DestinationPath $temporaryRoot -Force
    $launcher = Join-Path $temporaryRoot "scripts\one_click_home_local.ps1"
    if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
        throw (Get-QuantumRussianText -Encoded "0JIg0L/QsNC60LXRgtC1IFF1YW50dW0g0L7RgtGB0YPRgtGB0YLQstGD0LXRgiDQv9GA0L7Qs9GA0LDQvNC80LAg0LfQsNC/0YPRgdC60LAg0L7QtNC90L7QuSDQutC90L7Qv9C60L7QuS4=")
    }
    Write-Host (Get-QuantumRussianText -Encoded "0KPRgdGC0LDQvdC+0LLQutCwIFF1YW50dW0g0Lgg0LfQsNC/0YPRgdC6INC/0LXRgNCy0L7QvdCw0YfQsNC70YzQvdC+0Lkg0L3QsNGB0YLRgNC+0LnQutC4Li4u") -ForegroundColor Cyan
    & $launcher -PackageRoot $temporaryRoot -TargetRoot $targetRoot
    Write-Host (Get-QuantumRussianText -Encoded "0J/QvtC70L3QsNGPINGD0YHRgtCw0L3QvtCy0LrQsCBRdWFudHVtINC30LDQstC10YDRiNC10L3QsC4=") -ForegroundColor Green
    Write-Host (Get-QuantumRussianText -Encoded "0KPRgdGC0LDQvdC+0LLQu9C10L3QvdCw0Y8g0L/RgNC+0LPRgNCw0LzQvNCwINC30LDQv9GD0YHQutCwOiB7MH0=" -Arguments @($(Join-Path $targetRoot 'START_QUANTUM.cmd')))
}
finally {
    Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
}
'@
    $fullPs1 = $fullPs1.Replace("__PYTHON_INSTALLER_NAME__", $pythonInstallerName)
    $fullPs1 = $fullPs1.Replace("__PYTHON_HASH__", $pythonActualSha256)
    $fullPs1 = $fullPs1.Replace("__QUANTUM_HASH__", $quantumHash)
    Write-AsciiFile -Path (Join-Path $fullRoot "INSTALL_QUANTUM_FULL_OFFLINE.ps1") -Content $fullPs1

    $fullReadme = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("0J/QkNCa0JXQoiBRVUFOVFVNIDIg4oCUINCf0J7Qm9Cd0JDQryDQkNCS0KLQntCd0J7QnNCd0JDQryDQo9Ch0KLQkNCd0J7QktCa0JAKCtCh0L7QtNC10YDQttC40LzQvtC1OgotINC+0YTQuNGG0LjQsNC70YzQvdGL0LkgNjQt0YDQsNC30YDRj9C00L3Ri9C5INGD0YHRgtCw0L3QvtCy0YnQuNC6IFB5dGhvbiBfX1BZVEhPTl9WRVJTSU9OX18g0YEgcHl0aG9uLm9yZzsKLSDQv9GA0L7QstC10YDQtdC90L3Ri9C5INC/0LDQutC10YIgUXVhbnR1bSBIT01FX0xPQ0FMIFIzOwotINC10LTQuNC90LDRjyDQv9GA0L7Qs9GA0LDQvNC80LAg0L/QvtC70L3QvtC5INGD0YHRgtCw0L3QvtCy0LrQuC4KCtCf0L7QtNC00LXRgNC20LjQstCw0LXQvNCw0Y8g0YHQuNGB0YLQtdC80LA6IDY0LdGA0LDQt9GA0Y/QtNC90LDRjyBXaW5kb3dzIDEwINC40LvQuCBXaW5kb3dzIDExLgrQn9C+0YHQu9C1INC30LDQs9GA0YPQt9C60LggWklQINC/0L7QtNC60LvRjtGH0LXQvdC40LUg0Log0LjQvdGC0LXRgNC90LXRgtGDINC90LUg0YLRgNC10LHRg9C10YLRgdGPLgrQlNC70Y8g0YPRgdGC0LDQvdC+0LLQutC4INGC0LXQutGD0YnQtdC80YMg0L/QvtC70YzQt9C+0LLQsNGC0LXQu9GOINC/0YDQsNCy0LAg0LDQtNC80LjQvdC40YHRgtGA0LDRgtC+0YDQsCDQvdC1INC90YPQttC90YsuCgoxLiDQoNCw0YHQv9Cw0LrRg9C50YLQtSBaSVAg0LIg0L7QsdGL0YfQvdGD0Y4g0LvQvtC60LDQu9GM0L3Rg9GOINC/0LDQv9C60YMg0LLQvdC1IE9uZURyaXZlLCBEcm9wYm94INC40LvQuCBHb29nbGUgRHJpdmUuCjIuINCX0LDQv9GD0YHRgtC40YLQtSBJTlNUQUxMX1FVQU5UVU1fRlVMTF9PRkZMSU5FLmNtZC4KMy4gUHl0aG9uINGD0YHRgtCw0L3QsNCy0LvQuNCy0LDQtdGC0YHRjyDRgtC+0LvRjNC60L4g0L/RgNC4INC+0YLRgdGD0YLRgdGC0LLQuNC4IFB5dGhvbiAzLjEyKy4KNC4gUXVhbnR1bSDRg9GB0YLQsNC90LDQstC70LjQstCw0LXRgtGB0Y8g0LIgJUxPQ0FMQVBQREFUQSVcUXVhbnR1bUxvY2FsUHJvZHVjdGlvbi4KNS4g0KHQu9C10LTRg9C50YLQtSDRgNGD0YHRgdC60LjQvCDQv9C+0LTRgdC60LDQt9C60LDQvCDQvdCw0YHRgtGA0L7QudC60Lgg0Lgg0L/RgNC+0LLQtdGA0LrQuCBYTFNYLgoK0JDQtNGA0LXRgSDRg9GB0YLQsNC90L7QstGJ0LjQutCwIFB5dGhvbjogX19QWVRIT05fVVJMX18KU0hBLTI1NiDRg9GB0YLQsNC90L7QstGJ0LjQutCwIFB5dGhvbjogX19QWVRIT05fSEFTSF9fClNIQS0yNTYg0L/QsNC60LXRgtCwIFF1YW50dW06IF9fUVVBTlRVTV9IQVNIX18K"))
    $fullReadme = $fullReadme.Replace("__PYTHON_VERSION__", $pythonVersion).Replace("__PYTHON_URL__", $pythonUrl).Replace("__PYTHON_HASH__", $pythonActualSha256).Replace("__QUANTUM_HASH__", $quantumHash)
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
