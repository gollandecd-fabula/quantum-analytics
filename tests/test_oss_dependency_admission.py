from __future__ import annotations

import json
import unittest
from pathlib import Path

from quantum.dependencies.admission import (
    load_json_document,
    validate_register,
    validate_sbom,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs/dependencies/OSS_DEPENDENCY_REGISTER.yaml"
LICENSES = ROOT / "docs/dependencies/LICENSE_ALLOWLIST.yaml"
SBOM = ROOT / "docs/dependencies/SBOM.spdx.json"
NOTICES = ROOT / "docs/dependencies/THIRD_PARTY_NOTICES.md"
POLICY = ROOT / "docs/security/SUPPLY_CHAIN_POLICY.md"
STATE = ROOT / "docs/evidence/OSS_DEPENDENCY_ADMISSION_STATE.yaml"
SCANNER = ROOT / "src/quantum/scripts/oss_admission_scan.py"

EXPECTED_COMPONENTS = {
    "duckdb": ("PyPI", "1.5.4", "MIT"),
    "polars": ("PyPI", "1.42.0", "MIT"),
    "pandera": ("PyPI", "0.32.0", "MIT"),
    "hypothesis": ("PyPI", "6.155.7", "MPL-2.0"),
    "fastapi": ("PyPI", "0.138.1", "MIT"),
    "pydantic": ("PyPI", "2.13.4", "MIT"),
    "react-admin": ("npm", "5.15.1", "MIT"),
    "echarts": ("npm", "6.1.0", "Apache-2.0"),
    "wbsdk": ("PyPI", "1.2.8", "MIT"),
}


class OssDependencyAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.register = load_json_document(REGISTER)
        self.licenses = load_json_document(LICENSES)
        self.sbom = load_json_document(SBOM)

    def test_01_register_and_sbom_validate(self) -> None:
        self.assertEqual(validate_register(self.register, self.licenses), ())
        self.assertEqual(validate_sbom(self.register, self.sbom), ())

    def test_02_exact_candidate_set_and_versions(self) -> None:
        actual = {
            item["name"]: (item["ecosystem"], item["version"], item["license"])
            for item in self.register["components"]
        }
        self.assertEqual(actual, EXPECTED_COMPONENTS)

    def test_03_no_runtime_installation_or_marketplace_writes(self) -> None:
        self.assertIs(self.register["runtime_installation_authorized"], False)
        self.assertIs(self.register["marketplace_write_enabled"], False)
        self.assertTrue(all(
            item["installation_authorized"] is False
            for item in self.register["components"]
        ))

    def test_04_wbsdk_is_fail_closed_until_separate_audit(self) -> None:
        wbsdk = next(item for item in self.register["components"] if item["name"] == "wbsdk")
        self.assertEqual(wbsdk["status"], "AUDIT_REQUIRED")
        self.assertIs(wbsdk["read_only_facade_required"], True)
        self.assertIs(wbsdk["write_methods_exposed"], True)
        self.assertIn("direct use by domain services", wbsdk["prohibited_use"])

    def test_05_license_policy_rejects_strong_copyleft_direct_integration(self) -> None:
        prohibited = set(self.licenses["prohibited_direct_integration"])
        self.assertIn("AGPL-3.0-only", prohibited)
        self.assertIn("GPL-2.0-only", prohibited)
        self.assertIn("GPL-3.0-only", prohibited)
        conditional = {
            item["license"]: item["conditions"]
            for item in self.licenses["conditional_licenses"]
        }
        self.assertIn("MPL-2.0", conditional)
        self.assertIn("development_or_test_scope_only", conditional["MPL-2.0"])

    def test_06_state_preserves_all_release_and_scope_gates(self) -> None:
        state = load_json_document(STATE)
        self.assertEqual(state["status"], "R2_VALIDATED")
        self.assertIs(state["runtime_installation_authorized"], False)
        self.assertIs(state["marketplace_write_enabled"], False)
        self.assertIn("release_blocked", state["restrictions"])
        self.assertEqual(state["gates"]["wbsdk_source_audit"], "NOT_STARTED_SEPARATE_STAGE")
        self.assertEqual(state["gates"]["official_registry_verification"], "PASS")
        self.assertEqual(state["gates"]["osv_vulnerability_scan"], "PASS_ZERO_KNOWN_VULNERABILITIES")
        self.assertEqual(state["component_counts"]["pending_registry_confirmation"], 0)

    def test_07_notices_and_policy_cover_admitted_components(self) -> None:
        notices = NOTICES.read_text(encoding="utf-8")
        policy = POLICY.read_text(encoding="utf-8")
        for name in EXPECTED_COMPONENTS:
            self.assertIn(name.lower(), notices.lower())
        self.assertIn("Automatic dependency upgrades are forbidden", policy)
        self.assertIn("read-only allowlist", policy)
        self.assertIn("RELEASE_BLOCKED", policy)

    def test_08_online_scanner_uses_official_registries_and_osv_fail_closed(self) -> None:
        source = SCANNER.read_text(encoding="utf-8")
        self.assertIn("https://pypi.org/pypi/", source)
        self.assertIn("https://registry.npmjs.org/", source)
        self.assertIn("https://api.osv.dev/v1/querybatch", source)
        self.assertIn("known vulnerabilities found", source)
        self.assertNotIn("requests", source)


if __name__ == "__main__":
    unittest.main()
