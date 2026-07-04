from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import re
from typing import Any, Mapping

_MONEY_Q = Decimal("0.01")
_RATE_Q = Decimal("0.000001")


class AdapterError(ValueError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class WorkbookData:
    path: Path
    file_sha256: str
    sheets: Mapping[str, tuple[tuple[Any, ...], ...]]


def norm_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split()).strip()


def decimal_value(value: Any, *, default: Decimal = Decimal("0")) -> Decimal:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise AdapterError("WB_ADAPTER_NUMBER_INVALID", str(value))
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    text = norm_text(value).replace(" ", "").replace(",", ".")
    if text.startswith("-"):
        text = "-" + text[1:].lstrip()
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise AdapterError("WB_ADAPTER_NUMBER_INVALID", str(value)) from exc


def integer_value(value: Any) -> int:
    dec = decimal_value(value)
    if dec != dec.to_integral_value():
        raise AdapterError("WB_ADAPTER_INTEGER_INVALID", str(value))
    return int(dec)


def money_text(value: Any) -> str:
    return str(decimal_value(value).quantize(_MONEY_Q, rounding=ROUND_HALF_UP))


def date_text(value: Any) -> str:
    if isinstance(value, (int, float)):
        return (date(1899, 12, 30) + timedelta(days=int(value))).isoformat()
    text = norm_text(value)
    return text[:10] if text else ""


def month_key(value: Any) -> str:
    if isinstance(value, (int, float)):
        return date_text(value)[:7]
    text = norm_text(value).casefold()
    months = {
        "\u044f\u043d\u0432\u0430\u0440": "01",
        "\u0444\u0435\u0432\u0440\u0430\u043b": "02",
        "\u043c\u0430\u0440\u0442": "03",
        "\u0430\u043f\u0440\u0435\u043b": "04",
        "\u043c\u0430\u0439": "05",
        "\u0438\u044e\u043d": "06",
        "\u0438\u044e\u043b": "07",
        "\u0430\u0432\u0433\u0443\u0441\u0442": "08",
        "\u0441\u0435\u043d\u0442\u044f\u0431\u0440": "09",
        "\u043e\u043a\u0442\u044f\u0431\u0440": "10",
        "\u043d\u043e\u044f\u0431\u0440": "11",
        "\u0434\u0435\u043a\u0430\u0431\u0440": "12",
    }
    year = re.search(r"20\d{2}", text)
    for prefix, number in months.items():
        if prefix in text and year:
            return f"{year.group(0)}-{number}"
    return ""


def product_category(value: Any) -> str:
    text = norm_text(value).casefold()
    if "\u043b\u043e\u043d\u0433\u0441\u043b\u0438\u0432" in text or text.startswith("long"):
        return "\u041b\u043e\u043d\u0433\u0441\u043b\u0438\u0432\u044b"
    if "\u0444\u0443\u0442\u0431\u043e\u043b" in text or text.startswith("iz-"):
        return "\u0424\u0443\u0442\u0431\u043e\u043b\u043a\u0438"
    return ""
