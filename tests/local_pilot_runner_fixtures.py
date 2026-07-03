from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

from quantum.finance import canonical_hash
from tests.p16_fixtures import build_xlsx, policy, wrap_xlsx
from tests.test_b1b_redteam_runtime_regressions import valid_request
from tests.test_b2_source_reconciliation import total

DATASET_ID = "22222222-2222-4222-8222-222222222222"
RUN_ID = "pilot-run-001"
TENANT_ID = "tenant-1"


def reconciliation_policy() -> dict:
    value = {
        "policy_id": "local-pilot-runner-v1",
        "version": 1,
        "content_hash": "",
        "row_count_tolerance": 0,
        "metric_tolerances": {
            "net_profit_amount": {
                "absolute": "0.01",
                "value_type": "MONEY",
                "unit": "MONEY",
                "currency": "RUB",
            }
        },
    }
    value["content_hash"] = canonical_hash(
        value,
        exclude=frozenset({"content_hash"}),
    )
    return value


def manifest(*, source_profit: str = "3980.00") -> dict:
    request = valid_request()
    request["calculated_at"] = "2026-07-02T00:00:00Z"
    inspection_policy = asdict(policy())
    return {
        "schema_version": "quantum-local-pilot-manifest-v1",
        "run_id": RUN_ID,
        "source_file": "sample.zip",
        "scope": {
            "host": "127.0.0.1",
            "port": 18080,
            "operator_id": "operator-1",
            "organization_id": "org-1",
            "tenant_id": TENANT_ID,
            "account_id": "account-1",
            "read_only": True,
            "single_operator": True,
            "single_organization": True,
            "marketplace_write_enabled": False,
            "production_credentials_enabled": False,
            "public_hosting_enabled": False,
        },
        "timestamps": {
            "declared_at": "2026-07-01T23:57:00Z",
            "observed_at": "2026-07-01T23:58:00Z",
            "admitted_at": "2026-07-01T23:59:00Z",
            "reconciled_at": "2026-07-02T00:01:00Z",
        },
        "dataset": {
            "dataset_id": DATASET_ID,
            "source_internal_id": "source-wb-001",
            "marketplace": "wildberries",
            "report_type": "weekly-detailed",
            "reporting_period_start": "2026-06-01",
            "reporting_period_end": "2026-06-07",
            "timezone": "Europe/Moscow",
            "expected_row_count": 1,
            "control_totals_sha256": "0" * 64,
            "data_categories": ["financial_operations", "product_identifiers"],
            "sensitivity": "COMMERCIAL_CONFIDENTIAL",
            "owner_authority_reference": "owner-attestation-001",
            "lawful_authority_attested": True,
            "retention_deadline": "2026-07-31T00:00:00Z",
        },
        "inspection_policy": inspection_policy,
        "controls": {
            "dataset_evidence_id": "dataset-evidence-001",
            "dataset_verifier_account_id": "dataset-reviewer-1",
            "source_authority_verified": True,
            "report_period_verified": True,
            "control_totals_verified": True,
            "direct_identifiers_absent_or_approved": True,
            "malware_scan_clean": True,
            "malware_scan_evidence_sha256": "a" * 64,
            "storage_evidence_id": "storage-evidence-001",
            "storage_verifier_account_id": "storage-reviewer-1",
            "loopback_only": True,
            "transport_encrypted": False,
            "encryption_at_rest": False,
            "tenant_scoped_paths": True,
            "immutable_original": True,
            "separated_quarantine_and_admitted_zones": True,
            "least_privilege_credentials": True,
        },
        "finance_requests": {"synthetic": request},
        "finance_lineage": {
            "synthetic": {
                "dataset_id": DATASET_ID,
                "normalization_evidence_sha256": "b" * 64,
                "source_row_count": 1,
            }
        },
        "source_snapshot": {
            "row_count": 1,
            "totals": {"net_profit_amount": total(source_profit)},
        },
        "reconciliation_metric_bindings": {
            "net_profit_amount": [["synthetic", "net_profit_amount"]]
        },
        "reconciliation_policy": reconciliation_policy(),
    }


def write_case(root: Path, *, document: dict | None = None) -> tuple[Path, bytes]:
    payload = wrap_xlsx(build_xlsx())
    manifest_path = root / "pilot.json"
    (root / "sample.zip").write_bytes(payload)
    manifest_path.write_text(
        json.dumps(document or manifest(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest_path, payload


def changed(document: dict, *path_and_value) -> dict:
    output = deepcopy(document)
    *path, value = path_and_value
    target = output
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return output
