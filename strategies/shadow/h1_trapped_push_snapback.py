#!/usr/bin/env python3
"""H1 Trapped Push Snapback shadow trade-intent strategy.

This is deliberately not an execution strategy. It converts the frozen H1
opening-window index micro-pattern into shadow-only trade-intent records so the
candidate can be measured inside TradeBot without broker writes, paper orders,
or live orders.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

STRATEGY_ID = "H1_TRAPPED_PUSH_SNAPBACK_SHADOW"
CANDIDATE_ID = "H1_TRAPPED_PUSH_SNAPBACK"
FROZEN_PREDICATE_VERSION = "H1_V14_FROZEN"
FROZEN_PREDICATE = "(range_bps[t-1] > 12.0) & (upper_wick_bps[t-1] > 4.0) & (body_bps[t] < -2.0)"
SUPPORT_SCOPE = "OPENING_WINDOW_5MIN_OHLC_INDEX_BPS"
SHADOW_EMISSION_MODE = "SHADOW_TRADE_INTENT_ONLY_NO_ORDER"
DEFAULT_OPENING_START = "09:15"
DEFAULT_OPENING_END = "11:30"
DEFAULT_HORIZON_BARS = 6


@dataclass(frozen=True)
class H1ShadowIntentConfig:
    opening_start: str = DEFAULT_OPENING_START
    opening_end: str = DEFAULT_OPENING_END
    horizon_bars: int = DEFAULT_HORIZON_BARS
    market_timezone: str = "Asia/Kolkata"

    def validate(self) -> None:
        if self.horizon_bars <= 0:
            raise ValueError("H1 shadow horizon_bars must be positive")
        if self.opening_start > self.opening_end:
            raise ValueError("H1 shadow opening_start must be <= opening_end")


def _coerce_ist_timestamp_series(frame: pd.DataFrame, market_timezone: str) -> pd.Series:
    timestamp_column = "datetime" if "datetime" in frame.columns else "timestamp"
    if timestamp_column not in frame.columns:
        raise ValueError("H1 shadow strategy requires datetime or timestamp column")
    parsed = pd.to_datetime(frame[timestamp_column], errors="coerce")
    if parsed.isna().any():
        raise ValueError("H1 shadow strategy received unparseable timestamps")
    if parsed.dt.tz is None:
        return parsed.dt.tz_localize(market_timezone)
    return parsed.dt.tz_convert(market_timezone)


def _ensure_features(frame: pd.DataFrame) -> pd.DataFrame:
    required = ["open", "high", "low", "close"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"H1 shadow strategy missing OHLC columns: {missing}")
    out = frame.copy()
    for column in required:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    if out[required].isna().any(axis=1).any():
        raise ValueError("H1 shadow strategy received non-numeric OHLC values")
    if "range_bps" not in out.columns:
        out["range_bps"] = ((out["high"] - out["low"]) / out["open"]) * 10000.0
    if "upper_wick_bps" not in out.columns:
        out["upper_wick_bps"] = ((out["high"] - out[["open", "close"]].max(axis=1)) / out["open"]) * 10000.0
    if "body_bps" not in out.columns:
        out["body_bps"] = ((out["close"] - out["open"]) / out["open"]) * 10000.0
    return out


def _h1_trigger_mask(frame: pd.DataFrame, timestamps_ist: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    session_dates = timestamps_ist.dt.date
    range_t1 = frame.groupby(session_dates)["range_bps"].shift(1)
    wick_t1 = frame.groupby(session_dates)["upper_wick_bps"].shift(1)
    trigger = (range_t1 > 12.0) & (wick_t1 > 4.0) & (frame["body_bps"] < -2.0)
    return trigger, range_t1, wick_t1


def generate_h1_shadow_trade_intents(
    bars: pd.DataFrame,
    *,
    config: H1ShadowIntentConfig | None = None,
    run_id: str = "H1_SHADOW_UNBOUND_RUN",
    source_file_or_feed: str = "UNKNOWN",
) -> list[dict[str, Any]]:
    """Emit BUY_PUT shadow trade intents from completed NIFTY index bars.

    Returned records are measurement-only. They intentionally do not include
    order ids, broker ids, lot sizes, order type, product type, or routeable
    instrument tokens.
    """

    cfg = config or H1ShadowIntentConfig()
    cfg.validate()

    frame = _ensure_features(bars).reset_index(drop=True)
    timestamps_ist = _coerce_ist_timestamp_series(frame, cfg.market_timezone)
    timestamps_utc = timestamps_ist.dt.tz_convert("UTC")
    time_hhmm = timestamps_ist.dt.strftime("%H:%M")
    in_opening_scope = (time_hhmm >= cfg.opening_start) & (time_hhmm <= cfg.opening_end)
    trigger_mask, range_t1, wick_t1 = _h1_trigger_mask(frame, timestamps_ist)

    intents: list[dict[str, Any]] = []
    close_values = frame["close"].to_numpy()
    high_values = frame["high"].to_numpy()
    low_values = frame["low"].to_numpy()

    for idx, is_trigger in enumerate((trigger_mask & in_opening_scope).fillna(False).tolist()):
        if not bool(is_trigger):
            continue

        entry_close = float(close_values[idx])
        outcome_available = idx + cfg.horizon_bars < len(frame)
        exit_close = None
        down_ret_bps = None
        max_adverse_excursion_bps = None
        max_favorable_excursion_bps = None
        if outcome_available:
            future_slice = slice(idx + 1, idx + cfg.horizon_bars + 1)
            exit_close = float(close_values[idx + cfg.horizon_bars])
            down_ret_bps = -((exit_close - entry_close) / entry_close) * 10000.0
            max_adverse_excursion_bps = float(((high_values[future_slice].max() - entry_close) / entry_close) * 10000.0)
            max_favorable_excursion_bps = float(((entry_close - low_values[future_slice].min()) / entry_close) * 10000.0)

        intents.append(
            {
                "schema_version": "H1_SHADOW_TRADE_INTENT_V1",
                "strategy_id": STRATEGY_ID,
                "candidate_id": CANDIDATE_ID,
                "run_id": run_id,
                "bar_index": int(idx),
                "timestamp_ist": timestamps_ist.iloc[idx].strftime("%Y-%m-%dT%H:%M:%S%z"),
                "timestamp_utc": timestamps_utc.iloc[idx].strftime("%Y-%m-%dT%H:%M:%S%z"),
                "source_file_or_feed": str(source_file_or_feed),
                "emission_mode": SHADOW_EMISSION_MODE,
                "shadow_trade_action": "BUY_PUT_SHADOW",
                "underlying": "NIFTY",
                "instrument_family": "INDEX_OPTION_SHADOW_INTENT_UNROUTED",
                "routeable_order": False,
                "completed_bar_only": True,
                "frozen_predicate_version": FROZEN_PREDICATE_VERSION,
                "frozen_predicate": FROZEN_PREDICATE,
                "predicate_changed": False,
                "support_scope": SUPPORT_SCOPE,
                "opening_scope_window": f"{cfg.opening_start}-{cfg.opening_end} IST",
                "horizon_bars": int(cfg.horizon_bars),
                "entry_reference": "UNDERLYING_INDEX_CLOSE",
                "entry_close": entry_close,
                "exit_close_horizon": exit_close,
                "down_ret_horizon_bps": None if down_ret_bps is None else float(down_ret_bps),
                "max_adverse_excursion_bps": max_adverse_excursion_bps,
                "max_favorable_excursion_bps": max_favorable_excursion_bps,
                "outcome_status": "OUTCOME_AVAILABLE" if outcome_available else "OUTCOME_PENDING_INSUFFICIENT_FUTURE_BARS",
                "range_bps_t1": float(range_t1.iloc[idx]),
                "upper_wick_bps_t1": float(wick_t1.iloc[idx]),
                "body_bps_t": float(frame["body_bps"].iloc[idx]),
                "orders_created": 0,
                "broker_writes_created": 0,
                "paper_authorized": False,
                "live_authorized": False,
                "order_authority": False,
                "broker_write_authority": False,
                "execution_viable": False,
                "structural_edge_certified": False,
                "edge_claimed": False,
            }
        )

    return intents


def write_h1_shadow_trade_intents(
    bars_csv_path: str | Path,
    output_jsonl_path: str | Path,
    *,
    config: H1ShadowIntentConfig | None = None,
    run_id: str = "H1_SHADOW_UNBOUND_RUN",
) -> dict[str, Any]:
    bars_path = Path(bars_csv_path)
    output_path = Path(output_jsonl_path)
    bars = pd.read_csv(bars_path)
    intents = generate_h1_shadow_trade_intents(
        bars,
        config=config,
        run_id=run_id,
        source_file_or_feed=str(bars_path),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(json.dumps(intent, sort_keys=True) + "\n" for intent in intents), encoding="utf-8")
    return {
        "schema_version": "H1_SHADOW_TRADE_INTENT_WRITE_AUDIT_V1",
        "strategy_id": STRATEGY_ID,
        "candidate_id": CANDIDATE_ID,
        "input_bars_csv": str(bars_path),
        "output_jsonl": str(output_path),
        "intents_emitted": int(len(intents)),
        "orders_created": 0,
        "broker_writes_created": 0,
        "paper_authorized": False,
        "live_authorized": False,
        "order_authority": False,
        "broker_write_authority": False,
        "execution_viable": False,
        "structural_edge_certified": False,
        "edge_claimed": False,
    }


# Compatibility callable for StrategyRegistryEntry.
def generate_shadow_trade_intents(bars: pd.DataFrame, **kwargs: Any) -> list[dict[str, Any]]:
    return generate_h1_shadow_trade_intents(bars, **kwargs)
