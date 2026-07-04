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

Write-Host "Building R3 extension from exact repository head..."
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File (Join-Path $PSScriptRoot "build_any_file_extension.ps1") `
    -OutputDirectory $OutputDirectory
if ($LASTEXITCODE -ne 0) {
    throw "Extension build failed with exit code $LASTEXITCODE."
}

$archive = Join-Path $OutputDirectory "QuantumAnyFileExtension_R3.zip"
if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) {
    throw "Extension archive was not produced: $archive"
}

$extractRoot = Join-Path $env:RUNNER_TEMP "quantum-any-extension"
$targetRoot = Join-Path $env:RUNNER_TEMP "quantum-existing-r2"
Remove-Item -LiteralPath $extractRoot -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $targetRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $targetRoot -Force | Out-Null
Expand-Archive -LiteralPath $archive -DestinationPath $extractRoot

$manifestPath = Join-Path $extractRoot "manifest.sha256.json"
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$manifest.package_version -ne "R3_ANY_FILE_EXTENSION") {
    throw "Unexpected extension version: $($manifest.package_version)"
}
$expectedCommit = (& git.exe -C $repositoryRoot rev-parse HEAD).Trim()
if ([string]$manifest.source_commit -ne $expectedCommit) {
    throw "Artifact commit mismatch. Expected $expectedCommit, got $($manifest.source_commit)."
}
foreach ($entry in @($manifest.files)) {
    $path = Join-Path $extractRoot ([string]$entry.path).Replace("/", "\")
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Manifest file missing: $($entry.path)"
    }
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne [string]$entry.sha256) {
        throw "Manifest hash mismatch: $($entry.path)"
    }
}

Copy-Item -LiteralPath (Join-Path $repositoryRoot "src") `
    -Destination (Join-Path $targetRoot "src") -Recurse -Force
foreach ($name in @("config", "data", "output", "scripts")) {
    New-Item -ItemType Directory -Path (Join-Path $targetRoot $name) -Force | Out-Null
}
foreach ($name in @("config", "data", "output")) {
    Set-Content -LiteralPath (Join-Path $targetRoot "$name\sentinel.txt") `
        -Value $name -Encoding ASCII
}

Write-Host "Installing extension over simulated R2 runtime..."
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File (Join-Path $extractRoot "scripts\install_any_file_extension.ps1") `
    -SourceRoot $extractRoot `
    -TargetRoot $targetRoot
if ($LASTEXITCODE -ne 0) {
    throw "Extension installation failed with exit code $LASTEXITCODE."
}

foreach ($name in @("config", "data", "output")) {
    $sentinel = Join-Path $targetRoot "$name\sentinel.txt"
    if (-not (Test-Path -LiteralPath $sentinel -PathType Leaf)) {
        throw "User data sentinel was removed: $sentinel"
    }
}
foreach ($required in @(
    (Join-Path $targetRoot "src\quantum\pilot\any_file_common.py"),
    (Join-Path $targetRoot "src\quantum\pilot\any_file_detection.py"),
    (Join-Path $targetRoot "src\quantum\pilot\any_file_gateway.py"),
    (Join-Path $targetRoot "src\quantum\pilot\any_file_runner.py"),
    (Join-Path $targetRoot "scripts\import_any_file.ps1"),
    (Join-Path $targetRoot "IMPORT_ANY_FILE.cmd")
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Installed extension file missing: $required"
    }
}

$sample = Join-Path $env:RUNNER_TEMP "quantum-any-sample.json"
$config = Join-Path $env:RUNNER_TEMP "quantum-any-config.json"
$output = Join-Path $targetRoot "output\any-file-smoke.json"
[IO.File]::WriteAllText($sample, '{"orders":3}', ([Text.UTF8Encoding]::new($false)))
[IO.File]::WriteAllText($config, '{}', ([Text.UTF8Encoding]::new($false)))
$hash = (Get-FileHash -LiteralPath $sample -Algorithm SHA256).Hash.ToLowerInvariant()
$env:PYTHONPATH = Join-Path $targetRoot "src"
python -m quantum.pilot.any_file_runner `
    --file $sample `
    --config $config `
    --storage-root (Join-Path $targetRoot "data") `
    --output $output `
    --home-local `
    --authority-attested `
    --schema-reviewed `
    --expected-file-sha256 $hash
if ($LASTEXITCODE -ne 0) {
    throw "Installed universal runner smoke test failed with exit code $LASTEXITCODE."
}
$report = Get-Content -LiteralPath $output -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$report.status -ne "ACCEPTED_PARTIAL") {
    throw "Unexpected smoke-test status: $($report.status)"
}

Write-Host "R3 extension build, manifest, install and smoke test passed." -ForegroundColor Green
Write-Host "Archive: $archive"
Write-Output $archive
