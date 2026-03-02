# Migration note:
# Added deterministic activation rules for suggested trades (PLANNING -> ACTIVE).

from __future__ import annotations

from datetime import datetime, timezone
import logging

try:
    from config import config as cfg
except Exception:
    cfg = None

try:
    from core.market_data_monitor import FeedHealth, FeedState, live_entry_gate
except Exception:
    FeedHealth = None
    FeedState = None
    live_entry_gate = None

logger = logging.getLogger(__name__)


def _to_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _manual_advisory_override_enabled() -> bool:
    if cfg is None:
        return False
    return bool(getattr(cfg, "LIVE_ALLOW_MANUAL_ADVISORY_ACTIVATION", False))


def _feed_state_from_snapshot(snapshot: dict | None) -> str:
    state = str((snapshot or {}).get("state") or "").upper()
    if state in {"OK", "DEGRADED", "DOWN"}:
        return state
    return "UNKNOWN"


def _live_feed_allows_activation(
    *,
    execution_mode: str | None = None,
    feed_health: FeedHealth | None = None,
    advisory: bool = False,
    now_epoch: float | None = None,
) -> tuple[bool, str, dict]:
    mode = str(execution_mode or getattr(cfg, "EXECUTION_MODE", "SIM") or "SIM").upper()
    if mode != "LIVE":
        return True, "non_live_mode", {}
    if not callable(live_entry_gate):
        return True, "feed_gate_unavailable", {}
    snapshot: dict = {}
    try:
        allowed, reason, gate_snapshot = live_entry_gate(
            advisory_only=bool(advisory),
            monitor=feed_health,
            now_epoch=now_epoch,
        )
        if isinstance(gate_snapshot, dict):
            snapshot = dict(gate_snapshot)
    except Exception as exc:
        logger.warning("activation_feed_gate_error err=%s", exc)
        return False, "feed_gate_error", snapshot

    feed_state = _feed_state_from_snapshot(snapshot)
    if bool(advisory) and feed_state == "DEGRADED":
        if _manual_advisory_override_enabled():
            return True, "manual_advisory_override", snapshot
        return False, "advisory_override_disabled", snapshot
    return bool(allowed), str(reason), snapshot


def build_activation_signal(
    *,
    execution_mode: str | None = None,
    feed_health: FeedHealth | None = None,
    advisory: bool = False,
    now_epoch: float | None = None,
    quote_age_sec: float | int | None = None,
    spread_pct: float | int | None = None,
) -> dict:
    gate_ok, gate_reason, snapshot = _live_feed_allows_activation(
        execution_mode=execution_mode,
        feed_health=feed_health,
        advisory=advisory,
        now_epoch=now_epoch,
    )
    mode = str(execution_mode or getattr(cfg, "EXECUTION_MODE", "SIM") or "SIM").upper()
    quote_age_val = _to_float(quote_age_sec)
    spread_pct_val = _to_float(spread_pct)
    feed_state = _feed_state_from_snapshot(snapshot)

    # Local quote-quality checks are applied only in LIVE mode.
    if mode == "LIVE" and gate_ok:
        max_quote_age = _to_float(getattr(cfg, "LIVE_MAX_QUOTE_AGE_SEC", 2.0))
        if quote_age_val is not None and max_quote_age is not None and quote_age_val > max_quote_age:
            gate_ok = False
            gate_reason = f"quote_age_exceeded:{quote_age_val:.3f}>{max_quote_age:.3f}"
        max_spread_pct = _to_float(getattr(cfg, "LIVE_MAX_SPREAD_PCT", 0.02))
        if spread_pct_val is not None and max_spread_pct is not None and spread_pct_val > max_spread_pct:
            gate_ok = False
            gate_reason = f"spread_pct_exceeded:{spread_pct_val:.6f}>{max_spread_pct:.6f}"

    ui_flag = "OK"
    manual_override_used = str(gate_reason) == "manual_advisory_override"
    if manual_override_used:
        ui_flag = "ADVISORY_MANUAL_OVERRIDE"
    elif not gate_ok:
        ui_flag = "BLOCKED"

    signal = {
        "ok": bool(gate_ok),
        "allow_activation": bool(gate_ok),
        "state": str(feed_state),
        "feed_state": str(feed_state),
        "reason": str(gate_reason),
        "feed_reason": str((snapshot or {}).get("reason") or ""),
        "advisory": bool(advisory),
        "quote_age_sec": quote_age_val,
        "spread_pct": spread_pct_val,
        "manual_override_allowed": bool(_manual_advisory_override_enabled()),
        "manual_override_used": bool(manual_override_used),
        "ui_flag": ui_flag,
    }
    if mode == "LIVE":
        if not signal["ok"]:
            logger.warning(
                "activation_blocked feed_state=%s reason=%s quote_age_sec=%s spread_pct=%s advisory=%s",
                signal["feed_state"],
                signal["reason"],
                signal["quote_age_sec"],
                signal["spread_pct"],
                signal["advisory"],
            )
        elif signal["manual_override_used"]:
            logger.warning(
                "activation_manual_override feed_state=%s quote_age_sec=%s spread_pct=%s",
                signal["feed_state"],
                signal["quote_age_sec"],
                signal["spread_pct"],
            )
    return signal


def should_activate(
    side,
    entry_condition,
    entry,
    ltp,
    *,
    execution_mode: str | None = None,
    feed_health: FeedHealth | None = None,
    advisory: bool = False,
    now_epoch: float | None = None,
    quote_age_sec: float | int | None = None,
    spread_pct: float | int | None = None,
    return_signal: bool = False,
) -> bool | tuple[bool, dict]:
    signal = build_activation_signal(
        execution_mode=execution_mode,
        feed_health=feed_health,
        advisory=advisory,
        now_epoch=now_epoch,
        quote_age_sec=quote_age_sec,
        spread_pct=spread_pct,
    )
    if not signal["ok"]:
        return (False, signal) if return_signal else False
    cond = str(entry_condition or "BREAKOUT").strip().upper()
    side_val = str(side or "").strip().upper()
    entry_val = _to_float(entry)
    ltp_val = _to_float(ltp)
    if entry_val is None or ltp_val is None:
        return (False, signal) if return_signal else False
    sell_rule = "LE"
    try:
        raw = str(getattr(cfg, "ACTIVATE_SELL_RULE", "LE") or "LE").strip().upper()
        if raw in ("GE", "ABOVE", ">=", "BREAKOUT_UP"):
            sell_rule = "GE"
        elif raw in ("LE", "BELOW", "<=", "BREAKOUT_DOWN"):
            sell_rule = "LE"
    except Exception:
        sell_rule = "LE"
    triggered = False
    if cond in ("BREAKOUT", "ABOVE", "CROSS_ABOVE"):
        if side_val == "BUY":
            triggered = ltp_val >= entry_val
            return (triggered, signal) if return_signal else triggered
        if side_val == "SELL":
            triggered = ltp_val >= entry_val if sell_rule == "GE" else ltp_val <= entry_val
            return (triggered, signal) if return_signal else triggered
        return (False, signal) if return_signal else False
    # Unknown conditions default to breakout semantics for deterministic behavior.
    if side_val == "BUY":
        triggered = ltp_val >= entry_val
        return (triggered, signal) if return_signal else triggered
    if side_val == "SELL":
        triggered = ltp_val >= entry_val if sell_rule == "GE" else ltp_val <= entry_val
        return (triggered, signal) if return_signal else triggered
    return (False, signal) if return_signal else False


def live_entry_gate_status(
    *,
    execution_mode: str | None = None,
    feed_health: FeedHealth | None = None,
    advisory: bool = False,
    now_epoch: float | None = None,
    quote_age_sec: float | int | None = None,
    spread_pct: float | int | None = None,
) -> dict:
    signal = build_activation_signal(
        execution_mode=execution_mode,
        feed_health=feed_health,
        advisory=advisory,
        now_epoch=now_epoch,
        quote_age_sec=quote_age_sec,
        spread_pct=spread_pct,
    )
    return dict(signal)


def activate_trade(row: dict, ltp, ts=None, activation_signal: dict | None = None) -> dict:
    if row is None:
        return {}
    updated = dict(row)
    if ts is None:
        ts = datetime.now(timezone.utc).isoformat()
    updated["status"] = "ACTIVE"
    updated["activated_ts"] = ts
    activation_price = _to_float(ltp)
    updated["activation_price"] = activation_price
    updated["ltp_at_activation"] = activation_price
    if activation_price is not None:
        updated["fill_price"] = activation_price
    else:
        updated["fill_price"] = _to_float(updated.get("entry"))
    if isinstance(activation_signal, dict):
        updated["activation_feed_state"] = activation_signal.get("feed_state")
        updated["activation_quote_age_sec"] = _to_float(activation_signal.get("quote_age_sec"))
        updated["activation_spread_pct"] = _to_float(activation_signal.get("spread_pct"))
        updated["activation_gate_reason"] = activation_signal.get("reason")
        updated["activation_ui_flag"] = activation_signal.get("ui_flag")
        updated["activation_advisory"] = bool(activation_signal.get("advisory"))
        updated["activation_manual_override_used"] = bool(activation_signal.get("manual_override_used"))
    return updated
