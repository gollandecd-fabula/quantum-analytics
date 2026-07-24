from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/m3-consolidated-ci.yml"


class M3CiConsolidationTests(unittest.TestCase):
    def test_order_is_source_then_one_build_then_same_artifact(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("needs: [source-foundation, source-oss]", text)
        self.assertIn("needs: build-once", text)
        self.assertIn("needs: [build-once, l4-same-artifact]", text)
        self.assertEqual(text.count("build_local_production.ps1"), 1)
        self.assertEqual(text.count("M3-Build-Once-${{ env.TARGET_SHA }}"), 2)

    def test_two_validators_consume_prebuilt_archive(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("slot: [A, B]", text)
        self.assertIn("-PackageArchive $archive", text)
        self.assertIn("-EvidenceSlot \"${{ matrix.slot }}\"", text)
        validator = text[text.index("l4-same-artifact:"):]
        self.assertNotIn("build_two_installer_bundles.ps1", validator)

    def test_l4_supports_prebuilt_same_artifact_fail_closed(self) -> None:
        text = (ROOT / "scripts/ci/l4_installed_runtime.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn('[string]$PackageArchive = ""', text)
        self.assertIn('"PREBUILT_SAME_ARTIFACT"', text)
        self.assertIn("Resolve-Path -LiteralPath $PackageArchive", text)
        self.assertIn("validation_slot = $EvidenceSlot", text)
        self.assertIn("origin = $packageOrigin", text)

    def test_comparator_requires_identical_installed_manifest(self) -> None:
        text = (ROOT / "tools/m3_same_artifact_compare.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("M3_AB_INSTALLED_MANIFEST_MISMATCH", text)
        self.assertIn('"build_count": 1', text)
        self.assertIn('"validator_count": 2', text)
        self.assertIn('"marketplace_write_enabled": False', text)

    def test_boundaries_are_explicit(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("gatekeeper", text.lower())
        self.assertNotIn("ozon", text.lower())
        self.assertIn('release_scope = "WB_ONLY"', text)
        self.assertIn('marketplace_write_enabled = $false', text)


if __name__ == "__main__":
    unittest.main()
