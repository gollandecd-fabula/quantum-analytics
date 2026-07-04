[CmdletBinding()]
param(
    [string]$SourceRoot,
    [string]$TargetRoot = (Join-Path $env:LOCALAPPDATA "QuantumLocalProduction")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-Manifest {
    param([Parameter(Mandatory = $true)][string]$Root)
    $path = Join-Path $Root "manifest.sha256.json"
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Extension manifest is missing: $path"
    }
    $manifest = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([string]$manifest.package -ne "QuantumAnyFileExtension") {
        throw "Unexpected extension package identity."
    }
    if ([string]$manifest.package_version -ne "R3_ANY_FILE_EXTENSION") {
        throw "Unexpected extension package version."
    }
    if ([string]$manifest.release_state -ne "RELEASE_BLOCKED") {
        throw "Unexpected extension release state."
    }
    if ($manifest.marketplace_write_enabled -ne $false) {
        throw "Marketplace writes must remain disabled."
    }
    if ([string]$manifest.source_commit -notmatch "^[0-9a-fA-F]{40}$") {
        throw "Extension source commit is invalid."
    }

    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd([char[]]"\/")
    $rootPrefix = $rootFull + [IO.Path]::DirectorySeparatorChar
    $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($entry in @($manifest.files)) {
        $relative = [string]$entry.path
        $normalized = $relative.Replace("/", "\")
        if ([IO.Path]::IsPathRooted($normalized) -or $normalized.Split("\") -contains "..") {
            throw "Unsafe manifest path: $relative"
        }
        $full = [IO.Path]::GetFullPath((Join-Path $rootFull $normalized))
        if (-not $full.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Manifest path escaped package root: $relative"
        }
        if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
            throw "Manifest file is missing: $relative"
        }
        if (-not $seen.Add($relative.Replace("\", "/"))) {
            throw "Duplicate manifest path: $relative"
        }
        $item = Get-Item -LiteralPath $full
        if ([int64]$entry.size_bytes -ne [int64]$item.Length) {
            throw "Manifest size mismatch: $relative"
        }
        $actual = (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne ([string]$entry.sha256).ToLowerInvariant()) {
            throw "Manifest hash mismatch: $relative"
        }
    }
    foreach ($required in @(
        "src/quantum/pilot/any_file_common.py",
        "src/quantum/pilot/any_file_detection.py",
        "src/quantum/pilot/any_file_gateway.py",
        "src/quantum/pilot/any_file_runner.py",
        "scripts/import_any_file.ps1"
    )) {
        if (-not $seen.Contains($required)) {
            throw "Required extension file is not manifested: $required"
        }
    }
    return $manifest
}

function Reset-Acl {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    & icacls.exe $Path /inheritance:e /reset /C | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "ACL repair failed for $Path"
    }
}

if ([string]::IsNullOrWhiteSpace($SourceRoot)) {
    $SourceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
}
else {
    $SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
}
$TargetRoot = [IO.Path]::GetFullPath($TargetRoot)
$manifest = Assert-Manifest -Root $SourceRoot

$baseRunner = Join-Path $TargetRoot "src\quantum\pilot\windows_runner.py"
if (-not (Test-Path -LiteralPath $baseRunner -PathType Leaf)) {
    throw "Compatible Quantum HOME_LOCAL R2 installation was not found: $baseRunner"
}
$baseText = Get-Content -LiteralPath $baseRunner -Raw -Encoding UTF8
if ($baseText -notmatch "HOME_LOCAL_SOURCE_FILE_HASH_MISMATCH") {
    throw "Installed Quantum runtime is too old for the R3 any-file extension."
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupRoot = Join-Path $TargetRoot ("any_file_extension.backup_" + $timestamp)
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null

$mappings = @(
    [pscustomobject]@{
        Source = Join-Path $SourceRoot "src\quantum\pilot\any_file_common.py"
        Target = Join-Path $TargetRoot "src\quantum\pilot\any_file_common.py"
    },
    [pscustomobject]@{
        Source = Join-Path $SourceRoot "src\quantum\pilot\any_file_detection.py"
        Target = Join-Path $TargetRoot "src\quantum\pilot\any_file_detection.py"
    },
    [pscustomobject]@{
        Source = Join-Path $SourceRoot "src\quantum\pilot\any_file_gateway.py"
        Target = Join-Path $TargetRoot "src\quantum\pilot\any_file_gateway.py"
    },
    [pscustomobject]@{
        Source = Join-Path $SourceRoot "src\quantum\pilot\any_file_runner.py"
        Target = Join-Path $TargetRoot "src\quantum\pilot\any_file_runner.py"
    },
    [pscustomobject]@{
        Source = Join-Path $SourceRoot "scripts\import_any_file.ps1"
        Target = Join-Path $TargetRoot "scripts\import_any_file.ps1"
    }
)

foreach ($mapping in $mappings) {
    $targetDirectory = Split-Path -Parent $mapping.Target
    New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
    Reset-Acl -Path $mapping.Target
    if (Test-Path -LiteralPath $mapping.Target -PathType Leaf) {
        Copy-Item -LiteralPath $mapping.Target -Destination (Join-Path $backupRoot ([IO.Path]::GetFileName($mapping.Target))) -Force
    }
    $temporary = $mapping.Target + ".installing_" + [guid]::NewGuid().ToString("N")
    Copy-Item -LiteralPath $mapping.Source -Destination $temporary -Force
    Move-Item -LiteralPath $temporary -Destination $mapping.Target -Force
    Reset-Acl -Path $mapping.Target
}

$cmd = @'
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\import_any_file.ps1"
if errorlevel 1 pause
'@
$commandTarget = Join-Path $TargetRoot "IMPORT_ANY_FILE.cmd"
Set-Content -LiteralPath $commandTarget -Value $cmd -Encoding ASCII
Reset-Acl -Path $commandTarget

$marker = [ordered]@{
    package = "QuantumAnyFileExtension"
    package_version = [string]$manifest.package_version
    source_commit = [string]$manifest.source_commit
    installed_at_utc = [DateTime]::UtcNow.ToString("o")
    release_state = "RELEASE_BLOCKED"
    marketplace_write_enabled = $false
}
$marker | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $TargetRoot "ANY_FILE_EXTENSION.json") -Encoding UTF8

foreach ($required in @(
    (Join-Path $TargetRoot "src\quantum\pilot\any_file_common.py"),
    (Join-Path $TargetRoot "src\quantum\pilot\any_file_detection.py"),
    (Join-Path $TargetRoot "src\quantum\pilot\any_file_gateway.py"),
    (Join-Path $TargetRoot "src\quantum\pilot\any_file_runner.py"),
    (Join-Path $TargetRoot "scripts\import_any_file.ps1"),
    $commandTarget
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Extension installation verification failed: $required"
    }
    $stream = [IO.File]::Open($required, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    $stream.Dispose()
}

Write-Host "Quantum R3 universal file extension installed." -ForegroundColor Green
Write-Host "Launch: $commandTarget"
Write-Host "Existing config, data and output were preserved."
