from __future__ import annotations

import re

from ._xlsx_contracts import XlsxInspectionError

_MAX_FORMULA_LENGTH = 512
_CELL_REFERENCE = re.compile(
    r"\$?[A-Za-z]{1,3}\$?[1-9][0-9]{0,6}"
    r"(?::\$?[A-Za-z]{1,3}\$?[1-9][0-9]{0,6})?"
)
_NUMBER = re.compile(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)")
_OPERATOR = re.compile(r"[()+\-*/^%,<>= ]+")
_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_.]{0,31}")
_ALLOWED_FUNCTIONS = frozenset(
    {
        "ABS",
        "AVERAGE",
        "COUNT",
        "COUNTA",
        "IF",
        "MAX",
        "MIN",
        "ROUND",
        "SUBTOTAL",
        "SUM",
    }
)
_ALLOWED_FORMULA_TYPES = frozenset({"normal", "array", "shared", "dataTable"})
_BOOLEAN_ATTRIBUTES = frozenset({"ca", "dt2D", "dtr", "del1", "del2", "bx"})
_REFERENCE_ATTRIBUTES = frozenset({"ref", "r1", "r2"})
_ALLOWED_ATTRIBUTES = frozenset(
    {"t", "ref", "si", "ca", "dt2D", "dtr", "del1", "del2", "r1", "r2", "bx"}
)


def _invalid() -> XlsxInspectionError:
    return XlsxInspectionError("XLSX_FORMULA_CONTENT_UNMODELED")


def _validate_attributes(element) -> None:
    if any(name not in _ALLOWED_ATTRIBUTES for name in element.attrib):
        raise _invalid()
    for name, value in element.attrib.items():
        if not isinstance(value, str) or not value or value != value.strip():
            raise _invalid()
        if name == "t":
            if value not in _ALLOWED_FORMULA_TYPES:
                raise _invalid()
        elif name in _REFERENCE_ATTRIBUTES:
            if _CELL_REFERENCE.fullmatch(value) is None:
                raise _invalid()
        elif name == "si":
            if not value.isdecimal() or int(value) > 1_000_000:
                raise _invalid()
        elif name in _BOOLEAN_ATTRIBUTES and value not in {"0", "1"}:
            raise _invalid()


def _validate_formula_text(text: str) -> None:
    if (
        not text
        or text != text.strip()
        or len(text) > _MAX_FORMULA_LENGTH
        or not text.isascii()
    ):
        raise _invalid()
    position = 0
    while position < len(text):
        for pattern in (_CELL_REFERENCE, _NUMBER, _OPERATOR):
            match = pattern.match(text, position)
            if match is not None:
                position = match.end()
                break
        else:
            identifier = _IDENTIFIER.match(text, position)
            if identifier is None:
                raise _invalid()
            token = identifier.group(0).upper()
            end = identifier.end()
            if token in {"TRUE", "FALSE"}:
                position = end
                continue
            if token not in _ALLOWED_FUNCTIONS or end >= len(text) or text[end] != "(":
                raise _invalid()
            position = end


def validate_formula_element(element) -> None:
    if list(element) or (element.tail is not None and element.tail.strip()):
        raise _invalid()
    _validate_attributes(element)
    text = element.text or ""
    if not text.strip():
        if element.get("t") == "shared" and element.get("si") is not None:
            return
        raise _invalid()
    _validate_formula_text(text)


__all__ = ["validate_formula_element"]
