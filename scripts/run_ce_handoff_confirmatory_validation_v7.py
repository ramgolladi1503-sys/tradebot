#!/usr/bin/env python3
"""Confirmatory validation of the frozen CE leadership-handoff candidate V7.

Selection occurred exclusively on the earliest 70% research partition after 31
cumulative exploratory mechanisms. Exactly one candidate is frozen:
- CE only;
- initial cross-strike lag;
- five minutes later the target has overtaken its peers;
- entry at the next same-contract open;
- fixed 10-minute exit;
- premium 80-300.

This runner opens only the pre-reserved middle 15% validation partition. The latest
15% campaign master holdout remains sealed and is not read.
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

from scripts import run_cross_strike_diffusion_discovery_v1 as v1
from scripts import run_cross_strike_diffusion_campaign_v2 as splitmod
from scripts import run_selective_option_leadership_campaign_v3 as lead
from scripts import run_post_imbalance_digestion_campaign_v4 as digest
from scripts import run_peer_reclaim_horizon_campaign_v5 as horizon
from scripts import run_peer_reclaim_horizon_campaign_v5_1 as fixed
from scripts import run_leadership_handoff_campaign_v6 as handoff
from scripts.run_conditional_precursor_discrimination_v2 import PRIOR_REL, stable_json

OUT_REL = Path("runtime/research/ce_handoff_confirmatory_validation_v7")
RESEARCH_REL = Path("research/ce_handoff_confirmatory_validation_v7")
EVENT_FILE = "event_universe_5m.parquet"
CANDIDATE_ID = "ce_leadership_handoff_10m_v7"
MIN_VALIDATION_TRADES = 20
MIN_VALIDATION_SESSIONS = 15

# Repair the delayed-entry control inherited by the V6 module.
handoff.horizon.shift_signal_entry = fixed.shift_signal_entry


def session_cluster_ci(trades: pd.DataFrame, seed: int = 20260729) -> tuple[float | None, float | None]:
    groups = [
        group["net_return_pct"].dropna().to_numpy(dtype=float)
        for _, group in trades.groupby("session_id", observed=True)
    ]
    groups = [values for values in groups if len(values)]
    if len(groups) < 15:
        return None, None
    rng = np.random.default_rng(seed)
    means = np.empty(10000, dtype=float)
    for index in range(len(means)):
        picks = rng.integers(0, len(groups), size=len(groups))
        means[index] = np.concatenate([groups[pick] for pick in picks]).mean()
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def selection_metrics(trades: pd.DataFrame) -> dict[str, Any]:
    metric = v1.calculate_metrics(trades)
    ci_low, ci_high = session_cluster_ci(trades)
    return {**asdict(metric), "session_cluster_ci_low": ci_low, "session_cluster_ci_high": ci_high}


def validation_gate(
    primary: dict[str, Any],
    delayed: dict[str, Any],
    pe_control: dict[str, Any],
) -> tuple[bool, dict[str, bool]]:
    gates = {
        "minimum_trades": primary["trades"] >= MIN_VALIDATION_TRADES,
        "minimum_sessions": primary["sessions"] >= MIN_VALIDATION_SESSIONS,
        "profit_factor": primary["profit_factor"] is not None and primary["profit_factor"] >= 1.25,
        "mean_positive": primary["mean_return_pct"] is not None and primary["mean_return_pct"] > 0,
        "median_positive": primary["median_return_pct"] is not None and primary["median_return_pct"] > 0,
        "stress_profit_factor": primary["stress_profit_factor"] is not None and primary["stress_profit_factor"] >= 1.05,
        "remove_top_five": primary["remove_top_five_profit_factor"] is not None and primary["remove_top_five_profit_factor"] >= 1.05,
        "cluster_ci": primary["session_cluster_ci_low"] is not None and primary["session_cluster_ci_low"] > 0,
        "largest_winner": primary["largest_winner_share"] is None or primary["largest_winner_share"] <= 0.25,
        "session_concentration": primary["top_five_session_profit_share"] is None or primary["top_five_session_profit_share"] <= 0.45,
        "delayed_control": (
            delayed["trades"] >= max(10, int(primary["trades"] * 0.50))
            and delayed["mean_return_pct"] is not None
            and primary["mean_return_pct"] is not None
            and primary["mean_return_pct"] >= delayed["mean_return_pct"] + 0.20
        ),
        "pe_side_control": (
            pe_control["trades"] >= 10
            and pe_control["mean_return_pct"] is not None
            and primary["mean_return_pct"] is not None
            and primary["mean_return_pct"] >= pe_control["mean_return_pct"] + 0.50
        ),
    }
    return all(gates.values()), gates


def semantic_hash(payload: Any) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(body).hexdigest()


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
    research = causal.loc[causal["session_id"].isin(partitions["research"])]
    validation = causal.loc[causal["session_id"].isin(partitions["validation"])]
    cut = handoff.thresholds(research)

    freeze = {
        "candidate_id": CANDIDATE_ID,
        "selection_partition": "earliest_70pct_research_only",
        "selection_burden": "31_cumulative_exploratory_mechanisms",
        "selection_reason": {
            "oof_trades": 95,
            "oof_sessions": 71,
            "oof_profit_factor": 2.025,
            "oof_mean_return_pct": 2.210,
            "oof_median_return_pct": 0.578,
            "oof_stress_profit_factor": 1.504,
            "positive_folds": 4,
            "total_folds": 5,
        },
        "option_type": "CE",
        "variant": "handoff",
        "origin_condition": "peer_lead_gap_positive_before_five_minute_digestion",
        "confirmation_condition": "peer_lead_gap_negative_after_digestion_with_positive_return_and_nonnegative_acceleration",
        "entry": "next_same_contract_open_after_completed_confirmation_candle",
        "exit": "same_contract_close_exactly_10_minutes_after_confirmation",
        "entry_premium_range": [80.0, 300.0],
        "maximum_signals_per_session": v1.MAX_SIGNALS_PER_SESSION,
        "minimum_signal_separation_minutes": v1.MIN_SIGNAL_SEPARATION_MINUTES,
        "validation_partition": "middle_15pct_sessions",
        "master_holdout_policy": "latest_15pct_sessions_sealed_and_unread",
        "thresholds_frozen_from_research": cut,
        "research_only": True,
        "allowed_for_live_execution": False,
    }
    freeze["semantic_sha256"] = semantic_hash(freeze)
    stable_json(out / "frozen_candidate.json", freeze)

    origin_mask = digest.origin_masks(validation, cut)[handoff.BASE_MECHANISM]
    all_handoff = handoff.build_handoff_signals(
        validation,
        origin_mask,
        "handoff",
        cut,
        partitions["validation"],
    )
    ce_signals = all_handoff.loc[all_handoff["option_type"].eq("CE")].copy()
    pe_signals = all_handoff.loc[all_handoff["option_type"].eq("PE")].copy()

    primary = horizon.attach_exact_horizon(ce_signals, validation, 10, "validation")
    shifted = fixed.shift_signal_entry(ce_signals, validation, 5)
    delayed = horizon.attach_exact_horizon(shifted, validation, 10, "validation")
    pe_control = horizon.attach_exact_horizon(pe_signals, validation, 10, "validation")

    primary_metrics = selection_metrics(primary)
    delayed_metrics = selection_metrics(delayed)
    pe_metrics = selection_metrics(pe_control)
    passed, gates = validation_gate(primary_metrics, delayed_metrics, pe_metrics)

    for frame, control in ((primary, "primary"), (delayed, "additional_delay_5m"), (pe_control, "pe_side_control")):
        if not frame.empty:
            frame["control"] = control
            frame["candidate_id"] = CANDIDATE_ID
    frames = [frame for frame in (primary, delayed, pe_control) if not frame.empty]
    if frames:
        ledger = pd.concat(frames, ignore_index=True, sort=False)
        keep = [
            "candidate_id", "control", "fold_id", "session_id", "timestamp", "exit_timestamp",
            "origin_timestamp", "expired_instrument_key", "expiry_id", "option_type", "strike",
            "entry_price_next_open", "exit_close", "gross_return_pct", "net_return_pct",
            "stress_return_pct", "label_horizon_minutes", "origin_peer_lead_gap", "peer_lead_gap",
            "prior_5m_return_pct", "return_acceleration", "days_to_expiry", "minute_of_day",
        ]
        ledger[[column for column in keep if column in ledger.columns]].to_csv(out / "validation_trade_ledger.csv", index=False)

    verdict = (
        "CE_HANDOFF_PASSED_CONFIRMATORY_VALIDATION_MASTER_HOLDOUT_SEALED"
        if passed
        else "CE_HANDOFF_FAILED_CONFIRMATORY_VALIDATION"
    )
    result = {
        "principal_verdict": verdict,
        "candidate_id": CANDIDATE_ID,
        "validation_passed": passed,
        "gates": gates,
        "primary_metrics": primary_metrics,
        "delayed_control_metrics": delayed_metrics,
        "pe_side_control_metrics": pe_metrics,
        "candidate_freeze_semantic_sha256": freeze["semantic_sha256"],
        "master_holdout_outcomes_materialized": False,
        "master_holdout_status": "SEALED_FOR_SINGLE_CANDIDATE_FINAL_CERTIFICATION",
        "execution_certification": "BLOCKED_AUTHORITATIVE_TIMESTAMP_ALIGNED_SPREAD_MISSING",
        "research_only": True,
        "paper_or_live_authorized": False,
        "allowed_for_live_execution": False,
    }
    result["semantic_sha256"] = semantic_hash(result)
    stable_json(out / "validation_decision.json", result)
    (research_dir / "RESULT.md").write_text(
        "# CE Leadership Handoff Confirmatory Validation V7\n\n"
        f"Principal verdict: `{verdict}`\n\n"
        f"Primary metrics: `{json.dumps(primary_metrics, sort_keys=True)}`\n\n"
        f"Gate results: `{json.dumps(gates, sort_keys=True)}`\n\n"
        "Master holdout: `SEALED_AND_UNREAD`.\n\n"
        "No paper or live authorization is granted.\n",
        encoding="utf-8",
    )
    print(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
