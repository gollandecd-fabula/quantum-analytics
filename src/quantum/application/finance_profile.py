from __future__ import annotations

from collections.abc import Mapping as _Mapping
from datetime import UTC as _UTC, datetime as _datetime
import json as _json
import os as _os
from pathlib import Path as _Path
import tempfile as _tempfile
import time as _time
from typing import Any as _Any

from quantum.application._finance_profile_model import *
from quantum.application._finance_profile_xlsx import *
from quantum.application._finance_profile_groups import *
from quantum.application._finance_profile_template import *
from quantum.application._finance_profile_financial_rows import *
from quantum.application._finance_profile_engine import *
from quantum.application._finance_profile_outputs import *


_PROFILE_REPLACE_ATTEMPTS = 5
_PROFILE_REPLACE_INITIAL_DELAY_SECONDS = 0.05
_PROFILE_MAX_BYTES = 4 * 1024 * 1024


def _profile_payload_bytes(payload: _Mapping[str, _Any]) -> bytes:
    try:
        return _json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FinanceProfileError(
            "FINANCE_PROFILE_SERIALIZATION_FAILED",
            (type(exc).__name__,),
        ) from exc


def _validate_staged_profile(path: _Path) -> None:
    try:
        raw = _json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, _json.JSONDecodeError) as exc:
        raise FinanceProfileError(
            "FINANCE_PROFILE_STAGED_VALIDATION_FAILED",
            (type(exc).__name__,),
        ) from exc
    if not isinstance(raw, _Mapping):
        raise FinanceProfileError("FINANCE_PROFILE_STAGED_VALIDATION_FAILED")
    FinanceProfile.from_dict(raw)


def _replace_with_retry(source: _Path, target: _Path) -> None:
    delay = _PROFILE_REPLACE_INITIAL_DELAY_SECONDS
    for attempt in range(_PROFILE_REPLACE_ATTEMPTS):
        try:
            _os.replace(source, target)
            return
        except OSError:
            if attempt + 1 >= _PROFILE_REPLACE_ATTEMPTS:
                raise
            _time.sleep(delay)
            delay *= 2


def _atomic_profile_json(path: _Path, payload: _Mapping[str, _Any]) -> None:
    temporary: _Path | None = None
    descriptor: int | None = None
    try:
        encoded = _profile_payload_bytes(payload)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = _tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary = _Path(temporary_name)
        with _os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(encoded)
            handle.flush()
            _os.fsync(handle.fileno())
        _validate_staged_profile(temporary)
        _replace_with_retry(temporary, path)
        temporary = None
    except FinanceProfileError:
        raise
    except OSError as exc:
        raise FinanceProfileError(
            "FINANCE_PROFILE_WRITE_FAILED",
            (type(exc).__name__, str(path)),
        ) from exc
    finally:
        if descriptor is not None:
            try:
                _os.close(descriptor)
            except OSError:
                pass
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _commit_saved_profile(
    target: FinanceProfile,
    staged: FinanceProfile,
) -> None:
    target.tax_rate_percent = staged.tax_rate_percent
    target.tax_base_metric_id = staged.tax_base_metric_id
    target.other_expense_per_unit = staged.other_expense_per_unit
    target.groups = staged.groups
    target.product_to_group = staged.product_to_group
    target.confirmed = staged.confirmed
    target.updated_at = staged.updated_at
    target.schema_version = staged.schema_version


def load_profile(path: _Path) -> FinanceProfile | None:
    if not path.is_file():
        return None
    try:
        with path.open("rb") as stream:
            payload = stream.read(_PROFILE_MAX_BYTES + 1)
    except OSError as exc:
        raise FinanceProfileError(
            "FINANCE_PROFILE_READ_FAILED",
            (type(exc).__name__, str(path)),
        ) from exc
    if len(payload) > _PROFILE_MAX_BYTES:
        raise FinanceProfileError(
            "FINANCE_PROFILE_TOO_LARGE",
            (str(len(payload)), str(_PROFILE_MAX_BYTES)),
        )
    try:
        raw = _json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, _json.JSONDecodeError) as exc:
        raise FinanceProfileError(
            "FINANCE_PROFILE_READ_FAILED",
            (type(exc).__name__, str(path)),
        ) from exc
    if not isinstance(raw, _Mapping):
        raise FinanceProfileError("FINANCE_PROFILE_INVALID")
    return FinanceProfile.from_dict(raw)


def backup_corrupt_profile(path: _Path) -> _Path:
    """Atomically move an unreadable profile aside before replacement."""
    if not path.is_file():
        raise FinanceProfileError(
            "FINANCE_PROFILE_BACKUP_FAILED",
            ("SOURCE_NOT_FOUND", str(path)),
        )
    backup = path.with_name(
        f"{path.name}.corrupt-{_time.time_ns()}.bak"
    )
    try:
        _replace_with_retry(path, backup)
    except OSError as exc:
        raise FinanceProfileError(
            "FINANCE_PROFILE_BACKUP_FAILED",
            (type(exc).__name__, str(path)),
        ) from exc
    return backup




def _normalize_partial_profile(profile: FinanceProfile) -> FinanceProfile:
    """Validate supplied values while allowing unresolved fields to remain blank."""
    staged = FinanceProfile.from_dict(profile.to_dict())
    if _optional_text(staged.tax_rate_percent) is not None:
        staged.tax_rate_percent = _rate(
            _decimal(
                staged.tax_rate_percent,
                "TAX_RATE_REQUIRED",
                maximum=Decimal("100"),
            )
        )
    else:
        staged.tax_rate_percent = None
    if staged.tax_base_metric_id is not None:
        if staged.tax_base_metric_id not in TAX_BASE_OPTIONS:
            raise FinanceProfileError("TAX_BASE_REQUIRED")
    if _optional_text(staged.other_expense_per_unit) is not None:
        staged.other_expense_per_unit = _money(
            _decimal(
                staged.other_expense_per_unit,
                "OTHER_EXPENSE_REQUIRED",
            )
        )
    else:
        staged.other_expense_per_unit = None
    integer_fields = (
        "resalable_returned_units",
        "compensated_returned_units",
    )
    money_fields = (
        "return_compensation_amount",
        "discounts_amount",
        "subsidies_amount",
        "advertising_amount",
    )
    for name, group in staged.groups.items():
        if _optional_text(group.cost_per_unit) is not None:
            group.cost_per_unit = _money(
                _decimal(group.cost_per_unit, "COST_REQUIRED:" + name)
            )
        else:
            group.cost_per_unit = None
        for field_name in integer_fields:
            raw = getattr(group, field_name)
            if _optional_text(raw) is None:
                setattr(group, field_name, None)
                continue
            value = _decimal(
                raw,
                "INVALID_GROUP_INPUT:" + name + ":" + field_name,
                integer=True,
            )
            setattr(group, field_name, str(int(value)))
        for field_name in money_fields:
            raw = getattr(group, field_name)
            if _optional_text(raw) is None:
                setattr(group, field_name, None)
                continue
            setattr(
                group,
                field_name,
                _money(
                    _decimal(
                        raw,
                        "INVALID_GROUP_INPUT:" + name + ":" + field_name,
                    )
                ),
            )
    staged.confirmed = not validate_profile(staged)
    staged.updated_at = _datetime.now(_UTC).isoformat()
    staged.schema_version = PROFILE_SCHEMA_VERSION
    return staged


def save_profile(path: _Path, profile: FinanceProfile) -> None:
    staged = _normalize_partial_profile(profile)
    _atomic_profile_json(path, staged.to_dict())
    _commit_saved_profile(profile, staged)


def detect_products_from_any_file(path: _Path) -> tuple[ProductRecord, ...]:
    """Detect explicit product identifiers from any safely readable table."""
    if not path.is_file():
        raise FinanceProfileError("SOURCE_FILE_NOT_FOUND")
    try:
        with path.open("rb") as stream:
            payload = stream.read(100 * 1024 * 1024 + 1)
    except OSError as exc:
        raise FinanceProfileError("SOURCE_FILE_READ_FAILED") from exc
    if len(payload) > 100 * 1024 * 1024:
        raise FinanceProfileError(
            "SOURCE_FILE_TOO_LARGE",
            (str(100 * 1024 * 1024),),
        )
    if not payload:
        raise FinanceProfileError("SOURCE_FILE_EMPTY")
    from quantum.pilot.universal_tables import extract_tables
    from quantum.application._finance_generic_tabular import (
        detect_products_from_tables,
    )

    extraction = extract_tables(payload, source_name=path.name)
    return detect_products_from_tables(extraction.tables)
