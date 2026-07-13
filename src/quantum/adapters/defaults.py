from __future__ import annotations

from .registry import MarketplaceAdapterRegistry
from .wildberries.adapter import WildberriesSourceAdapter


LOCAL_RELEASE_SCOPE = "WB_ONLY"
LOCAL_RELEASE_MARKETPLACES = ("WILDBERRIES",)
DEFERRED_MARKETPLACES = ("OZON",)


def build_default_marketplace_registry() -> MarketplaceAdapterRegistry:
    """Build the adapter registry exposed by the current local release."""
    registry = MarketplaceAdapterRegistry()
    registry.register(WildberriesSourceAdapter())
    registry.freeze()
    return registry
