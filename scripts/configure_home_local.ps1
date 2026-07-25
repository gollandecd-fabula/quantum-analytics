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
        throw (Get-QuantumRussianText -Encoded "0JIg0L3QtdC40L3RgtC10YDQsNC60YLQuNCy0L3QvtC8INGA0LXQttC40LzQtSDQvtCx0Y/Qt9Cw0YLQtdC70YzQvdC+INC30L3QsNGH0LXQvdC40LU6IHswfS4=" -Arguments @($Name))
    }
    $value = Read-Host $Prompt
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw (Get-QuantumRussianText -Encoded "0J7QsdGP0LfQsNGC0LXQu9GM0L3QviDQt9C90LDRh9C10L3QuNC1OiB7MH0u" -Arguments @($Name))
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
        throw (Get-QuantumRussianText -Encoded "0JfQvdCw0YfQtdC90LjQtSB7MH0g0LTQvtC70LbQvdC+INC40LzQtdGC0Ywg0YTQvtGA0LzQsNGCIFlZWVktTU0tREQu" -Arguments @($Name))
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
    -Prompt (Get-QuantumRussianText -Encoded "0J3QsNGH0LDQu9C+INC+0YLRh9GR0YLQvdC+0LPQviDQv9C10YDQuNC+0LTQsCAoWVlZWS1NTS1ERCk=") `
    -Name "ReportingPeriodStart"
$ReportingPeriodEnd = Read-IsoDate `
    -CurrentValue $ReportingPeriodEnd `
    -Prompt (Get-QuantumRussianText -Encoded "0J7QutC+0L3Rh9Cw0L3QuNC1INC+0YLRh9GR0YLQvdC+0LPQviDQv9C10YDQuNC+0LTQsCAoWVlZWS1NTS1ERCk=") `
    -Name "ReportingPeriodEnd"
$RetentionDeadline = Read-IsoDate `
    -CurrentValue $RetentionDeadline `
    -Prompt (Get-QuantumRussianText -Encoded "0KHRgNC+0Log0YXRgNCw0L3QtdC90LjRjyDQtNCw0L3QvdGL0YUgKFlZWVktTU0tREQp") `
    -Name "RetentionDeadline"
$SourceInternalId = Read-RequiredValue `
    -CurrentValue $SourceInternalId `
    -Prompt (Get-QuantumRussianText -Encoded "0JvQvtC60LDQu9GM0L3Ri9C5INC40LTQtdC90YLQuNGE0LjQutCw0YLQvtGAINC40YHRgtC+0YfQvdC40LrQsCAo0L3QsNC/0YDQuNC80LXRgCwgd2Itc2FsZXMtbWFpbik=") `
    -Name "SourceInternalId"

$normalizedMarketplace = $Marketplace.Trim().ToUpperInvariant()
if ($normalizedMarketplace -eq "WB") {
    $normalizedMarketplace = "WILDBERRIES"
}
if ($normalizedMarketplace -ne "WILDBERRIES") {
    throw (Get-QuantumRussianText -Encoded "0K3RgtCwINCy0LXRgNGB0LjRjyBIT01FX0xPQ0FMINC/0L7QtNC00LXRgNC20LjQstCw0LXRgiDRgtC+0LvRjNC60L4gV0lMREJFUlJJRVMuINCf0L7QtNC00LXRgNC20LrQsCBPem9uINC+0YLQu9C+0LbQtdC90LAu")
}
$Marketplace = $normalizedMarketplace

if ([DateTime]::ParseExact($ReportingPeriodEnd, "yyyy-MM-dd", [Globalization.CultureInfo]::InvariantCulture) -lt [DateTime]::ParseExact($ReportingPeriodStart, "yyyy-MM-dd", [Globalization.CultureInfo]::InvariantCulture)) {
    throw (Get-QuantumRussianText -Encoded "0J7QutC+0L3Rh9Cw0L3QuNC1INC+0YLRh9GR0YLQvdC+0LPQviDQv9C10YDQuNC+0LTQsCDQvdC1INC80L7QttC10YIg0LHRi9GC0Ywg0YDQsNC90YzRiNC1INC10LPQviDQvdCw0YfQsNC70LAu")
}

$reportingEndDate = [DateTime]::ParseExact($ReportingPeriodEnd, "yyyy-MM-dd", [Globalization.CultureInfo]::InvariantCulture)
$retentionDate = [DateTime]::ParseExact($RetentionDeadline, "yyyy-MM-dd", [Globalization.CultureInfo]::InvariantCulture)
if ($retentionDate -le $reportingEndDate) {
    throw (Get-QuantumRussianText -Encoded "0KHRgNC+0Log0YXRgNCw0L3QtdC90LjRjyDQtNCw0L3QvdGL0YUg0LTQvtC70LbQtdC9INCx0YvRgtGMINC/0L7Qt9C20LUg0L7QutC+0L3Rh9Cw0L3QuNGPINC+0YLRh9GR0YLQvdC+0LPQviDQv9C10YDQuNC+0LTQsC4=")
}
if ($retentionDate -le [DateTime]::UtcNow.Date) {
    throw (Get-QuantumRussianText -Encoded "0KHRgNC+0Log0YXRgNCw0L3QtdC90LjRjyDQtNCw0L3QvdGL0YUg0LTQvtC70LbQtdC9INCx0YvRgtGMINC/0L7Qt9C20LUg0YLQtdC60YPRidC10Lkg0LTQsNGC0YsgVVRDLg==")
}

$targetDirectory = Split-Path -Parent ([IO.Path]::GetFullPath($ConfigPath))
if ([string]::IsNullOrWhiteSpace($targetDirectory)) {
    throw (Get-QuantumRussianText -Encoded "0J/Rg9GC0YwgQ29uZmlnUGF0aCDQtNC+0LvQttC10L0g0YHQvtC00LXRgNC20LDRgtGMINGA0L7QtNC40YLQtdC70YzRgdC60YPRjiDQv9Cw0L/QutGDLg==")
}
New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null

$config = [ordered]@{
    configuration_status = "READY"
    execution_mode = "ADMISSION_ONLY"
    tenant_id = "tenant-home-local"
    account_id = "operator-home-local"
    verifier_account_id = "verifier-home-local"
    source_internal_id = $SourceInternalId
    release_scope = "WB_ONLY"
    marketplace = $Marketplace
    deferred_marketplaces = @("OZON")
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
        source_authority_verified = $false
        report_period_verified = $false
        control_totals_verified = $false
        direct_identifiers_absent_or_approved = $false
        malware_scan_clean = $false
    }
    inspection_policy = [ordered]@{
        policy_id = "wb-home-local-discovery"
        version = 2
        limits = [ordered]@{
            max_file_bytes = 104857600
            max_archive_entries = 10000
            max_total_uncompressed_bytes = 536870912
            max_entry_uncompressed_bytes = 134217728
            max_compression_ratio = 100
            max_xml_bytes = 134217728
            max_rows = 1000000
            max_columns = 500
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
            "email", "phone", "telephone", "mobile", "address",
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
Write-Host (Get-QuantumRussianText -Encoded "0JrQvtC90YTQuNCz0YPRgNCw0YbQuNGPIEhPTUVfTE9DQUwg0YHQvtC30LTQsNC90LAu") -ForegroundColor Green
Write-Host (Get-QuantumRussianText -Encoded "0J/Rg9GC0Yw6IHswfQ==" -Arguments @($ConfigPath))
Write-Host (Get-QuantumRussianText -Encoded "0J7QsdC70LDRgdGC0Ywg0LLQtdGA0YHQuNC4OiBXQl9PTkxZICjQv9C+0LTQtNC10YDQttC60LAgT3pvbiDQvtGC0LvQvtC20LXQvdCwKS4=") -ForegroundColor Cyan
Write-Host (Get-QuantumRussianText -Encoded "0KDQtdC20LjQvDogQURNSVNTSU9OX09OTFkgKNGE0LjQvdCw0L3RgdC+0LLRi9C5INGA0LDRgdGH0ZHRgiDQvtGC0LrQu9GO0YfRkdC9INC00L4g0L/RgNC10LTQvtGB0YLQsNCy0LvQtdC90LjRjyDQv9GA0L7QstC10YDQtdC90L3QvtCz0L4g0YTQuNC90LDQvdGB0L7QstC+0LPQviDQv9GA0L7RhNC40LvRjyku") -ForegroundColor Yellow
