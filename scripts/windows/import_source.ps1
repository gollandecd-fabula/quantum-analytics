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
        [Parameter(Mandatory = $true)][string[]]$Prefix
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
        return
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
        throw "Configuration template is not ready. Fill it and save it as config\default-home-local.json or config\production.local.json."
    }
    $financeProperty = $raw.PSObject.Properties["finance_request"]
    if (-not $financeProperty -or $null -eq $financeProperty.Value) {
        throw "Configuration has no finance_request object: $Path"
    }
    $placeholderProperty = $financeProperty.Value.PSObject.Properties["replace_with_a_valid_versioned_finance_request"]
    if ($placeholderProperty -and $placeholderProperty.Value -eq $true) {
        throw "Configuration still contains a finance_request placeholder: $Path"
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
        throw "No ready Quantum configuration was found. Fill $template and save it as config\default-home-local.json."
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

Invoke-DefenderScan -Path $File

Write-Host "Runtime profile: HOME_LOCAL" -ForegroundColor Cyan
Write-Host "Disk encryption is not required in HOME_LOCAL. The result will record the unencrypted-storage limitation." -ForegroundColor Yellow

Confirm-Literal -Expected "AUTHORIZE" -Prompt "Type AUTHORIZE to attest lawful authority to process this report" -AlreadyAttested ([bool]$AuthorityAttested)
Confirm-Literal -Expected "REVIEWED" -Prompt "Type REVIEWED to approve automatic sheet/header discovery for this selected report" -AlreadyAttested ([bool]$SchemaReviewed)

$pythonCommand = Resolve-PythonCommand
$env:PYTHONPATH = Join-Path $projectRoot "src"

$arguments = @()
$arguments += $pythonCommand.Prefix
$arguments += @(
    "-m", "quantum.pilot.windows_runner",
    "--file", $File,
    "--config", $Config,
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

Write-Host "Import completed." -ForegroundColor Green
Write-Host "Report: $Output"
