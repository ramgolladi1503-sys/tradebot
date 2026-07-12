from __future__ import annotations

from typing import Any

import pandas as pd

from core.execution.execution_guard import evaluate_execution_guard

from .models import OptionBacktestConfig, ResearchMode


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
        if value not in (None, "", "None") and not pd.isna(value):
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


def _derive_timing_fields(row: dict[str, Any], cfg: OptionBacktestConfig) -> tuple[str | None, str | None, str | None, float | None]:
    timestamp = row["timestamp"]
    feature_cutoff = _text(row, "feature_cutoff_ts")
    signal_ts = _text(row, "signal_ts")
    earliest_entry = _text(row, "earliest_entry_ts")
    if not (feature_cutoff and signal_ts and earliest_entry):
        if cfg.require_signal_timing_provenance:
            return None, None, None, None
        feature_cutoff = feature_cutoff or timestamp.isoformat()
        signal_ts = signal_ts or timestamp.isoformat()
        earliest_entry_dt = timestamp + pd.Timedelta(minutes=int(cfg.bar_interval_minutes))
        earliest_entry = earliest_entry or earliest_entry_dt.isoformat()

    def _normalize_text_ts(value: str | None) -> tuple[str | None, pd.Timestamp | None]:
        if not value:
            return None, None
        parsed = pd.Timestamp(value)
        if parsed.tzinfo is None:
            parsed = parsed.tz_localize(cfg.timezone)
        else:
            parsed = parsed.tz_convert(cfg.timezone)
        return parsed.isoformat(), parsed

    feature_cutoff, _ = _normalize_text_ts(feature_cutoff)
    signal_ts, _ = _normalize_text_ts(signal_ts)
    earliest_entry, earliest_entry_parsed = _normalize_text_ts(earliest_entry)
    earliest_entry_epoch = (
        float(earliest_entry_parsed.timestamp())
        if earliest_entry_parsed is not None and not pd.isna(earliest_entry_parsed)
        else None
    )
    return feature_cutoff or None, signal_ts or None, earliest_entry or None, earliest_entry_epoch


def build_candidate_from_candle(row: dict[str, Any], cfg: OptionBacktestConfig) -> dict[str, Any]:
    symbol = str(row.get("symbol") or cfg.symbol)
    timestamp = row["timestamp"]
    close_price = _safe_float(row.get("close"))
    side = _resolve_side(row)
    bid = _safe_float(row.get("bid"))
    ask = _safe_float(row.get("ask"))
    has_bid_ask = bool(row.get("has_bid_ask"))
    ts_epoch = float(timestamp.timestamp())
    snapshot = {"ts": ts_epoch, "timestamp": ts_epoch, "bid": bid, "ask": ask}
    guard = evaluate_execution_guard(
        side=side,
        bid=bid,
        ask=ask,
        snapshot=snapshot,
        evaluated_at_epoch=ts_epoch,
        reference_price=close_price,
    )
    execution_entry = guard.execution_entry if has_bid_ask else close_price
    target, stop, geometry_source = _resolve_levels(row, execution_entry=execution_entry, side=side, cfg=cfg)
    confidence_raw = _safe_float(row.get("confidence_raw") if row.get("confidence_raw") is not None else row.get("signal_score"))
    confidence_final = _safe_float(row.get("confidence_final") if row.get("confidence_final") is not None else row.get("signal_score"))
    raw_rank_score = _safe_float(row.get("raw_rank_score") if row.get("raw_rank_score") is not None else row.get("signal_score"))
    selected_for_execution = _safe_bool(row.get("selected_for_execution"))
    if selected_for_execution is None:
        selected_for_execution = raw_rank_score is not None and raw_rank_score >= 0.5
    spread_pct = None
    if bid is not None and ask is not None:
        mid = (bid + ask) / 2.0
        if mid > 0:
            spread_pct = max(0.0, ask - bid) / mid
    feature_cutoff_ts, signal_ts, earliest_entry_ts, earliest_entry_epoch = _derive_timing_fields(row, cfg)
    source_flags = {
        "runtime_mode": "SIM",
        "candidate_origin": "historical_option_replay",
        "quote_source": "csv_bid_ask" if has_bid_ask else "csv_close_only",
        "fresh_quote_ok": has_bid_ask,
        "spread_ok": has_bid_ask,
        "liquidity_ok": has_bid_ask,
        "backtest_symbol": symbol,
        "backtest_geometry_source": geometry_source,
        "backtest_timing_source": "csv" if _text(row, "feature_cutoff_ts") else "derived",
        "backtest_require_bid_ask": bool(cfg.require_bid_ask),
        "fallback_candidate": not has_bid_ask,
    }
    candidate_class = _text(row, "candidate_class").lower() or "real"
    truth_quality = _text(row, "truth_quality").upper() or ("REAL" if has_bid_ask else "FALLBACK")
    candidate = {
        "symbol": symbol,
        "source_symbol": symbol,
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
        "feature_cutoff_ts": feature_cutoff_ts,
        "signal_ts": signal_ts,
        "earliest_entry_ts": earliest_entry_ts,
        "earliest_entry_ts_epoch": earliest_entry_epoch,
        "setup_id": _text(row, "setup_id") or "unknown",
        "regime": _text(row, "regime") or "unknown",
        "is_oos": _safe_bool(row.get("is_oos")) if _safe_bool(row.get("is_oos")) is not None else False,
        "underlying": _text(row, "underlying", "underlying_symbol"),
        "option_type": _text(row, "option_type", "instrument_type", "type").upper(),
        "strike": _safe_float(row.get("strike") if row.get("strike") is not None else row.get("strike_price")),
        "expiry": _text(row, "expiry", "expiry_date"),
        "provider": _text(row, "provider", "source_provider"),
        "dataset_hash": _text(row, "dataset_hash", "source_dataset_hash", "dataset_version"),
        "bar_interval": _text(row, "bar_interval", "interval", "bar_size"),
    }
    require_real_quotes = cfg.require_bid_ask or cfg.research_mode == ResearchMode.REAL_EXECUTABLE_RESEARCH
    if not has_bid_ask and require_real_quotes:
        candidate["planning_only"] = True
        candidate["execution_blocked"] = True
        candidate["execution_block_reason"] = "missing_bid_ask"
    if geometry_source == "missing":
        candidate["execution_blocked"] = True
        candidate["execution_block_reason"] = "missing_trade_geometry"
    if cfg.require_signal_timing_provenance and (feature_cutoff_ts is None or signal_ts is None or earliest_entry_ts is None):
        candidate["execution_blocked"] = True
        candidate["execution_block_reason"] = "missing_signal_timing_provenance"
    if cfg.research_mode == ResearchMode.REAL_EXECUTABLE_RESEARCH and earliest_entry_ts == timestamp.isoformat():
        candidate["execution_blocked"] = True
        candidate["execution_block_reason"] = "ambiguous_signal_timing"
    return candidate
