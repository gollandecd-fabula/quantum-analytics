[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ExactHead = [string]$env:TARGET_SHA
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
$EvidenceRoot = Join-Path $RepoRoot "artifacts\l4-installed-runtime"
$MainEvidencePath = Join-Path $EvidenceRoot "L4_INSTALLED_RUNTIME_EVIDENCE.json"
$MainEvidenceShaPath = Join-Path $EvidenceRoot "L4_INSTALLED_RUNTIME_EVIDENCE.sha256"
$PostcheckPath = Join-Path $EvidenceRoot "L4_INDEPENDENT_POSTCHECK_EVIDENCE.json"
$PostcheckShaPath = Join-Path $EvidenceRoot "L4_INDEPENDENT_POSTCHECK_EVIDENCE.sha256"
$BundleManifestPath = Join-Path $EvidenceRoot "EVIDENCE_BUNDLE_MANIFEST.json"

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Write-Json {
    param(
        [Parameter(Mandatory = $true)]$Value,
        [Parameter(Mandatory = $true)][string]$Path,
        [int]$Depth = 30
    )
    $Value | ConvertTo-Json -Depth $Depth | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Get-RelativePath {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Path
    )
    $prefix = [IO.Path]::GetFullPath($Root).TrimEnd("\") + "\"
    $full = [IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw ("PATH_OUTSIDE_EVIDENCE_ROOT:{0}" -f $full)
    }
    return $full.Substring($prefix.Length).Replace("\", "/")
}

function Assert-FileIdentity {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][int64]$ExpectedSize,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256,
        [Parameter(Mandatory = $true)][string]$IdentityName
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw ("FILE_MISSING:{0}" -f $IdentityName)
    }
    $item = Get-Item -LiteralPath $Path
    if ([int64]$item.Length -ne $ExpectedSize) {
        throw ("FILE_SIZE_MISMATCH:{0}" -f $IdentityName)
    }
    $actualHash = Get-Sha256 -Path $Path
    if ($actualHash -ne $ExpectedSha256.ToLowerInvariant()) {
        throw ("FILE_HASH_MISMATCH:{0}" -f $IdentityName)
    }
}

function Write-BundleManifest {
    Remove-Item -LiteralPath $BundleManifestPath -Force -ErrorAction SilentlyContinue
    $records = @()
    foreach ($file in @(Get-ChildItem -LiteralPath $EvidenceRoot -File -Recurse -Force)) {
        $records += [pscustomobject][ordered]@{
            relative_path = Get-RelativePath -Root $EvidenceRoot -Path $file.FullName
            size_bytes = [int64]$file.Length
            sha256 = Get-Sha256 -Path $file.FullName
        }
    }
    Write-Json -Value $records -Path $BundleManifestPath -Depth 10
}

trap {
    $failure = [ordered]@{
        status = "L4_INDEPENDENT_POSTCHECK_FAILED"
        exact_head = $ExactHead
        exception_type = $_.Exception.GetType().FullName
        exception_message = $_.Exception.Message
        script_stack_trace = $_.ScriptStackTrace
        captured_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    }
    Write-Json `
        -Value $failure `
        -Path (Join-Path $EvidenceRoot "L4_INDEPENDENT_POSTCHECK_FAILURE.json")
    exit 1
}

if ($ExactHead -notmatch "^[0-9a-f]{40}$") {
    throw ("TARGET_SHA_INVALID:{0}" -f $ExactHead)
}
if (-not (Test-Path -LiteralPath $MainEvidencePath -PathType Leaf)) {
    throw "MAIN_L4_EVIDENCE_NOT_FOUND"
}
if (-not (Test-Path -LiteralPath $MainEvidenceShaPath -PathType Leaf)) {
    throw "MAIN_L4_EVIDENCE_SIDECAR_NOT_FOUND"
}

$mainEvidenceHash = Get-Sha256 -Path $MainEvidencePath
$declaredMainHash = (
    (Get-Content -LiteralPath $MainEvidenceShaPath -Raw -Encoding ASCII).Trim() -split "\s+"
)[0].ToLowerInvariant()
if ($mainEvidenceHash -ne $declaredMainHash) {
    throw "MAIN_L4_EVIDENCE_HASH_MISMATCH"
}

$main = Get-Content -LiteralPath $MainEvidencePath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$main.status -ne "L4_INSTALLED_RUNTIME_PASS") {
    throw ("MAIN_L4_STATUS_INVALID:{0}" -f $main.status)
}
if ([string]$main.evidence_level -ne "L4_INSTALLED_RUNTIME") {
    throw ("MAIN_L4_LEVEL_INVALID:{0}" -f $main.evidence_level)
}
if ([string]$main.exact_head -ne $ExactHead) {
    throw ("MAIN_L4_HEAD_MISMATCH:{0}" -f $main.exact_head)
}
if ($main.marketplace_write_enabled -ne $false) {
    throw "MAIN_L4_MARKETPLACE_WRITES_ENABLED"
}
if ($main.physical_user_path_verified -ne $false) {
    throw "MAIN_L4_FALSE_PHYSICAL_CLAIM"
}

$runtime = $main.runtime_probe
if ([int]$runtime.alive_after_seconds -lt 8) {
    throw ("RUNTIME_OBSERVATION_TOO_SHORT:{0}" -f $runtime.alive_after_seconds)
}
if ([int64]$runtime.main_window_handle -eq 0) {
    throw "INSTALLED_RUNTIME_GUI_WINDOW_NOT_FOUND"
}
$windowTitle = [string]$runtime.main_window_title
if ([string]::IsNullOrWhiteSpace($windowTitle)) {
    throw "INSTALLED_RUNTIME_GUI_TITLE_EMPTY"
}
if ($windowTitle.IndexOf("Quantum", [StringComparison]::OrdinalIgnoreCase) -lt 0) {
    throw ("INSTALLED_RUNTIME_GUI_TITLE_INVALID:{0}" -f $windowTitle)
}
$installedRoot = [string]$main.installed_root
$commandLine = [string]$runtime.command_line
if ($commandLine.IndexOf($installedRoot, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
    throw "INSTALLED_RUNTIME_COMMAND_NOT_BOUND_TO_ROOT"
}
if ($commandLine.IndexOf("quantum.application.desktop_center", [StringComparison]::OrdinalIgnoreCase) -lt 0) {
    throw "INSTALLED_RUNTIME_COMMAND_NOT_DESKTOP_CENTER"
}

$installedManifestPath = [string]$main.installed_manifest.path
$declaredInstalledManifestHash = [string]$main.installed_manifest.sha256
Assert-FileIdentity `
    -Path $installedManifestPath `
    -ExpectedSize (Get-Item -LiteralPath $installedManifestPath).Length `
    -ExpectedSha256 $declaredInstalledManifestHash `
    -IdentityName "INSTALLED_MANIFEST"

$installedManifest = (
    Get-Content -LiteralPath $installedManifestPath -Raw -Encoding UTF8
) | ConvertFrom-Json
if ([string]$installedManifest.exact_head -ne $ExactHead) {
    throw ("INSTALLED_MANIFEST_HEAD_MISMATCH:{0}" -f $installedManifest.exact_head)
}
if ($installedManifest.marketplace_write_enabled -ne $false) {
    throw "INSTALLED_MANIFEST_MARKETPLACE_WRITES_ENABLED"
}
$managedEntries = @($installedManifest.managed_files)
if ($managedEntries.Count -lt 100) {
    throw ("INSTALLED_MANIFEST_TOO_SMALL:{0}" -f $managedEntries.Count)
}

$targetRelativePath = "src/quantum/application/_finance_center_shared.py"
$targetEntry = @(
    $managedEntries | Where-Object { [string]$_.path -eq $targetRelativePath }
)
if ($targetEntry.Count -ne 1) {
    throw ("TAMPER_TARGET_ENTRY_COUNT:{0}" -f $targetEntry.Count)
}
$targetEntry = $targetEntry[0]
$targetPath = Join-Path $installedRoot $targetRelativePath.Replace("/", "\")
Assert-FileIdentity `
    -Path $targetPath `
    -ExpectedSize ([int64]$targetEntry.size_bytes) `
    -ExpectedSha256 ([string]$targetEntry.sha256) `
    -IdentityName $targetRelativePath

$tamperPath = Join-Path $env:RUNNER_TEMP "quantum-l4-identity-tamper.py"
Remove-Item -LiteralPath $tamperPath -Force -ErrorAction SilentlyContinue
Copy-Item -LiteralPath $targetPath -Destination $tamperPath -Force
$bytes = [IO.File]::ReadAllBytes($tamperPath)
if ($bytes.Length -lt 1) {
    throw "TAMPER_TARGET_EMPTY"
}
$bytes[0] = $bytes[0] -bxor 1
[IO.File]::WriteAllBytes($tamperPath, $bytes)

$tamperRejected = $false
$tamperReason = ""
try {
    Assert-FileIdentity `
        -Path $tamperPath `
        -ExpectedSize ([int64]$targetEntry.size_bytes) `
        -ExpectedSha256 ([string]$targetEntry.sha256) `
        -IdentityName $targetRelativePath
}
catch {
    if ($_.Exception.Message -notlike "FILE_HASH_MISMATCH:*") {
        throw
    }
    $tamperRejected = $true
    $tamperReason = $_.Exception.Message
}
finally {
    Remove-Item -LiteralPath $tamperPath -Force -ErrorAction SilentlyContinue
}
if (-not $tamperRejected) {
    throw "INDEPENDENT_TAMPER_CONTROL_DID_NOT_FAIL"
}

$postcheck = [ordered]@{
    status = "L4_INDEPENDENT_POSTCHECK_PASS"
    evidence_level = "L4_INSTALLED_RUNTIME"
    exact_head = $ExactHead
    main_evidence = [ordered]@{
        path = $MainEvidencePath
        sha256 = $mainEvidenceHash
        sidecar_matches = $true
    }
    installed_manifest = [ordered]@{
        path = $installedManifestPath
        sha256 = Get-Sha256 -Path $installedManifestPath
        managed_file_count = $managedEntries.Count
        exact_head_matches = $true
    }
    gui_runtime = [ordered]@{
        process_id = [int]$runtime.process_id
        executable_path = [string]$runtime.executable_path
        command_line = $commandLine
        main_window_handle = [int64]$runtime.main_window_handle
        main_window_title = $windowTitle
        alive_after_seconds = [int]$runtime.alive_after_seconds
        installed_root_binding = $true
        desktop_center_binding = $true
    }
    tamper_negative_control = [ordered]@{
        target_path = $targetRelativePath
        original_size_bytes = [int64]$targetEntry.size_bytes
        original_sha256 = [string]$targetEntry.sha256
        tampered_size_unchanged = $true
        rejected = $tamperRejected
        rejection_reason = $tamperReason
    }
    marketplace_write_enabled = $false
    physical_user_path_verified = $false
    limitations = @(
        "This independently validates automated installed-runtime L4 evidence.",
        "It does not validate physical-user-path L5.",
        "Merge, deployment and marketplace writes remain disabled."
    )
    captured_at_utc = (Get-Date).ToUniversalTime().ToString("o")
}
Write-Json -Value $postcheck -Path $PostcheckPath -Depth 30
$postcheckHash = Get-Sha256 -Path $PostcheckPath
(
    $postcheckHash +
    "  L4_INDEPENDENT_POSTCHECK_EVIDENCE.json"
) | Set-Content -LiteralPath $PostcheckShaPath -Encoding ASCII
Write-BundleManifest

Write-Host "L4_INDEPENDENT_POSTCHECK_PASS"
exit 0
