"""Option entry validation based on option LTP freshness policy."""

from __future__ import annotations

from typing import Any

from config import config as cfg
from core.freshness import record_freshness_decision
from core.freshness_evaluator import evaluate_quote_freshness, freshness_public_fields
from core.freshness_policy import resolve_freshness_policy
from core.time_utils import now_utc_epoch, is_market_open_ist


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _default_allow_stale_quotes(mode: str | None) -> bool:
    mode_key = str(mode or "").strip().upper()
    return bool(mode_key in {"PAPER", "SIM", "BACKTEST", "PLANNING", "ADVISORY", "OFFHOURS"})


def get_option_ltp_sla_sec(
    mode: str | None,
    default_live: float,
    *,
    allow_stale_quotes: bool | None = None,
    market_open: bool = True,
    expiry_lotto_mode: bool = False,
) -> float:
    live_sla = float(default_live)
    planning_sla = float(
        getattr(
            cfg,
            "OFFHOURS_SLA_MAX_LTP_AGE_SEC",
            max(float(getattr(cfg, "SLA_MAX_LTP_AGE_SEC", live_sla)), 900.0),
        )
    )
    allow_stale = _default_allow_stale_quotes(mode) if allow_stale_quotes is None else bool(allow_stale_quotes)
    policy = resolve_freshness_policy(
        mode=mode,
        market_open=bool(market_open),
        allow_stale_quotes=allow_stale,
        live_ltp_sec=live_sla,
        live_depth_sec=float(getattr(cfg, "SLA_MAX_DEPTH_AGE_SEC", 6.0)),
        planning_ltp_sec=planning_sla,
        planning_depth_sec=float(getattr(cfg, "OFFHOURS_SLA_MAX_DEPTH_AGE_SEC", planning_sla)),
        option_ok_live_sec=float(getattr(cfg, "FEED_HEALTH_OPTION_OK_AGE_SEC", live_sla)),
        option_ok_planning_sec=float(getattr(cfg, "OFFHOURS_SLA_MAX_LTP_AGE_SEC", planning_sla)),
        expiry_lotto_mode=bool(expiry_lotto_mode),
    )
    return float(policy.ltp_max_age_sec)


def validate_live_entry(
    *,
    signal_price: float | None,
    current_ltp: float | None,
    ltp_ts_epoch: float | None,
    candle_ts_epoch: float | None = None,
    now_epoch: float | None = None,
    mismatch_pct: float | None = None,
    max_age_sec: float | None = None,
    mode: str | None = None,
    allow_stale_quotes: bool | None = None,
    market_open: bool | None = None,
    segment: str | None = None,
    token: int | str | None = None,
    symbol: str | None = None,
    trade_id: str | None = None,
    require_token: bool = False,
    require_strict_match: bool = False,
    allow_candle_fallback: bool = False,
) -> dict[str, Any]:
    now_epoch = float(now_epoch if now_epoch is not None else now_utc_epoch())
    mismatch_pct = float(mismatch_pct if mismatch_pct is not None else getattr(cfg, "OPTION_ENTRY_MISMATCH_PCT", 0.03))
    option_sla = float(getattr(cfg, "OPTION_LTP_SLA_SEC", 2.0))
    canonical_live_sla = float(getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5))
    live_sla = min(option_sla, canonical_live_sla)
    if market_open is None:
        segment_key = str(segment or "NSE_FNO")
        try:
            market_open = bool(is_market_open_ist(segment=segment_key))
        except Exception:
            market_open = False
    max_age_sec = float(
        max_age_sec
        if max_age_sec is not None
        else get_option_ltp_sla_sec(
            mode,
            live_sla,
            allow_stale_quotes=allow_stale_quotes,
            market_open=bool(market_open),
            expiry_lotto_mode=bool(getattr(cfg, "EXPIRY_LOTTO_MODE", False)),
        )
    )

    out: dict[str, Any] = {
        "signal_price": signal_price,
        "current_ltp": current_ltp,
        "suggested_entry": None,
        "entry_status": None,
        "price_age_sec": None,
        "valid": False,
    }
    if require_token and token in (None, "", "None"):
        out["entry_status"] = "MISSING_OPTION_TOKEN"
        return out
    decision = evaluate_quote_freshness(
        symbol=str(symbol or ""),
        instrument_token=token,
        quote_epoch=ltp_ts_epoch,
        candle_epoch=candle_ts_epoch,
        threshold_sec=max_age_sec,
        market_open=bool(market_open),
        trade_id=str(trade_id or "").strip() or None,
        allow_candle_fallback=bool(allow_candle_fallback),
        decision_type="option_entry",
        now_epoch=now_epoch,
    )
    record_freshness_decision(decision)
    out.update(freshness_public_fields(decision))
    out["freshness_decision"] = decision.to_dict()
    if current_ltp is None:
        out["entry_status"] = "NO_LIVE_OPTION_FEED"
        return out
    if decision.blocker:
        if decision.reason in {"quote_missing", "quote_timestamp_missing"}:
            out["entry_status"] = "NO_LIVE_OPTION_FEED"
        else:
            out["entry_status"] = "STALE_OPTION_LTP"
        return out
    sig_val = _to_float(signal_price)
    ltp_val = _to_float(current_ltp)
    if ltp_val is None or ltp_val <= 0:
        out["entry_status"] = "INVALID_LTP"
        return out
    if sig_val is not None:
        diff = abs(sig_val - ltp_val) / ltp_val
        if diff > mismatch_pct:
            out["suggested_entry"] = ltp_val
            out["entry_status"] = "PRICE_MISMATCH"
            out["valid"] = True
            return out
    out["suggested_entry"] = ltp_val
    out["entry_status"] = "OK"
    out["valid"] = True
    return out
