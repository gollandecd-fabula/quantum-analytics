from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
TRACKED = (
    "pyproject.toml",
    "src/quantum/application/_finance_center_self_test.py",
    "tests/test_plateau_m6_build_metadata.py",
    "docs/governance/CURRENT_STATE.md",
    "docs/evidence/STAGE_B_EXECUTION_STATE.yaml",
    "docs/evidence/M9_DEFECT_REGISTER.json",
    "docs/evidence/M9_PLATEAU_RED_TEAM_REPORT.md",
    "tests/integration_manifest_support_m8.py",
)


class PlateauR84ManifestProbe(unittest.TestCase):
    def test_emit_exact_r84_byte_inventory(self) -> None:
        entries = []
        for relative in TRACKED:
            raw = (ROOT / relative).read_bytes()
            entries.append([relative, sha256(raw).hexdigest(), len(raw)])
        self.fail(
            "PLATEAU_R84_ENTRIES="
            + json.dumps(entries, ensure_ascii=False, separators=(",", ":"))
        )


if __name__ == "__main__":
    unittest.main()
