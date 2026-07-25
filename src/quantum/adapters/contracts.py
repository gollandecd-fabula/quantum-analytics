from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any, Protocol, runtime_checkable


MARKETPLACE_ADAPTER_CONTRACT_VERSION = "quantum-marketplace-adapter-contract-v1"
_MARKETPLACE_ID = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_MARKETPLACE_ALIASES = {
    "WB": "WILDBERRIES",
    "WILDBERRIES": "WILDBERRIES",
    "OZON": "OZON",
}


class MarketplaceAdapterError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def normalize_marketplace_id(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketplaceAdapterError("MARKETPLACE_ID_REQUIRED")
    normalized = re.sub(r"[\s-]+", "_", value.strip().upper())
    normalized = _MARKETPLACE_ALIASES.get(normalized, normalized)
    if _MARKETPLACE_ID.fullmatch(normalized) is None:
        raise MarketplaceAdapterError("MARKETPLACE_ID_INVALID")
    return normalized


@dataclass(frozen=True, slots=True)
class ReviewedSourceRequest:
    payload: bytes
    schema_discovery: Mapping[str, Any]
    inspection_limits: object
    source_id: str
    source_context: Mapping[str, Any] | None = None
    source_format: str = "XLSX"

    def __post_init__(self) -> None:
        if not isinstance(self.payload, bytes) or not self.payload:
            raise MarketplaceAdapterError("ADAPTER_SOURCE_BYTES_REQUIRED")
        if not isinstance(self.schema_discovery, Mapping):
            raise MarketplaceAdapterError("ADAPTER_SCHEMA_DISCOVERY_REQUIRED")
        if self.inspection_limits is None:
            raise MarketplaceAdapterError("ADAPTER_INSPECTION_LIMITS_REQUIRED")
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise MarketplaceAdapterError("ADAPTER_SOURCE_ID_REQUIRED")
        if self.source_context is not None and not isinstance(
            self.source_context,
            Mapping,
        ):
            raise MarketplaceAdapterError("ADAPTER_SOURCE_CONTEXT_INVALID")
        if not isinstance(self.source_format, str) or not self.source_format.strip():
            raise MarketplaceAdapterError("ADAPTER_SOURCE_FORMAT_REQUIRED")


@runtime_checkable
class MarketplaceSourceAdapter(Protocol):
    marketplace_id: str
    adapter_id: str
    schema_version: str

    def bridge_reviewed_source(
        self,
        request: ReviewedSourceRequest,
    ) -> Mapping[str, Any]: ...


def validate_adapter_result(
    result: Mapping[str, Any],
    *,
    marketplace_id: str,
    adapter_id: str,
    adapter_schema_version: str,
) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        raise MarketplaceAdapterError("ADAPTER_RESULT_MAPPING_REQUIRED")
    normalized = dict(result)
    status = normalized.get("status")
    if not isinstance(status, str) or not status.strip():
        raise MarketplaceAdapterError("ADAPTER_RESULT_STATUS_REQUIRED")
    if normalized.get("marketplace_write_enabled") not in (None, False):
        raise MarketplaceAdapterError("ADAPTER_MARKETPLACE_WRITE_FORBIDDEN")
    if normalized.get("raw_rows_in_report") is not False:
        raise MarketplaceAdapterError("ADAPTER_RAW_ROWS_FORBIDDEN")
    normalized["marketplace_id"] = marketplace_id
    normalized["adapter_id"] = adapter_id
    normalized["adapter_schema_version"] = adapter_schema_version
    normalized["adapter_contract_version"] = MARKETPLACE_ADAPTER_CONTRACT_VERSION
    normalized["marketplace_write_enabled"] = False
    return normalized
