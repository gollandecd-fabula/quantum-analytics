[CmdletBinding()]
param(
    [string]$ConfigPath = (Join-Path $env:LOCALAPPDATA "QuantumLocalProduction\config\default-home-local.json"),
    [string]$ReportingPeriodStart,
    [string]$ReportingPeriodEnd,
    [string]$RetentionDeadline,
    [string]$SourceInternalId,
    [switch]$NonInteractive
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
        if (Test-Path -LiteralPath (Join-Path $resolved "config\home-local.template.json") -PathType Leaf) {
            return $resolved
        }
    }
    throw "Quantum project root was not found from configurator location: $PSScriptRoot"
}

function Read-IsoDate {
    param(
        [AllowEmptyString()][string]$CurrentValue,
        [Parameter(Mandatory = $true)][string]$Prompt,
        [Parameter(Mandatory = $true)][string]$Name
    )
    $candidate = $CurrentValue
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        if ($NonInteractive) {
            throw "Non-interactive configuration requires $Name."
        }
        $candidate = Read-Host $Prompt
    }
    $parsed = [datetime]::MinValue
    if (-not [datetime]::TryParseExact(
        $candidate,
        "yyyy-MM-dd",
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::None,
        [ref]$parsed
    )) {
        throw "$Name must use YYYY-MM-DD format."
    }
    return $parsed.Date
}

$projectRoot = Resolve-ProjectRoot
$templatePath = Join-Path $projectRoot "config\home-local.template.json"
try {
    $config = Get-Content -LiteralPath $templatePath -Raw -Encoding UTF8 | ConvertFrom-Json
}
catch {
    throw "Quantum HOME_LOCAL template is not valid JSON: $templatePath"
}

$periodStart = Read-IsoDate -CurrentValue $ReportingPeriodStart -Prompt "Reporting period start (YYYY-MM-DD)" -Name "ReportingPeriodStart"
$periodEnd = Read-IsoDate -CurrentValue $ReportingPeriodEnd -Prompt "Reporting period end (YYYY-MM-DD)" -Name "ReportingPeriodEnd"
$retention = Read-IsoDate -CurrentValue $RetentionDeadline -Prompt "Retention deadline (YYYY-MM-DD)" -Name "RetentionDeadline"
if ($periodEnd -lt $periodStart) {
    throw "ReportingPeriodEnd cannot be earlier than ReportingPeriodStart."
}
if ($retention -lt $periodEnd) {
    throw "RetentionDeadline cannot be earlier than ReportingPeriodEnd."
}
if ($retention -lt [datetime]::UtcNow.Date) {
    throw "RetentionDeadline cannot be in the past."
}

if ([string]::IsNullOrWhiteSpace($SourceInternalId)) {
    $SourceInternalId = "home-local-{0}" -f (Get-Date -Format "yyyyMMdd-HHmmss")
}
if ($SourceInternalId.Length -gt 128 -or $SourceInternalId -notmatch "^[A-Za-z0-9._-]+$") {
    throw "SourceInternalId must contain only letters, digits, dot, underscore or hyphen and be at most 128 characters."
}

$config.configuration_status = "READY_ADMISSION_ONLY"
$config | Add-Member -NotePropertyName execution_mode -NotePropertyValue "ADMISSION_ONLY" -Force
$config.source_internal_id = $SourceInternalId
$config.reporting_period_start = $periodStart.ToString("yyyy-MM-dd")
$config.reporting_period_end = $periodEnd.ToString("yyyy-MM-dd")
$config.retention_deadline = $retention.ToString("yyyy-MM-dd") + "T23:59:59Z"
$config.expected_row_count = 1
$config.lawful_authority_attested = $false
$config.finance_request = $null
$config.reconciliation = $null

$targetDirectory = Split-Path -Parent ([IO.Path]::GetFullPath($ConfigPath))
New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
if (Test-Path -LiteralPath $ConfigPath -PathType Leaf) {
    $backup = "{0}.backup_{1}" -f $ConfigPath, (Get-Date -Format "yyyyMMdd_HHmmss")
    Copy-Item -LiteralPath $ConfigPath -Destination $backup -Force
    Write-Host "Previous configuration backed up to: $backup"
}

$config | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
$verified = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$verified.configuration_status -ne "READY_ADMISSION_ONLY" -or [string]$verified.execution_mode -ne "ADMISSION_ONLY") {
    throw "Generated configuration verification failed."
}

Write-Host "Quantum HOME_LOCAL configuration created." -ForegroundColor Green
Write-Host "Config: $ConfigPath"
Write-Host "Mode: ADMISSION_ONLY" -ForegroundColor Yellow
Write-Host "The selected XLSX will be validated and admitted without financial calculation."
Write-Host "A FULL finance_request is still required before profit calculations can run."
