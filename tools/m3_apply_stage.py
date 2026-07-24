from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
R96_OVERLAY_BLOB_SHA = "43c043cbb53aed8e7b880ab40bcbd7d4665a6d9f"


def replace_once(relative: str, old: str, new: str) -> None:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"M3_REPLACE_COUNT:{relative}:{count}")
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


def main() -> int:
    replace_once(
        "scripts/ci/l4_installed_runtime.ps1",
        "[CmdletBinding()]\nparam()\n",
        "[CmdletBinding()]\nparam(\n"
        "    [string]$PackageArchive = \"\",\n"
        "    [ValidatePattern(\"^[A-Za-z0-9_-]+$\")]\n"
        "    [string]$EvidenceSlot = \"default\"\n"
        ")\n",
    )
    replace_once(
        "scripts/ci/l4_installed_runtime.ps1",
        "$EvidenceRoot = Join-Path $RepoRoot \"artifacts\\l4-installed-runtime\"\n"
        "$BuildRoot = Join-Path $RepoRoot \"dist\\l4-installed-runtime-build\"\n"
        "$ExtractRoot = Join-Path $env:RUNNER_TEMP \"quantum-l4-package\"\n"
        "$InstallRoot = Join-Path $env:RUNNER_TEMP \"quantum-l4-installed\"\n"
        "$TamperRoot = Join-Path $env:RUNNER_TEMP \"quantum-l4-tampered\"\n",
        "$EvidenceRoot = Join-Path $RepoRoot "
        "(\"artifacts\\l4-installed-runtime-\" + $EvidenceSlot)\n"
        "$BuildRoot = Join-Path $RepoRoot "
        "(\"dist\\l4-installed-runtime-build-\" + $EvidenceSlot)\n"
        "$ExtractRoot = Join-Path $env:RUNNER_TEMP "
        "(\"quantum-l4-package-\" + $EvidenceSlot)\n"
        "$InstallRoot = Join-Path $env:RUNNER_TEMP "
        "(\"quantum-l4-installed-\" + $EvidenceSlot)\n"
        "$TamperRoot = Join-Path $env:RUNNER_TEMP "
        "(\"quantum-l4-tampered-\" + $EvidenceSlot)\n",
    )
    replace_once(
        "scripts/ci/l4_installed_runtime.ps1",
        "$Step = \"PACKAGE_BUILD\"\n"
        "powershell.exe `\n"
        "    -NoProfile `\n"
        "    -ExecutionPolicy Bypass `\n"
        "    -File .\\scripts\\windows\\build_local_production.ps1 `\n"
        "    -OutputDirectory $BuildRoot\n"
        "if ($LASTEXITCODE -ne 0) {\n"
        "    throw (\"L4_PACKAGE_BUILD_FAILED:{0}\" -f $LASTEXITCODE)\n"
        "}\n"
        "$archive = Join-Path $BuildRoot \"QuantumLocalProduction_HOME_LOCAL.zip\"\n"
        "if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) {\n"
        "    throw \"L4_PACKAGE_NOT_FOUND\"\n"
        "}\n"
        "$packageHash = Get-Sha256 -Path $archive\n",
        "$Step = \"PACKAGE_SOURCE\"\n"
        "$packageOrigin = \"BUILT_IN_JOB\"\n"
        "if ([string]::IsNullOrWhiteSpace($PackageArchive)) {\n"
        "    powershell.exe `\n"
        "        -NoProfile `\n"
        "        -ExecutionPolicy Bypass `\n"
        "        -File .\\scripts\\windows\\build_local_production.ps1 `\n"
        "        -OutputDirectory $BuildRoot\n"
        "    if ($LASTEXITCODE -ne 0) {\n"
        "        throw (\"L4_PACKAGE_BUILD_FAILED:{0}\" -f $LASTEXITCODE)\n"
        "    }\n"
        "    $archive = Join-Path $BuildRoot \"QuantumLocalProduction_HOME_LOCAL.zip\"\n"
        "}\n"
        "else {\n"
        "    $archive = (Resolve-Path -LiteralPath $PackageArchive).Path\n"
        "    $packageOrigin = \"PREBUILT_SAME_ARTIFACT\"\n"
        "}\n"
        "if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) {\n"
        "    throw \"L4_PACKAGE_NOT_FOUND\"\n"
        "}\n"
        "$packageHash = Get-Sha256 -Path $archive\n",
    )
    replace_once(
        "scripts/ci/l4_installed_runtime.ps1",
        "    status = \"L4_INSTALLED_RUNTIME_PASS\"\n"
        "    evidence_level = \"L4_INSTALLED_RUNTIME\"\n"
        "    exact_head = $ExactHead\n",
        "    status = \"L4_INSTALLED_RUNTIME_PASS\"\n"
        "    evidence_level = \"L4_INSTALLED_RUNTIME\"\n"
        "    exact_head = $ExactHead\n"
        "    validation_slot = $EvidenceSlot\n",
    )
    replace_once(
        "scripts/ci/l4_installed_runtime.ps1",
        "    source_package = [ordered]@{\n        path = $archive\n",
        "    source_package = [ordered]@{\n"
        "        path = $archive\n"
        "        origin = $packageOrigin\n",
    )
    replace_once(
        "scripts/ci/l4_installed_runtime_postcheck.ps1",
        "[CmdletBinding()]\nparam()\n",
        "[CmdletBinding()]\nparam(\n"
        "    [ValidatePattern(\"^[A-Za-z0-9_-]+$\")]\n"
        "    [string]$EvidenceSlot = \"default\"\n"
        ")\n",
    )
    replace_once(
        "scripts/ci/l4_installed_runtime_postcheck.ps1",
        "$EvidenceRoot = Join-Path $RepoRoot \"artifacts\\l4-installed-runtime\"\n",
        "$EvidenceRoot = Join-Path $RepoRoot "
        "(\"artifacts\\l4-installed-runtime-\" + $EvidenceSlot)\n",
    )

    integration = ROOT / "tests/integration_manifest_support_m8.py"
    text = integration.read_text(encoding="utf-8")
    marker = "for number in range(1, 97)"
    if text.count(marker) != 1:
        raise SystemExit("M3_MANIFEST_RANGE_NOT_FOUND")
    integration.write_text(
        text.replace(marker, "for number in range(1, 98)"),
        encoding="utf-8",
        newline="\n",
    )

    temporary_paths = (
        "tools/M3_CI_CONSOLIDATION_TRIGGER.txt",
        "tools/m3_apply_stage.py",
        ".github/workflows/m3-stage-applicator.yml",
        ".github/workflows/m3-stage-applicator-r2.yml",
        ".github/workflows/m3-export-source.yml",
    )
    for relative in temporary_paths:
        (ROOT / relative).unlink(missing_ok=True)

    tracked_entries: list[list[object]] = []
    for relative in (
        ".github/workflows/m3-consolidated-ci.yml",
        "scripts/ci/l4_installed_runtime.ps1",
        "scripts/ci/l4_installed_runtime_postcheck.ps1",
        "tools/m3_same_artifact_compare.py",
        "tests/test_m3_ci_consolidation.py",
        "tests/integration_manifest_support_m8.py",
        "docs/evidence/M3_CI_CONSOLIDATION_RTM.json",
    ):
        data = (ROOT / relative).read_bytes()
        tracked_entries.append(
            [relative, hashlib.sha256(data).hexdigest(), len(data)]
        )

    manifest = {
        "base_pilot_integration_r96_overlay_git_blob_sha": R96_OVERLAY_BLOB_SHA,
        "entries": tracked_entries,
        "hash_encoding": "sha256-hex",
        "overlay_version": 97,
        "reason": (
            "M3 CI consolidation: source gates precede one HOME_LOCAL package "
            "build; two independent Windows L4 validators consume the same "
            "hash-bound artifact. Approved UI, Gatekeeper disconnection, "
            "WB_ONLY scope and marketplace-write-disabled state are unchanged."
        ),
        "remove_paths": list(temporary_paths),
    }
    manifest_path = (
        ROOT
        / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R97.json"
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("M3_STAGE_PATCH=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
