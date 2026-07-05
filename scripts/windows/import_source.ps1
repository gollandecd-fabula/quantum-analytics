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
        $gateway = Join-Path $resolved "src\quantum\pilot\universal_import.py"
        $xlsxHelper = Join-Path $resolved "src\quantum\pilot\import_xlsx_source.ps1"
        if (
            (Test-Path -LiteralPath $gateway -PathType Leaf) -and
            (Test-Path -LiteralPath $xlsxHelper -PathType Leaf)
        ) {
            return $resolved
        }
    }
    throw "Quantum project root was not found from launcher location: $PSScriptRoot"
}

function Select-SourceFile {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = "Select an authorized local file for Quantum"
    $dialog.Filter = "All files (*.*)|*.*"
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
    if ($AlreadyAttested) {
        return
    }
    if ($NonInteractive) {
        throw "Non-interactive mode requires explicit $Expected attestation switch."
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
        }
    }
    finally {
        $receiptStream.Dispose()
    }
}

$projectRoot = Resolve-ProjectRoot
$hashCompat = Join-Path $projectRoot "src\quantum\pilot\hash_compat.ps1"
if (-not (Test-Path -LiteralPath $hashCompat -PathType Leaf)) {
    throw "Quantum SHA-256 compatibility shim was not found: $hashCompat"
}
. $hashCompat

if ([string]::IsNullOrWhiteSpace($File)) {
    $File = Select-SourceFile
}
$File = (Resolve-Path -LiteralPath $File).Path
if ([string]::IsNullOrWhiteSpace($StorageRoot)) {
    $StorageRoot = Join-Path $env:LOCALAPPDATA "QuantumLocalProduction\data"
}
if ([string]::IsNullOrWhiteSpace($Output)) {
    $outputDirectory = Join-Path $env:LOCALAPPDATA "QuantumLocalProduction\output"
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
    $Output = Join-Path $outputDirectory ("import_{0}.json" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
}
$Output = [IO.Path]::GetFullPath($Output)
$outputDirectory = Split-Path -Parent $Output
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
$gatewayOutput = Join-Path $outputDirectory (".quantum-intake-{0}.json" -f [guid]::NewGuid().ToString("N"))

$scanResult = Invoke-DefenderScan -Path $File
$scanReceipt = New-ScanReceipt -SourcePath $File -ScanResult $scanResult
$reviewedFileHash = [string]$scanReceipt.source_sha256
Confirm-Literal -Expected "AUTHORIZE" -Prompt "Type AUTHORIZE to attest lawful authority to process this file" -AlreadyAttested ([bool]$AuthorityAttested)

$pythonCommand = Resolve-PythonCommand
$env:PYTHONPATH = Join-Path $projectRoot "src"
$finalExitCode = 0
try {
    $arguments = @()
    $arguments += $pythonCommand.Prefix
    $arguments += @(
        "-c", "from quantum.pilot.universal_import import main; raise SystemExit(main())",
        "--file", $File,
        "--storage-root", $StorageRoot,
        "--output", $gatewayOutput,
        "--authority-attested",
        "--malware-scan-evidence-sha256", ([string]$scanReceipt.evidence_sha256),
        "--malware-scan-outcome", ([string]$scanResult.outcome)
    )
    & $pythonCommand.Executable @arguments
    $gatewayExitCode = $LASTEXITCODE
    if (-not (Test-Path -LiteralPath $gatewayOutput -PathType Leaf)) {
        throw "Universal intake did not produce a report: $gatewayOutput"
    }
    $report = Get-Content -LiteralPath $gatewayOutput -Raw -Encoding UTF8 | ConvertFrom-Json
    $status = [string]$report.status
    $hashProperty = $report.PSObject.Properties["file_sha256"]
    if (
        $hashProperty -and
        -not [string]::IsNullOrWhiteSpace([string]$hashProperty.Value) -and
        [string]$hashProperty.Value -ne $reviewedFileHash
    ) {
        throw "Universal intake file hash does not match the scanned file."
    }

    if ($status -eq "ROUTE_XLSX") {
        if ($gatewayExitCode -ne 0) {
            throw "Universal intake routed XLSX with non-zero exit code $gatewayExitCode."
        }
        $helper = Join-Path $projectRoot "src\quantum\pilot\import_xlsx_source.ps1"
        $helperArguments = @{
            File = $File
            StorageRoot = $StorageRoot
            Output = $Output
            AuthorityAttested = $true
            SchemaReviewed = [bool]$SchemaReviewed
            PreScannedEvidenceSha256 = [string]$scanReceipt.evidence_sha256
            PreScannedOutcome = [string]$scanResult.outcome
            ExpectedFileSha256 = $reviewedFileHash
        }
        if (-not [string]::IsNullOrWhiteSpace($Config)) {
            $helperArguments["Config"] = $Config
        }
        if ($NonInteractive) {
            $helperArguments["NonInteractive"] = $true
        }
        if ($DebugErrors) {
            $helperArguments["DebugErrors"] = $true
        }
        & $helper @helperArguments
        return
    }

    Move-Item -LiteralPath $gatewayOutput -Destination $Output -Force
    Write-Host "Universal intake completed." -ForegroundColor Cyan
    Write-Host "Status: $status"
    Write-Host "Detected format: $([string]$report.detected_format)"
    Write-Host "Report: $Output"
    if ($status -like "QUARANTINED*") {
        Write-Host "The file was isolated and was not used for calculations." -ForegroundColor Red
        $finalExitCode = 2
    }
    elseif ($status -eq "ERROR" -or $gatewayExitCode -ne 0) {
        Write-Host "The file could not be processed. Review reason_codes in the report." -ForegroundColor Red
        $finalExitCode = 2
    }
    else {
        Write-Host "No financial calculation was performed for this file." -ForegroundColor Green
    }
}
finally {
    Remove-Item -LiteralPath $gatewayOutput -Force -ErrorAction SilentlyContinue
}

if ($finalExitCode -ne 0) {
    exit $finalExitCode
}
