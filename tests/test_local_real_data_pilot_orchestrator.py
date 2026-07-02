from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import unittest

from quantum.finance import canonical_hash
from quantum.pilot import (
    LocalPilotExecutionError,
    LocalPilotScope,
    execute_local_read_only_pilot,
    finance_result_snapshot,
)
from tests.p16_fixtures import *  # noqa: F403
from tests.test_b1b_redteam_runtime_regressions import valid_request
from tests.test_b2_source_reconciliation import total


class LocalRealDataPilotOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tenant = TenantContext("tenant-1", "account-1")
        self.registry = RealDatasetAdmissionRegistry()
        self.payload = wrap_xlsx(build_xlsx())
        self.declaration = declaration(self.tenant, self.payload)
        self.scope = LocalPilotScope(
            host="127.0.0.1",
            port=18080,
            operator_id="operator-1",
            organization_id="org-1",
            tenant_id="tenant-1",
            account_id="account-1",
        )
        self.observed_at = NOW + timedelta(minutes=1)
        self.admitted_at = NOW + timedelta(minutes=2)
        self.reconciled_at = NOW + timedelta(minutes=3)
        self.request = valid_request()
        self.request["calculated_at"] = (
            NOW + timedelta(minutes=2, seconds=30)
        ).isoformat().replace("+00:00", "Z")

    def reconciliation_policy(self) -> dict:
        value = {
            "policy_id": "local-pilot-orchestrator-v1",
            "version": 1,
            "content_hash": "",
            "row_count_tolerance": 0,
            "metric_tolerances": {
                "net_profit_amount": {
                    "absolute": "0.01",
                    "value_type": "MONEY",
                    "unit": "MONEY",
                    "currency": "RUB",
                },
            },
        }
        value["content_hash"] = canonical_hash(
            value,
            exclude=frozenset({"content_hash"}),
        )
        return value

    def source_snapshot(self, *, profit: str = "3980.00") -> dict:
        return {
            "dataset_id": self.declaration.dataset_id,
            "original_file_sha256": self.declaration.original_file_sha256,
            "row_count": self.declaration.expected_row_count,
            "totals": {"net_profit_amount": total(profit)},
        }

    def execute(self, **overrides):
        values = {
            "scope": self.scope,
            "tenant": self.tenant,
            "registry": self.registry,
            "declaration": self.declaration,
            "payload": self.payload,
            "inspection_policy": policy(),
            "dataset_control_evidence_builder": lambda record: dataset_evidence(
                self.tenant,
                record,
            ),
            "storage_evidence_builder": lambda record: evidence(
                self.tenant,
                record,
            ),
            "observed_at": self.observed_at,
            "admitted_at": self.admitted_at,
            "finance_requests": {"synthetic": self.request},
            "source_snapshot": self.source_snapshot(),
            "reconciliation_metric_bindings": {
                "net_profit_amount": (("synthetic", "net_profit_amount"),),
            },
            "reconciliation_policy": self.reconciliation_policy(),
            "reconciled_at": self.reconciled_at,
        }
        values.update(overrides)
        return execute_local_read_only_pilot(**values)

    def test_full_chain_reconciles_and_hashes_without_raw_payload(self) -> None:
        result = self.execute()
        self.assertEqual(result["dataset"]["state"], "ADMITTED")
        self.assertEqual(result["reconciliation"]["state"], "RECONCILED")
        self.assertEqual(len(result["evidence_hash"]), 64)
        self.assertFalse(result["raw_payload_persisted"])
        self.assertFalse(result["scope"]["marketplace_write_enabled"])
        self.assertNotIn(self.payload.hex(), str(result))

    def test_retry_reuses_admitted_record(self) -> None:
        first = self.execute()
        second = self.execute()
        self.assertEqual(first["dataset"], second["dataset"])
        self.assertEqual(first["evidence_hash"], second["evidence_hash"])

    def test_retry_rejects_different_inspection_policy(self) -> None:
        self.execute()
        with self.assertRaisesRegex(
            LocalPilotExecutionError,
            "PILOT_INSPECTION_POLICY_MISMATCH",
        ):
            self.execute(inspection_policy=object())

    def test_non_loopback_scope_fails_before_admission(self) -> None:
        bad = replace(self.scope, host="0.0.0.0")
        with self.assertRaisesRegex(
            LocalPilotExecutionError,
            "PILOT_LOOPBACK_REQUIRED",
        ):
            self.execute(scope=bad)

    def test_marketplace_writes_fail_before_admission(self) -> None:
        bad = replace(self.scope, marketplace_write_enabled=True)
        with self.assertRaisesRegex(
            LocalPilotExecutionError,
            "PILOT_MARKETPLACE_WRITES_FORBIDDEN",
        ):
            self.execute(scope=bad)

    def test_finance_organization_mismatch_fails_closed(self) -> None:
        request = deepcopy(self.request)
        request["organization_id"] = "org-2"
        with self.assertRaisesRegex(
            LocalPilotExecutionError,
            "PILOT_FINANCE_ORGANIZATION_MISMATCH",
        ):
            self.execute(finance_requests={"synthetic": request})

    def test_non_string_finance_label_fails_with_stable_code(self) -> None:
        with self.assertRaisesRegex(
            LocalPilotExecutionError,
            "PILOT_FINANCE_LABEL_INVALID",
        ):
            self.execute(finance_requests={1: self.request})  # type: ignore[dict-item]

    def test_finance_timestamp_must_be_inside_execution_window(self) -> None:
        request = deepcopy(self.request)
        request["calculated_at"] = (NOW - timedelta(seconds=1)).isoformat()
        with self.assertRaisesRegex(
            LocalPilotExecutionError,
            "PILOT_FINANCE_TIMESTAMP_OUT_OF_RANGE",
        ):
            self.execute(finance_requests={"synthetic": request})

    def test_unknown_schema_never_reaches_finance(self) -> None:
        payload = build_xlsx(headers=("different", "header", "set"))
        declaration_value = declaration(self.tenant, payload)
        with self.assertRaisesRegex(
            LocalPilotExecutionError,
            "PILOT_DATASET_NOT_VALIDATED:QUARANTINED",
        ):
            self.execute(payload=payload, declaration=declaration_value)

    def test_material_b2_difference_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            LocalPilotExecutionError,
            "PILOT_RECONCILIATION_CONFLICT",
        ):
            self.execute(source_snapshot=self.source_snapshot(profit="3979.98"))

    def test_source_identity_mismatch_fails_before_finance(self) -> None:
        source = self.source_snapshot()
        source["original_file_sha256"] = "b" * 64
        with self.assertRaisesRegex(
            LocalPilotExecutionError,
            "PILOT_SOURCE_SNAPSHOT_IDENTITY_MISMATCH",
        ):
            self.execute(source_snapshot=source)

    def test_snapshot_binding_requires_existing_finance_metric(self) -> None:
        with self.assertRaisesRegex(
            LocalPilotExecutionError,
            "PILOT_RECONCILIATION_BINDING_INVALID",
        ):
            finance_result_snapshot(
                dataset_id=self.declaration.dataset_id,
                original_file_sha256=self.declaration.original_file_sha256,
                row_count=self.declaration.expected_row_count,
                finance_results={"synthetic": {"results": {}}},
                metric_bindings={
                    "net_profit_amount": (("synthetic", "missing"),),
                },
            )

    def test_duplicate_metric_binding_is_rejected(self) -> None:
        result = self.execute()
        with self.assertRaisesRegex(
            LocalPilotExecutionError,
            "PILOT_RECONCILIATION_BINDING_DUPLICATE",
        ):
            finance_result_snapshot(
                dataset_id=self.declaration.dataset_id,
                original_file_sha256=self.declaration.original_file_sha256,
                row_count=self.declaration.expected_row_count,
                finance_results={"synthetic": result["finance_results"]["synthetic"]},
                metric_bindings={
                    "net_profit_amount": (
                        ("synthetic", "net_profit_amount"),
                        ("synthetic", "net_profit_amount"),
                    ),
                },
            )

    def test_explicit_bindings_sum_multiple_finance_results(self) -> None:
        request_two = deepcopy(self.request)
        request_two["calculation_id"] = "calc-redteam-2"
        source = self.source_snapshot(profit="7960.00")
        result = self.execute(
            finance_requests={
                "first": self.request,
                "second": request_two,
            },
            source_snapshot=source,
            reconciliation_metric_bindings={
                "net_profit_amount": (
                    ("first", "net_profit_amount"),
                    ("second", "net_profit_amount"),
                ),
            },
        )
        self.assertEqual(
            result["reconciliation"]["metrics"]["net_profit_amount"]["state"],
            "MATCH",
        )


if __name__ == "__main__":
    unittest.main()
