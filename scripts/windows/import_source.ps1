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
        Write-Host "Defender scan skipped by explicit switch." -ForegroundColor Yellow
        return [ordered]@{
            scanner = "EXPLICIT_EQUIVALENT_SCAN_ATTESTED"
            outcome = "SKIPPED_BY_EXPLICIT_SWITCH"
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
        outcome = "CLEAN"
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
        throw "Configuration template is not ready. Run CONFIGURE_HOME_LOCAL.cmd first."
    }
    $modeProperty = $raw.PSObject.Properties["execution_mode"]
    $executionMode = if ($modeProperty) { [string]$modeProperty.Value } else { "FULL" }
    if ($executionMode -eq "ADMISSION_ONLY") {
        return
    }
    if ($executionMode -ne "FULL") {
        throw "Configuration has unsupported execution_mode: $executionMode"
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
    $receiptJson = $receipt | ConvertTo-Json -Compress
    $receiptBytes = [Text.Encoding]::UTF8.GetBytes($receiptJson)
    $receiptStream = [IO.MemoryStream]::new($receiptBytes)
    try {
        return [ordered]@{
            source_sha256 = $sourceHash
            evidence_sha256 = (Get-FileHash -InputStream $receiptStream -Algorithm SHA256).Hash.ToLowerInvariant()
            receipt = $receipt
        }
    }
    finally {
        $receiptStream.Dispose()
    }
}

function New-RuntimeConfig {
    param(
        [Parameter(Mandatory = $true)][string]$SourceConfig,
        [Parameter(Mandatory = $true)][string]$MalwareEvidenceSha256
    )
    $raw = Get-Content -LiteralPath $SourceConfig -Raw -Encoding UTF8 | ConvertFrom-Json
    $raw.malware_scan_evidence_sha256 = $MalwareEvidenceSha256
    return $raw
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
        throw "No ready Quantum configuration was found. Run CONFIGURE_HOME_LOCAL.cmd. Template: $template"
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

$scanResult = Invoke-DefenderScan -Path $File
$scanReceipt = New-ScanReceipt -SourcePath $File -ScanResult $scanResult
$reviewedFileHash = [string]$scanReceipt.source_sha256

Write-Host "Runtime profile: HOME_LOCAL" -ForegroundColor Cyan
Write-Host "Disk encryption is not required in HOME_LOCAL. The result will record the unencrypted-storage limitation." -ForegroundColor Yellow

Confirm-Literal -Expected "AUTHORIZE" -Prompt "Type AUTHORIZE to attest lawful authority to process this report" -AlreadyAttested ([bool]$AuthorityAttested)

$pythonCommand = Resolve-PythonCommand
$env:PYTHONPATH = Join-Path $projectRoot "src"
$runtimeConfig = Join-Path ([IO.Path]::GetTempPath()) ("quantum-runtime-config-{0}.json" -f [guid]::NewGuid().ToString("N"))
$previewOutput = Join-Path ([IO.Path]::GetTempPath()) ("quantum-schema-preview-{0}.json" -f [guid]::NewGuid().ToString("N"))

try {
    $runtimeConfigObject = New-RuntimeConfig -SourceConfig $Config -MalwareEvidenceSha256 ([string]$scanReceipt.evidence_sha256)
    $runtimeConfigJson = $runtimeConfigObject | ConvertTo-Json -Depth 16
    [IO.File]::WriteAllText($runtimeConfig, $runtimeConfigJson, ([System.Text.UTF8Encoding]::new($false)))

    $previewArguments = @()
    $previewArguments += $pythonCommand.Prefix
    $previewArguments += @(
        "-m", "quantum.pilot.windows_runner",
        "--file", $File,
        "--config", $runtimeConfig,
        "--storage-root", $StorageRoot,
        "--output", $previewOutput,
        "--home-local",
        "--discover-only",
        "--authority-attested"
    )
    if ($DebugErrors) {
        $previewArguments += "--debug-errors"
    }
    & $pythonCommand.Executable @previewArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Quantum schema discovery failed with exit code $LASTEXITCODE."
    }
    $preview = Get-Content -LiteralPath $previewOutput -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([string]$preview.file_sha256 -ne $reviewedFileHash) {
        throw "Schema preview file hash does not match the scanned file."
    }
    $headers = @($preview.schema.headers) -join " | "
    Write-Host "Discovered sheet: $($preview.schema.sheet_name)" -ForegroundColor Cyan
    Write-Host "Header row: $($preview.schema.header_row_index)"
    Write-Host "Columns: $($preview.schema.column_count)"
    Write-Host "Data rows: $($preview.schema.data_row_count)"
    Write-Host "Headers: $headers"
    Write-Host "File SHA-256: $reviewedFileHash"
    Confirm-Literal -Expected "REVIEWED" -Prompt "Review the displayed schema and type REVIEWED to continue" -AlreadyAttested ([bool]$SchemaReviewed)

    $currentFileHash = (Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($currentFileHash -ne $reviewedFileHash) {
        throw "Source file changed after schema review. Restart the import."
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
        "--expected-file-sha256", $reviewedFileHash,
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
    Remove-Item -LiteralPath $runtimeConfig -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $previewOutput -Force -ErrorAction SilentlyContinue
}

Write-Host "Import completed." -ForegroundColor Green
Write-Host "Report: $Output"
