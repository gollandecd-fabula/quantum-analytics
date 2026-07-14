from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


_POWERSHELL_SCRIPT = r"""
$ErrorActionPreference = "Stop"
$launcher = [IO.Path]::GetFullPath($env:QUANTUM_SHORTCUT_LAUNCHER)
$root = [IO.Path]::GetFullPath($env:QUANTUM_SHORTCUT_ROOT)
$currentName = [Text.Encoding]::UTF8.GetString(
    [Convert]::FromBase64String($env:QUANTUM_SHORTCUT_CURRENT_NAME_B64)
)
$knownNames = @(
    $currentName,
    "Quantum Analytics",
    "Quantum"
)
$desktopCandidates = @(
    [Environment]::GetFolderPath("Desktop"),
    (Join-Path $env:USERPROFILE "Desktop")
)
if (-not [string]::IsNullOrWhiteSpace($env:OneDrive)) {
    $desktopCandidates += (Join-Path $env:OneDrive "Desktop")
}
$desktops = @(
    $desktopCandidates |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
        Select-Object -Unique
)
$shell = New-Object -ComObject WScript.Shell
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$repaired = 0
$disabled = 0

function Set-QuantumLink {
    param([Parameter(Mandatory = $true)][string]$Path)
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath = $launcher
    $shortcut.Arguments = ""
    $shortcut.WorkingDirectory = $root
    $shortcut.Description = $currentName
    $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,167"
    $shortcut.Save()
    $script:repaired += 1
}

foreach ($desktop in $desktops) {
    if (-not (Test-Path -LiteralPath $desktop -PathType Container)) {
        continue
    }

    Set-QuantumLink -Path (Join-Path $desktop ($currentName + ".lnk"))

    foreach ($item in @(Get-ChildItem -LiteralPath $desktop -Filter "*.lnk" -File -ErrorAction SilentlyContinue)) {
        try {
            $shortcut = $shell.CreateShortcut($item.FullName)
            $probe = "{0} {1} {2}" -f $shortcut.TargetPath, $shortcut.Arguments, $shortcut.WorkingDirectory
            if (($probe -match "localhost:8000") -or ($knownNames -contains $item.BaseName)) {
                Set-QuantumLink -Path $item.FullName
            }
        }
        catch {
            continue
        }
    }

    foreach ($item in @(Get-ChildItem -LiteralPath $desktop -Filter "*.url" -File -ErrorAction SilentlyContinue)) {
        try {
            $raw = Get-Content -LiteralPath $item.FullName -Raw -ErrorAction Stop
            if (($raw -match "localhost:8000") -or ($knownNames -contains $item.BaseName)) {
                $disabledPath = $item.FullName + ".disabled_" + $timestamp
                Move-Item -LiteralPath $item.FullName -Destination $disabledPath -Force
                $replacement = [IO.Path]::ChangeExtension($item.FullName, ".lnk")
                Set-QuantumLink -Path $replacement
                $script:disabled += 1
            }
        }
        catch {
            continue
        }
    }
}

[pscustomobject]@{
    status = "SHORTCUT_REPAIR_PASS"
    repaired = $repaired
    disabled_urls = $disabled
} | ConvertTo-Json -Compress
"""


def _write_report(root: Path, payload: dict[str, Any]) -> None:
    try:
        output = root / "output"
        output.mkdir(parents=True, exist_ok=True)
        path = output / "shortcut_repair_latest.json"
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except OSError:
        return


def repair_legacy_shortcuts(root: Path) -> dict[str, Any]:
    resolved_root = root.resolve()
    if not sys.platform.startswith("win"):
        return {"status": "SHORTCUT_REPAIR_SKIPPED_NON_WINDOWS"}

    launcher = resolved_root / "START_QUANTUM.cmd"
    if not launcher.is_file():
        payload = {
            "status": "SHORTCUT_REPAIR_SKIPPED_LAUNCHER_MISSING",
            "launcher": str(launcher),
        }
        _write_report(resolved_root, payload)
        return payload

    encoded = base64.b64encode(
        _POWERSHELL_SCRIPT.encode("utf-16-le")
    ).decode("ascii")
    environment = os.environ.copy()
    environment.update(
        {
            "QUANTUM_SHORTCUT_LAUNCHER": str(launcher),
            "QUANTUM_SHORTCUT_ROOT": str(resolved_root),
            "QUANTUM_SHORTCUT_CURRENT_NAME_B64": base64.b64encode(
                "Центр решений Quantum".encode("utf-8")
            ).decode("ascii"),
        }
    )
    try:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-EncodedCommand",
                encoded,
            ],
            cwd=str(resolved_root),
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        payload = {
            "status": (
                "SHORTCUT_REPAIR_PASS"
                if completed.returncode == 0
                else "SHORTCUT_REPAIR_FAILED"
            ),
            "return_code": completed.returncode,
            "stdout": completed.stdout[-2000:],
            "stderr": completed.stderr[-2000:],
        }
    except (OSError, subprocess.SubprocessError) as exc:
        payload = {
            "status": "SHORTCUT_REPAIR_FAILED",
            "error_type": type(exc).__name__,
        }
    _write_report(resolved_root, payload)
    return payload


__all__ = ["repair_legacy_shortcuts"]
