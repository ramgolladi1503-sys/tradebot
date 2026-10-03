"""Read-only linkage to existing EDGE-65 metadata; never grants evaluation access."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import ResearchStrategySpec


@dataclass(frozen=True)
class RegistryLinkCheck:
    linked: bool
    blockers: tuple[str, ...]
    registry_strategy_id: str | None
    registry_payload: dict[str, Any] | None


def validate_registry_link(spec: ResearchStrategySpec, *, registry=None) -> RegistryLinkCheck:
    # Importing the metadata-only registry is deferred until this function is
    # explicitly invoked. Do not import strategy modules or execute callables.
    if not spec.existing_registry_strategy_id:
        return RegistryLinkCheck(False, ("NO_EXISTING_REGISTRY_LINK",), None, None)
    if registry is None:
        from core.strategy_spec import build_strategy_spec_registry
        registry = build_strategy_spec_registry()
    if not getattr(registry, "valid", False):
        return RegistryLinkCheck(False, ("EXISTING_REGISTRY_INVALID",),
                                 spec.existing_registry_strategy_id, None)
    item = registry.get(spec.existing_registry_strategy_id)
    if item is None:
        return RegistryLinkCheck(False, ("UNKNOWN_EXISTING_STRATEGY_ID",),
                                 spec.existing_registry_strategy_id, None)
    payload = item.to_payload()
    # EDGE-65 is non-action metadata, not an execution credential.
    if not (payload.get("read_only") is True and payload.get("append") is False
            and payload.get("is_order_action") is False
            and payload.get("broker_api_called") is False):
        return RegistryLinkCheck(False, ("EXISTING_REGISTRY_ACTION_BOUNDARY",),
                                 spec.existing_registry_strategy_id, None)
    return RegistryLinkCheck(True, (), spec.existing_registry_strategy_id, payload)
