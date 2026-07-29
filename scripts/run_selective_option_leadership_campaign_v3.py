#!/usr/bin/env python3
"""Selective option-leadership continuation campaign V3.

Adaptive reasoning boundary:
V2 tested whether a lagging contract catches up to coherently repricing neighbours.
That family showed high occurrence but no economic edge. V3 tests the reverse
microstructure interpretation: selective premium leadership may reflect concentrated
informed flow and continue before the rest of the surface catches up.

The latest 15% campaign master holdout remains sealed and unread.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scripts import run_cross_strike_diffusion_discovery_v1 as v1
from scripts import run_cross_strike_diffusion_campaign_v2 as splitmod
from scripts import run_option_surface_transition_discovery_v1 as base
from scripts.run_conditional_precursor_discrimination_v2 import PRIOR_REL, stable_json

OUT_REL = Path("runtime/research/selective_option_leadership_campaign_v3")
RESEARCH_REL = Path("research/selective_option_leadership_campaign_v3")
EVENT_FILE = "event_universe_5m.parquet"
SEED = 20260729
CUMULATIVE_MECHANISM_COUNT = 16

MECHANISMS = (
    "selective_leader_continuation",
    "confirmed_surface_leader_continuation",
    "accelerating_leader_persistence",
    "mirror_decay_selective_leader",
    "oi_volume_informed_leader",
    "orderly_surface_leader",
    "near_expiry_selective_convexity",
    "repeated_leader_persistence",
)


def prepare_causal(event_path: Path) -> pd.DataFrame:
    frame = v1.prepare_causal(event_path)
    frame["leader_gap"] = frame["prior_5m_return_pct"] - frame["adjacent_mean_return"]
    instrument = frame.groupby("expired_instrument_key", sort=False, observed=True)
    frame["previous_leader_gap"] = instrument["leader_gap"].shift(1)
    frame["leader_gap_acceleration"] = frame["leader_gap"] - frame["previous_leader_gap"]
    return frame


def _q(frame: pd.DataFrame, column: str, quantile: float, default: float = 0.0) -> float:
    values = v1._finite(frame[column]).dropna()
    return float(values.quantile(quantile)) if not values.empty else default


def thresholds(training: pd.DataFrame) -> dict[str, float]:
    return {
        "target_p60": _q(training, "prior_5m_return_pct", 0.60),
        "target_p65": _q(training, "prior_5m_return_pct", 0.65),
        "target_p70": _q(training, "prior_5m_return_pct", 0.70),
        "target_p80": _q(training, "prior_5m_return_pct", 0.80),
        "leader_gap_p65": _q(training, "leader_gap", 0.65),
        "leader_gap_p75": _q(training, "leader_gap", 0.75),
        "leader_gap_p85": _q(training, "leader_gap", 0.85),
        "volume_p55": _q(training, "prior_5m_volume_ratio", 0.55, 1.0),
        "volume_p70": _q(training, "prior_5m_volume_ratio", 0.70, 1.0),
        "oi_p60": _q(training, "oi_change_ratio", 0.60),
        "accel_p65": _q(training, "return_acceleration", 0.65),
        "accel_p75": _q(training, "return_acceleration", 0.75),
        "mirror_p40": _q(training, "mirror_return", 0.40),
        "asymmetry_p70": _q(training, "option_asymmetry", 0.70),
        "peer_p40": _q(training, "adjacent_mean_return", 0.40),
        "peer_p55": _q(training, "adjacent_mean_return", 0.55),
        "dispersion_p50": _q(training, "peer_dispersion", 0.50),
    }


def mechanism_masks(frame: pd.DataFrame, cut: dict[str, float]) -> dict[str, pd.Series]:
    target = frame["prior_5m_return_pct"]
    leader = frame["leader_gap"]
    peer = frame["adjacent_mean_return"]
    volume = frame["prior_5m_volume_ratio"]
    return {
        "selective_leader_continuation": (
            (target >= cut["target_p70"])
            & (leader >= cut["leader_gap_p75"])
            & (volume >= cut["volume_p55"])
        ),
        "confirmed_surface_leader_continuation": (
            (target >= cut["target_p65"])
            & (leader >= cut["leader_gap_p65"])
            & (peer > 0)
            & (frame["adjacent_positive_breadth"] >= 0.50)
            & (volume >= cut["volume_p55"])
        ),
        "accelerating_leader_persistence": (
            (target >= cut["target_p65"])
            & (leader >= cut["leader_gap_p65"])
            & (frame["return_acceleration"] >= cut["accel_p75"])
            & (frame["leader_gap_acceleration"] > 0)
        ),
        "mirror_decay_selective_leader": (
            (target >= cut["target_p65"])
            & (leader >= cut["leader_gap_p65"])
            & (frame["mirror_return"] <= cut["mirror_p40"])
            & (frame["option_asymmetry"] >= cut["asymmetry_p70"])
        ),
        "oi_volume_informed_leader": (
            (target >= cut["target_p65"])
            & (leader >= cut["leader_gap_p65"])
            & (volume >= cut["volume_p70"])
            & (frame["oi_change_ratio"] >= cut["oi_p60"])
        ),
        "orderly_surface_leader": (
            (target >= cut["target_p70"])
            & (leader >= cut["leader_gap_p65"])
            & (peer >= cut["peer_p40"])
            & (frame["peer_dispersion"] <= cut["dispersion_p50"])
        ),
        "near_expiry_selective_convexity": (
            frame["days_to_expiry"].between(0, 2, inclusive="both")
            & (target >= cut["target_p70"])
            & (leader >= cut["leader_gap_p75"])
            & (volume >= cut["volume_p55"])
        ),
        "repeated_leader_persistence": (
            (frame["previous_return"] > 0)
            & (target > 0)
            & (frame["previous_leader_gap"] > 0)
            & (leader >= cut["leader_gap_p65"])
            & (frame["leader_gap_acceleration"] >= 0)
        ),
    }


def eligibility(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["entry_price_next_open"].between(30.0, 300.0, inclusive="both")
        & frame["minute_of_day"].between(585, 885, inclusive="both")
        & frame["days_to_expiry"].between(0, 7, inclusive="both")
        & (frame["surface_count"] >= 3)
        & (frame["adjacent_count"] >= 1)
        & (frame["volume"] > 0)
        & frame["previous_return"].notna()
        & frame["leader_gap"].notna()
    )


def _select_independent(group: pd.DataFrame) -> pd.DataFrame:
    selected: list[int] = []
    last_timestamp: pd.Timestamp | None = None
    ordered = group.sort_values(
        ["timestamp", "leadership_score", "premium_distance", "expired_instrument_key"],
        ascending=[True, False, True, True],
        kind="mergesort",
    )
    for index, row in ordered.iterrows():
        timestamp = pd.Timestamp(row["timestamp"])
        if last_timestamp is not None:
            elapsed = (timestamp - last_timestamp).total_seconds() / 60.0
            if elapsed < v1.MIN_SIGNAL_SEPARATION_MINUTES:
                continue
        selected.append(index)
        last_timestamp = timestamp
        if len(selected) >= v1.MAX_SIGNALS_PER_SESSION:
            break
    return group.loc[selected]


def select_signals(frame: pd.DataFrame, mask: pd.Series, mechanism: str, sessions: list[str]) -> pd.DataFrame:
    candidates = frame.loc[mask & eligibility(frame) & frame["session_id"].isin(sessions)].copy()
    if candidates.empty:
        return candidates
    candidates["mechanism"] = mechanism
    candidates["premium_distance"] = (candidates["entry_price_next_open"] - 120.0).abs()
    candidates["leadership_score"] = (
        candidates["leader_gap"].fillna(0)
        + candidates["prior_5m_return_pct"].fillna(0)
        + 0.50 * candidates["return_acceleration"].fillna(0)
        + 0.25 * candidates["prior_5m_volume_ratio"].fillna(0)
        + 0.25 * candidates["option_asymmetry"].fillna(0)
    )
    best = candidates.groupby(["session_id", "timestamp"], observed=True)["leadership_score"].transform("max")
    candidates = candidates.loc[candidates["leadership_score"].eq(best)]
    candidates = candidates.sort_values(
        ["session_id", "timestamp", "leadership_score", "premium_distance", "expired_instrument_key"],
        ascending=[True, True, False, True, True],
        kind="mergesort",
    ).drop_duplicates(["session_id", "timestamp"], keep="first")
    parts = [_select_independent(part) for _, part in candidates.groupby("session_id", sort=False, observed=True)]
    return pd.concat(parts, ignore_index=False).sort_values(["session_id", "timestamp"], kind="mergesort") if parts else candidates.iloc[0:0]


def delayed_control(signals: pd.DataFrame, causal: pd.DataFrame, outcomes: pd.DataFrame, fold_id: str) -> pd.DataFrame:
    return v1.delayed_control(signals, causal, outcomes, fold_id)


def cluster_bootstrap_ci_low(trades: pd.DataFrame, family_count: int) -> float | None:
    if trades.empty or trades["session_id"].nunique() < 30:
        return None
    grouped = [group["net_return_pct"].dropna().to_numpy(dtype=float) for _, group in trades.groupby("session_id", observed=True)]
    grouped = [values for values in grouped if len(values)]
    if len(grouped) < 30:
        return None
    rng = np.random.default_rng(SEED)
    means = np.empty(8000, dtype=float)
    for index in range(len(means)):
        picks = rng.integers(0, len(grouped), size=len(grouped))
        sample = np.concatenate([grouped[pick] for pick in picks])
        means[index] = sample.mean()
    lower_quantile = 0.05 / (2.0 * family_count)
    return float(np.quantile(means, lower_quantile))


def oof_gate(metric: v1.Metrics, adjusted_ci_low: float | None) -> bool:
    return bool(v1.oof_gate(metric) and adjusted_ci_low is not None and adjusted_ci_low > 0)


def validation_gate(metric: v1.Metrics, cluster_ci_low: float | None) -> bool:
    return bool(splitmod.validation_gate(metric) and cluster_ci_low is not None and cluster_ci_low > 0)


def _write_ledger(frames: list[pd.DataFrame], path: Path) -> None:
    if not frames:
        return
    ledger = pd.concat(frames, ignore_index=True, sort=False)
    keep = [
        "partition", "control", "fold_id", "mechanism", "session_id", "timestamp",
        "expired_instrument_key", "expiry_id", "option_type", "strike", "entry_price_next_open",
        "gross_return_pct", "net_return_pct", "stress_return_pct", "forward_mfe_points",
        "forward_mae_points", "label_horizon_minutes", "prior_5m_return_pct", "previous_return",
        "adjacent_mean_return", "adjacent_positive_breadth", "leader_gap", "previous_leader_gap",
        "leader_gap_acceleration", "peer_dispersion", "prior_5m_volume_ratio", "oi_change_ratio",
        "mirror_return", "option_asymmetry", "days_to_expiry", "minute_of_day",
    ]
    ledger[[column for column in keep if column in ledger.columns]].to_csv(path, index=False)


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

    causal = prepare_causal(event_path)
    partitions = splitmod.partition_sessions(causal)
    folds = splitmod.expanding_folds(partitions["research"])
    contract = {
        "schema_version": "selective_option_leadership_campaign_v3",
        "adaptive_iteration": 2,
        "prior_family_result": "cross_strike_laggard_catchup_no_oof_survivor",
        "hypothesis": "selective_contract_leadership_reflects_concentrated_informed_flow_and_persists",
        "mechanisms": list(MECHANISMS),
        "mechanism_count": len(MECHANISMS),
        "cumulative_mechanisms_in_campaign": CUMULATIVE_MECHANISM_COUNT,
        "multiplicity_policy": "cluster_bootstrap_lower_quantile_0_05_divided_by_2_times_16",
        "research_sessions": len(partitions["research"]),
        "validation_sessions": len(partitions["validation"]),
        "master_holdout_sessions": len(partitions["master_holdout"]),
        "master_holdout_policy": "sealed_and_never_materialized_by_this_runner",
        "normal_cost_pct": v1.NORMAL_COST_PCT,
        "stress_cost_pct": v1.STRESS_COST_PCT,
        "minimum_oof_trades": 80,
        "minimum_validation_trades": 25,
        "research_only": True,
        "allowed_for_live_execution": False,
    }
    contract["semantic_sha256"] = v1.semantic_hash(contract)
    stable_json(out / "frozen_contract.json", contract)
    stable_json(
        out / "adaptive_research_ledger.json",
        {
            "iterations": [
                {
                    "iteration": 1,
                    "family": "cross_strike_laggard_catchup",
                    "mechanisms": 8,
                    "result": "NO_HIGH_OCCURRENCE_OOF_SURVIVOR",
                },
                {
                    "iteration": 2,
                    "family": "selective_option_leadership_continuation",
                    "mechanisms": 8,
                    "result": "PENDING_THIS_RUN",
                },
            ],
            "cumulative_mechanisms": CUMULATIVE_MECHANISM_COUNT,
            "master_holdout_status": "SEALED",
        },
    )

    research_outcomes = base._load_outcomes(event_path, base._raw_sessions(causal, partitions["research"]))
    ledgers: dict[str, list[pd.DataFrame]] = {name: [] for name in MECHANISMS}
    delayed_ledgers: dict[str, list[pd.DataFrame]] = {name: [] for name in MECHANISMS}
    threshold_records: list[dict[str, Any]] = []
    evidence_frames: list[pd.DataFrame] = []

    for training_sessions, testing_sessions, fold_id in folds:
        training = causal.loc[causal["session_id"].isin(training_sessions)]
        testing = causal.loc[causal["session_id"].isin(testing_sessions)]
        cut = thresholds(training)
        threshold_records.append({"fold_id": fold_id, "training_sessions": len(training_sessions), "thresholds": cut})
        masks = mechanism_masks(testing, cut)
        for mechanism in MECHANISMS:
            signals = select_signals(testing, masks[mechanism], mechanism, testing_sessions)
            primary = v1.attach(signals, research_outcomes, fold_id)
            delayed = delayed_control(signals, testing, research_outcomes, fold_id)
            if not primary.empty:
                ledgers[mechanism].append(primary)
            if not delayed.empty:
                delayed_ledgers[mechanism].append(delayed)
    stable_json(out / "fold_thresholds.json", threshold_records)

    oof_records: list[dict[str, Any]] = []
    survivors: list[tuple[str, v1.Metrics, float]] = []
    for mechanism in MECHANISMS:
        primary = pd.concat(ledgers[mechanism], ignore_index=True, sort=False) if ledgers[mechanism] else pd.DataFrame()
        delayed = pd.concat(delayed_ledgers[mechanism], ignore_index=True, sort=False) if delayed_ledgers[mechanism] else pd.DataFrame()
        metric = v1.calculate_metrics(primary)
        delayed_metric = v1.calculate_metrics(delayed)
        adjusted_ci_low = cluster_bootstrap_ci_low(primary, CUMULATIVE_MECHANISM_COUNT)
        economic_pass = oof_gate(metric, adjusted_ci_low)
        control_pass = v1.control_gate(metric, delayed_metric) if economic_pass else False
        passed = economic_pass and control_pass
        oof_records.append(
            {
                "mechanism": mechanism,
                **asdict(metric),
                "multiplicity_adjusted_cluster_bootstrap_ci_low": adjusted_ci_low,
                "delayed_control": asdict(delayed_metric),
                "economic_gate": economic_pass,
                "delayed_control_gate": control_pass,
                "oof_gate": passed,
            }
        )
        if not primary.empty:
            evidence_frames.append(primary.assign(partition="research_oof", control="primary"))
        if not delayed.empty:
            evidence_frames.append(delayed.assign(partition="research_oof", control="delayed_5m"))
        if passed and adjusted_ci_low is not None:
            survivors.append((mechanism, metric, adjusted_ci_low))

    survivors = sorted(
        survivors,
        key=lambda item: (
            item[2],
            item[1].remove_top_five_profit_factor or -math.inf,
            item[1].trades,
            item[0],
        ),
        reverse=True,
    )[:2]
    survivor_names = [name for name, _, _ in survivors]
    stable_json(out / "oof_screen.json", {"records": oof_records, "validation_survivors_frozen": survivor_names})

    validation_records: list[dict[str, Any]] = []
    validation_survivors: list[str] = []
    if survivor_names:
        final_cut = thresholds(causal.loc[causal["session_id"].isin(partitions["research"])])
        validation = causal.loc[causal["session_id"].isin(partitions["validation"])]
        masks = mechanism_masks(validation, final_cut)
        validation_outcomes = base._load_outcomes(event_path, base._raw_sessions(causal, partitions["validation"]))
        for mechanism in survivor_names:
            signals = select_signals(validation, masks[mechanism], mechanism, partitions["validation"])
            primary = v1.attach(signals, validation_outcomes, "validation")
            delayed = delayed_control(signals, validation, validation_outcomes, "validation")
            metric = v1.calculate_metrics(primary)
            delayed_metric = v1.calculate_metrics(delayed)
            cluster_ci_low = cluster_bootstrap_ci_low(primary, 1)
            economic_pass = validation_gate(metric, cluster_ci_low)
            control_pass = v1.control_gate(metric, delayed_metric) if economic_pass else False
            passed = economic_pass and control_pass
            validation_records.append(
                {
                    "mechanism": mechanism,
                    **asdict(metric),
                    "cluster_bootstrap_ci_low": cluster_ci_low,
                    "delayed_control": asdict(delayed_metric),
                    "economic_gate": economic_pass,
                    "delayed_control_gate": control_pass,
                    "validation_gate": passed,
                }
            )
            if not primary.empty:
                evidence_frames.append(primary.assign(partition="validation", control="primary"))
            if not delayed.empty:
                evidence_frames.append(delayed.assign(partition="validation", control="delayed_5m"))
            if passed:
                validation_survivors.append(mechanism)
    stable_json(
        out / "validation_screen.json",
        {
            "records": validation_records,
            "validation_survivors": validation_survivors,
            "master_holdout_outcomes_materialized": False,
        },
    )
    _write_ledger(evidence_frames, out / "trade_ledger.csv")

    verdict = (
        "PROMISING_HIGH_OCCURRENCE_SELECTIVE_LEADERSHIP_MASTER_HOLDOUT_UNOPENED"
        if validation_survivors
        else (
            "NO_MULTIPLICITY_ADJUSTED_OOF_SURVIVOR_IN_SELECTIVE_LEADERSHIP_FAMILY"
            if not survivor_names
            else "SELECTIVE_LEADERSHIP_OOF_SURVIVORS_FAILED_VALIDATION"
        )
    )
    final = {
        "principal_verdict": verdict,
        "oof_survivors": survivor_names,
        "validation_survivors": validation_survivors,
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
        "# Selective Option Leadership Campaign V3\n\n"
        f"Principal verdict: `{verdict}`\n\n"
        f"OOF survivors: `{survivor_names}`\n\n"
        f"Validation survivors: `{validation_survivors}`\n\n"
        "Master holdout: `SEALED_AND_UNREAD`.\n\n"
        "No paper or live authorization is granted.\n",
        encoding="utf-8",
    )
    print(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
