[CmdletBinding()]
param(
    [string]$File,
    [string]$Config,
    [string]$StorageRoot,
    [string]$OutputDirectory,
    [switch]$NonInteractive,
    [switch]$AuthorityAttested,
    [switch]$SchemaReviewed,
    [switch]$SkipDefenderScan,
    [switch]$DebugErrors
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-ProjectRoot {
    $candidates = @(
        (Join-Path $PSScriptRoot ".."),
        (Join-Path $PSScriptRoot "..\..")
    )
    foreach ($candidate in $candidates) {
        try {
            $resolved = (Resolve-Path -LiteralPath $candidate).Path
        }
        catch {
            continue
        }
        $runner = Join-Path $resolved "src\quantum\pilot\any_file_runner.py"
        if (Test-Path -LiteralPath $runner -PathType Leaf) {
            return $resolved
        }
    }
    throw "Quantum project root was not found from launcher location: $PSScriptRoot"
}

function Select-SourceFiles {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = "Select one or more files for Quantum"
    $dialog.Filter = "All files (*.*)|*.*"
    $dialog.Multiselect = $true
    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
        throw "Source selection cancelled."
    }
    return @($dialog.FileNames)
}

function Confirm-Batch {
    param([Parameter(Mandatory = $true)][string[]]$Paths)
    if ($NonInteractive) {
        if (-not $AuthorityAttested -or -not $SchemaReviewed) {
            throw "Non-interactive mode requires -AuthorityAttested and -SchemaReviewed."
        }
        return
    }
    Add-Type -AssemblyName System.Windows.Forms
    $message = @"
Selected files: $($Paths.Count)

By clicking Yes you confirm:
1. you have lawful authority to process these files;
2. Quantum may automatically inspect their structure;
3. files remain on this computer in HOME_LOCAL mode.

Continue?
"@
    $answer = [System.Windows.Forms.MessageBox]::Show(
        $message,
        "Quantum universal import",
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Question,
        [System.Windows.Forms.MessageBoxDefaultButton]::Button2
    )
    if ($answer -ne [System.Windows.Forms.DialogResult]::Yes) {
        throw "User cancelled authority and schema confirmation."
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
    throw "Python 3.12 or newer was not found."
}

function Resolve-DefenderScanner {
    $direct = Join-Path $env:ProgramFiles "Windows Defender\MpCmdRun.exe"
    if (Test-Path -LiteralPath $direct -PathType Leaf) {
        return $direct
    }
    $platformRoot = Join-Path $env:ProgramData "Microsoft\Windows Defender\Platform"
    if (Test-Path -LiteralPath $platformRoot -PathType Container) {
        $scanner = Get-ChildItem -LiteralPath $platformRoot -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName "MpCmdRun.exe" } |
            Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
            Select-Object -First 1
        if ($scanner) {
            return $scanner
        }
    }
    return $null
}

function Invoke-DefenderScan {
    param([Parameter(Mandatory = $true)][string]$Path)
    if ($SkipDefenderScan) {
        return [ordered]@{
            scanner = "EXPLICIT_EQUIVALENT_SCAN_ATTESTED"
            outcome = "SKIPPED_BY_EXPLICIT_SWITCH"
        }
    }
    $scanner = Resolve-DefenderScanner
    if (-not $scanner) {
        throw "Microsoft Defender scanner was not found. Use -SkipDefenderScan only after an equivalent scan."
    }
    Write-Host "Scanning with Microsoft Defender: $Path"
    & $scanner -Scan -ScanType 3 -File $Path | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Microsoft Defender scan failed or reported a threat. Exit code: $LASTEXITCODE"
    }
    return [ordered]@{
        scanner = $scanner
        outcome = "CLEAN"
    }
}

function New-ScanReceipt {
    param(
        [Parameter(Mandatory = $true)][string]$SourcePath,
        [Parameter(Mandatory = $true)]$ScanResult
    )
    $sourceHash = (Get-FileHash -LiteralPath $SourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $receipt = [ordered]@{
        receipt_version = 1
        source_sha256 = $sourceHash
        scanner = [string]$ScanResult.scanner
        outcome = [string]$ScanResult.outcome
        created_at_utc = [DateTime]::UtcNow.ToString("o")
    }
    $json = $receipt | ConvertTo-Json -Compress
    $bytes = [Text.Encoding]::UTF8.GetBytes($json)
    $stream = [IO.MemoryStream]::new($bytes)
    try {
        return [ordered]@{
            source_sha256 = $sourceHash
            evidence_sha256 = (Get-FileHash -InputStream $stream -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
    finally {
        $stream.Dispose()
    }
}

function Resolve-Config {
    param([string]$Requested, [string]$ProjectRoot)
    if (-not [string]::IsNullOrWhiteSpace($Requested)) {
        return (Resolve-Path -LiteralPath $Requested).Path
    }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "QuantumLocalProduction\config\production.local.json"),
        (Join-Path $env:LOCALAPPDATA "QuantumLocalProduction\config\default-home-local.json"),
        (Join-Path $env:LOCALAPPDATA "QuantumLocalProduction\config\default-production.json")
    )
    $resolved = $candidates |
        Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
        Select-Object -First 1
    if (-not $resolved) {
        $template = Join-Path $ProjectRoot "config\home-local.template.json"
        throw "No ready Quantum configuration was found. Run CONFIGURE_HOME_LOCAL.cmd. Template: $template"
    }
    return (Resolve-Path -LiteralPath $resolved).Path
}

function Assert-UsableConfig {
    param([Parameter(Mandatory = $true)][string]$Path)
    try {
        $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        throw "Quantum configuration is not valid JSON: $Path"
    }
    $status = $raw.PSObject.Properties["configuration_status"]
    if ($status -and [string]$status.Value -eq "REQUIRES_USER_VALUES") {
        throw "Configuration template is not ready. Run CONFIGURE_HOME_LOCAL.cmd."
    }
}

$projectRoot = Resolve-ProjectRoot
$pythonCommand = Resolve-PythonCommand
$env:PYTHONPATH = Join-Path $projectRoot "src"
$Config = Resolve-Config -Requested $Config -ProjectRoot $projectRoot
Assert-UsableConfig -Path $Config

if ([string]::IsNullOrWhiteSpace($StorageRoot)) {
    $StorageRoot = Join-Path $env:LOCALAPPDATA "QuantumLocalProduction\data"
}
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $env:LOCALAPPDATA "QuantumLocalProduction\output"
}
New-Item -ItemType Directory -Path $StorageRoot -Force | Out-Null
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

$files = if ([string]::IsNullOrWhiteSpace($File)) {
    Select-SourceFiles
}
else {
    @((Resolve-Path -LiteralPath $File).Path)
}
$files = @($files | ForEach-Object { (Resolve-Path -LiteralPath $_).Path })
Confirm-Batch -Paths $files

$accepted = 0
$quarantined = 0
$errors = 0
$index = 0

foreach ($source in $files) {
    $index += 1
    $runtimeConfig = Join-Path ([IO.Path]::GetTempPath()) ("quantum-any-config-{0}.json" -f [guid]::NewGuid().ToString("N"))
    try {
        $scan = Invoke-DefenderScan -Path $source
        $receipt = New-ScanReceipt -SourcePath $source -ScanResult $scan
        $configObject = Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
        $configObject.malware_scan_evidence_sha256 = [string]$receipt.evidence_sha256
        $configJson = $configObject | ConvertTo-Json -Depth 16
        [IO.File]::WriteAllText(
            $runtimeConfig,
            $configJson,
            ([System.Text.UTF8Encoding]::new($false))
        )

        $stamp = Get-Date -Format "yyyyMMdd_HHmmss_fff"
        $output = Join-Path $OutputDirectory ("intake_{0}_{1}.json" -f $stamp, $index)
        $arguments = @()
        $arguments += $pythonCommand.Prefix
        $arguments += @(
            "-m", "quantum.pilot.any_file_runner",
            "--file", $source,
            "--config", $runtimeConfig,
            "--storage-root", $StorageRoot,
            "--output", $output,
            "--home-local",
            "--authority-attested",
            "--schema-reviewed",
            "--expected-file-sha256", ([string]$receipt.source_sha256)
        )
        if ($DebugErrors) {
            $arguments += "--debug-errors"
        }

        Write-Host ""
        Write-Host "Importing: $source" -ForegroundColor Cyan
        & $pythonCommand.Executable @arguments
        $exitCode = $LASTEXITCODE

        if (-not (Test-Path -LiteralPath $output -PathType Leaf)) {
            $errors += 1
            Write-Host "No result file was produced." -ForegroundColor Red
            continue
        }
        $report = Get-Content -LiteralPath $output -Raw -Encoding UTF8 | ConvertFrom-Json
        $status = [string]$report.status
        Write-Host "Status: $status" -ForegroundColor Cyan
        Write-Host "Result: $output"
        if ($status.StartsWith("ACCEPTED_")) {
            $accepted += 1
        }
        elseif ($status.StartsWith("QUARANTINED_")) {
            $quarantined += 1
        }
        else {
            $errors += 1
        }
        if ($exitCode -ne 0 -and -not $status.StartsWith("QUARANTINED_")) {
            $errors += 1
        }
    }
    catch {
        $errors += 1
        Write-Host "Import error for $source`: $($_.Exception.Message)" -ForegroundColor Red
    }
    finally {
        Remove-Item -LiteralPath $runtimeConfig -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "Quantum universal import finished." -ForegroundColor Green
Write-Host "Accepted: $accepted"
Write-Host "Quarantined: $quarantined"
Write-Host "Errors: $errors"

if ($errors -gt 0 -or $quarantined -gt 0) {
    exit 2
}
exit 0
