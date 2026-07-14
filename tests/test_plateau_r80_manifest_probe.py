from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
TRACKED = (
    "src/quantum/application/_finance_center_queue.py",
    "src/quantum/application/_finance_center_queue_runtime.py",
    "src/quantum/application/_finance_center_reports.py",
    "src/quantum/application/_finance_profile_model.py",
    "src/quantum/application/_finance_profile_groups.py",
    "src/quantum/application/finance_profile.py",
    "src/quantum/application/_finance_center_dialog.py",
    "src/quantum/application/_finance_profile_financial_rows.py",
    "src/quantum/application/_finance_profile_engine.py",
    "src/quantum/application/_finance_center_calculation.py",
    "tests/test_plateau_m1_runtime_integration.py",
    "tests/test_plateau_m2_financial_integration.py",
    "tests/test_finance_center_profile.py",
    "tests/test_profile_save_and_shortcut_hotfix.py",
    "tests/integration_manifest_support_m8.py",
)


class PlateauR80ManifestProbe(unittest.TestCase):
    def test_emit_exact_r80_byte_inventory(self) -> None:
        entries = []
        for relative in TRACKED:
            raw = (ROOT / relative).read_bytes()
            entries.append([relative, sha256(raw).hexdigest(), len(raw)])
        self.fail(
            "PLATEAU_R80_ENTRIES="
            + json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
        )


if __name__ == "__main__":
    unittest.main()
