#!/usr/bin/env python3
"""Cross-strike diffusion campaign V2 with a permanent master holdout.

V1 used a single 75/25 split. V2 is authoritative for iterative discovery:
- earliest 70%: expanding out-of-fold research;
- next 15%: mechanism-family validation;
- latest 15%: campaign-level master holdout, never read by this runner.

A separate independent final-certification runner may open the master holdout for
at most one frozen mechanism after all intended mechanism families are complete.
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
from scripts import run_option_surface_transition_discovery_v1 as base
from scripts.run_conditional_precursor_discrimination_v2 import PRIOR_REL, stable_json

OUT_REL = Path("runtime/research/cross_strike_diffusion_campaign_v2")
RESEARCH_REL = Path("research/cross_strike_diffusion_campaign_v2")
EVENT_FILE = "event_universe_5m.parquet"


def partition_sessions(frame: pd.DataFrame) -> dict[str, list[str]]:
    sessions = sorted(frame["session_id"].dropna().unique().tolist())
    research_end = int(math.floor(len(sessions) * 0.70))
    validation_end = int(math.floor(len(sessions) * 0.85))
    return {
        "research": sessions[:research_end],
        "validation": sessions[research_end:validation_end],
        "master_holdout": sessions[validation_end:],
    }


def expanding_folds(research_sessions: list[str]) -> list[tuple[list[str], list[str], str]]:
    initial = int(math.floor(len(research_sessions) * 0.35))
    remaining = np.asarray(research_sessions[initial:], dtype=object)
    blocks = [list(block) for block in np.array_split(remaining, 5) if len(block)]
    folds: list[tuple[list[str], list[str], str]] = []
    train_end = initial
    for index, testing in enumerate(blocks, start=1):
        folds.append((research_sessions[:train_end], testing, f"fold_{index}"))
        train_end += len(testing)
    return folds


def validation_gate(metric: v1.Metrics) -> bool:
    return bool(
        metric.trades >= 25
        and metric.sessions >= 20
        and metric.profit_factor is not None
        and metric.profit_factor >= 1.15
        and metric.mean_return_pct is not None
        and metric.mean_return_pct > 0
        and metric.median_return_pct is not None
        and metric.median_return_pct >= 0
        and metric.remove_top_five_profit_factor is not None
        and metric.remove_top_five_profit_factor >= 1.00
        and metric.stress_profit_factor is not None
        and metric.stress_profit_factor >= 1.00
        and metric.bootstrap_mean_ci_low is not None
        and metric.bootstrap_mean_ci_low > 0
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.25)
        and (metric.top_five_session_profit_share is None or metric.top_five_session_profit_share <= 0.40)
    )


def _write_ledger(frames: list[pd.DataFrame], path: Path) -> None:
    if not frames:
        return
    ledger = pd.concat(frames, ignore_index=True, sort=False)
    keep = [
        "partition", "control", "fold_id", "mechanism", "session_id", "timestamp",
        "expired_instrument_key", "expiry_id", "option_type", "strike", "entry_price_next_open",
        "gross_return_pct", "net_return_pct", "stress_return_pct", "forward_mfe_points",
        "forward_mae_points", "label_horizon_minutes", "prior_5m_return_pct", "previous_return",
        "adjacent_mean_return", "adjacent_min_return", "adjacent_positive_breadth", "peer_lead_gap",
        "peer_dispersion", "previous_peer_mean", "previous_peer_gap", "adjacent_mean_volume_ratio",
        "mirror_return", "days_to_expiry", "minute_of_day",
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

    causal = v1.prepare_causal(event_path)
    partitions = partition_sessions(causal)
    folds = expanding_folds(partitions["research"])
    contract = {
        "schema_version": "cross_strike_diffusion_campaign_v2",
        "supersedes_split_policy": "cross_strike_diffusion_discovery_v1_75_25",
        "hypothesis": "coherent_adjacent_strike_repricing_precedes_lagging_contract_catchup",
        "mechanisms": list(v1.MECHANISMS),
        "mechanism_count": len(v1.MECHANISMS),
        "research_sessions": len(partitions["research"]),
        "validation_sessions": len(partitions["validation"]),
        "master_holdout_sessions": len(partitions["master_holdout"]),
        "master_holdout_first_session": partitions["master_holdout"][0] if partitions["master_holdout"] else None,
        "fold_count": len(folds),
        "threshold_policy": "fixed_quantiles_recomputed_from_prior_fold_sessions_only",
        "maximum_signals_per_session": v1.MAX_SIGNALS_PER_SESSION,
        "minimum_signal_separation_minutes": v1.MIN_SIGNAL_SEPARATION_MINUTES,
        "minimum_oof_trades": 80,
        "minimum_validation_trades": 25,
        "normal_cost_pct": v1.NORMAL_COST_PCT,
        "stress_cost_pct": v1.STRESS_COST_PCT,
        "validation_policy": "next_15pct_outcomes_read_only_for_oof_survivors",
        "master_holdout_policy": "latest_15pct_outcomes_never_materialized_by_this_runner",
        "research_only": True,
        "allowed_for_live_execution": False,
    }
    contract["semantic_sha256"] = v1.semantic_hash(contract)
    stable_json(out / "frozen_contract.json", contract)
    stable_json(
        out / "session_partitions.json",
        {
            "research": partitions["research"],
            "validation": partitions["validation"],
            "master_holdout_sha256": v1.semantic_hash(partitions["master_holdout"]),
            "master_holdout_count": len(partitions["master_holdout"]),
            "master_holdout_sessions_redacted": True,
        },
    )

    research_outcomes = base._load_outcomes(event_path, base._raw_sessions(causal, partitions["research"]))
    ledgers: dict[str, list[pd.DataFrame]] = {name: [] for name in v1.MECHANISMS}
    delayed_ledgers: dict[str, list[pd.DataFrame]] = {name: [] for name in v1.MECHANISMS}
    threshold_records: list[dict[str, Any]] = []
    evidence_frames: list[pd.DataFrame] = []

    for training_sessions, testing_sessions, fold_id in folds:
        training = causal.loc[causal["session_id"].isin(training_sessions)]
        testing = causal.loc[causal["session_id"].isin(testing_sessions)]
        cut = v1.thresholds(training)
        threshold_records.append({"fold_id": fold_id, "training_sessions": len(training_sessions), "thresholds": cut})
        masks = v1.mechanism_masks(testing, cut)
        for mechanism in v1.MECHANISMS:
            signals = v1.select_signals(testing, masks[mechanism], mechanism, testing_sessions)
            primary = v1.attach(signals, research_outcomes, fold_id)
            delayed = v1.delayed_control(signals, testing, research_outcomes, fold_id)
            if not primary.empty:
                ledgers[mechanism].append(primary)
            if not delayed.empty:
                delayed_ledgers[mechanism].append(delayed)
    stable_json(out / "fold_thresholds.json", threshold_records)

    oof_records: list[dict[str, Any]] = []
    survivors: list[tuple[str, v1.Metrics]] = []
    for mechanism in v1.MECHANISMS:
        primary = pd.concat(ledgers[mechanism], ignore_index=True, sort=False) if ledgers[mechanism] else pd.DataFrame()
        delayed = (
            pd.concat(delayed_ledgers[mechanism], ignore_index=True, sort=False)
            if delayed_ledgers[mechanism]
            else pd.DataFrame()
        )
        metric = v1.calculate_metrics(primary)
        delayed_metric = v1.calculate_metrics(delayed)
        economic_pass = v1.oof_gate(metric)
        control_pass = v1.control_gate(metric, delayed_metric) if economic_pass else False
        passed = economic_pass and control_pass
        oof_records.append(
            {
                "mechanism": mechanism,
                **asdict(metric),
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
        if passed:
            survivors.append((mechanism, metric))

    survivors = sorted(
        survivors,
        key=lambda item: (
            item[1].bootstrap_mean_ci_low or -math.inf,
            item[1].remove_top_five_profit_factor or -math.inf,
            item[1].trades,
            item[0],
        ),
        reverse=True,
    )[:3]
    survivor_names = [name for name, _ in survivors]
    stable_json(out / "oof_screen.json", {"records": oof_records, "validation_survivors_frozen": survivor_names})

    validation_records: list[dict[str, Any]] = []
    validation_survivors: list[str] = []
    if survivor_names:
        final_cut = v1.thresholds(causal.loc[causal["session_id"].isin(partitions["research"])])
        validation = causal.loc[causal["session_id"].isin(partitions["validation"])]
        validation_masks = v1.mechanism_masks(validation, final_cut)
        validation_outcomes = base._load_outcomes(
            event_path, base._raw_sessions(causal, partitions["validation"])
        )
        for mechanism in survivor_names:
            signals = v1.select_signals(validation, validation_masks[mechanism], mechanism, partitions["validation"])
            primary = v1.attach(signals, validation_outcomes, "validation")
            delayed = v1.delayed_control(signals, validation, validation_outcomes, "validation")
            metric = v1.calculate_metrics(primary)
            delayed_metric = v1.calculate_metrics(delayed)
            economic_pass = validation_gate(metric)
            control_pass = v1.control_gate(metric, delayed_metric) if economic_pass else False
            passed = economic_pass and control_pass
            validation_records.append(
                {
                    "mechanism": mechanism,
                    **asdict(metric),
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
        "PROMISING_HIGH_OCCURRENCE_CROSS_STRIKE_DIFFUSION_MASTER_HOLDOUT_UNOPENED"
        if validation_survivors
        else (
            "NO_HIGH_OCCURRENCE_OOF_SURVIVOR_IN_CROSS_STRIKE_DIFFUSION_FAMILIES"
            if not survivor_names
            else "CROSS_STRIKE_DIFFUSION_OOF_SURVIVORS_FAILED_VALIDATION"
        )
    )
    final = {
        "principal_verdict": verdict,
        "oof_survivors": survivor_names,
        "validation_survivors": validation_survivors,
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
        "# Cross-Strike Diffusion Campaign V2\n\n"
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
