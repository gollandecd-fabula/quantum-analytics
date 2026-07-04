[CmdletBinding()]
param(
    [string]$ConfigPath = (Join-Path $env:LOCALAPPDATA "QuantumLocalProduction\config\default-home-local.json"),
    [string]$ReportingPeriodStart,
    [string]$ReportingPeriodEnd,
    [string]$RetentionDeadline,
    [string]$SourceInternalId,
    [string]$Marketplace = "WILDBERRIES",
    [string]$ReportType = "SALES_REPORT",
    [string]$Timezone = "Europe/Moscow",
    [switch]$NonInteractive
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Read-RequiredValue {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$CurrentValue,
        [Parameter(Mandatory = $true)][string]$Prompt,
        [Parameter(Mandatory = $true)][string]$Name
    )
    if (-not [string]::IsNullOrWhiteSpace($CurrentValue)) {
        return $CurrentValue.Trim()
    }
    if ($NonInteractive) {
        throw "$Name is required in non-interactive mode."
    }
    $value = Read-Host $Prompt
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "$Name is required."
    }
    return $value.Trim()
}

function Read-IsoDate {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$CurrentValue,
        [Parameter(Mandatory = $true)][string]$Prompt,
        [Parameter(Mandatory = $true)][string]$Name
    )
    $value = Read-RequiredValue -CurrentValue $CurrentValue -Prompt $Prompt -Name $Name
    $parsed = [DateTime]::MinValue
    if (-not [DateTime]::TryParseExact(
        $value,
        "yyyy-MM-dd",
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::None,
        [ref]$parsed
    )) {
        throw "$Name must use YYYY-MM-DD."
    }
    return $parsed.ToString("yyyy-MM-dd")
}

function Convert-FromUtf8Base64 {
    param(
        [Parameter(Mandatory = $true)][string]$Value
    )
    return [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Value))
}

$ReportingPeriodStart = Read-IsoDate `
    -CurrentValue $ReportingPeriodStart `
    -Prompt "Report period start (YYYY-MM-DD)" `
    -Name "ReportingPeriodStart"
$ReportingPeriodEnd = Read-IsoDate `
    -CurrentValue $ReportingPeriodEnd `
    -Prompt "Report period end (YYYY-MM-DD)" `
    -Name "ReportingPeriodEnd"
$RetentionDeadline = Read-IsoDate `
    -CurrentValue $RetentionDeadline `
    -Prompt "Retention deadline (YYYY-MM-DD)" `
    -Name "RetentionDeadline"
$SourceInternalId = Read-RequiredValue `
    -CurrentValue $SourceInternalId `
    -Prompt "Local source identifier (for example wb-sales-main)" `
    -Name "SourceInternalId"

if ([DateTime]::ParseExact($ReportingPeriodEnd, "yyyy-MM-dd", [Globalization.CultureInfo]::InvariantCulture) -lt [DateTime]::ParseExact($ReportingPeriodStart, "yyyy-MM-dd", [Globalization.CultureInfo]::InvariantCulture)) {
    throw "ReportingPeriodEnd must not be earlier than ReportingPeriodStart."
}

$targetDirectory = Split-Path -Parent ([IO.Path]::GetFullPath($ConfigPath))
if ([string]::IsNullOrWhiteSpace($targetDirectory)) {
    throw "ConfigPath must include a parent directory."
}
New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null

$config = [ordered]@{
    configuration_status = "READY"
    execution_mode = "ADMISSION_ONLY"
    tenant_id = "tenant-home-local"
    account_id = "operator-home-local"
    verifier_account_id = "verifier-home-local"
    source_internal_id = $SourceInternalId
    marketplace = $Marketplace
    report_type = $ReportType
    reporting_period_start = $ReportingPeriodStart
    reporting_period_end = $ReportingPeriodEnd
    timezone = $Timezone
    expected_row_count = 1
    control_totals_sha256 = $null
    data_categories = @("FINANCIAL", "SALES")
    owner_authority_reference = "HOME-LOCAL-OWNER-REVIEW"
    lawful_authority_attested = $false
    retention_deadline = "${RetentionDeadline}T00:00:00Z"
    malware_scan_evidence_sha256 = "0000000000000000000000000000000000000000000000000000000000000000"
    attestations = [ordered]@{
        source_authority_verified = $true
        report_period_verified = $true
        control_totals_verified = $true
        direct_identifiers_absent_or_approved = $true
        malware_scan_clean = $true
    }
    inspection_policy = [ordered]@{
        policy_id = "wb-home-local-discovery"
        version = 2
        limits = [ordered]@{
            max_file_bytes = 104857600
            max_package_entries = 5000
            max_package_uncompressed_bytes = 536870912
            max_single_part_bytes = 134217728
            max_xml_nodes_per_part = 2000000
            max_sheets = 64
            max_rows = 1000000
            max_columns = 512
            max_cell_text_length = 32767
            max_shared_strings = 1000000
            max_shared_string_characters = 134217728
        }
        schemas = @(
            [ordered]@{
                schema_id = "HOME_LOCAL_DISCOVERY_TEMPLATE"
                schema_version = "2"
                schema_authority_reference = "HOME_LOCAL_OPERATOR_REVIEW"
                direct_identifiers_expected = $false
                package_kind = "XLSX"
                sheet_name = "REPLACED_BY_REVIEWED_DISCOVERY"
                sheet_count = 1
                header_row_index = 1
                header_sha256 = "0000000000000000000000000000000000000000000000000000000000000000"
                column_count = 1
                min_data_rows = 1
                max_data_rows = 1000000
                max_formula_count = 0
            }
        )
        prohibited_header_tokens = @(
            "email", "e-mail", "phone", "telephone", "mobile", "address",
            "full name", "surname", "passport", "snils", "inn",
            (Convert-FromUtf8Base64 -Value "0Y3Qu9C10LrRgtGA0L7QvdC90LDRjyDQv9C+0YfRgtCw"),
            (Convert-FromUtf8Base64 -Value "0YLQtdC70LXRhNC+0L0="),
            (Convert-FromUtf8Base64 -Value "0LDQtNGA0LXRgQ=="),
            (Convert-FromUtf8Base64 -Value "0YTQuNC+"),
            (Convert-FromUtf8Base64 -Value "0YTQsNC80LjQu9C40Y8="),
            (Convert-FromUtf8Base64 -Value "0L/QsNGB0L/QvtGA0YI="),
            (Convert-FromUtf8Base64 -Value "0YHQvdC40LvRgQ=="),
            (Convert-FromUtf8Base64 -Value "0LjQvdC9")
        )
    }
    finance_request = $null
    reconciliation = $null
}

$configJson = $config | ConvertTo-Json -Depth 12
$utf8NoBom = New-Object System.Text.UTF8Encoding
[IO.File]::WriteAllText($ConfigPath, $configJson, $utf8NoBom)
Write-Host "HOME_LOCAL configuration created." -ForegroundColor Green
Write-Host "Path: $ConfigPath"
Write-Host "Mode: ADMISSION_ONLY (financial calculation remains disabled until a reviewed finance profile is supplied)." -ForegroundColor Yellow
