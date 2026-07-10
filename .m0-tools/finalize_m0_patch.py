from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path.cwd()
R33_BLOB = "e1093257ebc13ffa0e940af137d2f7802e4b9847"
ENTRY_PATHS = sorted(
    {
        "config/home-local.template.json",
        "scripts/windows/build_local_production.ps1",
        "scripts/windows/configure_home_local.ps1",
        "scripts/windows/install_home_local.ps1",
        "scripts/windows/one_click_home_local.ps1",
        "src/quantum/application/local_app.py",
        "src/quantum/pilot/import_xlsx_source.ps1",
        "src/quantum/pilot/local_runner.py",
        "src/quantum/pilot/windows_runner.py",
        "tests/integration_manifest_support.py",
        "tests/test_m0_attestation_redteam.py",
        "tests/test_windows_one_click_installer_r1.py",
        "tests/test_windows_source_package_launchers_r1.py",
    }
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


support_path = ROOT / "tests/integration_manifest_support.py"
support = support_path.read_text(encoding="utf-8")
old = "for n in range(1, 34)"
new = "for n in range(1, 35)"
if support.count(old) != 1:
    raise SystemExit("M0_MANIFEST_RANGE_ANCHOR_MISMATCH")
support_path.write_text(support.replace(old, new), encoding="utf-8", newline="\n")

for relative in ENTRY_PATHS:
    if not (ROOT / relative).is_file():
        raise SystemExit(f"M0_REQUIRED_FILE_MISSING:{relative}")

builder = (ROOT / "scripts/windows/build_local_production.ps1").read_text(encoding="utf-8-sig")
installer = (ROOT / "scripts/windows/install_home_local.ps1").read_text(encoding="utf-8-sig")
if '-AuthorityAttested -SchemaReviewed' in builder or '-AuthorityAttested -SchemaReviewed' in installer:
    raise SystemExit("M0_LAUNCHER_AUTO_ATTESTATION_REMAINS")
if "Launchers never attest on your behalf" not in builder:
    raise SystemExit("M0_OPERATOR_CONFIRMATION_TEXT_MISSING")

config = json.loads((ROOT / "config/home-local.template.json").read_text(encoding="utf-8-sig"))
if config.get("lawful_authority_attested") is not False:
    raise SystemExit("M0_AUTHORITY_DEFAULT_NOT_FALSE")
if not config.get("attestations") or any(value is not False for value in config["attestations"].values()):
    raise SystemExit("M0_CONTROL_EVIDENCE_PREVERIFIED")

entries = []
for relative in ENTRY_PATHS:
    path = ROOT / relative
    entries.append([relative, digest(path), path.stat().st_size])

overlay = {
    "base_pilot_integration_r33_overlay_git_blob_sha": R33_BLOB,
    "entries": entries,
    "hash_encoding": "sha256-hex",
    "overlay_version": 34,
    "reason": (
        "M0 reconciliation: preserve the canonical HOME_LOCAL line while fail-closing operator "
        "authority and schema-review attestations, binding control evidence to actual review and "
        "malware-scan outcomes, and retaining marketplace writes disabled"
    ),
    "remove_paths": [],
}
overlay_path = ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R34.json"
overlay_path.write_text(json.dumps(overlay, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print("M0_R34_PREPARED")
for row in entries:
    print(*row)
