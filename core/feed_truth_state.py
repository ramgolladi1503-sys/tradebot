from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from core.feed_health_truth import FeedHealthTruthDecision, classify_feed_health_truth

FEED_TRUTH_STATE_SCHEMA_VERSION = 1

MARKET_CLOSED = "MARKET_CLOSED"
STARTING = "STARTING"
LIVE = "LIVE"
DEGRADED = "DEGRADED"
DEGRADED_LOCAL = "DEGRADED_LOCAL"
VERIFYING_RECOVERY = "VERIFYING_RECOVERY"
DEAD = "DEAD"
AUTH_BLOCKED = "AUTH_BLOCKED"
RESTARTING = "RESTARTING"
RESTART_FAILED = "RESTART_FAILED"
RESTART_VERIFY_FAILED = "RESTART_VERIFY_FAILED"
RECONNECTING = "RECONNECTING"
RESUBSCRIBING = "RESUBSCRIBING"
RECOVERING_WS_DROP = "RECOVERING_WS_DROP"

_ALL_STATES = {
    MARKET_CLOSED,
    STARTING,
    LIVE,
    DEGRADED,
    DEGRADED_LOCAL,
    VERIFYING_RECOVERY,
    DEAD,
    AUTH_BLOCKED,
    RESTARTING,
    RESTART_FAILED,
    RESTART_VERIFY_FAILED,
    RECONNECTING,
    RESUBSCRIBING,
    RECOVERING_WS_DROP,
}


@dataclass(frozen=True)
class FeedTruthStateDecision:
    state: str
    reason_code: str
    reasons: tuple[str, ...] = ()
    feed_health_truth: dict[str, Any] | None = None
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def strict_live(self) -> bool:
        return self.state == LIVE

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["schema_version"] = FEED_TRUTH_STATE_SCHEMA_VERSION
        payload["strict_live"] = bool(self.strict_live)
        return payload


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "ok", "healthy"}:
        return True
    if text in {"0", "false", "no", "n", "down", "unhealthy", "degraded"}:
        return False
    return None


def _normalize_state(value: Any) -> str:
    return str(value or "").strip().upper()


def classify_feed_truth_state(
    payload: dict[str, Any] | None,
    *,
    now_epoch: float | None = None,
    max_option_tick_age_sec: float = 15.0,
    max_ltp_age_sec: float = 15.0,
    max_depth_age_sec: float = 15.0,
) -> FeedTruthStateDecision:
    """Classify one canonical runtime feed truth state.

    This is read-only and must not be treated as evidence of broker calls or
    order actions. It relies only on runtime feed facts carried in the payload.
    """
    if not isinstance(payload, dict):
        return FeedTruthStateDecision(
            state=DEAD,
            reason_code="invalid_payload",
            reasons=("invalid_payload",),
            feed_health_truth=None,
            context={},
        )

    snapshot = dict(payload)
    market_open = bool(snapshot.get("market_open", False))
    if not market_open:
        return FeedTruthStateDecision(
            state=MARKET_CLOSED,
            reason_code="market_closed",
            reasons=("market_closed",),
            feed_health_truth=None,
            context={"market_open": False},
        )

    runtime_state = _normalize_state(snapshot.get("runtime_state"))
    if runtime_state.startswith("AUTH") or runtime_state in {"TOKEN_INVALID", "LOGIN_REQUIRED"}:
        return FeedTruthStateDecision(
            state=AUTH_BLOCKED,
            reason_code="auth_blocked",
            reasons=("auth_blocked",),
            feed_health_truth=None,
            context={"runtime_state": runtime_state},
        )

    restart_verification = _mapping(snapshot.get("restart_verification"))
    restart_verify_state = _normalize_state(restart_verification.get("state"))
    if restart_verify_state == "PENDING":
        return FeedTruthStateDecision(
            state=RESTARTING,
            reason_code="restart_verify_pending",
            reasons=("restart_verify_pending",),
            feed_health_truth=None,
            context={"restart_verification": restart_verification},
        )
    if restart_verify_state == "FAILED":
        return FeedTruthStateDecision(
            state=RESTART_VERIFY_FAILED,
            reason_code="restart_verify_failed",
            reasons=("restart_verify_failed",),
            feed_health_truth=None,
            context={"restart_verification": restart_verification},
        )
    if runtime_state in {"RESTART_FAILED", "FULL_RESTART_FAILED", "START_FAILED"}:
        return FeedTruthStateDecision(
            state=RESTART_FAILED,
            reason_code="restart_failed",
            reasons=("restart_failed",),
            feed_health_truth=None,
            context={"runtime_state": runtime_state},
        )
    if runtime_state in {"RESTARTING", "RESTART_PENDING", "FULL_RESTARTING"}:
        return FeedTruthStateDecision(
            state=RESTARTING,
            reason_code="restarting",
            reasons=("restarting",),
            feed_health_truth=None,
            context={"runtime_state": runtime_state},
        )

    ws_connected = _bool_or_none(snapshot.get("effective_ws_connected", snapshot.get("ws_connected")))
    if runtime_state in {DEGRADED_LOCAL, VERIFYING_RECOVERY, RECONNECTING, RESUBSCRIBING, RECOVERING_WS_DROP}:
        return FeedTruthStateDecision(
            state=VERIFYING_RECOVERY if runtime_state == VERIFYING_RECOVERY else DEGRADED,
            reason_code=runtime_state or "recovering",
            reasons=(runtime_state or "recovering",),
            feed_health_truth=None,
            context={"runtime_state": runtime_state, "ws_connected": ws_connected},
        )

    if ws_connected is False:
        return FeedTruthStateDecision(
            state=DEAD,
            reason_code="ws_disconnected",
            reasons=("ws_disconnected",),
            feed_health_truth=None,
            context={"ws_connected": False},
        )

    subscribed_option_tokens = _safe_int(snapshot.get("subscribed_option_tokens_count"), 0)
    missing_option_tokens = _safe_int(snapshot.get("missing_option_tokens_count"), 0)
    last_tick_age = _safe_float(snapshot.get("last_tick_age_sec"))
    last_depth_age = _safe_float(snapshot.get("last_depth_age_sec"))

    # If we have not observed any tick age yet, do not treat the feed as recovered/live.
    if last_tick_age is None:
        return FeedTruthStateDecision(
            state=STARTING,
            reason_code="awaiting_first_tick",
            reasons=("awaiting_first_tick",),
            feed_health_truth=None,
            context={"ws_connected": ws_connected, "last_tick_age_sec": None},
        )

    truth: FeedHealthTruthDecision = classify_feed_health_truth(
        snapshot,
        symbols=(),
        max_option_tick_age_sec=float(max_option_tick_age_sec),
        max_ltp_age_sec=float(max_ltp_age_sec),
        max_depth_age_sec=float(max_depth_age_sec),
    )

    if not truth.feed_ok:
        return FeedTruthStateDecision(
            state=DEAD,
            reason_code="feed_unhealthy",
            reasons=tuple(truth.reasons) or ("feed_unhealthy",),
            feed_health_truth=truth.to_payload(),
            context={
                "ws_connected": ws_connected,
                "runtime_state": runtime_state or None,
                "subscribed_option_tokens_count": subscribed_option_tokens,
            },
        )

    # At this point, we have fresh ticks and no blockers. Distinguish full vs degraded coverage.
    degraded = False
    degraded_reasons: list[str] = []
    if missing_option_tokens > 0:
        degraded = True
        degraded_reasons.append("missing_option_tokens")
    if subscribed_option_tokens <= 0:
        degraded = True
        degraded_reasons.append("no_subscribed_option_tokens")
    if last_tick_age is not None and last_tick_age > float(max_ltp_age_sec):
        degraded = True
        degraded_reasons.append("ltp_age_over_sla")
    if last_depth_age is not None and last_depth_age > float(max_depth_age_sec):
        degraded = True
        degraded_reasons.append("depth_age_over_sla")

    if degraded:
        return FeedTruthStateDecision(
            state=DEGRADED,
            reason_code="degraded",
            reasons=tuple(degraded_reasons) or ("degraded",),
            feed_health_truth=truth.to_payload(),
            context={
                "ws_connected": ws_connected,
                "subscribed_option_tokens_count": subscribed_option_tokens,
                "missing_option_tokens_count": missing_option_tokens,
                "last_tick_age_sec": last_tick_age,
                "last_depth_age_sec": last_depth_age,
            },
        )

    return FeedTruthStateDecision(
        state=LIVE,
        reason_code="live",
        reasons=("live",),
        feed_health_truth=truth.to_payload(),
        context={
            "ws_connected": ws_connected,
            "subscribed_option_tokens_count": subscribed_option_tokens,
            "missing_option_tokens_count": missing_option_tokens,
            "last_tick_age_sec": last_tick_age,
            "last_depth_age_sec": last_depth_age,
        },
    )


def normalize_feed_truth_state(value: Any) -> str:
    state = _normalize_state(value)
    return state if state in _ALL_STATES else DEAD
