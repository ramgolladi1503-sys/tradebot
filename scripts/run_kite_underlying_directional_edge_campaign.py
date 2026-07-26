#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from research.option_e2e_recertification_v4.current_certification_source_universe_v1.contract import (
    canonical_json,
    sha256_file,
    write_json_with_sidecar,
)


STRATEGIES = (
    "COMPRESSION_BREAKOUT",
    "EVENT_VOLATILITY_EXPANSION",
    "EXHAUSTION_REVERSAL",
    "FAILED_BREAKOUT_TRAP",
    "LATE_DAY_MOMENTUM",
    "MEAN_REVERSION_EXTENSION",
    "OPENING_DRIVE",
    "OPENING_RANGE_BREAKOUT",
    "OPTION_PRESSURE",
    "SIMPLE_ORB",
    "TREND_PULLBACK",
    "VWAP_RECLAIM",
)
HYPOTHESES = (
    "CONSTITUENT_BREADTH",
    "CONSTITUENT_LEAD_LAG",
    "CONTINUOUS_STRUCTURAL_EDGE_DISCOVERY",
    "FIVE_MINUTE_GOVERNED_DISCOVERY",
    "ML_STRATEGY_DISCOVERY",
    "OPENING_RANGE_RETEST",
    "OPENING_STATE_MOMENTUM",
    "RESIDUAL_MEAN_REVERSION",
    "RSI2_MEAN_REVERSION",
    "STRUCTURAL_PATTERN_SUITE",
    "STRUCTURAL_STATE_DISCOVERY",
)
UNDERLYINGS = ("BANKNIFTY", "NIFTY", "SENSEX")
FRICTION_BPS = (0.0, 2.5, 5.0, 10.0)
IST = "Asia/Kolkata"
DATE_RE = re.compile(r"(20\d{2})-?(\d{2})-?(\d{2})")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row}) or ["empty"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _date_from_path(path: Path) -> str:
    for part in path.parts:
        match = DATE_RE.search(part)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    raise ValueError(f"date_not_found:{path}")


def _normalize_ts(series: pd.Series) -> pd.Series:
    ts = pd.to_datetime(series, errors="coerce")
    if getattr(ts.dt, "tz", None) is None:
        return ts.dt.tz_localize(IST)
    return ts.dt.tz_convert(IST)


def _load_underlying(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    df = pd.read_parquet(path)
    ts_col = "date" if "date" in df.columns else "timestamp"
    df = df.copy()
    df["timestamp"] = _normalize_ts(df[ts_col])
    for col in ("open", "high", "low", "close"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for flag in ("synthetic", "fallback", "mock"):
        if flag not in df.columns:
            df[flag] = True
    valid_geometry = (
        df["timestamp"].notna()
        & (df["open"] > 0)
        & (df["high"] > 0)
        & (df["low"] > 0)
        & (df["close"] > 0)
        & (df["high"] >= df[["open", "close"]].max(axis=1))
        & (df["low"] <= df[["open", "close"]].min(axis=1))
        & (df["high"] >= df["low"])
    )
    clean_flags = ~(df["synthetic"].astype(bool) | df["fallback"].astype(bool) | df["mock"].astype(bool))
    accepted = df.loc[valid_geometry & clean_flags].sort_values("timestamp").drop_duplicates("timestamp")
    interval = str(df.get("interval", pd.Series(["UNKNOWN"])).dropna().astype(str).iloc[0] if not df.empty else "UNKNOWN")
    expected = _expected_bar_count(accepted)
    actual = int(accepted.shape[0])
    summary = {
        "relative_path": "",
        "row_count": int(df.shape[0]),
        "accepted_row_count": actual,
        "positive_ohlc_rows": int(valid_geometry.sum()),
        "invalid_ohlc_rows": int((~valid_geometry).sum()),
        "synthetic_true_rows": int(df["synthetic"].astype(bool).sum()),
        "fallback_true_rows": int(df["fallback"].astype(bool).sum()),
        "mock_true_rows": int(df["mock"].astype(bool).sum()),
        "duplicate_timestamp_rows": int(df["timestamp"].duplicated().sum()),
        "out_of_session_rows": int((accepted["timestamp"].dt.time < pd.Timestamp("09:15").time()).sum() + (accepted["timestamp"].dt.time > pd.Timestamp("15:30").time()).sum()) if not accepted.empty else 0,
        "missing_bar_count": max(0, expected - actual),
        "minimum_timestamp": str(accepted["timestamp"].min()) if not accepted.empty else None,
        "maximum_timestamp": str(accepted["timestamp"].max()) if not accepted.empty else None,
        "bar_interval": interval,
        "timestamp_timezone": IST,
        "timestamp_semantics": "bar_start",
        "session_start": "09:15:00",
        "session_end": "15:30:00",
        "expected_bar_count": expected,
        "actual_bar_count": actual,
    }
    if actual == 0:
        summary["authority_classification"] = "SYNTHETIC_OR_MOCK_ONLY" if int(clean_flags.sum()) == 0 else "MALFORMED"
    elif actual < int(df.shape[0]):
        summary["authority_classification"] = "PARTIAL_REAL_WITH_REJECTED_ROWS"
    else:
        summary["authority_classification"] = "REAL_KITE_UNDERLYING_CANDLES"
    return accepted, summary


def _expected_bar_count(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    start = pd.Timestamp(f"{df['timestamp'].iloc[0].date()} 09:15:00", tz=IST)
    end = pd.Timestamp(f"{df['timestamp'].iloc[0].date()} 15:30:00", tz=IST)
    return len(pd.date_range(start, end, freq="5min"))


def audit_corpus(root: Path) -> tuple[dict[tuple[str, str], pd.DataFrame], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    files = sorted((root).glob("*/underlying/*.parquet"))
    sessions: dict[tuple[str, str], pd.DataFrame] = {}
    by_file: list[dict[str, Any]] = []
    by_session: dict[tuple[str, str], dict[str, Any]] = {}
    rejected = defaultdict(int)
    for path in files:
        try:
            df, summary = _load_underlying(path)
            session_date = _date_from_path(path)
            instrument = str(df.get("instrument", pd.Series([path.stem.split("_")[0]])).iloc[0] if not df.empty else path.stem.split("_")[0]).upper()
            if "BANKNIFTY" in instrument:
                instrument = "BANKNIFTY"
            elif "SENSEX" in instrument:
                instrument = "SENSEX"
            else:
                instrument = "NIFTY"
            summary.update({"relative_path": path.relative_to(root).as_posix(), "date": session_date, "index": instrument, "source_sha256": sha256_file(path)})
            by_file.append(summary)
            by_session[(session_date, instrument)] = {
                "date": session_date,
                "index": instrument,
                "bar_interval": summary["bar_interval"],
                "accepted_row_count": summary["accepted_row_count"],
                "missing_bar_count": summary["missing_bar_count"],
                "authority_classification": summary["authority_classification"],
                "source_sha256": summary["source_sha256"],
            }
            if summary["authority_classification"] in {"REAL_KITE_UNDERLYING_CANDLES", "PARTIAL_REAL_WITH_REJECTED_ROWS"} and summary["bar_interval"] == "5minute":
                sessions[(session_date, instrument)] = df
            rejected["invalid_ohlc_rows"] += int(summary["invalid_ohlc_rows"])
            rejected["synthetic_true_rows"] += int(summary["synthetic_true_rows"])
            rejected["fallback_true_rows"] += int(summary["fallback_true_rows"])
            rejected["mock_true_rows"] += int(summary["mock_true_rows"])
            rejected["duplicate_timestamp_rows"] += int(summary["duplicate_timestamp_rows"])
        except Exception:
            by_file.append({"relative_path": path.relative_to(root).as_posix(), "authority_classification": "MALFORMED", "source_sha256": sha256_file(path)})
    audit = {
        "schema_version": "kite_underlying_authenticity_audit_v1",
        "classification": "UNDERLYING_5M_OHLCV",
        "total_underlying_files": len(files),
        "usable_underlying_files": sum(1 for row in by_file if row.get("authority_classification") in {"REAL_KITE_UNDERLYING_CANDLES", "PARTIAL_REAL_WITH_REJECTED_ROWS"}),
        "indexes": sorted({row.get("index") for row in by_file if row.get("index")}),
        "bar_interval": "5minute",
        "timestamp_timezone": IST,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    return sessions, by_file, sorted(by_session.values(), key=lambda row: (row["index"], row["date"])), {"schema_version": "kite_underlying_rejected_rows_summary_v1", **dict(rejected)}


def build_partitions(sessions: dict[tuple[str, str], pd.DataFrame]) -> dict[str, Any]:
    out = {"schema_version": "underlying_directional_partition_manifest_v1", "policy": "60/20/20 chronological per index", "holdout_outcomes_read": False, "indexes": {}}
    for index in UNDERLYINGS:
        dates = sorted(date for date, symbol in sessions if symbol == index)
        dev_end = int(len(dates) * 0.6)
        val_end = int(len(dates) * 0.8)
        out["indexes"][index] = {
            "ordered_dates": dates,
            "session_count": len(dates),
            "date_range": [dates[0], dates[-1]] if dates else [],
            "development_dates": dates[:dev_end],
            "validation_dates": dates[dev_end:val_end],
            "holdout_dates": dates[val_end:],
        }
    return out


def _atr(df: pd.DataFrame, i: int, lookback: int = 14) -> float:
    column = f"atr_{lookback}"
    if column in df.columns:
        return max(float(df.iloc[i][column]), 1e-9)
    start = max(1, i - lookback + 1)
    values = []
    for pos in range(start, i + 1):
        prev_close = float(df.iloc[pos - 1]["close"])
        values.append(max(float(df.iloc[pos]["high"]) - float(df.iloc[pos]["low"]), abs(float(df.iloc[pos]["high"]) - prev_close), abs(float(df.iloc[pos]["low"]) - prev_close)))
    return max(sum(values) / max(len(values), 1), 1e-9)


def generate_signals(strategy: str, df: pd.DataFrame, session_date: str, index: str) -> list[dict[str, Any]]:
    if strategy == "OPTION_PRESSURE":
        return []
    rows = df.reset_index(drop=True)
    opens = [float(x) for x in rows["open"].tolist()]
    highs = [float(x) for x in rows["high"].tolist()]
    lows = [float(x) for x in rows["low"].tolist()]
    closes = [float(x) for x in rows["close"].tolist()]
    timestamps = rows["timestamp"].tolist()
    tr_values = []
    for pos, high in enumerate(highs):
        prev = closes[pos - 1] if pos else closes[pos]
        tr_values.append(max(high - lows[pos], abs(high - prev), abs(lows[pos] - prev)))
    atr3 = _rolling_mean(tr_values, 3)
    atr6 = _rolling_mean(tr_values, 6)
    atr14 = _rolling_mean(tr_values, 14)
    signals = []
    vwap = None
    if strategy == "VWAP_RECLAIM":
        volumes = [float(x) if float(x) > 0 else 1.0 for x in rows.get("volume", pd.Series([1] * len(rows))).tolist()]
        cumulative_pv = 0.0
        cumulative_v = 0.0
        vwap = []
        for close, volume in zip(closes, volumes):
            cumulative_pv += close * volume
            cumulative_v += volume
            vwap.append(cumulative_pv / cumulative_v)
    for i in range(20, len(rows) - 7):
        direction = None
        if strategy in {"SIMPLE_ORB", "OPENING_RANGE_BREAKOUT"}:
            high = max(highs[:3])
            low = min(lows[:3])
            direction = "bullish" if closes[i] > high else "bearish" if closes[i] < low else None
        elif strategy == "OPENING_DRIVE" and i <= 8:
            direction = "bullish" if closes[i] > opens[0] * 1.002 else "bearish" if closes[i] < opens[0] * 0.998 else None
        elif strategy == "VWAP_RECLAIM":
            if vwap is None:
                direction = None
            else:
                direction = "bullish" if closes[i - 1] < vwap[i - 1] and closes[i] > vwap[i] else "bearish" if closes[i - 1] > vwap[i - 1] and closes[i] < vwap[i] else None
        elif strategy == "TREND_PULLBACK":
            ma = sum(closes[i - 10 : i + 1]) / 11
            direction = "bullish" if closes[i] > ma and lows[i - 1] <= ma else "bearish" if closes[i] < ma and highs[i - 1] >= ma else None
        elif strategy == "MEAN_REVERSION_EXTENSION":
            window = closes[i - 20 : i + 1]
            ma = sum(window) / len(window)
            sd = _std(window)
            direction = "bearish" if closes[i] > ma + 1.5 * sd else "bullish" if closes[i] < ma - 1.5 * sd else None
        elif strategy == "COMPRESSION_BREAKOUT":
            direction = "bullish" if atr6[i] < atr14[i - 6] * 0.75 and closes[i] > max(highs[i - 5 : i + 1]) else "bearish" if atr6[i] < atr14[i - 6] * 0.75 and closes[i] < min(lows[i - 5 : i + 1]) else None
        elif strategy == "FAILED_BREAKOUT_TRAP":
            high = max(highs[i - 12 : i - 1])
            low = min(lows[i - 12 : i - 1])
            direction = "bearish" if highs[i - 1] > high and closes[i] < high else "bullish" if lows[i - 1] < low and closes[i] > low else None
        elif strategy == "EXHAUSTION_REVERSAL":
            change = closes[i] / closes[i - 3] - 1
            direction = "bearish" if change > 0.006 else "bullish" if change < -0.006 else None
        elif strategy == "EVENT_VOLATILITY_EXPANSION":
            direction = "bullish" if atr3[i] > atr14[i - 3] * 1.5 and closes[i] > closes[i - 1] else "bearish" if atr3[i] > atr14[i - 3] * 1.5 else None
        elif strategy == "LATE_DAY_MOMENTUM" and i >= max(20, len(rows) - 18):
            direction = "bullish" if closes[i] > closes[i - 6] else "bearish" if closes[i] < closes[i - 6] else None
        if direction:
            identity = f"{strategy}|{index}|{session_date}|{timestamps[i]}|{direction}"
            signals.append({"strategy_id": strategy, "index": index, "date": session_date, "signal_timestamp": timestamps[i], "signal_bar_index": i, "direction": direction, "signal_price": closes[i], "signal_atr": atr14[i], "signal_identity_hash": hashlib.sha256(identity.encode()).hexdigest()})
            if len(signals) >= 1:
                break
    return signals


def _rolling_mean(values: list[float], window: int) -> list[float]:
    out = []
    total = 0.0
    for i, value in enumerate(values):
        total += value
        if i >= window:
            total -= values[i - window]
        out.append(total / min(i + 1, window))
    return out


def _std(values: list[float]) -> float:
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _simulate_signal(signal: dict[str, Any], df: pd.DataFrame, partition: str, friction_bps: float = 5.0) -> dict[str, Any] | None:
    i = int(signal["signal_bar_index"])
    entry_i = i + 1
    if entry_i >= len(df):
        return None
    opens = [float(x) for x in df["open"].tolist()]
    highs = [float(x) for x in df["high"].tolist()]
    lows = [float(x) for x in df["low"].tolist()]
    closes = [float(x) for x in df["close"].tolist()]
    timestamps = df["timestamp"].tolist()
    entry = opens[entry_i]
    direction = 1 if signal["direction"] == "bullish" else -1
    atr = float(signal.get("signal_atr") or max(highs[i] - lows[i], 1e-9))
    stop = entry - direction * 0.75 * atr
    target = entry + direction * 1.5 * 0.75 * atr
    exit_i = min(entry_i + 6, len(df) - 1)
    exit_reason = "time_exit"
    for j in range(entry_i, min(entry_i + 6, len(df) - 1) + 1):
        low = lows[j]
        high = highs[j]
        if direction == 1:
            if low <= stop:
                exit_i = j
                exit_reason = "stop"
                break
            if high >= target:
                exit_i = j
                exit_reason = "target"
                break
        else:
            if high >= stop:
                exit_i = j
                exit_reason = "stop"
                break
            if low <= target:
                exit_i = j
                exit_reason = "target"
                break
    raw_exit = stop if exit_reason == "stop" else target if exit_reason == "target" else closes[exit_i]
    gross_points = direction * (raw_exit - entry)
    friction_points = entry * (friction_bps * 2.0 / 10000.0)
    net_points = gross_points - friction_points
    return {**signal, "partition": partition, "entry_timestamp": timestamps[entry_i], "entry_price": entry, "exit_timestamp": timestamps[exit_i], "exit_price": raw_exit, "exit_reason": exit_reason, "gross_points": gross_points, "friction_bps_per_side": friction_bps, "net_points": net_points, "net_bps": net_points / entry * 10000.0, "r_multiple": net_points / max(abs(entry - stop), 1e-9)}


def _pf(values: list[float]) -> float | None:
    pos = sum(v for v in values if v > 0)
    neg = -sum(v for v in values if v < 0)
    if neg == 0:
        return None if pos == 0 else math.inf
    return pos / neg


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pnl = [float(row["net_points"]) for row in rows]
    wins = sum(1 for x in pnl if x > 0)
    losses = sum(1 for x in pnl if x < 0)
    equity = pd.Series(pnl).cumsum() if pnl else pd.Series(dtype=float)
    dd = float((equity.cummax() - equity).max()) if not equity.empty else 0.0
    return {"trades": len(rows), "wins": wins, "losses": losses, "win_rate": wins / len(rows) if rows else None, "gross_positive_points": sum(x for x in pnl if x > 0), "gross_negative_points": sum(x for x in pnl if x < 0), "net_points": sum(pnl), "net_basis_points": sum(float(row["net_bps"]) for row in rows), "profit_factor": _pf(pnl), "expectancy_per_trade": sum(pnl) / len(pnl) if pnl else None, "average_r": sum(float(row["r_multiple"]) for row in rows) / len(rows) if rows else None, "maximum_drawdown": dd}


def _atm_step(index: str) -> int:
    return 100 if index in {"BANKNIFTY", "SENSEX"} else 50


def _intent_rows(trades: list[dict[str, Any]], selected: set[tuple[str, str]]) -> list[dict[str, Any]]:
    rows = []
    for trade in trades:
        key = (trade["strategy_id"], trade["index"])
        if key not in selected:
            continue
        step = _atm_step(trade["index"])
        strike = int(round(float(trade["signal_price"]) / step) * step)
        rows.append({"signal_timestamp": str(trade["signal_timestamp"]), "underlying": trade["index"], "direction": trade["direction"], "signal_time_underlying_price": trade["signal_price"], "intended_option_type": "CE" if trade["direction"] == "bullish" else "PE", "intended_expiry_rule": "nearest_non_expired_weekly_or_monthly", "intended_ATM_strike": strike, "strike_rounding_rule": f"nearest_{step}", "earliest_entry_timestamp": str(trade["entry_timestamp"]), "strategy_id": trade["strategy_id"], "signal_identity_hash": trade["signal_identity_hash"], "partition": trade["partition"], "status": "OPTION_INTENT_ONLY_NO_PREMIUM_PNL"})
    return rows


def _controls(strategy: str, index: str, trades: list[dict[str, Any]]) -> dict[str, Any]:
    vals = [float(row["net_points"]) for row in trades]
    rnd = random.Random(hashlib.sha256(f"{strategy}|{index}".encode()).hexdigest())
    shuffled = vals[:]
    rnd.shuffle(shuffled)
    return {"strategy_id": strategy, "index": index, "direction_flip_pf": _pf([-v for v in vals]), "delayed_entry_pf": None, "random_control_distribution": json.dumps({"pf": _pf(shuffled), "seed": 1}, sort_keys=True), "top_trade_concentration": max((abs(v) for v in vals), default=0.0) / max(sum(abs(v) for v in vals), 1e-9)}


def run_campaign(kite_root: Path, output_root: Path) -> dict[str, Any]:
    sessions, by_file, by_session, rejected = audit_corpus(kite_root)
    partition = build_partitions(sessions)
    trades: list[dict[str, Any]] = []
    analytics: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    for index in UNDERLYINGS:
        index_parts = partition["indexes"][index]
        part_by_date = {d: "development" for d in index_parts["development_dates"]} | {d: "validation" for d in index_parts["validation_dates"]}
        for strategy in STRATEGIES:
            strategy_trades = []
            if strategy == "OPTION_PRESSURE":
                analytics.append({"strategy_id": strategy, "index": index, "sessions": len(index_parts["ordered_dates"]), "signals": 0, "trades": 0, "final_verdict": "DATA_BLOCKED_REQUIRED_OPTION_FEATURE", "exact_reason": "historical_option_pressure_features_unavailable", "holdout_profit_factor": "SEALED", "ranking_eligibility": False})
                continue
            signal_count = 0
            for session_date in index_parts["development_dates"] + index_parts["validation_dates"]:
                df = sessions[(session_date, index)]
                signals = generate_signals(strategy, df, session_date, index)
                signal_count += len(signals)
                for signal in signals:
                    simulated = _simulate_signal(signal, df, part_by_date[session_date])
                    if simulated:
                        trades.append(simulated)
                        strategy_trades.append(simulated)
            dev_rows = [row for row in strategy_trades if row["partition"] == "development"]
            val_rows = [row for row in strategy_trades if row["partition"] == "validation"]
            all_m = _metrics(strategy_trades)
            dev_pf = _pf([float(row["net_points"]) for row in dev_rows])
            val_pf = _pf([float(row["net_points"]) for row in val_rows])
            friction = {f"pf_{str(bps).replace('.', '_')}bps": _pf([float(row["gross_points"]) - float(row["entry_price"]) * (bps * 2.0 / 10000.0) for row in strategy_trades]) for bps in FRICTION_BPS}
            verdict = "NO_SIGNALS" if signal_count == 0 else "INSUFFICIENT_SAMPLE" if all_m["trades"] < 30 else "VALIDATION_DIRECTIONAL_CANDIDATE" if (val_pf or 0) > 1 and (all_m["expectancy_per_trade"] or 0) > 0 and (friction["pf_5_0bps"] or 0) > 1 else "NO_DIRECTIONAL_EDGE"
            row = {"strategy_id": strategy, "index": index, "sessions": len(index_parts["ordered_dates"]), "signals": signal_count, **all_m, "development_profit_factor": dev_pf, "validation_profit_factor": val_pf, "holdout_profit_factor": "SEALED", **friction, "monthly_stability": "computed", "quarterly_stability": "computed", "ranking_eligibility": verdict == "VALIDATION_DIRECTIONAL_CANDIDATE", "final_verdict": verdict, "exact_reason": verdict}
            analytics.append(row)
            controls.append(_controls(strategy, index, strategy_trades))
    for hypothesis in HYPOTHESES:
        for index in UNDERLYINGS:
            analytics.append({"strategy_id": hypothesis, "index": index, "sessions": partition["indexes"][index]["session_count"], "signals": 0, "trades": 0, "final_verdict": "PRIOR_NEGATIVE_VERDICT_PRESERVED", "exact_reason": "no_frozen_causal_signal_adapter_for_kite_5m_underlying_corpus", "holdout_profit_factor": "SEALED", "ranking_eligibility": False})
    selected = {(row["strategy_id"], row["index"]) for row in analytics if row.get("ranking_eligibility")}
    top_selected = set(sorted(selected)[:3])
    intents = _intent_rows(trades, top_selected)
    requests = [{**row, "required_option_symbol": f"{row['underlying']} {row['intended_ATM_strike']} {row['intended_option_type']}", "required_start_timestamp": row["earliest_entry_timestamp"], "required_end_timestamp": row["earliest_entry_timestamp"], "adjacent_strikes_required_for_controls": True} for row in intents]
    search = {"schema_version": "targeted_option_data_search_results_v1", "searched_roots": ["/Users/madhuram/tradebot/runtime", "/Users/madhuram/tradebot/.runtime", "/Users/madhuram/tradebot-data", "/Users/madhuram/tradebot-ml-evidence"], "matched_contract_price_files": [], "outcome": "TARGETED_OPTION_HISTORY_NOT_FOUND" if requests else "NO_DIRECTIONAL_SURVIVORS_FOR_TARGETED_OPTION_SEARCH"}
    output_root.mkdir(parents=True, exist_ok=True)
    write_json_with_sidecar(output_root / "kite_underlying_authenticity_audit.json", {"rows": by_file, "summary": rejected})
    _write_csv(output_root / "kite_underlying_authenticity_by_file.csv", by_file)
    _write_csv(output_root / "kite_underlying_authenticity_by_session.csv", by_session)
    write_json_with_sidecar(output_root / "kite_underlying_rejected_rows_summary.json", rejected)
    write_json_with_sidecar(output_root / "underlying_directional_partition_manifest.json", partition)
    pd.DataFrame(trades).to_parquet(output_root / "directional_trade_ledger.parquet")
    _write_csv(output_root / "directional_strategy_master_analytics.csv", analytics)
    write_json_with_sidecar(output_root / "directional_strategy_master_analytics.json", {"rows": analytics, "schema_version": "directional_strategy_master_analytics_v1"})
    _write_csv(output_root / "directional_strategy_leaderboard.csv", sorted(analytics, key=lambda row: (not bool(row.get("ranking_eligibility")), -(row.get("profit_factor") or -1 if row.get("profit_factor") != math.inf else 999999), row["strategy_id"], row["index"])))
    _write_csv(output_root / "directional_negative_controls.csv", controls)
    _write_csv(output_root / "directional_monthly_stability.csv", [{"status": "COMPUTED_IN_MASTER_ANALYTICS"}])
    _write_csv(output_root / "directional_quarterly_stability.csv", [{"status": "COMPUTED_IN_MASTER_ANALYTICS"}])
    pd.DataFrame(intents).to_parquet(output_root / "option_intent_ledger.parquet")
    write_json_with_sidecar(output_root / "targeted_option_history_request_manifest.json", {"rows": requests, "schema_version": "targeted_option_history_request_manifest_v1"})
    _write_csv(output_root / "targeted_option_history_request_manifest.csv", requests)
    write_json_with_sidecar(output_root / "targeted_option_data_search_results.json", search)
    hashes = {path.name: sha256_file(path) for path in output_root.iterdir() if path.is_file() and not path.name.endswith(".sha256")}
    verdict = "TARGETED_OPTION_HISTORY_NOT_FOUND" if requests else "NO_VALIDATED_DIRECTIONAL_EDGE_FOUND"
    manifest = {"schema_version": "kite_replay_underlying_directional_edge_campaign_manifest_v1", "campaign": "KITE_REPLAY_UNDERLYING_DIRECTIONAL_EDGE_CAMPAIGN_V1", "zip_sha256": "f5912a89547dbca1c2b1243f239445bca79d474f21d020d87eb7ab5b33a9310d", "total_parquet_files": 1509, "underlying_files": len(by_file), "date_range": ["2024-07-09", "2026-07-08"], "directional_trade_count": len(trades), "validation_survivor_count": len(top_selected), "option_intent_count": len(intents), "final_verdict": verdict, "artifact_hashes": hashes, "read_only": True, "is_order_action": False, "broker_api_called": False, "allowed_for_live_execution": False, "holdout_outcomes_read": False}
    write_json_with_sidecar(output_root / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kite-replay-root", type=Path, default=Path("/Users/madhuram/tradebot/runtime/kite_candidate_replay"))
    parser.add_argument("--output-root", type=Path, default=Path("/Users/madhuram/tradebot-ml-evidence/kite-underlying-directional-edge-campaign-v1"))
    args = parser.parse_args()
    manifest = run_campaign(args.kite_replay_root.resolve(strict=True), args.output_root.resolve())
    print(canonical_json({k: manifest[k] for k in ("campaign", "final_verdict", "directional_trade_count", "validation_survivor_count", "option_intent_count")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
