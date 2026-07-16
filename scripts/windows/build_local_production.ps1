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
title Quantum
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

$readme = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("UVVBTlRVTSBIT01FX0xPQ0FMINCU0JvQryBXSU5ET1dTIOKAlCDQm9Ce0JrQkNCb0KzQndCr0Jkg0KbQldCd0KLQoCDQoNCV0KjQldCd0JjQmQoK0J7QkdCb0JDQodCi0Kwg0JLQldCg0KHQmNCYCi0g0KLQtdC60YPRidCw0Y8g0LvQvtC60LDQu9GM0L3QsNGPINCy0LXRgNGB0LjRjyDQv9C+0LTQtNC10YDQttC40LLQsNC10YIg0YLQvtC70YzQutC+IFdJTERCRVJSSUVTLgotINCf0L7QtNC00LXRgNC20LrQsCBPem9uINC+0YLQu9C+0LbQtdC90LAg0Lgg0L3QtSDQstC60LvRjtGH0LXQvdCwINCyINC/0L7Qu9GM0LfQvtCy0LDRgtC10LvRjNGB0LrQuNC5INC/0LDQutC10YIuCi0g0JfQsNC/0LjRgdGMINC90LAg0LzQsNGA0LrQtdGC0L/Qu9C10LnRgSDQvtGC0LrQu9GO0YfQtdC90LAuCgrQntCh0J3QntCS0J3QntCZINCX0JDQn9Cj0KHQmgoxLiDQoNCw0YHQv9Cw0LrRg9C50YLQtSBaSVAg0LIg0L7QsdGL0YfQvdGD0Y4g0LvQvtC60LDQu9GM0L3Rg9GOINC/0LDQv9C60YMg0LLQvdC1IE9uZURyaXZlLCBEcm9wYm94LCBHb29nbGUgRHJpdmUg0Lgg0LTRgNGD0LPQuNGFINGB0LjQvdGF0YDQvtC90LjQt9C40YDRg9C10LzRi9GFINC60LDRgtCw0LvQvtCz0L7Qsi4KMi4g0JTQstCw0LbQtNGLINC90LDQttC80LjRgtC1IFNUQVJUX1FVQU5UVU0uY21kLgozLiDQn9GA0Lgg0L/QtdGA0LLQvtC8INC30LDQv9GD0YHQutC1IFF1YW50dW0g0L/RgNC+0LLQtdGA0LjRgiDQuCDRg9GB0YLQsNC90L7QstC40YIg0L/QsNC60LXRgiwg0L/RgNC4INC90LXQvtCx0YXQvtC00LjQvNC+0YHRgtC4INGB0L7Qt9C00LDRgdGCINCx0LXQt9C+0L/QsNGB0L3Rg9GOINC60L7QvdGE0LjQs9GD0YDQsNGG0LjRjiBBRE1JU1NJT05fT05MWSwg0L/RgNC10LTQu9C+0LbQuNGCINCy0YvQsdGA0LDRgtGMIFhMU1gg0Lgg0L/RgNC+0LTQvtC70LbQuNGCINC+0LHRgNCw0LHQvtGC0LrRgy4KNC4g0JLQstC10LTQuNGC0LUgQVVUSE9SSVpFLCDRh9GC0L7QsdGLINC/0L7QtNGC0LLQtdGA0LTQuNGC0Ywg0LfQsNC60L7QvdC90YvQtSDQv9C+0LvQvdC+0LzQvtGH0LjRjywg0LfQsNGC0LXQvCDQv9GA0L7QstC10YDRjNGC0LUg0YHRhdC10LzRgyDQuCDQvtGC0YfRkdGC0L3Ri9C5INC/0LXRgNC40L7QtCDQuCDQstCy0LXQtNC40YLQtSBSRVZJRVdFRC4KNS4g0J/QvtGB0LvQtSDRg9GB0L/QtdGI0L3QvtCz0L4g0LfQsNC/0YPRgdC60LAgUXVhbnR1bSDQvtGC0LrRgNC+0LXRgiDQu9C+0LrQsNC70YzQvdGL0Lkg0KbQtdC90YLRgCDRgNC10YjQtdC90LjQuSDQuCDQv9Cw0L/QutGDINGA0LXQt9GD0LvRjNGC0LDRgtC+0LIuCgrQkdCV0JfQntCf0JDQodCd0J7QodCi0KwKLSDQn9GA0L7Qs9GA0LDQvNC80Ysg0LfQsNC/0YPRgdC60LAg0L3QuNC60L7Qs9C00LAg0L3QtSDQv9C+0LTRgtCy0LXRgNC20LTQsNGO0YIgQVVUSE9SSVpFINC40LvQuCBSRVZJRVdFRCDQt9CwINC/0L7Qu9GM0LfQvtCy0LDRgtC10LvRjy4KLSBNaWNyb3NvZnQgRGVmZW5kZXIg0L7RgdGC0LDRkdGC0YHRjyDQstC60LvRjtGH0ZHQvdC90YvQvCDQv9GA0Lgg0L7QsdGL0YfQvdC+0Lwg0LjRgdC/0L7Qu9GM0LfQvtCy0LDQvdC40LguCi0g0JTQviDQuNC30LzQtdC90LXQvdC40Y8g0YPRgdGC0LDQvdC+0LLQutC4INC60LDQttC00YvQuSDRhNCw0LnQuyDQv9GA0L7QstC10YDRj9C10YLRgdGPINC/0L4gbWFuaWZlc3Quc2hhMjU2Lmpzb24uCi0g0KHRg9GJ0LXRgdGC0LLRg9GO0YnQuNC1INC/0LDQv9C60LggY29uZmlnLCBkYXRhINC4IG91dHB1dCDRgdC+0YXRgNCw0L3Rj9GO0YLRgdGPLgotINCh0LXQsdC10YHRgtC+0LjQvNC+0YHRgtGMLCDQvdCw0LvQvtCzINC4INC/0YDQvtGH0LjQtSDRgNCw0YHRhdC+0LTRiyDQvdC1INCy0YvQtNGD0LzRi9Cy0LDRjtGC0YHRjy4g0J/QvtC70L3Ri9C5INGE0LjQvdCw0L3RgdC+0LLRi9C5INGA0LDRgdGH0ZHRgiDRgtGA0LXQsdGD0LXRgiDRj9Cy0L3QvtCz0L4g0L/RgNC+0LLQtdGA0LXQvdC90L7Qs9C+IGZpbmFuY2VfcmVxdWVzdC4KLSDQl9Cw0L/QuNGB0Ywg0L3QsCDQvNCw0YDQutC10YLQv9C70LXQudGBLCDQtNC+0YHRgtGD0L8g0LjQtyDQu9C+0LrQsNC70YzQvdC+0Lkg0YHQtdGC0Lgg0Lgg0L/RgNC+0LjQt9Cy0L7QtNGB0YLQstC10L3QvdGL0Lkg0LLRi9C/0YPRgdC6INC+0YLQutC70Y7Rh9C10L3Riy4KLSDQoNC10LDQu9GM0L3Ri9C1INC+0YLRh9GR0YLRiywg0LrQvtC90YTQuNCz0YPRgNCw0YbQuNC4INC4INGA0LXQt9GD0LvRjNGC0LDRgtGLINC90LXQu9GM0LfRjyDQt9Cw0LPRgNGD0LbQsNGC0Ywg0LIgR2l0SHViINC40LvQuCDQvtCx0LvQsNGH0L3Qvi3RgdC40L3RhdGA0L7QvdC40LfQuNGA0YPQtdC80YvQtSDQv9Cw0L/QutC4LgoK0JLQntCh0KHQotCQ0J3QntCS0JvQldCd0JjQlQotIElOU1RBTExfSE9NRV9MT0NBTC5jbWQg4oCUINGD0YHRgtCw0L3QvtCy0LrQsCDQuNC70Lgg0LLQvtGB0YHRgtCw0L3QvtCy0LvQtdC90LjQtS4KLSBDT05GSUdVUkVfSE9NRV9MT0NBTC5jbWQg4oCUINGB0L7Qt9C00LDQvdC40LUg0LrQvtC90YTQuNCz0YPRgNCw0YbQuNC4LgotIElNUE9SVF9YTFNYLmNtZCDigJQg0LjQvNC/0L7RgNGCINGBINGP0LLQvdGL0LzQuCDQv9C+0LTRgtCy0LXRgNC20LTQtdC90LjRj9C80LggQVVUSE9SSVpFINC4IFJFVklFV0VELgoK0KPQodCi0JDQndCe0JLQmtCQINCf0J4g0KPQnNCe0JvQp9CQ0J3QmNCuCiVMT0NBTEFQUERBVEElXFF1YW50dW1Mb2NhbFByb2R1Y3Rpb24K0J/RgNC4INGA0LDQt9GA0LXRiNC10L3QuNC4IFdpbmRvd3Mg0YHQvtC30LTQsNGR0YLRgdGPINGP0YDQu9GL0LogwqvQptC10L3RgtGAINGA0LXRiNC10L3QuNC5IFF1YW50dW3Cuy4K"))
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
