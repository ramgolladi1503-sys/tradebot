from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .data import load_canonical_candles
from .engine import generate_trades
from .models import HistoricalCampaignConfig, HistoricalCampaignError, sha256_file, summarize_returns


def _partition_sessions(sessions: list[str], config: HistoricalCampaignConfig) -> dict[str, list[str]]:
    if len(sessions) < config.minimum_sessions:
        raise HistoricalCampaignError(f"insufficient_sessions:{len(sessions)}<{config.minimum_sessions}")
    holdout_count = max(10, int(len(sessions) * config.holdout_fraction))
    holdout_start = len(sessions) - holdout_count
    purge = config.boundary_purge_sessions
    train_pool = sessions[: max(0, holdout_start - purge)]
    holdout = sessions[min(len(sessions), holdout_start + purge) :]
    validation_count = max(10, int(len(train_pool) * 0.20))
    validation_start = len(train_pool) - validation_count
    train = train_pool[: max(0, validation_start - purge)]
    validation = train_pool[min(len(train_pool), validation_start + purge) :]
    return {"train": train, "validation": validation, "holdout": holdout}


def _metrics_for_sessions(trades: list[dict[str, Any]], sessions: list[str], cost_bps: float) -> dict[str, Any]:
    allowed = set(sessions)
    returns = [float(trade["gross_return_bps"]) - cost_bps for trade in trades if trade["session_date"] in allowed]
    return {**summarize_returns(returns), "session_count": len(sessions)}


def _walk_forward(trades: list[dict[str, Any]], sessions: list[str], config: HistoricalCampaignConfig) -> dict[str, Any]:
    folds: list[dict[str, Any]] = []
    positive = start = 0
    while start + config.train_sessions + config.validation_sessions <= len(sessions):
        train = sessions[start : start + config.train_sessions]
        validation_start = start + config.train_sessions + config.boundary_purge_sessions
        validation = sessions[validation_start : validation_start + config.validation_sessions]
        if len(validation) < config.validation_sessions:
            break
        metrics = _metrics_for_sessions(trades, validation, config.round_trip_cost_bps)
        is_positive = bool(metrics["trades"] and (metrics["net_expectancy_bps"] or 0.0) > 0.0)
        positive += int(is_positive)
        folds.append({
            "fold": len(folds) + 1, "train_start": train[0], "train_end": train[-1],
            "validation_start": validation[0], "validation_end": validation[-1],
            "metrics": metrics, "positive": is_positive,
        })
        start += config.step_sessions
    return {
        "folds": folds, "fold_count": len(folds),
        "positive_fold_fraction": positive / len(folds) if folds else 0.0,
        "parameters_frozen": True, "optimization_performed": False,
    }


def _concentration(trades: list[dict[str, Any]], sessions: list[str], cost_bps: float) -> dict[str, Any]:
    totals: dict[str, float] = {}
    allowed = set(sessions)
    for trade in trades:
        if trade["session_date"] in allowed:
            totals[trade["session_date"]] = totals.get(trade["session_date"], 0.0) + float(trade["gross_return_bps"]) - cost_bps
    positive = sorted((value for value in totals.values() if value > 0), reverse=True)
    total_positive = sum(positive)
    return {
        "sessions_with_trades": len(totals),
        "best_session_net_bps": max(totals.values()) if totals else None,
        "worst_session_net_bps": min(totals.values()) if totals else None,
        "top_five_session_positive_share": sum(positive[:5]) / total_positive if total_positive > 0 else 0.0,
    }


def run_historical_campaign(input_path: str | Path, output_dir: str | Path, *, source_repository: str, source_commit: str, config: HistoricalCampaignConfig | None = None) -> dict[str, Any]:
    config = config or HistoricalCampaignConfig()
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_path = Path(input_path).expanduser().resolve()
    try:
        frame = load_canonical_candles(source_path, timezone=config.timezone)
        frame = frame[frame["symbol"] == config.symbol].copy()
        if frame.empty:
            raise HistoricalCampaignError(f"symbol_not_found:{config.symbol}")
        sessions = sorted(frame["timestamp"].dt.tz_convert(config.timezone).dt.date.astype(str).unique().tolist())
        if float(frame["volume"].sum()) <= 0:
            raise HistoricalCampaignError("zero_volume_dataset_invalid_for_vwap_strategy")
        partitions = _partition_sessions(sessions, config)
        trades, diagnostics = generate_trades(frame, config)
        metrics = {name: _metrics_for_sessions(trades, values, config.round_trip_cost_bps) for name, values in partitions.items()}
        wfa_sessions = [session for session in sessions if session not in set(partitions["holdout"])]
        wfa = _walk_forward(trades, wfa_sessions, config)
        holdout = metrics["holdout"]
        cost_stress = {
            "baseline": _metrics_for_sessions(trades, partitions["holdout"], config.round_trip_cost_bps),
            "adverse": _metrics_for_sessions(trades, partitions["holdout"], config.adverse_cost_bps),
            "severe": _metrics_for_sessions(trades, partitions["holdout"], config.severe_cost_bps),
        }
        concentration = _concentration(trades, partitions["holdout"], config.round_trip_cost_bps)
        blockers: list[str] = []
        if len(trades) < config.minimum_total_trades: blockers.append(f"insufficient_total_trades:{len(trades)}")
        if int(holdout["trades"]) < config.minimum_holdout_trades: blockers.append(f"insufficient_holdout_trades:{holdout['trades']}")
        if holdout["net_expectancy_bps"] is None or float(holdout["net_expectancy_bps"]) <= 0: blockers.append(f"holdout_expectancy_non_positive:{holdout['net_expectancy_bps']}")
        if holdout["profit_factor"] is None or float(holdout["profit_factor"]) < config.minimum_holdout_profit_factor: blockers.append(f"holdout_profit_factor_below_gate:{holdout['profit_factor']}")
        if float(wfa["positive_fold_fraction"]) < config.minimum_positive_wfa_fraction: blockers.append(f"positive_wfa_fraction_below_gate:{wfa['positive_fold_fraction']}")
        adverse = cost_stress["adverse"]["net_expectancy_bps"]
        if adverse is None or float(adverse) <= 0: blockers.append(f"adverse_cost_expectancy_non_positive:{adverse}")
        if concentration["top_five_session_positive_share"] > config.maximum_top_five_session_positive_share: blockers.append(f"session_concentration_above_gate:{concentration['top_five_session_positive_share']}")
        manifest = {
            "source_repository": source_repository, "source_commit": source_commit,
            "input_path": str(source_path), "input_sha256": sha256_file(source_path),
            "symbol": config.symbol, "rows": len(frame), "sessions": len(sessions),
            "timestamp_start": frame["timestamp"].min().isoformat(), "timestamp_end": frame["timestamp"].max().isoformat(),
            "volume_sum": float(frame["volume"].sum()),
        }
        result = {
            "schema_version": 1, "verdict": "STRUCTURAL_EDGE_CANDIDATE" if not blockers else "NO_STRUCTURAL_EDGE",
            "blockers": blockers, "claim_scope": "underlying_futures_structural_research_only",
            "options_execution_certified": False, "live_trading_allowed": False, "strategy_code_modified": False,
            "strategy_callable": "strategies.movement.trend_pullback.generate_trend_pullback_candidates",
            "regime_classifier": "core.movement_regime.MovementRegimeClassifier",
            "entry_timing": "next_bar_open_after_trigger_bar_end", "same_bar_ambiguity_policy": "stop_first",
            "config": asdict(config), "dataset_manifest": manifest, "diagnostics": diagnostics,
            "partitions": {name: {"sessions": values, "metrics": metrics[name]} for name, values in partitions.items()},
            "walk_forward": wfa, "cost_stress": cost_stress, "concentration": concentration,
        }
    except HistoricalCampaignError as exc:
        trades = []
        result = {
            "schema_version": 1, "verdict": "INVALID_DUE_TO_DATA", "blockers": [str(exc)],
            "claim_scope": "no_edge_claim", "options_execution_certified": False,
            "live_trading_allowed": False, "strategy_code_modified": False, "config": asdict(config),
        }
    (output / "dataset_manifest.json").write_text(json.dumps(result.get("dataset_manifest", {}), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (output / "trades.jsonl").open("w", encoding="utf-8") as handle:
        for trade in trades: handle.write(json.dumps(trade, sort_keys=True, default=str) + "\n")
    (output / "campaign_result.json").write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    lines = ["# TREND_PULLBACK_v1 historical campaign", "", f"**Verdict:** `{result['verdict']}`", "", f"**Claim scope:** `{result['claim_scope']}`", "", "This campaign uses the production strategy callable and production movement-regime classifier, enters only on the next bar, deducts fixed costs, applies an untouched holdout, and never claims executable option profitability.", "", "## Blockers", ""]
    lines.extend([f"- `{blocker}`" for blocker in result.get("blockers", [])] or ["- None"])
    (output / "campaign_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result
