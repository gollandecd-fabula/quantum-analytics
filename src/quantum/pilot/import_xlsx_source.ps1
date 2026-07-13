[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$File,
    [string]$Config,
    [string]$StorageRoot,
    [string]$Output,
    [switch]$NonInteractive,
    [switch]$AuthorityAttested,
    [switch]$SchemaReviewed,
    [switch]$SkipDefenderScan,
    [string]$PreScannedEvidenceSha256,
    [string]$PreScannedOutcome,
    [string]$ExpectedFileSha256,
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
$Sha256Pattern = "^[0-9a-fA-F]{64}$"

function Resolve-ProjectRoot {
    $candidate = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path
    $runner = Join-Path $candidate "src\quantum\pilot\windows_runner.py"
    if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
        throw (Get-QuantumRussianText -Encoded "0J3QtSDRg9C00LDQu9C+0YHRjCDQvtC/0YDQtdC00LXQu9C40YLRjCDQutC+0YDQvdC10LLRg9GOINC/0LDQv9C60YMgUXVhbnR1bSDQuNC3INGA0LDRgdC/0L7Qu9C+0LbQtdC90LjRjyDQvNC+0LTRg9C70Y8gWExTWDogezB9" -Arguments @($PSScriptRoot))
    }
    return $candidate
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

function New-StructuralFallbackScanResult {
    param(
        [Parameter(Mandatory = $true)][string]$Reason,
        [string]$Scanner = "MICROSOFT_DEFENDER_UNAVAILABLE"
    )
    Write-Host (Get-QuantumRussianText -Encoded "TWljcm9zb2Z0IERlZmVuZGVyINC90LXQtNC+0YHRgtGD0L/QtdC9OiB7MH0=" -Arguments @($Reason)) -ForegroundColor Yellow
    Write-Host (Get-QuantumRussianText -Encoded "UXVhbnR1bSDQv9GA0L7QtNC+0LvQttC40YIg0LvQvtC60LDQu9GM0L3Rg9GOINGB0YLRgNGD0LrRgtGD0YDQvdGD0Y4g0L/RgNC+0LLQtdGA0LrRgy4g0JDQutGC0LjQstC90L7QtSDRgdC+0LTQtdGA0LbQuNC80L7QtSDQuCDQv9C+0LLRgNC10LbQtNGR0L3QvdGL0LUg0LDRgNGF0LjQstGLINC/0L4t0L/RgNC10LbQvdC10LzRgyDQsdC70L7QutC40YDRg9GO0YLRgdGPLg==") -ForegroundColor Yellow
    return [ordered]@{
        scanner = $Scanner
        outcome = "DEFENDER_UNAVAILABLE_STRUCTURAL_FALLBACK"
        fallback_reason = $Reason
    }
}

function Invoke-DefenderScan {
    param([Parameter(Mandatory = $true)][string]$Path)
    if ($SkipDefenderScan) {
        Write-Host (Get-QuantumRussianText -Encoded "0J/RgNC+0LLQtdGA0LrQsCBNaWNyb3NvZnQgRGVmZW5kZXIg0L/RgNC+0L/Rg9GJ0LXQvdCwINC/0L4g0Y/QstC90L4g0L/QtdGA0LXQtNCw0L3QvdC+0LzRgyDQv9Cw0YDQsNC80LXRgtGA0YMu") -ForegroundColor Yellow
        return [ordered]@{
            scanner = "EXPLICIT_EQUIVALENT_SCAN_ATTESTED"
            outcome = "SKIPPED_BY_EXPLICIT_SWITCH"
        }
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
        return [ordered]@{
            scanner = $scanner
            outcome = "CLEAN"
        }
    }
    $outputText = ($scanOutput | Out-String)
    if (Test-DefenderUnavailableOutput -Text $outputText) {
        return New-StructuralFallbackScanResult -Reason ("MpCmdRun unavailable or service failure. Exit code: {0}" -f $exitCode) -Scanner $scanner
    }
    throw (Get-QuantumRussianText -Encoded "0J/RgNC+0LLQtdGA0LrQsCBNaWNyb3NvZnQgRGVmZW5kZXIg0LfQsNCy0LXRgNGI0LjQu9Cw0YHRjCDQvtGI0LjQsdC60L7QuSDQuNC70Lgg0L7QsdC90LDRgNGD0LbQuNC70LAg0YPQs9GA0L7Qt9GDLiDQmtC+0LQg0LLRi9GF0L7QtNCwOiB7MH0=" -Arguments @($exitCode))
}

function Test-UsableConfig {
    param([Parameter(Mandatory = $true)][string]$Path)
    try {
        $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        throw (Get-QuantumRussianText -Encoded "0JrQvtC90YTQuNCz0YPRgNCw0YbQuNGPIFF1YW50dW0g0L3QtSDRj9Cy0LvRj9C10YLRgdGPINC60L7RgNGA0LXQutGC0L3Ri9C8IEpTT046IHswfQ==" -Arguments @($Path))
    }
    $statusProperty = $raw.PSObject.Properties["configuration_status"]
    if ($statusProperty -and [string]$statusProperty.Value -eq "REQUIRES_USER_VALUES") {
        throw (Get-QuantumRussianText -Encoded "0KjQsNCx0LvQvtC9INC60L7QvdGE0LjQs9GD0YDQsNGG0LjQuCDQvdC1INCz0L7RgtC+0LIuINCh0L3QsNGH0LDQu9CwINC30LDQv9GD0YHRgtC40YLQtSBDT05GSUdVUkVfSE9NRV9MT0NBTC5jbWQu")
    }
    $modeProperty = $raw.PSObject.Properties["execution_mode"]
    $executionMode = if ($modeProperty) { [string]$modeProperty.Value } else { "FULL" }
    if ($executionMode -eq "ADMISSION_ONLY") {
        return
    }
    if ($executionMode -ne "FULL") {
        throw (Get-QuantumRussianText -Encoded "0JIg0LrQvtC90YTQuNCz0YPRgNCw0YbQuNC4INGD0LrQsNC30LDQvSDQvdC10L/QvtC00LTQtdGA0LbQuNCy0LDQtdC80YvQuSBleGVjdXRpb25fbW9kZTogezB9" -Arguments @($executionMode))
    }
    $financeProperty = $raw.PSObject.Properties["finance_request"]
    if (-not $financeProperty -or $null -eq $financeProperty.Value) {
        throw (Get-QuantumRussianText -Encoded "0JIg0LrQvtC90YTQuNCz0YPRgNCw0YbQuNC4IEZVTEwg0L7RgtGB0YPRgtGB0YLQstGD0LXRgiDQvtCx0YrQtdC60YIgZmluYW5jZV9yZXF1ZXN0OiB7MH0=" -Arguments @($Path))
    }
    $placeholderProperty = $financeProperty.Value.PSObject.Properties["replace_with_a_valid_versioned_finance_request"]
    if ($placeholderProperty -and $placeholderProperty.Value -eq $true) {
        throw (Get-QuantumRussianText -Encoded "0JrQvtC90YTQuNCz0YPRgNCw0YbQuNGPIEZVTEwg0LLRgdGRINC10YnRkSDRgdC+0LTQtdGA0LbQuNGCINC30LDQs9C70YPRiNC60YMgZmluYW5jZV9yZXF1ZXN0OiB7MH0=" -Arguments @($Path))
    }
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
            receipt = $receipt
        }
    }
    finally {
        $receiptStream.Dispose()
    }
}

function Resolve-ScanReceipt {
    param([Parameter(Mandatory = $true)][string]$SourcePath)
    $sourceHash = (Get-FileHash -LiteralPath $SourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if (
        -not [string]::IsNullOrWhiteSpace($ExpectedFileSha256) -and
        $sourceHash -ne $ExpectedFileSha256.ToLowerInvariant()
    ) {
        throw (Get-QuantumRussianText -Encoded "0KXQtdGIINC40YHRhdC+0LTQvdC+0LPQviBYTFNYINC90LUg0YHQvtCy0L/QsNC00LDQtdGCINGBINC/0YDQvtCy0LXRgNC10L3QvdGL0Lwg0YTQsNC50LvQvtC8Lg==")
    }
    if (-not [string]::IsNullOrWhiteSpace($PreScannedEvidenceSha256)) {
        if ($PreScannedEvidenceSha256 -notmatch $Sha256Pattern) {
            throw (Get-QuantumRussianText -Encoded "0J/QtdGA0LXQtNCw0L3QvdGL0LkgU0hBLTI1NiDQv9GA0LXQtNCy0LDRgNC40YLQtdC70YzQvdC+0Lkg0L/RgNC+0LLQtdGA0LrQuCDQvdC10LrQvtGA0YDQtdC60YLQtdC9Lg==")
        }
        if ([string]::IsNullOrWhiteSpace($PreScannedOutcome)) {
            throw (Get-QuantumRussianText -Encoded "0JLQvNC10YHRgtC1INGBIFNIQS0yNTYg0L/RgNC10LTQstCw0YDQuNGC0LXQu9GM0L3QvtC5INC/0YDQvtCy0LXRgNC60Lgg0YLRgNC10LHRg9C10YLRgdGPINC10ZEg0YDQtdC30YPQu9GM0YLQsNGCLg==")
        }
        return [ordered]@{
            source_sha256 = $sourceHash
            evidence_sha256 = $PreScannedEvidenceSha256.ToLowerInvariant()
            receipt = [ordered]@{
                receipt_version = 1
                source_sha256 = $sourceHash
                scanner = "UNIVERSAL_FRONT_DOOR"
                outcome = $PreScannedOutcome
                created_at_utc = [DateTime]::UtcNow.ToString("o")
            }
        }
    }
    $scanResult = Invoke-DefenderScan -Path $SourcePath
    return New-ScanReceipt -SourcePath $SourcePath -ScanResult $scanResult
}

function New-RuntimeConfig {
    param(
        [Parameter(Mandatory = $true)][string]$SourceConfig,
        [Parameter(Mandatory = $true)][string]$MalwareEvidenceSha256,
        [Parameter(Mandatory = $true)][string]$MalwareScanOutcome
    )
    $raw = Get-Content -LiteralPath $SourceConfig -Raw -Encoding UTF8 | ConvertFrom-Json
    $raw.malware_scan_evidence_sha256 = $MalwareEvidenceSha256
    $raw | Add-Member -NotePropertyName malware_scan_outcome -NotePropertyValue $MalwareScanOutcome -Force
    return $raw
}

$projectRoot = Resolve-ProjectRoot
$hashCompat = Join-Path $projectRoot "src\quantum\pilot\hash_compat.ps1"
if (-not (Test-Path -LiteralPath $hashCompat -PathType Leaf)) {
    throw (Get-QuantumRussianText -Encoded "0JzQvtC00YPQu9GMINGB0L7QstC80LXRgdGC0LjQvNC+0YHRgtC4IFNIQS0yNTYgUXVhbnR1bSDQvdC1INC90LDQudC00LXQvTogezB9" -Arguments @($hashCompat))
}
. $hashCompat

$File = (Resolve-Path -LiteralPath $File).Path

if ([string]::IsNullOrWhiteSpace($Config)) {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "QuantumLocalProduction\config\production.local.json"),
        (Join-Path $env:LOCALAPPDATA "QuantumLocalProduction\config\default-home-local.json"),
        (Join-Path $env:LOCALAPPDATA "QuantumLocalProduction\config\default-production.json")
    )
    $Config = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $Config) {
        $template = Join-Path $projectRoot "config\home-local.template.json"
        throw (Get-QuantumRussianText -Encoded "0JPQvtGC0L7QstCw0Y8g0LrQvtC90YTQuNCz0YPRgNCw0YbQuNGPIFF1YW50dW0g0L3QtSDQvdCw0LnQtNC10L3QsC4g0JfQsNC/0YPRgdGC0LjRgtC1IENPTkZJR1VSRV9IT01FX0xPQ0FMLmNtZC4g0KjQsNCx0LvQvtC9OiB7MH0=" -Arguments @($template))
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

$scanReceipt = Resolve-ScanReceipt -SourcePath $File
$reviewedFileHash = [string]$scanReceipt.source_sha256

Write-Host (Get-QuantumRussianText -Encoded "0J/RgNC+0YTQuNC70Ywg0LfQsNC/0YPRgdC60LA6IEhPTUVfTE9DQUw=") -ForegroundColor Cyan
Write-Host (Get-QuantumRussianText -Encoded "0JIgSE9NRV9MT0NBTCDRiNC40YTRgNC+0LLQsNC90LjQtSDQtNC40YHQutCwINC90LUg0Y/QstC70Y/QtdGC0YHRjyDQvtCx0Y/Qt9Cw0YLQtdC70YzQvdGL0LwuINCSINGA0LXQt9GD0LvRjNGC0LDRgtC1INCx0YPQtNC10YIg0LfQsNGE0LjQutGB0LjRgNC+0LLQsNC90L4g0L7Qs9GA0LDQvdC40YfQtdC90LjQtSDQvdC10LfQsNGI0LjRhNGA0L7QstCw0L3QvdC+0LPQviDRhdGA0LDQvdC10L3QuNGPLg==") -ForegroundColor Yellow
Confirm-Literal -Expected "AUTHORIZE" -Prompt (Get-QuantumRussianText -Encoded "0JLQstC10LTQuNGC0LUgQVVUSE9SSVpFLCDRh9GC0L7QsdGLINC/0L7QtNGC0LLQtdGA0LTQuNGC0Ywg0LfQsNC60L7QvdC90YvQtSDQv9C+0LvQvdC+0LzQvtGH0LjRjyDQvdCwINC+0LHRgNCw0LHQvtGC0LrRgyDQvtGC0YfRkdGC0LA=") -AlreadyAttested ([bool]$AuthorityAttested)

$pythonCommand = Resolve-PythonCommand
$env:PYTHONPATH = Join-Path $projectRoot "src"
$runtimeConfig = Join-Path ([IO.Path]::GetTempPath()) ("quantum-runtime-config-{0}.json" -f [guid]::NewGuid().ToString("N"))
$previewOutput = Join-Path ([IO.Path]::GetTempPath()) ("quantum-schema-preview-{0}.json" -f [guid]::NewGuid().ToString("N"))

try {
    $runtimeConfigObject = New-RuntimeConfig `
        -SourceConfig $Config `
        -MalwareEvidenceSha256 ([string]$scanReceipt.evidence_sha256) `
        -MalwareScanOutcome ([string]$scanReceipt.receipt.outcome)
    $runtimeConfigJson = $runtimeConfigObject | ConvertTo-Json -Depth 16
    [IO.File]::WriteAllText($runtimeConfig, $runtimeConfigJson, ([System.Text.UTF8Encoding]::new($false)))

    $previewArguments = @()
    $previewArguments += $pythonCommand.Prefix
    $previewArguments += @(
        "-c", "from quantum.pilot.windows_runner import main; raise SystemExit(main())",
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
        throw (Get-QuantumRussianText -Encoded "0J7Qv9GA0LXQtNC10LvQtdC90LjQtSDRgdGF0LXQvNGLIFF1YW50dW0g0LfQsNCy0LXRgNGI0LjQu9C+0YHRjCDQvtGI0LjQsdC60L7QuS4g0JrQvtC0INCy0YvRhdC+0LTQsDogezB9Lg==" -Arguments @($LASTEXITCODE))
    }
    $preview = Get-Content -LiteralPath $previewOutput -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([string]$preview.file_sha256 -ne $reviewedFileHash) {
        throw (Get-QuantumRussianText -Encoded "0KXQtdGIINGE0LDQudC70LAg0L/RgNC10LTQv9GA0L7RgdC80L7RgtGA0LAg0YHRhdC10LzRiyDQvdC1INGB0L7QstC/0LDQtNCw0LXRgiDRgSDQv9GA0L7QstC10YDQtdC90L3Ri9C8INGE0LDQudC70L7QvC4=")
    }
    $schemaProperty = $preview.PSObject.Properties["schema_discovery"]
    if (-not $schemaProperty -or $null -eq $schemaProperty.Value) {
        throw (Get-QuantumRussianText -Encoded "0J/RgNC10LTQv9GA0L7RgdC80L7RgtGAINGB0YXQtdC80Ysg0L3QtSDRgdC+0LTQtdGA0LbQuNGCIHNjaGVtYV9kaXNjb3Zlcnku")
    }
    $schema = $schemaProperty.Value
    foreach ($requiredProperty in @(
        "headers",
        "sheet_name",
        "header_row_index",
        "column_count",
        "data_row_count"
    )) {
        if (-not $schema.PSObject.Properties[$requiredProperty]) {
            throw (Get-QuantumRussianText -Encoded "0JIg0L/RgNC10LTQv9GA0L7RgdC80L7RgtGA0LUg0YHRhdC10LzRiyDQvtGC0YHRg9GC0YHRgtCy0YPQtdGCINC+0LHRj9C30LDRgtC10LvRjNC90L7QtSDRgdCy0L7QudGB0YLQstC+OiB7MH0=" -Arguments @($requiredProperty))
        }
    }
    if (@($schema.headers).Count -lt 1) {
        throw (Get-QuantumRussianText -Encoded "0JfQsNCz0L7Qu9C+0LLQutC4INCyINC/0YDQtdC00L/RgNC+0YHQvNC+0YLRgNC1INGB0YXQtdC80Ysg0L/Rg9GB0YLRiy4=")
    }
    Write-Host (Get-QuantumRussianText -Encoded "0J7Qv9GA0LXQtNC10LvRkdC90L3Ri9C5INC70LjRgdGCOiB7MH0=" -Arguments @($($schema.sheet_name))) -ForegroundColor Cyan
    Write-Host (Get-QuantumRussianText -Encoded "0KHRgtGA0L7QutCwINC30LDQs9C+0LvQvtCy0LrQvtCyOiB7MH0=" -Arguments @($($schema.header_row_index)))
    Write-Host (Get-QuantumRussianText -Encoded "0JrQvtC70LjRh9C10YHRgtCy0L4g0YHRgtC+0LvQsdGG0L7QsjogezB9" -Arguments @($($schema.column_count)))
    Write-Host (Get-QuantumRussianText -Encoded "0JrQvtC70LjRh9C10YHRgtCy0L4g0YHRgtGA0L7QuiDQtNCw0L3QvdGL0YU6IHswfQ==" -Arguments @($($schema.data_row_count)))
    Write-Host (Get-QuantumRussianText -Encoded "0JfQsNCz0L7Qu9C+0LLQutC4OiB7MH0=" -Arguments @($(@($schema.headers) -join ' | ')))
    Write-Host (Get-QuantumRussianText -Encoded "0J3QsNGB0YLRgNC+0LXQvdC90YvQuSDQvtGC0YfRkdGC0L3Ri9C5INC/0LXRgNC40L7QtDogezB9IOKAlCB7MX0=" -Arguments @($($runtimeConfigObject.reporting_period_start), $($runtimeConfigObject.reporting_period_end)))
    Write-Host (Get-QuantumRussianText -Encoded "U0hBLTI1NiDRhNCw0LnQu9CwOiB7MH0=" -Arguments @($reviewedFileHash))
    Confirm-Literal -Expected "REVIEWED" -Prompt (Get-QuantumRussianText -Encoded "0J/RgNC+0LLQtdGA0YzRgtC1INC/0L7QutCw0LfQsNC90L3Rg9GOINGB0YXQtdC80YMg0Lgg0L7RgtGH0ZHRgtC90YvQuSDQv9C10YDQuNC+0LQsINC30LDRgtC10Lwg0LLQstC10LTQuNGC0LUgUkVWSUVXRUQg0LTQu9GPINC/0YDQvtC00L7Qu9C20LXQvdC40Y8=") -AlreadyAttested ([bool]$SchemaReviewed)

    $currentFileHash = (Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($currentFileHash -ne $reviewedFileHash) {
        throw (Get-QuantumRussianText -Encoded "0JjRgdGF0L7QtNC90YvQuSDRhNCw0LnQuyDQuNC30LzQtdC90LjQu9GB0Y8g0L/QvtGB0LvQtSDQv9GA0L7QstC10YDQutC4INGB0YXQtdC80YsuINCf0LXRgNC10LfQsNC/0YPRgdGC0LjRgtC1INC40LzQv9C+0YDRgi4=")
    }

    $arguments = @()
    $arguments += $pythonCommand.Prefix
    $arguments += @(
        "-c", "from quantum.pilot.windows_runner import main; raise SystemExit(main())",
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
    if ($LASTEXITCODE -ne 0) {
        throw (Get-QuantumRussianText -Encoded "0JjQvNC/0L7RgNGCIFF1YW50dW0g0LfQsNCy0LXRgNGI0LjQu9GB0Y8g0L7RiNC40LHQutC+0LkuINCa0L7QtCDQstGL0YXQvtC00LA6IHswfS4=" -Arguments @($LASTEXITCODE))
    }
}
finally {
    Remove-Item -LiteralPath $runtimeConfig -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $previewOutput -Force -ErrorAction SilentlyContinue
}

Write-Host (Get-QuantumRussianText -Encoded "0JjQvNC/0L7RgNGCINC30LDQstC10YDRiNGR0L0u") -ForegroundColor Green
Write-Host (Get-QuantumRussianText -Encoded "0J7RgtGH0ZHRgjogezB9" -Arguments @($Output))
