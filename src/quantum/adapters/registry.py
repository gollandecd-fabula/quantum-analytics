from __future__ import annotations

from collections.abc import Iterable

from .contracts import (
    MarketplaceAdapterError,
    MarketplaceSourceAdapter,
    ReviewedSourceRequest,
    normalize_marketplace_id,
    validate_adapter_result,
)


class MarketplaceAdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, MarketplaceSourceAdapter] = {}
        self._frozen = False

    def register(self, adapter: MarketplaceSourceAdapter) -> None:
        if self._frozen:
            raise MarketplaceAdapterError("MARKETPLACE_ADAPTER_REGISTRY_FROZEN")
        if not isinstance(adapter, MarketplaceSourceAdapter):
            raise MarketplaceAdapterError("MARKETPLACE_ADAPTER_PROTOCOL_INVALID")
        marketplace_id = normalize_marketplace_id(adapter.marketplace_id)
        adapter_id = getattr(adapter, "adapter_id", None)
        schema_version = getattr(adapter, "schema_version", None)
        if not isinstance(adapter_id, str) or not adapter_id.strip():
            raise MarketplaceAdapterError("MARKETPLACE_ADAPTER_ID_REQUIRED")
        if not isinstance(schema_version, str) or not schema_version.strip():
            raise MarketplaceAdapterError("MARKETPLACE_ADAPTER_SCHEMA_REQUIRED")
        if marketplace_id in self._adapters:
            raise MarketplaceAdapterError("MARKETPLACE_ADAPTER_DUPLICATE")
        self._adapters[marketplace_id] = adapter

    def register_many(self, adapters: Iterable[MarketplaceSourceAdapter]) -> None:
        for adapter in adapters:
            self.register(adapter)

    def freeze(self) -> None:
        self._frozen = True

    def registered_marketplaces(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))

    def resolve(self, marketplace: object) -> MarketplaceSourceAdapter:
        marketplace_id = normalize_marketplace_id(marketplace)
        try:
            return self._adapters[marketplace_id]
        except KeyError as exc:
            raise MarketplaceAdapterError(
                "MARKETPLACE_ADAPTER_NOT_REGISTERED"
            ) from exc

    def bridge_reviewed_source(
        self,
        marketplace: object,
        request: ReviewedSourceRequest,
    ) -> dict[str, object]:
        marketplace_id = normalize_marketplace_id(marketplace)
        adapter = self.resolve(marketplace_id)
        result = adapter.bridge_reviewed_source(request)
        return validate_adapter_result(
            result,
            marketplace_id=marketplace_id,
            adapter_id=adapter.adapter_id,
            adapter_schema_version=adapter.schema_version,
        )
