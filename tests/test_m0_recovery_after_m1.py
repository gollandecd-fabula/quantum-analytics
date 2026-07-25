from __future__ import annotations

import base64
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _surface(text: str) -> str:
    decoded = [
        base64.b64decode(value, validate=True).decode("utf-8")
        for value in re.findall(r'-Encoded\s+["\']([A-Za-z0-9+/=]{16,})["\']', text)
    ]
    return text + "\n" + "\n".join(decoded)


class M0RecoveryAfterM1Tests(unittest.TestCase):
    def test_external_ready_config_is_persisted_fail_closed(self) -> None:
        text = (ROOT / "scripts/windows/one_click_home_local.ps1").read_text(encoding="utf-8")
        self.assertIn('Join-Path $TargetRoot "config\\default-home-local.json"', text)
        surface = _surface(text)
        self.assertIn("Переданная конфигурация конфликтует с существующей управляемой конфигурацией", surface)
        self.assertIn("Move-Item -LiteralPath $temporaryConfig -Destination $managedConfig -Force", text)
        self.assertIn("Переданная конфигурация сохранена в HOME_LOCAL", surface)

    def test_versioned_gate_scripts_publish_explicit_exit_contract(self) -> None:
        for relative in (
            "scripts/ci/windows_local_production_r37.ps1",
            "scripts/ci/native_one_button_r37.ps1",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8").rstrip()
            self.assertTrue(text.endswith("exit 0"), relative)
            self.assertIn("Explicit script contract", text)

    def test_workflow_wrappers_never_overwrite_gate_status(self) -> None:
        for relative in (
            ".github/workflows/windows-local-production.yml",
            ".github/workflows/build-one-button-redteam-r3.yml",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("$gateExitCode = $LASTEXITCODE", text)
            self.assertIn("if ($gateExitCode -ne 0)", text)
            self.assertNotIn("          exit 0", text)


if __name__ == "__main__":
    unittest.main()
