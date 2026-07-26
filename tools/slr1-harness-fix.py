from __future__ import annotations

from pathlib import Path
import hashlib
import json

ROOT = Path.cwd()
WORKFLOW = ROOT / ".github/workflows/shortcut-launch-repair-r1.yml"
OVERLAY = ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_SHORTCUT_LAUNCH_REPAIR_R1.json"

text = WORKFLOW.read_text(encoding="utf-8")
old = '''          $partialLog = Join-Path $env:RUNNER_TEMP "slr1-partial.log"\n          powershell.exe -NoProfile -ExecutionPolicy Bypass `\n            -File (Join-Path $partial "scripts\\one_click_home_local.ps1") `\n            -InstallOnly -NoOpenResult *> $partialLog\n          if ($LASTEXITCODE -eq 0) {\n            throw "Incomplete installation was accepted."\n          }\n'''
new = '''          $partialLog = Join-Path $env:RUNNER_TEMP "slr1-partial.log"\n          $previousErrorActionPreference = $ErrorActionPreference\n          $ErrorActionPreference = "Continue"\n          try {\n            powershell.exe -NoProfile -ExecutionPolicy Bypass `\n              -File (Join-Path $partial "scripts\\one_click_home_local.ps1") `\n              -InstallOnly -NoOpenResult *> $partialLog\n            $partialExitCode = $LASTEXITCODE\n          }\n          finally {\n            $ErrorActionPreference = $previousErrorActionPreference\n          }\n          if ($partialExitCode -eq 0) {\n            throw "Incomplete installation was accepted."\n          }\n'''
if text.count(old) != 1:
    raise SystemExit(f"PARTIAL_HARNESS_BLOCK_COUNT:{text.count(old)}")
WORKFLOW.write_text(text.replace(old, new), encoding="utf-8")

overlay = json.loads(OVERLAY.read_text(encoding="utf-8"))
for entry in overlay["entries"]:
    relative = entry[0]
    payload = (ROOT / relative).read_bytes()
    entry[1] = hashlib.sha256(payload).hexdigest()
    entry[2] = len(payload)
OVERLAY.write_text(
    json.dumps(overlay, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
