from __future__ import annotations

from .ozon.adapter import OzonSourceAdapter
from .registry import MarketplaceAdapterRegistry
from .wildberries.adapter import WildberriesSourceAdapter


def build_default_marketplace_registry() -> MarketplaceAdapterRegistry:
    registry = MarketplaceAdapterRegistry()
    registry.register_many(
        (
            WildberriesSourceAdapter(),
            OzonSourceAdapter(),
        )
    )
    registry.freeze()
    return registry
