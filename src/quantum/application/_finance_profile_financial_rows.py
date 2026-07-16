from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile

from quantum.adapters.wildberries.detailed_financial import (
    WbDetailedFinancialError,
    _ALIASES as _WB_DETAILED_ALIASES,
    normalize_detailed_financial_rows,
)
from quantum.adapters.wildberries.source_bridge import _sheet_rows
from quantum.finance import FinanceError, calculate, canonical_hash
from quantum.ingestion import XlsxInspectionLimits
from quantum.ingestion._xlsx_archive import _extract_workbook

from quantum.application._finance_profile_model import *
from quantum.application._finance_profile_groups import *

_FINANCE_KERNEL_INPUT_NAMES = frozenset({
    "gross_sales_units",
    "returned_units",
    "resalable_returned_units",
    "compensated_returned_units",
    "return_compensation_amount",
    "gross_sales_amount",
    "discounts_amount",
    "subsidies_excluding_return_compensation_amount",
    "marketplace_commission_amount",
    "forward_logistics_amount",
    "reverse_logistics_amount",
    "storage_amount",
    "advertising_amount",
    "fines_withholdings_amount",
})


def _typed(
    state: str,
    value: str | int | None,
    value_type: str,
    unit: str,
    currency: str | None = None,
    reason_code: str | None = None,
    source_ids: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "state": state,
        "value": None if value is None else str(value),
        "value_type": value_type,
        "unit": unit,
        "currency": currency,
        "reason_code": reason_code,
        "source_ids": list(source_ids),
    }


def _valid_money(value: object, source_ids: Sequence[str]) -> dict[str, Any]:
    return _typed(
        "VALID",
        _money(_decimal(value, "FINANCE_VALUE_INVALID")),
        "MONEY",
        "MONEY",
        "RUB",
        source_ids=source_ids,
    )


def _valid_integer(value: object, source_ids: Sequence[str]) -> dict[str, Any]:
    parsed = _decimal(value, "FINANCE_VALUE_INVALID", integer=True)
    return _typed(
        "VALID",
        str(int(parsed)),
        "INTEGER",
        "ITEM",
        source_ids=source_ids,
    )


def _rounding_policy() -> dict[str, Any]:
    policy: dict[str, Any] = {
        "policy_id": "home-local-finance-center",
        "version": 1,
        "content_hash": "",
        "status": "PILOT",
        "calculation_mode": "HALF_EVEN",
        "calculation_scale": 6,
        "money_scale": 2,
        "rate_scale": 6,
        "presentation_mode": "HALF_EVEN",
        "presentation_scale": 2,
        "currency_presentation_scales": {"RUB": 2},
        "application_points": [
            "RULE_INPUT_NORMALIZATION",
            "RULE_COMPONENT_RESULT",
            "METRIC_FINAL_ACCOUNTING",
        ],
        "max_input_precision": 28,
        "max_input_scale": 8,
        "actor": "home-local-user",
        "created_at": "2026-07-13T00:00:00Z",
        "source": "finance-center",
        "change_reason": "user-confirmed financial profile",
        "approval_reference": "local-user-confirmation",
        "supersedes": None,
    }
    policy["content_hash"] = canonical_hash(
        policy,
        exclude=frozenset({"content_hash"}),
    )
    return policy


def _metric_value(metric: Mapping[str, Any]) -> Decimal:
    if metric.get("state") != "VALID" or metric.get("value") is None:
        raise FinanceProfileError("METRIC_BLOCKED")
    return _decimal(metric.get("value"), "METRIC_INVALID", minimum=Decimal("-1E100"))


def _group_rows(
    raw_rows: Sequence[Mapping[str, Any]],
    product_to_group: Mapping[str, str],
) -> dict[str, list[Mapping[str, Any]]]:
    result: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in raw_rows:
        vendor_code = ""
        for key in ("vendorCode", "sa_name", "Артикул", "Артикул продавца"):
            if key in row and str(row[key]).strip():
                vendor_code = str(row[key]).strip()
                break
        group_name = product_to_group.get(vendor_code, UNASSIGNED_GROUP)
        result[group_name].append(row)
    return dict(result)


def _source_context_from_report(report: Mapping[str, Any] | None) -> dict[str, str]:
    if not isinstance(report, Mapping):
        return {}
    bridge = report.get("source_bridge")
    if not isinstance(bridge, Mapping):
        bridge = report
    report_ids = bridge.get("report_ids")
    periods = bridge.get("report_periods")
    if not isinstance(report_ids, list) or len(report_ids) != 1:
        return {}
    report_id = str(report_ids[0]).strip()
    if not report_id or not isinstance(periods, Mapping):
        return {}
    period = periods.get(report_id)
    if not isinstance(period, Mapping):
        return {}
    date_from = _optional_text(period.get("date_from"))
    date_to = _optional_text(period.get("date_to"))
    if date_from is None or date_to is None:
        return {}
    return {
        "report_id": report_id,
        "date_from": date_from,
        "date_to": date_to,
        "currency": "RUB",
    }


def read_detailed_financial_rows(
    path: Path,
    report: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows = read_first_sheet(path)
    header_index, headers, _positions = _find_header(
        rows,
        ("operation", "quantity", "retail_amount", "for_pay"),
        max_scan_rows=80,
    )
    context = _source_context_from_report(report)
    prepared: list[dict[str, Any]] = []
    for row_index, values in rows:
        if row_index <= header_index or not any(value.strip() for value in values):
            continue
        padded = values + ("",) * (len(headers) - len(values))
        if len(padded) != len(headers):
            raise FinanceProfileError("DETAILED_ROW_COLUMN_OVERFLOW")
        raw = dict(zip(headers, padded, strict=True))

        def fill_aliases(field_name: str, fallback: str) -> None:
            aliases = _WB_DETAILED_ALIASES[field_name]
            present = [alias for alias in aliases if alias in raw]
            nonblank = [str(raw[alias]).strip() for alias in present if str(raw[alias]).strip()]
            canonical = nonblank[0] if nonblank else fallback
            if any(value != canonical for value in nonblank[1:]):
                raise FinanceProfileError("DETAILED_ALIAS_CONFLICT:" + field_name)
            if present:
                for alias in present:
                    if not str(raw[alias]).strip():
                        raw[alias] = canonical
            else:
                raw[aliases[0]] = canonical

        fill_aliases("row_id", str(row_index))
        if context:
            fill_aliases("report_id", context["report_id"])
            fill_aliases("date_from", context["date_from"])
            fill_aliases("date_to", context["date_to"])
            fill_aliases("currency", context["currency"])
        prepared.append(raw)
    if not prepared:
        raise FinanceProfileError("DETAILED_ROWS_NOT_FOUND")
    return prepared


def _fill_blocked_kernel_inputs(
    kernel_inputs: Mapping[str, Any],
    group: GroupInput,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    inputs = {key: dict(value) for key, value in kernel_inputs.items()}
    evidence = tuple(
        source_id
        for metric in inputs.values()
        if isinstance(metric, Mapping)
        for source_id in metric.get("source_ids", [])
        if isinstance(source_id, str)
    )
    evidence = tuple(dict.fromkeys(evidence))
    user_fields = {
        "resalable_returned_units": (group.resalable_returned_units, "INTEGER"),
        "compensated_returned_units": (group.compensated_returned_units, "INTEGER"),
        "return_compensation_amount": (group.return_compensation_amount, "MONEY"),
        "discounts_amount": (group.discounts_amount, "MONEY"),
        "subsidies_excluding_return_compensation_amount": (
            group.subsidies_amount,
            "MONEY",
        ),
        "advertising_amount": (group.advertising_amount, "MONEY"),
    }
    missing: list[str] = []
    for metric_id, (raw_value, value_type) in user_fields.items():
        existing = inputs.get(metric_id)
        if isinstance(existing, Mapping) and existing.get("state") == "VALID":
            continue
        if _optional_text(raw_value) is None:
            reason = existing.get("reason_code") if isinstance(existing, Mapping) else None
            missing.append(str(reason or metric_id))
            continue
        if value_type == "INTEGER":
            inputs[metric_id] = _valid_integer(raw_value, evidence)
        else:
            inputs[metric_id] = _valid_money(raw_value, evidence)
    return inputs, tuple(sorted(set(missing)))

__all__ = [name for name in globals() if not name.startswith("__")]
