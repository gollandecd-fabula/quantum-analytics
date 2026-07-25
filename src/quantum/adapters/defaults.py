from __future__ import annotations

from .registry import MarketplaceAdapterRegistry
from .wildberries.adapter import WildberriesSourceAdapter


def _available_default_adapters() -> tuple[object, ...]:
    """Return adapters present in the current installation.

    The repository keeps the marketplace-neutral WB/Ozon adapter set. A
    release package may intentionally omit a deferred adapter; only the
    missing optional adapter itself is tolerated. Missing dependencies inside
    an installed adapter still fail closed.
    """
    adapters: list[object] = [WildberriesSourceAdapter()]
    try:
        from .ozon.adapter import OzonSourceAdapter
    except ModuleNotFoundError as exc:
        if exc.name not in {
            "quantum.adapters.ozon",
            "quantum.adapters.ozon.adapter",
        }:
            raise
    else:
        adapters.append(OzonSourceAdapter())
    return tuple(adapters)


def build_default_marketplace_registry() -> MarketplaceAdapterRegistry:
    registry = MarketplaceAdapterRegistry()
    registry.register_many(_available_default_adapters())
    registry.freeze()
    return registry
