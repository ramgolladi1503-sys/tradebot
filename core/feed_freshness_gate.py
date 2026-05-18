"""Read-only feed freshness execution gate.

This module converts the existing freshness SLA payload into one authoritative
entry decision. It does not read feeds, write orders, call brokers, or mutate
candidate/ranking state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

FEED_FRESHNESS_GATE_SCHEMA_VERSION = 1
BLOCKING_STATES: frozenset[str] = frozenset({"STALE", "DEGRADED", "DISCONNECTED", "ERROR", "UNKNOWN"})
FRESH_STATES: frozenset[str] = frozenset({"OK"})


def _norm(value: Any) -> str:
    return str(value or "").strip().upper()


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except Exception:
        return None
    return out if out == out else None


def _nested(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, Mapping) else {}


def _reason_blocker(reason: Any) -> str:
    text = str(reason or "").strip().lower()
    if not text:
        return "FEED_BLOCKED"
    if "no_ticks" in text:
        return "FEED_NO_TICKS"
    if "ltp_stale" in text or "stale_tokens" in text:
        return "STALE_OPTION_LTP"
    if "depth_missing" in text:
        return "MISSING_DEPTH"
    if "depth_stale" in text:
        return "STALE_OPTION_DEPTH"
    if "disconnected" in text or "ws_connected=false" in text:
        return "FEED_DISCONNECTED"
    return "FEED_BLOCKED"


def _dedupe(values: list[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip().upper() for value in values if str(value).strip()}))


@dataclass(frozen=True)
class FeedFreshnessGateDecision:
    schema_version: int
    gate_state: str
    allowed_for_execution: bool
    allowed_for_paper_execution: bool
    allowed_for_live_execution: bool
    advisory_only: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    reasons: tuple[str, ...]
    freshness_state: str
    market_open: bool
    allow_stale_quotes: bool
    ltp_age_sec: float | None
    depth_age_sec: float | None
    is_order_action: bool = False
    append: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        payload["reasons"] = list(self.reasons)
        return payload


def assess_feed_freshness_gate(
    freshness_status: Mapping[str, Any] | None,
    *,
    require_market_open: bool = True,
    fail_on_degraded: bool = True,
) -> FeedFreshnessGateDecision:
    """Assess whether feed freshness is safe for paper/live entry.

    The gate is fail-closed for execution. Off-hours and stale-quote planning
    modes are allowed to remain advisory, but they are not execution-grade.
    """

    if not isinstance(freshness_status, Mapping):
        return FeedFreshnessGateDecision(
            schema_version=FEED_FRESHNESS_GATE_SCHEMA_VERSION,
            gate_state="BLOCKED",
            allowed_for_execution=False,
            allowed_for_paper_execution=False,
            allowed_for_live_execution=False,
            advisory_only=False,
            blockers=("FEED_STATUS_MISSING",),
            warnings=(),
            reasons=("freshness_status_missing_or_invalid",),
            freshness_state="UNKNOWN",
            market_open=False,
            allow_stale_quotes=False,
            ltp_age_sec=None,
            depth_age_sec=None,
        )

    freshness_state = _norm(freshness_status.get("state")) or "UNKNOWN"
    ok = _as_bool(freshness_status.get("ok"), default=False)
    market_open = _as_bool(freshness_status.get("market_open"), default=False)
    allow_stale_quotes = _as_bool(freshness_status.get("allow_stale_quotes"), default=False)
    ltp = _nested(freshness_status, "ltp")
    depth = _nested(freshness_status, "depth")
    ltp_age = _as_float(ltp.get("age_sec"))
    depth_age = _as_float(depth.get("age_sec"))

    blockers: list[str] = []
    warnings: list[str] = []
    reasons: list[str] = [str(reason) for reason in list(freshness_status.get("reasons") or []) if str(reason).strip()]

    if require_market_open and not market_open:
        blockers.append("MARKET_CLOSED")
        warnings.append("feed_gate_advisory_only_when_market_closed")

    if allow_stale_quotes:
        blockers.append("ALLOW_STALE_QUOTES_ACTIVE")
        warnings.append("stale_quotes_allowed_for_planning_not_execution")

    if freshness_state in BLOCKING_STATES:
        blockers.append(f"FEED_STATE_{freshness_state}")
    elif freshness_state not in FRESH_STATES and market_open:
        blockers.append("FEED_STATE_UNKNOWN")

    if fail_on_degraded and freshness_state == "DEGRADED":
        blockers.append("FEED_STATE_DEGRADED")

    if not ok:
        blockers.append("FEED_NOT_OK")

    if ltp and not _as_bool(ltp.get("ok"), default=False):
        blockers.append("STALE_OPTION_LTP")
    if depth and _as_bool(depth.get("required"), default=False) and not _as_bool(depth.get("ok"), default=False):
        if depth_age is None:
            blockers.append("MISSING_DEPTH")
        else:
            blockers.append("STALE_OPTION_DEPTH")

    if freshness_status.get("ws_connected") is False:
        blockers.append("FEED_DISCONNECTED")

    runtime_stale_symbols = freshness_status.get("runtime_option_stale_symbols")
    if isinstance(runtime_stale_symbols, list) and runtime_stale_symbols:
        blockers.append("STALE_OPTION_LTP")
        warnings.append("runtime_option_stale_symbols_present")

    for reason in reasons:
        blockers.append(_reason_blocker(reason))

    normalized_blockers = _dedupe(blockers)
    normalized_warnings = _dedupe(warnings)
    normalized_reasons = tuple(sorted({reason for reason in reasons if reason}))

    allowed = bool(
        not normalized_blockers
        and ok
        and market_open
        and not allow_stale_quotes
        and freshness_state in FRESH_STATES
    )

    if allowed:
        gate_state = "FRESH"
        advisory_only = False
    elif "MARKET_CLOSED" in normalized_blockers or "ALLOW_STALE_QUOTES_ACTIVE" in normalized_blockers:
        gate_state = "ADVISORY_ONLY"
        advisory_only = True
    else:
        gate_state = "BLOCKED"
        advisory_only = False

    return FeedFreshnessGateDecision(
        schema_version=FEED_FRESHNESS_GATE_SCHEMA_VERSION,
        gate_state=gate_state,
        allowed_for_execution=allowed,
        allowed_for_paper_execution=allowed,
        allowed_for_live_execution=allowed,
        advisory_only=advisory_only,
        blockers=normalized_blockers,
        warnings=normalized_warnings,
        reasons=normalized_reasons,
        freshness_state=freshness_state,
        market_open=market_open,
        allow_stale_quotes=allow_stale_quotes,
        ltp_age_sec=ltp_age,
        depth_age_sec=depth_age,
    )


__all__ = [
    "FeedFreshnessGateDecision",
    "assess_feed_freshness_gate",
]
