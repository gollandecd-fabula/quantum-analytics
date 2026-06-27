from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quantum.ingestion.fingerprints import structural_fingerprint


WB_SYNTHETIC_SCHEMA_ID = "wb-synthetic-operations-v1"
WB_SYNTHETIC_ADAPTER_ID = "wildberries-synthetic"
WB_SYNTHETIC_ADAPTER_VERSION = "1.0"

WB_SYNTHETIC_HEADERS = (
    "row_id",
    "operation_id",
    "operation_type",
    "event_time",
    "recognition_time",
    "product_external_id",
    "quantity",
    "gross_amount",
    "currency",
    "revision",
    "supersedes_event_id",
    "reversal_of_event_id",
)


@dataclass(frozen=True, slots=True)
class SchemaDetection:
    status: str
    schema_id: str | None
    adapter_id: str | None
    adapter_version: str | None
    structural_fingerprint: dict[str, object]
    diagnostics: tuple[str, ...]


def detect_csv_schema(path: Path) -> SchemaDetection:
    fingerprint = structural_fingerprint(path)
    headers = tuple(fingerprint["descriptor"]["headers"])

    if headers == WB_SYNTHETIC_HEADERS:
        return SchemaDetection(
            status="MATCHED",
            schema_id=WB_SYNTHETIC_SCHEMA_ID,
            adapter_id=WB_SYNTHETIC_ADAPTER_ID,
            adapter_version=WB_SYNTHETIC_ADAPTER_VERSION,
            structural_fingerprint=fingerprint,
            diagnostics=(),
        )

    expected = set(WB_SYNTHETIC_HEADERS)
    actual = set(headers)
    diagnostics: list[str] = []

    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        diagnostics.append("missing_columns=" + ",".join(missing))
    if unexpected:
        diagnostics.append("unexpected_columns=" + ",".join(unexpected))
    if not missing and not unexpected and headers != WB_SYNTHETIC_HEADERS:
        diagnostics.append("column_order_changed")
    if not diagnostics:
        diagnostics.append("no_registered_schema")

    return SchemaDetection(
        status="UNKNOWN",
        schema_id=None,
        adapter_id=None,
        adapter_version=None,
        structural_fingerprint=fingerprint,
        diagnostics=tuple(diagnostics),
    )
