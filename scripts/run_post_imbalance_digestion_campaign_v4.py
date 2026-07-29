#!/usr/bin/env python3
"""Post-imbalance digestion and reconfirmed re-entry campaign V4.

Observed development-only fact motivating this adaptive iteration:
- immediate laggard and leader entries were weak;
- several five-minute delayed controls had positive means.

V4 does not blindly use the delayed control. It requires a completed five-minute
digestion interval and a causal reconfirmation at t+5, enters at the next open,
and exits five minutes later. The latest 15% master holdout remains sealed.
"""
from __future__ import annotations

import argparse
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scripts import run_cross_strike_diffusion_discovery_v1 as v1
from scripts import run_cross_strike_diffusion_campaign_v2 as splitmod
from scripts import run_selective_option_leadership_campaign_v3 as lead
from scripts import run_option_surface_transition_discovery_v1 as base
from scripts.run_conditional_precursor_discrimination_v2 import PRIOR_REL, stable_json

OUT_REL = Path("runtime/research/post_imbalance_digestion_campaign_v4")
RESEARCH_REL = Path("research/post_imbalance_digestion_campaign_v4")
EVENT_FILE = "event_universe_5m.parquet"
SEED = 20260729
CUMULATIVE_MECHANISM_COUNT = 24
DELAY_MINUTES = 5

MECHANISMS = (
    "delayed_confirmed_leader_reentry",
    "delayed_oi_volume_leader_reentry",
    "delayed_orderly_leader_reentry",
    "delayed_repeated_leader_reentry",
    "delayed_persistent_peer_reclaim",
    "delayed_volume_peer_reclaim",
    "delayed_mirror_decay_reentry",
    "delayed_leader_pullback_reentry",
)

ORIGIN_FAMILY = {
    "delayed_confirmed_leader_reentry": "confirmed_surface_leader_continuation",
    "delayed_oi_volume_leader_reentry": "oi_volume_informed_leader",
    "delayed_orderly_leader_reentry": "orderly_surface_leader",
    "delayed_repeated_leader_reentry": "repeated_leader_persistence",
    "delayed_persistent_peer_reclaim": "persistent_peer_impulse_catchup",
    "delayed_volume_peer_reclaim": "volume_confirmed_peer_diffusion",
    "delayed_mirror_decay_reentry": "mirror_decay_selective_leader",
    "delayed_leader_pullback_reentry": "selective_leader_continuation",
}


def prepare_causal(event_path: Path) -> pd.DataFrame:
    return lead.prepare_causal(event_path)


def combined_thresholds(training: pd.DataFrame) -> dict[str, float]:
    values = {f"lead__{key}": value for key, value in lead.thresholds(training).items()}
    values.update({f"lag__{key}": value for key, value in v1.thresholds(training).items()})
    values["delayed_volume_p50"] = lead._q(training, "prior_5m_volume_ratio", 0.50, 1.0)
    values["delayed_dispersion_p60"] = lead._q(training, "peer_dispersion", 0.60)
    values["delayed_target_abs_p60"] = float(
        v1._finite(training["prior_5m_return_pct"]).abs().dropna().quantile(0.60)
    )
    return values


def origin_masks(frame: pd.DataFrame, cut: dict[str, float]) -> dict[str, pd.Series]:
    lead_cut = {key.removeprefix("lead__"): value for key, value in cut.items() if key.startswith("lead__")}
    lag_cut = {key.removeprefix("lag__"): value for key, value in cut.items() if key.startswith("lag__")}
    lead_masks = lead.mechanism_masks(frame, lead_cut)
    lag_masks = v1.mechanism_masks(frame, lag_cut)
    return {
        mechanism: (
            lead_masks[family]
            if family in lead_masks
            else lag_masks[family]
        )
        for mechanism, family in ORIGIN_FAMILY.items()
    }


def origin_eligibility(frame: pd.DataFrame) -> pd.Series:
    return lead.eligibility(frame)


def _origin_rows(frame: pd.DataFrame, mask: pd.Series, mechanism: str, sessions: list[str]) -> pd.DataFrame:
    columns = [
        "expired_instrument_key", "timestamp", "session_id", "expiry_id", "option_type", "strike",
        "peer_lead_gap", "leader_gap", "prior_5m_return_pct", "adjacent_mean_return",
        "prior_5m_volume_ratio", "oi_change_ratio", "mirror_return", "option_asymmetry",
    ]
    rows = frame.loc[mask & origin_eligibility(frame) & frame["session_id"].isin(sessions), columns].copy()
    if rows.empty:
        return rows
    rows = rows.rename(columns={column: f"origin_{column}" for column in columns if column not in {"expired_instrument_key", "session_id"}})
    rows["mechanism"] = mechanism
    rows["timestamp"] = rows["origin_timestamp"] + pd.Timedelta(minutes=DELAY_MINUTES)
    return rows


def _delayed_lookup(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "expired_instrument_key", "timestamp", "session_id", "expiry_id", "option_type", "strike",
        "entry_price_next_open", "prior_5m_return_pct", "previous_return", "return_acceleration",
        "prior_5m_volume_ratio", "oi_change_ratio", "adjacent_mean_return", "adjacent_positive_breadth",
        "peer_lead_gap", "leader_gap", "peer_dispersion", "mirror_return", "option_asymmetry",
        "days_to_expiry", "minute_of_day", "volume", "surface_count", "adjacent_count",
    ]
    return frame[columns].drop_duplicates(["expired_instrument_key", "timestamp"])


def confirmation_mask(frame: pd.DataFrame, mechanism: str, cut: dict[str, float]) -> pd.Series:
    target = frame["prior_5m_return_pct"]
    if mechanism == "delayed_confirmed_leader_reentry":
        return (target >= 0) & (frame["leader_gap"] >= 0) & (frame["return_acceleration"] >= 0)
    if mechanism == "delayed_oi_volume_leader_reentry":
        return (
            (target >= 0)
            & (frame["prior_5m_volume_ratio"] >= cut["delayed_volume_p50"])
            & (frame["oi_change_ratio"] >= 0)
        )
    if mechanism == "delayed_orderly_leader_reentry":
        return (
            (target >= 0)
            & (frame["adjacent_mean_return"] >= 0)
            & (frame["peer_dispersion"] <= cut["delayed_dispersion_p60"])
        )
    if mechanism == "delayed_repeated_leader_reentry":
        return (target > 0) & (frame["previous_return"] > 0) & (frame["leader_gap"] >= 0)
    if mechanism == "delayed_persistent_peer_reclaim":
        return (
            (target > 0)
            & (frame["peer_lead_gap"] < frame["origin_peer_lead_gap"])
            & (frame["return_acceleration"] >= 0)
        )
    if mechanism == "delayed_volume_peer_reclaim":
        return (
            (target > 0)
            & (frame["prior_5m_volume_ratio"] >= cut["delayed_volume_p50"])
            & (frame["peer_lead_gap"] < frame["origin_peer_lead_gap"])
        )
    if mechanism == "delayed_mirror_decay_reentry":
        return (target >= 0) & (frame["mirror_return"] <= 0) & (frame["option_asymmetry"] >= 0)
    if mechanism == "delayed_leader_pullback_reentry":
        return (
            (target <= 0)
            & (target.abs() <= cut["delayed_target_abs_p60"])
            & (frame["adjacent_mean_return"] >= 0)
        )
    raise KeyError(mechanism)


def build_confirmed_signals(
    frame: pd.DataFrame,
    origin_mask: pd.Series,
    mechanism: str,
    cut: dict[str, float],
    sessions: list[str],
) -> pd.DataFrame:
    origins = _origin_rows(frame, origin_mask, mechanism, sessions)
    if origins.empty:
        return origins
    joined = origins.merge(
        _delayed_lookup(frame),
        on=["expired_instrument_key", "timestamp", "session_id"],
        how="inner",
        validate="many_to_one",
    )
    joined = joined.loc[
        confirmation_mask(joined, mechanism, cut)
        & joined["entry_price_next_open"].between(30.0, 300.0, inclusive="both")
        & joined["minute_of_day"].between(590, 890, inclusive="both")
        & joined["days_to_expiry"].between(0, 7, inclusive="both")
        & (joined["volume"] > 0)
        & (joined["surface_count"] >= 3)
    ].copy()
    if joined.empty:
        return joined
    joined["premium_distance"] = (joined["entry_price_next_open"] - 120.0).abs()
    joined["digestion_score"] = (
        joined["return_acceleration"].fillna(0)
        + joined["option_asymmetry"].fillna(0)
        + joined["prior_5m_volume_ratio"].fillna(0)
        + 0.50 * joined["adjacent_positive_breadth"].fillna(0)
        - 0.25 * joined["peer_dispersion"].fillna(0)
    )
    best = joined.groupby(["session_id", "timestamp"], observed=True)["digestion_score"].transform("max")
    joined = joined.loc[joined["digestion_score"].eq(best)]
    joined = joined.sort_values(
        ["session_id", "timestamp", "digestion_score", "premium_distance", "expired_instrument_key"],
        ascending=[True, True, False, True, True],
        kind="mergesort",
    ).drop_duplicates(["session_id", "timestamp"], keep="first")
    parts = []
    for _, group in joined.groupby("session_id", sort=False, observed=True):
        selected: list[int] = []
        last: pd.Timestamp | None = None
        for index, row in group.sort_values(["timestamp", "digestion_score"], ascending=[True, False], kind="mergesort").iterrows():
            timestamp = pd.Timestamp(row["timestamp"])
            if last is not None and (timestamp - last).total_seconds() / 60.0 < v1.MIN_SIGNAL_SEPARATION_MINUTES:
                continue
            selected.append(index)
            last = timestamp
            if len(selected) >= v1.MAX_SIGNALS_PER_SESSION:
                break
        parts.append(group.loc[selected])
    return pd.concat(parts, ignore_index=False).sort_values(["session_id", "timestamp"], kind="mergesort") if parts else joined.iloc[0:0]


def second_delay_control(signals: pd.DataFrame, causal: pd.DataFrame, outcomes: pd.DataFrame, fold_id: str) -> pd.DataFrame:
    return v1.delayed_control(signals, causal, outcomes, fold_id)


def adjusted_cluster_ci_low(trades: pd.DataFrame) -> float | None:
    return lead.cluster_bootstrap_ci_low(trades, CUMULATIVE_MECHANISM_COUNT)


def oof_gate(metric: v1.Metrics, ci_low: float | None) -> bool:
    return bool(v1.oof_gate(metric) and ci_low is not None and ci_low > 0)


def validation_gate(metric: v1.Metrics, ci_low: float | None) -> bool:
    return bool(splitmod.validation_gate(metric) and ci_low is not None and ci_low > 0)


def _write_ledger(frames: list[pd.DataFrame], path: Path) -> None:
    if not frames:
        return
    ledger = pd.concat(frames, ignore_index=True, sort=False)
    keep = [
        "partition", "control", "fold_id", "mechanism", "session_id", "timestamp",
        "origin_timestamp", "expired_instrument_key", "expiry_id", "option_type", "strike",
        "entry_price_next_open", "gross_return_pct", "net_return_pct", "stress_return_pct",
        "forward_mfe_points", "forward_mae_points", "label_horizon_minutes",
        "origin_prior_5m_return_pct", "prior_5m_return_pct", "previous_return", "return_acceleration",
        "origin_peer_lead_gap", "peer_lead_gap", "origin_leader_gap", "leader_gap",
        "adjacent_mean_return", "peer_dispersion", "prior_5m_volume_ratio", "oi_change_ratio",
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
        "schema_version": "post_imbalance_digestion_campaign_v4",
        "adaptive_iteration": 3,
        "prior_results": [
            "laggard_catchup_immediate_entry_failed",
            "selective_leadership_immediate_entry_failed",
            "multiple_five_minute_delayed_controls_showed_positive_development_means",
        ],
        "hypothesis": "cross_strike_imbalance_requires_a_completed_digestion_interval_before_reconfirmed_continuation",
        "origin_delay_minutes": DELAY_MINUTES,
        "entry": "next_same_contract_open_after_completed_delayed_confirmation_candle",
        "exit": "same_contract_close_five_minutes_after_delayed_confirmation",
        "mechanisms": list(MECHANISMS),
        "mechanism_count": len(MECHANISMS),
        "cumulative_mechanisms_in_campaign": CUMULATIVE_MECHANISM_COUNT,
        "multiplicity_policy": "session_cluster_bootstrap_lower_quantile_0_05_divided_by_2_times_24",
        "research_sessions": len(partitions["research"]),
        "validation_sessions": len(partitions["validation"]),
        "master_holdout_sessions": len(partitions["master_holdout"]),
        "master_holdout_policy": "sealed_and_never_materialized_by_this_runner",
        "normal_cost_pct": v1.NORMAL_COST_PCT,
        "stress_cost_pct": v1.STRESS_COST_PCT,
        "minimum_oof_trades": 80,
        "minimum_validation_trades": 25,
        "negative_control": "additional_five_minute_delay_must_be_at_least_0_20_percentage_points_weaker",
        "research_only": True,
        "allowed_for_live_execution": False,
    }
    contract["semantic_sha256"] = v1.semantic_hash(contract)
    stable_json(out / "frozen_contract.json", contract)
    stable_json(
        out / "adaptive_research_ledger.json",
        {
            "iterations": [
                {"iteration": 1, "family": "laggard_catchup", "mechanisms": 8, "result": "NO_OOF_SURVIVOR"},
                {"iteration": 2, "family": "selective_leadership", "mechanisms": 8, "result": "NO_OOF_SURVIVOR"},
                {"iteration": 3, "family": "post_imbalance_digestion", "mechanisms": 8, "result": "PENDING_THIS_RUN"},
            ],
            "cumulative_mechanisms": CUMULATIVE_MECHANISM_COUNT,
            "master_holdout_status": "SEALED",
        },
    )

    research_outcomes = base._load_outcomes(event_path, base._raw_sessions(causal, partitions["research"]))
    ledgers: dict[str, list[pd.DataFrame]] = {name: [] for name in MECHANISMS}
    controls: dict[str, list[pd.DataFrame]] = {name: [] for name in MECHANISMS}
    threshold_records: list[dict[str, Any]] = []
    evidence_frames: list[pd.DataFrame] = []

    for training_sessions, testing_sessions, fold_id in folds:
        training = causal.loc[causal["session_id"].isin(training_sessions)]
        testing = causal.loc[causal["session_id"].isin(testing_sessions)]
        cut = combined_thresholds(training)
        threshold_records.append({"fold_id": fold_id, "training_sessions": len(training_sessions), "thresholds": cut})
        masks = origin_masks(testing, cut)
        for mechanism in MECHANISMS:
            signals = build_confirmed_signals(testing, masks[mechanism], mechanism, cut, testing_sessions)
            primary = v1.attach(signals, research_outcomes, fold_id)
            control = second_delay_control(signals, testing, research_outcomes, fold_id)
            if not primary.empty:
                ledgers[mechanism].append(primary)
            if not control.empty:
                controls[mechanism].append(control)
    stable_json(out / "fold_thresholds.json", threshold_records)

    oof_records: list[dict[str, Any]] = []
    survivors: list[tuple[str, v1.Metrics, float]] = []
    for mechanism in MECHANISMS:
        primary = pd.concat(ledgers[mechanism], ignore_index=True, sort=False) if ledgers[mechanism] else pd.DataFrame()
        control = pd.concat(controls[mechanism], ignore_index=True, sort=False) if controls[mechanism] else pd.DataFrame()
        metric = v1.calculate_metrics(primary)
        control_metric = v1.calculate_metrics(control)
        ci_low = adjusted_cluster_ci_low(primary)
        economic_pass = oof_gate(metric, ci_low)
        timing_pass = v1.control_gate(metric, control_metric) if economic_pass else False
        passed = economic_pass and timing_pass
        oof_records.append(
            {
                "mechanism": mechanism,
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
            survivors.append((mechanism, metric, ci_low))

    survivors = sorted(
        survivors,
        key=lambda item: (item[2], item[1].remove_top_five_profit_factor or -math.inf, item[1].trades, item[0]),
        reverse=True,
    )[:2]
    survivor_names = [name for name, _, _ in survivors]
    stable_json(out / "oof_screen.json", {"records": oof_records, "validation_survivors_frozen": survivor_names})

    validation_records: list[dict[str, Any]] = []
    validation_survivors: list[str] = []
    if survivor_names:
        final_cut = combined_thresholds(causal.loc[causal["session_id"].isin(partitions["research"])])
        validation = causal.loc[causal["session_id"].isin(partitions["validation"])]
        masks = origin_masks(validation, final_cut)
        validation_outcomes = base._load_outcomes(event_path, base._raw_sessions(causal, partitions["validation"]))
        for mechanism in survivor_names:
            signals = build_confirmed_signals(validation, masks[mechanism], mechanism, final_cut, partitions["validation"])
            primary = v1.attach(signals, validation_outcomes, "validation")
            control = second_delay_control(signals, validation, validation_outcomes, "validation")
            metric = v1.calculate_metrics(primary)
            control_metric = v1.calculate_metrics(control)
            ci_low = lead.cluster_bootstrap_ci_low(primary, 1)
            economic_pass = validation_gate(metric, ci_low)
            timing_pass = v1.control_gate(metric, control_metric) if economic_pass else False
            passed = economic_pass and timing_pass
            validation_records.append(
                {
                    "mechanism": mechanism,
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
                validation_survivors.append(mechanism)
    stable_json(
        out / "validation_screen.json",
        {"records": validation_records, "validation_survivors": validation_survivors, "master_holdout_outcomes_materialized": False},
    )
    _write_ledger(evidence_frames, out / "trade_ledger.csv")

    verdict = (
        "PROMISING_HIGH_OCCURRENCE_POST_IMBALANCE_DIGESTION_MASTER_HOLDOUT_UNOPENED"
        if validation_survivors
        else (
            "NO_MULTIPLICITY_ADJUSTED_OOF_SURVIVOR_IN_POST_IMBALANCE_DIGESTION_FAMILY"
            if not survivor_names
            else "POST_IMBALANCE_DIGESTION_OOF_SURVIVORS_FAILED_VALIDATION"
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
        "# Post-Imbalance Digestion Campaign V4\n\n"
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
