from __future__ import annotations
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from ._calculation_core import calculate_units_and_product_cost
from ._calculation_expenses import calculate_other_expense
from ._calculation_profit import calculate_settlement_tax_profit
from ._common import (
    FinanceError,
    KERNEL_SCHEMA_VERSION,
    PUBLICATION_STATE,
    _CURRENCY_RE,
    _MAX_EXPRESSION_NODES,
    _MAX_OTHER_EXPENSE_COMPONENTS,
    _is_nonempty_string,
    _parse_rfc3339,
    _value_from_dict,
    canonical_hash,
)
from ._expression import evaluate_expression as _evaluate_expression
from ._expression_limits import validate_expression_policy_limits
from ._metrics import _metric, _validate_ref
from ._rounding import _decimal_context, _normalize_value, validate_rounding_policy
from ._rules_hardening import evaluate_resolved_rule, resolve_rule

_KERNEL_INPUT_NAMES = frozenset(
    {
        "gross_sales_units",
        "returned_units",
        "gross_sales_amount",
        "discounts_amount",
        "subsidies_amount",
        "marketplace_commission_amount",
        "forward_logistics_amount",
        "reverse_logistics_amount",
        "storage_amount",
        "advertising_amount",
        "fines_withholdings_amount",
    }
)
_NET_PROFIT_EXPENSE_BOUNDARY = (
    "MARKETPLACE_COMMISSION",
    "FORWARD_LOGISTICS",
    "REVERSE_LOGISTICS",
    "STORAGE",
    "ADVERTISING",
    "FINES_WITHHOLDINGS",
    "PRODUCT_COST",
    "OTHER_EXPENSE",
    "TAX",
)


def _validate_kernel_input_domains(inputs: Mapping[str, Any]) -> None:
    for name, value in inputs.items():
        if value.state == "VALID" and value.value < 0:
            raise FinanceError(f"KERNEL_INPUT_NEGATIVE_FORBIDDEN:{name}")


def evaluate_expression(
    expression: object,
    variables: Mapping[str, Mapping[str, Any]],
    dependencies: Sequence[str],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    validated_policy = validate_rounding_policy(policy)
    validate_expression_policy_limits(expression, validated_policy)
    with _decimal_context(
        validated_policy,
        operation_budget=_MAX_EXPRESSION_NODES,
    ):
        return _evaluate_expression(
            expression,
            variables,
            dependencies,
            validated_policy,
        )


def calculate(request: Mapping[str, Any]) -> dict[str, Any]:
    original = deepcopy(request)
    if not isinstance(request, Mapping):
        raise FinanceError("KERNEL_REQUEST_INVALID")
    required = {
        "calculation_id",
        "organization_id",
        "mode",
        "scenario_id",
        "calculated_at",
        "profile_ref",
        "profile_status",
        "rounding_policy",
        "currency",
        "inputs",
        "cost_per_unit",
        "other_expense_components",
        "tax_rate",
        "tax_base_metric_id",
    }
    if set(request) != required:
        raise FinanceError("KERNEL_REQUEST_INVALID")
    for field in ("calculation_id", "organization_id", "tax_base_metric_id"):
        if not _is_nonempty_string(request[field]):
            raise FinanceError("KERNEL_REQUEST_INVALID")
    if request["mode"] == "ACTUAL":
        if request["scenario_id"] is not None:
            raise FinanceError("PROFILE_MODE_CONTAMINATION")
    elif request["mode"] == "SCENARIO":
        if not _is_nonempty_string(request["scenario_id"]):
            raise FinanceError("PROFILE_MODE_CONTAMINATION")
    else:
        raise FinanceError("KERNEL_REQUEST_INVALID")
    if request["profile_status"] not in {"SHADOW", "PILOT"}:
        raise FinanceError("PROFILE_PUBLICATION_BLOCKED")
    _parse_rfc3339(request["calculated_at"], "KERNEL_TIMESTAMP_INVALID")
    profile_ref = _validate_ref(
        request["profile_ref"],
        "PROFILE_REFERENCE_MISSING",
    )
    policy = validate_rounding_policy(request["rounding_policy"])
    currency = request["currency"]
    if (
        not isinstance(currency, str)
        or _CURRENCY_RE.fullmatch(currency) is None
    ):
        raise FinanceError("KERNEL_CURRENCY_INVALID")
    raw_inputs = request["inputs"]
    if (
        not isinstance(raw_inputs, Mapping)
        or len(raw_inputs) > len(_KERNEL_INPUT_NAMES)
        or any(
            not _is_nonempty_string(name) or name not in _KERNEL_INPUT_NAMES
            for name in raw_inputs
        )
    ):
        raise FinanceError("KERNEL_INPUTS_INVALID")
    raw_expenses = request["other_expense_components"]
    if isinstance(raw_expenses, list):
        if len(raw_expenses) > _MAX_OTHER_EXPENSE_COMPONENTS:
            raise FinanceError("OTHER_EXPENSE_COMPONENTS_INVALID")
        expense_count = len(raw_expenses)
    else:
        expense_count = 1
    operation_budget = max(2, len(raw_inputs) + expense_count + 8)
    with _decimal_context(policy, operation_budget=operation_budget):
        inputs = {
            name: _normalize_value(
                _value_from_dict(raw, source_id=name),
                policy,
            )
            for name, raw in raw_inputs.items()
        }
        _validate_kernel_input_domains(inputs)
        net_units, product_cost = calculate_units_and_product_cost(
            inputs,
            request["cost_per_unit"],
            policy,
            currency,
        )
        other_expense = calculate_other_expense(
            raw_expenses,
            inputs,
            net_units,
            policy,
            currency,
        )
        (
            income,
            tax,
            profit,
            ppu,
            profitability,
        ) = calculate_settlement_tax_profit(
            inputs,
            request["tax_rate"],
            request["tax_base_metric_id"],
            policy,
            currency,
            net_units,
            product_cost,
            other_expense,
        )
        results = {
            "net_sold_units": _metric(
                net_units,
                accounting_view="OPERATIONAL",
                expense_boundary=(),
                policy=policy,
                final_round=False,
            ),
            "product_cost_amount": _metric(
                product_cost,
                accounting_view="OPERATIONAL",
                expense_boundary=("PRODUCT_COST",),
                policy=policy,
                final_round=True,
            ),
            "other_expense_amount": _metric(
                other_expense,
                accounting_view="OPERATIONAL",
                expense_boundary=("OTHER_EXPENSE",),
                policy=policy,
                final_round=True,
            ),
            "tax_amount": _metric(
                tax,
                accounting_view="TAX_RECOGNITION",
                expense_boundary=("TAX",),
                policy=policy,
                final_round=True,
            ),
            "net_marketplace_income_amount": _metric(
                income,
                accounting_view="SETTLEMENT",
                expense_boundary=(
                    "MARKETPLACE_COMMISSION",
                    "FORWARD_LOGISTICS",
                    "REVERSE_LOGISTICS",
                    "STORAGE",
                    "ADVERTISING",
                    "FINES_WITHHOLDINGS",
                ),
                policy=policy,
                final_round=True,
            ),
            "net_profit_amount": _metric(
                profit,
                accounting_view="SETTLEMENT",
                expense_boundary=_NET_PROFIT_EXPENSE_BOUNDARY,
                policy=policy,
                final_round=True,
            ),
            "profit_per_sold_unit": _metric(
                ppu,
                accounting_view="SETTLEMENT",
                expense_boundary=_NET_PROFIT_EXPENSE_BOUNDARY,
                policy=policy,
                final_round=True,
            ),
            "profitability_of_costs": _metric(
                profitability,
                accounting_view="SETTLEMENT",
                expense_boundary=(),
                policy=policy,
                final_round=True,
            ),
        }
    payload = {
        "schema_version": KERNEL_SCHEMA_VERSION,
        "calculation_id": request["calculation_id"],
        "organization_id": request["organization_id"],
        "mode": request["mode"],
        "scenario_id": request["scenario_id"],
        "profile_ref": profile_ref,
        "rounding_policy_ref": {
            "id": policy["policy_id"],
            "version": policy["version"],
            "content_hash": policy["content_hash"],
        },
        "publication_state": PUBLICATION_STATE,
        "results": results,
        "limitations": [
            "SOURCE_AUTHORITY_NOT_ACTIVATED",
            "REAL_COMMERCIAL_DATA_REQUIRES_ADMISSION",
            "B2_RECONCILIATION_NOT_IMPLEMENTED",
            "EXPENSE_UNITS_PILOT_SCOPE",
            "RETURN_COST_RESTORATION_POLICY_NOT_APPROVED",
            "PROFITABILITY_DENOMINATOR_NOT_APPROVED",
            "PRODUCTION_RELEASE_BLOCKED",
        ],
        "calculated_at": request["calculated_at"],
        "input_hash": canonical_hash(request),
        "result_hash": "",
    }
    payload["result_hash"] = canonical_hash(
        payload,
        exclude=frozenset({"result_hash"}),
    )
    if request != original:
        raise FinanceError("KERNEL_MUTATED_INPUT")
    return payload
