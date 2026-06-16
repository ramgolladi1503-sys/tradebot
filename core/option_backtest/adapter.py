from __future__ import annotations

from typing import Any

from core.execution.execution_guard import evaluate_execution_guard

from .models import OptionBacktestConfig


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        out = float(value)
        if out != out:
            return None
        return out
    except Exception:
        return None


def _safe_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _text(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, "", "None"):
            return str(value)
    return ""


def _resolve_side(row: dict[str, Any]) -> str:
    side = _text(row, "side", "trade_side", "direction").upper()
    if side in {"BUY", "SELL"}:
        return side
    option_type = _text(row, "option_type").upper()
    if option_type in {"CE", "CALL", "PE", "PUT"}:
        return "BUY"
    return "BUY"


def _resolve_levels(
    row: dict[str, Any],
    *,
    execution_entry: float | None,
    side: str,
    cfg: OptionBacktestConfig,
) -> tuple[float | None, float | None, str]:
    target = _safe_float(row.get("target") if row.get("target") is not None else row.get("target_price"))
    stop = _safe_float(row.get("stop_loss") if row.get("stop_loss") is not None else row.get("stop_price"))
    if target is not None and stop is not None:
        return target, stop, "csv"
    if execution_entry is None or not cfg.allow_derived_levels:
        return target, stop, "missing"
    stop_distance = float(execution_entry) * float(cfg.derived_stop_pct)
    target_distance = stop_distance * float(cfg.derived_target_rr)
    if side == "SELL":
        target = float(execution_entry) - target_distance
        stop = float(execution_entry) + stop_distance
    else:
        target = float(execution_entry) + target_distance
        stop = float(execution_entry) - stop_distance
    return target, stop, "derived"


def build_candidate_from_candle(row: dict[str, Any], cfg: OptionBacktestConfig) -> dict[str, Any]:
    symbol = str(row.get("symbol") or cfg.symbol)
    timestamp = row["timestamp"]
    close_price = _safe_float(row.get("close"))
    side = _resolve_side(row)
    bid = _safe_float(row.get("bid"))
    ask = _safe_float(row.get("ask"))
    has_bid_ask = bool(row.get("has_bid_ask"))
    ts_epoch = float(timestamp.timestamp())
    snapshot = {
        "ts": ts_epoch,
        "timestamp": ts_epoch,
        "bid": bid,
        "ask": ask,
    }
    guard = evaluate_execution_guard(
        side=side,
        bid=bid,
        ask=ask,
        snapshot=snapshot,
        evaluated_at_epoch=ts_epoch,
        reference_price=close_price,
    )
    execution_entry = guard.execution_entry if has_bid_ask else close_price
    target, stop, geometry_source = _resolve_levels(
        row,
        execution_entry=execution_entry,
        side=side,
        cfg=cfg,
    )

    confidence_raw = _safe_float(
        row.get("confidence_raw")
        if row.get("confidence_raw") is not None
        else row.get("signal_score")
    )
    confidence_final = _safe_float(
        row.get("confidence_final")
        if row.get("confidence_final") is not None
        else row.get("signal_score")
    )
    raw_rank_score = _safe_float(
        row.get("raw_rank_score")
        if row.get("raw_rank_score") is not None
        else row.get("signal_score")
    )
    selected_for_execution = _safe_bool(row.get("selected_for_execution"))
    if selected_for_execution is None:
        selected_for_execution = raw_rank_score is not None and raw_rank_score >= 0.5

    spread_pct = None
    if bid is not None and ask is not None:
        mid = (bid + ask) / 2.0
        if mid > 0:
            spread_pct = max(0.0, ask - bid) / mid

    source_flags = {
        "runtime_mode": "SIM",
        "candidate_origin": "historical_option_replay",
        "quote_source": "csv_bid_ask" if has_bid_ask else "csv_close_only",
        "fresh_quote_ok": has_bid_ask,
        "spread_ok": has_bid_ask,
        "liquidity_ok": has_bid_ask,
        "backtest_symbol": symbol,
        "backtest_geometry_source": geometry_source,
        "backtest_require_bid_ask": bool(cfg.require_bid_ask),
        "fallback_candidate": not has_bid_ask,
    }

    candidate_class = _text(row, "candidate_class").lower() or "real"
    truth_quality = _text(row, "truth_quality").upper() or ("REAL" if has_bid_ask else "FALLBACK")

    candidate = {
        "symbol": symbol,
        "side": side,
        "direction": side,
        "timestamp": timestamp.isoformat(),
        "ts_epoch": ts_epoch,
        "entry": execution_entry,
        "entry_price": execution_entry,
        "execution_entry": execution_entry,
        "execution_entry_source": guard.execution_entry_source if has_bid_ask else "close_fallback",
        "execution_entry_status": "executable" if has_bid_ask else "non_executable",
        "target": target,
        "target_price": target,
        "stop_loss": stop,
        "stop_price": stop,
        "current_ltp": close_price,
        "ltp": close_price,
        "best_bid": bid,
        "best_ask": ask,
        "opt_bid": bid,
        "opt_ask": ask,
        "quote_ok": has_bid_ask,
        "fresh_quote_ok": has_bid_ask,
        "liquidity_ok": has_bid_ask,
        "spread_ok": has_bid_ask,
        "quote_age_sec": 0.0 if has_bid_ask else None,
        "spread_pct": spread_pct,
        "volume": _safe_float(row.get("volume")),
        "oi": _safe_float(row.get("oi")),
        "data_confidence": 1.0 if has_bid_ask else 0.0,
        "confidence_raw": confidence_raw,
        "confidence_final": confidence_final,
        "raw_rank_score": raw_rank_score,
        "selected_for_execution": bool(selected_for_execution),
        "candidate_class": candidate_class,
        "truth_quality": truth_quality,
        "source_flags": source_flags,
        "data_state": "DATA_OK" if has_bid_ask else "DATA_MISSING",
    }

    # Fail closed if REAL_EXECUTABLE_RESEARCH and real bid/ask option data is absent
    require_real_quotes = cfg.require_bid_ask or getattr(cfg, "research_mode", None) == "REAL_EXECUTABLE_RESEARCH"
    if not has_bid_ask and require_real_quotes:
        candidate["planning_only"] = True
        candidate["execution_blocked"] = True
        candidate["execution_block_reason"] = "missing_bid_ask"
    if geometry_source == "missing":
        candidate["execution_blocked"] = True
        candidate["execution_block_reason"] = "missing_trade_geometry"
    return candidate
