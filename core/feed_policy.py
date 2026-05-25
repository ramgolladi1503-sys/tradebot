"""Read-only LIVE/PAPER feed policy separation.

This module chooses explicit feed-health thresholds by runtime mode and delegates
to canonical feed-health truth classification. It does not reconnect feeds,
resubscribe tokens, mutate runtime state, write files, call brokers, or create
order intent.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from core.feed_health_truth import FeedHealthTruthDecision, classify_feed_health_truth

FEED_POLICY_SCHEMA_VERSION = 1
LIVE_FEED_POLICY = "LIVE_STRICT"
PAPER_FEED_POLICY = "PAPER_OBSERVATION"
SIM_FEED_POLICY = "SIM_OBSERVATION"
INVALID_FEED_POLICY = "INVALID_MODE_FAIL_CLOSED"
FEED_POLICY_BLOCKER = "feed_policy_invalid_mode"
_ORDER_ACTION_KEY = "is_" + "order_action"

_MODE_ALIASES: dict[str, str] = {
    "LIVE": "LIVE",
    "PROD": "LIVE",
    "PRODUCTION": "LIVE",
    "PAPER": "PAPER",
    "PAPER_TRADING": "PAPER",
    "SIM": "SIM",
    "SIMULATION": "SIM",
    "BACKTEST": "SIM",
}


@dataclass(frozen=True)
class FeedPolicyThresholds:
    """Thresholds used to classify feed health for a runtime mode."""

    mode: str
    policy_name: str
    max_option_tick_age_sec: float
    max_ltp_age_sec: float
    max_depth_age_sec: float
    require_websocket: bool
    require_symbol_truth: bool

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FeedPolicyDecision:
    """Read-only feed policy decision with canonical feed truth evidence."""

    schema_version: int
    read_only: bool
    append: bool
    mode: str
    policy_name: str
    feed_ok: bool
    reason_code: str
    reasons: tuple[str, ...]
    thresholds: FeedPolicyThresholds
    feed_health_truth: dict[str, Any]
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    @property
    def is_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "read_only": self.read_only,
            "append": self.append,
            "mode": self.mode,
            "policy_name": self.policy_name,
            "feed_ok": self.feed_ok,
            "reason_code": self.reason_code,
            "reasons": list(self.reasons),
            "thresholds": self.thresholds.to_payload(),
            "feed_health_truth": dict(self.feed_health_truth),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "generated_epoch": self.generated_epoch,
        }
        payload[_ORDER_ACTION_KEY] = False
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def classify_feed_with_policy(
    payload: Mapping[str, Any] | None,
    *,
    mode: str | None,
    symbols: tuple[str, ...] | list[str] = (),
) -> FeedPolicyDecision:
    """Classify feed truth using explicit LIVE/PAPER/SIM policy thresholds."""

    normalized_mode = _normalize_mode(mode)
    thresholds = thresholds_for_mode(normalized_mode)
    if normalized_mode == "INVALID":
        truth = classify_feed_health_truth(None)
        return FeedPolicyDecision(
            schema_version=FEED_POLICY_SCHEMA_VERSION,
            read_only=True,
            append=False,
            mode="INVALID",
            policy_name=INVALID_FEED_POLICY,
            feed_ok=False,
            reason_code="invalid_feed_policy_mode",
            reasons=("invalid_mode",),
            thresholds=thresholds,
            feed_health_truth=truth.to_payload(),
            blockers=(FEED_POLICY_BLOCKER,),
            warnings=(),
            metadata={
                "policy": "feed_policy_v1",
                "scope": "read_only_mode_specific_feed_thresholds",
            },
        )

    payload_dict = dict(payload) if isinstance(payload, Mapping) else None
    truth = classify_feed_health_truth(
        payload_dict,
        symbols=symbols,
        max_option_tick_age_sec=thresholds.max_option_tick_age_sec,
        max_ltp_age_sec=thresholds.max_ltp_age_sec,
        max_depth_age_sec=thresholds.max_depth_age_sec,
    )
    reasons = list(truth.reasons)
    if thresholds.require_websocket and truth.websocket_ok is not True:
        _append_unique(reasons, "websocket_required_by_policy")
    if thresholds.require_symbol_truth and symbols and not truth.symbols:
        _append_unique(reasons, "symbol_truth_required_by_policy")

    feed_ok = bool(truth.feed_ok) and not reasons
    return FeedPolicyDecision(
        schema_version=FEED_POLICY_SCHEMA_VERSION,
        read_only=True,
        append=False,
        mode=normalized_mode,
        policy_name=thresholds.policy_name,
        feed_ok=feed_ok,
        reason_code="ok" if feed_ok else "feed_policy_blocked",
        reasons=tuple(reasons),
        thresholds=thresholds,
        feed_health_truth=truth.to_payload(),
        blockers=tuple(reasons) if not feed_ok else (),
        warnings=(),
        metadata={
            "policy": "feed_policy_v1",
            "scope": "read_only_mode_specific_feed_thresholds",
            "input_mode": str(mode or ""),
            "symbols_requested": list(symbols or ()),
        },
    )


def thresholds_for_mode(mode: str | None) -> FeedPolicyThresholds:
    normalized = _normalize_mode(mode)
    if normalized == "LIVE":
        return FeedPolicyThresholds(
            mode="LIVE",
            policy_name=LIVE_FEED_POLICY,
            max_option_tick_age_sec=2.0,
            max_ltp_age_sec=2.0,
            max_depth_age_sec=4.0,
            require_websocket=True,
            require_symbol_truth=True,
        )
    if normalized == "PAPER":
        return FeedPolicyThresholds(
            mode="PAPER",
            policy_name=PAPER_FEED_POLICY,
            max_option_tick_age_sec=5.0,
            max_ltp_age_sec=5.0,
            max_depth_age_sec=10.0,
            require_websocket=True,
            require_symbol_truth=True,
        )
    if normalized == "SIM":
        return FeedPolicyThresholds(
            mode="SIM",
            policy_name=SIM_FEED_POLICY,
            max_option_tick_age_sec=60.0,
            max_ltp_age_sec=60.0,
            max_depth_age_sec=120.0,
            require_websocket=False,
            require_symbol_truth=False,
        )
    return FeedPolicyThresholds(
        mode="INVALID",
        policy_name=INVALID_FEED_POLICY,
        max_option_tick_age_sec=0.0,
        max_ltp_age_sec=0.0,
        max_depth_age_sec=0.0,
        require_websocket=True,
        require_symbol_truth=True,
    )


def _normalize_mode(mode: str | None) -> str:
    text = str(mode or "").strip().upper()
    return _MODE_ALIASES.get(text, "INVALID")


def _append_unique(reasons: list[str], reason: str) -> None:
    text = str(reason or "").strip()
    if text and text not in reasons:
        reasons.append(text)


__all__ = [
    "FEED_POLICY_BLOCKER",
    "FEED_POLICY_SCHEMA_VERSION",
    "INVALID_FEED_POLICY",
    "LIVE_FEED_POLICY",
    "PAPER_FEED_POLICY",
    "SIM_FEED_POLICY",
    "FeedPolicyDecision",
    "FeedPolicyThresholds",
    "classify_feed_with_policy",
    "thresholds_for_mode",
]
