from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from . import local_runner_legacy_m4 as _legacy


LocalPilotError = _legacy.LocalPilotError
_REQUIRED_FINANCE_METRICS = _legacy._REQUIRED_FINANCE_METRICS


def _expected_metrics_sha256(expected: Mapping[str, str]) -> str:
    encoded = json.dumps(
        dict(expected),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _reconcile(
    result: Mapping[str, Any],
    raw: object,
    declared_control_totals_sha256: str | None = None,
) -> dict[str, Any]:
    if raw is None:
        return {
            "state": "PENDING",
            "differences": [],
            "reason_code": "RECONCILIATION_NOT_CONFIGURED",
            "control_totals_bound": False,
            "control_totals_sha256": declared_control_totals_sha256,
        }
    data = _legacy._mapping(
        raw,
        "LOCAL_PILOT_RECONCILIATION_INVALID",
    )
    if set(data) != {"expected_metrics"}:
        raise LocalPilotError("LOCAL_PILOT_RECONCILIATION_INVALID")
    expected_raw = _legacy._mapping(
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
        raise LocalPilotError("LOCAL_PILOT_EXPECTED_METRICS_INVALID")

    expected = dict(expected_raw)
    required = set(_REQUIRED_FINANCE_METRICS)
    provided = set(expected)
    results = _legacy._mapping(
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

    computed_control_totals_sha256 = _expected_metrics_sha256(expected)
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


# The existing runner remains byte-for-byte preserved. Only its reconciliation
# boundary is replaced before any public entry point is exposed.
_legacy._reconcile = _reconcile
run_local_pilot = _legacy.run_local_pilot


def main() -> None:
    _legacy.main()


__all__ = [
    "LocalPilotError",
    "_expected_metrics_sha256",
    "_reconcile",
    "main",
    "run_local_pilot",
]


if __name__ == "__main__":
    main()
