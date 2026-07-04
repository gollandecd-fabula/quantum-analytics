[CmdletBinding()]
param(
    [string]$File,
    [string]$Config,
    [string]$StorageRoot,
    [string]$Output,
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
        $runner = Join-Path $resolved "src\quantum\pilot\windows_runner.py"
        if (Test-Path -LiteralPath $runner -PathType Leaf) {
            return $resolved
        }
    }
    throw "Quantum project root was not found from launcher location: $PSScriptRoot"
}

function Select-XlsxFile {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = "Select authorized Wildberries XLSX report"
    $dialog.Filter = "Excel Workbook (*.xlsx)|*.xlsx"
    $dialog.Multiselect = $false
    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
        throw "Source selection cancelled."
    }
    return $dialog.FileName
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

function Confirm-Literal {
    param(
        [Parameter(Mandatory = $true)][string]$Expected,
        [Parameter(Mandatory = $true)][string]$Prompt,
        [Parameter(Mandatory = $true)][bool]$AlreadyAttested
    )
    if ($NonInteractive) {
        if (-not $AlreadyAttested) {
            throw "Non-interactive mode requires explicit $Expected attestation switch."
        }
        return
    }
    $answer = Read-Host $Prompt
    if ($answer -cne $Expected) {
        throw "Required attestation $Expected was not supplied."
    }
}

function Get-Sha256Hex {
    param([Parameter(Mandatory = $true)][string]$Text)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
        return ([BitConverter]::ToString($algorithm.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $algorithm.Dispose()
    }
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
    $sourceHash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    $scannedAt = [datetime]::UtcNow.ToString("o")
    if ($SkipDefenderScan) {
        Write-Host "Defender scan skipped by explicit switch after equivalent local scan." -ForegroundColor Yellow
        return [ordered]@{
            scanner = "EQUIVALENT_SCAN_ATTESTED"
            scanned_at = $scannedAt
            source_sha256 = $sourceHash
            result = "CLEAN_ATTESTED"
        }
    }
    $scanner = Resolve-DefenderScanner
    if (-not $scanner) {
        throw "Microsoft Defender command-line scanner was not found. Use -SkipDefenderScan only after an equivalent scan."
    }
    Write-Host "Scanning source file with Microsoft Defender..."
    & $scanner -Scan -ScanType 3 -File $Path | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Microsoft Defender scan failed or reported a threat. Exit code: $LASTEXITCODE"
    }
    return [ordered]@{
        scanner = $scanner
        scanned_at = $scannedAt
        source_sha256 = $sourceHash
        result = "CLEAN"
    }
}

function Test-UsableConfig {
    param([Parameter(Mandatory = $true)][string]$Path)
    try {
        $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        throw "Quantum configuration is not valid JSON: $Path"
    }
    $statusProperty = $raw.PSObject.Properties["configuration_status"]
    if ($statusProperty -and [string]$statusProperty.Value -eq "REQUIRES_USER_VALUES") {
        throw "Configuration template is not ready. Run CONFIGURE_HOME_LOCAL.cmd or provide a ready production config."
    }
    $modeProperty = $raw.PSObject.Properties["execution_mode"]
    $mode = if ($modeProperty) { [string]$modeProperty.Value } else { "FULL" }
    if ($mode -notin @("FULL", "ADMISSION_ONLY")) {
        throw "Unsupported execution_mode in Quantum configuration: $mode"
    }
    if ($mode -eq "ADMISSION_ONLY") {
        return
    }
    $financeProperty = $raw.PSObject.Properties["finance_request"]
    if (-not $financeProperty -or $null -eq $financeProperty.Value) {
        throw "FULL configuration has no finance_request object: $Path"
    }
    $placeholderProperty = $financeProperty.Value.PSObject.Properties["replace_with_a_valid_versioned_finance_request"]
    if ($placeholderProperty -and $placeholderProperty.Value -eq $true) {
        throw "FULL configuration still contains a finance_request placeholder: $Path"
    }
}

$projectRoot = Resolve-ProjectRoot

if ([string]::IsNullOrWhiteSpace($File)) {
    $File = Select-XlsxFile
}
$File = (Resolve-Path -LiteralPath $File).Path
if ([IO.Path]::GetExtension($File) -ine ".xlsx") {
    throw "Only .xlsx source files are accepted."
}

if ([string]::IsNullOrWhiteSpace($Config)) {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "QuantumLocalProduction\config\production.local.json"),
        (Join-Path $env:LOCALAPPDATA "QuantumLocalProduction\config\default-home-local.json"),
        (Join-Path $env:LOCALAPPDATA "QuantumLocalProduction\config\default-production.json")
    )
    $Config = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $Config) {
        $template = Join-Path $projectRoot "config\home-local.template.json"
        throw "No ready Quantum configuration was found. Run CONFIGURE_HOME_LOCAL.cmd, then retry the import."
    }
}
$Config = (Resolve-Path -LiteralPath $Config).Path
Test-UsableConfig -Path $Config

if ([string]::IsNullOrWhiteSpace($StorageRoot)) {
    $StorageRoot = Join-Path $env:LOCALAPPDATA "QuantumLocalProduction\data"
}
if ([string]::IsNullOrWhiteSpace($Output)) {
    $outputDirectory = Join-Path $env:LOCALAPPDATA "QuantumLocalProduction\output"
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
    $Output = Join-Path $outputDirectory ("import_{0}.json" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
}

$scanReceipt = Invoke-DefenderScan -Path $File
$scanReceiptJson = $scanReceipt | ConvertTo-Json -Compress
$scanReceiptHash = Get-Sha256Hex -Text $scanReceiptJson
$runtimeConfig = Join-Path ([IO.Path]::GetTempPath()) ("quantum_config_{0}.json" -f [guid]::NewGuid().ToString("N"))
try {
    $runtimeConfigObject = Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
    $runtimeConfigObject.malware_scan_evidence_sha256 = $scanReceiptHash
    if (-not $runtimeConfigObject.PSObject.Properties["attestations"] -or $null -eq $runtimeConfigObject.attestations) {
        throw "Quantum configuration has no attestations object."
    }
    $runtimeConfigObject.attestations.malware_scan_clean = $true
    $runtimeConfigObject | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath $runtimeConfig -Encoding UTF8
}
catch {
    Remove-Item -LiteralPath $runtimeConfig -Force -ErrorAction SilentlyContinue
    throw
}

Write-Host "Runtime profile: HOME_LOCAL" -ForegroundColor Cyan
Write-Host "Disk encryption is not required in HOME_LOCAL. The result will record the unencrypted-storage limitation." -ForegroundColor Yellow

Confirm-Literal -Expected "AUTHORIZE" -Prompt "Type AUTHORIZE to attest lawful authority to process this report" -AlreadyAttested ([bool]$AuthorityAttested)

$pythonCommand = Resolve-PythonCommand
$env:PYTHONPATH = Join-Path $projectRoot "src"
$sourceHashBefore = [string]$scanReceipt.source_sha256
$discoveryOutput = Join-Path ([IO.Path]::GetTempPath()) ("quantum_schema_{0}.json" -f [guid]::NewGuid().ToString("N"))

try {
    $discoveryArguments = @()
    $discoveryArguments += $pythonCommand.Prefix
    $discoveryArguments += @(
        "-m", "quantum.pilot.windows_runner",
        "--file", $File,
        "--config", $runtimeConfig,
        "--storage-root", $StorageRoot,
        "--output", $discoveryOutput,
        "--home-local",
        "--discover-only",
        "--authority-attested"
    )
    if ($DebugErrors) {
        $discoveryArguments += "--debug-errors"
    }

    & $pythonCommand.Executable @discoveryArguments
    $discoveryExitCode = $LASTEXITCODE
    if ($discoveryExitCode -ne 0) {
        throw "Quantum schema discovery failed with exit code $discoveryExitCode."
    }
    $preview = Get-Content -LiteralPath $discoveryOutput -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([string]$preview.status -ne "SCHEMA_DISCOVERED") {
        throw "Quantum schema discovery returned an unexpected status."
    }
    if ([string]$preview.file_sha256 -ne $sourceHashBefore) {
        throw "Schema preview file hash does not match the selected source."
    }

    $schema = $preview.schema_discovery
    Write-Host ""
    Write-Host "Discovered XLSX schema:" -ForegroundColor Cyan
    Write-Host ("  File SHA-256: {0}" -f $preview.file_sha256)
    Write-Host ("  Sheet: {0} of {1}" -f $schema.sheet_name, $schema.sheet_count)
    Write-Host ("  Header row: {0}" -f $schema.header_row_index)
    Write-Host ("  Columns: {0}; data rows: {1}; formulas: {2}" -f $schema.column_count, $schema.data_row_count, $schema.formula_count)
    $displayHeaders = @(
        $schema.headers | Select-Object -First 30 | ForEach-Object {
            ([string]$_ -replace "[\r\n\t]", " ").Trim()
        }
    )
    Write-Host ("  Headers: {0}" -f ($displayHeaders -join " | "))
    if ([int]$schema.column_count -gt $displayHeaders.Count) {
        Write-Host ("  ... plus {0} additional columns" -f ([int]$schema.column_count - $displayHeaders.Count))
    }
    Write-Host ""

    Confirm-Literal -Expected "REVIEWED" -Prompt "Type REVIEWED only if the displayed sheet and header row are correct" -AlreadyAttested ([bool]$SchemaReviewed)

    $sourceHashAfter = (Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($sourceHashAfter -ne $sourceHashBefore) {
        throw "Selected XLSX changed after schema review. Select and review it again."
    }

    $arguments = @()
    $arguments += $pythonCommand.Prefix
    $arguments += @(
        "-m", "quantum.pilot.windows_runner",
        "--file", $File,
        "--config", $runtimeConfig,
        "--storage-root", $StorageRoot,
        "--output", $Output,
        "--home-local",
        "--discover-schema",
        "--authority-attested",
        "--schema-reviewed"
    )
    if ($DebugErrors) {
        $arguments += "--debug-errors"
    }

    & $pythonCommand.Executable @arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "Quantum import failed with exit code $exitCode."
    }
}
finally {
    Remove-Item -LiteralPath $discoveryOutput -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $runtimeConfig -Force -ErrorAction SilentlyContinue
}

Write-Host "Import completed." -ForegroundColor Green
Write-Host "Report: $Output"
