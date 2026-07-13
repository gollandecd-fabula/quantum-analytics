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
    throw (Get-QuantumRussianText -Encoded "0J3QtSDRg9C00LDQu9C+0YHRjCDQvtC/0YDQtdC00LXQu9C40YLRjCDQutC+0YDQvdC10LLRg9GOINC/0LDQv9C60YMg0L/RgNC+0LXQutGC0LAgUXVhbnR1bSDQuNC3INGA0LDRgdC/0L7Qu9C+0LbQtdC90LjRjyDQv9GA0L7Qs9GA0LDQvNC80Ysg0LfQsNC/0YPRgdC60LA6IHswfQ==" -Arguments @($PSScriptRoot))
}

function Select-SourceFile {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = (Get-QuantumRussianText -Encoded "0JLRi9Cx0LXRgNC40YLQtSDQu9C+0LrQsNC70YzQvdGL0Lkg0YTQsNC50LssINGA0LDQt9GA0LXRiNGR0L3QvdGL0Lkg0Log0L7QsdGA0LDQsdC+0YLQutC1INCyIFF1YW50dW0=")
    $dialog.Filter = (Get-QuantumRussianText -Encoded "0JLRgdC1INGE0LDQudC70YsgKCouKil8Ki4q")
    $dialog.Multiselect = $false
    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
        throw (Get-QuantumRussianText -Encoded "0JLRi9Cx0L7RgCDRhNCw0LnQu9CwINC+0YLQvNC10L3RkdC9Lg==")
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
    throw (Get-QuantumRussianText -Encoded "UHl0aG9uIDMuMTIg0LjQu9C4INC90L7QstC10LUg0L3QtSDQvdCw0LnQtNC10L0u")
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
        throw (Get-QuantumRussianText -Encoded "0JIg0L3QtdC40L3RgtC10YDQsNC60YLQuNCy0L3QvtC8INGA0LXQttC40LzQtSDQvdC10L7QsdGF0L7QtNC40LzQviDRj9Cy0L3QviDQv9C10YDQtdC00LDRgtGMINC/0L7QtNGC0LLQtdGA0LbQtNC10L3QuNC1IHswfS4=" -Arguments @($Expected))
    }
    $answer = Read-Host $Prompt
    if ($answer -cne $Expected) {
        throw (Get-QuantumRussianText -Encoded "0J7QsdGP0LfQsNGC0LXQu9GM0L3QvtC1INC/0L7QtNGC0LLQtdGA0LbQtNC10L3QuNC1IHswfSDQvdC1INC/0YDQtdC00L7RgdGC0LDQstC70LXQvdC+Lg==" -Arguments @($Expected))
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

function Test-DefenderUnavailableOutput {
    param([AllowEmptyString()][string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) {
        return $false
    }
    return $Text -match "0x800106BA|800106BA|0x80004003|Failed with hr|MpScanStart.*Failed"
}

function New-ScanResult {
    param(
        [Parameter(Mandatory = $true)][string]$Scanner,
        [Parameter(Mandatory = $true)][string]$Outcome,
        [string]$FallbackReason = ""
    )
    return [ordered]@{
        scanner = $Scanner
        outcome = $Outcome
        fallback_reason = $FallbackReason
    }
}

function New-StructuralFallbackScanResult {
    param(
        [Parameter(Mandatory = $true)][string]$Reason,
        [string]$Scanner = "MICROSOFT_DEFENDER_UNAVAILABLE"
    )
    Write-Host (Get-QuantumRussianText -Encoded "TWljcm9zb2Z0IERlZmVuZGVyINC90LXQtNC+0YHRgtGD0L/QtdC9OiB7MH0=" -Arguments @($Reason)) -ForegroundColor Yellow
    Write-Host (Get-QuantumRussianText -Encoded "UXVhbnR1bSDQv9GA0L7QtNC+0LvQttC40YIg0LvQvtC60LDQu9GM0L3Rg9GOINGB0YLRgNGD0LrRgtGD0YDQvdGD0Y4g0L/RgNC+0LLQtdGA0LrRgy4g0JDQutGC0LjQstC90L7QtSDRgdC+0LTQtdGA0LbQuNC80L7QtSDQuCDQv9C+0LLRgNC10LbQtNGR0L3QvdGL0LUg0LDRgNGF0LjQstGLINC/0L4t0L/RgNC10LbQvdC10LzRgyDQsdC70L7QutC40YDRg9GO0YLRgdGPLg==") -ForegroundColor Yellow
    return New-ScanResult -Scanner $Scanner -Outcome "DEFENDER_UNAVAILABLE_STRUCTURAL_FALLBACK" -FallbackReason $Reason
}

function Invoke-DefenderScan {
    param([Parameter(Mandatory = $true)][string]$Path)
    if ($SkipDefenderScan) {
        Write-Host (Get-QuantumRussianText -Encoded "0J/RgNC+0LLQtdGA0LrQsCBNaWNyb3NvZnQgRGVmZW5kZXIg0L/RgNC+0L/Rg9GJ0LXQvdCwINC/0L4g0Y/QstC90L4g0L/QtdGA0LXQtNCw0L3QvdC+0LzRgyDQv9Cw0YDQsNC80LXRgtGA0YMu") -ForegroundColor Yellow
        return New-ScanResult -Scanner "EXPLICIT_EQUIVALENT_SCAN_ATTESTED" -Outcome "SKIPPED_BY_EXPLICIT_SWITCH"
    }
    $scanner = Resolve-DefenderScanner
    if (-not $scanner) {
        return New-StructuralFallbackScanResult -Reason "MPCmdRun scanner was not found."
    }
    Write-Host (Get-QuantumRussianText -Encoded "0J/RgNC+0LLQtdGA0LrQsCDQuNGB0YXQvtC00L3QvtCz0L4g0YTQsNC50LvQsCDRgSDQv9C+0LzQvtGJ0YzRjiBNaWNyb3NvZnQgRGVmZW5kZXIuLi4=")
    $scanOutput = @(& $scanner -Scan -ScanType 3 -File $Path 2>&1)
    $exitCode = $LASTEXITCODE
    $scanOutput | Out-Host
    if ($exitCode -eq 0) {
        return New-ScanResult -Scanner $scanner -Outcome "CLEAN"
    }
    $outputText = ($scanOutput | Out-String)
    if (Test-DefenderUnavailableOutput -Text $outputText) {
        return New-StructuralFallbackScanResult -Reason ("MpCmdRun unavailable or service failure. Exit code: {0}" -f $exitCode) -Scanner $scanner
    }
    throw (Get-QuantumRussianText -Encoded "0J/RgNC+0LLQtdGA0LrQsCBNaWNyb3NvZnQgRGVmZW5kZXIg0LfQsNCy0LXRgNGI0LjQu9Cw0YHRjCDQvtGI0LjQsdC60L7QuSDQuNC70Lgg0L7QsdC90LDRgNGD0LbQuNC70LAg0YPQs9GA0L7Qt9GDLiDQmtC+0LQg0LLRi9GF0L7QtNCwOiB7MH0=" -Arguments @($exitCode))
}

function New-ScanReceipt {
    param(
        [Parameter(Mandatory = $true)][string]$SourcePath,
        [Parameter(Mandatory = $true)]$ScanResult
    )
    $sourceHash = (Get-FileHash -LiteralPath $SourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $receipt = [ordered]@{
        receipt_version = 2
        source_sha256 = $sourceHash
        scanner = [string]$ScanResult.scanner
        outcome = [string]$ScanResult.outcome
        fallback_reason = [string]$ScanResult.fallback_reason
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
    throw (Get-QuantumRussianText -Encoded "0JzQvtC00YPQu9GMINGB0L7QstC80LXRgdGC0LjQvNC+0YHRgtC4IFNIQS0yNTYgUXVhbnR1bSDQvdC1INC90LDQudC00LXQvTogezB9" -Arguments @($hashCompat))
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
Confirm-Literal -Expected "AUTHORIZE" -Prompt (Get-QuantumRussianText -Encoded "0JLQstC10LTQuNGC0LUgQVVUSE9SSVpFLCDRh9GC0L7QsdGLINC/0L7QtNGC0LLQtdGA0LTQuNGC0Ywg0LfQsNC60L7QvdC90YvQtSDQv9C+0LvQvdC+0LzQvtGH0LjRjyDQvdCwINC+0LHRgNCw0LHQvtGC0LrRgyDRhNCw0LnQu9Cw") -AlreadyAttested ([bool]$AuthorityAttested)

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
        throw (Get-QuantumRussianText -Encoded "0KPQvdC40LLQtdGA0YHQsNC70YzQvdGL0Lkg0LjQvNC/0L7RgNGCINC90LUg0YHQvtC30LTQsNC7INC+0YLRh9GR0YI6IHswfQ==" -Arguments @($gatewayOutput))
    }
    $report = Get-Content -LiteralPath $gatewayOutput -Raw -Encoding UTF8 | ConvertFrom-Json
    $status = [string]$report.status
    $hashProperty = $report.PSObject.Properties["file_sha256"]
    if (
        $hashProperty -and
        -not [string]::IsNullOrWhiteSpace([string]$hashProperty.Value) -and
        [string]$hashProperty.Value -ne $reviewedFileHash
    ) {
        throw (Get-QuantumRussianText -Encoded "0KXQtdGIINGE0LDQudC70LAg0YPQvdC40LLQtdGA0YHQsNC70YzQvdC+0LPQviDQuNC80L/QvtGA0YLQsCDQvdC1INGB0L7QstC/0LDQtNCw0LXRgiDRgSDQv9GA0L7QstC10YDQtdC90L3Ri9C8INGE0LDQudC70L7QvC4=")
    }

    if ($status -eq "ROUTE_XLSX") {
        if ($gatewayExitCode -ne 0) {
            throw (Get-QuantumRussianText -Encoded "0JzQsNGA0YjRgNGD0YLQuNC30LDRhtC40Y8gWExTWCDQt9Cw0LLQtdGA0YjQuNC70LDRgdGMINC90LXQvdGD0LvQtdCy0YvQvCDQutC+0LTQvtC8OiB7MH0u" -Arguments @($gatewayExitCode))
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
    Write-Host (Get-QuantumRussianText -Encoded "0KPQvdC40LLQtdGA0YHQsNC70YzQvdGL0Lkg0LjQvNC/0L7RgNGCINC30LDQstC10YDRiNGR0L0u") -ForegroundColor Cyan
    Write-Host (Get-QuantumRussianText -Encoded "0KHRgtCw0YLRg9GBOiB7MH0=" -Arguments @($status))
    Write-Host (Get-QuantumRussianText -Encoded "0J7Qv9GA0LXQtNC10LvRkdC90L3Ri9C5INGE0L7RgNC80LDRgjogezB9" -Arguments @($([string]$report.detected_format)))
    Write-Host (Get-QuantumRussianText -Encoded "0J7RgtGH0ZHRgjogezB9" -Arguments @($Output))
    if ($status -like "QUARANTINED*") {
        Write-Host (Get-QuantumRussianText -Encoded "0KTQsNC50Lsg0LjQt9C+0LvQuNGA0L7QstCw0L0g0Lgg0L3QtSDQuNGB0L/QvtC70YzQt9C+0LLQsNC70YHRjyDQsiDRgNCw0YHRh9GR0YLQsNGFLg==") -ForegroundColor Red
        $finalExitCode = 2
    }
    elseif ($status -eq "ERROR" -or $gatewayExitCode -ne 0) {
        Write-Host (Get-QuantumRussianText -Encoded "0KTQsNC50Lsg0L3QtSDRg9C00LDQu9C+0YHRjCDQvtCx0YDQsNCx0L7RgtCw0YLRjC4g0J/RgNC+0LLQtdGA0YzRgtC1IHJlYXNvbl9jb2RlcyDQsiDQvtGC0YfRkdGC0LUu") -ForegroundColor Red
        $finalExitCode = 2
    }
    else {
        Write-Host (Get-QuantumRussianText -Encoded "0JTQu9GPINGN0YLQvtCz0L4g0YTQsNC50LvQsCDRhNC40L3QsNC90YHQvtCy0YvQuSDRgNCw0YHRh9GR0YIg0L3QtSDQstGL0L/QvtC70L3Rj9C70YHRjy4=") -ForegroundColor Green
    }
}
finally {
    Remove-Item -LiteralPath $gatewayOutput -Force -ErrorAction SilentlyContinue
}

if ($finalExitCode -ne 0) {
    exit $finalExitCode
}
