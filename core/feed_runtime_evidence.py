"""Read-only feed runtime evidence bundle.

This module packages feed policy, config audit, and sanitized runtime feed
snapshot evidence into one deterministic payload. It does not reconnect feeds,
resubscribe tokens, mutate runtime state, write files, call brokers, or create
order intent.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.feed_policy import (
    FeedPolicyConfigAudit,
    FeedPolicyDecision,
    classify_feed_with_policy,
    validate_feed_policy_config,
)

FEED_RUNTIME_EVIDENCE_SCHEMA_VERSION = 1
FEED_RUNTIME_EVIDENCE_SOURCE = "feed_runtime_evidence_bundle_v1"
_ORDER_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"

_FEED_SNAPSHOT_KEYS: tuple[str, ...] = (
    "feed_ok",
    "effective_ws_connected",
    "ws_connected",
    "runtime_state",
    "last_tick_age_sec",
    "last_depth_age_sec",
    "option_feed_block_reason_by_symbol",
    "option_last_tick_age_by_symbol",
    "symbol_feed_ok_by_symbol",
    "feed_ok_by_symbol",
)
_STATE_MACHINE_KEYS: tuple[str, ...] = ("state", "runtime_state")


@dataclass(frozen=True)
class FeedRuntimeEvidenceBundle:
    """Read-only bundle for runtime feed evidence emission."""

    schema_version: int
    read_only: bool
    append: bool
    mode: str
    feed_ok: bool
    reason_code: str
    reasons: tuple[str, ...]
    feed_policy_decision: dict[str, Any]
    feed_policy_config_audit: dict[str, Any]
    runtime_feed_snapshot: dict[str, Any]
    symbols: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "mode": self.mode,
            "feed_ok": self.feed_ok,
            "reason_code": self.reason_code,
            "reasons": list(self.reasons),
            "symbols": list(self.symbols),
            "feed_policy_decision": dict(self.feed_policy_decision),
            "feed_policy_config_audit": dict(self.feed_policy_config_audit),
            "runtime_feed_snapshot": dict(self.runtime_feed_snapshot),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }
        payload[_ORDER_ACTION_KEY] = False
        payload[_BROKER_KEY] = False
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def build_feed_runtime_evidence_bundle(
    runtime_feed_payload: Mapping[str, Any] | None,
    *,
    mode: str | None,
    symbols: tuple[str, ...] | list[str] = (),
    policy_config: Mapping[str, Any] | None = None,
    cycle_id: str | None = None,
    source: str = FEED_RUNTIME_EVIDENCE_SOURCE,
) -> FeedRuntimeEvidenceBundle:
    """Build one read-only feed runtime evidence bundle.

    The function is pure over supplied inputs except for `generated_epoch`.
    It does not write the bundle anywhere; runtime wiring can choose where to
    emit it in a later PR.
    """

    normalized_symbols = tuple(_normalize_symbol(symbol) for symbol in symbols if _normalize_symbol(symbol))
    config_audit = validate_feed_policy_config(policy_config)
    decision = classify_feed_with_policy(
        runtime_feed_payload,
        mode=mode,
        symbols=normalized_symbols,
        policy_config=policy_config,
    )
    return FeedRuntimeEvidenceBundle(
        schema_version=FEED_RUNTIME_EVIDENCE_SCHEMA_VERSION,
        read_only=True,
        append=False,
        mode=decision.mode,
        feed_ok=decision.feed_ok,
        reason_code=decision.reason_code,
        reasons=decision.reasons,
        feed_policy_decision=decision.to_payload(),
        feed_policy_config_audit=config_audit.to_payload(),
        runtime_feed_snapshot=_sanitize_runtime_feed_payload(runtime_feed_payload),
        symbols=normalized_symbols,
        metadata={
            "source": source,
            "scope": "read_only_feed_runtime_evidence_bundle",
            "cycle_id": cycle_id,
            "policy_name": decision.policy_name,
            "config_ok": config_audit.config_ok,
        },
    )


def _sanitize_runtime_feed_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {"payload_present": False, "payload_type": type(payload).__name__}

    out: dict[str, Any] = {"payload_present": True}
    for key in _FEED_SNAPSHOT_KEYS:
        if key in payload:
            out[key] = _safe_json_value(payload.get(key))
    state_machine = payload.get("state_machine")
    if isinstance(state_machine, Mapping):
        out["state_machine"] = {
            key: _safe_json_value(state_machine.get(key))
            for key in _STATE_MACHINE_KEYS
            if key in state_machine
        }
    out["snapshot_keys"] = sorted(str(key) for key in payload.keys())
    return out


def _safe_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _safe_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _normalize_symbol(symbol: Any) -> str:
    return str(symbol or "").strip().upper()


__all__ = [
    "FEED_RUNTIME_EVIDENCE_SCHEMA_VERSION",
    "FEED_RUNTIME_EVIDENCE_SOURCE",
    "FeedRuntimeEvidenceBundle",
    "build_feed_runtime_evidence_bundle",
]
