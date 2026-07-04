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
    $candidate = Join-Path $PSScriptRoot "..\.."
    return (Resolve-Path -LiteralPath $candidate).Path
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

function Resolve-PythonCommand {
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($python) {
        return [pscustomobject]@{ Executable = $python.Source; Prefix = @() }
    }
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) {
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

function Invoke-DefenderScan {
    param([Parameter(Mandatory = $true)][string]$Path)
    if ($SkipDefenderScan) {
        Write-Host "Defender scan skipped by explicit switch." -ForegroundColor Yellow
        return
    }
    $scanner = Join-Path $env:ProgramFiles "Windows Defender\MpCmdRun.exe"
    if (-not (Test-Path -LiteralPath $scanner -PathType Leaf)) {
        throw "Microsoft Defender command-line scanner was not found. Use -SkipDefenderScan only after an equivalent scan."
    }
    Write-Host "Scanning source file with Microsoft Defender..."
    & $scanner -Scan -ScanType 3 -File $Path | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Microsoft Defender scan failed or reported a threat. Exit code: $LASTEXITCODE"
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
        (Join-Path $env:LOCALAPPDATA "QuantumLocalProduction\config\default-production.json"),
        (Join-Path $projectRoot "config\home-local.template.json")
    )
    $Config = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $Config) {
        throw "No Quantum configuration was found. Create config\production.local.json first."
    }
}
$Config = (Resolve-Path -LiteralPath $Config).Path

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
