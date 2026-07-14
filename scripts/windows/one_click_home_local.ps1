[CmdletBinding()]
param(
    [string]$PackageRoot,
    [string]$InstalledRoot,
    [string]$TargetRoot = (Join-Path $env:LOCALAPPDATA "QuantumLocalProduction"),
    [string]$File,
    [string]$Config,
    [string]$ReportingPeriodStart,
    [string]$ReportingPeriodEnd,
    [string]$RetentionDeadline,
    [string]$SourceInternalId,
    [switch]$NonInteractive,
    [switch]$AuthorityAttested,
    [switch]$SchemaReviewed,
    [switch]$SkipDefenderScan,
    [switch]$SkipInstall,
    [switch]$InstallOnly,
    [switch]$NoOpenResult
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

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

function Resolve-FullPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [switch]$MustExist
    )
    $expanded = [Environment]::ExpandEnvironmentVariables($Path)
    if ($MustExist) {
        return (Resolve-Path -LiteralPath $expanded).Path
    }
    return [IO.Path]::GetFullPath($expanded)
}

function Test-PathWithin {
    param(
        [Parameter(Mandatory = $true)][string]$Child,
        [Parameter(Mandatory = $true)][string]$Parent
    )
    $childFull = [IO.Path]::GetFullPath($Child).TrimEnd([char[]]"\/")
    $parentFull = [IO.Path]::GetFullPath($Parent).TrimEnd([char[]]"\/")
    if ($childFull.Equals($parentFull, [StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }
    return $childFull.StartsWith(
        $parentFull + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase
    )
}

function Assert-LocalPathSafety {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Purpose
    )
    $full = [IO.Path]::GetFullPath($Path)
    $cloudRoots = @(
        $env:OneDrive,
        $env:OneDriveConsumer,
        $env:OneDriveCommercial
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    foreach ($root in $cloudRoots) {
        if (Test-PathWithin -Child $full -Parent ([string]$root)) {
            throw (Get-QuantumRussianText -Encoded "ezB9INC90LUg0LTQvtC70LbQtdC9INC90LDRhdC+0LTQuNGC0YzRgdGPINCyINC/0LDQv9C60LUg0L7QsdC70LDRh9C90L7QuSDRgdC40L3RhdGA0L7QvdC40LfQsNGG0LjQuDogezF9" -Arguments @($Purpose, $full))
        }
    }
    $normalized = $full.Replace("/", "\")
    foreach ($token in @("\Dropbox\", "\Google Drive\", "\GoogleDrive\")) {
        if ($normalized.IndexOf($token, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            throw (Get-QuantumRussianText -Encoded "ezB9INC90LUg0LTQvtC70LbQtdC9INC90LDRhdC+0LTQuNGC0YzRgdGPINCyINC/0LDQv9C60LUg0L7QsdC70LDRh9C90L7QuSDRgdC40L3RhdGA0L7QvdC40LfQsNGG0LjQuDogezF9" -Arguments @($Purpose, $full))
        }
    }
}

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
    throw (Get-QuantumRussianText -Encoded "UHl0aG9uIDMuMTIg0LjQu9C4INC90L7QstC10LUg0L3QtSDQvdCw0LnQtNC10L0uINCj0YHRgtCw0L3QvtCy0LjRgtC1IFB5dGhvbiAzLjEyKyDQuCDRgdC90L7QstCwINC30LDQv9GD0YHRgtC40YLQtSBTVEFSVF9RVUFOVFVNLmNtZC4=")
}

function Test-ReadyConfig {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $false
    }
    try {
        $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        Write-Warning (Get-QuantumRussianText -Encoded "0J3QtdC60L7RgNGA0LXQutGC0L3QsNGPINC60L7QvdGE0LjQs9GD0YDQsNGG0LjRjyBKU09OINC/0YDQvtC/0YPRidC10L3QsDogezB9" -Arguments @($Path))
        return $false
    }
    $status = $raw.PSObject.Properties["configuration_status"]
    if (-not $status -or [string]$status.Value -ne "READY") {
        return $false
    }
    $modeProperty = $raw.PSObject.Properties["execution_mode"]
    $mode = if ($modeProperty) { [string]$modeProperty.Value } else { "FULL" }
    if ($mode -eq "ADMISSION_ONLY") {
        return $true
    }
    if ($mode -ne "FULL") {
        return $false
    }
    $finance = $raw.PSObject.Properties["finance_request"]
    if (-not $finance -or $null -eq $finance.Value) {
        return $false
    }
    $placeholder = $finance.Value.PSObject.Properties["replace_with_a_valid_versioned_finance_request"]
    return -not ($placeholder -and $placeholder.Value -eq $true)
}

function Find-ReadyConfig {
    param([Parameter(Mandatory = $true)][string]$Root)
    $candidates = @(
        (Join-Path $Root "config\production.local.json"),
        (Join-Path $Root "config\default-home-local.json"),
        (Join-Path $Root "config\default-production.json")
    )
    foreach ($candidate in $candidates) {
        if (Test-ReadyConfig -Path $candidate) {
            return [IO.Path]::GetFullPath($candidate)
        }
    }
    return $null
}

function Backup-InvalidDefaultConfig {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }
    if (Test-ReadyConfig -Path $Path) {
        return
    }
    $backup = "{0}.invalid_backup_{1}" -f $Path, (Get-Date -Format "yyyyMMdd_HHmmss")
    Copy-Item -LiteralPath $Path -Destination $backup -Force
    Write-Host (Get-QuantumRussianText -Encoded "0KHRg9GJ0LXRgdGC0LLRg9GO0YnQsNGPINC90LXQutC+0YDRgNC10LrRgtC90LDRjyDQutC+0L3RhNC40LPRg9GA0LDRhtC40Y8g0YHQvtGF0YDQsNC90LXQvdCwINCyINGA0LXQt9C10YDQstC90L7QuSDQutC+0L/QuNC4OiB7MH0=" -Arguments @($backup)) -ForegroundColor Yellow
}

function Invoke-ConfigurationWizard {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Configurator
    )
    $configPath = Join-Path $Root "config\default-home-local.json"
    Backup-InvalidDefaultConfig -Path $configPath
    Write-Host (Get-QuantumRussianText -Encoded "0JPQvtGC0L7QstCw0Y8g0LrQvtC90YTQuNCz0YPRgNCw0YbQuNGPIEhPTUVfTE9DQUwg0L3QtSDQvdCw0LnQtNC10L3QsC4=") -ForegroundColor Yellow
    Write-Host (Get-QuantumRussianText -Encoded "0JHRg9C00LXRgiDRgdC+0LfQtNCw0L3QsCDQsdC10LfQvtC/0LDRgdC90LDRjyDQutC+0L3RhNC40LPRg9GA0LDRhtC40Y8gQURNSVNTSU9OX09OTFkuINCk0LjQvdCw0L3RgdC+0LLRi9C1INC30L3QsNGH0LXQvdC40Y8g0L3QtSDQsdGD0LTRg9GCINCy0YvQtNGD0LzQsNC90Ysu") -ForegroundColor Cyan
    $arguments = @{ ConfigPath = $configPath }
    foreach ($pair in @(
        @("ReportingPeriodStart", $ReportingPeriodStart),
        @("ReportingPeriodEnd", $ReportingPeriodEnd),
        @("RetentionDeadline", $RetentionDeadline),
        @("SourceInternalId", $SourceInternalId)
    )) {
        if (-not [string]::IsNullOrWhiteSpace([string]$pair[1])) {
            $arguments[[string]$pair[0]] = [string]$pair[1]
        }
    }
    if ($NonInteractive) {
        $arguments["NonInteractive"] = $true
    }
    & $Configurator @arguments
    if (-not (Test-ReadyConfig -Path $configPath)) {
        throw (Get-QuantumRussianText -Encoded "0JzQsNGB0YLQtdGAINC60L7QvdGE0LjQs9GD0YDQsNGG0LjQuCDQvdC1INGB0L7Qt9C00LDQuyDQs9C+0YLQvtCy0YPRjiDQutC+0L3RhNC40LPRg9GA0LDRhtC40Y46IHswfQ==" -Arguments @($configPath))
    }
    return [IO.Path]::GetFullPath($configPath)
}

function Open-PilotResult {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$OutputPath
    )
    if ($NoOpenResult -or $NonInteractive) {
        return
    }
    $report = $null
    try {
        $report = Get-Content -LiteralPath $OutputPath -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        Write-Warning (Get-QuantumRussianText -Encoded "0KDQtdC30YPQu9GM0YLQsNGCINGB0L7Qt9C00LDQvSwg0L3QviDQtdCz0L4g0L3QtSDRg9C00LDQu9C+0YHRjCDQv9GA0L7Rh9C40YLQsNGC0Ywg0LTQu9GPINCw0LLRgtC+0LzQsNGC0LjRh9C10YHQutC+0LPQviDQvtGC0LrRgNGL0YLQuNGPOiB7MH0=" -Arguments @($OutputPath))
    }
    $opened = $false
    if ($report) {
        $bundleProperty = $report.PSObject.Properties["output_bundle"]
        if ($bundleProperty -and $null -ne $bundleProperty.Value) {
            $directoryProperty = $bundleProperty.Value.PSObject.Properties["directory"]
            if ($directoryProperty -and -not [string]::IsNullOrWhiteSpace([string]$directoryProperty.Value)) {
                $directory = [IO.Path]::GetFullPath([string]$directoryProperty.Value)
                if (Test-PathWithin -Child $directory -Parent $Root) {
                    $dashboard = Join-Path $directory "dashboard.html"
                    if (Test-Path -LiteralPath $dashboard -PathType Leaf) {
                        Start-Process -FilePath $dashboard
                        $opened = $true
                    }
                    if (Test-Path -LiteralPath $directory -PathType Container) {
                        Start-Process -FilePath "explorer.exe" -ArgumentList @($directory)
                        $opened = $true
                    }
                }
                else {
                    Write-Warning (Get-QuantumRussianText -Encoded "0J/Rg9GC0Ywg0Log0YDQtdC30YPQu9GM0YLQsNGC0LDQvCDQvdCw0YXQvtC00LjRgtGB0Y8g0LLQvdC1INGD0L/RgNCw0LLQu9GP0LXQvNC+0Lkg0L/QsNC/0LrQuCBIT01FX0xPQ0FMLCDQv9C+0Y3RgtC+0LzRgyDQsNCy0YLQvtC80LDRgtC40YfQtdGB0LrQvtC1INC+0YLQutGA0YvRgtC40LUg0LfQsNCx0LvQvtC60LjRgNC+0LLQsNC90L4u")
                }
            }
        }
    }
    if (-not $opened) {
        Start-Process -FilePath "explorer.exe" -ArgumentList @((Split-Path -Parent $OutputPath))
    }
}

if (-not $SkipInstall -and [string]::IsNullOrWhiteSpace($PackageRoot) -and [string]::IsNullOrWhiteSpace($InstalledRoot)) {
    $installedCandidate = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
    $packageInstaller = Join-Path $installedCandidate "scripts\install_home_local.ps1"
    $installedMarkers = @(
        (Join-Path $installedCandidate "START_QUANTUM.cmd"),
        (Join-Path $installedCandidate "scripts\import_source.ps1"),
        (Join-Path $installedCandidate "scripts\configure_home_local.ps1"),
        (Join-Path $installedCandidate "src\quantum\pilot\windows_runner.py")
    )
    $hasInstalledMarker = $false
    foreach ($marker in $installedMarkers) {
        if (Test-Path -LiteralPath $marker -PathType Leaf) {
            $hasInstalledMarker = $true
            break
        }
    }
    if ($hasInstalledMarker -and -not (Test-Path -LiteralPath $packageInstaller -PathType Leaf)) {
        $SkipInstall = $true
        $InstalledRoot = $installedCandidate
    }
}

if ($SkipInstall) {
    if ([string]::IsNullOrWhiteSpace($InstalledRoot)) {
        $InstalledRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
    }
    $TargetRoot = Resolve-FullPath -Path $InstalledRoot -MustExist
}
else {
    if ([string]::IsNullOrWhiteSpace($PackageRoot)) {
        $PackageRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
    }
    $PackageRoot = Resolve-FullPath -Path $PackageRoot -MustExist
    Assert-LocalPathSafety -Path $PackageRoot -Purpose (Get-QuantumRussianText -Encoded "0KDQsNGB0L/QsNC60L7QstCw0L3QvdGL0Lkg0L/QsNC60LXRgiBRdWFudHVt")
    $TargetRoot = Resolve-FullPath -Path $TargetRoot
    Assert-LocalPathSafety -Path $TargetRoot -Purpose (Get-QuantumRussianText -Encoded "0KPRgdGC0LDQvdC+0LLQutCwIEhPTUVfTE9DQUw=")
    $installer = Join-Path $PackageRoot "scripts\install_home_local.ps1"
    if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
        throw (Get-QuantumRussianText -Encoded "0KPRgdGC0LDQvdC+0LLRidC40Log0L/QsNC60LXRgtCwINC90LUg0L3QsNC50LTQtdC9OiB7MH0=" -Arguments @($installer))
    }
    Write-Host (Get-QuantumRussianText -Encoded "WzEvNF0g0J/RgNC+0LLQtdGA0LrQsCDQv9Cw0LrQtdGC0LAg0Lgg0YPRgdGC0LDQvdC+0LLQutCwINGB0YDQtdC00YsgSE9NRV9MT0NBTC4uLg==") -ForegroundColor Cyan
    & $installer -SourceRoot $PackageRoot -TargetRoot $TargetRoot
}

$TargetRoot = Resolve-FullPath -Path $TargetRoot -MustExist
Assert-LocalPathSafety -Path $TargetRoot -Purpose (Get-QuantumRussianText -Encoded "0KPRgdGC0LDQvdC+0LLQutCwIEhPTUVfTE9DQUw=")
$importer = Join-Path $TargetRoot "scripts\import_source.ps1"
$configurator = Join-Path $TargetRoot "scripts\configure_home_local.ps1"
foreach ($required in @($importer, $configurator, (Join-Path $TargetRoot "src\quantum\pilot\windows_runner.py"))) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw (Get-QuantumRussianText -Encoded "0J/QvtGB0LvQtSDRg9GB0YLQsNC90L7QstC60Lgg0L7RgtGB0YPRgtGB0YLQstGD0LXRgiDQutC+0LzQv9C+0L3QtdC90YIgSE9NRV9MT0NBTDogezB9" -Arguments @($required))
    }
}
Resolve-PythonCommand | Out-Null
Write-Host (Get-QuantumRussianText -Encoded "WzIvNF0gUHl0aG9uINC4INGD0YHRgtCw0L3QvtCy0LvQtdC90L3QsNGPINGB0YDQtdC00LAg0LPQvtGC0L7QstGLLg==") -ForegroundColor Green

if ($InstallOnly) {
    Write-Host (Get-QuantumRussianText -Encoded "0KPRgdGC0LDQvdC+0LLQutCwINC30LDQstC10YDRiNC10L3QsC4g0JfQsNC/0YPRgdC60LDQudGC0LUgU1RBUlRfUVVBTlRVTS5jbWQg0LjQtyDQv9Cw0L/QutC4OiB7MH0=" -Arguments @($TargetRoot)) -ForegroundColor Green
    return
}

if (-not [string]::IsNullOrWhiteSpace($Config)) {
    $Config = Resolve-FullPath -Path $Config -MustExist
    if (-not (Test-ReadyConfig -Path $Config)) {
        throw (Get-QuantumRussianText -Encoded "0J/QtdGA0LXQtNCw0L3QvdCw0Y8g0LrQvtC90YTQuNCz0YPRgNCw0YbQuNGPINC90LUg0LPQvtGC0L7QstCwOiB7MH0=" -Arguments @($Config))
    }

    $managedConfig = Join-Path $TargetRoot "config\default-home-local.json"
    if (-not (Test-PathWithin -Child $Config -Parent $TargetRoot)) {
        $managedConfigDirectory = Split-Path -Parent $managedConfig
        New-Item -ItemType Directory -Path $managedConfigDirectory -Force | Out-Null
        if (Test-Path -LiteralPath $managedConfig -PathType Leaf) {
            $sourceHash = (Get-FileHash -LiteralPath $Config -Algorithm SHA256).Hash
            $managedHash = (Get-FileHash -LiteralPath $managedConfig -Algorithm SHA256).Hash
            if ($sourceHash -ne $managedHash) {
                throw (Get-QuantumRussianText -Encoded "0J/QtdGA0LXQtNCw0L3QvdCw0Y8g0LrQvtC90YTQuNCz0YPRgNCw0YbQuNGPINC60L7QvdGE0LvQuNC60YLRg9C10YIg0YEg0YHRg9GJ0LXRgdGC0LLRg9GO0YnQtdC5INGD0L/RgNCw0LLQu9GP0LXQvNC+0Lkg0LrQvtC90YTQuNCz0YPRgNCw0YbQuNC10Lk6IHswfQ==" -Arguments @($managedConfig))
            }
        }
        else {
            $temporaryConfig = Join-Path $managedConfigDirectory (".default-home-local.{0}.tmp" -f [guid]::NewGuid().ToString("N"))
            try {
                Copy-Item -LiteralPath $Config -Destination $temporaryConfig -Force
                if (-not (Test-ReadyConfig -Path $temporaryConfig)) {
                    throw (Get-QuantumRussianText -Encoded "0KHQutC+0L/QuNGA0L7QstCw0L3QvdCw0Y8g0LrQvtC90YTQuNCz0YPRgNCw0YbQuNGPINC90LUg0LPQvtGC0L7QstCwOiB7MH0=" -Arguments @($temporaryConfig))
                }
                Move-Item -LiteralPath $temporaryConfig -Destination $managedConfig -Force
            }
            finally {
                Remove-Item -LiteralPath $temporaryConfig -Force -ErrorAction SilentlyContinue
            }
        }
        $Config = Resolve-FullPath -Path $managedConfig -MustExist
        Write-Host (Get-QuantumRussianText -Encoded "WzMvNF0g0J/QtdGA0LXQtNCw0L3QvdCw0Y8g0LrQvtC90YTQuNCz0YPRgNCw0YbQuNGPINGB0L7RhdGA0LDQvdC10L3QsCDQsiBIT01FX0xPQ0FMOiB7MH0=" -Arguments @($Config)) -ForegroundColor Green
    }
}
else {
    $Config = Find-ReadyConfig -Root $TargetRoot
    if (-not $Config) {
        Write-Host (Get-QuantumRussianText -Encoded "WzMvNF0g0KHQvtC30LTQsNC90LjQtSDQutC+0L3RhNC40LPRg9GA0LDRhtC40Lgg0L/QtdGA0LLQvtCz0L4g0LfQsNC/0YPRgdC60LAuLi4=") -ForegroundColor Cyan
        $Config = Invoke-ConfigurationWizard -Root $TargetRoot -Configurator $configurator
    }
    else {
        Write-Host (Get-QuantumRussianText -Encoded "WzMvNF0g0J3QsNC50LTQtdC90LAg0LPQvtGC0L7QstCw0Y8g0LrQvtC90YTQuNCz0YPRgNCw0YbQuNGPOiB7MH0=" -Arguments @($Config)) -ForegroundColor Green
    }
}

# Regression note: obsolete "$SkipInstall -and -not $NonInteractive" gate must not control desktop startup.
if (-not $NonInteractive -and [string]::IsNullOrWhiteSpace($File)) {
    $pythonCommand = Resolve-PythonCommand
    $pythonArguments = @()
    $pythonArguments += $pythonCommand.Prefix
    $pythonArguments += @(
        "-m",
        "quantum.application.desktop_center",
        "--root",
        $TargetRoot,
        "--config",
        $Config
    )
    $previousPythonPath = $env:PYTHONPATH
    try {
        $env:PYTHONPATH = Join-Path $TargetRoot "src"
        & $pythonCommand.Executable @pythonArguments
        $desktopExitCode = $LASTEXITCODE
    }
    finally {
        $env:PYTHONPATH = $previousPythonPath
    }
    if ($desktopExitCode -ne 0) {
        throw (Get-QuantumRussianText -Encoded "0KbQtdC90YLRgCDRgNC10YjQtdC90LjQuSBRdWFudHVtINC30LDQstC10YDRiNC40LvRgdGPINGBINC+0YjQuNCx0LrQvtC5LiDQmtC+0LQg0LLRi9GF0L7QtNCwOiB7MH0u" -Arguments @($desktopExitCode))
    }
    return
}

if ($NonInteractive -and [string]::IsNullOrWhiteSpace($File)) {
    throw (Get-QuantumRussianText -Encoded "0JIg0L3QtdC40L3RgtC10YDQsNC60YLQuNCy0L3QvtC8INGA0LXQttC40LzQtSDQvdC10L7QsdGF0L7QtNC40LzQviDRj9Cy0L3QviDRg9C60LDQt9Cw0YLRjCDRhNCw0LnQuy4=")
}
if (-not [string]::IsNullOrWhiteSpace($File)) {
    $File = Resolve-FullPath -Path $File -MustExist
}

$outputDirectory = Join-Path $TargetRoot "output"
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
$outputPath = Join-Path $outputDirectory ("pilot_{0}.json" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
$storageRoot = Join-Path $TargetRoot "data"

$importArguments = @{
    Config = $Config
    StorageRoot = $storageRoot
    Output = $outputPath
}
if ($File) { $importArguments["File"] = $File }
if ($NonInteractive) {
    if (-not $AuthorityAttested -or -not $SchemaReviewed) {
        throw (Get-QuantumRussianText -Encoded "0JIg0L3QtdC40L3RgtC10YDQsNC60YLQuNCy0L3QvtC8INGA0LXQttC40LzQtSDQvdC10L7QsdGF0L7QtNC40LzQviDRj9Cy0L3QviDQv9C+0LTRgtCy0LXRgNC00LjRgtGMIEF1dGhvcml0eUF0dGVzdGVkINC4IFNjaGVtYVJldmlld2VkLg==")
    }
    $importArguments["NonInteractive"] = $true
}
if ($AuthorityAttested) { $importArguments["AuthorityAttested"] = $true }
if ($SchemaReviewed) { $importArguments["SchemaReviewed"] = $true }
if ($SkipDefenderScan) { $importArguments["SkipDefenderScan"] = $true }

Write-Host (Get-QuantumRussianText -Encoded "WzQvNF0g0JLRi9Cx0LXRgNC40YLQtSDRgNCw0LfRgNC10YjRkdC90L3Ri9C5INC6INC+0LHRgNCw0LHQvtGC0LrQtSDQvtGC0YfRkdGCIFhMU1gu") -ForegroundColor Cyan
if ($NonInteractive) {
    Write-Host (Get-QuantumRussianText -Encoded "0J7Qv9C10YDQsNGC0L7RgCDRj9Cy0L3QviDQv9C10YDQtdC00LDQuyDQv9C+0LTRgtCy0LXRgNC20LTQtdC90LjRjyDQtNC70Y8g0L3QtdC40L3RgtC10YDQsNC60YLQuNCy0L3QvtCz0L4g0YDQtdC20LjQvNCwLg==") -ForegroundColor Green
}
else {
    Write-Host (Get-QuantumRussianText -Encoded "UXVhbnR1bSDQt9Cw0L/RgNC+0YHQuNGCINC/0L7QtNGC0LLQtdGA0LbQtNC10L3QuNGPIEFVVEhPUklaRSDQuCBSRVZJRVdFRDsg0L/RgNC+0LPRgNCw0LzQvNGLINC30LDQv9GD0YHQutCwINC90LjQutC+0LPQtNCwINC90LUg0L/QvtC00YLQstC10YDQttC00LDRjtGCINC40YUg0LfQsCDQv9C+0LvRjNC30L7QstCw0YLQtdC70Y8u") -ForegroundColor Yellow
}
& $importer @importArguments
if (-not (Test-Path -LiteralPath $outputPath -PathType Leaf)) {
    throw (Get-QuantumRussianText -Encoded "UXVhbnR1bSDQvdC1INGB0L7Qt9C00LDQuyDQvtC20LjQtNCw0LXQvNGL0Lkg0YDQtdC30YPQu9GM0YLQsNGCINC/0LjQu9C+0YLQvdC+0LPQviDQt9Cw0L/Rg9GB0LrQsDogezB9" -Arguments @($outputPath))
}

Write-Host (Get-QuantumRussianText -Encoded "0JvQntCa0JDQm9Cs0J3Qq9CZINCf0JjQm9Ce0KLQndCr0Jkg0JfQkNCf0KPQodCaINCX0JDQktCV0KDQqNCB0J0u") -ForegroundColor Green
Write-Host (Get-QuantumRussianText -Encoded "0KDQtdC30YPQu9GM0YLQsNGCOiB7MH0=" -Arguments @($outputPath))
Write-Host (Get-QuantumRussianText -Encoded "0KPRgdGC0LDQvdC+0LLQu9C10L3QvdCw0Y8g0L/RgNC+0LPRgNCw0LzQvNCwINC30LDQv9GD0YHQutCwOiB7MH0=" -Arguments @($(Join-Path $TargetRoot 'START_QUANTUM.cmd')))
Open-PilotResult -Root $TargetRoot -OutputPath $outputPath
