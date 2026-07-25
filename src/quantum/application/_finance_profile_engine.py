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


def _blocked_profile_value(
    *,
    reason_code: str,
    value_type: str,
    unit: str,
    currency: str | None,
    source_ids: Sequence[str],
) -> dict[str, Any]:
    return _typed(
        "BLOCKED",
        None,
        value_type,
        unit,
        currency,
        reason_code=reason_code,
        source_ids=source_ids,
    )


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

    cost_text = _optional_text(group.cost_per_unit)
    cost_value = (
        _typed(
            "VALID",
            _money(_decimal(cost_text, "COST_REQUIRED:" + group_name)),
            "MONEY",
            "MONEY_PER_ITEM",
            "RUB",
            source_ids=source_ids,
        )
        if cost_text is not None
        else _blocked_profile_value(
            reason_code="COST_REQUIRED:" + group_name,
            value_type="MONEY",
            unit="MONEY_PER_ITEM",
            currency="RUB",
            source_ids=source_ids,
        )
    )
    other_text = _optional_text(profile.other_expense_per_unit)
    other_value = (
        _typed(
            "VALID",
            _money(_decimal(other_text, "OTHER_EXPENSE_REQUIRED")),
            "MONEY",
            "MONEY_PER_ITEM",
            "RUB",
            source_ids=source_ids,
        )
        if other_text is not None
        else _blocked_profile_value(
            reason_code="OTHER_EXPENSE_REQUIRED",
            value_type="MONEY",
            unit="MONEY_PER_ITEM",
            currency="RUB",
            source_ids=source_ids,
        )
    )
    resolved_rate = (
        profile.tax_rate_percent
        if tax_rate_percent is None
        else tax_rate_percent
    )
    resolved_base = (
        profile.tax_base_metric_id
        if tax_base_metric_id is None
        else tax_base_metric_id
    )
    rate_text = _optional_text(resolved_rate)
    base_text = _optional_text(resolved_base)
    if rate_text is None or base_text is None:
        tax_reason = "TAX_RATE_REQUIRED" if rate_text is None else "TAX_BASE_REQUIRED"
        tax_value = _blocked_profile_value(
            reason_code=tax_reason,
            value_type="RATE",
            unit="RATE",
            currency=None,
            source_ids=source_ids,
        )
    else:
        tax_value = _typed(
            "VALID",
            _rate(
                _decimal(
                    rate_text,
                    "TAX_RATE_REQUIRED",
                    maximum=Decimal("100"),
                )
                / Decimal("100")
            ),
            "RATE",
            "RATE",
            source_ids=source_ids,
        )
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
        "cost_per_unit": cost_value,
        "other_expense_components": [
            {
                "component_id": "user-confirmed-per-sold-unit",
                "value": other_value,
            }
        ],
        "tax_rate": tax_value,
        # The kernel requires an identifier. When the user has not selected a
        # tax base, gross_sales_amount is used only as an inert structural
        # placeholder while tax_rate is BLOCKED with TAX_BASE_REQUIRED.
        "tax_base_metric_id": base_text or "gross_sales_amount",
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


_ADDITIVE_METRICS = (
    "net_sold_units",
    "product_cost_amount",
    "other_expense_amount",
    "net_marketplace_income_amount",
)


def _primary_reason(metric: Mapping[str, Any], metric_id: str) -> str:
    reason = str(metric.get("reason_code") or metric_id)
    for prefix in (
        "DEPENDENCY_BLOCKED:",
        "DEPENDENCY_UNAVAILABLE:",
        "DEPENDENCY_EMPTY:",
        "DEPENDENCY_CONFLICT:",
    ):
        while reason.startswith(prefix):
            reason = reason[len(prefix) :]
    return reason


def _metric_state_record(
    *,
    state: str,
    value: str | None,
    included: Sequence[str],
    excluded: Sequence[str],
    reasons: Sequence[str],
) -> dict[str, Any]:
    return {
        "state": state,
        "value": value,
        "included_scopes": list(included),
        "excluded_scopes": list(excluded),
        "reason_codes": list(dict.fromkeys(reasons)),
    }


def _calculate_group_from_inputs(
    *,
    display_name: str,
    inputs: Mapping[str, Any],
    observed_metrics: Mapping[str, Any] | None,
    group: GroupInput,
    profile: FinanceProfile,
    organization_id: str,
    initial_reasons: Sequence[str] = (),
) -> GroupCalculation:
    if not inputs and initial_reasons:
        return GroupCalculation(
            display_name,
            "BLOCKED",
            tuple(sorted(set(initial_reasons))),
            None,
            dict(observed_metrics) if isinstance(observed_metrics, Mapping) else None,
        )
    filled, missing = _fill_blocked_kernel_inputs(inputs, group)
    request = _build_request(
        group_name=display_name,
        organization_id=organization_id,
        inputs=filled,
        group=group,
        profile=profile,
        # Product/group calculations are intentionally pre-tax. Period tax is
        # calculated once across the covered tax base below.
        tax_rate_percent="0",
        tax_base_metric_id="gross_sales_amount",
    )
    try:
        calculation = calculate(request)
    except FinanceError as exc:
        return GroupCalculation(
            display_name,
            "BLOCKED",
            tuple(sorted(set((*initial_reasons, *missing, exc.code)))),
            None,
            dict(observed_metrics) if isinstance(observed_metrics, Mapping) else None,
        )
    results = calculation.get("results")
    if not isinstance(results, Mapping):
        return GroupCalculation(
            display_name,
            "BLOCKED",
            tuple(sorted(set((*initial_reasons, *missing, "KERNEL_RESULTS_INVALID")))),
            calculation,
            dict(observed_metrics) if isinstance(observed_metrics, Mapping) else None,
        )
    valid_count = 0
    blocked: list[str] = [*initial_reasons, *missing]
    required_result_ids = {
        "net_sold_units",
        "product_cost_amount",
        "other_expense_amount",
        "tax_amount",
        "net_marketplace_income_amount",
        "net_profit_amount",
        "profit_per_sold_unit",
    }
    for metric_id, metric in results.items():
        if metric_id not in required_result_ids:
            continue
        if not isinstance(metric, Mapping):
            blocked.append("METRIC_INVALID:" + str(metric_id))
            continue
        if metric.get("state") == "VALID":
            valid_count += 1
        else:
            reason = _primary_reason(metric, str(metric_id))
            sold_metric = results.get("net_sold_units")
            sold_value = (
                sold_metric.get("value")
                if isinstance(sold_metric, Mapping)
                else None
            )
            if (
                metric_id == "profit_per_sold_unit"
                and reason == "ZERO_DENOMINATOR"
                and sold_value in {"0", "0.00", 0}
            ):
                # Per-unit profit is not applicable to a service-only or
                # zero-unit scope. It must not downgrade otherwise complete
                # period calculations. The aggregate per-unit metric is still
                # computed from all covered sold units.
                continue
            blocked.append(reason)
    state = "VALID" if not blocked else ("PARTIAL" if valid_count else "BLOCKED")
    return GroupCalculation(
        display_name,
        state,
        tuple(sorted(set(blocked))) or ("PRE_TAX_PRODUCT_RESULT",),
        calculation,
        dict(observed_metrics) if isinstance(observed_metrics, Mapping) else None,
    )


def _aggregate_group_metrics(
    group_results: Sequence[GroupCalculation],
    profile: FinanceProfile,
) -> tuple[dict[str, str], dict[str, dict[str, Any]], GroupCalculation | None, list[str]]:
    totals: dict[str, str] = {}
    states: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    additive_values: dict[str, Decimal] = {
        metric_id: Decimal("0") for metric_id in _ADDITIVE_METRICS
    }
    included: dict[str, list[str]] = {metric_id: [] for metric_id in _ADDITIVE_METRICS}
    excluded: dict[str, list[str]] = {metric_id: [] for metric_id in _ADDITIVE_METRICS}
    reasons: dict[str, list[str]] = {metric_id: [] for metric_id in _ADDITIVE_METRICS}
    pre_tax = Decimal("0")
    pre_tax_included: list[str] = []
    pre_tax_excluded: list[str] = []
    pre_tax_reasons: list[str] = []
    tax_base = Decimal("0")
    tax_base_included: list[str] = []
    tax_base_excluded: list[str] = []
    tax_base_reasons: list[str] = []

    for group in group_results:
        if "ZERO_ACTIVITY" in group.reason_codes:
            continue
        calculation = group.calculation
        metrics = calculation.get("results") if isinstance(calculation, Mapping) else None
        if not isinstance(metrics, Mapping):
            for metric_id in _ADDITIVE_METRICS:
                excluded[metric_id].append(group.group_name)
                reasons[metric_id].extend(group.reason_codes)
            pre_tax_excluded.append(group.group_name)
            pre_tax_reasons.extend(group.reason_codes)
            tax_base_excluded.append(group.group_name)
            tax_base_reasons.extend(group.reason_codes)
            continue
        for metric_id in _ADDITIVE_METRICS:
            metric = metrics.get(metric_id)
            if isinstance(metric, Mapping) and metric.get("state") == "VALID" and metric.get("value") is not None:
                additive_values[metric_id] += _decimal(
                    metric.get("value"), "METRIC_INVALID", minimum=Decimal("-1E100")
                )
                included[metric_id].append(group.group_name)
            else:
                excluded[metric_id].append(group.group_name)
                if isinstance(metric, Mapping):
                    reasons[metric_id].append(_primary_reason(metric, metric_id))
                else:
                    reasons[metric_id].append("METRIC_MISSING:" + metric_id)
        profit_metric = metrics.get("net_profit_amount")
        if isinstance(profit_metric, Mapping) and profit_metric.get("state") == "VALID" and profit_metric.get("value") is not None:
            pre_tax += _decimal(
                profit_metric.get("value"), "METRIC_INVALID", minimum=Decimal("-1E100")
            )
            pre_tax_included.append(group.group_name)
        else:
            pre_tax_excluded.append(group.group_name)
            if isinstance(profit_metric, Mapping):
                pre_tax_reasons.append(_primary_reason(profit_metric, "pre_tax_profit_amount"))
            else:
                pre_tax_reasons.append("METRIC_MISSING:pre_tax_profit_amount")
        base_id = profile.tax_base_metric_id
        observed = group.observed_metrics if isinstance(group.observed_metrics, Mapping) else {}
        base_metric = (
            observed.get("gross_sales_amount")
            if base_id == "gross_sales_amount"
            else metrics.get("net_marketplace_income_amount")
        )
        if base_id in {"gross_sales_amount", "net_marketplace_income_amount"} and isinstance(base_metric, Mapping) and base_metric.get("state") == "VALID" and base_metric.get("value") is not None:
            tax_base += _decimal(
                base_metric.get("value"), "METRIC_INVALID", minimum=Decimal("-1E100")
            )
            tax_base_included.append(group.group_name)
        else:
            tax_base_excluded.append(group.group_name)
            if base_id is None:
                tax_base_reasons.append("TAX_BASE_REQUIRED")
            elif isinstance(base_metric, Mapping):
                tax_base_reasons.append(_primary_reason(base_metric, str(base_id)))
            else:
                tax_base_reasons.append("TAX_BASE_REQUIRED")

    for metric_id in _ADDITIVE_METRICS:
        if included[metric_id]:
            if metric_id == "net_sold_units":
                count_value = additive_values[metric_id]
                value = (
                    str(int(count_value))
                    if count_value == count_value.to_integral_value()
                    else format(count_value.normalize(), "f")
                )
            else:
                value = _money(additive_values[metric_id])
            totals[metric_id] = value
            state = "VALID" if not excluded[metric_id] else "PARTIAL"
        else:
            value = None
            state = "BLOCKED"
        states[metric_id] = _metric_state_record(
            state=state,
            value=value,
            included=included[metric_id],
            excluded=excluded[metric_id],
            reasons=reasons[metric_id],
        )

    if pre_tax_included:
        pre_tax_value = _money(pre_tax)
        totals["pre_tax_profit_amount"] = pre_tax_value
        pre_tax_state = "VALID" if not pre_tax_excluded else "PARTIAL"
    else:
        pre_tax_value = None
        pre_tax_state = "BLOCKED"
    states["pre_tax_profit_amount"] = _metric_state_record(
        state=pre_tax_state,
        value=pre_tax_value,
        included=pre_tax_included,
        excluded=pre_tax_excluded,
        reasons=pre_tax_reasons,
    )

    period_tax_group: GroupCalculation | None = None
    rate_text = _optional_text(profile.tax_rate_percent)
    base_id = _optional_text(profile.tax_base_metric_id)
    tax_reasons = list(tax_base_reasons)
    direct_tax_missing: list[str] = []
    if rate_text is None:
        tax_reasons.append("TAX_RATE_REQUIRED")
        direct_tax_missing.append("Налог периода: TAX_RATE_REQUIRED")
    if base_id is None:
        tax_reasons.append("TAX_BASE_REQUIRED")
        direct_tax_missing.append("Налог периода: TAX_BASE_REQUIRED")
    elif not tax_base_included:
        direct_tax_missing.append(
            "Налог периода: TAX_BASE_DATA_REQUIRED:" + base_id
        )
    if not tax_base_included or rate_text is None or base_id is None:
        tax_state = "BLOCKED"
        tax_value = None
    elif tax_base < 0:
        tax_state = "BLOCKED"
        tax_value = None
        tax_reasons.append("NEGATIVE_TAX_BASE_POLICY_REQUIRED")
        direct_tax_missing.append(
            "Налог периода: NEGATIVE_TAX_BASE_POLICY_REQUIRED"
        )
    else:
        rate = _decimal(rate_text, "TAX_RATE_REQUIRED", maximum=Decimal("100")) / Decimal("100")
        tax_amount = Decimal(_money(tax_base * rate))
        tax_value = _money(tax_amount)
        totals["tax_amount"] = tax_value
        tax_state = "VALID" if not tax_base_excluded else "PARTIAL"
        period_tax_group = GroupCalculation(
            PERIOD_TAX_GROUP,
            tax_state,
            tuple(sorted(set(
                ["PERIOD_TAX_NOT_ALLOCATED_TO_PRODUCT_GROUPS"]
                + (["PARTIAL_TAX_BASE_COVERAGE"] if tax_base_excluded else [])
            ))),
            _period_tax_calculation(tax_amount),
            {
                "tax_base_metric_id": base_id,
                "tax_base_amount": _money(tax_base),
                "included_scopes": list(tax_base_included),
                "excluded_scopes": list(tax_base_excluded),
            },
        )
    states["tax_amount"] = _metric_state_record(
        state=tax_state,
        value=tax_value,
        included=tax_base_included,
        excluded=tax_base_excluded,
        reasons=tax_reasons,
    )
    if tax_state != "VALID":
        missing.extend(direct_tax_missing)

    pre_tax_scope = set(pre_tax_included)
    tax_scope = set(tax_base_included)
    compatible_profit_coverage = pre_tax_scope == tax_scope
    if (
        pre_tax_value is not None
        and tax_value is not None
        and compatible_profit_coverage
    ):
        net_profit = pre_tax - Decimal(tax_value)
        net_profit_value = _money(net_profit)
        totals["net_profit_amount"] = net_profit_value
        net_profit_state = (
            "VALID"
            if pre_tax_state == "VALID" and tax_state == "VALID"
            else "PARTIAL"
        )
        net_profit_reasons = [*pre_tax_reasons, *tax_reasons]
    else:
        net_profit_value = None
        net_profit_state = "BLOCKED"
        net_profit_reasons = [*pre_tax_reasons, *tax_reasons]
        if pre_tax_value is not None and tax_value is not None:
            net_profit_reasons.append(
                "COVERAGE_MISMATCH_PRE_TAX_VS_TAX"
            )
    states["net_profit_amount"] = _metric_state_record(
        state=net_profit_state,
        value=net_profit_value,
        included=sorted(set(pre_tax_included) & set(tax_base_included)),
        excluded=sorted(set(pre_tax_excluded) | set(tax_base_excluded)),
        reasons=net_profit_reasons,
    )

    units_state = states["net_sold_units"]
    profit_scope = set(states["net_profit_amount"]["included_scopes"])
    units_scope = set(units_state["included_scopes"])
    compatible_unit_coverage = profit_scope == units_scope
    if (
        net_profit_value is not None
        and units_state["value"] is not None
        and Decimal(str(units_state["value"])) > 0
        and compatible_unit_coverage
    ):
        ppu_value = _money(
            Decimal(net_profit_value) / Decimal(str(units_state["value"]))
        )
        totals["profit_per_sold_unit"] = ppu_value
        ppu_state = (
            "VALID"
            if net_profit_state == "VALID" and units_state["state"] == "VALID"
            else "PARTIAL"
        )
        ppu_reasons = [*net_profit_reasons, *units_state["reason_codes"]]
    else:
        ppu_value = None
        ppu_state = "BLOCKED"
        ppu_reasons = [*net_profit_reasons, *units_state["reason_codes"]]
        if units_state["value"] in {None, "0", "0.00"}:
            ppu_reasons.append("SOLD_UNITS_REQUIRED_FOR_PER_UNIT")
        elif net_profit_value is not None and not compatible_unit_coverage:
            ppu_reasons.append(
                "COVERAGE_MISMATCH_PROFIT_VS_UNITS"
            )
    states["profit_per_sold_unit"] = _metric_state_record(
        state=ppu_state,
        value=ppu_value,
        included=states["net_profit_amount"]["included_scopes"],
        excluded=states["net_profit_amount"]["excluded_scopes"],
        reasons=ppu_reasons,
    )
    return totals, states, period_tax_group, missing


def calculate_metric_groups(
    *,
    evidence_groups: Sequence[Any],
    profile: FinanceProfile,
    organization_id: str,
) -> FinanceRunResult:
    organization_id = _required_text(organization_id, "ORGANIZATION_ID_REQUIRED")
    results: list[GroupCalculation] = []
    unresolved: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for evidence in evidence_groups:
        profile_group_name = getattr(evidence, "profile_group_name", None)
        display_name = str(getattr(evidence, "display_name"))
        group = (
            profile.groups[profile_group_name]
            if profile_group_name in profile.groups
            else (
                _service_group_input()
                if profile_group_name is None and display_name.startswith(UNALLOCATED_SERVICE_GROUP)
                else GroupInput(name=display_name)
            )
        )
        calculation = _calculate_group_from_inputs(
            display_name=display_name,
            inputs=getattr(evidence, "kernel_inputs"),
            observed_metrics=getattr(evidence, "observed_metrics", None),
            group=group,
            profile=profile,
            organization_id=organization_id,
            initial_reasons=getattr(evidence, "reason_codes", ()),
        )
        results.append(calculation)
        seen_sources.add(str(getattr(evidence, "source_sha256", "")))
        if calculation.state != "VALID":
            unresolved.append(
                {
                    "scope": display_name,
                    "state": calculation.state,
                    "reason_codes": list(calculation.reason_codes),
                    "source_name": str(getattr(evidence, "source_name", "")),
                    "member_path": str(getattr(evidence, "member_path", "")),
                }
            )
    totals, metric_states, period_tax, missing = _aggregate_group_metrics(results, profile)
    if period_tax is not None:
        results.append(period_tax)
    valid_metrics = sum(
        state.get("state") in {"VALID", "PARTIAL"} and state.get("value") is not None
        for state in metric_states.values()
    )
    fully_valid = bool(metric_states) and all(
        state.get("state") == "VALID" for state in metric_states.values()
    ) and not unresolved
    status = "CALCULATED" if fully_valid else ("CALCULATED_PARTIAL" if valid_metrics else "CALCULATION_BLOCKED")
    missing.extend(
        f"{item.group_name}: {reason}"
        for item in results
        if item.group_name != PERIOD_TAX_GROUP and item.state != "VALID"
        for reason in item.reason_codes
    )
    coverage = {
        "source_count": len({value for value in seen_sources if value}),
        "scope_count": len(results) - (1 if period_tax is not None else 0),
        "valid_scope_count": sum(item.state == "VALID" for item in results if item.group_name != PERIOD_TAX_GROUP),
        "partial_scope_count": sum(item.state == "PARTIAL" for item in results if item.group_name != PERIOD_TAX_GROUP),
        "blocked_scope_count": sum(item.state == "BLOCKED" for item in results if item.group_name != PERIOD_TAX_GROUP),
        "complete": fully_valid,
    }
    return FinanceRunResult(
        status=status,
        group_results=tuple(results),
        totals=totals,
        missing_inputs=tuple(sorted(set(item for item in missing if item))),
        metric_states=metric_states,
        coverage=coverage,
        unresolved_scopes=tuple(unresolved),
    )


def calculate_by_group(
    *,
    detailed_rows: Sequence[Mapping[str, Any]],
    profile: FinanceProfile,
    organization_id: str,
    source_id: str,
    source_sha256: str,
) -> FinanceRunResult:
    organization_id = _required_text(organization_id, "ORGANIZATION_ID_REQUIRED")
    source_id = _required_text(source_id, "SOURCE_ID_REQUIRED")
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise FinanceProfileError("SOURCE_SHA256_INVALID")
    grouped_rows = _group_rows(detailed_rows, profile.product_to_group)
    evidence_groups: list[Any] = []

    @dataclass(frozen=True, slots=True)
    class _Evidence:
        display_name: str
        profile_group_name: str | None
        source_name: str
        source_sha256: str
        member_path: str
        kernel_inputs: dict[str, Any]
        observed_metrics: dict[str, Any] | None
        reason_codes: tuple[str, ...]

    all_names = sorted(set(profile.groups) | set(grouped_rows))
    for group_name in all_names:
        rows = grouped_rows.get(group_name, [])
        if not rows:
            # Zero-activity groups are retained for operator visibility but do
            # not block unrelated calculations or require missing cost values.
            continue
        try:
            bridge = normalize_detailed_financial_rows(
                rows,
                source_id=source_id + ":" + group_name,
                source_sha256=source_sha256,
            )
            kernel_inputs = {
                key: value
                for key, value in bridge["kernel_inputs"].items()
                if key in _FINANCE_KERNEL_INPUT_NAMES
            }
            reasons: tuple[str, ...] = ()
            observed = bridge.get("observed_metrics")
        except WbDetailedFinancialError as exc:
            kernel_inputs = {}
            reasons = (exc.code,)
            observed = None
        evidence_groups.append(
            _Evidence(
                display_name=group_name,
                profile_group_name=(group_name if group_name in profile.groups else None),
                source_name=source_id,
                source_sha256=source_sha256,
                member_path=source_id,
                kernel_inputs=kernel_inputs,
                observed_metrics=observed,
                reason_codes=reasons,
            )
        )
    result = calculate_metric_groups(
        evidence_groups=evidence_groups,
        profile=profile,
        organization_id=organization_id,
    )
    existing = {item.group_name for item in result.group_results}
    zero_groups = tuple(
        GroupCalculation(
            group_name,
            "VALID",
            ("ZERO_ACTIVITY",),
            None,
            {"activity_state": "ZERO_ACTIVITY"},
        )
        for group_name in sorted(profile.groups)
        if group_name not in existing and not grouped_rows.get(group_name)
    )
    return FinanceRunResult(
        status=result.status,
        group_results=tuple((*result.group_results, *zero_groups)),
        totals=result.totals,
        missing_inputs=result.missing_inputs,
        metric_states=result.metric_states,
        coverage={**result.coverage, "zero_activity_scope_count": len(zero_groups)},
        unresolved_scopes=result.unresolved_scopes,
    )


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def save_run_result(path: Path, result: FinanceRunResult) -> None:
    _atomic_json(path, result.to_dict())


__all__ = [name for name in globals() if not name.startswith("__")]
