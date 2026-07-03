from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ._scope import LocalPilotExecutionError

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")


def load_json(path: Path) -> Mapping[str, Any]:
    if not isinstance(path, Path):
        raise LocalPilotExecutionError("PILOT_MANIFEST_PATH_INVALID")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalPilotExecutionError("PILOT_MANIFEST_READ_FAILED") from exc
    return mapping(payload, "PILOT_MANIFEST_INVALID")


def mapping(value: object, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LocalPilotExecutionError(code)
    return value


def exact_keys(value: Mapping[str, Any], expected: set[str], code: str) -> None:
    if set(value) != expected:
        raise LocalPilotExecutionError(code)


def text(value: object, code: str, *, safe: bool = True) -> str:
    if not isinstance(value, str) or not value:
        raise LocalPilotExecutionError(code)
    if safe and _SAFE_ID.fullmatch(value) is None:
        raise LocalPilotExecutionError(code)
    return value


def boolean(value: object, code: str) -> bool:
    if not isinstance(value, bool):
        raise LocalPilotExecutionError(code)
    return value


def integer(value: object, code: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise LocalPilotExecutionError(code)
    return value


def sha256_text(value: object, code: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise LocalPilotExecutionError(code)
    return value


def date_value(value: object, code: str) -> date:
    if not isinstance(value, str):
        raise LocalPilotExecutionError(code)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise LocalPilotExecutionError(code) from exc


def datetime_value(value: object, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise LocalPilotExecutionError(code)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise LocalPilotExecutionError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LocalPilotExecutionError(code)
    return parsed


__all__ = [
    "boolean",
    "date_value",
    "datetime_value",
    "exact_keys",
    "integer",
    "load_json",
    "mapping",
    "sha256_text",
    "text",
]
