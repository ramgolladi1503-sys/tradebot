from __future__ import annotations

from typing import Any, Mapping

RUNTIME_SETUP_IDENTITY_FIELDS = (
    "setup_id",
    "regime_key",
    "entry_rule_id",
    "exit_rule_id",
    "cost_model_version",
    "score_bucket",
)


def runtime_setup_identity_from_trade(trade: Any) -> dict[str, Any]:
    """Return setup identity fields explicitly supplied by a trade object.

    This helper does not invent setup identity. Missing fields stay missing so
    the journal can keep backward compatibility and reject partial identity only
    when upstream starts supplying identity fields.
    """

    payload: dict[str, Any] = {}
    for field in RUNTIME_SETUP_IDENTITY_FIELDS:
        value = getattr(trade, field, None)
        if value not in (None, "", "None"):
            payload[field] = value
    return payload


def attach_runtime_setup_identity(payload: Mapping[str, Any], trade: Any) -> dict[str, Any]:
    """Copy supplied trade setup identity into a journal payload."""

    enriched = dict(payload or {})
    enriched.update(runtime_setup_identity_from_trade(trade))
    return enriched


__all__ = [
    "RUNTIME_SETUP_IDENTITY_FIELDS",
    "attach_runtime_setup_identity",
    "runtime_setup_identity_from_trade",
]
