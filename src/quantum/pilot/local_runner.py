from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping
from uuid import uuid4

from quantum.access import TenantContext
from quantum.finance import calculate
from quantum.ingestion import (
    DatasetAdmissionState,
    DatasetControlEvidence,
    DatasetDeclaration,
    DatasetSensitivity,
    LocalRawStorage,
    RealDatasetAdmissionRegistry,
    StorageControlEvidence,
    StorageEnvironment,
    UploadReceiptRegistry,
    XlsxInspectionLimits,
    XlsxInspectionPolicy,
    XlsxSchemaExpectation,
)


class LocalPilotError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


_REQUIRED_ATTESTATIONS = {
    "source_authority_verified",
    "report_period_verified",
    "control_totals_verified",
    "direct_identifiers_absent_or_approved",
    "malware_scan_clean",
}
_REQUIRED_FINANCE_METRICS = (
    "net_sold_units",
    "product_cost_amount",
    "other_expense_amount",
    "tax_amount",
    "net_marketplace_income_amount",
    "net_profit_amount",
    "profit_per_sold_unit",
)


def _mapping(value: object, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LocalPilotError(code)
    return value


def _text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LocalPilotError(code)
    return value.strip()


def _date(value: object, code: str) -> date:
    try:
        parsed = date.fromisoformat(_text(value, code))
    except ValueError as exc:
        raise LocalPilotError(code) from exc
    return parsed


def _datetime(value: object, code: str) -> datetime:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LocalPilotError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LocalPilotError(code)
    return parsed.astimezone(UTC)


def _optional_sha(value: object, code: str) -> str | None:
    if value is None:
        return None
    text = _text(value, code)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise LocalPilotError(code)
    return text


def _build_policy(raw: object) -> XlsxInspectionPolicy:
    data = _mapping(raw, "LOCAL_PILOT_POLICY_INVALID")
    limits_raw = _mapping(data.get("limits"), "LOCAL_PILOT_LIMITS_INVALID")
    try:
        limits = XlsxInspectionLimits(**dict(limits_raw))
        schemas_raw = data.get("schemas")
        if not isinstance(schemas_raw, list) or not schemas_raw:
            raise LocalPilotError("LOCAL_PILOT_SCHEMAS_REQUIRED")
        schemas = tuple(
            XlsxSchemaExpectation(**dict(_mapping(item, "LOCAL_PILOT_SCHEMA_INVALID")))
            for item in schemas_raw
        )
        tokens = data.get("prohibited_header_tokens", [])
        if not isinstance(tokens, list) or any(not isinstance(item, str) for item in tokens):
            raise LocalPilotError("LOCAL_PILOT_PROHIBITED_TOKENS_INVALID")
        return XlsxInspectionPolicy(
            policy_id=_text(data.get("policy_id"), "LOCAL_PILOT_POLICY_ID_INVALID"),
            version=data.get("version"),
            limits=limits,
            schemas=schemas,
            prohibited_header_tokens=tuple(tokens),
        )
    except TypeError as exc:
        raise LocalPilotError("LOCAL_PILOT_POLICY_INVALID") from exc


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ).encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
            os.replace(temporary, path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise


def _inspection_summary(record: object) -> dict[str, Any] | None:
    inspection = getattr(record, "inspection", None)
    if inspection is None:
        return None
    return {
        "package_kind": inspection.package_kind,
        "workbook_sha256": inspection.workbook_sha256,
        "sheet_name": inspection.sheet_name,
        "sheet_count": inspection.sheet_count,
        "data_row_count": inspection.data_row_count,
        "column_count": inspection.column_count,
        "formula_count": inspection.formula_count,
        "structural_fingerprint_sha256": inspection.structural_fingerprint_sha256,
        "matched_schema_id": inspection.matched_schema_id,
        "matched_schema_version": inspection.matched_schema_version,
        "diagnostics": list(inspection.diagnostics),
    }


def _base_report(
    *,
    dataset_id: str,
    receipt: object,
    record: object,
    policy: XlsxInspectionPolicy,
) -> dict[str, Any]:
    decisions = [
        {
            "state": decision.state.value,
            "reason_code": decision.reason_code,
            "decided_at": decision.decided_at.isoformat(),
            "diagnostics": list(decision.diagnostics),
        }
        for decision in record.decisions
    ]
    return {
        "runner_version": "LOCAL_PILOT_RUNNER_R1",
        "dataset_id": dataset_id,
        "raw_file_id": receipt.raw_file_id,
        "file_sha256": receipt.sha256,
        "file_size_bytes": receipt.size_bytes,
        "sanitized_filename": receipt.sanitized_filename,
        "duplicate_upload": receipt.duplicate,
        "admission_state": record.state.value,
        "admission_diagnostics": list(record.diagnostics),
        "decisions": decisions,
        "policy": {
            "id": policy.policy_id,
            "version": policy.version,
            "content_hash": policy.content_hash,
        },
        "inspection": _inspection_summary(record),
        "marketplace_write_enabled": False,
        "raw_rows_in_report": False,
    }


def _reconcile(
    result: Mapping[str, Any],
    raw: object,
) -> dict[str, Any]:
    if raw is None:
        return {"state": "PENDING", "differences": []}
    data = _mapping(raw, "LOCAL_PILOT_RECONCILIATION_INVALID")
    expected = _mapping(
        data.get("expected_metrics"),
        "LOCAL_PILOT_EXPECTED_METRICS_INVALID",
    )
    differences: list[dict[str, str | None]] = []
    results = _mapping(result.get("results"), "LOCAL_PILOT_RESULTS_INVALID")
    for metric_id, expected_value in expected.items():
        if not isinstance(metric_id, str) or not isinstance(expected_value, str):
            raise LocalPilotError("LOCAL_PILOT_EXPECTED_METRICS_INVALID")
        actual_metric = results.get(metric_id)
        actual_value = (
            actual_metric.get("value")
            if isinstance(actual_metric, Mapping)
            else None
        )
        if actual_value != expected_value:
            differences.append(
                {
                    "metric_id": metric_id,
                    "expected": expected_value,
                    "actual": actual_value,
                }
            )
    return {
        "state": "CONFLICT" if differences else "RECONCILED",
        "differences": differences,
    }


def run_local_pilot(
    *,
    file_path: Path,
    config: Mapping[str, Any],
    storage_root: Path,
) -> dict[str, Any]:
    if not isinstance(file_path, Path) or not file_path.is_file():
        raise LocalPilotError("LOCAL_PILOT_FILE_NOT_FOUND")
    if not isinstance(storage_root, Path):
        raise LocalPilotError("LOCAL_PILOT_STORAGE_ROOT_INVALID")
    payload = file_path.read_bytes()
    if not payload:
        raise LocalPilotError("LOCAL_PILOT_FILE_EMPTY")

    tenant_id = _text(config.get("tenant_id"), "LOCAL_PILOT_TENANT_INVALID")
    account_id = _text(config.get("account_id"), "LOCAL_PILOT_ACCOUNT_INVALID")
    verifier_id = _text(
        config.get("verifier_account_id"),
        "LOCAL_PILOT_VERIFIER_INVALID",
    )
    if verifier_id == account_id:
        raise LocalPilotError("LOCAL_PILOT_INDEPENDENT_VERIFIER_REQUIRED")
    tenant = TenantContext(tenant_id, account_id)

    receipt = UploadReceiptRegistry().receive(
        tenant=tenant,
        payload=payload,
        filename=file_path.name,
    )
    storage = LocalRawStorage(storage_root)
    storage_record = storage.store(tenant=tenant, receipt=receipt, payload=payload)
    if storage_record.sha256 != receipt.sha256:
        raise LocalPilotError("LOCAL_PILOT_STORAGE_INTEGRITY_FAILED")

    now = datetime.now(UTC)
    dataset_id = str(uuid4())
    declaration = DatasetDeclaration(
        dataset_id=dataset_id,
        tenant_id=tenant_id,
        uploader_account_id=account_id,
        source_internal_id=_text(
            config.get("source_internal_id"),
            "LOCAL_PILOT_SOURCE_ID_INVALID",
        ),
        marketplace=_text(
            config.get("marketplace"),
            "LOCAL_PILOT_MARKETPLACE_INVALID",
        ),
        report_type=_text(
            config.get("report_type"),
            "LOCAL_PILOT_REPORT_TYPE_INVALID",
        ),
        reporting_period_start=_date(
            config.get("reporting_period_start"),
            "LOCAL_PILOT_PERIOD_INVALID",
        ),
        reporting_period_end=_date(
            config.get("reporting_period_end"),
            "LOCAL_PILOT_PERIOD_INVALID",
        ),
        timezone=_text(config.get("timezone"), "LOCAL_PILOT_TIMEZONE_INVALID"),
        original_file_sha256=receipt.sha256,
        original_size_bytes=receipt.size_bytes,
        expected_row_count=config.get("expected_row_count"),
        control_totals_sha256=_optional_sha(
            config.get("control_totals_sha256"),
            "LOCAL_PILOT_CONTROL_TOTALS_INVALID",
        ),
        data_categories=tuple(config.get("data_categories", ())),
        sensitivity=DatasetSensitivity.COMMERCIAL_CONFIDENTIAL,
        owner_authority_reference=_text(
            config.get("owner_authority_reference"),
            "LOCAL_PILOT_AUTHORITY_INVALID",
        ),
        lawful_authority_attested=config.get("lawful_authority_attested"),
        retention_deadline=_datetime(
            config.get("retention_deadline"),
            "LOCAL_PILOT_RETENTION_INVALID",
        ),
        declared_at=now,
    )
    policy = _build_policy(config.get("inspection_policy"))
    registry = RealDatasetAdmissionRegistry()
    record = registry.declare(tenant=tenant, declaration=declaration)
    record = registry.inspect_and_validate(
        tenant=tenant,
        dataset_id=dataset_id,
        payload=storage.read(tenant=tenant, raw_file_id=receipt.raw_file_id),
        policy=policy,
        observed_at=now + timedelta(seconds=1),
    )
    report = _base_report(
        dataset_id=dataset_id,
        receipt=receipt,
        record=record,
        policy=policy,
    )
    if record.state is not DatasetAdmissionState.VALIDATED:
        report["status"] = "ADMISSION_REJECTED"
        report["limitations"] = ["CALCULATION_NOT_EXECUTED"]
        return report

    attestations = _mapping(
        config.get("attestations"),
        "LOCAL_PILOT_ATTESTATIONS_INVALID",
    )
    if set(attestations) != _REQUIRED_ATTESTATIONS or any(
        attestations[name] is not True for name in _REQUIRED_ATTESTATIONS
    ):
        raise LocalPilotError("LOCAL_PILOT_ATTESTATIONS_INCOMPLETE")
    inspection = record.inspection
    assert inspection is not None
    dataset_evidence = DatasetControlEvidence(
        evidence_id="dataset-evidence-" + str(uuid4()),
        tenant_id=tenant_id,
        dataset_id=dataset_id,
        original_file_sha256=receipt.sha256,
        owner_authority_reference=declaration.owner_authority_reference,
        reporting_period_start=declaration.reporting_period_start,
        reporting_period_end=declaration.reporting_period_end,
        timezone=declaration.timezone,
        control_totals_sha256=declaration.control_totals_sha256,
        policy_content_hash=policy.content_hash,
        workbook_sha256=inspection.workbook_sha256,
        structural_fingerprint_sha256=inspection.structural_fingerprint_sha256,
        matched_schema_id=inspection.matched_schema_id or "",
        matched_schema_version=inspection.matched_schema_version or "",
        matched_schema_authority_reference=(
            inspection.matched_schema_authority_reference or ""
        ),
        source_authority_verified=True,
        report_period_verified=True,
        control_totals_verified=True,
        direct_identifiers_absent_or_approved=True,
        malware_scan_clean=True,
        malware_scan_evidence_sha256=_optional_sha(
            config.get("malware_scan_evidence_sha256"),
            "LOCAL_PILOT_MALWARE_EVIDENCE_INVALID",
        )
        or "",
        verified_at=now + timedelta(seconds=2),
        verifier_account_id=verifier_id,
    )
    storage_evidence = StorageControlEvidence(
        evidence_id="storage-evidence-" + str(uuid4()),
        tenant_id=tenant_id,
        dataset_id=dataset_id,
        original_file_sha256=receipt.sha256,
        storage_key_sha256=sha256(receipt.storage_key.encode("utf-8")).hexdigest(),
        transport_encrypted=False,
        encryption_at_rest=False,
        tenant_scoped_paths=True,
        immutable_original=True,
        separated_quarantine_and_admitted_zones=True,
        least_privilege_credentials=True,
        verified_at=now + timedelta(seconds=2),
        verifier_account_id=verifier_id,
        storage_environment=StorageEnvironment.LOCAL_SINGLE_USER,
        loopback_only=True,
    )
    record = registry.admit(
        tenant=tenant,
        dataset_id=dataset_id,
        dataset_control_evidence=dataset_evidence,
        storage_evidence=storage_evidence,
        admitted_at=now + timedelta(seconds=3),
    )
    report = _base_report(
        dataset_id=dataset_id,
        receipt=receipt,
        record=record,
        policy=policy,
    )
    if record.state is not DatasetAdmissionState.ADMITTED:
        report["status"] = "ADMISSION_BLOCKED"
        report["limitations"] = ["CALCULATION_NOT_EXECUTED"]
        return report

    finance_request = dict(
        _mapping(config.get("finance_request"), "LOCAL_PILOT_FINANCE_REQUEST_INVALID")
    )
    if finance_request.get("organization_id") != tenant_id:
        raise LocalPilotError("LOCAL_PILOT_FINANCE_TENANT_MISMATCH")
    calculation = calculate(finance_request)
    report["calculation"] = calculation
    blocked_metrics = [
        metric_id
        for metric_id in _REQUIRED_FINANCE_METRICS
        if calculation["results"][metric_id]["state"] != "VALID"
    ]
    reconciliation = _reconcile(calculation, config.get("reconciliation"))
    report["reconciliation"] = reconciliation
    if blocked_metrics:
        report["status"] = "CALCULATION_BLOCKED"
    elif reconciliation["state"] == "CONFLICT":
        report["status"] = "RECONCILIATION_CONFLICT"
    elif reconciliation["state"] == "RECONCILED":
        report["status"] = "PILOT_RUN_COMPLETE"
    else:
        report["status"] = "CALCULATED_RECONCILIATION_PENDING"
    report["blocked_metrics"] = blocked_metrics
    report["limitations"] = [
        "PILOT_READY_NOT_ASSERTED",
        "DURABLE_AUTHENTICATION_NOT_INCLUDED",
        "BACKUP_RESTORE_TEST_NOT_INCLUDED",
        "DELETION_REHEARSAL_NOT_INCLUDED",
        "INDEPENDENT_RELEASE_AUDIT_PENDING",
    ]
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the loopback-only Quantum local pilot pipeline"
    )
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--storage-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        report = run_local_pilot(
            file_path=args.file,
            config=_mapping(config, "LOCAL_PILOT_CONFIG_INVALID"),
            storage_root=args.storage_root,
        )
        _atomic_json(args.output, report)
        print(json.dumps({"status": report["status"], "output": str(args.output)}))
        if report["status"] in {"PILOT_RUN_COMPLETE", "CALCULATED_RECONCILIATION_PENDING"}:
            return
        raise SystemExit(2)
    except SystemExit:
        raise
    except Exception as exc:
        code = getattr(exc, "code", "LOCAL_PILOT_UNEXPECTED_ERROR")
        print(json.dumps({"status": "ERROR", "code": code}), file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
