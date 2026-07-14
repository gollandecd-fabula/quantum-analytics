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

LEGACY_PROFILE_SCHEMA_VERSION = "quantum-home-local-finance-profile-v1"
PROFILE_SCHEMA_VERSION = "quantum-home-local-finance-profile-v2"
TAX_BASE_OPTIONS = {
    "gross_sales_amount": "Продажи/возвраты до удержаний Wildberries",
    "net_marketplace_income_amount": "Доход после расходов Wildberries",
}
GROUP_RESULT_SCHEMA_VERSION = "quantum-home-local-group-finance-result-v1"
UNASSIGNED_GROUP = "Не определено"

_SAFE_LIMITS = XlsxInspectionLimits(
    max_file_bytes=256 * 1024 * 1024,
    max_archive_entries=20_000,
    max_total_uncompressed_bytes=1024 * 1024 * 1024,
    max_entry_uncompressed_bytes=256 * 1024 * 1024,
    max_compression_ratio=250,
    max_xml_bytes=128 * 1024 * 1024,
    max_rows=1_000_000,
    max_columns=512,
)

_HEADER_ALIASES: dict[str, frozenset[str]] = {
    "product_id": frozenset(
        {
            "артикулпродавца",
            "артикул",
            "vendorcode",
            "saname",
            "sku",
            "артикулwb",
            "nmid",
            "barcode",
            "баркод",
        }
    ),
    "product_name": frozenset(
        {
            "наименование",
            "товар",
            "названиетовара",
            "productname",
            "title",
        }
    ),
    "group": frozenset(
        {
            "предмет",
            "категория",
            "товарнаягруппа",
            "группа",
            "subject",
            "subjectname",
            "category",
            "productgroup",
        }
    ),
    "cost": frozenset(
        {
            "себестоимость",
            "себестоимостьруб",
            "себестоимостьзаединицу",
            "cost",
            "costperunit",
            "unitcost",
        }
    ),
}

_PRODUCT_ID_PRIORITY = (
    "артикулпродавца",
    "vendorcode",
    "saname",
    "артикул",
    "sku",
    "артикулwb",
    "nmid",
    "barcode",
    "баркод",
)

_DETAILED_REQUIRED_HEADERS = {
    "operation": frozenset(
        {
            "обоснование",
            "обоснованиедляоплаты",
            "selleropername",
            "supplieropername",
        }
    ),
    "quantity": frozenset({"колво", "quantity"}),
    "retail_amount": frozenset(
        {"продаживозвраты", "продаживозвратыруб", "retailamount"}
    ),
    "for_pay": frozenset(
        {
            "кперечислениюпродавцу",
            "кперечислениюпродавцуруб",
            "forpay",
            "ppvzforpay",
        }
    ),
}


class FinanceProfileError(ValueError):
    def __init__(self, code: str, details: Sequence[str] = ()) -> None:
        super().__init__(code)
        self.code = code
        self.details = tuple(details)


@dataclass(frozen=True, slots=True)
class ProductRecord:
    product_id: str
    name: str
    detected_group: str
    source_file: str


@dataclass(slots=True)
class GroupInput:
    name: str
    product_ids: list[str] = field(default_factory=list)
    cost_per_unit: str | None = None
    resalable_returned_units: str | None = None
    compensated_returned_units: str | None = None
    return_compensation_amount: str | None = None
    discounts_amount: str | None = None
    subsidies_amount: str | None = None
    advertising_amount: str | None = None


@dataclass(slots=True)
class FinanceProfile:
    tax_rate_percent: str | None = None
    tax_base_metric_id: str | None = None
    other_expense_per_unit: str | None = None
    groups: dict[str, GroupInput] = field(default_factory=dict)
    product_to_group: dict[str, str] = field(default_factory=dict)
    confirmed: bool = False
    updated_at: str | None = None
    schema_version: str = PROFILE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["groups"] = {
            name: asdict(group)
            for name, group in sorted(self.groups.items())
        }
        payload["product_to_group"] = dict(
            sorted(self.product_to_group.items())
        )
        return payload

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "FinanceProfile":
        schema_version = raw.get("schema_version")
        if schema_version not in {
            LEGACY_PROFILE_SCHEMA_VERSION,
            PROFILE_SCHEMA_VERSION,
        }:
            raise FinanceProfileError("FINANCE_PROFILE_SCHEMA_UNSUPPORTED")
        legacy = schema_version == LEGACY_PROFILE_SCHEMA_VERSION
        groups_raw = raw.get("groups")
        mapping_raw = raw.get("product_to_group")
        if not isinstance(groups_raw, Mapping) or not isinstance(
            mapping_raw,
            Mapping,
        ):
            raise FinanceProfileError("FINANCE_PROFILE_INVALID")
        groups: dict[str, GroupInput] = {}
        for name, value in groups_raw.items():
            if not isinstance(name, str) or not isinstance(value, Mapping):
                raise FinanceProfileError("FINANCE_PROFILE_INVALID")
            groups[name] = GroupInput(
                name=name,
                product_ids=_string_list(value.get("product_ids")),
                cost_per_unit=_optional_text(value.get("cost_per_unit")),
                resalable_returned_units=_optional_text(
                    value.get("resalable_returned_units")
                ),
                compensated_returned_units=_optional_text(
                    value.get("compensated_returned_units")
                ),
                return_compensation_amount=_optional_text(
                    value.get("return_compensation_amount")
                ),
                discounts_amount=_optional_text(value.get("discounts_amount")),
                subsidies_amount=_optional_text(value.get("subsidies_amount")),
                advertising_amount=_optional_text(value.get("advertising_amount")),
            )
        product_to_group = {
            _required_text(
                product_id,
                "FINANCE_PROFILE_PRODUCT_ID_INVALID",
            ): _required_text(
                group_name,
                "FINANCE_PROFILE_GROUP_INVALID",
            )
            for product_id, group_name in mapping_raw.items()
        }
        tax_base = (
            None
            if legacy
            else _optional_text(raw.get("tax_base_metric_id"))
        )
        return cls(
            tax_rate_percent=_optional_text(raw.get("tax_rate_percent")),
            tax_base_metric_id=tax_base,
            other_expense_per_unit=_optional_text(
                raw.get("other_expense_per_unit")
            ),
            groups=groups,
            product_to_group=product_to_group,
            confirmed=(not legacy and raw.get("confirmed") is True),
            updated_at=(
                None if legacy else _optional_text(raw.get("updated_at"))
            ),
            schema_version=PROFILE_SCHEMA_VERSION,
        )


@dataclass(frozen=True, slots=True)
class GroupCalculation:
    group_name: str
    state: str
    reason_codes: tuple[str, ...]
    calculation: dict[str, Any] | None
    observed_metrics: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class FinanceRunResult:
    status: str
    group_results: tuple[GroupCalculation, ...]
    totals: dict[str, str]
    missing_inputs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": GROUP_RESULT_SCHEMA_VERSION,
            "status": self.status,
            "group_results": [
                {
                    "group_name": item.group_name,
                    "state": item.state,
                    "reason_codes": list(item.reason_codes),
                    "calculation": item.calculation,
                    "observed_metrics": item.observed_metrics,
                }
                for item in self.group_results
            ],
            "totals": dict(self.totals),
            "missing_inputs": list(self.missing_inputs),
            "marketplace_write_enabled": False,
        }


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_text(value: object, code: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise FinanceProfileError(code)
    return text


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise FinanceProfileError("FINANCE_PROFILE_INVALID")
    result: list[str] = []
    for item in value:
        result.append(_required_text(item, "FINANCE_PROFILE_INVALID"))
    return result


def _header_token(value: object) -> str:
    text = " ".join(
        str(value).replace("\u00a0", " ").split()
    ).casefold()
    return "".join(character for character in text if character.isalnum())


def _decimal(
    value: object,
    code: str,
    *,
    minimum: Decimal = Decimal("0"),
    maximum: Decimal | None = None,
    integer: bool = False,
) -> Decimal:
    if value is None or isinstance(value, bool):
        raise FinanceProfileError(code)
    text = str(value).replace("\u00a0", "").replace(" ", "").strip()
    if not text:
        raise FinanceProfileError(code)
    try:
        parsed = Decimal(text.replace(",", "."))
    except InvalidOperation as exc:
        raise FinanceProfileError(code) from exc
    if not parsed.is_finite() or parsed < minimum:
        raise FinanceProfileError(code)
    if maximum is not None and parsed > maximum:
        raise FinanceProfileError(code)
    if integer and parsed != parsed.to_integral_value():
        raise FinanceProfileError(code)
    return parsed


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def _rate(value: Decimal) -> str:
    normalized = value.normalize()
    return format(normalized, "f")


__all__ = [name for name in globals() if not name.startswith("__")]
