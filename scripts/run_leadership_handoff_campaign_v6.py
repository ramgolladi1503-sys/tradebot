#!/usr/bin/env python3
"""Leadership-handoff transition campaign V6.

A target initially lags coherently rising adjacent strikes. Five minutes later the
profitable subset is not merely catching up: the target has overtaken its peers
(peer_lead_gap turns negative). This runner freezes that causal handoff transition,
uses practical premiums of 80-300, and tests fixed 10/15-minute exits.

The campaign-level latest 15% master holdout remains sealed.
"""
from __future__ import annotations

import argparse
import math
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from scripts import run_cross_strike_diffusion_discovery_v1 as v1
from scripts import run_cross_strike_diffusion_campaign_v2 as splitmod
from scripts import run_selective_option_leadership_campaign_v3 as lead
from scripts import run_post_imbalance_digestion_campaign_v4 as digest
from scripts import run_peer_reclaim_horizon_campaign_v5 as horizon
from scripts.run_conditional_precursor_discrimination_v2 import PRIOR_REL, stable_json

OUT_REL = Path("runtime/research/leadership_handoff_campaign_v6")
RESEARCH_REL = Path("research/leadership_handoff_campaign_v6")
EVENT_FILE = "event_universe_5m.parquet"
SEED = 20260729
HORIZONS = (10, 15)
VARIANTS = ("handoff", "strong_handoff")
CUMULATIVE_MECHANISM_COUNT = 31
BASE_MECHANISM = "delayed_persistent_peer_reclaim"


def thresholds(training: pd.DataFrame) -> dict[str, float]:
    cut = digest.combined_thresholds(training)
    cut["handoff_gap_p30"] = lead._q(training, "peer_lead_gap", 0.30)
    return cut


def build_handoff_signals(
    frame: pd.DataFrame,
    origin_mask: pd.Series,
    variant: str,
    cut: dict[str, float],
    sessions: list[str],
) -> pd.DataFrame:
    origins = digest._origin_rows(frame, origin_mask, variant, sessions)
    if origins.empty:
        return origins
    joined = origins.merge(
        digest._delayed_lookup(frame),
        on=["expired_instrument_key", "timestamp", "session_id"],
        how="inner",
        validate="many_to_one",
    )
    gap_limit = min(0.0, cut["handoff_gap_p30"]) if variant == "strong_handoff" else 0.0
    joined = joined.loc[
        (joined["prior_5m_return_pct"] > 0)
        & (joined["return_acceleration"] >= 0)
        & (joined["peer_lead_gap"] < gap_limit)
        & (joined["origin_peer_lead_gap"] > 0)
        & joined["entry_price_next_open"].between(80.0, 300.0, inclusive="both")
        & joined["minute_of_day"].between(590, 875, inclusive="both")
        & joined["days_to_expiry"].between(0, 7, inclusive="both")
        & (joined["volume"] > 0)
        & (joined["surface_count"] >= 3)
    ].copy()
    if joined.empty:
        return joined
    joined["mechanism"] = variant
    joined["premium_distance"] = (joined["entry_price_next_open"] - 130.0).abs()
    joined["handoff_score"] = (
        -joined["peer_lead_gap"].fillna(0)
        + joined["prior_5m_return_pct"].fillna(0)
        + joined["return_acceleration"].fillna(0)
        + 0.25 * joined["prior_5m_volume_ratio"].fillna(0)
    )
    best = joined.groupby(["session_id", "timestamp"], observed=True)["handoff_score"].transform("max")
    joined = joined.loc[joined["handoff_score"].eq(best)]
    joined = joined.sort_values(
        ["session_id", "timestamp", "handoff_score", "premium_distance", "expired_instrument_key"],
        ascending=[True, True, False, True, True],
        kind="mergesort",
    ).drop_duplicates(["session_id", "timestamp"], keep="first")
    parts = []
    for _, group in joined.groupby("session_id", sort=False, observed=True):
        selected: list[int] = []
        last: pd.Timestamp | None = None
        for index, row in group.sort_values(["timestamp", "handoff_score"], ascending=[True, False], kind="mergesort").iterrows():
            timestamp = pd.Timestamp(row["timestamp"])
            if last is not None and (timestamp - last).total_seconds() / 60.0 < v1.MIN_SIGNAL_SEPARATION_MINUTES:
                continue
            selected.append(index)
            last = timestamp
            if len(selected) >= v1.MAX_SIGNALS_PER_SESSION:
                break
        parts.append(group.loc[selected])
    return pd.concat(parts, ignore_index=False).sort_values(["session_id", "timestamp"], kind="mergesort") if parts else joined.iloc[0:0]


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
    mechanism_ids = [f"{variant}_{minutes}m" for variant in VARIANTS for minutes in HORIZONS]
    contract = {
        "schema_version": "leadership_handoff_campaign_v6",
        "adaptive_iteration": 5,
        "hypothesis": "initial_cross_strike_laggard_that_overtakes_peers_after_digestion_continues_repricing",
        "origin_state": BASE_MECHANISM,
        "handoff_definition": "origin_peer_lead_gap_positive_then_delayed_peer_lead_gap_negative",
        "strong_handoff_definition": "delayed_peer_lead_gap_at_or_below_prior_session_p30",
        "entry_premium_range": [80.0, 300.0],
        "fixed_exit_horizons_minutes": list(HORIZONS),
        "mechanisms": mechanism_ids,
        "mechanism_count": len(mechanism_ids),
        "cumulative_mechanisms_in_campaign": CUMULATIVE_MECHANISM_COUNT,
        "multiplicity_policy": "session_cluster_bootstrap_lower_quantile_0_05_divided_by_2_times_31",
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

    ledgers: dict[str, list[pd.DataFrame]] = {name: [] for name in mechanism_ids}
    controls: dict[str, list[pd.DataFrame]] = {name: [] for name in mechanism_ids}
    threshold_records = []
    evidence_frames: list[pd.DataFrame] = []

    for training_sessions, testing_sessions, fold_id in folds:
        training = causal.loc[causal["session_id"].isin(training_sessions)]
        testing = causal.loc[causal["session_id"].isin(testing_sessions)]
        cut = thresholds(training)
        origin = digest.origin_masks(testing, cut)[BASE_MECHANISM]
        threshold_records.append({"fold_id": fold_id, "training_sessions": len(training_sessions), "thresholds": cut})
        for variant in VARIANTS:
            signals = build_handoff_signals(testing, origin, variant, cut, testing_sessions)
            shifted = horizon.shift_signal_entry(signals, testing, 5)
            for minutes in HORIZONS:
                mechanism = f"{variant}_{minutes}m"
                primary = horizon.attach_exact_horizon(signals, testing, minutes, fold_id)
                control = horizon.attach_exact_horizon(shifted, testing, minutes, fold_id)
                if not primary.empty:
                    primary["mechanism"] = mechanism
                    ledgers[mechanism].append(primary)
                if not control.empty:
                    control["mechanism"] = mechanism + "__additional_delay_control"
                    controls[mechanism].append(control)
    stable_json(out / "fold_thresholds.json", threshold_records)

    oof_records = []
    survivors: list[tuple[str, v1.Metrics, float]] = []
    for mechanism in mechanism_ids:
        primary = pd.concat(ledgers[mechanism], ignore_index=True, sort=False) if ledgers[mechanism] else pd.DataFrame()
        control = pd.concat(controls[mechanism], ignore_index=True, sort=False) if controls[mechanism] else pd.DataFrame()
        metric = v1.calculate_metrics(primary)
        control_metric = v1.calculate_metrics(control)
        ci_low = lead.cluster_bootstrap_ci_low(primary, CUMULATIVE_MECHANISM_COUNT)
        economic_pass = bool(v1.oof_gate(metric) and ci_low is not None and ci_low > 0)
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
    )[:1]
    survivor_names = [name for name, _, _ in survivors]
    stable_json(out / "oof_screen.json", {"records": oof_records, "validation_survivors_frozen": survivor_names})

    validation_records = []
    validation_survivors: list[str] = []
    if survivor_names:
        final_cut = thresholds(causal.loc[causal["session_id"].isin(partitions["research"])])
        validation = causal.loc[causal["session_id"].isin(partitions["validation"])]
        origin = digest.origin_masks(validation, final_cut)[BASE_MECHANISM]
        for mechanism in survivor_names:
            variant, minutes_text = mechanism.rsplit("_", 1)
            minutes = int(minutes_text.removesuffix("m"))
            signals = build_handoff_signals(validation, origin, variant, final_cut, partitions["validation"])
            shifted = horizon.shift_signal_entry(signals, validation, 5)
            primary = horizon.attach_exact_horizon(signals, validation, minutes, "validation")
            control = horizon.attach_exact_horizon(shifted, validation, minutes, "validation")
            metric = v1.calculate_metrics(primary)
            control_metric = v1.calculate_metrics(control)
            ci_low = lead.cluster_bootstrap_ci_low(primary, 1)
            economic_pass = bool(splitmod.validation_gate(metric) and ci_low is not None and ci_low > 0)
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

    if evidence_frames:
        ledger = pd.concat(evidence_frames, ignore_index=True, sort=False)
        keep = [
            "partition", "control", "fold_id", "mechanism", "session_id", "timestamp", "exit_timestamp",
            "origin_timestamp", "expired_instrument_key", "expiry_id", "option_type", "strike",
            "entry_price_next_open", "exit_close", "gross_return_pct", "net_return_pct",
            "stress_return_pct", "label_horizon_minutes", "origin_peer_lead_gap", "peer_lead_gap",
            "prior_5m_return_pct", "return_acceleration", "days_to_expiry", "minute_of_day",
        ]
        ledger[[column for column in keep if column in ledger.columns]].to_csv(out / "trade_ledger.csv", index=False)

    verdict = (
        "PROMISING_HIGH_OCCURRENCE_LEADERSHIP_HANDOFF_MASTER_HOLDOUT_UNOPENED"
        if validation_survivors
        else (
            "NO_MULTIPLICITY_ADJUSTED_OOF_SURVIVOR_IN_LEADERSHIP_HANDOFF_FAMILY"
            if not survivor_names
            else "LEADERSHIP_HANDOFF_OOF_SURVIVOR_FAILED_VALIDATION"
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
        "# Leadership Handoff Campaign V6\n\n"
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
