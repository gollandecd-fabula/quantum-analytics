[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$Step = "INIT"
$ExactHead = [string]$env:TARGET_SHA
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
$EvidenceRoot = Join-Path $RepoRoot "artifacts\l4-installed-runtime"
$BuildRoot = Join-Path $RepoRoot "dist\l4-installed-runtime-build"
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
    $prefix = [IO.Path]::GetFullPath($Root).TrimEnd("\") + "\"
    $full = [IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw ("PATH_OUTSIDE_ROOT:{0}" -f $full)
    }
    return $full.Substring($prefix.Length).Replace("\", "/")
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

function New-UserSentinels {
    param([Parameter(Mandatory = $true)][string]$Root)
    $records = @()
    foreach ($name in @("config", "data", "output")) {
        $directory = Join-Path $Root $name
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
        $sentinel = Join-Path $directory ("l4-user-sentinel-" + $name + ".txt")
        [IO.File]::WriteAllText(
            $sentinel,
            "L4_USER_SENTINEL_" + $name,
            [Text.Encoding]::ASCII
        )
        $records += Get-FileRecord -Root $Root -Path $sentinel
    }
    return $records
}

function Assert-UserSentinels {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)]$Expected
    )
    $records = @()
    foreach ($entry in @($Expected)) {
        $path = Join-Path $Root ([string]$entry.path).Replace("/", "\")
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw ("USER_SENTINEL_MISSING:{0}" -f $entry.path)
        }
        $actual = Get-FileRecord -Root $Root -Path $path
        if (
            [int64]$actual.size_bytes -ne [int64]$entry.size_bytes -or
            [string]$actual.sha256 -ne [string]$entry.sha256
        ) {
            throw ("USER_SENTINEL_CHANGED:{0}" -f $entry.path)
        }
        $records += $actual
    }
    return $records
}

function Get-ExpectedManagedFiles {
    param([Parameter(Mandatory = $true)]$PackageManifest)
    $records = @()
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
            $records += [pscustomobject][ordered]@{
                path = $relative
                size_bytes = [int64]$entry.size_bytes
                sha256 = ([string]$entry.sha256).ToLowerInvariant()
            }
        }
    }
    return @($records | Sort-Object path)
}

function Get-ActualManagedFiles {
    param([Parameter(Mandatory = $true)][string]$Root)
    $files = @()
    $src = Join-Path $Root "src"
    if (Test-Path -LiteralPath $src -PathType Container) {
        $files += @(Get-ChildItem -LiteralPath $src -File -Recurse -Force)
    }
    foreach ($relative in @(
        "scripts\import_source.ps1",
        "scripts\configure_home_local.ps1",
        "scripts\one_click_home_local.ps1",
        "README_FIRST.txt"
    )) {
        $candidate = Join-Path $Root $relative
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            $files += Get-Item -LiteralPath $candidate
        }
    }
    $records = @()
    foreach ($file in @($files)) {
        $records += Get-FileRecord -Root $Root -Path $file.FullName
    }
    return @($records | Sort-Object path)
}

function Assert-ManagedFiles {
    param(
        [Parameter(Mandatory = $true)]$Expected,
        [Parameter(Mandatory = $true)]$Actual
    )
    $expectedList = @($Expected)
    $actualList = @($Actual)
    if ($expectedList.Count -ne $actualList.Count) {
        throw (
            "MANAGED_FILE_COUNT_MISMATCH:expected={0};actual={1}" -f
            $expectedList.Count,
            $actualList.Count
        )
    }
    for ($index = 0; $index -lt $expectedList.Count; $index++) {
        $left = $expectedList[$index]
        $right = $actualList[$index]
        if ([string]$left.path -ne [string]$right.path) {
            throw ("MANAGED_PATH_MISMATCH:{0}:{1}" -f $left.path, $right.path)
        }
        if ([int64]$left.size_bytes -ne [int64]$right.size_bytes) {
            throw ("MANAGED_SIZE_MISMATCH:{0}" -f $left.path)
        }
        if ([string]$left.sha256 -ne [string]$right.sha256) {
            throw ("MANAGED_HASH_MISMATCH:{0}" -f $left.path)
        }
    }
}

function Assert-LauncherContracts {
    param([Parameter(Mandatory = $true)][string]$Root)
    $expected = [ordered]@{
        "START_QUANTUM.cmd" = @(
            "@echo off",
            "setlocal",
            "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"%~dp0scripts\one_click_home_local.ps1`" -InstalledRoot `"%~dp0`" -SkipInstall",
            "set `"quantum_exit=%errorlevel%`"",
            "if not `"%quantum_exit%`"==`"0`" pause",
            "exit /b %quantum_exit%"
        )
        "IMPORT_XLSX.cmd" = @(
            "@echo off",
            "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"%~dp0scripts\import_source.ps1`"",
            "if errorlevel 1 pause"
        )
        "CONFIGURE_HOME_LOCAL.cmd" = @(
            "@echo off",
            "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"%~dp0scripts\configure_home_local.ps1`"",
            "if errorlevel 1 pause"
        )
    }

    $records = @()
    foreach ($name in $expected.Keys) {
        $path = Join-Path $Root $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw ("INSTALLED_LAUNCHER_MISSING:{0}" -f $name)
        }
        $actualLines = @(
            (Get-Content -LiteralPath $path -Encoding ASCII) |
                ForEach-Object { ([string]$_).TrimEnd() } |
                Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
        )
        $expectedLines = @($expected[$name])
        if ($actualLines.Count -ne $expectedLines.Count) {
            throw ("INSTALLED_LAUNCHER_LINE_COUNT:{0}" -f $name)
        }
        for ($index = 0; $index -lt $expectedLines.Count; $index++) {
            if ($actualLines[$index] -cne $expectedLines[$index]) {
                throw (
                    "INSTALLED_LAUNCHER_CONTENT:{0}:{1}" -f
                    $name,
                    $index
                )
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
    $previous = $env:PYTHONPATH
    try {
        $env:PYTHONPATH = Join-Path $Root "src"
        $stdout = Join-Path $EvidenceRoot "installed-self-test.stdout.txt"
        $stderr = Join-Path $EvidenceRoot "installed-self-test.stderr.txt"
        $output = @(
            python -m quantum.application.desktop_center `
                --root $Root `
                --config $Config `
                --self-test 2>&1
        )
        $exitCode = $LASTEXITCODE
        $output | Set-Content -LiteralPath $stdout -Encoding UTF8
        "" | Set-Content -LiteralPath $stderr -Encoding UTF8
        if ($exitCode -ne 0) {
            throw ("INSTALLED_SELF_TEST_EXIT:{0}" -f $exitCode)
        }
        $nonEmpty = @(
            $output |
                Where-Object {
                    -not [string]::IsNullOrWhiteSpace([string]$_)
                }
        )
        if ($nonEmpty.Count -lt 1) {
            throw "INSTALLED_SELF_TEST_EMPTY"
        }
        $result = ([string]$nonEmpty[-1]) | ConvertFrom-Json
        if ([string]$result.status -ne "DESKTOP_CENTER_SELF_TEST_PASS") {
            throw ("INSTALLED_SELF_TEST_STATUS:{0}" -f $result.status)
        }
        if ([string]$result.finance_center.status -ne "FINANCE_CENTER_SELF_TEST_PASS") {
            throw (
                "INSTALLED_FINANCE_CENTER_SELF_TEST_STATUS:{0}" -f
                $result.finance_center.status
            )
        }
        if ($result.marketplace_write_enabled -ne $false) {
            throw "INSTALLED_SELF_TEST_MARKETPLACE_WRITES"
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
        $env:PYTHONPATH = $previous
    }
}

function Invoke-TaxBaseProbe {
    param([Parameter(Mandatory = $true)][string]$Root)
    $previous = $env:PYTHONPATH
    try {
        $env:PYTHONPATH = Join-Path $Root "src"
        $stdout = Join-Path $EvidenceRoot "installed-tax-base.stdout.txt"
        $stderr = Join-Path $EvidenceRoot "installed-tax-base.stderr.txt"
        $code = "from quantum.application import _finance_center_reports as r; assert 'gross_sales_amount' in r.TAX_BASE_OPTIONS; print('INSTALLED_TAX_BASE_IMPORT_PASS')"
        $output = @(python -c $code 2>&1)
        $exitCode = $LASTEXITCODE
        $output | Set-Content -LiteralPath $stdout -Encoding UTF8
        "" | Set-Content -LiteralPath $stderr -Encoding UTF8
        if (
            $exitCode -ne 0 -or
            ($output -join "`n") -notmatch "INSTALLED_TAX_BASE_IMPORT_PASS"
        ) {
            throw ("INSTALLED_TAX_BASE_PROBE_FAILED:{0}" -f $exitCode)
        }
        return [ordered]@{
            exit_code = $exitCode
            stdout_sha256 = Get-Sha256 -Path $stdout
            stderr_sha256 = Get-Sha256 -Path $stderr
        }
    }
    finally {
        $env:PYTHONPATH = $previous
    }
}

function Invoke-RuntimeProbe {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Config
    )
    $previous = $env:PYTHONPATH
    $process = $null
    $record = $null
    $stdout = Join-Path $EvidenceRoot "installed-runtime.stdout.txt"
    $stderr = Join-Path $EvidenceRoot "installed-runtime.stderr.txt"
    try {
        $env:PYTHONPATH = Join-Path $Root "src"
        $arguments = @(
            "-m",
            "quantum.application.desktop_center",
            "--root",
            $Root,
            "--config",
            $Config
        )
        $process = Start-Process `
            -FilePath "python.exe" `
            -ArgumentList $arguments `
            -WorkingDirectory $Root `
            -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr `
            -PassThru
        Start-Sleep -Seconds 8
        $process.Refresh()
        if ($process.HasExited) {
            throw ("INSTALLED_RUNTIME_EXITED:{0}" -f $process.ExitCode)
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
        }
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
        $env:PYTHONPATH = $previous
    }
    if ($null -eq $record) {
        throw "INSTALLED_RUNTIME_RECORD_NOT_CREATED"
    }
    $record["stdout_sha256"] = Get-Sha256 -Path $stdout
    $record["stderr_sha256"] = Get-Sha256 -Path $stderr
    return $record
}

function Invoke-TamperNegativeControl {
    param(
        [Parameter(Mandatory = $true)][string]$SourceRoot,
        [Parameter(Mandatory = $true)]$Expected
    )
    Copy-Item -LiteralPath $SourceRoot -Destination $TamperRoot -Recurse -Force
    $target = Join-Path $TamperRoot "src\quantum\application\_finance_center_shared.py"
    Add-Content -LiteralPath $target -Value "# l4 tamper negative control" -Encoding ASCII
    $actual = Get-ActualManagedFiles -Root $TamperRoot
    try {
        Assert-ManagedFiles -Expected $Expected -Actual $actual
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
        step = $Step
        exception_type = $_.Exception.GetType().FullName
        exception_message = $_.Exception.Message
        script_stack_trace = $_.ScriptStackTrace
        captured_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    }
    Write-Json -Value $failure -Path (Join-Path $EvidenceRoot "L4_FAILURE.json")
    exit 1
}

$Step = "EXACT_HEAD"
if ($ExactHead -notmatch "^[0-9a-f]{40}$") {
    throw ("TARGET_SHA_INVALID:{0}" -f $ExactHead)
}
$actualHead = (& git -C $RepoRoot rev-parse HEAD).Trim().ToLowerInvariant()
if ($actualHead -ne $ExactHead.ToLowerInvariant()) {
    throw ("EXACT_HEAD_MISMATCH:{0}" -f $actualHead)
}

$Step = "PINNED_DEPENDENCIES"
python -m pip install `
    --disable-pip-version-check `
    --no-deps `
    --only-binary=:all: `
    --require-hashes `
    -r requirements/windows-home-local.txt
if ($LASTEXITCODE -ne 0) {
    throw ("PINNED_DEPENDENCY_INSTALL_FAILED:{0}" -f $LASTEXITCODE)
}

$Step = "CONTRACT_TEST"
$env:PYTHONPATH = "src"
python -m unittest tests.test_l4_installed_runtime_contract -v
if ($LASTEXITCODE -ne 0) {
    throw ("L4_CONTRACT_TEST_FAILED:{0}" -f $LASTEXITCODE)
}

$Step = "PACKAGE_BUILD"
powershell.exe `
    -NoProfile `
    -ExecutionPolicy Bypass `
    -File .\scripts\windows\build_local_production.ps1 `
    -OutputDirectory $BuildRoot
if ($LASTEXITCODE -ne 0) {
    throw ("L4_PACKAGE_BUILD_FAILED:{0}" -f $LASTEXITCODE)
}
$archive = Join-Path $BuildRoot "QuantumLocalProduction_HOME_LOCAL.zip"
if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) {
    throw "L4_PACKAGE_NOT_FOUND"
}
$packageHash = Get-Sha256 -Path $archive

$Step = "PACKAGE_VERIFY"
Expand-Archive -LiteralPath $archive -DestinationPath $ExtractRoot
$packageManifestPath = Join-Path $ExtractRoot "manifest.sha256.json"
$packageManifest = (
    Get-Content -LiteralPath $packageManifestPath -Raw -Encoding UTF8
) | ConvertFrom-Json
if ([string]$packageManifest.source_commit -ne $ExactHead) {
    throw ("PACKAGE_HEAD_MISMATCH:{0}" -f $packageManifest.source_commit)
}
if ($packageManifest.marketplace_write_enabled -ne $false) {
    throw "PACKAGE_MARKETPLACE_WRITES_ENABLED"
}
$expectedManaged = Get-ExpectedManagedFiles -PackageManifest $packageManifest
if ($expectedManaged.Count -lt 100) {
    throw ("EXPECTED_MANAGED_SET_TOO_SMALL:{0}" -f $expectedManaged.Count)
}

$Step = "USER_SENTINELS"
$userSentinels = New-UserSentinels -Root $InstallRoot

$Step = "FIRST_INSTALL"
$installer = Join-Path $ExtractRoot "scripts\install_home_local.ps1"
powershell.exe `
    -NoProfile `
    -ExecutionPolicy Bypass `
    -File $installer `
    -SourceRoot $ExtractRoot `
    -TargetRoot $InstallRoot
if ($LASTEXITCODE -ne 0) {
    throw ("FIRST_INSTALL_FAILED:{0}" -f $LASTEXITCODE)
}
$firstSentinels = Assert-UserSentinels -Root $InstallRoot -Expected $userSentinels
$firstManaged = Get-ActualManagedFiles -Root $InstallRoot
Assert-ManagedFiles -Expected $expectedManaged -Actual $firstManaged
$firstLaunchers = Assert-LauncherContracts -Root $InstallRoot

$Step = "SECOND_INSTALL"
powershell.exe `
    -NoProfile `
    -ExecutionPolicy Bypass `
    -File $installer `
    -SourceRoot $ExtractRoot `
    -TargetRoot $InstallRoot
if ($LASTEXITCODE -ne 0) {
    throw ("SECOND_INSTALL_FAILED:{0}" -f $LASTEXITCODE)
}
$secondSentinels = Assert-UserSentinels -Root $InstallRoot -Expected $userSentinels
$secondManaged = Get-ActualManagedFiles -Root $InstallRoot
Assert-ManagedFiles -Expected $expectedManaged -Actual $secondManaged
$secondLaunchers = Assert-LauncherContracts -Root $InstallRoot
if (@(Get-ChildItem -LiteralPath $InstallRoot -Directory -Filter ".installing_*").Count -ne 0) {
    throw "STALE_INSTALL_TRANSACTION_FOUND"
}
$backupCount = @(
    Get-ChildItem -LiteralPath $InstallRoot -Directory -Filter "src.backup_*"
).Count
if ($backupCount -lt 1) {
    throw "SECOND_INSTALL_BACKUP_NOT_FOUND"
}

$Step = "CONFIGURE"
$configPath = Join-Path $InstallRoot "config\default-home-local.json"
powershell.exe `
    -NoProfile `
    -ExecutionPolicy Bypass `
    -File (Join-Path $InstallRoot "scripts\configure_home_local.ps1") `
    -ConfigPath $configPath `
    -ReportingPeriodStart "2026-07-01" `
    -ReportingPeriodEnd "2026-07-04" `
    -RetentionDeadline "2030-01-01" `
    -SourceInternalId "l4-installed-runtime" `
    -NonInteractive
if ($LASTEXITCODE -ne 0) {
    throw ("INSTALLED_CONFIGURE_FAILED:{0}" -f $LASTEXITCODE)
}

$Step = "SELF_TEST"
$selfTest = Invoke-InstalledSelfTest -Root $InstallRoot -Config $configPath

$Step = "TAX_BASE"
$taxProbe = Invoke-TaxBaseProbe -Root $InstallRoot

$Step = "RUNTIME_STARTUP"
$runtimeProbe = Invoke-RuntimeProbe -Root $InstallRoot -Config $configPath

$Step = "TAMPER_CONTROL"
$tamper = Invoke-TamperNegativeControl -SourceRoot $InstallRoot -Expected $expectedManaged

$Step = "EVIDENCE"
$installedManifest = [ordered]@{
    schema_version = "quantum-l4-installed-manifest-v1"
    exact_head = $ExactHead
    source_package_sha256 = $packageHash
    release_state = "RELEASE_BLOCKED"
    marketplace_write_enabled = $false
    managed_files = $secondManaged
    launchers = $secondLaunchers
}
$installedManifestPath = Join-Path $EvidenceRoot "INSTALLED_MANIFEST.json"
Write-Json -Value $installedManifest -Path $installedManifestPath -Depth 20

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
        runtime_backup_count = $backupCount
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
        "This proves automated installed-runtime L4 on a GitHub-hosted Windows runner.",
        "It does not prove physical-user-path L5 on the operator workstation.",
        "Merge, deployment and marketplace writes remain disabled."
    )
    captured_at_utc = (Get-Date).ToUniversalTime().ToString("o")
}
$resultPath = Join-Path $EvidenceRoot "L4_INSTALLED_RUNTIME_EVIDENCE.json"
Write-Json -Value $result -Path $resultPath -Depth 50
(
    (Get-Sha256 -Path $resultPath) +
    "  L4_INSTALLED_RUNTIME_EVIDENCE.json"
) | Set-Content `
    -LiteralPath (Join-Path $EvidenceRoot "L4_INSTALLED_RUNTIME_EVIDENCE.sha256") `
    -Encoding ASCII

$bundle = @()
foreach ($file in @(Get-ChildItem -LiteralPath $EvidenceRoot -File -Recurse -Force)) {
    $bundle += [pscustomobject][ordered]@{
        relative_path = Get-RelativePath -Root $EvidenceRoot -Path $file.FullName
        size_bytes = [int64]$file.Length
        sha256 = Get-Sha256 -Path $file.FullName
    }
}
Write-Json `
    -Value $bundle `
    -Path (Join-Path $EvidenceRoot "EVIDENCE_BUNDLE_MANIFEST.json") `
    -Depth 10

Write-Host "L4_INSTALLED_RUNTIME_PASS"
exit 0
