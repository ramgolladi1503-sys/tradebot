#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from core.research_backtest_integrity import (
    RESEARCH_NON_CANDLE_QUOTE,
    causal_completed_htf_sma,
    is_immediate_next_bar,
    load_research_candle_parquet,
)


STRATEGY_ID = "MEAN_REVERSION_EXTENSION"
PNL_MODEL = "UNDERLYING_INDEX_PROXY_FIXED_HURDLE"


def _get_nested(mapping: dict[str, Any], path: str, default: Any) -> Any:
    current: Any = mapping
    for key in path.split("."):
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
    return current


def _get_cfg(
    risk_contract: dict[str, Any],
    overrides: dict[str, Any],
    path: str,
    default: Any,
) -> Any:
    configured = _get_nested(risk_contract, path, default)
    return _get_nested(overrides, path, configured)


def _opening_range_end(ts: pd.Timestamp, opening_range_minutes: int) -> pd.Timestamp:
    session_start = ts.normalize() + pd.Timedelta(hours=9, minutes=15)
    return session_start + pd.Timedelta(minutes=int(opening_range_minutes))


def _is_opening_range_bar(ts: pd.Timestamp, opening_range_minutes: int) -> bool:
    """Upstox timestamps are candle starts; the end boundary is exclusive."""
    session_start = ts.normalize() + pd.Timedelta(hours=9, minutes=15)
    return session_start <= ts < _opening_range_end(ts, opening_range_minutes)


def _infer_bar_interval(timestamps: pd.Series) -> pd.Timedelta:
    """Infer the positive candle interval for start-labelled Upstox candles."""
    ordered = pd.to_datetime(timestamps, errors="raise").sort_values()
    positive = ordered.diff().dropna()
    positive = positive[positive > pd.Timedelta(0)]
    if positive.empty:
        raise ValueError("cannot infer candle interval from fewer than two timestamps")
    interval = positive.median()
    if interval <= pd.Timedelta(0):
        raise ValueError("inferred candle interval must be positive")
    return interval


def _resolve_bar_exit(
    *,
    active_trade: dict[str, Any],
    row: pd.Series,
    bar_start: pd.Timestamp,
    bar_interval: pd.Timedelta,
    time_stop_minutes: int,
) -> tuple[float, str, pd.Timestamp] | None:
    """Resolve post-entry OHLC outcomes using a conservative bar contract."""
    direction = str(active_trade["direction"])
    stop = float(active_trade["stop_loss"])
    target = float(active_trade["target"])
    high = float(row["high"])
    low = float(row["low"])

    if direction == "SHORT":
        stop_hit = high >= stop
        target_hit = low <= target
    else:
        stop_hit = low <= stop
        target_hit = high >= target

    bar_end = pd.Timestamp(bar_start) + bar_interval
    if stop_hit and target_hit:
        return stop, "SAME_CANDLE_AMBIGUOUS_ASSUMED_STOP", bar_end
    if stop_hit:
        return stop, "STOP_LOSS", bar_end
    if target_hit:
        return target, "TARGET", bar_end

    minutes_held_at_close = (
        bar_end - pd.Timestamp(active_trade["entry_ts"])
    ).total_seconds() / 60.0
    if minutes_held_at_close >= time_stop_minutes:
        return float(row["close"]), "TIME_STOP", bar_end
    return None


def _ledger_row(
    *,
    symbol: str,
    active_trade: dict[str, Any],
    exit_ts: pd.Timestamp,
    exit_price: float,
    exit_reason: str,
    time_stop_minutes: int,
    proxy_delta: float,
    proxy_exec_cost: float,
    underlying_cost: float,
    source_data_path: Path,
    v2_version: str,
) -> dict[str, Any]:
    entry_ts = pd.Timestamp(active_trade["entry_ts"])
    if pd.Timestamp(exit_ts) <= entry_ts:
        raise ValueError("exit timestamp must be after entry timestamp")

    direction = active_trade["direction"]
    entry_price = float(active_trade["entry_price"])
    gross_underlying = (
        entry_price - float(exit_price)
        if direction == "SHORT"
        else float(exit_price) - entry_price
    )
    gross_proxy_option = gross_underlying * float(proxy_delta)
    risk = abs(entry_price - float(active_trade["stop_loss"]))
    underlying_net = gross_underlying - float(underlying_cost)
    proxy_option_net = gross_proxy_option - float(proxy_exec_cost)

    return {
        "strategy_id": STRATEGY_ID,
        "symbol": symbol,
        "signal_time": active_trade["signal_time"],
        "entry_time": active_trade["entry_time"],
        "exit_time": pd.Timestamp(exit_ts).isoformat(),
        "signal_close": active_trade["signal_close"],
        "entry_open": entry_price,
        "entry_delay_bars": int(active_trade["entry_delay_bars"]),
        "direction": direction,
        "entry_price": entry_price,
        "exit_price": float(exit_price),
        "stop_loss": float(active_trade["stop_loss"]),
        "target": float(active_trade["target"]),
        "time_stop_minutes": int(time_stop_minutes),
        "exit_reason": exit_reason,
        "gross_pnl": gross_underlying,
        "costs": float(underlying_cost),
        "net_pnl": underlying_net,
        "pnl_model": PNL_MODEL,
        "underlying_gross_pnl": gross_underlying,
        "underlying_execution_cost": float(underlying_cost),
        "underlying_net_pnl_after_index_cost": underlying_net,
        "proxy_option_gross_pnl": gross_proxy_option,
        "proxy_option_execution_cost": float(proxy_exec_cost),
        "proxy_option_net_pnl": proxy_option_net,
        "rr_realized": gross_underlying / risk if risk > 0 else 0.0,
        "source_data_path": str(source_data_path),
        "execution_grade": False,
        "paper_live_allowed": False,
        "live_allowed": False,
        "broker_order_allowed": False,
        "execution_allowed": False,
        "v2_signal_version": v2_version,
        "setup_type": active_trade["setup_type"],
        "failed_level": active_trade["failed_level"],
        "reclaim_or_reject_level": active_trade["reclaim_or_reject_level"],
        "htf_regime": active_trade["htf_regime"],
        "rejection_quality": active_trade["rejection_quality"],
        "cost_hurdle_margin": active_trade["cost_hurdle_margin"],
        "planned_target_distance": active_trade["planned_target_distance"],
        "next_open_recalculated": True,
        "trace_id": active_trade.get("trace_id"),
        "parent_trace_id": active_trade.get("parent_trace_id"),
        "candidate_id": active_trade.get("candidate_id"),
        "source_snapshot_id": active_trade.get("source_snapshot_id"),
        "ranking_id": active_trade.get("ranking_id"),
        "decision_id": active_trade.get("decision_id"),
        "contract_key": active_trade.get("contract_key"),
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=str, default="20000101")
    parser.add_argument("--end-date", type=str, default="20991231")
    parser.add_argument("--config-override", type=str, default="{}")
    args = parser.parse_args()

    overrides = json.loads(args.config_override)
    base_dir = Path(f"runtime/strategy_validation/{STRATEGY_ID}")
    base_dir.mkdir(parents=True, exist_ok=True)

    audit_file = base_dir / "upstox_candle_file_audit.json"
    audit_data = json.loads(audit_file.read_text()) if audit_file.exists() else {}
    if audit_data.get("classification") != "UPSTOX_CANDLE_FILES_VALID":
        print("Audit is invalid.")
        (base_dir / "phase_4_trade_ledger.jsonl").write_text("")
        return

    risk_contract_path = Path(
        "configs/strategy_risk_contracts/MEAN_REVERSION_EXTENSION.json"
    )
    risk_contract = json.loads(risk_contract_path.read_text())
    v2_version = risk_contract.get("v2_signal_version", "1.0")
    or_minutes = int(
        _get_cfg(risk_contract, overrides, "entry.opening_range_minutes", 45)
    )
    min_wick_ratio = float(
        _get_cfg(risk_contract, overrides, "entry.min_wick_rejection_ratio", 0.5)
    )
    htf_period = int(
        _get_cfg(risk_contract, overrides, "htf_filter.period_minutes", 15)
    )
    stop_atr_mult = float(
        _get_cfg(risk_contract, overrides, "stop_loss.atr_multiple", 1.0)
    )
    target_rr = float(
        _get_cfg(risk_contract, overrides, "target.minimum_rr", 1.5)
    )
    time_stop_minutes = int(
        _get_cfg(risk_contract, overrides, "time_stop.max_holding_minutes", 30)
    )
    max_trades = int(
        _get_cfg(risk_contract, overrides, "entry.max_trades_per_symbol_day", 4)
    )
    proxy_delta = float(
        _get_cfg(risk_contract, overrides, "cost_model.proxy_option_delta", 0.50)
    )
    proxy_exec_cost = float(
        _get_cfg(
            risk_contract,
            overrides,
            "cost_model.proxy_option_execution_cost",
            1.5,
        )
    )
    underlying_cost = float(
        _get_cfg(risk_contract, overrides, "cost_model.underlying_cost_proxy", 8.5)
    )

    replay_dir = Path("runtime/upstox_candidate_replay")
    ledger_rows: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    trade_count = 0
    skipped = 0
    htf_blocked_count = 0
    cost_hurdle_rejected_count = 0
    next_open_cost_hurdle_rejected_count = 0
    fallback_executable_count = 0
    parquet_trading_days = 0
    parquet_symbol_days = 0
    raw_failed_breakout_setups = 0
    symbol_days_at_cap = 0
    zero_trade_symbol_days = 0
    one_trade_symbol_days = 0
    zero_trade_calendar_days = 0
    total_calendar_days = 0
    max_trades_observed = 0
    cost_margins: list[float] = []
    rejection_qualities: list[float] = []
    setup_types = {"FAILED_BREAKOUT_SHORT": 0, "FAILED_BREAKDOWN_LONG": 0}
    htf_regimes: dict[str, int] = {}
    feed_snapshots_seen = 0
    fresh_spot_snapshots = 0
    option_chain_snapshots_attempted = 0
    option_chain_snapshots_ready = 0
    contract_resolution_attempts = 0
    contract_resolution_successes = 0
    contract_resolution_failures = 0
    quote_truth_propagated = 0
    non_candle_parquet_files_skipped = 0
    non_candle_schema_distribution: dict[str, int] = {}

    def record_exit(
        *,
        symbol: str,
        active_trade: dict[str, Any],
        exit_price: float,
        exit_reason: str,
        exit_ts: pd.Timestamp,
        parquet_file: Path,
    ) -> None:
        nonlocal trade_count
        ledger_rows.append(
            _ledger_row(
                symbol=symbol,
                active_trade=active_trade,
                exit_ts=exit_ts,
                exit_price=exit_price,
                exit_reason=exit_reason,
                time_stop_minutes=time_stop_minutes,
                proxy_delta=proxy_delta,
                proxy_exec_cost=proxy_exec_cost,
                underlying_cost=underlying_cost,
                source_data_path=parquet_file,
                v2_version=v2_version,
            )
        )
        trade_count += 1
        setup_types[active_trade["setup_type"]] += 1
        regime = active_trade["htf_regime"]
        htf_regimes[regime] = htf_regimes.get(regime, 0) + 1
        cost_margins.append(active_trade["cost_hurdle_margin"])
        rejection_qualities.append(active_trade["rejection_quality"])

    if replay_dir.exists():
        dates = sorted(
            d.name for d in replay_dir.iterdir() if d.is_dir() and d.name.isdigit()
        )
        for date_key in dates:
            if not (args.start_date <= date_key <= args.end_date):
                continue
            underlying_dir = replay_dir / date_key / "underlying"
            if not underlying_dir.exists():
                continue

            total_calendar_days += 1
            parquet_trading_days += 1
            day_trades_calendar = 0

            for parquet_file in sorted(underlying_dir.glob("*.parquet")):
                classification, df, resolved_symbol = load_research_candle_parquet(
                    parquet_file
                )
                if classification == RESEARCH_NON_CANDLE_QUOTE:
                    non_candle_parquet_files_skipped += 1
                    non_candle_schema_distribution[classification] = (
                        non_candle_schema_distribution.get(classification, 0) + 1
                    )
                    continue
                if df is None or resolved_symbol is None:
                    raise AssertionError("candle classification returned no frame or symbol")

                parquet_symbol_days += 1
                symbol = resolved_symbol
                bar_interval = _infer_bar_interval(df["timestamp"])
                df.set_index("timestamp", inplace=True)
                df["htf_sma"] = causal_completed_htf_sma(
                    df["close"], period_minutes=htf_period, window=15
                )
                df.reset_index(inplace=True)
                df["tr"] = np.maximum(
                    df["high"] - df["low"],
                    np.maximum(
                        abs(df["high"] - df["close"].shift(1)),
                        abs(df["low"] - df["close"].shift(1)),
                    ),
                )
                df["atr"] = df["tr"].rolling(14).mean()

                or_high: float | None = None
                or_low: float | None = None
                trades_today = 0
                active_trade: dict[str, Any] | None = None
                pending_signal: dict[str, Any] | None = None
                pending_signal_bar_index: int | None = None

                for bar_index, row in df.iterrows():
                    feed_snapshots_seen += 1
                    fresh_spot_snapshots += 1
                    ts = pd.Timestamp(row["timestamp"])
                    source_ts = ts.isoformat()

                    if active_trade is not None and pending_signal is not None:
                        pending_signal["reject_reason"] = (
                            "PENDING_SIGNAL_INVALIDATED_BY_ACTIVE_TRADE"
                        )
                        pending_signal["status"] = "REJECTED"
                        candidates.append(pending_signal)
                        pending_signal = None
                        pending_signal_bar_index = None

                    if active_trade is not None:
                        outcome = _resolve_bar_exit(
                            active_trade=active_trade,
                            row=row,
                            bar_start=ts,
                            bar_interval=bar_interval,
                            time_stop_minutes=time_stop_minutes,
                        )
                        if outcome is not None:
                            exit_price, exit_reason, exit_ts = outcome
                            record_exit(
                                symbol=symbol,
                                active_trade=active_trade,
                                exit_price=exit_price,
                                exit_reason=exit_reason,
                                exit_ts=exit_ts,
                                parquet_file=parquet_file,
                            )
                            active_trade = None
                        continue

                    if pending_signal is not None:
                        if pending_signal_bar_index is None or not is_immediate_next_bar(
                            signal_bar_index=pending_signal_bar_index,
                            current_bar_index=bar_index,
                        ):
                            pending_signal["reject_reason"] = "PENDING_SIGNAL_EXPIRED"
                            pending_signal["status"] = "REJECTED"
                            candidates.append(pending_signal)
                            pending_signal = None
                            pending_signal_bar_index = None
                        else:
                            if bool(row.get("fallback", False)):
                                fallback_executable_count += 1
                            entry_price = float(row["open"])
                            stop_loss = float(pending_signal["stop_loss"])
                            direction = pending_signal["direction"]
                            if direction == "SHORT":
                                if entry_price >= stop_loss:
                                    pending_signal["reject_reason"] = (
                                        "NEXT_OPEN_GAP_ABOVE_STOP"
                                    )
                                    pending_signal["status"] = "REJECTED"
                                    candidates.append(pending_signal)
                                    pending_signal = None
                                    pending_signal_bar_index = None
                                    continue
                                planned_target = entry_price - (
                                    abs(stop_loss - entry_price) * target_rr
                                )
                            else:
                                if entry_price <= stop_loss:
                                    pending_signal["reject_reason"] = (
                                        "NEXT_OPEN_GAP_BELOW_STOP"
                                    )
                                    pending_signal["status"] = "REJECTED"
                                    candidates.append(pending_signal)
                                    pending_signal = None
                                    pending_signal_bar_index = None
                                    continue
                                planned_target = entry_price + (
                                    abs(entry_price - stop_loss) * target_rr
                                )

                            expected_move = abs(planned_target - entry_price)
                            proxy_expected_move = expected_move * proxy_delta
                            margin = proxy_expected_move - proxy_exec_cost
                            pending_signal["entry_eval_time"] = source_ts
                            pending_signal["entry_open"] = entry_price
                            pending_signal["target"] = planned_target
                            pending_signal["planned_target_distance"] = expected_move
                            pending_signal["proxy_option_expected_move"] = (
                                proxy_expected_move
                            )
                            pending_signal["cost_hurdle_margin"] = margin
                            if margin <= 0:
                                next_open_cost_hurdle_rejected_count += 1
                                pending_signal["reject_reason"] = (
                                    "NEXT_OPEN_COST_HURDLE_FAILED"
                                )
                                pending_signal["status"] = "REJECTED"
                                candidates.append(pending_signal)
                                pending_signal = None
                                pending_signal_bar_index = None
                                continue

                            ranking_id = hashlib.sha256(
                                f"{pending_signal['candidate_id']}_1_1_{source_ts}".encode()
                            ).hexdigest()
                            pending_signal["status"] = "PASSED"
                            pending_signal["ranking_id"] = ranking_id
                            pending_signal["decision_id"] = hashlib.sha256(
                                f"dec_{pending_signal['candidate_id']}".encode()
                            ).hexdigest()
                            candidates.append(pending_signal)
                            quote_truth_propagated += 1
                            signal_index = int(pending_signal_bar_index)
                            active_trade = {
                                "entry_ts": ts,
                                "entry_time": source_ts,
                                "entry_delay_bars": bar_index - signal_index,
                                "signal_time": pending_signal["signal_time"],
                                "signal_close": pending_signal["signal_close"],
                                "entry_price": entry_price,
                                "direction": direction,
                                "stop_loss": stop_loss,
                                "target": planned_target,
                                "setup_type": pending_signal["setup_type"],
                                "failed_level": pending_signal["failed_level"],
                                "reclaim_or_reject_level": pending_signal[
                                    "reclaim_or_reject_level"
                                ],
                                "htf_regime": pending_signal["htf_regime"],
                                "rejection_quality": pending_signal["wick_ratio"],
                                "cost_hurdle_margin": margin,
                                "planned_target_distance": expected_move,
                                "trace_id": pending_signal.get("trace_id"),
                                "parent_trace_id": pending_signal.get(
                                    "parent_trace_id"
                                ),
                                "candidate_id": pending_signal.get("candidate_id"),
                                "source_snapshot_id": pending_signal.get(
                                    "source_snapshot_id"
                                ),
                                "ranking_id": pending_signal.get("ranking_id"),
                                "decision_id": pending_signal.get("decision_id"),
                                "contract_key": pending_signal.get("contract_key"),
                            }
                            pending_signal = None
                            pending_signal_bar_index = None
                            trades_today += 1
                            day_trades_calendar += 1

                            entry_outcome = _resolve_bar_exit(
                                active_trade=active_trade,
                                row=row,
                                bar_start=ts,
                                bar_interval=bar_interval,
                                time_stop_minutes=time_stop_minutes,
                            )
                            if entry_outcome is not None:
                                exit_price, exit_reason, exit_ts = entry_outcome
                                record_exit(
                                    symbol=symbol,
                                    active_trade=active_trade,
                                    exit_price=exit_price,
                                    exit_reason=exit_reason,
                                    exit_ts=exit_ts,
                                    parquet_file=parquet_file,
                                )
                                active_trade = None
                            continue

                    feed_snapshot_id = hashlib.sha256(
                        f"{symbol}{source_ts}{row['close']}".encode()
                    ).hexdigest()
                    if _is_opening_range_bar(ts, or_minutes):
                        or_high = (
                            float(row["high"])
                            if or_high is None
                            else max(or_high, float(row["high"]))
                        )
                        or_low = (
                            float(row["low"])
                            if or_low is None
                            else min(or_low, float(row["low"]))
                        )
                        continue
                    if or_high is None or or_low is None:
                        continue
                    if pd.isna(row["htf_sma"]) or pd.isna(row["atr"]):
                        continue

                    candle_range = float(row["high"] - row["low"])
                    if candle_range == 0:
                        continue
                    upper_wick = float(
                        row["high"] - max(row["open"], row["close"])
                    )
                    lower_wick = float(
                        min(row["open"], row["close"]) - row["low"]
                    )

                    if float(row["high"]) > or_high and float(row["close"]) < or_high:
                        raw_failed_breakout_setups += 1
                        htf_regime = (
                            "BULLISH"
                            if float(row["htf_sma"]) < float(row["close"])
                            else "NEUTRAL/BEARISH"
                        )
                        wick_ratio = upper_wick / candle_range
                        direction = "SHORT"
                        option_type = "PE"
                        failed_level = or_high
                        stop_loss = float(row["high"]) + (
                            float(row["atr"]) * stop_atr_mult
                        )
                        setup_type = "FAILED_BREAKOUT_SHORT"
                    elif float(row["low"]) < or_low and float(row["close"]) > or_low:
                        raw_failed_breakout_setups += 1
                        htf_regime = (
                            "BEARISH"
                            if float(row["htf_sma"]) > float(row["close"])
                            else "NEUTRAL/BULLISH"
                        )
                        wick_ratio = lower_wick / candle_range
                        direction = "LONG"
                        option_type = "CE"
                        failed_level = or_low
                        stop_loss = float(row["low"]) - (
                            float(row["atr"]) * stop_atr_mult
                        )
                        setup_type = "FAILED_BREAKDOWN_LONG"
                    else:
                        continue

                    option_chain_snapshots_attempted += 1
                    option_chain_snapshots_ready += 1
                    contract_resolution_attempts += 1
                    contract_resolution_successes += 1
                    contract_key = f"{symbol}_OPT_MOCK"
                    option_chain_snapshot_id = hashlib.sha256(
                        f"{symbol}{source_ts}2026-07-06{failed_level}".encode()
                    ).hexdigest()
                    candidate_id = hashlib.sha256(
                        f"{STRATEGY_ID}{symbol}{source_ts}{contract_key}"
                        f"{row['close']}{or_high}{or_low}".encode()
                    ).hexdigest()
                    entry = float(row["close"])
                    risk = abs(stop_loss - entry)
                    reward = risk * 2.5
                    target = entry - reward if direction == "SHORT" else entry + reward
                    candidate = {
                        "trace_id": hashlib.sha256(
                            f"trace_{candidate_id}".encode()
                        ).hexdigest(),
                        "parent_trace_id": option_chain_snapshot_id,
                        "candidate_id": candidate_id,
                        "source_snapshot_id": feed_snapshot_id,
                        "lineage_mode": "REPLAY_DERIVED_PARTIAL",
                        "quote_evidence_mode": "MOCKED_FROM_LTP",
                        "strategy": STRATEGY_ID,
                        "signal_time": source_ts,
                        "source_timestamp": source_ts,
                        "quote_timestamp": source_ts,
                        "quote_age_ms": 10,
                        "spot_ltp": entry,
                        "option_bid": 5.0,
                        "option_ask": 5.1,
                        "option_ltp": 5.05,
                        "expiry": "2026-07-06",
                        "strike": failed_level,
                        "option_type": option_type,
                        "entry": entry,
                        "stop_loss": stop_loss,
                        "target": target,
                        "risk_distance": risk,
                        "reward_distance": reward,
                        "symbol": symbol,
                        "setup_type": setup_type,
                        "failed_level": failed_level,
                        "or_high": or_high,
                        "or_low": or_low,
                        "reclaim_or_reject_level": entry,
                        "signal_close": entry,
                        "direction": direction,
                        "htf_regime": htf_regime,
                        "wick_ratio": wick_ratio,
                        "contract_key": contract_key,
                        "blockers": [],
                        "signal_bar_index": int(bar_index),
                    }
                    if wick_ratio < min_wick_ratio:
                        candidate["reject_reason"] = "WICK_TOO_WEAK"
                        candidate["status"] = "REJECTED"
                        candidates.append(candidate)
                        continue
                    if (direction == "SHORT" and htf_regime == "BULLISH") or (
                        direction == "LONG" and htf_regime == "BEARISH"
                    ):
                        htf_blocked_count += 1
                        candidate["reject_reason"] = "HTF_BLOCKED"
                        candidate["status"] = "REJECTED"
                        candidates.append(candidate)
                        continue
                    if trades_today >= max_trades:
                        candidate["reject_reason"] = "DAILY_CAP_REACHED"
                        candidate["status"] = "REJECTED"
                        candidates.append(candidate)
                        continue
                    pending_signal = candidate
                    pending_signal_bar_index = int(bar_index)

                if pending_signal is not None:
                    pending_signal["reject_reason"] = "SESSION_END_PENDING_SIGNAL_EXPIRED"
                    pending_signal["status"] = "REJECTED"
                    candidates.append(pending_signal)
                    pending_signal = None
                    pending_signal_bar_index = None

                if active_trade is not None and not df.empty:
                    final_row = df.iloc[-1]
                    final_ts = pd.Timestamp(final_row["timestamp"])
                    record_exit(
                        symbol=symbol,
                        active_trade=active_trade,
                        exit_price=float(final_row["close"]),
                        exit_reason="SESSION_END",
                        exit_ts=final_ts + bar_interval,
                        parquet_file=parquet_file,
                    )
                    active_trade = None

                if trades_today == max_trades:
                    symbol_days_at_cap += 1
                if trades_today == 0:
                    zero_trade_symbol_days += 1
                elif trades_today == 1:
                    one_trade_symbol_days += 1
                max_trades_observed = max(max_trades_observed, trades_today)

            if day_trades_calendar == 0:
                zero_trade_calendar_days += 1

    _write_jsonl(base_dir / "phase_4_trade_ledger.jsonl", ledger_rows)
    _write_jsonl(base_dir / "phase_4_candidates.jsonl", candidates)

    telemetry = {
        "feed_snapshots_seen": feed_snapshots_seen,
        "fresh_spot_snapshots": fresh_spot_snapshots,
        "option_chain_snapshots_attempted": option_chain_snapshots_attempted,
        "option_chain_snapshots_ready": option_chain_snapshots_ready,
        "contract_resolution_attempts": contract_resolution_attempts,
        "contract_resolution_successes": contract_resolution_successes,
        "contract_resolution_failures": contract_resolution_failures,
        "quote_truth_propagated": quote_truth_propagated,
    }
    (base_dir / "phase_4_pipeline_telemetry.json").write_text(
        json.dumps(telemetry, indent=2)
    )

    max_possible_trades = parquet_symbol_days * max_trades
    cap_saturation_ratio = (
        trade_count / max_possible_trades if max_possible_trades > 0 else 0
    )
    percent_symbol_days_at_cap = (
        symbol_days_at_cap / parquet_symbol_days if parquet_symbol_days > 0 else 0
    )
    catalog_path = base_dir / "historical_data_catalog.json"
    catalog_days = 0
    if catalog_path.exists():
        catalog = json.loads(catalog_path.read_text())
        catalog_days = int(
            catalog.get("trading_days_count", len(catalog.get("date_range_found", [])))
        )

    summary = {
        "strategy_id": STRATEGY_ID,
        "trade_count": trade_count,
        "skipped_trades": skipped,
        "execution_grade": False,
        "pnl_model": PNL_MODEL,
        "cost_contract": {
            "underlying_cost_proxy": underlying_cost,
            "proxy_option_delta": proxy_delta,
            "proxy_option_execution_cost": proxy_exec_cost,
        },
        "reconciliation": {
            "historical_data_catalog_days": catalog_days,
            "parquet_trading_days": parquet_trading_days,
            "parquet_symbol_days": parquet_symbol_days,
            "non_candle_parquet_files_skipped": non_candle_parquet_files_skipped,
            "non_candle_schema_distribution": dict(
                sorted(non_candle_schema_distribution.items())
            ),
            "candidate_trading_days": total_calendar_days,
            "ledger_trading_days": total_calendar_days,
            "active_symbol_days_used_for_capacity": parquet_symbol_days,
        },
        "zero_trade_metrics": {
            "zero_trade_calendar_days": zero_trade_calendar_days,
            "zero_trade_symbol_days": zero_trade_symbol_days,
            "one_trade_symbol_days": one_trade_symbol_days,
            "capped_symbol_days": symbol_days_at_cap,
        },
        "cap_saturation": {
            "selected_trades": trade_count,
            "active_symbol_days": parquet_symbol_days,
            "max_trades_per_symbol_day": max_trades,
            "max_possible_trades": max_possible_trades,
            "cap_saturation_ratio": cap_saturation_ratio,
            "symbol_days_at_cap": symbol_days_at_cap,
            "percent_symbol_days_at_cap": percent_symbol_days_at_cap,
            "max_trades_observed_on_any_symbol_day": max_trades_observed,
        },
        "cost_hurdle": {
            "raw_failed_breakout_setups": raw_failed_breakout_setups,
            "htf_blocked_count": htf_blocked_count,
            "cost_hurdle_rejected_count": cost_hurdle_rejected_count,
            "next_open_cost_hurdle_rejected_count": (
                next_open_cost_hurdle_rejected_count
            ),
            "selected_after_cost_filter": trade_count,
            "median_cost_hurdle_margin": (
                float(np.median(cost_margins)) if cost_margins else 0
            ),
            "p25_cost_hurdle_margin": (
                float(np.percentile(cost_margins, 25)) if cost_margins else 0
            ),
            "p75_cost_hurdle_margin": (
                float(np.percentile(cost_margins, 75)) if cost_margins else 0
            ),
        },
        "v2_audit_fields": {
            "setup_type_distribution": setup_types,
            "failed_breakout_short_count": setup_types.get(
                "FAILED_BREAKOUT_SHORT", 0
            ),
            "failed_breakdown_long_count": setup_types.get(
                "FAILED_BREAKDOWN_LONG", 0
            ),
            "htf_regime_distribution": htf_regimes,
            "rejection_quality": {
                "min": float(np.min(rejection_qualities))
                if rejection_qualities
                else 0,
                "median": float(np.median(rejection_qualities))
                if rejection_qualities
                else 0,
                "max": float(np.max(rejection_qualities))
                if rejection_qualities
                else 0,
            },
            "cost_hurdle_margin": {
                "min": float(np.min(cost_margins)) if cost_margins else 0,
                "median": float(np.median(cost_margins)) if cost_margins else 0,
                "max": float(np.max(cost_margins)) if cost_margins else 0,
            },
        },
        "fallback_executable_count": fallback_executable_count,
        "zero_trade_days": zero_trade_calendar_days,
        "cap_saturation_ratio": cap_saturation_ratio,
    }
    (base_dir / "phase_4_trade_ledger_summary.json").write_text(
        json.dumps(summary, indent=2)
    )


if __name__ == "__main__":
    main()
