#!/usr/bin/env python3
"""Peer-reclaim longer-horizon campaign V5.

The selected development near-miss from V4 was delayed_persistent_peer_reclaim:
high occurrence, PF > 1 and positive mean, but negative median, confidence bound,
and 1% stress. V5 freezes the entry mechanism and tests only 10/15/20-minute
fixed exits to determine whether cross-strike repricing is slower than five minutes.

No entry threshold is changed. The latest 15% master holdout remains sealed.
"""
from __future__ import annotations

import argparse
import math
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from scripts import run_cross_strike_diffusion_discovery_v1 as v1
from scripts import run_cross_strike_diffusion_campaign_v2 as splitmod
from scripts import run_selective_option_leadership_campaign_v3 as lead
from scripts import run_post_imbalance_digestion_campaign_v4 as digest
from scripts.run_conditional_precursor_discrimination_v2 import PRIOR_REL, stable_json

OUT_REL = Path("runtime/research/peer_reclaim_horizon_campaign_v5")
RESEARCH_REL = Path("research/peer_reclaim_horizon_campaign_v5")
EVENT_FILE = "event_universe_5m.parquet"
SEED = 20260729
HORIZONS = (10, 15, 20)
CUMULATIVE_MECHANISM_COUNT = 27
BASE_MECHANISM = "delayed_persistent_peer_reclaim"


def attach_exact_horizon(signals: pd.DataFrame, causal: pd.DataFrame, horizon: int, fold_id: str) -> pd.DataFrame:
    if signals.empty:
        return signals.copy()
    trades = signals.copy()
    trades["exit_timestamp"] = trades["timestamp"] + pd.Timedelta(minutes=horizon)
    exits = causal[["expired_instrument_key", "timestamp", "close"]].drop_duplicates(
        ["expired_instrument_key", "timestamp"]
    )
    exits = exits.rename(columns={"timestamp": "exit_timestamp", "close": "exit_close"})
    trades = trades.merge(
        exits,
        on=["expired_instrument_key", "exit_timestamp"],
        how="inner",
        validate="many_to_one",
    )
    trades["gross_return_pct"] = (
        v1._finite(trades["exit_close"]) - v1._finite(trades["entry_price_next_open"])
    ) / v1._finite(trades["entry_price_next_open"]).replace(0, np.nan) * 100.0
    trades["net_return_pct"] = trades["gross_return_pct"] - v1.NORMAL_COST_PCT
    trades["stress_return_pct"] = trades["gross_return_pct"] - v1.STRESS_COST_PCT
    trades["label_horizon_minutes"] = horizon
    trades["fold_id"] = fold_id
    return trades


def shift_signal_entry(signals: pd.DataFrame, causal: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if signals.empty:
        return signals.copy()
    shifted = signals.copy()
    shifted["timestamp"] = shifted["timestamp"] + pd.Timedelta(minutes=minutes)
    refresh_columns = [
        "expired_instrument_key", "timestamp", "entry_price_next_open", "session_id",
        "expiry_id", "option_type", "strike", "days_to_expiry", "minute_of_day",
    ]
    lookup = causal[refresh_columns].drop_duplicates(["expired_instrument_key", "timestamp"])
    preserve = [column for column in shifted.columns if column not in refresh_columns[2:]]
    shifted = shifted[preserve].merge(
        lookup,
        on=["expired_instrument_key", "timestamp", "session_id"],
        how="inner",
        validate="many_to_one",
    )
    return shifted


def oof_gate(metric: v1.Metrics, ci_low: float | None) -> bool:
    return bool(v1.oof_gate(metric) and ci_low is not None and ci_low > 0)


def validation_gate(metric: v1.Metrics, ci_low: float | None) -> bool:
    return bool(splitmod.validation_gate(metric) and ci_low is not None and ci_low > 0)


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

    causal = digest.prepare_causal(event_path)
    partitions = splitmod.partition_sessions(causal)
    folds = splitmod.expanding_folds(partitions["research"])
    contract = {
        "schema_version": "peer_reclaim_horizon_campaign_v5",
        "adaptive_iteration": 4,
        "base_mechanism": BASE_MECHANISM,
        "base_mechanism_selection_reason": "highest_v4_oof_pf_and_mean_among_high_occurrence_near_misses",
        "entry_contract": "unchanged_v4_delayed_persistent_peer_reclaim",
        "fixed_exit_horizons_minutes": list(HORIZONS),
        "horizon_count": len(HORIZONS),
        "cumulative_mechanisms_in_campaign": CUMULATIVE_MECHANISM_COUNT,
        "multiplicity_policy": "session_cluster_bootstrap_lower_quantile_0_05_divided_by_2_times_27",
        "research_sessions": len(partitions["research"]),
        "validation_sessions": len(partitions["validation"]),
        "master_holdout_sessions": len(partitions["master_holdout"]),
        "master_holdout_policy": "sealed_and_never_materialized_by_this_runner",
        "normal_cost_pct": v1.NORMAL_COST_PCT,
        "stress_cost_pct": v1.STRESS_COST_PCT,
        "minimum_oof_trades": 80,
        "minimum_validation_trades": 25,
        "negative_control": "same_horizon_with_entry_delayed_an_additional_five_minutes",
        "research_only": True,
        "allowed_for_live_execution": False,
    }
    contract["semantic_sha256"] = v1.semantic_hash(contract)
    stable_json(out / "frozen_contract.json", contract)

    ledgers: dict[int, list[pd.DataFrame]] = {horizon: [] for horizon in HORIZONS}
    controls: dict[int, list[pd.DataFrame]] = {horizon: [] for horizon in HORIZONS}
    threshold_records = []
    evidence_frames: list[pd.DataFrame] = []

    for training_sessions, testing_sessions, fold_id in folds:
        training = causal.loc[causal["session_id"].isin(training_sessions)]
        testing = causal.loc[causal["session_id"].isin(testing_sessions)]
        cut = digest.combined_thresholds(training)
        masks = digest.origin_masks(testing, cut)
        signals = digest.build_confirmed_signals(
            testing,
            masks[BASE_MECHANISM],
            BASE_MECHANISM,
            cut,
            testing_sessions,
        )
        shifted = shift_signal_entry(signals, testing, 5)
        threshold_records.append({"fold_id": fold_id, "training_sessions": len(training_sessions), "thresholds": cut})
        for horizon in HORIZONS:
            primary = attach_exact_horizon(signals, testing, horizon, fold_id)
            control = attach_exact_horizon(shifted, testing, horizon, fold_id)
            if not primary.empty:
                primary["mechanism"] = f"{BASE_MECHANISM}_{horizon}m"
                ledgers[horizon].append(primary)
            if not control.empty:
                control["mechanism"] = f"{BASE_MECHANISM}_{horizon}m__additional_delay_control"
                controls[horizon].append(control)
    stable_json(out / "fold_thresholds.json", threshold_records)

    oof_records = []
    survivors: list[tuple[int, v1.Metrics, float]] = []
    for horizon in HORIZONS:
        primary = pd.concat(ledgers[horizon], ignore_index=True, sort=False) if ledgers[horizon] else pd.DataFrame()
        control = pd.concat(controls[horizon], ignore_index=True, sort=False) if controls[horizon] else pd.DataFrame()
        metric = v1.calculate_metrics(primary)
        control_metric = v1.calculate_metrics(control)
        ci_low = lead.cluster_bootstrap_ci_low(primary, CUMULATIVE_MECHANISM_COUNT)
        economic_pass = oof_gate(metric, ci_low)
        timing_pass = v1.control_gate(metric, control_metric) if economic_pass else False
        passed = economic_pass and timing_pass
        oof_records.append(
            {
                "mechanism": f"{BASE_MECHANISM}_{horizon}m",
                "horizon_minutes": horizon,
                **asdict(metric),
                "multiplicity_adjusted_cluster_bootstrap_ci_low": ci_low,
                "additional_delay_control": asdict(control_metric),
                "economic_gate": economic_pass,
                "timing_specificity_gate": timing_pass,
                "oof_gate": passed,
            }
        )
        if not primary.empty:
            evidence_frames.append(primary.assign(partition="research_oof", control="primary"))
        if not control.empty:
            evidence_frames.append(control.assign(partition="research_oof", control="additional_delay_5m"))
        if passed and ci_low is not None:
            survivors.append((horizon, metric, ci_low))

    survivors = sorted(
        survivors,
        key=lambda item: (item[2], item[1].remove_top_five_profit_factor or -math.inf, item[1].trades),
        reverse=True,
    )[:1]
    survivor_horizons = [horizon for horizon, _, _ in survivors]
    stable_json(out / "oof_screen.json", {"records": oof_records, "validation_horizons_frozen": survivor_horizons})

    validation_records = []
    validation_survivors: list[int] = []
    if survivor_horizons:
        final_cut = digest.combined_thresholds(causal.loc[causal["session_id"].isin(partitions["research"])])
        validation = causal.loc[causal["session_id"].isin(partitions["validation"])]
        masks = digest.origin_masks(validation, final_cut)
        signals = digest.build_confirmed_signals(
            validation,
            masks[BASE_MECHANISM],
            BASE_MECHANISM,
            final_cut,
            partitions["validation"],
        )
        shifted = shift_signal_entry(signals, validation, 5)
        for horizon in survivor_horizons:
            primary = attach_exact_horizon(signals, validation, horizon, "validation")
            control = attach_exact_horizon(shifted, validation, horizon, "validation")
            metric = v1.calculate_metrics(primary)
            control_metric = v1.calculate_metrics(control)
            ci_low = lead.cluster_bootstrap_ci_low(primary, 1)
            economic_pass = validation_gate(metric, ci_low)
            timing_pass = v1.control_gate(metric, control_metric) if economic_pass else False
            passed = economic_pass and timing_pass
            validation_records.append(
                {
                    "mechanism": f"{BASE_MECHANISM}_{horizon}m",
                    "horizon_minutes": horizon,
                    **asdict(metric),
                    "cluster_bootstrap_ci_low": ci_low,
                    "additional_delay_control": asdict(control_metric),
                    "economic_gate": economic_pass,
                    "timing_specificity_gate": timing_pass,
                    "validation_gate": passed,
                }
            )
            if not primary.empty:
                evidence_frames.append(primary.assign(partition="validation", control="primary"))
            if not control.empty:
                evidence_frames.append(control.assign(partition="validation", control="additional_delay_5m"))
            if passed:
                validation_survivors.append(horizon)
    stable_json(
        out / "validation_screen.json",
        {"records": validation_records, "validation_horizon_survivors": validation_survivors, "master_holdout_outcomes_materialized": False},
    )

    if evidence_frames:
        ledger = pd.concat(evidence_frames, ignore_index=True, sort=False)
        keep = [
            "partition", "control", "fold_id", "mechanism", "session_id", "timestamp", "exit_timestamp",
            "expired_instrument_key", "expiry_id", "option_type", "strike", "entry_price_next_open",
            "exit_close", "gross_return_pct", "net_return_pct", "stress_return_pct", "label_horizon_minutes",
            "origin_timestamp", "origin_peer_lead_gap", "peer_lead_gap", "prior_5m_return_pct",
            "return_acceleration", "days_to_expiry", "minute_of_day",
        ]
        ledger[[column for column in keep if column in ledger.columns]].to_csv(out / "trade_ledger.csv", index=False)

    verdict = (
        "PROMISING_HIGH_OCCURRENCE_PEER_RECLAIM_HORIZON_MASTER_HOLDOUT_UNOPENED"
        if validation_survivors
        else (
            "NO_MULTIPLICITY_ADJUSTED_OOF_SURVIVOR_IN_PEER_RECLAIM_HORIZONS"
            if not survivor_horizons
            else "PEER_RECLAIM_HORIZON_OOF_SURVIVOR_FAILED_VALIDATION"
        )
    )
    final = {
        "principal_verdict": verdict,
        "oof_horizon_survivors": survivor_horizons,
        "validation_horizon_survivors": validation_survivors,
        "cumulative_mechanisms_tested": CUMULATIVE_MECHANISM_COUNT,
        "master_holdout_outcomes_materialized": False,
        "master_holdout_status": "SEALED_FOR_CROSS_FAMILY_FINAL_CERTIFICATION",
        "execution_certification": "BLOCKED_AUTHORITATIVE_TIMESTAMP_ALIGNED_SPREAD_MISSING",
        "contract_semantic_sha256": contract["semantic_sha256"],
        "research_only": True,
        "paper_or_live_authorized": False,
        "allowed_for_live_execution": False,
    }
    final["semantic_sha256"] = v1.semantic_hash(final)
    stable_json(out / "final_decision.json", final)
    (research_dir / "RESULT.md").write_text(
        "# Peer-Reclaim Horizon Campaign V5\n\n"
        f"Principal verdict: `{verdict}`\n\n"
        f"OOF horizon survivors: `{survivor_horizons}`\n\n"
        f"Validation horizon survivors: `{validation_survivors}`\n\n"
        "Master holdout: `SEALED_AND_UNREAD`.\n\n"
        "No paper or live authorization is granted.\n",
        encoding="utf-8",
    )
    print(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
