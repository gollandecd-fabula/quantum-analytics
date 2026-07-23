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
from quantum.application._finance_profile_financial_rows import *


def _build_request(
    *,
    group_name: str,
    organization_id: str,
    inputs: Mapping[str, Any],
    group: GroupInput,
    profile: FinanceProfile,
    tax_rate_percent: str | None = None,
    tax_base_metric_id: str | None = None,
) -> dict[str, Any]:
    source_ids = tuple(
        source_id
        for metric in inputs.values()
        if isinstance(metric, Mapping)
        for source_id in metric.get("source_ids", [])
        if isinstance(source_id, str)
    )
    source_ids = tuple(dict.fromkeys(source_ids))
    profile_payload = profile.to_dict()
    profile_hash = sha256(
        json.dumps(
            profile_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    calculation_identity = json.dumps(
        {
            "group": group_name,
            "profile_hash": profile_hash,
            "source_ids": sorted(source_ids),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "calculation_id": (
            "home-local-"
            + sha256(calculation_identity).hexdigest()[:20]
        ),
        "organization_id": organization_id,
        "mode": "ACTUAL",
        "scenario_id": None,
        "calculated_at": datetime.now(UTC).isoformat(),
        "profile_ref": {
            "id": "home-local-finance-profile",
            "version": 2,
            "content_hash": profile_hash,
        },
        "profile_status": "PILOT",
        "rounding_policy": _rounding_policy(),
        "currency": "RUB",
        "inputs": dict(inputs),
        "cost_per_unit": _typed(
            "VALID",
            _money(
                _decimal(
                    group.cost_per_unit,
                    "COST_REQUIRED:" + group_name,
                )
            ),
            "MONEY",
            "MONEY_PER_ITEM",
            "RUB",
            source_ids=source_ids,
        ),
        "other_expense_components": [
            {
                "component_id": "user-confirmed-per-sold-unit",
                "value": _typed(
                    "VALID",
                    _money(
                        _decimal(
                            profile.other_expense_per_unit,
                            "OTHER_EXPENSE_REQUIRED",
                        )
                    ),
                    "MONEY",
                    "MONEY_PER_ITEM",
                    "RUB",
                    source_ids=source_ids,
                ),
            }
        ],
        "tax_rate": _typed(
            "VALID",
            _rate(
                _decimal(
                    (
                        profile.tax_rate_percent
                        if tax_rate_percent is None
                        else tax_rate_percent
                    ),
                    "TAX_RATE_REQUIRED",
                    maximum=Decimal("100"),
                )
                / Decimal("100")
            ),
            "RATE",
            "RATE",
            source_ids=source_ids,
        ),
        "tax_base_metric_id": _required_text(
            (
                profile.tax_base_metric_id
                if tax_base_metric_id is None
                else tax_base_metric_id
            ),
            "TAX_BASE_REQUIRED",
        ),
    }


def _service_group_input() -> GroupInput:
    return GroupInput(
        name=UNALLOCATED_SERVICE_GROUP,
        product_ids=[],
        cost_per_unit="0",
        resalable_returned_units="0",
        compensated_returned_units="0",
        return_compensation_amount="0",
        discounts_amount="0",
        subsidies_amount="0",
        advertising_amount="0",
    )


def _period_tax_calculation(tax_amount: Decimal) -> dict[str, Any]:
    zero = {"state": "VALID", "value": "0.00"}
    return {
        "results": {
            "net_sold_units": {"state": "VALID", "value": "0"},
            "product_cost_amount": dict(zero),
            "other_expense_amount": dict(zero),
            "tax_amount": {
                "state": "VALID",
                "value": _money(tax_amount),
            },
            "net_marketplace_income_amount": dict(zero),
            "net_profit_amount": {
                "state": "VALID",
                "value": _money(-tax_amount),
            },
            "profit_per_sold_unit": {
                "state": "BLOCKED",
                "value": None,
                "reason_code": "PERIOD_TAX_NOT_PRODUCT_UNIT_METRIC",
            },
        },
        "publication_state": "PREVIEW_ONLY",
    }


def calculate_by_group(
    *,
    detailed_rows: Sequence[Mapping[str, Any]],
    profile: FinanceProfile,
    organization_id: str,
    source_id: str,
    source_sha256: str,
) -> FinanceRunResult:
    confirm_profile(profile)
    organization_id = _required_text(
        organization_id,
        "ORGANIZATION_ID_REQUIRED",
    )
    source_id = _required_text(source_id, "SOURCE_ID_REQUIRED")
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise FinanceProfileError("SOURCE_SHA256_INVALID")

    grouped_rows = _group_rows(detailed_rows, profile.product_to_group)
    unknown_count = len(grouped_rows.get(UNASSIGNED_GROUP, ()))
    physical_without_sku = len(
        grouped_rows.get(UNATTRIBUTED_PHYSICAL_GROUP, ())
    )
    attribution_blockers: list[str] = []
    if unknown_count:
        attribution_blockers.append(
            f"UNKNOWN_PRODUCT_FINANCIAL_ROWS:{unknown_count}"
        )
    if physical_without_sku:
        attribution_blockers.append(
            f"UNATTRIBUTED_PHYSICAL_ROWS:{physical_without_sku}"
        )
    if attribution_blockers:
        return FinanceRunResult(
            status="CALCULATION_BLOCKED",
            group_results=(),
            totals={},
            missing_inputs=tuple(attribution_blockers),
        )

    results: list[GroupCalculation] = []
    missing_all: list[str] = []
    total_metric_ids = (
        "net_sold_units",
        "product_cost_amount",
        "other_expense_amount",
        "tax_amount",
        "net_marketplace_income_amount",
        "net_profit_amount",
    )
    totals = {
        metric_id: Decimal("0")
        for metric_id in total_metric_ids
    }
    tax_base_total = Decimal("0")
    work_items: list[
        tuple[str, GroupInput, Sequence[Mapping[str, Any]]]
    ] = [
        (
            group_name,
            profile.groups[group_name],
            grouped_rows.get(group_name, []),
        )
        for group_name in sorted(profile.groups)
    ]
    service_rows = grouped_rows.get(UNALLOCATED_SERVICE_GROUP, [])
    if service_rows:
        work_items.append(
            (
                UNALLOCATED_SERVICE_GROUP,
                _service_group_input(),
                service_rows,
            )
        )

    for group_name, group, rows in work_items:
        if not rows:
            results.append(
                GroupCalculation(
                    group_name,
                    "VALID",
                    ("ZERO_ACTIVITY",),
                    None,
                    {"activity_state": "ZERO_ACTIVITY"},
                )
            )
            continue
        try:
            bridge = normalize_detailed_financial_rows(
                rows,
                source_id=source_id + ":" + group_name,
                source_sha256=source_sha256,
            )
        except WbDetailedFinancialError as exc:
            results.append(
                GroupCalculation(
                    group_name,
                    "BLOCKED",
                    (exc.code,),
                    None,
                    None,
                )
            )
            missing_all.append(group_name + ": " + exc.code)
            continue
        kernel_inputs = {
            key: value
            for key, value in bridge["kernel_inputs"].items()
            if key in _FINANCE_KERNEL_INPUT_NAMES
        }
        inputs, missing = _fill_blocked_kernel_inputs(
            kernel_inputs,
            group,
        )
        if missing:
            results.append(
                GroupCalculation(
                    group_name,
                    "BLOCKED",
                    missing,
                    None,
                    bridge.get("observed_metrics"),
                )
            )
            missing_all.extend(
                group_name + ": " + item for item in missing
            )
            continue
        request = _build_request(
            group_name=group_name,
            organization_id=organization_id,
            inputs=inputs,
            group=group,
            profile=profile,
            tax_rate_percent="0",
            tax_base_metric_id="gross_sales_amount",
        )
        try:
            calculation = calculate(request)
        except FinanceError as exc:
            results.append(
                GroupCalculation(
                    group_name,
                    "BLOCKED",
                    (exc.code,),
                    None,
                    bridge.get("observed_metrics"),
                )
            )
            missing_all.append(group_name + ": " + exc.code)
            continue
        blocked_reasons: list[str] = []
        for metric_id in total_metric_ids:
            metric = calculation["results"][metric_id]
            if metric["state"] == "VALID":
                continue
            reason = str(metric.get("reason_code") or metric_id)
            while reason.startswith("DEPENDENCY_BLOCKED:"):
                reason = reason[len("DEPENDENCY_BLOCKED:") :]
            if reason not in blocked_reasons:
                blocked_reasons.append(reason)
        blocked = tuple(blocked_reasons)
        if blocked:
            results.append(
                GroupCalculation(
                    group_name,
                    "BLOCKED",
                    blocked,
                    calculation,
                    bridge.get("observed_metrics"),
                )
            )
            missing_all.extend(
                group_name + ": " + item for item in blocked
            )
            continue

        if profile.tax_base_metric_id == "gross_sales_amount":
            tax_base_total += _metric_value(inputs["gross_sales_amount"])
        elif profile.tax_base_metric_id == "net_marketplace_income_amount":
            tax_base_total += _metric_value(
                calculation["results"]["net_marketplace_income_amount"]
            )
        else:
            raise FinanceProfileError("TAX_BASE_REQUIRED")

        for metric_id in total_metric_ids:
            totals[metric_id] += _metric_value(
                calculation["results"][metric_id]
            )
        result_reason = (
            "UNALLOCATED_MARKETPLACE_SERVICE_EXPENSES"
            if group_name == UNALLOCATED_SERVICE_GROUP
            else "PRE_TAX_PRODUCT_RESULT"
        )
        results.append(
            GroupCalculation(
                group_name,
                "VALID",
                (result_reason,),
                calculation,
                bridge.get("observed_metrics"),
            )
        )

    if not missing_all:
        if tax_base_total < 0:
            missing_all.append("NEGATIVE_TAX_BASE_POLICY_REQUIRED")
        else:
            rate = (
                _decimal(
                    profile.tax_rate_percent,
                    "TAX_RATE_REQUIRED",
                    maximum=Decimal("100"),
                )
                / Decimal("100")
            )
            period_tax = Decimal(_money(tax_base_total * rate))
            totals["tax_amount"] = period_tax
            totals["net_profit_amount"] -= period_tax
            results.append(
                GroupCalculation(
                    PERIOD_TAX_GROUP,
                    "VALID",
                    ("PERIOD_TAX_NOT_ALLOCATED_TO_PRODUCT_GROUPS",),
                    _period_tax_calculation(period_tax),
                    {
                        "tax_base_metric_id": (
                            profile.tax_base_metric_id
                        ),
                        "tax_base_amount": _money(tax_base_total),
                    },
                )
            )

    status = (
        "CALCULATED"
        if (
            results
            and not missing_all
            and all(item.state == "VALID" for item in results)
        )
        else "CALCULATION_BLOCKED"
    )
    formatted_totals = {
        metric_id: _money(value)
        for metric_id, value in totals.items()
    }
    sold_units = totals["net_sold_units"]
    formatted_totals["profit_per_sold_unit"] = (
        _money(totals["net_profit_amount"] / sold_units)
        if sold_units > 0
        else "0.00"
    )
    return FinanceRunResult(
        status=status,
        group_results=tuple(results),
        totals=formatted_totals,
        missing_inputs=tuple(sorted(set(missing_all))),
    )


def save_run_result(path: Path, result: FinanceRunResult) -> None:
    _atomic_json(path, result.to_dict())


__all__ = [name for name in globals() if not name.startswith("__")]
