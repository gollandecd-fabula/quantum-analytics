[CmdletBinding()]
param([string]$OutputDirectory)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $repositoryRoot "dist"
}
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$OutputDirectory = (Resolve-Path -LiteralPath $OutputDirectory).Path

$stage = Join-Path $OutputDirectory "QuantumAnyFileExtension"
$archive = Join-Path $OutputDirectory "QuantumAnyFileExtension_R3.zip"
Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue

foreach ($directory in @(
    $stage,
    (Join-Path $stage "src\quantum\pilot"),
    (Join-Path $stage "scripts")
)) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}

Copy-Item -LiteralPath (Join-Path $repositoryRoot "src\quantum\pilot\any_file_common.py") -Destination (Join-Path $stage "src\quantum\pilot\any_file_common.py")
Copy-Item -LiteralPath (Join-Path $repositoryRoot "src\quantum\pilot\any_file_detection.py") -Destination (Join-Path $stage "src\quantum\pilot\any_file_detection.py")
Copy-Item -LiteralPath (Join-Path $repositoryRoot "src\quantum\pilot\any_file_gateway.py") -Destination (Join-Path $stage "src\quantum\pilot\any_file_gateway.py")
Copy-Item -LiteralPath (Join-Path $repositoryRoot "src\quantum\pilot\any_file_runner.py") -Destination (Join-Path $stage "src\quantum\pilot\any_file_runner.py")
Copy-Item -LiteralPath (Join-Path $repositoryRoot "scripts\windows\import_any_file.ps1") -Destination (Join-Path $stage "scripts\import_any_file.ps1")
Copy-Item -LiteralPath (Join-Path $repositoryRoot "scripts\windows\install_any_file_extension.ps1") -Destination (Join-Path $stage "scripts\install_any_file_extension.ps1")

$installCmd = @'
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_any_file_extension.ps1"
if errorlevel 1 pause
'@
Set-Content -LiteralPath (Join-Path $stage "INSTALL_ANY_FILE_EXTENSION.cmd") -Value $installCmd -Encoding ASCII

$readme = @'
QUANTUM R3 ANY FILE EXTENSION

1. This extension requires the existing Quantum HOME_LOCAL R2 installation.
2. Extract the ZIP fully.
3. Run INSTALL_ANY_FILE_EXTENSION.cmd.
4. Then run %LOCALAPPDATA%\QuantumLocalProduction\IMPORT_ANY_FILE.cmd.
5. Select any safe file or several files of any extension.
6. Unknown safe formats are preserved as ACCEPTED_UNPARSED.
7. Partially supported formats are ACCEPTED_PARTIAL.
8. Dangerous or corrupted content remains quarantined.
9. Existing config, data and output are preserved.
10. Financial calculation remains blocked until data is normalized.
'@
Set-Content -LiteralPath (Join-Path $stage "README_FIRST.txt") -Value $readme -Encoding UTF8

$sourceCommitOutput = @(& git.exe -C $repositoryRoot rev-parse HEAD)
$sourceCommit = ($sourceCommitOutput -join "").Trim()
if ($LASTEXITCODE -ne 0 -or $sourceCommit -notmatch "^[0-9a-fA-F]{40}$") {
    throw "Exact source commit is required."
}
$sourceBranchOutput = @(& git.exe -C $repositoryRoot branch --show-current)
$sourceBranch = ($sourceBranchOutput -join "").Trim()
if ([string]::IsNullOrWhiteSpace($sourceBranch)) {
    $sourceBranch = "DETACHED_HEAD"
}

$stageFull = [IO.Path]::GetFullPath($stage).TrimEnd([char[]]"\/")
$prefix = $stageFull + [IO.Path]::DirectorySeparatorChar
$files = Get-ChildItem -LiteralPath $stage -Recurse -File |
    Sort-Object FullName |
    ForEach-Object {
        $relative = $_.FullName.Substring($prefix.Length).Replace("\", "/")
        [pscustomobject]@{
            path = $relative
            size_bytes = $_.Length
            sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }

$manifest = [ordered]@{
    package = "QuantumAnyFileExtension"
    package_version = "R3_ANY_FILE_EXTENSION"
    compatible_base = "HOME_LOCAL_R2"
    source_branch = $sourceBranch
    source_commit = $sourceCommit.ToLowerInvariant()
    release_state = "RELEASE_BLOCKED"
    marketplace_write_enabled = $false
    files = @($files)
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $stage "manifest.sha256.json") -Encoding UTF8
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $archive -CompressionLevel Optimal

Write-Host "Extension built." -ForegroundColor Green
Write-Host "Archive: $archive"
Write-Host "SHA-256: $((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant())"
Write-Output $archive
