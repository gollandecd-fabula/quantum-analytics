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
            throw "$Purpose must not be inside a cloud-synchronized directory: $full"
        }
    }
    $normalized = $full.Replace("/", "\")
    foreach ($token in @("\Dropbox\", "\Google Drive\", "\GoogleDrive\")) {
        if ($normalized.IndexOf($token, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            throw "$Purpose must not be inside a cloud-synchronized directory: $full"
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
    throw "Python 3.12 or newer was not found. Install Python 3.12+ and run START_QUANTUM.cmd again."
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
        Write-Warning "Ignored invalid JSON configuration: $Path"
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
    Write-Host "Existing invalid default config was preserved: $backup" -ForegroundColor Yellow
}

function Invoke-ConfigurationWizard {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Configurator
    )
    $configPath = Join-Path $Root "config\default-home-local.json"
    Backup-InvalidDefaultConfig -Path $configPath
    Write-Host "No ready HOME_LOCAL configuration was found." -ForegroundColor Yellow
    Write-Host "The safe ADMISSION_ONLY setup will now be created. Finance values will not be invented." -ForegroundColor Cyan
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
        throw "Configuration wizard did not create a ready configuration: $configPath"
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
        Write-Warning "The result was created but could not be parsed for automatic opening: $OutputPath"
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
                    Write-Warning "Output bundle path is outside the managed HOME_LOCAL root and will not be opened automatically."
                }
            }
        }
    }
    if (-not $opened) {
        Start-Process -FilePath "explorer.exe" -ArgumentList @((Split-Path -Parent $OutputPath))
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
    Assert-LocalPathSafety -Path $PackageRoot -Purpose "Extracted Quantum package"
    $TargetRoot = Resolve-FullPath -Path $TargetRoot
    Assert-LocalPathSafety -Path $TargetRoot -Purpose "HOME_LOCAL installation"
    $installer = Join-Path $PackageRoot "scripts\install_home_local.ps1"
    if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
        throw "Package installer is missing: $installer"
    }
    Write-Host "[1/4] Verifying package and installing HOME_LOCAL runtime..." -ForegroundColor Cyan
    & $installer -SourceRoot $PackageRoot -TargetRoot $TargetRoot
}

$TargetRoot = Resolve-FullPath -Path $TargetRoot -MustExist
Assert-LocalPathSafety -Path $TargetRoot -Purpose "HOME_LOCAL installation"
$importer = Join-Path $TargetRoot "scripts\import_source.ps1"
$configurator = Join-Path $TargetRoot "scripts\configure_home_local.ps1"
foreach ($required in @($importer, $configurator, (Join-Path $TargetRoot "src\quantum\pilot\windows_runner.py"))) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Installed HOME_LOCAL component is missing: $required"
    }
}
Resolve-PythonCommand | Out-Null
Write-Host "[2/4] Python and installed runtime are ready." -ForegroundColor Green

if ($InstallOnly) {
    Write-Host "Installation completed. Launch START_QUANTUM.cmd from: $TargetRoot" -ForegroundColor Green
    return
}

if (-not [string]::IsNullOrWhiteSpace($Config)) {
    $Config = Resolve-FullPath -Path $Config -MustExist
    if (-not (Test-ReadyConfig -Path $Config)) {
        throw "The supplied configuration is not ready: $Config"
    }
}
else {
    $Config = Find-ReadyConfig -Root $TargetRoot
    if (-not $Config) {
        Write-Host "[3/4] Creating first-run configuration..." -ForegroundColor Cyan
        $Config = Invoke-ConfigurationWizard -Root $TargetRoot -Configurator $configurator
    }
    else {
        Write-Host "[3/4] Ready configuration found: $Config" -ForegroundColor Green
    }
}

if ($NonInteractive -and [string]::IsNullOrWhiteSpace($File)) {
    throw "File is required in non-interactive mode."
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
        throw "Non-interactive mode requires explicit AuthorityAttested and SchemaReviewed switches."
    }
    $importArguments["NonInteractive"] = $true
}
if ($AuthorityAttested) { $importArguments["AuthorityAttested"] = $true }
if ($SchemaReviewed) { $importArguments["SchemaReviewed"] = $true }
if ($SkipDefenderScan) { $importArguments["SkipDefenderScan"] = $true }

Write-Host "[4/4] Select the authorized XLSX report." -ForegroundColor Cyan
if ($NonInteractive) {
    Write-Host "Explicit non-interactive attestations were supplied by the invoking operator." -ForegroundColor Green
}
else {
    Write-Host "Quantum will require AUTHORIZE and REVIEWED confirmations; launchers never attest on your behalf." -ForegroundColor Yellow
}
& $importer @importArguments
if (-not (Test-Path -LiteralPath $outputPath -PathType Leaf)) {
    throw "Quantum did not create the expected pilot result: $outputPath"
}

Write-Host "LOCAL PILOT RUN COMPLETED." -ForegroundColor Green
Write-Host "Result: $outputPath"
Write-Host "Installed launcher: $(Join-Path $TargetRoot 'START_QUANTUM.cmd')"
Open-PilotResult -Root $TargetRoot -OutputPath $outputPath
