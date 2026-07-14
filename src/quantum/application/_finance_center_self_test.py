from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
from typing import Any

from quantum.application.finance_profile import (
    ProductRecord,
    build_profile,
    calculate_by_group,
    confirm_profile,
)
from quantum.application.local_app import ImportRow


def _config_check(config: Path) -> tuple[bool, str | None]:
    try:
        raw = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return False, type(exc).__name__
    if not isinstance(raw, dict):
        return False, "CONFIG_NOT_OBJECT"
    if raw.get("configuration_status") not in {None, "READY"}:
        return False, "CONFIG_NOT_READY"
    if not str(raw.get("tenant_id") or "").strip():
        return False, "TENANT_ID_MISSING"
    if raw.get("execution_mode", "FULL") not in {
        "FULL",
        "ADMISSION_ONLY",
    }:
        return False, "EXECUTION_MODE_INVALID"
    return True, None


def _known_answer_finance() -> tuple[bool, dict[str, str]]:
    profile = build_profile(
        (ProductRecord("KNOWN", "Товар", "Футболка", "self-test"),)
    )
    profile.tax_rate_percent = "6"
    profile.tax_base_metric_id = "gross_sales_amount"
    profile.other_expense_per_unit = "40"
    group = profile.groups["Футболка"]
    group.cost_per_unit = "400"
    group.resalable_returned_units = "0"
    group.compensated_returned_units = "0"
    group.return_compensation_amount = "0"
    group.discounts_amount = "0"
    group.subsidies_amount = "0"
    group.advertising_amount = "0"
    confirm_profile(profile)
    row = {
        "reportId": "self-test-report",
        "rrdId": "1",
        "dateFrom": "2026-07-01",
        "dateTo": "2026-07-07",
        "currency": "RUB",
        "vendorCode": "KNOWN",
        "techSize": "M",
        "sku": "460000000001",
        "docTypeName": "Продажа",
        "sellerOperName": "Продажа",
        "quantity": "2",
        "retailAmount": "2000",
        "ppvzSalesCommission": "200",
        "forPay": "1680",
        "ppvzReward": "0",
        "acquiringFee": "0",
        "deliveryAmount": "1",
        "returnAmount": "0",
        "deliveryService": "100",
        "paidStorage": "20",
        "penalty": "0",
        "deduction": "0",
        "paidAcceptance": "0",
        "rebillLogisticCost": "0",
        "additionalPayment": "0",
        "orderDt": "2026-07-01",
        "saleDt": "2026-07-02",
        "srid": "self-test-sale",
    }
    result = calculate_by_group(
        detailed_rows=(row,),
        profile=profile,
        organization_id="tenant-self-test",
        source_id="self-test:known-answer",
        source_sha256="a" * 64,
    )
    expected = {
        "net_sold_units": "2.00",
        "product_cost_amount": "800.00",
        "other_expense_amount": "80.00",
        "tax_amount": "120.00",
        "net_profit_amount": "680.00",
        "profit_per_sold_unit": "340.00",
    }
    actual = {key: result.totals.get(key, "") for key in expected}
    return result.status == "CALCULATED" and actual == expected, actual


def _runtime_mro_check() -> bool:
    from quantum.application.finance_center import QuantumFinanceCenter
    from quantum.application._finance_center_queue_runtime import (
        FinanceCenterQueueRuntimeMixin,
    )

    return all(
        getattr(QuantumFinanceCenter, name).__module__
        == FinanceCenterQueueRuntimeMixin.__module__
        for name in (
            "add_reports",
            "_worker",
            "_drain_events",
            "repeat_selected",
        )
    )


def _persistence_round_trip() -> tuple[bool, dict[str, Any]]:
    from quantum.application._finance_center_persistence import (
        REPORT_INDEX_RELATIVE_PATH,
        REPORT_INDEX_SCHEMA_VERSION,
        restore_reports,
        save_report_index,
    )

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        config = root / "config" / "default-home-local.json"
        config.parent.mkdir(parents=True)
        config.write_text(
            json.dumps(
                {
                    "configuration_status": "READY",
                    "execution_mode": "ADMISSION_ONLY",
                    "tenant_id": "tenant-self-test",
                }
            ),
            encoding="utf-8",
        )
        payload = b"self-test-immutable-source"
        digest = sha256(payload).hexdigest()
        dataset_id = "self-test-dataset"
        tenant_token = sha256(b"tenant-self-test").hexdigest()
        managed = (
            root
            / "data"
            / "pilot-zones"
            / tenant_token
            / "admitted"
            / dataset_id
            / digest
        )
        managed.parent.mkdir(parents=True)
        managed.write_bytes(payload)
        report = {
            "status": "ADMISSION_COMPLETE",
            "dataset_id": dataset_id,
            "file_sha256": digest,
            "file_size_bytes": len(payload),
            "sanitized_filename": "self-test.xlsx",
            "source_bridge": {
                "status": "SOURCE_BRIDGE_COMPLETE",
                "source_type": "WB_DETAILED_FINANCIAL",
            },
        }
        output = root / "output" / "pilot_gui_self_test.json"
        output.parent.mkdir(parents=True)
        output.write_text(json.dumps(report), encoding="utf-8")
        row = ImportRow(
            row_id="self-test",
            source_path=managed,
            size_text=str(len(payload)),
            output_path=output,
            status="Готово",
            detected_format="WB_DETAILED_FINANCIAL",
            progress="100%",
            report=report,
            details={"original_source_name": "self-test.xlsx"},
        )
        index_path = save_report_index(root, (row,))
        index = json.loads(index_path.read_text(encoding="utf-8"))
        restored = restore_reports(root, config)
        serialized = json.dumps(index, ensure_ascii=False)
        details = {
            "schema_version": index.get("schema_version"),
            "restored_count": len(restored),
            "contains_external_absolute_path": str(root) in serialized,
            "index_path": str(index_path.relative_to(root)),
        }
        passed = (
            index.get("schema_version") == REPORT_INDEX_SCHEMA_VERSION
            and index_path == root / REPORT_INDEX_RELATIVE_PATH
            and len(restored) == 1
            and restored[0].row.source_path == managed.resolve()
            and not details["contains_external_absolute_path"]
        )
        return passed, details


def run_finance_center_self_test(
    root: Path,
    config: Path,
) -> dict[str, object]:
    checks: dict[str, bool] = {}
    diagnostics: dict[str, object] = {}

    checks["root_exists"] = root.resolve().is_dir()
    checks["config_exists"] = config.resolve().is_file()
    config_ok, config_error = _config_check(config)
    checks["config_valid"] = config_ok
    if config_error:
        diagnostics["config_error"] = config_error

    try:
        finance_ok, actual = _known_answer_finance()
    except Exception as exc:
        finance_ok = False
        actual = {"error": type(exc).__name__}
    checks["known_answer_finance"] = finance_ok
    diagnostics["known_answer_actual"] = actual

    try:
        checks["runtime_mro"] = _runtime_mro_check()
    except Exception as exc:
        checks["runtime_mro"] = False
        diagnostics["runtime_mro_error"] = type(exc).__name__

    try:
        persistence_ok, persistence = _persistence_round_trip()
    except Exception as exc:
        persistence_ok = False
        persistence = {"error": type(exc).__name__}
    checks["persistence_round_trip"] = persistence_ok
    diagnostics["persistence"] = persistence

    try:
        from quantum.application._finance_schema_review import (
            build_schema_review_preview,
        )

        checks["schema_review_gate"] = callable(
            build_schema_review_preview
        )
    except Exception as exc:
        checks["schema_review_gate"] = False
        diagnostics["schema_review_error"] = type(exc).__name__

    checks["marketplace_writes_disabled"] = True
    passed = all(checks.values())
    return {
        "status": (
            "FINANCE_CENTER_SELF_TEST_PASS"
            if passed
            else "FINANCE_CENTER_SELF_TEST_FAILED"
        ),
        "checks": checks,
        "diagnostics": diagnostics,
        "marketplace_write_enabled": False,
        "release_scope": "WB_ONLY",
    }


__all__ = ["run_finance_center_self_test"]
