from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import unittest

from quantum.adapters import (
    DEFERRED_MARKETPLACES,
    LOCAL_RELEASE_MARKETPLACES,
    LOCAL_RELEASE_SCOPE,
    MARKETPLACE_ADAPTER_CONTRACT_VERSION,
    MarketplaceAdapterError,
    MarketplaceAdapterRegistry,
    ReviewedSourceRequest,
    build_default_marketplace_registry,
    normalize_marketplace_id,
)
from quantum.adapters.ozon import OzonSourceAdapter


ROOT = Path(__file__).resolve().parents[1]


class _Adapter:
    marketplace_id = "TEST_MARKET"
    adapter_id = "test-market-v1"
    schema_version = "test-market-schema-v1"

    def __init__(self, *, write_enabled: bool = False) -> None:
        self.write_enabled = write_enabled
        self.calls = 0

    def bridge_reviewed_source(
        self,
        request: ReviewedSourceRequest,
    ) -> Mapping[str, object]:
        self.calls += 1
        return {
            "status": "SOURCE_BRIDGE_PARTIAL",
            "finance_request": None,
            "finance_request_state": "BLOCKED",
            "finance_request_reason_codes": ["TEST_PROFILE_REQUIRED"],
            "marketplace_write_enabled": self.write_enabled,
            "raw_rows_in_report": False,
        }


def request() -> ReviewedSourceRequest:
    return ReviewedSourceRequest(
        payload=b"reviewed-source",
        schema_discovery={
            "sheet_name": "Sheet1",
            "header_row_index": 1,
            "column_count": 2,
            "data_row_count": 3,
        },
        inspection_limits=object(),
        source_id="dataset:test",
        source_context={"currency": "RUB"},
    )


class M6MarketplaceNeutralAdapterTests(unittest.TestCase):
    def test_marketplace_ids_are_canonical_and_missing_values_fail_closed(self):
        self.assertEqual(normalize_marketplace_id("wb"), "WILDBERRIES")
        self.assertEqual(normalize_marketplace_id(" Ozon "), "OZON")
        self.assertEqual(normalize_marketplace_id("future-market"), "FUTURE_MARKET")
        for invalid in (None, "", "bad/id", 7):
            with self.subTest(invalid=invalid):
                with self.assertRaises(MarketplaceAdapterError):
                    normalize_marketplace_id(invalid)

    def test_registry_dispatches_without_exposing_concrete_adapter_to_core(self):
        adapter = _Adapter()
        registry = MarketplaceAdapterRegistry()
        registry.register(adapter)
        registry.freeze()
        result = registry.bridge_reviewed_source("test market", request())
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(result["marketplace_id"], "TEST_MARKET")
        self.assertEqual(result["adapter_id"], "test-market-v1")
        self.assertEqual(
            result["adapter_contract_version"],
            MARKETPLACE_ADAPTER_CONTRACT_VERSION,
        )
        self.assertFalse(result["marketplace_write_enabled"])
        self.assertFalse(result["raw_rows_in_report"])

    def test_registry_rejects_duplicate_unknown_and_post_freeze_changes(self):
        registry = MarketplaceAdapterRegistry()
        registry.register(_Adapter())
        with self.assertRaisesRegex(
            MarketplaceAdapterError,
            "MARKETPLACE_ADAPTER_DUPLICATE",
        ):
            registry.register(_Adapter())
        with self.assertRaisesRegex(
            MarketplaceAdapterError,
            "MARKETPLACE_ADAPTER_NOT_REGISTERED",
        ):
            registry.resolve("FUTURE_MARKET")
        registry.freeze()
        with self.assertRaisesRegex(
            MarketplaceAdapterError,
            "MARKETPLACE_ADAPTER_REGISTRY_FROZEN",
        ):
            registry.register(_Adapter())

    def test_adapter_cannot_enable_marketplace_writes(self):
        registry = MarketplaceAdapterRegistry()
        registry.register(_Adapter(write_enabled=True))
        with self.assertRaisesRegex(
            MarketplaceAdapterError,
            "ADAPTER_MARKETPLACE_WRITE_FORBIDDEN",
        ):
            registry.bridge_reviewed_source("TEST_MARKET", request())

    def test_default_registry_exposes_only_wildberries_for_local_release(self):
        self.assertEqual(LOCAL_RELEASE_SCOPE, "WB_ONLY")
        self.assertEqual(LOCAL_RELEASE_MARKETPLACES, ("WILDBERRIES",))
        self.assertEqual(DEFERRED_MARKETPLACES, ("OZON",))
        registry = build_default_marketplace_registry()
        self.assertEqual(
            registry.registered_marketplaces(),
            ("WILDBERRIES",),
        )
        with self.assertRaisesRegex(
            MarketplaceAdapterError,
            "MARKETPLACE_ADAPTER_NOT_REGISTERED",
        ):
            registry.resolve("OZON")

    def test_deferred_ozon_adapter_remains_fail_closed_when_explicitly_loaded(self):
        registry = MarketplaceAdapterRegistry()
        registry.register(OzonSourceAdapter())
        registry.freeze()
        result = registry.bridge_reviewed_source("OZON", request())
        self.assertEqual(result["status"], "SOURCE_BRIDGE_BLOCKED")
        self.assertEqual(result["marketplace_id"], "OZON")
        self.assertIn(
            "OZON_SOURCE_PROFILE_REQUIRED",
            result["finance_request_reason_codes"],
        )
        self.assertIsNone(result["finance_request"])
        self.assertFalse(result["marketplace_write_enabled"])
        self.assertFalse(result["raw_rows_in_report"])

    def test_core_and_windows_bridge_have_no_direct_wildberries_dependency(self):
        forbidden = (
            "quantum.adapters.wildberries",
            "bridge_reviewed_wb_source",
        )
        boundary_files = [
            ROOT / "src/quantum/pilot/windows_source_bridge.py",
            *(ROOT / "src/quantum/finance").glob("*.py"),
            *(ROOT / "src/quantum/insights").glob("*.py"),
            *(ROOT / "src/quantum/recommendations").glob("*.py"),
        ]
        for path in boundary_files:
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                with self.subTest(path=str(path), token=token):
                    self.assertNotIn(token, text)

    def test_concrete_adapters_do_not_import_application_or_pilot_layers(self):
        for directory in (
            ROOT / "src/quantum/adapters/wildberries",
            ROOT / "src/quantum/adapters/ozon",
        ):
            for path in directory.glob("*.py"):
                text = path.read_text(encoding="utf-8")
                with self.subTest(path=str(path)):
                    self.assertNotIn("quantum.application", text)
                    self.assertNotIn("quantum.pilot", text)
                    self.assertNotIn("quantum.outputs", text)


if __name__ == "__main__":
    unittest.main()
