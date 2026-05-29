"""Deterministic live-feed zombie classifier.

A process can be alive while the market-data feed is unusable.  This module
classifies that state without attempting reconnects, placing orders, or making
broker calls.  Runtime writers can use the result to expose the failure clearly
instead of relying on PID/process health alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

FEED_ZOMBIE_SOURCE = "feed_zombie_state_v1"
FEED_ZOMBIE_STATE = "FEED_ZOMBIE"
FEED_ZOMBIE_NO_SUBSCRIPTIONS = "feed_zombie_no_subscriptions"
FEED_ZOMBIE_WS_DISCONNECTED = "feed_zombie_ws_disconnected"
FEED_ZOMBIE_STALE_FEED = "feed_zombie_stale_feed"

_STALE_STATUSES = {"BREACH", "DEGRADED", "STALE", "FAIL", "FAILED", "ERROR"}
_LIVE_MODES = {"LIVE", "REAL", "PROD", "PRODUCTION"}


@dataclass(frozen=True)
class FeedZombieDecision:
    is_zombie: bool
    state: str
    blockers: tuple[str, ...]
    reasons: tuple[str, ...]
    evidence: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "source": FEED_ZOMBIE_SOURCE,
            "is_zombie": bool(self.is_zombie),
            "state": self.state,
            "blockers": list(self.blockers),
            "reasons": list(self.reasons),
            "evidence": dict(self.evidence),
            "read_only": True,
            "append": False,
            "is_order_action": False,
        }


def classify_feed_zombie_state(
    feed: Mapping[str, Any] | None,
    *,
    market_open: bool,
    mode: str | None = None,
    require_live_feed: bool | None = None,
) -> FeedZombieDecision:
    """Classify whether runtime feed health is a feed-zombie state.

    The classifier is intentionally conservative: a zombie requires live-feed
    context plus websocket/subscription failure plus stale/breached freshness.
    Healthy snapshots must not be marked zombie simply because one field is
    missing.
    """

    feed_payload = dict(feed or {})
    mode_text = str(mode or feed_payload.get("mode") or "").strip().upper()
    live_required = bool(require_live_feed) if require_live_feed is not None else bool(market_open and mode_text in _LIVE_MODES)

    ws_connected = _bool_or_none(feed_payload.get("ws_connected"))
    subscribed_tokens = _int_or_none(
        feed_payload.get("subscribed_tokens_count", feed_payload.get("subscriptions_count"))
    )
    subscribed_options = _int_or_none(feed_payload.get("subscribed_option_tokens_count"))
    intended_tokens = _int_or_none(feed_payload.get("intended_tokens_count"))
    sla_status = str(feed_payload.get("sla_status") or feed_payload.get("sla_state") or "").strip().upper()
    feed_reasons = tuple(str(reason) for reason in list(feed_payload.get("reasons") or []) if str(reason).strip())

    no_subscriptions = bool((subscribed_tokens is not None and subscribed_tokens <= 0) and (subscribed_options is None or subscribed_options <= 0))
    ws_down = bool(ws_connected is False)
    stale_feed = bool(sla_status in _STALE_STATUSES or feed_reasons)

    blockers: list[str] = []
    if live_required and no_subscriptions:
        blockers.append(FEED_ZOMBIE_NO_SUBSCRIPTIONS)
    if live_required and ws_down:
        blockers.append(FEED_ZOMBIE_WS_DISCONNECTED)
    if live_required and stale_feed:
        blockers.append(FEED_ZOMBIE_STALE_FEED)

    is_zombie = bool(live_required and no_subscriptions and ws_down and stale_feed)
    state = FEED_ZOMBIE_STATE if is_zombie else str(feed_payload.get("runtime_state") or feed_payload.get("state") or "UNKNOWN")

    evidence = {
        "market_open": bool(market_open),
        "mode": mode_text or None,
        "require_live_feed": bool(live_required),
        "ws_connected": ws_connected,
        "subscribed_tokens_count": subscribed_tokens,
        "subscriptions_count": _int_or_none(feed_payload.get("subscriptions_count")),
        "subscribed_option_tokens_count": subscribed_options,
        "intended_tokens_count": intended_tokens,
        "sla_status": sla_status or None,
        "feed_reasons": list(feed_reasons),
    }

    return FeedZombieDecision(
        is_zombie=is_zombie,
        state=state,
        blockers=tuple(_dedupe(blockers)),
        reasons=tuple(_dedupe(blockers if is_zombie else [])),
        evidence=evidence,
    )


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "connected", "ok", "live"}:
        return True
    if text in {"0", "false", "no", "n", "disconnected", "stale", "down"}:
        return False
    return None


def _int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


__all__ = [
    "FEED_ZOMBIE_NO_SUBSCRIPTIONS",
    "FEED_ZOMBIE_SOURCE",
    "FEED_ZOMBIE_STATE",
    "FEED_ZOMBIE_STALE_FEED",
    "FEED_ZOMBIE_WS_DISCONNECTED",
    "FeedZombieDecision",
    "classify_feed_zombie_state",
]
