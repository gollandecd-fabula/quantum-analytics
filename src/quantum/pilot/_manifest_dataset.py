from __future__ import annotations

from datetime import datetime
from hashlib import sha256

from quantum.ingestion.admission import DatasetDeclaration, DatasetSensitivity

from ._manifest_common import (
    boolean,
    date_value,
    datetime_value,
    exact_keys,
    integer,
    mapping,
    sha256_text,
    text,
)
from ._scope import LocalPilotExecutionError, LocalPilotScope

_DATASET_FIELDS = {
    "dataset_id",
    "source_internal_id",
    "marketplace",
    "report_type",
    "reporting_period_start",
    "reporting_period_end",
    "timezone",
    "expected_row_count",
    "control_totals_sha256",
    "data_categories",
    "sensitivity",
    "owner_authority_reference",
    "lawful_authority_attested",
    "retention_deadline",
}


def build_declaration(
    value: object,
    *,
    scope: LocalPilotScope,
    payload: bytes,
    declared_at: datetime,
) -> DatasetDeclaration:
    item = mapping(value, "PILOT_DATASET_INVALID")
    exact_keys(item, _DATASET_FIELDS, "PILOT_DATASET_INVALID")
    categories = item["data_categories"]
    if not isinstance(categories, list) or not categories:
        raise LocalPilotExecutionError("PILOT_DATASET_INVALID")
    normalized_categories = tuple(
        text(category, "PILOT_DATASET_INVALID") for category in categories
    )
    expected_rows = item["expected_row_count"]
    if expected_rows is not None:
        expected_rows = integer(expected_rows, "PILOT_DATASET_INVALID")
    control_hash = item["control_totals_sha256"]
    if control_hash is not None:
        control_hash = sha256_text(control_hash, "PILOT_DATASET_INVALID")
    try:
        sensitivity = DatasetSensitivity(item["sensitivity"])
    except (ValueError, TypeError) as exc:
        raise LocalPilotExecutionError("PILOT_DATASET_INVALID") from exc
    return DatasetDeclaration(
        dataset_id=text(item["dataset_id"], "PILOT_DATASET_INVALID"),
        tenant_id=scope.tenant_id,
        uploader_account_id=scope.account_id,
        source_internal_id=text(
            item["source_internal_id"],
            "PILOT_DATASET_INVALID",
        ),
        marketplace=text(item["marketplace"], "PILOT_DATASET_INVALID"),
        report_type=text(item["report_type"], "PILOT_DATASET_INVALID"),
        reporting_period_start=date_value(
            item["reporting_period_start"],
            "PILOT_DATASET_INVALID",
        ),
        reporting_period_end=date_value(
            item["reporting_period_end"],
            "PILOT_DATASET_INVALID",
        ),
        timezone=text(item["timezone"], "PILOT_DATASET_INVALID", safe=False),
        original_file_sha256=sha256(payload).hexdigest(),
        original_size_bytes=len(payload),
        expected_row_count=expected_rows,
        control_totals_sha256=control_hash,
        data_categories=normalized_categories,
        sensitivity=sensitivity,
        owner_authority_reference=text(
            item["owner_authority_reference"],
            "PILOT_DATASET_INVALID",
        ),
        lawful_authority_attested=boolean(
            item["lawful_authority_attested"],
            "PILOT_DATASET_INVALID",
        ),
        retention_deadline=datetime_value(
            item["retention_deadline"],
            "PILOT_DATASET_INVALID",
        ),
        declared_at=declared_at,
    )


__all__ = ["build_declaration"]
