from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement marker, got {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


for path in (
    "src/quantum/pilot/windows_runner.py",
    "src/quantum/pilot/local_runner.py",
):
    replace_once(
        path,
        'args.config.read_text(encoding="utf-8")',
        'args.config.read_text(encoding="utf-8-sig")',
    )

replace_once(
    "scripts/windows/import_source.ps1",
    "    $runtimeConfigObject | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath $runtimeConfig -Encoding UTF8",
    "    $runtimeConfigJson = $runtimeConfigObject | ConvertTo-Json -Depth 16\n"
    "    [IO.File]::WriteAllText($runtimeConfig, $runtimeConfigJson, ([System.Text.UTF8Encoding]::new($false)))",
)
replace_once(
    "scripts/windows/configure_home_local.ps1",
    "$config | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $ConfigPath -Encoding UTF8",
    "$configJson = $config | ConvertTo-Json -Depth 12\n"
    "[IO.File]::WriteAllText($ConfigPath, $configJson, ([System.Text.UTF8Encoding]::new($false)))",
)

test_path = ROOT / "tests/test_windows_redteam_hardening.py"
test_text = test_path.read_text(encoding="utf-8")
method_name = "    def test_discover_only_accepts_utf8_bom_config(self):\n"
if method_name in test_text:
    raise SystemExit("BOM regression already exists unexpectedly")
marker = "\n\nclass AdmissionOnlyRedTeamTests(unittest.TestCase):\n"
if test_text.count(marker) != 1:
    raise SystemExit("BOM regression insertion marker is invalid")
method = '''
    def test_discover_only_accepts_utf8_bom_config(self):
        workbook = build_xlsx(
            headers=("Артикул", "Количество продаж", "Сумма продаж"),
        )
        config = {
            "inspection_policy": json.loads(json.dumps(asdict(policy()))),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "report.xlsx"
            source.write_bytes(workbook)
            config_path = root / "config.json"
            config_path.write_bytes(
                b"\\xef\\xbb\\xbf" + json.dumps(config).encode("utf-8")
            )
            output = root / "preview.json"
            argv = [
                "windows_runner",
                "--file",
                str(source),
                "--config",
                str(config_path),
                "--storage-root",
                str(root / "storage"),
                "--output",
                str(output),
                "--home-local",
                "--discover-only",
                "--authority-attested",
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch(
                "quantum.pilot.windows_runner._engine.run_local_pilot"
            ) as run_pilot:
                self.assertEqual(main(), 0)
                run_pilot.assert_not_called()
            preview = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(preview["status"], "SCHEMA_DISCOVERED")
            self.assertEqual(preview["file_sha256"], sha256(workbook).hexdigest())
'''
test_path.write_text(test_text.replace(marker, "\n" + method + marker, 1), encoding="utf-8")

tracked = (
    "src/quantum/pilot/windows_runner.py",
    "src/quantum/pilot/local_runner.py",
    "scripts/windows/import_source.ps1",
    "scripts/windows/configure_home_local.ps1",
    "tests/test_windows_redteam_hardening.py",
)
manifest_path = ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R23.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
replacements = {}
for path in tracked:
    data = (ROOT / path).read_bytes()
    replacements[path] = [path, sha256(data).hexdigest(), len(data)]
seen = set()
updated = []
for entry in manifest["entries"]:
    path = entry[0]
    if path in replacements:
        updated.append(replacements[path])
        seen.add(path)
    else:
        updated.append(entry)
if seen != set(tracked):
    raise SystemExit(f"manifest entries missing: {sorted(set(tracked) - seen)}")
manifest["entries"] = updated
manifest["reason"] = (
    "Red-team harden HOME_LOCAL with semantic schema discovery, preview-before-review, "
    "hash-bound scan evidence, safe admission-only onboarding, manifest-verified installation, "
    "UTF-8 BOM compatibility, installed-import diagnostics and exact-head Windows regressions"
)
manifest_path.write_text(
    json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
    encoding="utf-8",
)
print(json.dumps({"status": "BOM_PATCH_APPLIED", "files": len(tracked)}, sort_keys=True))
