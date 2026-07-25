from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quantum.adapters.contracts import (
    MarketplaceAdapterError,
    ReviewedSourceRequest,
)

from .dispatcher import DISPATCH_SCHEMA_VERSION, bridge_reviewed_wb_source


class WildberriesSourceAdapter:
    marketplace_id = "WILDBERRIES"
    adapter_id = "wildberries-reviewed-source-v1"
    schema_version = DISPATCH_SCHEMA_VERSION

    def bridge_reviewed_source(
        self,
        request: ReviewedSourceRequest,
    ) -> Mapping[str, Any]:
        if request.source_format.strip().upper() != "XLSX":
            raise MarketplaceAdapterError("WB_SOURCE_FORMAT_UNSUPPORTED")
        return bridge_reviewed_wb_source(
            payload=request.payload,
            schema_discovery=request.schema_discovery,
            limits=request.inspection_limits,
            source_id=request.source_id,
            source_context=request.source_context,
        )
