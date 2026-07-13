from __future__ import annotations

import json
from pathlib import Path
import unittest

from quantum.adapters import (
    DEFERRED_MARKETPLACES,
    LOCAL_RELEASE_MARKETPLACES,
    LOCAL_RELEASE_SCOPE,
    MarketplaceAdapterError,
    build_default_marketplace_registry,
)


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs" / "evidence" / "M9_INDEPENDENT_FINAL_RED_TEAM_PLAN.json"
CONFIG = ROOT / "config" / "home-local.template.json"
BUILDER = ROOT / "scripts" / "windows" / "build_local_production.ps1"


class M9IndependentFinalRedTeamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = json.loads(PLAN.read_text(encoding="utf-8"))
        cls.config = json.loads(CONFIG.read_text(encoding="utf-8"))
        cls.builder = BUILDER.read_text(encoding="utf-8")

    def test_release_scope_is_wildberries_only(self):
        self.assertEqual(LOCAL_RELEASE_SCOPE, "WB_ONLY")
        self.assertEqual(LOCAL_RELEASE_MARKETPLACES, ("WILDBERRIES",))
        self.assertEqual(DEFERRED_MARKETPLACES, ("OZON",))
        registry = build_default_marketplace_registry()
        self.assertEqual(registry.registered_marketplaces(), ("WILDBERRIES",))
        with self.assertRaisesRegex(
            MarketplaceAdapterError,
            "MARKETPLACE_ADAPTER_NOT_REGISTERED",
        ):
            registry.resolve("OZON")

    def test_home_local_configuration_declares_the_same_scope(self):
        self.assertEqual(self.config["release_scope"], "WB_ONLY")
        self.assertEqual(self.config["marketplace"], "WILDBERRIES")
        self.assertEqual(self.config["deferred_marketplaces"], ["OZON"])

    def test_user_package_removes_deferred_ozon_adapter(self):
        self.assertIn('src\\quantum\\adapters\\ozon', self.builder)
        self.assertIn(
            'Remove-Item -LiteralPath $deferredOzonAdapter -Recurse -Force',
            self.builder,
        )
        self.assertIn('release_scope = "WB_ONLY"', self.builder)
        self.assertIn('enabled_marketplaces = @("WILDBERRIES")', self.builder)
        self.assertIn('deferred_marketplaces = @("OZON")', self.builder)

    def test_m9_plan_is_fail_closed_until_external_evidence_exists(self):
        self.assertEqual(self.plan["milestone"], "M9")
        self.assertEqual(self.plan["release_scope"], "WB_ONLY")
        self.assertEqual(self.plan["enabled_marketplaces"], ["WILDBERRIES"])
        self.assertEqual(self.plan["deferred_marketplaces"], ["OZON"])
        self.assertEqual(
            self.plan["current_verdict"],
            "BLOCKED_PENDING_EXTERNAL_EVIDENCE",
        )
        self.assertGreaterEqual(len(self.plan["external_evidence_blockers"]), 2)

    def test_m9_hard_boundaries_remain_closed(self):
        boundaries = self.plan["hard_boundaries"]
        for key in (
            "marketplace_writes_authorized",
            "ozon_release_authorized",
            "merge_to_main_authorized",
            "production_release_authorized",
            "final_score_authorized_before_m9_pass",
            "raw_commercial_data_in_repository",
        ):
            with self.subTest(key=key):
                self.assertIs(boundaries[key], False)

    def test_m9_acceptance_requires_independent_operational_evidence(self):
        gates = self.plan["required_gates"]
        self.assertEqual(gates["open_p0"], 0)
        self.assertEqual(gates["open_p1"], 0)
        self.assertEqual(gates["unresolved_review_threads"], 0)
        self.assertEqual(gates["physical_windows_pilot"], "PASS")
        self.assertEqual(gates["real_wb_dataset_admission"], "RECONCILED")
        self.assertEqual(gates["rollback_bundle"], "VERIFIED")
        self.assertEqual(gates["marketplace_write_capability"], "ABSENT")


if __name__ == "__main__":
    unittest.main()
