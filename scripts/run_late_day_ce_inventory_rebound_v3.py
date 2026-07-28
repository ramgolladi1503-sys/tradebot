#!/usr/bin/env python3
"""Freeze and test the late-day CE inventory-rebound candidate on untouched holdout.

Research-universe formulation, frozen before holdout access:
- NIFTY CE only;
- completed five-minute observation at or after 13:00 IST;
- CE return in the prior-session-data 10th percentile or lower;
- CE volume ratio in the 90th percentile or higher;
- CE return acceleration in the 10th percentile or lower;
- same-strike PE return in the 80th percentile or higher;
- CE-minus-PE response asymmetry in the 10th percentile or lower;
- next-open CE premium between INR 30 and INR 150;
- first eligible occurrence per session;
- buy at the next one-minute/open proxy already present in the governed event corpus;
- evaluate the existing fixed 20-minute forward close outcome;
- normal cost stress 5 bps/side; severe stress 50 bps/side.

The script first reconstructs expanding OOF evidence from the first 75% of
sessions. It materializes the latest 25% holdout only if every frozen OOF gate
passes. Holdout is tested once. Direction-flip (same-strike PE) and five-minute
delayed CE controls are evaluated without changing the frozen candidate.

Research only. No broker/provider calls or order actions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scripts import run_extreme_option_pressure_discovery_v2 as research
from scripts import run_option_surface_transition_discovery_v1 as base
from scripts.run_conditional_precursor_discrimination_v2 import PRIOR_REL, stable_json

OUT_REL = Path("runtime/research/late_day_ce_inventory_rebound_v3")
RESEARCH_REL = Path("research/late_day_ce_inventory_rebound_v3")
EVENT_FILE = "event_universe_5m.parquet"


def semantic_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def candidate_mask(frame: pd.DataFrame, cut: dict[str, float]) -> pd.Series:
    return (
        frame["option_type"].eq("CE")
        & (frame["minute_of_day"] >= 780)
        & (frame["prior_5m_return_pct"] <= cut["ret_p10"])
        & (frame["prior_5m_volume_ratio"] >= cut["volume_p90"])
        & (frame["return_acceleration"] <= cut["accel_p10"])
        & (frame["mirror_return"] >= cut["ret_p80"])
        & (frame["option_asymmetry"] <= cut["asym_p10"])
        & frame["entry_price_next_open"].between(30.0, 150.0, inclusive="both")
        & frame["days_to_expiry"].between(0, 7, inclusive="both")
        & (frame["surface_count"] >= 3)
        & (frame["volume"] > 0)
    )


def select_candidate(frame: pd.DataFrame, cut: dict[str, float], sessions: list[str]) -> pd.DataFrame:
    signals = research.select_signal(
        frame,
        candidate_mask(frame, cut),
        "late_day_ce_inventory_rebound_v3",
        sessions,
    )
    return signals


def oof_gate(metric: research.Metrics) -> bool:
    return bool(
        metric.trades >= 30
        and metric.profit_factor is not None
        and metric.profit_factor >= 1.50
        and metric.mean_return_pct is not None
        and metric.mean_return_pct > 0
        and metric.median_return_pct is not None
        and metric.median_return_pct > 0
        and metric.remove_top_two_profit_factor is not None
        and metric.remove_top_two_profit_factor >= 1.25
        and metric.stress_profit_factor is not None
        and metric.stress_profit_factor >= 1.25
        and metric.bootstrap_mean_ci_low is not None
        and metric.bootstrap_mean_ci_low > 0
        and metric.total_folds == 4
        and metric.positive_folds == 4
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.25)
    )


def _two_half_positive(trades: pd.DataFrame) -> bool:
    if len(trades) < 10:
        return False
    ordered = trades.sort_values(["session_id", "timestamp"]).reset_index(drop=True)
    halves = [half for half in np.array_split(np.arange(len(ordered)), 2) if len(half) >= 5]
    return len(halves) == 2 and all(float(ordered.iloc[index]["net_return_pct"].mean()) > 0 for index in halves)


def holdout_primary_gate(metric: research.Metrics, trades: pd.DataFrame) -> bool:
    return bool(
        metric.trades >= 10
        and metric.profit_factor is not None
        and metric.profit_factor >= 1.25
        and metric.mean_return_pct is not None
        and metric.mean_return_pct > 0
        and metric.median_return_pct is not None
        and metric.median_return_pct > 0
        and metric.remove_top_two_profit_factor is not None
        and metric.remove_top_two_profit_factor >= 1.05
        and metric.stress_profit_factor is not None
        and metric.stress_profit_factor >= 1.05
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.35)
        and _two_half_positive(trades)
    )


def mirror_pe_signals(signals: pd.DataFrame, holdout_frame: pd.DataFrame) -> pd.DataFrame:
    if signals.empty:
        return signals.copy()
    desired = signals[["session_id", "timestamp", "expiry_id", "strike"]].copy()
    desired["option_type"] = "PE"
    mirror = holdout_frame.merge(
        desired,
        on=["session_id", "timestamp", "expiry_id", "strike", "option_type"],
        how="inner",
        validate="many_to_one",
    )
    mirror = mirror.sort_values(
        ["session_id", "timestamp", "entry_price_next_open", "expired_instrument_key"],
        kind="mergesort",
    )
    mirror = mirror.drop_duplicates("session_id", keep="first").copy()
    mirror["mechanism"] = "same_strike_pe_direction_flip_control"
    return mirror


def delayed_ce_signals(signals: pd.DataFrame, holdout_frame: pd.DataFrame) -> pd.DataFrame:
    if signals.empty:
        return signals.copy()
    ordered = holdout_frame.sort_values(
        ["expired_instrument_key", "session_id", "timestamp"],
        kind="mergesort",
    ).copy()
    grouped = ordered.groupby(["expired_instrument_key", "session_id"], sort=False, observed=True)
    ordered["previous_timestamp"] = grouped["timestamp"].shift(1)
    desired = signals[["session_id", "expired_instrument_key", "timestamp"]].rename(
        columns={"timestamp": "previous_timestamp"}
    )
    delayed = ordered.merge(
        desired,
        on=["session_id", "expired_instrument_key", "previous_timestamp"],
        how="inner",
        validate="many_to_one",
    )
    delayed = delayed.loc[delayed["option_type"].eq("CE")].copy()
    delayed = delayed.sort_values(["session_id", "timestamp", "expired_instrument_key"], kind="mergesort")
    delayed = delayed.drop_duplicates("session_id", keep="first")
    delayed["mechanism"] = "five_minute_delayed_ce_control"
    return delayed


def control_gate(
    primary: research.Metrics,
    mirror: research.Metrics,
    delayed: research.Metrics,
) -> bool:
    mirror_pf = mirror.profit_factor if mirror.profit_factor is not None else 0.0
    delayed_pf = delayed.profit_factor if delayed.profit_factor is not None else 0.0
    mirror_mean = mirror.mean_return_pct if mirror.mean_return_pct is not None else -math.inf
    delayed_mean = delayed.mean_return_pct if delayed.mean_return_pct is not None else -math.inf
    primary_pf = primary.profit_factor if primary.profit_factor is not None else 0.0
    primary_mean = primary.mean_return_pct if primary.mean_return_pct is not None else -math.inf
    return bool(
        mirror.trades >= max(5, int(primary.trades * 0.50))
        and primary_pf >= mirror_pf + 0.25
        and primary_mean > mirror_mean
        and delayed.trades >= max(5, int(primary.trades * 0.60))
        and delayed_pf >= 1.00
        and delayed_mean > 0
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.repo_root.resolve()
    event_path = root / PRIOR_REL / EVENT_FILE
    out = root / OUT_REL
    research_dir = root / RESEARCH_REL
    out.mkdir(parents=True, exist_ok=True)
    research_dir.mkdir(parents=True, exist_ok=True)

    causal = research.prepare_causal(event_path)
    research_sessions, holdout_sessions = research.research_holdout_sessions(causal)
    folds = research.expanding_folds(research_sessions)

    contract = {
        "candidate_id": "late_day_ce_inventory_rebound_v3",
        "side": "BUY_CE_ONLY",
        "session_gate": "minute_of_day_gte_780",
        "ce_return_gate": "development_prior_5m_return_p10_or_lower",
        "ce_volume_gate": "development_prior_5m_volume_ratio_p90_or_higher",
        "ce_acceleration_gate": "development_return_acceleration_p10_or_lower",
        "mirror_pe_gate": "development_mirror_return_p80_or_higher",
        "asymmetry_gate": "development_ce_minus_pe_asymmetry_p10_or_lower",
        "entry_premium": {"minimum": 30.0, "maximum": 150.0},
        "dte": {"minimum": 0, "maximum": 7},
        "selection": "first_eligible_occurrence_per_session_then_max_extremity",
        "entry": "governed_next_open_proxy",
        "exit": "existing_fixed_20_minute_forward_close",
        "normal_cost_pct": research.NORMAL_COST_PCT,
        "stress_cost_pct": research.STRESS_COST_PCT,
        "research_sessions": len(research_sessions),
        "holdout_sessions": len(holdout_sessions),
        "holdout_policy": "materialize_once_only_after_exact_oof_gate_pass",
        "controls": ["same_strike_pe_direction_flip", "five_minute_delayed_ce"],
        "research_only": True,
        "allowed_for_live_execution": False,
    }
    contract["semantic_sha256"] = semantic_hash(contract)
    stable_json(out / "frozen_candidate_contract.json", contract)

    research_outcomes = base._load_outcomes(event_path, base._raw_sessions(causal, research_sessions))
    oof_ledgers: list[pd.DataFrame] = []
    fold_records: list[dict[str, Any]] = []
    for training_sessions, testing_sessions, fold_id in folds:
        training = causal.loc[causal["session_id"].isin(training_sessions)]
        testing = causal.loc[causal["session_id"].isin(testing_sessions)]
        cut = research.thresholds(training)
        signals = select_candidate(testing, cut, testing_sessions)
        trades = research.attach(signals, research_outcomes, fold_id)
        if not trades.empty:
            oof_ledgers.append(trades.assign(partition="research_oof"))
        fold_metric = research.calculate_metrics(trades)
        fold_records.append(
            {
                "fold_id": fold_id,
                "thresholds": cut,
                "signals": len(signals),
                "metrics": asdict(fold_metric),
            }
        )

    oof_trades = pd.concat(oof_ledgers, ignore_index=True, sort=False) if oof_ledgers else pd.DataFrame()
    oof_metric = research.calculate_metrics(oof_trades)
    oof_passed = oof_gate(oof_metric)
    stable_json(
        out / "oof_reconstruction.json",
        {
            "folds": fold_records,
            "aggregate": asdict(oof_metric),
            "oof_gate": oof_passed,
            "holdout_outcomes_materialized": oof_passed,
        },
    )

    holdout_primary = pd.DataFrame()
    holdout_mirror = pd.DataFrame()
    holdout_delayed = pd.DataFrame()
    primary_metric = research.calculate_metrics(pd.DataFrame())
    mirror_metric = research.calculate_metrics(pd.DataFrame())
    delayed_metric = research.calculate_metrics(pd.DataFrame())
    primary_passed = False
    controls_passed = False

    if oof_passed:
        final_cut = research.thresholds(causal.loc[causal["session_id"].isin(research_sessions)])
        holdout_frame = causal.loc[causal["session_id"].isin(holdout_sessions)].copy()
        holdout_outcomes = base._load_outcomes(event_path, base._raw_sessions(causal, holdout_sessions))
        primary_signals = select_candidate(holdout_frame, final_cut, holdout_sessions)
        holdout_primary = research.attach(primary_signals, holdout_outcomes, "holdout")
        holdout_mirror = research.attach(
            mirror_pe_signals(primary_signals, holdout_frame),
            holdout_outcomes,
            "holdout_mirror",
        )
        holdout_delayed = research.attach(
            delayed_ce_signals(primary_signals, holdout_frame),
            holdout_outcomes,
            "holdout_delayed",
        )
        primary_metric = research.calculate_metrics(holdout_primary)
        mirror_metric = research.calculate_metrics(holdout_mirror)
        delayed_metric = research.calculate_metrics(holdout_delayed)
        primary_passed = holdout_primary_gate(primary_metric, holdout_primary)
        controls_passed = control_gate(primary_metric, mirror_metric, delayed_metric)

    stable_json(
        out / "untouched_holdout_result.json",
        {
            "holdout_outcomes_materialized": oof_passed,
            "primary": asdict(primary_metric),
            "primary_gate": primary_passed,
            "same_strike_pe_control": asdict(mirror_metric),
            "five_minute_delayed_ce_control": asdict(delayed_metric),
            "control_gate": controls_passed,
        },
    )

    ledgers: list[pd.DataFrame] = []
    if not oof_trades.empty:
        ledgers.append(oof_trades.assign(ledger_role="research_oof_primary"))
    if not holdout_primary.empty:
        ledgers.append(holdout_primary.assign(ledger_role="holdout_primary"))
    if not holdout_mirror.empty:
        ledgers.append(holdout_mirror.assign(ledger_role="holdout_mirror_control"))
    if not holdout_delayed.empty:
        ledgers.append(holdout_delayed.assign(ledger_role="holdout_delayed_control"))
    if ledgers:
        pd.concat(ledgers, ignore_index=True, sort=False).to_csv(out / "trade_ledger.csv", index=False)

    edge_found = bool(oof_passed and primary_passed and controls_passed)
    verdict = (
        "STRUCTURAL_EDGE_FOUND_LATE_DAY_CE_INVENTORY_REBOUND_CANDLE_PROXY"
        if edge_found
        else (
            "FROZEN_CANDIDATE_FAILED_OOF_RECONSTRUCTION"
            if not oof_passed
            else "FROZEN_CANDIDATE_FAILED_UNTOUCHED_HOLDOUT_OR_CONTROLS"
        )
    )
    final = {
        "principal_verdict": verdict,
        "structural_edge_found": edge_found,
        "candidate_id": contract["candidate_id"],
        "oof_gate": oof_passed,
        "holdout_primary_gate": primary_passed,
        "holdout_control_gate": controls_passed,
        "holdout_outcomes_materialized": oof_passed,
        "execution_certification": "BLOCKED_AUTHORITATIVE_TIMESTAMP_ALIGNED_SPREAD_MISSING",
        "paper_or_live_authorized": False,
        "contract_semantic_sha256": contract["semantic_sha256"],
        "research_only": True,
        "allowed_for_live_execution": False,
    }
    stable_json(out / "final_decision.json", final)
    (research_dir / "RESULT.md").write_text(
        "# Late-Day CE Inventory Rebound V3\n\n"
        f"Principal verdict: `{verdict}`\n\n"
        f"Structural edge found: `{edge_found}`\n\n"
        f"OOF metrics: `{json.dumps(asdict(oof_metric), sort_keys=True)}`\n\n"
        f"Holdout primary metrics: `{json.dumps(asdict(primary_metric), sort_keys=True)}`\n\n"
        f"Mirror PE control: `{json.dumps(asdict(mirror_metric), sort_keys=True)}`\n\n"
        f"Five-minute delayed CE control: `{json.dumps(asdict(delayed_metric), sort_keys=True)}`\n\n"
        "Historical candle-proxy survival does not certify executable bid/ask fills or authorize paper/live trading.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
