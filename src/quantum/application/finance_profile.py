from __future__ import annotations

from collections.abc import Mapping as _Mapping
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


def save_profile(path: _Path, profile: FinanceProfile) -> None:
    staged = FinanceProfile.from_dict(profile.to_dict())
    confirm_profile(staged)
    _atomic_profile_json(path, staged.to_dict())
    _commit_saved_profile(profile, staged)
