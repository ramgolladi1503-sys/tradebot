from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import pandas as pd

from .data import bar_payload, prepare_features
from .models import HistoricalCampaignConfig


def simulate_trade(
    session: pd.DataFrame,
    signal_index: int,
    *,
    direction: str,
    anchor: float,
    atr: float,
    config: HistoricalCampaignConfig,
) -> dict[str, Any] | None:
    entry_index = signal_index + 1
    if entry_index >= len(session):
        return None
    entry_row = session.iloc[entry_index]
    entry = float(entry_row["open"])
    if direction == "BUY_CALL":
        stop = anchor - config.stop_atr_buffer * atr
        risk = entry - stop
        target = entry + config.target_rr * risk
    else:
        stop = anchor + config.stop_atr_buffer * atr
        risk = stop - entry
        target = entry - config.target_rr * risk
    if not math.isfinite(risk) or risk <= 0 or risk / entry > 0.02:
        return None
    last_index = min(len(session) - 1, entry_index + config.max_hold_bars - 1)
    exit_price = float(session.iloc[last_index]["close"])
    exit_reason = "TIMEOUT"
    exit_index = last_index
    for index in range(entry_index, last_index + 1):
        row = session.iloc[index]
        stop_hit = float(row["low"]) <= stop if direction == "BUY_CALL" else float(row["high"]) >= stop
        target_hit = float(row["high"]) >= target if direction == "BUY_CALL" else float(row["low"]) <= target
        if stop_hit:
            exit_price = stop
            exit_index = index
            exit_reason = "STOP_AND_TARGET_SAME_BAR_STOP_FIRST" if target_hit else "STOP"
            break
        if target_hit:
            exit_price = target
            exit_reason = "TARGET"
            exit_index = index
            break
    gross = ((exit_price - entry) / entry) * 10000.0
    if direction == "BUY_PUT":
        gross = -gross
    return {
        "entry_index": entry_index,
        "exit_index": exit_index,
        "entry_timestamp": pd.Timestamp(entry_row["timestamp"]).isoformat(),
        "exit_timestamp": pd.Timestamp(session.iloc[exit_index]["timestamp"]).isoformat(),
        "entry_price": entry,
        "exit_price": exit_price,
        "stop_price": stop,
        "target_price": target,
        "gross_return_bps": gross,
        "net_return_bps": gross - config.round_trip_cost_bps,
        "exit_reason": exit_reason,
        "hold_bars": exit_index - entry_index + 1,
    }


def _necessary_structure(
    history: pd.DataFrame,
    *,
    spot: float,
    vwap: float,
) -> tuple[bool, bool, float, float]:
    first, second, pullback, trigger = [history.iloc[index] for index in range(4)]
    support = float(history.iloc[-2:]["low"].min())
    resistance = float(history.iloc[-2:]["high"].max())
    call_distance = abs(spot - support) / abs(support) if support > 0 else math.inf
    put_distance = abs(spot - resistance) / abs(resistance) if resistance > 0 else math.inf
    call_possible = bool(
        float(first["close"]) < float(second["close"])
        and float(second["close"]) >= vwap
        and spot >= support
        and spot >= vwap
        and call_distance <= 0.0035
        and float(second["close"]) > float(pullback["close"])
        and float(pullback["close"]) >= support
        and float(trigger["close"]) >= support
        and float(pullback["close"]) < float(trigger["close"])
        and float(trigger["close"]) >= vwap
        and (spot - support) / abs(support) >= 0.0004
    )
    put_possible = bool(
        float(first["close"]) > float(second["close"])
        and float(second["close"]) <= vwap
        and spot <= resistance
        and spot <= vwap
        and put_distance <= 0.0035
        and float(second["close"]) < float(pullback["close"])
        and float(pullback["close"]) <= resistance
        and float(trigger["close"]) <= resistance
        and float(pullback["close"]) > float(trigger["close"])
        and float(trigger["close"]) <= vwap
        and (resistance - spot) / abs(resistance) >= 0.0004
    )
    return call_possible, put_possible, support, resistance


def generate_trades(
    frame: pd.DataFrame,
    config: HistoricalCampaignConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from core.movement_contract import StrategyContext
    from core.movement_regime import MovementRegimeClassifier
    from strategies.movement.trend_pullback import generate_trend_pullback_candidates

    prepared = prepare_features(frame, timezone=config.timezone)
    classifier = MovementRegimeClassifier()
    trades: list[dict[str, Any]] = []
    signal_count = 0
    blocked_geometry = 0
    blocked_data_gap = 0
    prefilter_checkpoints = 0
    seen_setup_ids: set[str] = set()

    for session_date, session in prepared.groupby("session_date", sort=True):
        session = session.sort_values("timestamp").reset_index(drop=True)
        if float(session["volume"].sum()) <= 0:
            continue
        timestamps = pd.to_datetime(session["timestamp"])
        gap_flags = timestamps.diff().ne(pd.Timedelta(minutes=1)).astype(int)
        gap_flags.iloc[0] = 0
        gap_prefix = gap_flags.cumsum().to_numpy()
        start_ts = pd.Timestamp(session.iloc[0]["timestamp"])
        next_available_index = 0

        for index in range(30, len(session) - 1):
            if index < next_available_index:
                continue
            row = session.iloc[index]
            if any(pd.isna(row.get(name)) for name in ("vwap", "atr", "atr_short", "atr_long", "vwap_slope")):
                continue
            history = session.iloc[index - 3 : index + 1]
            spot = float(row["close"])
            vwap = float(row["vwap"])
            call_possible, put_possible, support, resistance = _necessary_structure(
                history,
                spot=spot,
                vwap=vwap,
            )
            if not call_possible and not put_possible:
                continue
            prefilter_checkpoints += 1

            path_start = index - 3
            path_end = min(len(session) - 1, index + config.max_hold_bars)
            if int(gap_prefix[path_end] - gap_prefix[path_start]) > 0:
                blocked_data_gap += 1
                continue

            current_ts = pd.Timestamp(row["timestamp"])
            ctx = StrategyContext(
                symbol=config.symbol,
                ts_epoch=(current_ts + pd.Timedelta(minutes=1)).timestamp(),
                spot_ltp=spot,
                open_price=float(session.iloc[0]["open"]),
                vwap=vwap,
                vwap_slope=float(row["vwap_slope"]),
                day_high=float(row["day_high"]),
                day_low=float(row["day_low"]),
                orb_high=float(row["orb_high"]) if not pd.isna(row["orb_high"]) else None,
                orb_low=float(row["orb_low"]) if not pd.isna(row["orb_low"]) else None,
                previous_completed_close=float(history.iloc[-2]["close"]),
                nearest_support=support,
                nearest_resistance=resistance,
                completed_bar_history=[
                    bar_payload(bar, timezone=config.timezone)
                    for _, bar in history.iterrows()
                ],
                atr=float(row["atr"]),
                atr_short=float(row["atr_short"]),
                atr_long=float(row["atr_long"]),
                range_width_pct=float(row["range_width_pct"])
                if not pd.isna(row["range_width_pct"])
                else None,
                volume_z=float(row["volume_z"])
                if not pd.isna(row["volume_z"])
                else None,
                time_of_day=current_ts.strftime("%H:%M"),
                minutes_since_open=int((current_ts - start_ts).total_seconds() // 60),
                metadata={"historical_campaign": True, "source": "aeron7_nifty_futures"},
            )
            regime = classifier.classify(ctx)
            for candidate in generate_trend_pullback_candidates(ctx, regime):
                if candidate.direction == "BUY_CALL" and not call_possible:
                    continue
                if candidate.direction == "BUY_PUT" and not put_possible:
                    continue
                identity = candidate.evidence.get("setup_identity") or {}
                setup_id = hashlib.sha256(
                    json.dumps(identity, sort_keys=True).encode()
                ).hexdigest()
                if setup_id in seen_setup_ids:
                    continue
                seen_setup_ids.add(setup_id)
                signal_count += 1
                anchor = support if candidate.direction == "BUY_CALL" else resistance
                simulated = simulate_trade(
                    session,
                    index,
                    direction=candidate.direction,
                    anchor=anchor,
                    atr=float(row["atr"]),
                    config=config,
                )
                if simulated is None:
                    blocked_geometry += 1
                    continue
                trades.append(
                    {
                        **simulated,
                        "session_date": session_date,
                        "signal_timestamp": (current_ts + pd.Timedelta(minutes=1)).isoformat(),
                        "direction": candidate.direction,
                        "raw_score": float(candidate.raw_score),
                        "primary_regime": regime.primary_regime,
                        "trend_up_score": float(regime.scores.get("TREND_UP", 0.0)),
                        "trend_down_score": float(regime.scores.get("TREND_DOWN", 0.0)),
                        "anchor": anchor,
                        "atr": float(row["atr"]),
                        "setup_id": setup_id,
                        "setup_identity": identity,
                    }
                )
                next_available_index = int(simulated["exit_index"]) + 1
                break

    return trades, {
        "signals_total": signal_count,
        "trades_total": len(trades),
        "prefilter_checkpoints": prefilter_checkpoints,
        "blocked_invalid_geometry": blocked_geometry,
        "blocked_data_gap": blocked_data_gap,
        "unique_setup_ids": len(seen_setup_ids),
    }
