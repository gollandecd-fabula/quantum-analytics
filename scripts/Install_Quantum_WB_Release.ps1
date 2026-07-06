$ErrorActionPreference = "Stop"

$SourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$InstallRoot = Join-Path $env:USERPROFILE ".quantum-analytics\app\Quantum"
$RuntimeRoot = Join-Path $env:USERPROFILE ".quantum-analytics\local-pilot"
$Desktop = [Environment]::GetFolderPath("Desktop")
$StartMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Quantum"
$ShortcutName = "Quantum WB Release.lnk"
$Launcher = Join-Path $InstallRoot "scripts\Quantum_ONE_CLICK_STABLE_RELEASE.cmd"

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RuntimeRoot "config") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RuntimeRoot "data") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RuntimeRoot "uploads") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RuntimeRoot "receipts") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RuntimeRoot "evidence") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RuntimeRoot "output") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RuntimeRoot "logs") | Out-Null
New-Item -ItemType Directory -Force -Path $StartMenu | Out-Null

foreach ($Item in @("src", "scripts", "docs", "pyproject.toml", "README.md")) {
    $Source = Join-Path $SourceRoot $Item
    if (Test-Path $Source) {
        $Destination = Join-Path $InstallRoot $Item
        Copy-Item -Path $Source -Destination $Destination -Recurse -Force
    }
}

$WScriptShell = New-Object -ComObject WScript.Shell
foreach ($ShortcutPath in @(Join-Path $Desktop $ShortcutName, Join-Path $StartMenu $ShortcutName)) {
    $Shortcut = $WScriptShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $Launcher
    $Shortcut.WorkingDirectory = $InstallRoot
    $Shortcut.Description = "Quantum WB Release local analytics"
    $Shortcut.Save()
}

$Receipt = @{
    status = "installed"
    app = "Quantum WB Release"
    install_root = $InstallRoot
    runtime_root = $RuntimeRoot
    launcher = $Launcher
    marketplace_write_enabled = $false
    installed_at = (Get-Date).ToString("o")
}
$Receipt | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 (Join-Path $RuntimeRoot "install_receipt.json")

Write-Host "Quantum WB Release installed."
Write-Host "Launcher:" $Launcher
Write-Host "Runtime:" $RuntimeRoot
Write-Host "Shortcuts created on Desktop and Start Menu."
