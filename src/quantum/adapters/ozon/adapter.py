from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from typing import Any

from quantum.adapters.contracts import (
    MarketplaceAdapterError,
    ReviewedSourceRequest,
)


OZON_ADAPTER_SCHEMA_VERSION = "quantum-ozon-source-adapter-v1"


class OzonSourceAdapter:
    marketplace_id = "OZON"
    adapter_id = "ozon-reviewed-source-v1"
    schema_version = OZON_ADAPTER_SCHEMA_VERSION

    def bridge_reviewed_source(
        self,
        request: ReviewedSourceRequest,
    ) -> Mapping[str, Any]:
        if request.source_format.strip().upper() != "XLSX":
            raise MarketplaceAdapterError("OZON_SOURCE_FORMAT_UNSUPPORTED")
        return {
            "schema_version": OZON_ADAPTER_SCHEMA_VERSION,
            "status": "SOURCE_BRIDGE_BLOCKED",
            "source_type": "OZON_REVIEWED_SOURCE_UNMAPPED",
            "source_id": request.source_id,
            "source_sha256": sha256(request.payload).hexdigest(),
            "sheet_name": request.schema_discovery.get("sheet_name"),
            "header_row_index": request.schema_discovery.get(
                "header_row_index"
            ),
            "header_sha256": request.schema_discovery.get("header_sha256"),
            "column_count": request.schema_discovery.get("column_count"),
            "data_row_count": request.schema_discovery.get("data_row_count"),
            "finance_request": None,
            "finance_request_state": "BLOCKED",
            "finance_request_reason_codes": [
                "OZON_SOURCE_PROFILE_REQUIRED",
                "CALCULATION_PROFILE_REQUIRED",
            ],
            "diagnostics": [
                "ADAPTER_REGISTERED_WITHOUT_SEMANTIC_SCHEMA"
            ],
            "limitations": [
                "NO_FINANCIAL_MEANING_INFERRED_FROM_UNKNOWN_COLUMNS",
                "RAW_ROWS_NOT_EXPOSED",
            ],
            "source_context": (
                dict(request.source_context)
                if request.source_context is not None
                else None
            ),
            "raw_rows_in_report": False,
        }
