[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$CurrentStep = "INITIALIZE"
$ExactHead = [string]$env:TARGET_SHA
$RepositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
$EvidenceRoot = Join-Path $RepositoryRoot "artifacts\l4-installed-runtime"
$BuildRoot = Join-Path $RepositoryRoot "dist\l4-installed-runtime-build"
$ExtractRoot = Join-Path $env:RUNNER_TEMP "quantum-l4-package"
$InstallRoot = Join-Path $env:RUNNER_TEMP "quantum-l4-installed"
$TamperRoot = Join-Path $env:RUNNER_TEMP "quantum-l4-tampered"

foreach ($path in @($EvidenceRoot, $BuildRoot, $ExtractRoot, $InstallRoot, $TamperRoot)) {
    Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Path $EvidenceRoot -Force | Out-Null

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Write-Json {
    param(
        [Parameter(Mandatory = $true)]$Value,
        [Parameter(Mandatory = $true)][string]$Path,
        [int]$Depth = 40
    )
    $Value | ConvertTo-Json -Depth $Depth | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Get-RelativePath {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Path
    )
    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd("\") + "\"
    $pathFull = [IO.Path]::GetFullPath($Path)
    if (-not $pathFull.StartsWith($rootFull, [StringComparison]::OrdinalIgnoreCase)) {
        throw "PATH_OUTSIDE_ROOT:$pathFull"
    }
    return $pathFull.Substring($rootFull.Length).Replace("\", "/")
}

function Get-FileRecord {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Path
    )
    $item = Get-Item -LiteralPath $Path
    return [pscustomobject][ordered]@{
        path = Get-RelativePath -Root $Root -Path $item.FullName
        size_bytes = [int64]$item.Length
        sha256 = Get-Sha256 -Path $item.FullName
    }
}

function Get-UserSentinels {
    param([Parameter(Mandatory = $true)][string]$Root)
    $records = @()
    foreach ($name in @("config", "data", "output")) {
        $directory = Join-Path $Root $name
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
        $sentinel = Join-Path $directory ("l4-user-sentinel-" + $name + ".txt")
        [IO.File]::WriteAllText($sentinel, "L4_USER_SENTINEL_" + $name, [Text.Encoding]::ASCII)
        $records += Get-FileRecord -Root $Root -Path $sentinel
    }
    return $records
}

function Assert-UserSentinels {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)]$Expected
    )
    $actual = @()
    foreach ($entry in @($Expected)) {
        $path = Join-Path $Root ([string]$entry.path).Replace("/", "\")
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "USER_SENTINEL_MISSING:$($entry.path)"
        }
        $record = Get-FileRecord -Root $Root -Path $path
        if ($record.size_bytes -ne [int64]$entry.size_bytes -or $record.sha256 -ne [string]$entry.sha256) {
            throw "USER_SENTINEL_CHANGED:$($entry.path)"
        }
        $actual += $record
    }
    return $actual
}

function Get-ExpectedManagedEntries {
    param(
        [Parameter(Mandatory = $true)]$PackageManifest,
        [Parameter(Mandatory = $true)][string]$PackageRoot
    )
    $entries = @()
    foreach ($entry in @($PackageManifest.files)) {
        $relative = ([string]$entry.path).Replace("\", "/")
        if (
            $relative.StartsWith("src/", [StringComparison]::OrdinalIgnoreCase) -or
            $relative -in @(
                "scripts/import_source.ps1",
                "scripts/configure_home_local.ps1",
                "scripts/one_click_home_local.ps1",
                "README_FIRST.txt"
            )
        ) {
            $entries += [pscustomobject][ordered]@{
                path = $relative
                size_bytes = [int64]$entry.size_bytes
                sha256 = ([string]$entry.sha256).ToLowerInvariant()
            }
        }
    }
    return @($entries | Sort-Object path)
}

function Get-ActualManagedEntries {
    param([Parameter(Mandatory = $true)][string]$Root)
    $files = @()
    $src = Join-Path $Root "src"
    $scripts = Join-Path $Root "scripts"
    if (Test-Path -LiteralPath $src -PathType Container) {
        $files += @(Get-ChildItem -LiteralPath $src -File -Recurse -Force)
    }
    foreach ($name in @("import_source.ps1", "configure_home_local.ps1", "one_click_home_local.ps1")) {
        $candidate = Join-Path $scripts $name
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            $files += Get-Item -LiteralPath $candidate
        }
    }
    $readme = Join-Path $Root "README_FIRST.txt"
    if (Test-Path -LiteralPath $readme -PathType Leaf) {
        $files += Get-Item -LiteralPath $readme
    }
    $records = @()
    foreach ($file in @($files)) {
        $records += Get-FileRecord -Root $Root -Path $file.FullName
    }
    return @($records | Sort-Object path)
}

function Assert-ManagedTree {
    param(
        [Parameter(Mandatory = $true)]$Expected,
        [Parameter(Mandatory = $true)]$Actual
    )
    if (@($Expected).Count -ne @($Actual).Count) {
        throw "MANAGED_FILE_COUNT_MISMATCH:expected=$(@($Expected).Count);actual=$(@($Actual).Count)"
    }
    for ($index = 0; $index -lt @($Expected).Count; $index++) {
        $left = @($Expected)[$index]
        $right = @($Actual)[$index]
        if ([string]$left.path -ne [string]$right.path) {
            throw "MANAGED_PATH_MISMATCH:$($left.path):$($right.path)"
        }
        if ([int64]$left.size_bytes -ne [int64]$right.size_bytes) {
            throw "MANAGED_SIZE_MISMATCH:$($left.path)"
        }
        if ([string]$left.sha256 -ne [string]$right.sha256) {
            throw "MANAGED_HASH_MISMATCH:$($left.path)"
        }
    }
}

function Assert-LauncherContracts {
    param([Parameter(Mandatory = $true)][string]$Root)
    $expected = [ordered]@{
        "START_QUANTUM.cmd" = @(
            "@echo off",
            "setlocal",
            "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"%~dp0scripts\one_click_home_local.ps1\" -InstalledRoot \"%~dp0\" -SkipInstall",
            "set \"quantum_exit=%errorlevel%\"",
            "if not \"%quantum_exit%\"==\"0\" pause",
            "exit /b %quantum_exit%"
        )
        "IMPORT_XLSX.cmd" = @(
            "@echo off",
            "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"%~dp0scripts\import_source.ps1\"",
            "if errorlevel 1 pause"
        )
        "CONFIGURE_HOME_LOCAL.cmd" = @(
            "@echo off",
            "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"%~dp0scripts\configure_home_local.ps1\"",
            "if errorlevel 1 pause"
        )
    }
    $records = @()
    foreach ($name in $expected.Keys) {
        $path = Join-Path $Root $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "INSTALLED_LAUNCHER_MISSING:$name"
        }
        $lines = @(
            (Get-Content -LiteralPath $path -Encoding ASCII) |
                ForEach-Object { ([string]$_).TrimEnd() } |
                Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
        )
        $wanted = @($expected[$name])
        if ($lines.Count -ne $wanted.Count) {
            throw "INSTALLED_LAUNCHER_LINE_COUNT:$name"
        }
        for ($index = 0; $index -lt $wanted.Count; $index++) {
            if ($lines[$index] -cne $wanted[$index]) {
                throw "INSTALLED_LAUNCHER_CONTENT:$name:$index"
            }
        }
        $records += Get-FileRecord -Root $Root -Path $path
    }
    return @($records | Sort-Object path)
}

function Invoke-InstalledSelfTest {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Config
    )
    $previousPythonPath = $env:PYTHONPATH
    try {
        $env:PYTHONPATH = Join-Path $Root "src"
        $stdout = Join-Path $EvidenceRoot "installed-self-test.stdout.txt"
        $stderr = Join-Path $EvidenceRoot "installed-self-test.stderr.txt"
        $output = @(python -m quantum.application.desktop_center --root $Root --config $Config --self-test 2>&1)
        $exitCode = $LASTEXITCODE
        $output | Set-Content -LiteralPath $stdout -Encoding UTF8
        "" | Set-Content -LiteralPath $stderr -Encoding UTF8
        if ($exitCode -ne 0) {
            throw "INSTALLED_SELF_TEST_EXIT:$exitCode"
        }
        $jsonLine = @($output | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })[-1]
        $result = ([string]$jsonLine) | ConvertFrom-Json
        if ([string]$result.status -ne "DESKTOP_CENTER_SELF_TEST_PASS") {
            throw "INSTALLED_SELF_TEST_STATUS:$($result.status)"
        }
        if ($result.marketplace_write_enabled -ne $false) {
            throw "INSTALLED_SELF_TEST_MARKETPLACE_WRITES"
        }
        if ([string]$result.finance_center.status -ne "FINANCE_CENTER_SELF_TEST_PASS") {
            throw "INSTALLED_FINANCE_CENTER_SELF_TEST_STATUS:$($result.finance_center.status)"
        }
        return [ordered]@{
            exit_code = $exitCode
            status = [string]$result.status
            finance_center_status = [string]$result.finance_center.status
            marketplace_write_enabled = [bool]$result.marketplace_write_enabled
            stdout_sha256 = Get-Sha256 -Path $stdout
            stderr_sha256 = Get-Sha256 -Path $stderr
        }
    }
    finally {
        $env:PYTHONPATH = $previousPythonPath
    }
}

function Invoke-TaxBaseProbe {
    param([Parameter(Mandatory = $true)][string]$Root)
    $previousPythonPath = $env:PYTHONPATH
    try {
        $env:PYTHONPATH = Join-Path $Root "src"
        $stdout = Join-Path $EvidenceRoot "installed-tax-base.stdout.txt"
        $stderr = Join-Path $EvidenceRoot "installed-tax-base.stderr.txt"
        $code = "from quantum.application import _finance_center_reports as r; assert 'gross_sales_amount' in r.TAX_BASE_OPTIONS; print('INSTALLED_TAX_BASE_IMPORT_PASS')"
        $output = @(python -c $code 2>&1)
        $exitCode = $LASTEXITCODE
        $output | Set-Content -LiteralPath $stdout -Encoding UTF8
        "" | Set-Content -LiteralPath $stderr -Encoding UTF8
        if ($exitCode -ne 0 -or ($output -join "`n") -notmatch "INSTALLED_TAX_BASE_IMPORT_PASS") {
            throw "INSTALLED_TAX_BASE_PROBE_FAILED:$exitCode"
        }
        return [ordered]@{
            exit_code = $exitCode
            stdout_sha256 = Get-Sha256 -Path $stdout
            stderr_sha256 = Get-Sha256 -Path $stderr
        }
    }
    finally {
        $env:PYTHONPATH = $previousPythonPath
    }
}

function Invoke-RuntimeProbe {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Config
    )
    $previousPythonPath = $env:PYTHONPATH
    $process = $null
    try {
        $env:PYTHONPATH = Join-Path $Root "src"
        $stdout = Join-Path $EvidenceRoot "installed-runtime.stdout.txt"
        $stderr = Join-Path $EvidenceRoot "installed-runtime.stderr.txt"
        $arguments = @(
            "-m",
            "quantum.application.desktop_center",
            "--root",
            $Root,
            "--config",
            $Config
        )
        $process = Start-Process -FilePath "python.exe" -ArgumentList $arguments -WorkingDirectory $Root -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
        Start-Sleep -Seconds 8
        $process.Refresh()
        if ($process.HasExited) {
            throw "INSTALLED_RUNTIME_EXITED:$($process.ExitCode)"
        }
        $cim = Get-CimInstance Win32_Process -Filter ("ProcessId = " + $process.Id)
        $runtime = Get-Process -Id $process.Id
        $record = [ordered]@{
            process_id = [int]$process.Id
            executable_path = [string]$cim.ExecutablePath
            command_line = [string]$cim.CommandLine
            main_window_handle = [int64]$runtime.MainWindowHandle
            main_window_title = [string]$runtime.MainWindowTitle
            alive_after_seconds = 8
            stdout_sha256 = Get-Sha256 -Path $stdout
            stderr_sha256 = Get-Sha256 -Path $stderr
        }
        return $record
    }
    finally {
        if ($null -ne $process) {
            try {
                $process.Refresh()
                if (-not $process.HasExited) {
                    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
                    Wait-Process -Id $process.Id -Timeout 10 -ErrorAction SilentlyContinue
                }
            }
            catch {
            }
        }
        $env:PYTHONPATH = $previousPythonPath
    }
}

function Test-TamperRejection {
    param(
        [Parameter(Mandatory = $true)][string]$SourceRoot,
        [Parameter(Mandatory = $true)]$Expected
    )
    Copy-Item -LiteralPath $SourceRoot -Destination $TamperRoot -Recurse -Force
    $target = Join-Path $TamperRoot "src\quantum\application\_finance_center_shared.py"
    Add-Content -LiteralPath $target -Value "# l4 tamper negative control" -Encoding ASCII
    $actual = Get-ActualManagedEntries -Root $TamperRoot
    try {
        Assert-ManagedTree -Expected $Expected -Actual $actual
    }
    catch {
        return [ordered]@{
            rejected = $true
            exception_type = $_.Exception.GetType().FullName
            exception_message = $_.Exception.Message
        }
    }
    throw "TAMPER_NEGATIVE_CONTROL_DID_NOT_FAIL"
}

trap {
    $failure = [ordered]@{
        status = "L4_INSTALLED_RUNTIME_FAILED"
        exact_head = $ExactHead
        step = $CurrentStep
        exception_type = $_.Exception.GetType().FullName
        exception_message = $_.Exception.Message
        script_stack_trace = $_.ScriptStackTrace
        captured_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    }
    Write-Json -Value $failure -Path (Join-Path $EvidenceRoot "L4_FAILURE.json")
    exit 1
}

$CurrentStep = "EXACT_HEAD"
if ($ExactHead -notmatch "^[0-9a-f]{40}$") {
    throw "TARGET_SHA_INVALID:$ExactHead"
}
$actualHead = (& git -C $RepositoryRoot rev-parse HEAD).Trim().ToLowerInvariant()
if ($actualHead -ne $ExactHead.ToLowerInvariant()) {
    throw "EXACT_HEAD_MISMATCH:$actualHead"
}

$CurrentStep = "PINNED_DEPENDENCIES"
python -m pip install --disable-pip-version-check --no-deps --only-binary=:all: --require-hashes -r requirements/windows-home-local.txt
if ($LASTEXITCODE -ne 0) {
    throw "PINNED_DEPENDENCY_INSTALL_FAILED:$LASTEXITCODE"
}

$CurrentStep = "CONTRACT_TEST"
$env:PYTHONPATH = "src"
python -m unittest tests.test_l4_installed_runtime_contract -v
if ($LASTEXITCODE -ne 0) {
    throw "L4_CONTRACT_TEST_FAILED:$LASTEXITCODE"
}

$CurrentStep = "PACKAGE_BUILD"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\build_local_production.ps1 -OutputDirectory $BuildRoot
if ($LASTEXITCODE -ne 0) {
    throw "L4_PACKAGE_BUILD_FAILED:$LASTEXITCODE"
}
$archive = Join-Path $BuildRoot "QuantumLocalProduction_HOME_LOCAL.zip"
if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) {
    throw "L4_PACKAGE_NOT_FOUND"
}
$packageHash = Get-Sha256 -Path $archive

$CurrentStep = "PACKAGE_VERIFY"
Expand-Archive -LiteralPath $archive -DestinationPath $ExtractRoot
$packageManifestPath = Join-Path $ExtractRoot "manifest.sha256.json"
$packageManifest = Get-Content -LiteralPath $packageManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$packageManifest.source_commit -ne $ExactHead) {
    throw "PACKAGE_HEAD_MISMATCH:$($packageManifest.source_commit)"
}
if ($packageManifest.marketplace_write_enabled -ne $false) {
    throw "PACKAGE_MARKETPLACE_WRITES_ENABLED"
}
$expectedManaged = Get-ExpectedManagedEntries -PackageManifest $packageManifest -PackageRoot $ExtractRoot
if ($expectedManaged.Count -lt 100) {
    throw "EXPECTED_MANAGED_SET_TOO_SMALL:$($expectedManaged.Count)"
}

$CurrentStep = "USER_SENTINELS"
$userSentinels = Get-UserSentinels -Root $InstallRoot

$CurrentStep = "FIRST_INSTALL"
$installer = Join-Path $ExtractRoot "scripts\install_home_local.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer -SourceRoot $ExtractRoot -TargetRoot $InstallRoot
if ($LASTEXITCODE -ne 0) {
    throw "FIRST_INSTALL_FAILED:$LASTEXITCODE"
}
$firstSentinels = Assert-UserSentinels -Root $InstallRoot -Expected $userSentinels
$firstManaged = Get-ActualManagedEntries -Root $InstallRoot
Assert-ManagedTree -Expected $expectedManaged -Actual $firstManaged
$firstLaunchers = Assert-LauncherContracts -Root $InstallRoot

$CurrentStep = "SECOND_INSTALL"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer -SourceRoot $ExtractRoot -TargetRoot $InstallRoot
if ($LASTEXITCODE -ne 0) {
    throw "SECOND_INSTALL_FAILED:$LASTEXITCODE"
}
$secondSentinels = Assert-UserSentinels -Root $InstallRoot -Expected $userSentinels
$secondManaged = Get-ActualManagedEntries -Root $InstallRoot
Assert-ManagedTree -Expected $expectedManaged -Actual $secondManaged
$secondLaunchers = Assert-LauncherContracts -Root $InstallRoot
if (@(Get-ChildItem -LiteralPath $InstallRoot -Directory -Filter ".installing_*").Count -ne 0) {
    throw "STALE_INSTALL_TRANSACTION_FOUND"
}
if (@(Get-ChildItem -LiteralPath $InstallRoot -Directory -Filter "src.backup_*").Count -lt 1) {
    throw "SECOND_INSTALL_BACKUP_NOT_FOUND"
}

$CurrentStep = "CONFIGURE_INSTALLED_RUNTIME"
$configPath = Join-Path $InstallRoot "config\default-home-local.json"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $InstallRoot "scripts\configure_home_local.ps1") -ConfigPath $configPath -ReportingPeriodStart "2026-07-01" -ReportingPeriodEnd "2026-07-04" -RetentionDeadline "2030-01-01" -SourceInternalId "l4-installed-runtime" -NonInteractive
if ($LASTEXITCODE -ne 0) {
    throw "INSTALLED_CONFIGURE_FAILED:$LASTEXITCODE"
}

$CurrentStep = "INSTALLED_SELF_TEST"
$selfTest = Invoke-InstalledSelfTest -Root $InstallRoot -Config $configPath

$CurrentStep = "INSTALLED_TAX_BASE"
$taxProbe = Invoke-TaxBaseProbe -Root $InstallRoot

$CurrentStep = "INSTALLED_RUNTIME_STARTUP"
$runtimeProbe = Invoke-RuntimeProbe -Root $InstallRoot -Config $configPath

$CurrentStep = "TAMPER_NEGATIVE_CONTROL"
$tamper = Test-TamperRejection -SourceRoot $InstallRoot -Expected $expectedManaged

$CurrentStep = "EVIDENCE"
$installedEvidenceManifest = [ordered]@{
    schema_version = "quantum-l4-installed-manifest-v1"
    exact_head = $ExactHead
    source_package_sha256 = $packageHash
    release_state = "RELEASE_BLOCKED"
    marketplace_write_enabled = $false
    managed_files = $secondManaged
    launchers = $secondLaunchers
}
$installedManifestPath = Join-Path $EvidenceRoot "INSTALLED_MANIFEST.json"
Write-Json -Value $installedEvidenceManifest -Path $installedManifestPath -Depth 20

$result = [ordered]@{
    status = "L4_INSTALLED_RUNTIME_PASS"
    evidence_level = "L4_INSTALLED_RUNTIME"
    exact_head = $ExactHead
    source_package = [ordered]@{
        path = $archive
        size_bytes = (Get-Item -LiteralPath $archive).Length
        sha256 = $packageHash
        package_manifest_sha256 = Get-Sha256 -Path $packageManifestPath
        managed_file_count = $expectedManaged.Count
    }
    installed_root = $InstallRoot
    first_install = [ordered]@{
        user_sentinels = $firstSentinels
        managed_file_count = $firstManaged.Count
        launchers = $firstLaunchers
    }
    second_install = [ordered]@{
        user_sentinels = $secondSentinels
        managed_file_count = $secondManaged.Count
        launchers = $secondLaunchers
        runtime_backup_count = @(Get-ChildItem -LiteralPath $InstallRoot -Directory -Filter "src.backup_*").Count
    }
    installed_self_test = $selfTest
    tax_base_probe = $taxProbe
    runtime_probe = $runtimeProbe
    tamper_negative_control = $tamper
    installed_manifest = [ordered]@{
        path = $installedManifestPath
        sha256 = Get-Sha256 -Path $installedManifestPath
    }
    marketplace_write_enabled = $false
    physical_user_path_verified = $false
    limitations = @(
        "This workflow proves automated installed-runtime L4 on a GitHub-hosted Windows runner.",
        "It does not prove physical-user-path L5 on the operator workstation.",
        "Merge, deployment and marketplace writes remain disabled."
    )
    captured_at_utc = (Get-Date).ToUniversalTime().ToString("o")
}
$resultPath = Join-Path $EvidenceRoot "L4_INSTALLED_RUNTIME_EVIDENCE.json"
Write-Json -Value $result -Path $resultPath -Depth 50
(Get-Sha256 -Path $resultPath) + "  L4_INSTALLED_RUNTIME_EVIDENCE.json" | Set-Content -LiteralPath (Join-Path $EvidenceRoot "L4_INSTALLED_RUNTIME_EVIDENCE.sha256") -Encoding ASCII

$bundleManifest = @()
foreach ($file in @(Get-ChildItem -LiteralPath $EvidenceRoot -File -Recurse -Force)) {
    $bundleManifest += [pscustomobject][ordered]@{
        relative_path = Get-RelativePath -Root $EvidenceRoot -Path $file.FullName
        size_bytes = [int64]$file.Length
        sha256 = Get-Sha256 -Path $file.FullName
    }
}
Write-Json -Value $bundleManifest -Path (Join-Path $EvidenceRoot "EVIDENCE_BUNDLE_MANIFEST.json") -Depth 10

Write-Host "L4_INSTALLED_RUNTIME_PASS"
exit 0
