from __future__ import annotations

import argparse
from datetime import datetime, timezone
from collections import Counter
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

from config import config as cfg
from core.paths import repo_root

from .schema import TradeIntentEvent, build_trade_key
from .store import load_executable_review_queue_events, load_trade_intent_events


IST = ZoneInfo("Asia/Kolkata")
_CANDLE_COLS = ("time_ms", "open", "high", "low", "close")


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        if out != out:  # NaN guard
            return None
        return out
    except Exception:
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(float(value))
    except Exception:
        return None


def _parse_date_key(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = str(value or "").strip()
    if not text:
        return datetime.now(tz=IST).date().isoformat()
    return datetime.fromisoformat(text).date().isoformat()


def _to_day_key(epoch_ms: int) -> str:
    return datetime.fromtimestamp(float(epoch_ms) / 1000.0, tz=timezone.utc).astimezone(IST).date().isoformat()


def _default_report_path(date_key: str) -> Path:
    return _report_path_for_scope(
        date_key,
        report_dir_key="SHADOW_PORTFOLIO_REPORT_DIR",
        filename="shadow_portfolio.json",
    )


def _default_executable_report_path(date_key: str) -> Path:
    return _report_path_for_scope(
        date_key,
        report_dir_key="EXECUTABLE_SHADOW_PORTFOLIO_REPORT_DIR",
        filename="executable_shadow_portfolio.json",
    )


def _report_path_for_scope(date_key: str, *, report_dir_key: str, filename: str) -> Path:
    base = str(getattr(cfg, report_dir_key, "") or "").strip()
    if base:
        return Path(base) / date_key / filename
    return repo_root() / "runtime" / "analytics" / "reports" / date_key / filename


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(dict(payload), ensure_ascii=True, sort_keys=True, indent=2), encoding="utf-8")
    tmp.replace(path)


def _coerce_event(item: TradeIntentEvent | Mapping[str, Any]) -> tuple[TradeIntentEvent, dict] | None:
    if isinstance(item, TradeIntentEvent):
        return item, item.to_dict()
    if not isinstance(item, Mapping):
        return None
    raw = dict(item)
    try:
        event = TradeIntentEvent.from_dict(raw)
    except Exception:
        return None
    return event, raw


def _is_sell_side(side: str | None) -> bool:
    text = str(side or "").strip().upper()
    return text.startswith("SELL") or text in {"SHORT", "S"}


def _normalize_candles(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(columns=list(_CANDLE_COLS))
    if df is None or df.empty:
        return out

    frame = df.copy()
    if "time_ms" not in frame.columns:
        return out

    if "close" not in frame.columns:
        if "ltp" in frame.columns:
            frame["close"] = frame["ltp"]
        elif "mark_price" in frame.columns:
            frame["close"] = frame["mark_price"]
        elif "bid" in frame.columns and "ask" in frame.columns:
            frame["close"] = (pd.to_numeric(frame["bid"], errors="coerce") + pd.to_numeric(frame["ask"], errors="coerce")) / 2.0

    if "open" not in frame.columns:
        frame["open"] = frame["close"]
    if "high" not in frame.columns:
        frame["high"] = frame["close"]
    if "low" not in frame.columns:
        frame["low"] = frame["close"]

    frame["time_ms"] = pd.to_numeric(frame.get("time_ms"), errors="coerce")
    frame["open"] = pd.to_numeric(frame.get("open"), errors="coerce")
    frame["high"] = pd.to_numeric(frame.get("high"), errors="coerce")
    frame["low"] = pd.to_numeric(frame.get("low"), errors="coerce")
    frame["close"] = pd.to_numeric(frame.get("close"), errors="coerce")
    frame = frame.dropna(subset=["time_ms", "open", "high", "low", "close"])
    if frame.empty:
        return out
    frame = frame.sort_values("time_ms").drop_duplicates(subset=["time_ms"], keep="last")
    return frame[list(_CANDLE_COLS)]


def _slippage_points(
    *,
    price: float,
    spread_pct: float | None,
    model: str,
    slippage_bps: float,
    spread_slippage_mult: float,
) -> float:
    model_key = str(model or "bps").strip().lower()
    px = max(float(price), 0.0)
    if model_key == "spread":
        sp = _safe_float(spread_pct)
        if sp is not None and sp >= 0:
            return px * float(sp) * float(spread_slippage_mult)
    return px * (float(slippage_bps) / 10000.0)


def _adverse_entry_price(price: float, *, is_sell: bool, slippage_pts: float) -> float:
    if is_sell:
        return float(price) - float(slippage_pts)
    return float(price) + float(slippage_pts)


def _adverse_exit_price(price: float, *, is_sell: bool, slippage_pts: float) -> float:
    if is_sell:
        return float(price) + float(slippage_pts)
    return float(price) - float(slippage_pts)


def _extract_strategy_id(raw: Mapping[str, Any], event: TradeIntentEvent) -> str:
    metrics = event.metrics_snapshot if isinstance(event.metrics_snapshot, Mapping) else {}
    strategy = (
        str(raw.get("strategy_id") or "").strip()
        or str(raw.get("strategy") or "").strip()
        or str(metrics.get("strategy_id") if isinstance(metrics, Mapping) else "").strip()
        or str(metrics.get("strategy") if isinstance(metrics, Mapping) else "").strip()
    )
    if strategy:
        return strategy
    parts = str(event.trade_key or "").split("|")
    if len(parts) >= 6 and str(parts[-1]).strip():
        return str(parts[-1]).strip()
    return "unknown"


def _extract_trade_context(event: TradeIntentEvent, raw: Mapping[str, Any]) -> dict | None:
    metrics = event.metrics_snapshot if isinstance(event.metrics_snapshot, Mapping) else {}

    def _first_float(*values: Any) -> float | None:
        for value in values:
            out = _safe_float(value)
            if out is not None:
                return out
        return None

    side = (
        str(raw.get("side") or "").strip().upper()
        or str(metrics.get("side") if isinstance(metrics, Mapping) else "").strip().upper()
        or str(event.side or "").strip().upper()
        or "BUY"
    )
    is_sell = _is_sell_side(side)

    bid = _first_float(
        raw.get("bid"),
        raw.get("option_bid"),
        metrics.get("bid") if isinstance(metrics, Mapping) else None,
        metrics.get("option_bid") if isinstance(metrics, Mapping) else None,
    )
    ask = _first_float(
        raw.get("ask"),
        raw.get("option_ask"),
        metrics.get("ask") if isinstance(metrics, Mapping) else None,
        metrics.get("option_ask") if isinstance(metrics, Mapping) else None,
    )
    mark = _first_float(
        raw.get("mark_price"),
        raw.get("mark"),
        metrics.get("mark_price") if isinstance(metrics, Mapping) else None,
        metrics.get("mark") if isinstance(metrics, Mapping) else None,
    )
    ltp = _first_float(
        raw.get("ltp"),
        raw.get("option_ltp"),
        raw.get("last_price"),
        metrics.get("ltp") if isinstance(metrics, Mapping) else None,
        metrics.get("option_ltp") if isinstance(metrics, Mapping) else None,
    )
    if mark is None and bid is not None and ask is not None and ask >= bid:
        mark = (float(bid) + float(ask)) / 2.0

    intended_entry = _first_float(
        raw.get("intended_entry"),
        raw.get("entry"),
        raw.get("entry_price"),
        metrics.get("intended_entry") if isinstance(metrics, Mapping) else None,
        metrics.get("entry") if isinstance(metrics, Mapping) else None,
        metrics.get("entry_price") if isinstance(metrics, Mapping) else None,
        mark,
        ltp,
    )
    target_price = _first_float(
        raw.get("target"),
        raw.get("target_price"),
        metrics.get("target") if isinstance(metrics, Mapping) else None,
        metrics.get("target_price") if isinstance(metrics, Mapping) else None,
    )
    stop_price = _first_float(
        raw.get("stop"),
        raw.get("stop_price"),
        raw.get("stop_loss"),
        metrics.get("stop") if isinstance(metrics, Mapping) else None,
        metrics.get("stop_price") if isinstance(metrics, Mapping) else None,
        metrics.get("stop_loss") if isinstance(metrics, Mapping) else None,
    )

    target_points = _first_float(
        raw.get("target_points"),
        metrics.get("target_points") if isinstance(metrics, Mapping) else None,
    )
    stop_points = _first_float(
        raw.get("stop_points"),
        raw.get("stop_distance_points"),
        metrics.get("stop_points") if isinstance(metrics, Mapping) else None,
        metrics.get("stop_distance_points") if isinstance(metrics, Mapping) else None,
    )

    if intended_entry is not None and target_price is None and target_points is not None and target_points > 0:
        target_price = float(intended_entry) - float(target_points) if is_sell else float(intended_entry) + float(target_points)
    if intended_entry is not None and stop_price is None and stop_points is not None and stop_points > 0:
        stop_price = float(intended_entry) + float(stop_points) if is_sell else float(intended_entry) - float(stop_points)

    if intended_entry is None:
        return None
    if target_price is None and stop_price is None:
        return None

    spread_pct = _first_float(
        raw.get("spread_pct"),
        metrics.get("spread_pct") if isinstance(metrics, Mapping) else None,
    )
    if spread_pct is None and bid is not None and ask is not None and mark is not None and mark > 0:
        spread_pct = (float(ask) - float(bid)) / float(mark)

    qty_units = _first_float(
        raw.get("qty_units"),
        raw.get("qty"),
        metrics.get("qty_units") if isinstance(metrics, Mapping) else None,
        metrics.get("qty") if isinstance(metrics, Mapping) else None,
    )
    if qty_units is None or qty_units <= 0:
        qty_units = 1.0

    option_type = (
        str(raw.get("option_type") or "").strip().upper()
        or str(raw.get("type") or "").strip().upper()
        or str(raw.get("right") or "").strip().upper()
        or str(event.option_type or "").strip().upper()
        or None
    )
    if option_type in {"CALL", "C"}:
        option_type = "CE"
    elif option_type in {"PUT", "P"}:
        option_type = "PE"

    return {
        "event_id": event.event_id,
        "trade_key": event.trade_key,
        "symbol": event.symbol,
        "ts_epoch_ms": int(event.ts_epoch_ms),
        "intent": event.intent,
        "side": side,
        "is_sell": is_sell,
        "strategy_id": _extract_strategy_id(raw, event),
        "entry_price": float(intended_entry),
        "target_price": float(target_price) if target_price is not None else None,
        "stop_price": float(stop_price) if stop_price is not None else None,
        "bid": bid,
        "ask": ask,
        "mark_price": mark,
        "ltp": ltp,
        "spread_pct": spread_pct,
        "qty_units": float(qty_units),
        "instrument_token": _safe_int(raw.get("instrument_token") or metrics.get("instrument_token") if isinstance(metrics, Mapping) else None),
        "tradingsymbol": str(raw.get("tradingsymbol") or metrics.get("tradingsymbol") if isinstance(metrics, Mapping) else "").strip() or None,
        "expiry": str(raw.get("expiry_date") or raw.get("expiry") or event.expiry or "").strip() or None,
        "strike": _safe_float(raw.get("strike") if raw.get("strike") is not None else event.strike),
        "option_type": option_type,
    }


def _derive_entry_reference(trade: Mapping[str, Any], *, entry_mode: str) -> float | None:
    is_sell = bool(trade.get("is_sell"))
    bid = _safe_float(trade.get("bid"))
    ask = _safe_float(trade.get("ask"))
    mark = _safe_float(trade.get("mark_price"))
    ltp = _safe_float(trade.get("ltp"))
    entry = _safe_float(trade.get("entry_price"))
    mode = str(entry_mode or "MARK").strip().upper()

    if mode == "SIDE_QUOTE":
        side_px = bid if is_sell else ask
        if side_px is not None and side_px > 0:
            return float(side_px)
        if mark is not None and mark > 0:
            return float(mark)
        if ltp is not None and ltp > 0:
            return float(ltp)
        return entry

    if mark is not None and mark > 0:
        return float(mark)
    side_px = bid if is_sell else ask
    if side_px is not None and side_px > 0:
        return float(side_px)
    if ltp is not None and ltp > 0:
        return float(ltp)
    return entry


def simulate_shadow_trade(
    trade: Mapping[str, Any],
    candles_df: pd.DataFrame,
    *,
    lookahead_minutes: int,
    slippage_model: str,
    slippage_bps: float,
    spread_slippage_mult: float,
    entry_mode: str = "MARK",
) -> dict:
    ctx = dict(trade or {})
    ts_ms = _safe_int(ctx.get("ts_epoch_ms"))
    if ts_ms is None:
        return {"status": "SKIPPED", "skip_reason": "missing_timestamp"}

    entry_ref = _derive_entry_reference(ctx, entry_mode=entry_mode)
    if entry_ref is None or entry_ref <= 0:
        return {"status": "SKIPPED", "skip_reason": "missing_entry_price"}

    target = _safe_float(ctx.get("target_price"))
    stop = _safe_float(ctx.get("stop_price"))
    if target is None and stop is None:
        return {"status": "SKIPPED", "skip_reason": "missing_target_and_stop"}

    qty = _safe_float(ctx.get("qty_units"))
    if qty is None or qty <= 0:
        qty = 1.0

    is_sell = bool(ctx.get("is_sell"))
    side_mult = -1.0 if is_sell else 1.0
    spread_pct = _safe_float(ctx.get("spread_pct"))

    entry_slip = _slippage_points(
        price=float(entry_ref),
        spread_pct=spread_pct,
        model=slippage_model,
        slippage_bps=slippage_bps,
        spread_slippage_mult=spread_slippage_mult,
    )
    entry_exec = _adverse_entry_price(float(entry_ref), is_sell=is_sell, slippage_pts=entry_slip)

    candles = _normalize_candles(candles_df)
    if candles.empty:
        return {"status": "SKIPPED", "skip_reason": "no_candles", "entry_exec_price": entry_exec}

    end_ms = int(ts_ms + (max(int(lookahead_minutes), 1) * 60 * 1000))
    window = candles[(candles["time_ms"] >= float(ts_ms)) & (candles["time_ms"] <= float(end_ms))]
    if window.empty:
        return {"status": "SKIPPED", "skip_reason": "no_candles_in_window", "entry_exec_price": entry_exec}

    exit_reason = "TIME_EXPIRY"
    exit_raw = _safe_float(window.iloc[-1]["close"])
    exit_ts_ms = _safe_int(window.iloc[-1]["time_ms"]) or end_ms
    target_hit = False
    stop_hit = False

    for _, row in window.iterrows():
        candle_high = _safe_float(row.get("high"))
        candle_low = _safe_float(row.get("low"))
        candle_ts = _safe_int(row.get("time_ms"))
        if candle_high is None or candle_low is None or candle_ts is None:
            continue

        if is_sell:
            hit_target = bool(target is not None and candle_low <= float(target))
            hit_stop = bool(stop is not None and candle_high >= float(stop))
        else:
            hit_target = bool(target is not None and candle_high >= float(target))
            hit_stop = bool(stop is not None and candle_low <= float(stop))

        if hit_target and hit_stop:
            # Conservative same-candle resolution: assume adverse fill first.
            exit_reason = "STOP_HIT_AMBIGUOUS"
            exit_raw = float(stop) if stop is not None else _safe_float(row.get("close"))
            exit_ts_ms = int(candle_ts)
            stop_hit = True
            break
        if hit_target:
            exit_reason = "TARGET_HIT"
            exit_raw = float(target) if target is not None else _safe_float(row.get("close"))
            exit_ts_ms = int(candle_ts)
            target_hit = True
            break
        if hit_stop:
            exit_reason = "STOP_HIT"
            exit_raw = float(stop) if stop is not None else _safe_float(row.get("close"))
            exit_ts_ms = int(candle_ts)
            stop_hit = True
            break

    if exit_raw is None:
        return {"status": "SKIPPED", "skip_reason": "invalid_exit_price", "entry_exec_price": entry_exec}

    exit_slip = _slippage_points(
        price=float(exit_raw),
        spread_pct=spread_pct,
        model=slippage_model,
        slippage_bps=slippage_bps,
        spread_slippage_mult=spread_slippage_mult,
    )
    exit_exec = _adverse_exit_price(float(exit_raw), is_sell=is_sell, slippage_pts=exit_slip)

    pnl_points = (float(exit_exec) - float(entry_exec)) * float(side_mult)
    pnl_value = float(pnl_points) * float(qty)
    duration_sec = max(0.0, (float(exit_ts_ms) - float(ts_ms)) / 1000.0)

    return {
        "status": "SIMULATED",
        "entry_ref_price": float(entry_ref),
        "entry_exec_price": float(entry_exec),
        "exit_ref_price": float(exit_raw),
        "exit_exec_price": float(exit_exec),
        "exit_reason": exit_reason,
        "target_hit": bool(target_hit),
        "stop_hit": bool(stop_hit),
        "duration_sec": float(duration_sec),
        "pnl_points": float(pnl_points),
        "pnl_value": float(pnl_value),
        "qty_units": float(qty),
        "exit_ts_ms": int(exit_ts_ms),
    }


def _default_candle_provider(trade: Mapping[str, Any], start_ms: int, end_ms: int, interval: str) -> pd.DataFrame:
    try:
        from core.market_data import get_option_candles_or_snapshots
    except Exception:
        return pd.DataFrame()
    trade_row = {
        "instrument_token": trade.get("instrument_token"),
        "tradingsymbol": trade.get("tradingsymbol"),
        "symbol": trade.get("symbol"),
    }
    return get_option_candles_or_snapshots(trade_row, interval, int(start_ms), int(end_ms))


def _shadow_portfolio_runtime_params(
    *,
    lookahead_minutes: int | None,
    interval: str | None,
    entry_mode: str | None,
    slippage_model: str | None,
    slippage_bps: float | None,
    spread_slippage_mult: float | None,
    starting_equity: float | None,
    lookahead_key: str = "SHADOW_PORTFOLIO_LOOKAHEAD_MINUTES",
    interval_key: str = "SHADOW_PORTFOLIO_INTERVAL",
    entry_mode_key: str = "SHADOW_PORTFOLIO_ENTRY_MODE",
    slippage_model_key: str = "SHADOW_PORTFOLIO_SLIPPAGE_MODEL",
    slippage_bps_key: str = "SHADOW_PORTFOLIO_SLIPPAGE_BPS",
    spread_mult_key: str = "SHADOW_PORTFOLIO_SPREAD_SLIPPAGE_MULT",
    starting_equity_key: str = "SHADOW_PORTFOLIO_STARTING_EQUITY",
) -> dict[str, float | int | str]:
    return {
        "lookahead": max(1, int(lookahead_minutes if lookahead_minutes is not None else getattr(cfg, lookahead_key, 30))),
        "interval": str(interval or getattr(cfg, interval_key, "minute")).strip() or "minute",
        "entry_mode": str(entry_mode or getattr(cfg, entry_mode_key, "MARK")).strip().upper(),
        "slippage_model": str(slippage_model or getattr(cfg, slippage_model_key, "bps")).strip().lower(),
        "slippage_bps": float(slippage_bps if slippage_bps is not None else getattr(cfg, slippage_bps_key, 0.0)),
        "spread_mult": float(
            spread_slippage_mult
            if spread_slippage_mult is not None
            else getattr(cfg, spread_mult_key, 0.5)
        ),
        "starting_equity": float(
            starting_equity if starting_equity is not None else getattr(cfg, starting_equity_key, 100000.0)
        ),
    }


def _equity_summary(rows: Sequence[Mapping[str, Any]], *, starting_equity: float) -> tuple[list[dict], dict]:
    ordered = sorted(
        [row for row in rows if str(row.get("status") or "") == "SIMULATED"],
        key=lambda row: (int(row.get("exit_ts_ms") or row.get("ts_epoch_ms") or 0), str(row.get("event_id") or "")),
    )
    equity = float(starting_equity)
    peak = float(starting_equity)
    max_dd_points = 0.0
    max_dd_pct = 0.0
    curve: list[dict] = []

    for row in ordered:
        pnl = float(_safe_float(row.get("pnl_value")) or 0.0)
        equity += pnl
        if equity > peak:
            peak = equity
        dd_points = max(0.0, peak - equity)
        dd_pct = (dd_points / peak) if peak > 0 else 0.0
        if dd_points > max_dd_points:
            max_dd_points = dd_points
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
        curve.append(
            {
                "event_id": row.get("event_id"),
                "ts_epoch_ms": int(row.get("exit_ts_ms") or row.get("ts_epoch_ms") or 0),
                "equity": float(equity),
                "cum_pnl": float(equity - float(starting_equity)),
                "drawdown_points": float(dd_points),
                "drawdown_pct": float(dd_pct),
            }
        )

    return curve, {"max_drawdown_points": float(max_dd_points), "max_drawdown_pct": float(max_dd_pct), "ending_equity": float(equity)}


def _stats(rows: Sequence[Mapping[str, Any]]) -> dict:
    simulated = [row for row in rows if str(row.get("status") or "") == "SIMULATED"]
    count = len(simulated)
    wins = sum(1 for row in simulated if float(_safe_float(row.get("pnl_value")) or 0.0) > 0.0)
    losses = sum(1 for row in simulated if float(_safe_float(row.get("pnl_value")) or 0.0) < 0.0)
    flats = count - wins - losses
    target_hits = sum(1 for row in simulated if bool(row.get("target_hit")))
    stop_hits = sum(1 for row in simulated if bool(row.get("stop_hit")))
    total_pnl_value = sum(float(_safe_float(row.get("pnl_value")) or 0.0) for row in simulated)
    total_pnl_points = sum(float(_safe_float(row.get("pnl_points")) or 0.0) for row in simulated)

    return {
        "trades": count,
        "wins": wins,
        "losses": losses,
        "flats": flats,
        "hit_rate": (float(target_hits) / float(count)) if count > 0 else 0.0,
        "win_rate": (float(wins) / float(count)) if count > 0 else 0.0,
        "stop_hit_rate": (float(stop_hits) / float(count)) if count > 0 else 0.0,
        "total_pnl_value": float(total_pnl_value),
        "total_pnl_points": float(total_pnl_points),
        "avg_pnl_value": (float(total_pnl_value) / float(count)) if count > 0 else 0.0,
    }


def _build_shadow_portfolio_report_payload(
    date_key: str,
    *,
    event_rows: Sequence[TradeIntentEvent | Mapping[str, Any]],
    scanned_events: int,
    lookahead_minutes: int | None = None,
    interval: str | None = None,
    entry_mode: str | None = None,
    slippage_model: str | None = None,
    slippage_bps: float | None = None,
    spread_slippage_mult: float | None = None,
    starting_equity: float | None = None,
    candle_provider: Callable[[Mapping[str, Any], int, int, str], pd.DataFrame] | None = None,
    output_path: Path | None = None,
    scope: str = "trade_intent",
) -> dict:
    params = _shadow_portfolio_runtime_params(
        lookahead_minutes=lookahead_minutes,
        interval=interval,
        entry_mode=entry_mode,
        slippage_model=slippage_model,
        slippage_bps=slippage_bps,
        spread_slippage_mult=spread_slippage_mult,
        starting_equity=starting_equity,
    )
    lookahead = int(params["lookahead"])
    iv = str(params["interval"])
    entry_px_mode = str(params["entry_mode"])
    slip_model = str(params["slippage_model"])
    slip_bps = float(params["slippage_bps"])
    spread_mult = float(params["spread_mult"])
    initial_equity = float(params["starting_equity"])
    provider = candle_provider or _default_candle_provider

    rows: list[dict] = []
    eligible_events = 0

    for item in event_rows:
        coerced = _coerce_event(item)
        if coerced is None:
            continue
        event, raw = coerced
        if _to_day_key(int(event.ts_epoch_ms)) != date_key:
            continue

        trade = _extract_trade_context(event, raw)
        if trade is None:
            rows.append(
                {
                    "event_id": event.event_id,
                    "trade_key": event.trade_key,
                    "symbol": event.symbol,
                    "strategy_id": _extract_strategy_id(raw, event),
                    "status": "SKIPPED",
                    "skip_reason": "missing_trade_levels",
                    "ts_epoch_ms": int(event.ts_epoch_ms),
                    "intent": event.intent,
                    "fill_kind": "simulated_entry",
                    "simulation_scope": scope,
                }
            )
            continue

        eligible_events += 1
        start_ms = int(trade["ts_epoch_ms"])
        end_ms = int(start_ms + (lookahead * 60 * 1000))
        candles = provider(trade, start_ms, end_ms, iv)
        sim = simulate_shadow_trade(
            trade,
            candles,
            lookahead_minutes=lookahead,
            slippage_model=slip_model,
            slippage_bps=slip_bps,
            spread_slippage_mult=spread_mult,
            entry_mode=entry_px_mode,
        )
        row = {
            "event_id": trade["event_id"],
            "trade_key": trade["trade_key"],
            "symbol": trade["symbol"],
            "strategy_id": trade["strategy_id"],
            "intent": trade["intent"],
            "side": trade["side"],
            "ts_epoch_ms": int(trade["ts_epoch_ms"]),
            "entry_price": trade["entry_price"],
            "target_price": trade["target_price"],
            "stop_price": trade["stop_price"],
            "spread_pct": trade["spread_pct"],
            "status": sim.get("status"),
            "skip_reason": sim.get("skip_reason"),
            "entry_ref_price": sim.get("entry_ref_price"),
            "entry_exec_price": sim.get("entry_exec_price"),
            "exit_ref_price": sim.get("exit_ref_price"),
            "exit_exec_price": sim.get("exit_exec_price"),
            "exit_reason": sim.get("exit_reason"),
            "target_hit": bool(sim.get("target_hit")),
            "stop_hit": bool(sim.get("stop_hit")),
            "duration_sec": sim.get("duration_sec"),
            "qty_units": sim.get("qty_units"),
            "pnl_points": sim.get("pnl_points"),
            "pnl_value": sim.get("pnl_value"),
            "exit_ts_ms": sim.get("exit_ts_ms"),
            "fill_kind": "simulated_entry",
            "simulation_scope": scope,
        }
        rows.append(row)

    rows.sort(key=lambda row: (int(row.get("ts_epoch_ms") or 0), str(row.get("event_id") or "")))
    equity_curve, dd = _equity_summary(rows, starting_equity=initial_equity)
    summary = _stats(rows)
    summary["starting_equity"] = float(initial_equity)
    summary["ending_equity"] = float(dd["ending_equity"])
    summary["max_drawdown_points"] = float(dd["max_drawdown_points"])
    summary["max_drawdown_pct"] = float(dd["max_drawdown_pct"])
    skip_reasons = Counter(
        str(row.get("skip_reason") or "unknown")
        for row in rows
        if str(row.get("status") or "") != "SIMULATED"
    )

    by_strategy: dict[str, list[dict]] = {}
    for row in rows:
        key = str(row.get("strategy_id") or "unknown")
        by_strategy.setdefault(key, []).append(row)

    strategy_breakdown: list[dict] = []
    for strategy_id, srows in sorted(by_strategy.items(), key=lambda item: item[0]):
        stats = _stats(srows)
        stats["strategy_id"] = strategy_id
        strategy_breakdown.append(stats)

    report = {
        "date": date_key,
        "generated_ts_epoch": datetime.now(tz=timezone.utc).timestamp(),
        "scope": scope,
        "params": {
            "scope": scope,
            "lookahead_minutes": int(lookahead),
            "interval": iv,
            "entry_mode": entry_px_mode,
            "slippage_model": slip_model,
            "slippage_bps": float(slip_bps),
            "spread_slippage_mult": float(spread_mult),
            "starting_equity": float(initial_equity),
        },
        "counts": {
            "scanned_events": int(scanned_events),
            "eligible_events": int(eligible_events),
            "simulated_trades": int(summary["trades"]),
            "skipped_events": int(len([row for row in rows if str(row.get("status")) != "SIMULATED"])),
        },
        "summary": summary,
        "skip_reasons": dict(sorted(skip_reasons.items())),
        "equity_curve": equity_curve,
        "per_strategy": strategy_breakdown,
        "rows": rows,
    }

    out_path = Path(output_path) if output_path is not None else _default_report_path(date_key)
    _atomic_write_json(out_path, report)
    report["output_path"] = str(out_path)
    return report


def build_shadow_portfolio_report(
    date: Any,
    *,
    events: Sequence[TradeIntentEvent | Mapping[str, Any]] | None = None,
    include_advisory: bool = True,
    include_rejected: bool = False,
    lookahead_minutes: int | None = None,
    interval: str | None = None,
    entry_mode: str | None = None,
    slippage_model: str | None = None,
    slippage_bps: float | None = None,
    spread_slippage_mult: float | None = None,
    starting_equity: float | None = None,
    candle_provider: Callable[[Mapping[str, Any], int, int, str], pd.DataFrame] | None = None,
    output_path: Path | None = None,
) -> dict:
    date_key = _parse_date_key(date)
    event_rows = list(events) if events is not None else list(load_trade_intent_events())
    scanned_events = 0
    selected_events: list[TradeIntentEvent | Mapping[str, Any]] = []
    for item in event_rows:
        coerced = _coerce_event(item)
        if coerced is None:
            continue
        event, _ = coerced
        if _to_day_key(int(event.ts_epoch_ms)) != date_key:
            continue
        scanned_events += 1
        intent = str(event.intent or "").strip().lower()
        allowed = (include_advisory and intent == "advisory") or (include_rejected and intent == "rejected")
        if allowed:
            selected_events.append(item)

    return _build_shadow_portfolio_report_payload(
        date_key,
        event_rows=selected_events,
        scanned_events=scanned_events,
        lookahead_minutes=lookahead_minutes,
        interval=interval,
        entry_mode=entry_mode,
        slippage_model=slippage_model,
        slippage_bps=slippage_bps,
        spread_slippage_mult=spread_slippage_mult,
        starting_equity=starting_equity,
        candle_provider=candle_provider,
        output_path=output_path,
        scope="trade_intent",
    )


def build_executable_shadow_portfolio_report(
    date: Any,
    *,
    review_queue_paths: Sequence[Path] | None = None,
    lookahead_minutes: int | None = None,
    interval: str | None = None,
    entry_mode: str | None = None,
    slippage_model: str | None = None,
    slippage_bps: float | None = None,
    spread_slippage_mult: float | None = None,
    starting_equity: float | None = None,
    candle_provider: Callable[[Mapping[str, Any], int, int, str], pd.DataFrame] | None = None,
    output_path: Path | None = None,
) -> dict:
    date_key = _parse_date_key(date)
    event_rows = list(load_executable_review_queue_events(paths=review_queue_paths))
    scanned_events = 0
    selected_events: list[TradeIntentEvent | Mapping[str, Any]] = []
    for item in event_rows:
        coerced = _coerce_event(item)
        if coerced is None:
            continue
        event, _ = coerced
        if _to_day_key(int(event.ts_epoch_ms)) != date_key:
            continue
        scanned_events += 1
        selected_events.append(item)

    params = _shadow_portfolio_runtime_params(
        lookahead_minutes=lookahead_minutes,
        interval=interval,
        entry_mode=entry_mode,
        slippage_model=slippage_model,
        slippage_bps=slippage_bps,
        spread_slippage_mult=spread_slippage_mult,
        starting_equity=starting_equity,
        lookahead_key="EXECUTABLE_SHADOW_PORTFOLIO_LOOKAHEAD_MINUTES",
        interval_key="EXECUTABLE_SHADOW_PORTFOLIO_INTERVAL",
        entry_mode_key="EXECUTABLE_SHADOW_PORTFOLIO_ENTRY_MODE",
        slippage_model_key="EXECUTABLE_SHADOW_PORTFOLIO_SLIPPAGE_MODEL",
        slippage_bps_key="EXECUTABLE_SHADOW_PORTFOLIO_SLIPPAGE_BPS",
        spread_mult_key="EXECUTABLE_SHADOW_PORTFOLIO_SPREAD_SLIPPAGE_MULT",
        starting_equity_key="EXECUTABLE_SHADOW_PORTFOLIO_STARTING_EQUITY",
    )
    out_path = output_path or _default_executable_report_path(date_key)
    return _build_shadow_portfolio_report_payload(
        date_key,
        event_rows=selected_events,
        scanned_events=scanned_events,
        lookahead_minutes=int(params["lookahead"]),
        interval=str(params["interval"]),
        entry_mode=str(params["entry_mode"]),
        slippage_model=str(params["slippage_model"]),
        slippage_bps=float(params["slippage_bps"]),
        spread_slippage_mult=float(params["spread_mult"]),
        starting_equity=float(params["starting_equity"]),
        candle_provider=candle_provider,
        output_path=out_path,
        scope="executable_review_queue",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Shadow portfolio simulator for advisory/rejected events.")
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD (exchange day).")
    parser.add_argument("--include-rejected", action="store_true", help="Include rejected events in simulation.")
    parser.add_argument("--exclude-advisory", action="store_true", help="Exclude advisory events from simulation.")
    parser.add_argument("--lookahead-min", type=int, default=None, help="Exit time-expiry horizon in minutes.")
    parser.add_argument("--interval", default=None, help="Candle interval (default from config).")
    parser.add_argument("--entry-mode", choices=["MARK", "SIDE_QUOTE"], default=None, help="Entry price reference mode.")
    parser.add_argument("--slippage-model", choices=["bps", "spread"], default=None, help="Slippage model.")
    parser.add_argument("--slippage-bps", type=float, default=None, help="Slippage in bps for bps model.")
    parser.add_argument("--spread-slippage-mult", type=float, default=None, help="Spread multiplier for spread model.")
    parser.add_argument("--starting-equity", type=float, default=None, help="Initial equity for curve.")
    parser.add_argument("--output", default=None, help="Optional output path override.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    output_path = Path(args.output) if args.output else None
    payload = build_shadow_portfolio_report(
        args.date,
        include_advisory=not bool(args.exclude_advisory),
        include_rejected=bool(args.include_rejected),
        lookahead_minutes=args.lookahead_min,
        interval=args.interval,
        entry_mode=args.entry_mode,
        slippage_model=args.slippage_model,
        slippage_bps=args.slippage_bps,
        spread_slippage_mult=args.spread_slippage_mult,
        starting_equity=args.starting_equity,
        output_path=output_path,
    )
    print(
        json.dumps(
            {
                "date": payload.get("date"),
                "summary": payload.get("summary"),
                "counts": payload.get("counts"),
                "output_path": payload.get("output_path"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
