from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from quantum.adapters.wildberries.detailed_financial import _ALIASES
from quantum.application._finance_profile_financial_rows import (
    UNALLOCATED_SERVICE_GROUP,
    UNATTRIBUTED_PHYSICAL_GROUP,
    _typed,
)
from quantum.application._finance_profile_model import ProductRecord, UNASSIGNED_GROUP
from quantum.pilot.universal_tables import ExtractedTable


GENERIC_TABULAR_SCHEMA_VERSION = "quantum-wb-generic-tabular-v1"


@dataclass(frozen=True, slots=True)
class MetricGroupEvidence:
    display_name: str
    profile_group_name: str | None
    source_name: str
    source_sha256: str
    member_path: str
    kernel_inputs: dict[str, dict[str, Any]]
    observed_metrics: dict[str, dict[str, Any]]
    reason_codes: tuple[str, ...]
    row_count: int
    excluded_row_count: int


@dataclass(slots=True)
class _Accumulator:
    source_name: str
    source_sha256: str
    member_path: str
    profile_group_name: str | None
    display_name: str
    row_count: int = 0
    excluded_row_count: int = 0
    reasons: list[str] = None  # type: ignore[assignment]
    values: dict[str, Decimal] = None  # type: ignore[assignment]
    present: set[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.reasons = []
        self.values = defaultdict(Decimal)
        self.present = set()


def _token(value: object) -> str:
    text = " ".join(str(value).replace("\u00a0", " ").split()).casefold()
    return "".join(character for character in text if character.isalnum())


_EXTRA_ALIASES: dict[str, tuple[str, ...]] = {
    "vendor_code": ("Артикул продавца", "vendor_code", "vendor code", "sku"),
    "product_name": ("Наименование", "Название товара", "Товар", "product_name", "title"),
    "group": ("Предмет", "Категория", "Товарная группа", "group", "category", "subject"),
    "operation": ("Операция", "Тип операции", "operation", "operation_type"),
    "quantity": ("Количество", "Количество, шт.", "qty"),
    "retail_amount": ("Выручка", "Продажи", "Сумма продаж", "sales_amount", "revenue"),
    "sales_commission": ("Комиссия", "Комиссия маркетплейса", "marketplace_fee"),
    "delivery_service": ("Логистика", "Логистика, ₽", "logistics", "delivery_fee"),
    "paid_storage": ("Хранение", "Хранение, ₽", "storage"),
    "penalty": ("Штраф", "Штраф, ₽", "fine"),
    "deduction": ("Удержание", "Удержания", "withholding"),
    "advertising_amount": ("Реклама", "Реклама, ₽", "advertising", "ad_spend"),
    "discounts_amount": ("Скидки", "Скидки, ₽", "discounts"),
    "subsidies_amount": ("Субсидии", "Субсидии, ₽", "subsidies"),
    "return_compensation_amount": ("Компенсации возвратов", "return_compensation"),
}

_ALIAS_TOKENS: dict[str, frozenset[str]] = {
    field: frozenset(
        _token(alias)
        for alias in (*_ALIASES.get(field, ()), *_EXTRA_ALIASES.get(field, ()))
    )
    for field in set(_ALIASES) | set(_EXTRA_ALIASES)
}


def _column_map(headers: Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    seen_tokens: dict[str, str] = {}
    for header in headers:
        token = _token(header)
        if token:
            seen_tokens[token] = header
    for field, aliases in _ALIAS_TOKENS.items():
        matches = [header for token, header in seen_tokens.items() if token in aliases]
        if len(matches) == 1:
            result[field] = matches[0]
        elif len(matches) > 1:
            # Multiple aliases for one semantic field are handled per row; the
            # first is not selected silently.
            result[field] = "\x00".join(matches)
    return result


def _value(row: Mapping[str, Any], columns: Mapping[str, str], field: str) -> str | None:
    encoded = columns.get(field)
    if not encoded:
        return None
    values = [str(row.get(header, "")).strip() for header in encoded.split("\x00")]
    nonblank = [value for value in values if value]
    if not nonblank:
        return None
    baseline = nonblank[0]
    if any(value != baseline for value in nonblank[1:]):
        raise ValueError("GENERIC_ALIAS_CONFLICT:" + field)
    return baseline


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    text = value.replace("\u00a0", "").replace(" ", "").strip()
    if not text:
        return None
    try:
        parsed = Decimal(text.replace(",", "."))
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _operation(value: str | None) -> str:
    token = _token(value or "")
    if token in {"продажа", "sale", "sales"}:
        return "SALE"
    if token in {"возврат", "return", "refund"}:
        return "RETURN"
    if "логист" in token or "delivery" in token:
        return "LOGISTICS"
    if "хран" in token or "storage" in token:
        return "STORAGE"
    if "штраф" in token or "penalty" in token or "fine" in token:
        return "PENALTY"
    if "удерж" in token or "withhold" in token:
        return "WITHHOLDING"
    return "UNKNOWN"


def _group_for_row(
    row: Mapping[str, Any],
    columns: Mapping[str, str],
    product_to_group: Mapping[str, str],
    operation: str,
) -> tuple[str, str | None]:
    vendor = _value(row, columns, "vendor_code")
    if vendor:
        profile_group = product_to_group.get(vendor)
        return (profile_group or UNASSIGNED_GROUP, profile_group)
    if operation in {"SALE", "RETURN"}:
        return UNATTRIBUTED_PHYSICAL_GROUP, None
    return UNALLOCATED_SERVICE_GROUP, None


def _source_ids(acc: _Accumulator) -> tuple[str, ...]:
    return (
        "source-sha256:" + acc.source_sha256,
        "table:" + acc.member_path,
    )


def _money_metric(acc: _Accumulator, metric_id: str) -> dict[str, Any]:
    if metric_id in acc.present:
        return _typed(
            "VALID", format(acc.values[metric_id].quantize(Decimal("0.01")), "f"),
            "MONEY", "MONEY", "RUB", source_ids=_source_ids(acc),
        )
    return _typed(
        "BLOCKED", None, "MONEY", "MONEY", "RUB",
        reason_code="INPUT_REQUIRED_MISSING:" + metric_id,
        source_ids=_source_ids(acc),
    )


def _integer_metric(acc: _Accumulator, metric_id: str) -> dict[str, Any]:
    if metric_id in acc.present:
        value = acc.values[metric_id]
        if value == value.to_integral_value() and value >= 0:
            return _typed(
                "VALID", str(int(value)), "INTEGER", "ITEM",
                source_ids=_source_ids(acc),
            )
        acc.reasons.append("INVALID_INTEGER_AGGREGATE:" + metric_id)
    return _typed(
        "BLOCKED", None, "INTEGER", "ITEM",
        reason_code="INPUT_REQUIRED_MISSING:" + metric_id,
        source_ids=_source_ids(acc),
    )


def extract_metric_groups(
    tables: Sequence[ExtractedTable],
    *,
    product_to_group: Mapping[str, str],
) -> tuple[MetricGroupEvidence, ...]:
    accumulators: dict[tuple[str, str, str], _Accumulator] = {}
    seen_sources: set[tuple[str, str]] = set()
    for table in tables:
        source_key = (table.source_sha256, table.member_path)
        if source_key in seen_sources:
            continue
        seen_sources.add(source_key)
        columns = _column_map(table.headers)
        for row in table.rows:
            try:
                operation = _operation(_value(row, columns, "operation"))
                group_name, profile_group = _group_for_row(
                    row, columns, product_to_group, operation
                )
            except ValueError:
                group_name, profile_group, operation = UNASSIGNED_GROUP, None, "UNKNOWN"
            key = (table.source_sha256, table.member_path, group_name)
            acc = accumulators.setdefault(
                key,
                _Accumulator(
                    source_name=table.source_name,
                    source_sha256=table.source_sha256,
                    member_path=table.member_path,
                    profile_group_name=profile_group,
                    display_name=f"{group_name} · {table.source_name}",
                ),
            )
            acc.row_count += 1
            try:
                quantity = _decimal(_value(row, columns, "quantity"))
                retail = _decimal(_value(row, columns, "retail_amount"))
                commission_parts = [
                    _decimal(_value(row, columns, field))
                    for field in ("sales_commission", "ppvz_reward", "acquiring_fee")
                ]
                logistics = _decimal(_value(row, columns, "delivery_service"))
                delivery_count = _decimal(_value(row, columns, "delivery_amount"))
                return_count = _decimal(_value(row, columns, "return_amount"))
                storage = _decimal(_value(row, columns, "paid_storage"))
                penalty = _decimal(_value(row, columns, "penalty"))
                deduction = _decimal(_value(row, columns, "deduction"))
                advertising = _decimal(_value(row, columns, "advertising_amount"))
                discounts = _decimal(_value(row, columns, "discounts_amount"))
                subsidies = _decimal(_value(row, columns, "subsidies_amount"))
                compensation = _decimal(_value(row, columns, "return_compensation_amount"))
            except ValueError as exc:
                acc.excluded_row_count += 1
                acc.reasons.append(str(exc))
                continue

            if quantity is not None:
                if quantity < 0 or quantity != quantity.to_integral_value():
                    acc.reasons.append("GENERIC_QUANTITY_INVALID")
                elif operation == "SALE":
                    acc.values["gross_sales_units"] += quantity
                    acc.present.add("gross_sales_units")
                elif operation == "RETURN":
                    acc.values["returned_units"] += quantity
                    acc.present.add("returned_units")
                else:
                    acc.reasons.append("OPERATION_REQUIRED_FOR_QUANTITY")
            if retail is not None:
                if operation == "SALE":
                    contribution = abs(retail)
                elif operation == "RETURN":
                    contribution = -abs(retail)
                elif _token(columns.get("retail_amount", "")) in {
                    "выручка",
                    "продажи",
                    "суммапродаж",
                    "salesamount",
                    "revenue",
                }:
                    # An explicitly named sales/revenue column carries its own
                    # semantics; preserve the source sign so negative returns
                    # remain negative. Generic amount columns without an
                    # operation are not interpreted.
                    contribution = retail
                else:
                    contribution = None
                    acc.reasons.append(
                        "OPERATION_REQUIRED_FOR_GROSS_SALES_AMOUNT"
                    )
                if contribution is not None:
                    acc.values["gross_sales_amount"] += contribution
                    acc.present.add("gross_sales_amount")
            commission_values = [value for value in commission_parts if value is not None]
            if commission_values:
                raw = sum(commission_values, Decimal("0"))
                contribution = abs(raw) if operation == "SALE" else (-abs(raw) if operation == "RETURN" else abs(raw))
                acc.values["marketplace_commission_amount"] += contribution
                acc.present.add("marketplace_commission_amount")
            if logistics is not None:
                magnitude = abs(logistics)
                if delivery_count is not None and delivery_count > 0 and not (return_count and return_count > 0):
                    acc.values["forward_logistics_amount"] += magnitude
                    acc.present.add("forward_logistics_amount")
                elif return_count is not None and return_count > 0 and not (delivery_count and delivery_count > 0):
                    acc.values["reverse_logistics_amount"] += magnitude
                    acc.present.add("reverse_logistics_amount")
                else:
                    acc.values["unclassified_logistics_amount"] += magnitude
                    acc.present.add("unclassified_logistics_amount")
                    acc.reasons.append("LOGISTICS_DIRECTION_REQUIRED")
            if storage is not None:
                acc.values["storage_amount"] += abs(storage)
                acc.present.add("storage_amount")
            if penalty is not None or deduction is not None:
                acc.values["fines_withholdings_amount"] += abs(penalty or Decimal("0")) + abs(deduction or Decimal("0"))
                acc.present.add("fines_withholdings_amount")
            for metric_id, value in (
                ("advertising_amount", advertising),
                ("discounts_amount", discounts),
                ("subsidies_excluding_return_compensation_amount", subsidies),
                ("return_compensation_amount", compensation),
            ):
                if value is not None:
                    acc.values[metric_id] += abs(value)
                    acc.present.add(metric_id)

    result: list[MetricGroupEvidence] = []
    for acc in accumulators.values():
        kernel = {
            "gross_sales_units": _integer_metric(acc, "gross_sales_units"),
            "returned_units": _integer_metric(acc, "returned_units"),
            "gross_sales_amount": _money_metric(acc, "gross_sales_amount"),
            "marketplace_commission_amount": _money_metric(acc, "marketplace_commission_amount"),
            "forward_logistics_amount": _money_metric(acc, "forward_logistics_amount"),
            "reverse_logistics_amount": _money_metric(acc, "reverse_logistics_amount"),
            "storage_amount": _money_metric(acc, "storage_amount"),
            "fines_withholdings_amount": _money_metric(acc, "fines_withholdings_amount"),
        }
        for metric_id in (
            "advertising_amount",
            "discounts_amount",
            "subsidies_excluding_return_compensation_amount",
            "return_compensation_amount",
        ):
            if metric_id in acc.present:
                kernel[metric_id] = _money_metric(acc, metric_id)
        observed = dict(kernel)
        if "unclassified_logistics_amount" in acc.present:
            observed["unclassified_logistics_amount"] = _money_metric(acc, "unclassified_logistics_amount")
        result.append(
            MetricGroupEvidence(
                display_name=acc.display_name,
                profile_group_name=acc.profile_group_name,
                source_name=acc.source_name,
                source_sha256=acc.source_sha256,
                member_path=acc.member_path,
                kernel_inputs=kernel,
                observed_metrics=observed,
                reason_codes=tuple(sorted(set(acc.reasons))),
                row_count=acc.row_count,
                excluded_row_count=acc.excluded_row_count,
            )
        )
    return tuple(result)


def detect_products_from_tables(
    tables: Sequence[ExtractedTable],
) -> tuple[ProductRecord, ...]:
    products: dict[str, ProductRecord] = {}
    conflicted: set[str] = set()
    for table in tables:
        columns = _column_map(table.headers)
        if "vendor_code" not in columns:
            continue
        for row in table.rows:
            try:
                product_id = _value(row, columns, "vendor_code")
                if not product_id:
                    continue
                name = _value(row, columns, "product_name") or product_id
                group = _value(row, columns, "group") or UNASSIGNED_GROUP
            except ValueError:
                continue
            if product_id in conflicted:
                continue
            record = ProductRecord(product_id, name, group, table.source_name)
            previous = products.get(product_id)
            if previous is not None and (
                previous.name != record.name
                or previous.detected_group != record.detected_group
            ):
                # Conflicting product metadata cannot be selected silently.
                products.pop(product_id, None)
                conflicted.add(product_id)
                continue
            products[product_id] = record
    return tuple(products[key] for key in sorted(products))


def _merge_metric_values(
    items: Sequence[MetricGroupEvidence],
    *,
    attribute: str,
    metric_id: str,
    reasons: list[str],
) -> dict[str, Any] | None:
    candidates = [
        getattr(item, attribute)[metric_id]
        for item in items
        if metric_id in getattr(item, attribute)
        and getattr(item, attribute)[metric_id].get("state") == "VALID"
    ]
    if len(candidates) == 1:
        return dict(candidates[0])
    if len(candidates) > 1:
        baseline = candidates[0]
        signatures = {
            (
                str(candidate.get("value")),
                str(candidate.get("value_type")),
                str(candidate.get("unit")),
                str(candidate.get("currency")),
            )
            for candidate in candidates
        }
        reason = (
            "DUPLICATE_SOURCE_SCOPE_REVIEW_REQUIRED:"
            if len(signatures) == 1
            else "CONFLICTING_SOURCE_VALUES:"
        ) + metric_id
        reasons.append(reason)
        return _typed(
            "CONFLICT",
            None,
            str(baseline.get("value_type")),
            str(baseline.get("unit")),
            baseline.get("currency"),
            reason_code=reason,
            source_ids=tuple(
                source
                for candidate in candidates
                for source in candidate.get("source_ids", [])
                if isinstance(source, str)
            ),
        )
    blocked = next(
        (
            getattr(item, attribute)[metric_id]
            for item in items
            if metric_id in getattr(item, attribute)
        ),
        None,
    )
    return dict(blocked) if blocked is not None else None


def merge_metric_groups(
    groups: Sequence[MetricGroupEvidence],
) -> tuple[MetricGroupEvidence, ...]:
    """Merge complementary evidence without adding overlapping values.

    One VALID value can fill a metric that is BLOCKED in other sources. Two
    independent VALID values for the same metric are a conflict because their
    period/overlap cannot be inferred safely.
    """
    buckets: dict[str, list[MetricGroupEvidence]] = defaultdict(list)
    for group in groups:
        key = group.profile_group_name or group.display_name.split(" · ", 1)[0]
        buckets[key].append(group)
    merged: list[MetricGroupEvidence] = []
    for key, items in buckets.items():
        if len(items) == 1:
            merged.append(items[0])
            continue
        kernel_metric_ids = sorted(
            {metric_id for item in items for metric_id in item.kernel_inputs}
        )
        observed_metric_ids = sorted(
            {metric_id for item in items for metric_id in item.observed_metrics}
        )
        kernel: dict[str, dict[str, Any]] = {}
        observed: dict[str, dict[str, Any]] = {}
        reasons = [reason for item in items for reason in item.reason_codes]
        for metric_id in kernel_metric_ids:
            metric = _merge_metric_values(
                items,
                attribute="kernel_inputs",
                metric_id=metric_id,
                reasons=reasons,
            )
            if metric is not None:
                kernel[metric_id] = metric
        for metric_id in observed_metric_ids:
            metric = _merge_metric_values(
                items,
                attribute="observed_metrics",
                metric_id=metric_id,
                reasons=reasons,
            )
            if metric is not None:
                observed[metric_id] = metric
        source_hashes = sorted({item.source_sha256 for item in items})
        merged_hash = __import__("hashlib").sha256(
            "|".join(source_hashes).encode("ascii")
        ).hexdigest()
        merged.append(
            MetricGroupEvidence(
                display_name=f"{key} · объединённые источники",
                profile_group_name=(key if any(item.profile_group_name == key for item in items) else None),
                source_name="; ".join(sorted({item.source_name for item in items})),
                source_sha256=merged_hash,
                member_path="; ".join(sorted({item.member_path for item in items})),
                kernel_inputs=kernel,
                observed_metrics=observed,
                reason_codes=tuple(sorted(set(reasons))),
                row_count=sum(item.row_count for item in items),
                excluded_row_count=sum(item.excluded_row_count for item in items),
            )
        )
    return tuple(merged)


__all__ = [
    "GENERIC_TABULAR_SCHEMA_VERSION",
    "MetricGroupEvidence",
    "detect_products_from_tables",
    "extract_metric_groups",
    "merge_metric_groups",
]
