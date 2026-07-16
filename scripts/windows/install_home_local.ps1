[CmdletBinding()]
param(
    [string]$SourceRoot,
    [string]$TargetRoot = (Join-Path $env:LOCALAPPDATA "QuantumLocalProduction")
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

function Invoke-Icacls {
    param([string]$Path, [string[]]$Arguments, [string]$Operation)
    & icacls.exe $Path @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw (Get-QuantumRussianText -Encoded "0J7Qv9C10YDQsNGG0LjRjyB7MH0g0LTQu9GPIHsxfSDQt9Cw0LLQtdGA0YjQuNC70LDRgdGMINC+0YjQuNCx0LrQvtC5LiDQmtC+0LQg0LLRi9GF0L7QtNCwOiB7Mn0u" -Arguments @($Operation, $Path, $LASTEXITCODE))
    }
}

function Reset-ManagedAcl {
    param([string]$Path, [switch]$Recursive)
    if (-not (Test-Path -LiteralPath $Path -ErrorAction SilentlyContinue)) { return }
    $inherit = @("/inheritance:e", "/C")
    $reset = @("/reset", "/C")
    if ($Recursive) { $inherit += "/T"; $reset += "/T" }
    Invoke-Icacls -Path $Path -Arguments $inherit -Operation "ACL inheritance repair"
    Invoke-Icacls -Path $Path -Arguments $reset -Operation "Explicit ACL reset"
}

function New-QuantumShortcut {
    param([string]$Launcher, [string]$WorkingDirectory)
    try {
        $desktop = [Environment]::GetFolderPath("Desktop")
        if ([string]::IsNullOrWhiteSpace($desktop)) { return }
        $path = Join-Path $desktop (Get-QuantumRussianText -Encoded "0KbQtdC90YLRgCDRgNC10YjQtdC90LjQuSBRdWFudHVtLmxuaw==")
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($path)
        $shortcut.TargetPath = $Launcher
        $shortcut.WorkingDirectory = $WorkingDirectory
        $shortcut.Description = Get-QuantumRussianText -Encoded "0KbQtdC90YLRgCDRgNC10YjQtdC90LjQuSBRdWFudHVtIOKAlCDQu9C+0LrQsNC70YzQvdGL0Lkg0LfQsNC/0YPRgdC6"
        $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,167"
        $shortcut.Save()
        Write-Host (Get-QuantumRussianText -Encoded "0K/RgNC70YvQuiDQvdCwINGA0LDQsdC+0YfQtdC8INGB0YLQvtC70LUg0YHQvtC30LTQsNC9OiB7MH0=" -Arguments @($path))
    }
    catch {
        Write-Warning (Get-QuantumRussianText -Encoded "0J3QtSDRg9C00LDQu9C+0YHRjCDRgdC+0LfQtNCw0YLRjCDRj9GA0LvRi9C6INC90LAg0YDQsNCx0L7Rh9C10Lwg0YHRgtC+0LvQtTogezB9" -Arguments @($($_.Exception.GetType().Name)))
    }
}

function Get-PortablePath {
    param([string]$FullPath, [string]$RootPrefix)
    if (-not $FullPath.StartsWith($RootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw (Get-QuantumRussianText -Encoded "0J/Rg9GC0Ywg0L/QsNC60LXRgtCwINCy0YvRhdC+0LTQuNGCINC30LAg0L/RgNC10LTQtdC70Ysg0LrQvtGA0L3QtdCy0L7QuSDQv9Cw0L/QutC4OiB7MH0=" -Arguments @($FullPath))
    }
    return $FullPath.Substring($RootPrefix.Length).Replace("\", "/")
}

function Assert-PackageManifest {
    param([string]$Root)
    $manifestPath = Join-Path $Root "manifest.sha256.json"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw (Get-QuantumRussianText -Encoded "0JzQsNC90LjRhNC10YHRgiDQv9Cw0LrQtdGC0LAg0L7RgtGB0YPRgtGB0YLQstGD0LXRgjogezB9" -Arguments @($manifestPath))
    }
    try { $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json }
    catch { throw (Get-QuantumRussianText -Encoded "0JzQsNC90LjRhNC10YHRgiDQv9Cw0LrQtdGC0LAg0L3QtSDRj9Cy0LvRj9C10YLRgdGPINC60L7RgNGA0LXQutGC0L3Ri9C8IEpTT046IHswfQ==" -Arguments @($manifestPath)) }

    if ([string]$manifest.package -ne "QuantumLocalProduction_HOME_LOCAL") { throw (Get-QuantumRussianText -Encoded "0JIg0LzQsNC90LjRhNC10YHRgtC1INGD0LrQsNC30LDQvdCwINC90LXQvtC20LjQtNCw0L3QvdCw0Y8g0LjQtNC10L3RgtC40YTQuNC60LDRhtC40Y8g0L/QsNC60LXRgtCwLg==") }
    if ([string]$manifest.release_state -ne "RELEASE_BLOCKED") { throw (Get-QuantumRussianText -Encoded "0JIg0LzQsNC90LjRhNC10YHRgtC1INGD0LrQsNC30LDQvdC+INC90LXQvtC20LjQtNCw0L3QvdC+0LUg0YHQvtGB0YLQvtGP0L3QuNC1INCy0LXRgNGB0LjQuC4=") }
    if ($manifest.marketplace_write_enabled -ne $false) { throw (Get-QuantumRussianText -Encoded "0JfQsNC/0LjRgdGMINC90LAg0LzQsNGA0LrQtdGC0L/Qu9C10LnRgSDQtNC+0LvQttC90LAg0L7RgdGC0LDQstCw0YLRjNGB0Y8g0L7RgtC60LvRjtGH0ZHQvdC90L7QuSDQsiBIT01FX0xPQ0FMLg==") }
    if ($manifest.manifest_excludes_self -ne $true) { throw (Get-QuantumRussianText -Encoded "0JrQvtC90YLRgNCw0LrRgiDRgdCw0LzQvtC40YHQutC70Y7Rh9C10L3QuNGPINC80LDQvdC40YTQtdGB0YLQsCDQv9Cw0LrQtdGC0LAg0L3QtdC60L7RgNGA0LXQutGC0LXQvS4=") }
    if ([string]$manifest.source_commit -notmatch "^[0-9a-fA-F]{40}$") { throw (Get-QuantumRussianText -Encoded "Q29tbWl0INC40YHRhdC+0LTQvdC+0LPQviDQutC+0LTQsCDQv9Cw0LrQtdGC0LAg0L7RgtGB0YPRgtGB0YLQstGD0LXRgiDQuNC70Lgg0LjQvNC10LXRgiDQvdC10LLQtdGA0L3Ri9C5INGE0L7RgNC80LDRgi4=") }

    $entries = @($manifest.files)
    if ($entries.Count -lt 1) { throw (Get-QuantumRussianText -Encoded "0JzQsNC90LjRhNC10YHRgiDQv9Cw0LrQtdGC0LAg0L3QtSDRgdC+0LTQtdGA0LbQuNGCINGE0LDQudC70L7Qsi4=") }
    $rootFull = (Get-Item -LiteralPath $Root).FullName.TrimEnd([char[]]"\/")
    $prefix = $rootFull + [IO.Path]::DirectorySeparatorChar
    $manifestFull = (Get-Item -LiteralPath $manifestPath).FullName
    $declared = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)

    foreach ($entry in $entries) {
        $relative = [string]$entry.path
        if ([string]::IsNullOrWhiteSpace($relative)) { throw (Get-QuantumRussianText -Encoded "0JzQsNC90LjRhNC10YHRgiDQv9Cw0LrQtdGC0LAg0YHQvtC00LXRgNC20LjRgiDQv9GD0YHRgtC+0Lkg0L/Rg9GC0Ywu") }
        $normalized = $relative.Replace("/", "\")
        if ([IO.Path]::IsPathRooted($normalized)) { throw (Get-QuantumRussianText -Encoded "0JzQsNC90LjRhNC10YHRgiDQv9Cw0LrQtdGC0LAg0YHQvtC00LXRgNC20LjRgiDQsNCx0YHQvtC70Y7RgtC90YvQuSDQv9GD0YLRjDogezB9" -Arguments @($relative)) }
        $parts = @($normalized.Split("\"))
        if (@($parts | Where-Object { [string]::IsNullOrWhiteSpace($_) -or $_ -in @(".", "..") }).Count -gt 0) {
            throw (Get-QuantumRussianText -Encoded "0JzQsNC90LjRhNC10YHRgiDQv9Cw0LrQtdGC0LAg0YHQvtC00LXRgNC20LjRgiDQvdC10LHQtdC30L7Qv9Cw0YHQvdGL0Lkg0L/Rg9GC0Yw6IHswfQ==" -Arguments @($relative))
        }
        $full = [IO.Path]::GetFullPath((Join-Path $rootFull $normalized))
        $portable = Get-PortablePath -FullPath $full -RootPrefix $prefix
        if (-not $declared.Add($portable)) { throw (Get-QuantumRussianText -Encoded "0JzQsNC90LjRhNC10YHRgiDQv9Cw0LrQtdGC0LAg0YHQvtC00LXRgNC20LjRgiDQv9C+0LLRgtC+0YDRj9GO0YnQuNC50YHRjyDQv9GD0YLRjDogezB9" -Arguments @($portable)) }
        if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { throw (Get-QuantumRussianText -Encoded "0KTQsNC50LssINGD0LrQsNC30LDQvdC90YvQuSDQsiDQvNCw0L3QuNGE0LXRgdGC0LUsINC+0YLRgdGD0YLRgdGC0LLRg9C10YI6IHswfQ==" -Arguments @($portable)) }
        $item = Get-Item -LiteralPath $full
        if ([int64]$entry.size_bytes -ne [int64]$item.Length) { throw (Get-QuantumRussianText -Encoded "0KDQsNC30LzQtdGAINGE0LDQudC70LAg0L3QtSDRgdC+0LLQv9Cw0LTQsNC10YIg0YEg0LzQsNC90LjRhNC10YHRgtC+0Lw6IHswfQ==" -Arguments @($portable)) }
        $hash = (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -ne ([string]$entry.sha256).ToLowerInvariant()) { throw (Get-QuantumRussianText -Encoded "0KXQtdGIINGE0LDQudC70LAg0L3QtSDRgdC+0LLQv9Cw0LTQsNC10YIg0YEg0LzQsNC90LjRhNC10YHRgtC+0Lw6IHswfQ==" -Arguments @($portable)) }
    }

    $actual = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($item in @(Get-ChildItem -LiteralPath $rootFull -Recurse -File)) {
        $full = [IO.Path]::GetFullPath($item.FullName)
        if ($full.Equals($manifestFull, [StringComparison]::OrdinalIgnoreCase)) { continue }
        $portable = Get-PortablePath -FullPath $full -RootPrefix $prefix
        if (-not $actual.Add($portable)) { throw (Get-QuantumRussianText -Encoded "0J/QsNC60LXRgiDRgdC+0LTQtdGA0LbQuNGCINC/0L7QstGC0L7RgNGP0Y7RidC40LnRgdGPINC/0YPRgtGMINGE0LDQudC70L7QstC+0Lkg0YHQuNGB0YLQtdC80Ys6IHswfQ==" -Arguments @($portable)) }
        if (-not $declared.Contains($portable)) { throw (Get-QuantumRussianText -Encoded "0J/QsNC60LXRgiDRgdC+0LTQtdGA0LbQuNGCINGE0LDQudC7LCDQvtGC0YHRg9GC0YHRgtCy0YPRjtGJ0LjQuSDQsiDQvNCw0L3QuNGE0LXRgdGC0LU6IHswfQ==" -Arguments @($portable)) }
    }
    foreach ($portable in $declared) {
        if (-not $actual.Contains($portable)) { throw (Get-QuantumRussianText -Encoded "0KTQsNC50Lsg0LjQtyDQvNCw0L3QuNGE0LXRgdGC0LAg0L3QtSDQvdCw0LnQtNC10L0g0L/RgNC4INC/0YDQvtCy0LXRgNC60LUg0L/QsNC60LXRgtCwOiB7MH0=" -Arguments @($portable)) }
    }
    if ($actual.Count -ne $declared.Count) {
        throw (Get-QuantumRussianText -Encoded "0J/QvtGB0LvQtSDRgtC+0YfQvdC+0LPQviDRgdGA0LDQstC90LXQvdC40Y8g0L/Rg9GC0LXQuSDRh9C40YHQu9C+INGE0LDQudC70L7QsiDQvdC1INGB0L7QstC/0LDQu9C+OiDRhNCw0LrRgtC40YfQtdGB0LrQuD17MH0sINCyINC80LDQvdC40YTQtdGB0YLQtT17MX0u" -Arguments @($($actual.Count), $($declared.Count)))
    }
    foreach ($required in @(
        "src/quantum/pilot/windows_runner.py",
        "scripts/import_source.ps1",
        "scripts/configure_home_local.ps1",
        "scripts/one_click_home_local.ps1",
        "IMPORT_XLSX.cmd",
        "CONFIGURE_HOME_LOCAL.cmd",
        "START_QUANTUM.cmd"
    )) {
        if (-not $declared.Contains($required)) { throw (Get-QuantumRussianText -Encoded "0J7QsdGP0LfQsNGC0LXQu9GM0L3Ri9C5INGE0LDQudC7INC/0LDQutC10YLQsCDQvdC1INC/0L7QutGA0YvRgiDQvNCw0L3QuNGE0LXRgdGC0L7QvDogezB9" -Arguments @($required)) }
    }
    return $manifest
}

if ([string]::IsNullOrWhiteSpace($SourceRoot)) {
    $SourceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
}
else { $SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path }
$TargetRoot = [IO.Path]::GetFullPath($TargetRoot)

$packageManifest = Assert-PackageManifest -Root $SourceRoot
$sourceRuntime = [IO.Path]::GetFullPath((Join-Path $SourceRoot "src"))
$sourceLauncher = Join-Path $SourceRoot "scripts\import_source.ps1"
$sourceConfigurator = Join-Path $SourceRoot "scripts\configure_home_local.ps1"
$sourceOneClick = Join-Path $SourceRoot "scripts\one_click_home_local.ps1"
foreach ($required in @($sourceLauncher, $sourceConfigurator, $sourceOneClick)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw (Get-QuantumRussianText -Encoded "0KHRhtC10L3QsNGA0LjQuSDQv9Cw0LrQtdGC0LAg0L7RgtGB0YPRgtGB0YLQstGD0LXRgjogezB9" -Arguments @($required)) }
}
if (-not (Test-Path -LiteralPath $sourceRuntime -PathType Container)) { throw (Get-QuantumRussianText -Encoded "0J/QsNC/0LrQsCDRgdGA0LXQtNGLINC/0LDQutC10YLQsCDQvtGC0YHRg9GC0YHRgtCy0YPQtdGCOiB7MH0=" -Arguments @($sourceRuntime)) }

$runtimeTarget = [IO.Path]::GetFullPath((Join-Path $TargetRoot "src"))
if ($sourceRuntime.TrimEnd("\", "/") -ieq $runtimeTarget.TrimEnd("\", "/")) {
    throw (Get-QuantumRussianText -Encoded "0KPRgdGC0LDQvdC+0LLRidC40Log0L3Rg9C20L3QviDQt9Cw0L/Rg9GB0LrQsNGC0Ywg0LjQtyDRgNCw0YHQv9Cw0LrQvtCy0LDQvdC90L7Qs9C+INC/0LDQutC10YLQsCwg0LAg0L3QtSDQuNC3INGD0LbQtSDRg9GB0YLQsNC90L7QstC70LXQvdC90L7QuSDRgdGA0LXQtNGLLg==")
}

New-Item -ItemType Directory -Path $TargetRoot -Force | Out-Null
Reset-ManagedAcl -Path $TargetRoot
foreach ($name in @("config", "data", "output", "scripts")) {
    New-Item -ItemType Directory -Path (Join-Path $TargetRoot $name) -Force | Out-Null
}

$scriptsTarget = Join-Path $TargetRoot "scripts"
$launcherTarget = Join-Path $scriptsTarget "import_source.ps1"
$configuratorTarget = Join-Path $scriptsTarget "configure_home_local.ps1"
$oneClickTarget = Join-Path $scriptsTarget "one_click_home_local.ps1"
$obsoleteCommon = Join-Path $scriptsTarget "common.ps1"
$commandTarget = Join-Path $TargetRoot "IMPORT_XLSX.cmd"
$configureCommandTarget = Join-Path $TargetRoot "CONFIGURE_HOME_LOCAL.cmd"
$startCommandTarget = Join-Path $TargetRoot "START_QUANTUM.cmd"
$readmeSource = Join-Path $SourceRoot "README_FIRST.txt"
$readmeTarget = Join-Path $TargetRoot "README_FIRST.txt"
$templateSource = Join-Path $SourceRoot "config\home-local.template.json"
$templateTarget = Join-Path $TargetRoot "config\home-local.template.json"

Reset-ManagedAcl -Path $scriptsTarget -Recursive
Reset-ManagedAcl -Path $runtimeTarget -Recursive

$installId = "{0}_{1}" -f (Get-Date -Format "yyyyMMdd_HHmmss"), ([guid]::NewGuid().ToString("N").Substring(0, 8))
$transactionRoot = Join-Path $TargetRoot (".installing_{0}" -f $installId)
$runtimeStage = Join-Path $transactionRoot "src"
$fileStageRoot = Join-Path $transactionRoot "files"
$fileRollbackRoot = Join-Path $transactionRoot "rollback"
$runtimeBackup = Join-Path $TargetRoot ("src.backup_{0}" -f $installId)
$fileRollback = @()
$hadRuntime = $false
$runtimeActivated = $false

try {
    New-Item -ItemType Directory -Path $fileStageRoot,$fileRollbackRoot -Force | Out-Null
    Copy-Item -LiteralPath $sourceRuntime -Destination $runtimeStage -Recurse -Force
    if (-not (Test-Path -LiteralPath (Join-Path $runtimeStage "quantum\pilot\windows_runner.py") -PathType Leaf)) {
        throw (Get-QuantumRussianText -Encoded "0J/RgNC+0LLQtdGA0LrQsCDQv9C+0LTQs9C+0YLQvtCy0LvQtdC90L3QvtC5INGB0YDQtdC00Ysg0LfQsNCy0LXRgNGI0LjQu9Cw0YHRjCDQvtGI0LjQsdC60L7QuS4=")
    }

    $stagedLauncher = Join-Path $fileStageRoot "import_source.ps1"
    $stagedConfigurator = Join-Path $fileStageRoot "configure_home_local.ps1"
    $stagedOneClick = Join-Path $fileStageRoot "one_click_home_local.ps1"
    Copy-Item -LiteralPath $sourceLauncher -Destination $stagedLauncher -Force
    Copy-Item -LiteralPath $sourceConfigurator -Destination $stagedConfigurator -Force
    Copy-Item -LiteralPath $sourceOneClick -Destination $stagedOneClick -Force

    $stagedImportCommand = Join-Path $fileStageRoot "IMPORT_XLSX.cmd"
    @'
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\import_source.ps1"
if errorlevel 1 pause
'@ | Set-Content -LiteralPath $stagedImportCommand -Encoding ASCII

    $stagedConfigureCommand = Join-Path $fileStageRoot "CONFIGURE_HOME_LOCAL.cmd"
    @'
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\configure_home_local.ps1"
if errorlevel 1 pause
'@ | Set-Content -LiteralPath $stagedConfigureCommand -Encoding ASCII

    $stagedStartCommand = Join-Path $fileStageRoot "START_QUANTUM.cmd"
    @'
@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\one_click_home_local.ps1" -InstalledRoot "%~dp0" -SkipInstall
set "quantum_exit=%errorlevel%"
if not "%quantum_exit%"=="0" pause
exit /b %quantum_exit%
'@ | Set-Content -LiteralPath $stagedStartCommand -Encoding ASCII

    $replacements = @(
        [pscustomobject]@{ Stage = $stagedLauncher; Target = $launcherTarget; Key = "scripts_import_source.ps1" },
        [pscustomobject]@{ Stage = $stagedConfigurator; Target = $configuratorTarget; Key = "scripts_configure_home_local.ps1" },
        [pscustomobject]@{ Stage = $stagedOneClick; Target = $oneClickTarget; Key = "scripts_one_click_home_local.ps1" },
        [pscustomobject]@{ Stage = $stagedImportCommand; Target = $commandTarget; Key = "IMPORT_XLSX.cmd" },
        [pscustomobject]@{ Stage = $stagedConfigureCommand; Target = $configureCommandTarget; Key = "CONFIGURE_HOME_LOCAL.cmd" },
        [pscustomobject]@{ Stage = $stagedStartCommand; Target = $startCommandTarget; Key = "START_QUANTUM.cmd" }
    )

    if (Test-Path -LiteralPath $readmeSource -PathType Leaf) {
        $stagedReadme = Join-Path $fileStageRoot "README_FIRST.txt"
        Copy-Item -LiteralPath $readmeSource -Destination $stagedReadme -Force
        $replacements += [pscustomobject]@{ Stage = $stagedReadme; Target = $readmeTarget; Key = "README_FIRST.txt" }
    }
    if ((Test-Path -LiteralPath $templateSource -PathType Leaf) -and -not (Test-Path -LiteralPath $templateTarget)) {
        $stagedTemplate = Join-Path $fileStageRoot "home-local.template.json"
        Copy-Item -LiteralPath $templateSource -Destination $stagedTemplate -Force
        $replacements += [pscustomobject]@{ Stage = $stagedTemplate; Target = $templateTarget; Key = "home-local.template.json" }
    }

    foreach ($replacement in $replacements) {
        if (-not (Test-Path -LiteralPath $replacement.Stage -PathType Leaf)) {
            throw (Get-QuantumRussianText -Encoded "0J/QvtC00LPQvtGC0L7QstC70LXQvdC90YvQuSDRg9C/0YDQsNCy0LvRj9C10LzRi9C5INGE0LDQudC7INC+0YLRgdGD0YLRgdGC0LLRg9C10YI6IHswfQ==" -Arguments @($($replacement.Stage)))
        }
        if ((Test-Path -LiteralPath $replacement.Target) -and -not (Test-Path -LiteralPath $replacement.Target -PathType Leaf)) {
            throw (Get-QuantumRussianText -Encoded "0KbQtdC70LXQstC+0Lkg0YPQv9GA0LDQstC70Y/QtdC80YvQuSDQvtCx0YrQtdC60YIg0YPRgdGC0LDQvdC+0LLQutC4INC90LUg0Y/QstC70Y/QtdGC0YHRjyDRhNCw0LnQu9C+0Lw6IHswfQ==" -Arguments @($($replacement.Target)))
        }
    }

    $hadRuntime = Test-Path -LiteralPath $runtimeTarget -PathType Container
    if ($hadRuntime) { Move-Item -LiteralPath $runtimeTarget -Destination $runtimeBackup }
    Move-Item -LiteralPath $runtimeStage -Destination $runtimeTarget
    $runtimeActivated = $true

    foreach ($replacement in $replacements) {
        $backupFile = Join-Path $fileRollbackRoot $replacement.Key
        $hadOriginal = Test-Path -LiteralPath $replacement.Target -PathType Leaf
        if ($hadOriginal) {
            Move-Item -LiteralPath $replacement.Target -Destination $backupFile
        }
        $fileRollback += [pscustomobject]@{
            Target = $replacement.Target
            Backup = $backupFile
            HadOriginal = $hadOriginal
        }
        Move-Item -LiteralPath $replacement.Stage -Destination $replacement.Target
    }

    $obsoleteBackup = Join-Path $fileRollbackRoot "obsolete_common.ps1"
    $hadObsoleteCommon = Test-Path -LiteralPath $obsoleteCommon -PathType Leaf
    if ($hadObsoleteCommon) {
        Move-Item -LiteralPath $obsoleteCommon -Destination $obsoleteBackup
        $fileRollback += [pscustomobject]@{
            Target = $obsoleteCommon
            Backup = $obsoleteBackup
            HadOriginal = $true
        }
    }

    Reset-ManagedAcl -Path $runtimeTarget -Recursive
    Reset-ManagedAcl -Path $scriptsTarget -Recursive
    foreach ($path in @($commandTarget, $configureCommandTarget, $startCommandTarget, $readmeTarget)) {
        if (Test-Path -LiteralPath $path) { Reset-ManagedAcl -Path $path }
    }

    foreach ($required in @(
        (Join-Path $runtimeTarget "quantum\pilot\windows_runner.py"),
        $launcherTarget,
        $configuratorTarget,
        $oneClickTarget,
        $commandTarget,
        $configureCommandTarget,
        $startCommandTarget
    )) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw (Get-QuantumRussianText -Encoded "0J/RgNC+0LLQtdGA0LrQsCDRg9GB0YLQsNC90L7QstC60Lgg0LfQsNCy0LXRgNGI0LjQu9Cw0YHRjCDQvtGI0LjQsdC60L7QuTogezB9" -Arguments @($required)) }
        $stream = [IO.File]::Open($required, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
        $stream.Dispose()
    }
    if (Test-Path -LiteralPath $obsoleteCommon) { throw (Get-QuantumRussianText -Encoded "0KPRgdGC0LDRgNC10LLRiNC40Lkg0YPQv9GA0LDQstC70Y/QtdC80YvQuSDRgdGG0LXQvdCw0YDQuNC5INC90LUg0LHRi9C7INGD0LTQsNC70ZHQvTogezB9" -Arguments @($obsoleteCommon)) }
}
catch {
    $failure = $_
    $rollbackErrors = @()

    for ($index = $fileRollback.Count - 1; $index -ge 0; $index--) {
        $record = $fileRollback[$index]
        try {
            if (Test-Path -LiteralPath $record.Target) {
                Remove-Item -LiteralPath $record.Target -Recurse -Force
            }
            if ($record.HadOriginal -and (Test-Path -LiteralPath $record.Backup)) {
                Move-Item -LiteralPath $record.Backup -Destination $record.Target
            }
        }
        catch { $rollbackErrors += $_.Exception.Message }
    }

    try {
        if ($runtimeActivated -and (Test-Path -LiteralPath $runtimeTarget)) {
            Remove-Item -LiteralPath $runtimeTarget -Recurse -Force
        }
        if ($hadRuntime -and (Test-Path -LiteralPath $runtimeBackup)) {
            Move-Item -LiteralPath $runtimeBackup -Destination $runtimeTarget
        }
    }
    catch { $rollbackErrors += $_.Exception.Message }

    Remove-Item -LiteralPath $transactionRoot -Recurse -Force -ErrorAction SilentlyContinue
    if ($rollbackErrors.Count -gt 0) {
        throw (Get-QuantumRussianText -Encoded "0KPRgdGC0LDQvdC+0LLQutCwINC30LDQstC10YDRiNC40LvQsNGB0Ywg0L7RiNC40LHQutC+0Lk6IHswfS4g0J7RgtC60LDRgiDRgtCw0LrQttC1INC30LDQstC10YDRiNC40LvRgdGPINC+0YjQuNCx0LrQvtC5OiB7MX0=" -Arguments @($($failure.Exception.Message), $($rollbackErrors -join '; ')))
    }
    throw $failure
}

Remove-Item -LiteralPath $transactionRoot -Recurse -Force -ErrorAction SilentlyContinue
New-QuantumShortcut -Launcher $startCommandTarget -WorkingDirectory $TargetRoot
Write-Host (Get-QuantumRussianText -Encoded "0KHRgNC10LTQsCBRdWFudHVtIEhPTUVfTE9DQUwg0YPRgdGC0LDQvdC+0LLQu9C10L3QsC4=") -ForegroundColor Green
Write-Host (Get-QuantumRussianText -Encoded "0J/QsNC/0LrQsCDRg9GB0YLQsNC90L7QstC60Lg6IHswfQ==" -Arguments @($TargetRoot))
Write-Host (Get-QuantumRussianText -Encoded "0KHRg9GJ0LXRgdGC0LLRg9GO0YnQuNC1INC/0LDQv9C60LggY29uZmlnLCBkYXRhINC4IG91dHB1dCDRgdC+0YXRgNCw0L3QtdC90Ysu")
Write-Host (Get-QuantumRussianText -Encoded "0JfQsNC/0YPRgdC6INC+0LTQvdC+0Lkg0LrQvdC+0L/QutC+0Lk6IHswfQ==" -Arguments @($startCommandTarget))
Write-Host (Get-QuantumRussianText -Encoded "0J/RgNC+0LPRgNCw0LzQvNCwINCy0L7RgdGB0YLQsNC90L7QstC70LXQvdC40Y8g0LjQvNC/0L7RgNGC0LA6IHswfQ==" -Arguments @($commandTarget))
