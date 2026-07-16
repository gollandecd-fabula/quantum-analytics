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
from quantum.application._finance_profile_xlsx import *

def merge_detected_products(
    collections: Iterable[Sequence[ProductRecord]],
) -> tuple[ProductRecord, ...]:
    merged: dict[str, ProductRecord] = {}
    for collection in collections:
        for record in collection:
            previous = merged.get(record.product_id)
            if previous is None or (
                previous.detected_group == UNASSIGNED_GROUP
                and record.detected_group != UNASSIGNED_GROUP
            ):
                merged[record.product_id] = record
                continue
            if (
                record.detected_group != UNASSIGNED_GROUP
                and previous.detected_group != record.detected_group
            ):
                raise FinanceProfileError(
                    "PRODUCT_GROUP_CONFLICT",
                    (record.product_id, previous.detected_group, record.detected_group),
                )
    return tuple(merged[key] for key in sorted(merged))


def build_profile(
    products: Sequence[ProductRecord],
    previous: FinanceProfile | None = None,
) -> FinanceProfile:
    prior_mapping = previous.product_to_group if previous else {}
    prior_groups = previous.groups if previous else {}
    product_to_group: dict[str, str] = {}
    group_products: dict[str, list[str]] = defaultdict(list)
    for product in products:
        group_name = prior_mapping.get(product.product_id, product.detected_group)
        group_name = group_name.strip() or UNASSIGNED_GROUP
        product_to_group[product.product_id] = group_name
        group_products[group_name].append(product.product_id)
    groups: dict[str, GroupInput] = {}
    for name, product_ids in sorted(group_products.items()):
        prior = prior_groups.get(name)
        groups[name] = GroupInput(
            name=name,
            product_ids=sorted(product_ids),
            cost_per_unit=prior.cost_per_unit if prior else None,
            resalable_returned_units=(
                prior.resalable_returned_units if prior else None
            ),
            compensated_returned_units=(
                prior.compensated_returned_units if prior else None
            ),
            return_compensation_amount=(
                prior.return_compensation_amount if prior else None
            ),
            discounts_amount=prior.discounts_amount if prior else None,
            subsidies_amount=prior.subsidies_amount if prior else None,
            advertising_amount=prior.advertising_amount if prior else None,
        )
    mapping_unchanged = bool(
        previous
        and previous.product_to_group == product_to_group
        and set(previous.groups) == set(groups)
        and all(
            previous.groups[name].product_ids == groups[name].product_ids
            for name in groups
        )
    )
    return FinanceProfile(
        tax_rate_percent=previous.tax_rate_percent if previous else None,
        other_expense_per_unit=(previous.other_expense_per_unit if previous else None),
        groups=groups,
        product_to_group=product_to_group,
        confirmed=bool(previous and previous.confirmed and mapping_unchanged),
        updated_at=previous.updated_at if previous and mapping_unchanged else None,
    )


def reassign_product(profile: FinanceProfile, product_id: str, group_name: str) -> None:
    product_id = _required_text(product_id, "PRODUCT_ID_REQUIRED")
    group_name = _required_text(group_name, "GROUP_NAME_REQUIRED")
    old_group = profile.product_to_group.get(product_id)
    if old_group is None:
        raise FinanceProfileError("PRODUCT_NOT_FOUND")
    if old_group == group_name:
        return
    if old_group in profile.groups:
        profile.groups[old_group].product_ids = [
            value for value in profile.groups[old_group].product_ids if value != product_id
        ]
        if not profile.groups[old_group].product_ids:
            profile.groups.pop(old_group)
    target = profile.groups.setdefault(group_name, GroupInput(name=group_name))
    if product_id not in target.product_ids:
        target.product_ids.append(product_id)
        target.product_ids.sort()
    profile.product_to_group[product_id] = group_name
    profile.confirmed = False


def rename_group(profile: FinanceProfile, old_name: str, new_name: str) -> None:
    old_name = _required_text(old_name, "GROUP_NAME_REQUIRED")
    new_name = _required_text(new_name, "GROUP_NAME_REQUIRED")
    if old_name not in profile.groups:
        raise FinanceProfileError("GROUP_NOT_FOUND")
    if old_name == new_name:
        return
    source = profile.groups.pop(old_name)
    target = profile.groups.get(new_name)
    if target is None:
        source.name = new_name
        profile.groups[new_name] = source
    else:
        target.product_ids = sorted(set(target.product_ids + source.product_ids))
        for field_name in (
            "cost_per_unit",
            "resalable_returned_units",
            "compensated_returned_units",
            "return_compensation_amount",
            "discounts_amount",
            "subsidies_amount",
            "advertising_amount",
        ):
            target_value = getattr(target, field_name)
            source_value = getattr(source, field_name)
            if target_value is None:
                setattr(target, field_name, source_value)
            elif source_value is not None and source_value != target_value:
                setattr(target, field_name, None)
    for product_id, group_name in list(profile.product_to_group.items()):
        if group_name == old_name:
            profile.product_to_group[product_id] = new_name
    profile.confirmed = False


def parse_cost_workbook(path: Path) -> dict[str, str]:
    rows = read_first_sheet(path)
    header_index, _headers, positions = _find_header(rows, ("group", "cost"))
    group_position = positions["group"]
    cost_position = positions["cost"]
    costs: dict[str, str] = {}
    for row_index, values in rows:
        if row_index <= header_index or not any(value.strip() for value in values):
            continue
        group_name = values[group_position].strip() if group_position < len(values) else ""
        cost_raw = values[cost_position].strip() if cost_position < len(values) else ""
        if not group_name and not cost_raw:
            continue
        if not group_name:
            raise FinanceProfileError("COST_GROUP_REQUIRED", (str(row_index),))
        cost = _decimal(cost_raw, "COST_INVALID:" + group_name)
        normalized = _money(cost)
        if group_name in costs:
            raise FinanceProfileError("COST_GROUP_DUPLICATE:" + group_name)
        costs[group_name] = normalized
    if not costs:
        raise FinanceProfileError("COST_ROWS_NOT_FOUND")
    return costs


def apply_costs(profile: FinanceProfile, costs: Mapping[str, object]) -> tuple[str, ...]:
    unknown: list[str] = []
    for group_name, raw_value in costs.items():
        if group_name not in profile.groups:
            unknown.append(group_name)
            continue
        profile.groups[group_name].cost_per_unit = _money(
            _decimal(raw_value, "COST_INVALID:" + group_name)
        )
    profile.confirmed = False
    return tuple(sorted(unknown))


def validate_profile(profile: FinanceProfile) -> tuple[str, ...]:
    missing: list[str] = []
    if not profile.groups:
        missing.append("Товарные группы не определены")
    if any(name == UNASSIGNED_GROUP for name in profile.groups):
        missing.append("Есть товары без подтверждённой группы")
    try:
        _decimal(profile.tax_rate_percent, "TAX_RATE_REQUIRED", maximum=Decimal("100"))
    except FinanceProfileError:
        missing.append("Налоговая ставка")
    try:
        _decimal(profile.other_expense_per_unit, "OTHER_EXPENSE_REQUIRED")
    except FinanceProfileError:
        missing.append("Прочие расходы на единицу")
    for name, group in sorted(profile.groups.items()):
        try:
            _decimal(group.cost_per_unit, "COST_REQUIRED:" + name)
        except FinanceProfileError:
            missing.append("Себестоимость: " + name)
    return tuple(missing)


def confirm_profile(profile: FinanceProfile) -> None:
    missing = validate_profile(profile)
    if missing:
        raise FinanceProfileError("FINANCE_PROFILE_INCOMPLETE", missing)
    profile.tax_rate_percent = _rate(
        _decimal(profile.tax_rate_percent, "TAX_RATE_REQUIRED", maximum=Decimal("100"))
    )
    profile.other_expense_per_unit = _money(
        _decimal(profile.other_expense_per_unit, "OTHER_EXPENSE_REQUIRED")
    )
    for name, group in profile.groups.items():
        group.cost_per_unit = _money(
            _decimal(group.cost_per_unit, "COST_REQUIRED:" + name)
        )
    profile.confirmed = True
    profile.updated_at = datetime.now(UTC).isoformat()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
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


def save_profile(path: Path, profile: FinanceProfile) -> None:
    confirm_profile(profile)
    _atomic_json(path, profile.to_dict())


def load_profile(path: Path) -> FinanceProfile | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FinanceProfileError("FINANCE_PROFILE_READ_FAILED") from exc
    if not isinstance(raw, Mapping):
        raise FinanceProfileError("FINANCE_PROFILE_INVALID")
    return FinanceProfile.from_dict(raw)

__all__ = [name for name in globals() if not name.startswith("__")]
