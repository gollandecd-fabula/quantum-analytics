from __future__ import annotations

from contextvars import ContextVar
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping, Protocol


_REQUIRED_FINANCE_METRICS = (
    "net_sold_units",
    "product_cost_amount",
    "other_expense_amount",
    "tax_amount",
    "net_marketplace_income_amount",
    "net_profit_amount",
    "profit_per_sold_unit",
)
_CONTROL_TOTALS_SHA256: ContextVar[str | None] = ContextVar(
    "m4_control_totals_sha256",
    default=None,
)


class _RunnerModule(Protocol):
    LocalPilotError: type[ValueError]
    run_local_pilot: Any
    _mapping: Any
    _reconcile: Any


def expected_metrics_sha256(expected: Mapping[str, str]) -> str:
    encoded = json.dumps(
        dict(expected),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def reconcile(
    engine: _RunnerModule,
    result: Mapping[str, Any],
    raw: object,
    declared_control_totals_sha256: str | None = None,
) -> dict[str, Any]:
    if declared_control_totals_sha256 is None:
        declared_control_totals_sha256 = _CONTROL_TOTALS_SHA256.get()
    if raw is None:
        return {
            "state": "PENDING",
            "differences": [],
            "reason_code": "RECONCILIATION_NOT_CONFIGURED",
            "control_totals_bound": False,
            "control_totals_sha256": declared_control_totals_sha256,
        }
    data = engine._mapping(raw, "LOCAL_PILOT_RECONCILIATION_INVALID")
    if set(data) != {"expected_metrics"}:
        raise engine.LocalPilotError("LOCAL_PILOT_RECONCILIATION_INVALID")
    expected_raw = engine._mapping(
        data.get("expected_metrics"),
        "LOCAL_PILOT_EXPECTED_METRICS_INVALID",
    )
    if any(
        not isinstance(metric_id, str)
        or not metric_id
        or not isinstance(expected_value, str)
        or not expected_value
        for metric_id, expected_value in expected_raw.items()
    ):
        raise engine.LocalPilotError("LOCAL_PILOT_EXPECTED_METRICS_INVALID")

    expected = dict(expected_raw)
    required = set(_REQUIRED_FINANCE_METRICS)
    provided = set(expected)
    results = engine._mapping(
        result.get("results"),
        "LOCAL_PILOT_RESULTS_INVALID",
    )

    if provided != required:
        differences: list[dict[str, str | None]] = []
        for metric_id in sorted(required - provided):
            metric = results.get(metric_id)
            actual = metric.get("value") if isinstance(metric, Mapping) else None
            differences.append(
                {
                    "metric_id": metric_id,
                    "expected": None,
                    "actual": actual,
                    "reason_code": "EXPECTED_METRIC_MISSING",
                }
            )
        for metric_id in sorted(provided - required):
            differences.append(
                {
                    "metric_id": metric_id,
                    "expected": expected[metric_id],
                    "actual": None,
                    "reason_code": "EXPECTED_METRIC_UNSUPPORTED",
                }
            )
        return {
            "state": "CONFLICT",
            "differences": differences,
            "reason_code": "RECONCILIATION_METRIC_SET_MISMATCH",
            "control_totals_bound": False,
            "control_totals_sha256": declared_control_totals_sha256,
        }

    computed_control_totals_sha256 = expected_metrics_sha256(expected)
    if declared_control_totals_sha256 is None:
        return {
            "state": "PENDING",
            "differences": [],
            "reason_code": "CONTROL_TOTALS_HASH_REQUIRED",
            "control_totals_bound": False,
            "control_totals_sha256": computed_control_totals_sha256,
        }
    if declared_control_totals_sha256 != computed_control_totals_sha256:
        return {
            "state": "CONFLICT",
            "differences": [
                {
                    "metric_id": "control_totals_sha256",
                    "expected": declared_control_totals_sha256,
                    "actual": computed_control_totals_sha256,
                    "reason_code": "CONTROL_TOTALS_HASH_MISMATCH",
                }
            ],
            "reason_code": "CONTROL_TOTALS_HASH_MISMATCH",
            "control_totals_bound": False,
            "control_totals_sha256": computed_control_totals_sha256,
        }

    differences = []
    for metric_id in _REQUIRED_FINANCE_METRICS:
        metric = results.get(metric_id)
        actual = metric.get("value") if isinstance(metric, Mapping) else None
        state = metric.get("state") if isinstance(metric, Mapping) else None
        if state != "VALID" or actual != expected[metric_id]:
            differences.append(
                {
                    "metric_id": metric_id,
                    "expected": expected[metric_id],
                    "actual": actual,
                    "reason_code": (
                        "METRIC_NOT_VALID"
                        if state != "VALID"
                        else "METRIC_VALUE_MISMATCH"
                    ),
                }
            )
    return {
        "state": "CONFLICT" if differences else "RECONCILED",
        "differences": differences,
        "reason_code": "METRIC_VALUE_MISMATCH" if differences else None,
        "control_totals_bound": True,
        "control_totals_sha256": computed_control_totals_sha256,
    }


def install(engine: _RunnerModule) -> tuple[type[ValueError], Any]:
    if getattr(engine, "_m4_reconciliation_guard_installed", False):
        return engine.LocalPilotError, engine.run_local_pilot

    original_run = engine.run_local_pilot

    def guarded_run_local_pilot(
        *,
        file_path: Path,
        config: Mapping[str, Any],
        storage_root: Path,
    ) -> dict[str, Any]:
        token = _CONTROL_TOTALS_SHA256.set(config.get("control_totals_sha256"))
        try:
            return original_run(
                file_path=file_path,
                config=config,
                storage_root=storage_root,
            )
        finally:
            _CONTROL_TOTALS_SHA256.reset(token)

    def guarded_reconcile(
        result: Mapping[str, Any],
        raw: object,
        declared_control_totals_sha256: str | None = None,
    ) -> dict[str, Any]:
        return reconcile(
            engine,
            result,
            raw,
            declared_control_totals_sha256,
        )

    engine._reconcile = guarded_reconcile
    engine.run_local_pilot = guarded_run_local_pilot
    engine._m4_reconciliation_guard_installed = True
    return engine.LocalPilotError, guarded_run_local_pilot
