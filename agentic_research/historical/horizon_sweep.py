from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable

import pandas as pd

from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeClassifier
from strategies.movement.trend_pullback import generate_trend_pullback_candidates

from .campaign import _partition_sessions, _walk_forward
from .data import bar_payload, load_canonical_candles, prepare_features
from .engine import _necessary_structure
from .models import HistoricalCampaignConfig, HistoricalCampaignError, sha256_file, summarize_returns

DEFAULT_HORIZONS = tuple(range(15, 61, 5))
STOP_REASONS = {"STOP", "STOP_AND_TARGET_SAME_BAR_STOP_FIRST"}


def _gross_return_bps(direction: str, entry_price: float, exit_price: float) -> float:
    gross = ((exit_price - entry_price) / entry_price) * 10000.0
    return -gross if direction == "BUY_PUT" else gross


def trace_signal_path(
    session: pd.DataFrame,
    signal_index: int,
    *,
    direction: str,
    anchor: float,
    atr: float,
    config: HistoricalCampaignConfig,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
) -> dict[str, Any] | None:
    """Trace one frozen signal through a common maximum horizon.

    Every horizon observes the same entry, stop, target and future candle path.
    Stop/target ambiguity inside one candle is resolved conservatively as stop-first.
    """

    ordered_horizons = tuple(sorted({int(value) for value in horizons}))
    if not ordered_horizons or ordered_horizons[0] <= 0:
        raise ValueError("horizons_must_be_positive")
    maximum_horizon = ordered_horizons[-1]
    entry_index = signal_index + 1
    final_required_index = entry_index + maximum_horizon - 1
    if entry_index >= len(session) or final_required_index >= len(session):
        return None

    entry_row = session.iloc[entry_index]
    entry_price = float(entry_row["open"])
    if direction == "BUY_CALL":
        stop_price = anchor - config.stop_atr_buffer * atr
        risk = entry_price - stop_price
        target_price = entry_price + config.target_rr * risk
    else:
        stop_price = anchor + config.stop_atr_buffer * atr
        risk = stop_price - entry_price
        target_price = entry_price - config.target_rr * risk
    if not math.isfinite(risk) or risk <= 0 or risk / entry_price > 0.02:
        return None

    first_touch_reason: str | None = None
    first_touch_bar: int | None = None
    first_touch_index: int | None = None
    first_touch_price: float | None = None
    for bar_number, index in enumerate(range(entry_index, final_required_index + 1), start=1):
        row = session.iloc[index]
        stop_hit = float(row["low"]) <= stop_price if direction == "BUY_CALL" else float(row["high"]) >= stop_price
        target_hit = float(row["high"]) >= target_price if direction == "BUY_CALL" else float(row["low"]) <= target_price
        if stop_hit:
            first_touch_reason = "STOP_AND_TARGET_SAME_BAR_STOP_FIRST" if target_hit else "STOP"
            first_touch_bar = bar_number
            first_touch_index = index
            first_touch_price = stop_price
            break
        if target_hit:
            first_touch_reason = "TARGET"
            first_touch_bar = bar_number
            first_touch_index = index
            first_touch_price = target_price
            break

    horizon_marks: dict[str, dict[str, Any]] = {}
    for horizon in ordered_horizons:
        index = entry_index + horizon - 1
        row = session.iloc[index]
        horizon_marks[str(horizon)] = {
            "index": index,
            "timestamp": pd.Timestamp(row["timestamp"]).isoformat(),
            "close": float(row["close"]),
        }

    return {
        "signal_index": signal_index,
        "entry_index": entry_index,
        "entry_timestamp": pd.Timestamp(entry_row["timestamp"]).isoformat(),
        "entry_price": entry_price,
        "direction": direction,
        "anchor": anchor,
        "atr": atr,
        "risk_points": risk,
        "stop_price": stop_price,
        "target_price": target_price,
        "first_touch_reason": first_touch_reason,
        "first_touch_bar": first_touch_bar,
        "first_touch_index": first_touch_index,
        "first_touch_price": first_touch_price,
        "horizon_marks": horizon_marks,
        "maximum_horizon_bars": maximum_horizon,
    }


def resolve_trace_at_horizon(trace: dict[str, Any], horizon: int, *, cost_bps: float) -> dict[str, Any]:
    touch_bar = trace.get("first_touch_bar")
    if touch_bar is not None and int(touch_bar) <= horizon:
        raw_reason = str(trace["first_touch_reason"])
        reason = "STOP" if raw_reason in STOP_REASONS else "TARGET"
        exit_price = float(trace["first_touch_price"])
        exit_index = int(trace["first_touch_index"])
        hold_bars = int(touch_bar)
        same_bar_ambiguity = raw_reason == "STOP_AND_TARGET_SAME_BAR_STOP_FIRST"
        exit_timestamp = None
    else:
        mark = trace["horizon_marks"][str(horizon)]
        reason = "TIMEOUT"
        exit_price = float(mark["close"])
        exit_index = int(mark["index"])
        hold_bars = horizon
        same_bar_ambiguity = False
        exit_timestamp = str(mark["timestamp"])
    gross = _gross_return_bps(str(trace["direction"]), float(trace["entry_price"]), exit_price)
    return {
        "session_date": str(trace["session_date"]),
        "setup_id": str(trace["setup_id"]),
        "signal_index": int(trace["signal_index"]),
        "entry_index": int(trace["entry_index"]),
        "exit_index": exit_index,
        "entry_timestamp": str(trace["entry_timestamp"]),
        "exit_timestamp": exit_timestamp,
        "direction": str(trace["direction"]),
        "horizon_bars": horizon,
        "exit_reason": reason,
        "same_bar_ambiguity": same_bar_ambiguity,
        "hold_bars": hold_bars,
        "gross_return_bps": gross,
        "net_return_bps": gross - cost_bps,
    }


def generate_signal_traces(
    frame: pd.DataFrame,
    config: HistoricalCampaignConfig,
    *,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Generate a fixed signal cohort with a complete 60-minute causal path."""

    ordered_horizons = tuple(sorted({int(value) for value in horizons}))
    maximum_horizon = ordered_horizons[-1]
    prepared = prepare_features(frame, timezone=config.timezone)
    classifier = MovementRegimeClassifier()
    traces: list[dict[str, Any]] = []
    seen_setup_ids: set[str] = set()
    diagnostics = Counter()

    for session_date, session in prepared.groupby("session_date", sort=True):
        session = session.sort_values("timestamp").reset_index(drop=True)
        if float(session["volume"].sum()) <= 0:
            diagnostics["zero_volume_sessions"] += 1
            continue
        timestamps = pd.to_datetime(session["timestamp"])
        gap_flags = timestamps.diff().ne(pd.Timedelta(minutes=1)).astype(int)
        gap_flags.iloc[0] = 0
        gap_prefix = gap_flags.cumsum().to_numpy()
        start_ts = pd.Timestamp(session.iloc[0]["timestamp"])

        for index in range(30, len(session) - 1):
            row = session.iloc[index]
            if any(pd.isna(row.get(name)) for name in ("vwap", "atr", "atr_short", "atr_long", "vwap_slope")):
                continue
            history = session.iloc[index - 3 : index + 1]
            spot = float(row["close"])
            vwap = float(row["vwap"])
            call_possible, put_possible, support, resistance = _necessary_structure(history, spot=spot, vwap=vwap)
            if not call_possible and not put_possible:
                continue
            diagnostics["prefilter_checkpoints"] += 1

            entry_index = index + 1
            final_required_index = entry_index + maximum_horizon - 1
            if final_required_index >= len(session):
                diagnostics["excluded_insufficient_future_bars"] += 1
                continue
            path_start = index - 3
            if int(gap_prefix[final_required_index] - gap_prefix[path_start]) > 0:
                diagnostics["excluded_data_gap"] += 1
                continue

            current_ts = pd.Timestamp(row["timestamp"])
            context = StrategyContext(
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
                completed_bar_history=[bar_payload(bar, timezone=config.timezone) for _, bar in history.iterrows()],
                atr=float(row["atr"]),
                atr_short=float(row["atr_short"]),
                atr_long=float(row["atr_long"]),
                range_width_pct=float(row["range_width_pct"]) if not pd.isna(row["range_width_pct"]) else None,
                volume_z=float(row["volume_z"]) if not pd.isna(row["volume_z"]) else None,
                time_of_day=current_ts.strftime("%H:%M"),
                minutes_since_open=int((current_ts - start_ts).total_seconds() // 60),
                metadata={"historical_horizon_sweep": True, "source": "aeron7_nifty_futures"},
            )
            regime = classifier.classify(context)
            for candidate in generate_trend_pullback_candidates(context, regime):
                if candidate.direction == "BUY_CALL" and not call_possible:
                    continue
                if candidate.direction == "BUY_PUT" and not put_possible:
                    continue
                identity = candidate.evidence.get("setup_identity") or {}
                setup_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
                if setup_id in seen_setup_ids:
                    diagnostics["duplicate_setup_ids"] += 1
                    continue
                anchor = support if candidate.direction == "BUY_CALL" else resistance
                trace = trace_signal_path(
                    session,
                    index,
                    direction=candidate.direction,
                    anchor=anchor,
                    atr=float(row["atr"]),
                    config=config,
                    horizons=ordered_horizons,
                )
                if trace is None:
                    diagnostics["excluded_invalid_geometry"] += 1
                    continue
                seen_setup_ids.add(setup_id)
                traces.append({
                    **trace,
                    "session_date": str(session_date),
                    "signal_timestamp": (current_ts + pd.Timedelta(minutes=1)).isoformat(),
                    "setup_id": setup_id,
                    "setup_identity": identity,
                    "raw_score": float(candidate.raw_score),
                    "primary_regime": regime.primary_regime,
                    "trend_up_score": float(regime.scores.get("TREND_UP", 0.0)),
                    "trend_down_score": float(regime.scores.get("TREND_DOWN", 0.0)),
                })
                diagnostics["signals_with_full_horizon"] += 1
                break

    diagnostics["unique_setup_ids"] = len(seen_setup_ids)
    return traces, dict(diagnostics)


def _select_one_position_at_a_time(resolved: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    selected: list[dict[str, Any]] = []
    occupied_through: dict[str, int] = {}
    skipped = 0
    for trade in sorted(resolved, key=lambda item: (item["session_date"], item["entry_index"], item["setup_id"])):
        session_date = str(trade["session_date"])
        if int(trade["entry_index"]) <= occupied_through.get(session_date, -1):
            skipped += 1
            continue
        selected.append(trade)
        occupied_through[session_date] = int(trade["exit_index"])
    return selected, skipped


def summarize_horizon(trades: list[dict[str, Any]]) -> dict[str, Any]:
    reason_counts = Counter(str(trade["exit_reason"]) for trade in trades)
    losses_by_reason = Counter(
        str(trade["exit_reason"]) for trade in trades if float(trade["net_return_bps"]) < 0
    )
    timeout_trades = [trade for trade in trades if trade["exit_reason"] == "TIMEOUT"]
    hold_values = [int(trade["hold_bars"]) for trade in trades]
    returns = [float(trade["net_return_bps"]) for trade in trades]
    metrics = summarize_returns(returns)
    total = len(trades)
    return {
        **metrics,
        "stop_count": reason_counts["STOP"],
        "target_count": reason_counts["TARGET"],
        "timeout_count": reason_counts["TIMEOUT"],
        "stop_rate": reason_counts["STOP"] / total if total else 0.0,
        "target_rate": reason_counts["TARGET"] / total if total else 0.0,
        "timeout_rate": reason_counts["TIMEOUT"] / total if total else 0.0,
        "same_bar_stop_first_count": sum(bool(trade.get("same_bar_ambiguity")) for trade in trades),
        "average_hold_bars": mean(hold_values) if hold_values else None,
        "median_hold_bars": median(hold_values) if hold_values else None,
        "stop_losses": losses_by_reason["STOP"],
        "timeout_losses": losses_by_reason["TIMEOUT"],
        "timeout_wins": sum(float(trade["net_return_bps"]) > 0 for trade in timeout_trades),
        "timeout_average_net_bps": mean(float(trade["net_return_bps"]) for trade in timeout_trades) if timeout_trades else None,
    }


def _first_touch_distribution(traces: list[dict[str, Any]], maximum_horizon: int) -> dict[str, Any]:
    bars: dict[str, dict[str, int]] = {
        str(bar): {"STOP": 0, "TARGET": 0} for bar in range(1, maximum_horizon + 1)
    }
    unresolved = 0
    stop_bars: list[int] = []
    target_bars: list[int] = []
    for trace in traces:
        bar = trace.get("first_touch_bar")
        reason = trace.get("first_touch_reason")
        if bar is None or reason is None:
            unresolved += 1
            continue
        normalized = "STOP" if str(reason) in STOP_REASONS else "TARGET"
        bars[str(int(bar))][normalized] += 1
        (stop_bars if normalized == "STOP" else target_bars).append(int(bar))
    return {
        "by_bar": bars,
        "unresolved_at_maximum_horizon": unresolved,
        "average_stop_hit_bar": mean(stop_bars) if stop_bars else None,
        "median_stop_hit_bar": median(stop_bars) if stop_bars else None,
        "average_target_hit_bar": mean(target_bars) if target_bars else None,
        "median_target_hit_bar": median(target_bars) if target_bars else None,
    }


def _later_outcomes_for_timeouts(traces: list[dict[str, Any]], horizon: int, maximum_horizon: int) -> dict[str, Any]:
    unresolved = [
        trace for trace in traces
        if trace.get("first_touch_bar") is None or int(trace["first_touch_bar"]) > horizon
    ]
    counts = Counter()
    for trace in unresolved:
        touch_bar = trace.get("first_touch_bar")
        reason = trace.get("first_touch_reason")
        if touch_bar is None or int(touch_bar) > maximum_horizon:
            counts["STILL_UNRESOLVED"] += 1
        elif str(reason) in STOP_REASONS:
            counts["LATER_STOP"] += 1
        else:
            counts["LATER_TARGET"] += 1
    total = len(unresolved)
    return {
        "timeout_cohort": total,
        "later_stop_by_maximum": counts["LATER_STOP"],
        "later_target_by_maximum": counts["LATER_TARGET"],
        "still_unresolved_at_maximum": counts["STILL_UNRESOLVED"],
        "later_stop_rate": counts["LATER_STOP"] / total if total else 0.0,
        "later_target_rate": counts["LATER_TARGET"] / total if total else 0.0,
        "still_unresolved_rate": counts["STILL_UNRESOLVED"] / total if total else 0.0,
    }


def _scope_sweep(
    traces: list[dict[str, Any]],
    sessions: list[str],
    horizons: tuple[int, ...],
    config: HistoricalCampaignConfig,
    *,
    wfa_sessions: list[str] | None = None,
) -> dict[str, Any]:
    allowed = set(sessions)
    scope_traces = [trace for trace in traces if trace["session_date"] in allowed]
    horizon_results: dict[str, Any] = {}
    for horizon in horizons:
        fixed = [resolve_trace_at_horizon(trace, horizon, cost_bps=config.round_trip_cost_bps) for trace in scope_traces]
        operational, skipped = _select_one_position_at_a_time(fixed)
        result: dict[str, Any] = {
            "fixed_signal_cohort": summarize_horizon(fixed),
            "one_position_at_a_time": {
                **summarize_horizon(operational),
                "overlapping_signals_skipped": skipped,
            },
            "timeouts_then_later_outcomes": _later_outcomes_for_timeouts(scope_traces, horizon, horizons[-1]),
        }
        if wfa_sessions is not None:
            result["walk_forward"] = _walk_forward(operational, wfa_sessions, config)
        horizon_results[str(horizon)] = result
    return {
        "session_count": len(sessions),
        "fixed_signal_count": len(scope_traces),
        "horizons": horizon_results,
        "first_touch_distribution": _first_touch_distribution(scope_traces, horizons[-1]),
    }


def run_horizon_sweep(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    source_repository: str,
    source_commit: str,
    config: HistoricalCampaignConfig | None = None,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
) -> dict[str, Any]:
    config = config or HistoricalCampaignConfig(max_hold_bars=60)
    ordered_horizons = tuple(sorted({int(value) for value in horizons}))
    if ordered_horizons != DEFAULT_HORIZONS:
        raise ValueError(f"expected_horizons:{DEFAULT_HORIZONS}")
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_path = Path(input_path).expanduser().resolve()

    try:
        frame = load_canonical_candles(source_path, timezone=config.timezone)
        frame = frame[frame["symbol"] == config.symbol].copy()
        if frame.empty:
            raise HistoricalCampaignError(f"symbol_not_found:{config.symbol}")
        if float(frame["volume"].sum()) <= 0:
            raise HistoricalCampaignError("zero_volume_dataset_invalid_for_vwap_strategy")
        sessions = sorted(frame["timestamp"].dt.tz_convert(config.timezone).dt.date.astype(str).unique().tolist())
        partitions = _partition_sessions(sessions, config)
        traces, diagnostics = generate_signal_traces(frame, config, horizons=ordered_horizons)
        development_sessions = partitions["train"] + partitions["validation"]
        wfa_sessions = [session for session in sessions if session not in set(partitions["holdout"])]
        development = _scope_sweep(traces, development_sessions, ordered_horizons, config, wfa_sessions=wfa_sessions)
        holdout = _scope_sweep(traces, partitions["holdout"], ordered_horizons, config)
        all_sessions = _scope_sweep(traces, sessions, ordered_horizons, config)

        def selection_key(horizon: int) -> tuple[float, float, int]:
            item = development["horizons"][str(horizon)]
            wfa_fraction = float(item["walk_forward"]["positive_fold_fraction"])
            expectancy = item["one_position_at_a_time"]["net_expectancy_bps"]
            return (wfa_fraction, float(expectancy or -math.inf), -horizon)

        selected_horizon = max(ordered_horizons, key=selection_key)
        selected_holdout = holdout["horizons"][str(selected_horizon)]["one_position_at_a_time"]
        selected_wfa = development["horizons"][str(selected_horizon)]["walk_forward"]
        recovery = bool(
            selected_holdout["trades"] >= config.minimum_holdout_trades
            and float(selected_holdout["net_expectancy_bps"] or 0.0) > 0.0
            and float(selected_holdout["profit_factor"] or 0.0) >= config.minimum_holdout_profit_factor
            and float(selected_wfa["positive_fold_fraction"]) >= config.minimum_positive_wfa_fraction
        )
        result = {
            "schema_version": 1,
            "verdict": "DIAGNOSTIC_HORIZON_RECOVERY_REQUIRES_FRESH_HOLDOUT" if recovery else "NO_HORIZON_RECOVERY",
            "claim_scope": "diagnostic_underlying_futures_horizon_analysis_only",
            "certification_eligible": False,
            "holdout_reused_for_diagnostics": True,
            "fresh_holdout_required_for_any_promotion": True,
            "strategy_code_modified": False,
            "options_execution_certified": False,
            "live_trading_allowed": False,
            "horizons_minutes": list(ordered_horizons),
            "fixed_signal_cohort_rule": "signals_require_complete_gap_free_60_minute_future_path",
            "same_bar_ambiguity_policy": "stop_first",
            "development_selected_horizon": selected_horizon,
            "selected_horizon_holdout_metrics": selected_holdout,
            "selected_horizon_wfa": selected_wfa,
            "config": asdict(config),
            "dataset_manifest": {
                "source_repository": source_repository,
                "source_commit": source_commit,
                "input_path": str(source_path),
                "input_sha256": sha256_file(source_path),
                "symbol": config.symbol,
                "rows": len(frame),
                "sessions": len(sessions),
                "timestamp_start": frame["timestamp"].min().isoformat(),
                "timestamp_end": frame["timestamp"].max().isoformat(),
                "volume_sum": float(frame["volume"].sum()),
            },
            "diagnostics": diagnostics,
            "partitions": partitions,
            "development": development,
            "holdout": holdout,
            "all_sessions": all_sessions,
        }
    except HistoricalCampaignError as exc:
        traces = []
        result = {
            "schema_version": 1,
            "verdict": "INVALID_DUE_TO_DATA",
            "blockers": [str(exc)],
            "claim_scope": "no_edge_claim",
            "certification_eligible": False,
            "options_execution_certified": False,
            "live_trading_allowed": False,
        }

    (output / "horizon_sweep_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    with (output / "signal_traces.jsonl").open("w", encoding="utf-8") as handle:
        for trace in traces:
            handle.write(json.dumps(trace, sort_keys=True, default=str) + "\n")

    lines = [
        "# TREND_PULLBACK horizon sweep",
        "",
        f"**Verdict:** `{result['verdict']}`",
        "",
        "The same eligible signals are followed for a complete 60-minute path. Each five-minute horizon distinguishes stop, target, and timeout outcomes. The one-position-at-a-time view separately models overlapping-signal suppression.",
        "",
    ]
    if result.get("verdict") != "INVALID_DUE_TO_DATA":
        lines.extend([
            f"Development-selected horizon: **{result['development_selected_horizon']} minutes**",
            "",
            "This is diagnostic only because the existing holdout is examined across multiple horizons. A new untouched period is required before promotion.",
        ])
    (output / "horizon_sweep_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run fixed-signal TREND_PULLBACK holding-horizon analysis")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--source-repository", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--minimum-sessions", type=int, default=300)
    args = parser.parse_args(argv)
    config = HistoricalCampaignConfig(minimum_sessions=args.minimum_sessions, max_hold_bars=60)
    result = run_horizon_sweep(
        args.input,
        args.output_dir,
        source_repository=args.source_repository,
        source_commit=args.source_commit,
        config=config,
    )
    print(json.dumps({
        "verdict": result["verdict"],
        "development_selected_horizon": result.get("development_selected_horizon"),
        "selected_horizon_holdout_metrics": result.get("selected_horizon_holdout_metrics"),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
