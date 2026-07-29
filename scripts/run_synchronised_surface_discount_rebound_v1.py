#!/usr/bin/env python3
"""Synchronised option-surface discount rebound discovery.

A distinct rebound family: buy a CE/PE option only after its whole option wing
is synchronously repriced downward with low dispersion, broad negative breadth,
volume/OI participation and causal stabilisation. This is intentionally different
from single-contract capitulation and leading-wing continuation.

Research only. No broker, paper, live or production action.
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

from scripts import run_inventory_absorption_transition_v1 as common
from scripts import run_leading_wing_pressure_persistence_v1 as prev
from scripts import run_option_surface_transition_discovery_v1 as base
from scripts.run_conditional_precursor_discrimination_v2 import PRIOR_REL, stable_json

OUT_REL = Path("runtime/research/synchronised_surface_discount_rebound_v1")
RESEARCH_REL = Path("research/synchronised_surface_discount_rebound_v1")
EVENT_FILE = "event_universe_5m.parquet"
NORMAL_COST_PCT = 0.10
STRESS_COST_PCT = 1.00
TARGET_PREMIUM = 120.0
MAX_SIGNALS_PER_SESSION = 2
COOLDOWN_MINUTES = 20

MECHANISMS = (
    "low_dispersion_surface_washout_rebound",
    "broad_negative_positive_acceleration",
    "volume_absorption_after_washout",
    "mirror_divergence_discount_rebound",
    "oi_supported_discount_absorption",
    "late_session_surface_discount_rebound",
    "near_expiry_discount_rebound",
    "compressed_discount_release",
    "two_bar_decelerating_selloff",
    "breadth_delta_repair_after_washout",
)


def q(frame: pd.DataFrame, column: str, quantile: float, default: float = 0.0) -> float:
    values = common._finite(frame[column]).dropna()
    return float(values.quantile(quantile)) if not values.empty else float(default)


def thresholds(training: pd.DataFrame) -> dict[str, float]:
    return {
        "ret15": q(training, "prior_5m_return_pct", 0.15),
        "ret25": q(training, "prior_5m_return_pct", 0.25),
        "ret35": q(training, "prior_5m_return_pct", 0.35),
        "acc60": q(training, "return_acceleration", 0.60),
        "acc70": q(training, "return_acceleration", 0.70),
        "acc80": q(training, "return_acceleration", 0.80),
        "vol60": q(training, "prior_5m_volume_ratio", 0.60, 1.0),
        "vol70": q(training, "prior_5m_volume_ratio", 0.70, 1.0),
        "vacc70": q(training, "volume_acceleration", 0.70),
        "oi60": q(training, "oi_change_ratio", 0.60),
        "oi70": q(training, "oi_change_ratio", 0.70),
        "breadth25": q(training, "breadth_positive", 0.25, 0.35),
        "breadth35": q(training, "breadth_positive", 0.35, 0.45),
        "bdelta60": q(training, "breadth_delta", 0.60),
        "bdelta70": q(training, "breadth_delta", 0.70),
        "bacc60": q(training, "breadth_acceleration", 0.60),
        "surface25": q(training, "surface_median_return", 0.25),
        "surface35": q(training, "surface_median_return", 0.35),
        "sacc60": q(training, "surface_median_acceleration", 0.60),
        "disp25": q(training, "surface_return_dispersion", 0.25),
        "disp35": q(training, "surface_return_dispersion", 0.35),
        "range25": q(training, "prior_10m_range_pct", 0.25),
        "mirror60": q(training, "mirror_return", 0.60),
    }


def masks(frame: pd.DataFrame, cut: dict[str, float]) -> dict[str, pd.Series]:
    ret = frame["prior_5m_return_pct"]
    prev_ret = frame["previous_return"]
    acc = frame["return_acceleration"]
    vol = frame["prior_5m_volume_ratio"]
    vacc = frame["volume_acceleration"]
    oi = frame["oi_change_ratio"]
    mirror = frame["mirror_return"]
    macc = frame["mirror_acceleration"]
    breadth = frame["breadth_positive"]
    bdelta = frame["breadth_delta"]
    bacc = frame["breadth_acceleration"]
    smedian = frame["surface_median_return"]
    sacc = frame["surface_median_acceleration"]
    dispersion = frame["surface_return_dispersion"]
    volume_breadth = frame["breadth_volume"]
    range10 = frame["prior_10m_range_pct"]

    washout = (
        (ret <= cut["ret35"])
        & (smedian <= cut["surface35"])
        & (breadth <= min(0.45, cut["breadth35"]))
        & (dispersion <= cut["disp35"])
    )
    hard_washout = (
        (ret <= cut["ret25"])
        & (smedian <= cut["surface25"])
        & (breadth <= min(0.35, cut["breadth25"]))
        & (dispersion <= cut["disp25"])
    )
    stabilising = (acc >= cut["acc60"]) | (sacc >= cut["sacc60"]) | (bdelta >= cut["bdelta60"])
    mirror_not_confirming = (mirror >= 0) | (mirror >= cut["mirror60"]) | (macc >= 0)

    result = {
        "low_dispersion_surface_washout_rebound": washout & stabilising & (volume_breadth >= 0.50),
        "broad_negative_positive_acceleration": hard_washout & (acc >= cut["acc70"]) & (bdelta >= cut["bdelta60"]),
        "volume_absorption_after_washout": washout & (vol >= cut["vol70"]) & (vacc >= cut["vacc70"]) & stabilising,
        "mirror_divergence_discount_rebound": washout & mirror_not_confirming & (acc >= cut["acc60"]),
        "oi_supported_discount_absorption": washout & (oi >= cut["oi70"]) & (vol >= cut["vol60"]) & stabilising,
        "late_session_surface_discount_rebound": washout & frame["minute_of_day"].between(750, 870, inclusive="both") & stabilising,
        "near_expiry_discount_rebound": washout & frame["days_to_expiry"].between(0, 2, inclusive="both") & (acc >= cut["acc70"]),
        "compressed_discount_release": washout & (range10 <= cut["range25"]) & (acc >= cut["acc70"]) & (bacc >= cut["bacc60"]),
        "two_bar_decelerating_selloff": hard_washout & (prev_ret < ret) & (acc >= cut["acc60"]) & (vol >= cut["vol60"]),
        "breadth_delta_repair_after_washout": washout & (bdelta >= cut["bdelta70"]) & (bacc >= cut["bacc60"]),
    }
    return {name: value.fillna(False) for name, value in result.items()}


def prepare(event_path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(event_path, columns=base.CAUSAL_COLUMNS)
    frame = base._surface_features(frame)
    return frame.loc[frame["minute_of_day"].between(585, 870, inclusive="both")].copy()


def eligible(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["entry_price_next_open"].between(30.0, 250.0, inclusive="both")
        & frame["days_to_expiry"].between(0, 7, inclusive="both")
        & (frame["surface_count"] >= 3)
        & (frame["volume"] > 0)
        & frame["previous_return"].notna()
        & frame["mirror_return"].notna()
        & frame["surface_median_return"].notna()
        & frame["surface_return_dispersion"].notna()
    )


def onset(frame: pd.DataFrame, mask: pd.Series) -> pd.Series:
    prior = mask.groupby(frame["expired_instrument_key"], sort=False).shift(1, fill_value=False)
    return mask & ~prior


def select(frame: pd.DataFrame, mask: pd.Series, mechanism: str, sessions: list[str]) -> pd.DataFrame:
    candidates = frame.loc[onset(frame, mask) & eligible(frame) & frame["session_id"].isin(sessions)].copy()
    if candidates.empty:
        return candidates
    candidates["mechanism"] = mechanism
    candidates["premium_distance"] = (candidates["entry_price_next_open"] - TARGET_PREMIUM).abs()
    candidates["score"] = (
        -1.20 * candidates["surface_median_return"].fillna(0)
        -0.75 * candidates["prior_5m_return_pct"].fillna(0)
        -0.25 * candidates["surface_return_dispersion"].fillna(0)
        + 1.25 * candidates["return_acceleration"].fillna(0)
        + 8.0 * candidates["breadth_delta"].fillna(0)
        + 0.50 * candidates["breadth_acceleration"].fillna(0)
        + 0.40 * candidates["prior_5m_volume_ratio"].fillna(0)
        + 0.30 * candidates["oi_change_ratio"].fillna(0)
    )
    candidates = candidates.sort_values(
        ["session_id", "timestamp", "score", "premium_distance", "expired_instrument_key"],
        ascending=[True, True, False, True, True],
        kind="mergesort",
    ).drop_duplicates(["session_id", "timestamp"], keep="first")
    chosen: list[int] = []
    cooldown = pd.Timedelta(minutes=COOLDOWN_MINUTES)
    for _, group in candidates.groupby("session_id", sort=True, observed=True):
        last: pd.Timestamp | None = None
        count = 0
        for index, row in group.iterrows():
            stamp = row["timestamp"]
            if last is not None and stamp - last < cooldown:
                continue
            chosen.append(index)
            last = stamp
            count += 1
            if count >= MAX_SIGNALS_PER_SESSION:
                break
    return candidates.loc[chosen].copy() if chosen else candidates.iloc[0:0].copy()


def oof_gate(metric: common.Metrics) -> bool:
    return bool(
        metric.trades >= 80
        and metric.sessions >= 60
        and metric.profit_factor is not None and metric.profit_factor >= 1.30
        and metric.mean_return_pct is not None and metric.mean_return_pct > 0
        and metric.median_return_pct is not None and metric.median_return_pct >= 0
        and metric.remove_top_five_profit_factor is not None and metric.remove_top_five_profit_factor >= 1.10
        and metric.stress_profit_factor is not None and metric.stress_profit_factor >= 1.05
        and metric.bootstrap_mean_ci_low is not None and metric.bootstrap_mean_ci_low > 0
        and metric.total_folds == 4 and metric.positive_folds >= 3
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.16)
        and (metric.largest_session_share is None or metric.largest_session_share <= 0.16)
    )


def holdout_gate(metric: common.Metrics) -> bool:
    return bool(
        metric.trades >= 24
        and metric.sessions >= 18
        and metric.profit_factor is not None and metric.profit_factor >= 1.20
        and metric.mean_return_pct is not None and metric.mean_return_pct > 0
        and metric.median_return_pct is not None and metric.median_return_pct >= 0
        and metric.remove_top_three_profit_factor is not None and metric.remove_top_three_profit_factor >= 1.05
        and metric.stress_profit_factor is not None and metric.stress_profit_factor >= 1.00
        and metric.total_halves == 2 and metric.positive_halves == 2
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.22)
        and (metric.largest_session_share is None or metric.largest_session_share <= 0.22)
    )


def control_gate(primary: common.Metrics, mirror: common.Metrics, delayed: common.Metrics) -> bool:
    mirror_rejected = bool(
        mirror.trades >= max(10, int(primary.trades * 0.45))
        and mirror.mean_return_pct is not None and mirror.mean_return_pct <= 0
        and (mirror.profit_factor is None or mirror.profit_factor <= 1.05)
    )
    delayed_degrades = bool(
        delayed.trades >= max(10, int(primary.trades * 0.45))
        and primary.mean_return_pct is not None and delayed.mean_return_pct is not None
        and primary.mean_return_pct > delayed.mean_return_pct
        and primary.profit_factor is not None and delayed.profit_factor is not None
        and primary.profit_factor >= delayed.profit_factor
    )
    return mirror_rejected and delayed_degrades


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    root = parser.parse_args().repo_root.resolve()
    event_path = root / PRIOR_REL / EVENT_FILE
    out = root / OUT_REL
    research = root / RESEARCH_REL
    out.mkdir(parents=True, exist_ok=True)
    research.mkdir(parents=True, exist_ok=True)

    causal = prepare(event_path)
    research_sessions, holdout_sessions = common.research_holdout_sessions(causal)
    folds = common.expanding_folds(research_sessions)
    research_outcomes = base._load_outcomes(event_path, base._raw_sessions(causal, research_sessions))
    contract = {
        "schema_version": "synchronised_surface_discount_rebound_v1",
        "mechanism_hypothesis": "whole_option_wing_discount_low_dispersion_breadth_washout_then_rebound",
        "mechanisms": list(MECHANISMS),
        "side": "BUY_CE_OR_PE_ONLY",
        "entry": "same_contract_open_exactly_one_minute_after_completed_signal",
        "outcome_horizon_minutes": 5,
        "premium_range": [30.0, 250.0],
        "days_to_expiry": [0, 7],
        "max_signals_per_session": MAX_SIGNALS_PER_SESSION,
        "cooldown_minutes": COOLDOWN_MINUTES,
        "normal_cost_pct": NORMAL_COST_PCT,
        "stress_cost_pct": STRESS_COST_PCT,
        "research_sessions": len(research_sessions),
        "holdout_sessions": len(holdout_sessions),
        "threshold_policy": "prior_training_session_quantiles_per_expanding_fold",
        "holdout_policy": "latest_25pct_unopened_until_oof_survivor_freeze",
        "multiplicity_policy": "ten_preregistered_mechanisms_top_two_only_open_holdout",
        "research_only": True,
        "paper_or_live_authorized": False,
        "allowed_for_live_execution": False,
    }
    contract["semantic_sha256"] = common.semantic_hash(contract)
    stable_json(out / "frozen_contract.json", contract)

    ledgers: dict[str, list[pd.DataFrame]] = {name: [] for name in MECHANISMS}
    fold_cuts: list[dict[str, Any]] = []
    for training_sessions, testing_sessions, fold_id in folds:
        training = causal.loc[causal["session_id"].isin(training_sessions)]
        testing = causal.loc[causal["session_id"].isin(testing_sessions)]
        cut = thresholds(training)
        fold_cuts.append({"fold_id": fold_id, "training_sessions": len(training_sessions), "testing_sessions": len(testing_sessions), "thresholds": cut})
        fold_masks = masks(testing, cut)
        for mechanism in MECHANISMS:
            signals = select(testing, fold_masks[mechanism], mechanism, testing_sessions)
            trades = prev.attach(signals, research_outcomes, fold_id)
            if not trades.empty:
                ledgers[mechanism].append(trades)
    stable_json(out / "fold_thresholds.json", fold_cuts)

    records: list[dict[str, Any]] = []
    oof_ledgers: list[pd.DataFrame] = []
    survivors: list[tuple[str, common.Metrics]] = []
    for mechanism in MECHANISMS:
        trades = pd.concat(ledgers[mechanism], ignore_index=True, sort=False) if ledgers[mechanism] else pd.DataFrame()
        metric = common.calculate_metrics(trades)
        passed = oof_gate(metric)
        records.append({"mechanism": mechanism, **asdict(metric), "oof_gate": passed})
        if not trades.empty:
            oof_ledgers.append(trades.assign(partition="research_oof"))
        if passed:
            survivors.append((mechanism, metric))
    survivors = sorted(
        survivors,
        key=lambda item: (
            item[1].remove_top_five_profit_factor or -math.inf,
            item[1].stress_profit_factor or -math.inf,
            item[1].profit_factor or -math.inf,
            item[1].trades,
        ),
        reverse=True,
    )[:2]
    names = [name for name, _ in survivors]
    stable_json(out / "oof_screen.json", {"records": records, "survivors_frozen_for_holdout": names, "holdout_outcomes_materialized": bool(names)})

    holdout_records: list[dict[str, Any]] = []
    holdout_ledgers: list[pd.DataFrame] = []
    validated: list[str] = []
    if names:
        final_cut = thresholds(causal.loc[causal["session_id"].isin(research_sessions)])
        holdout = causal.loc[causal["session_id"].isin(holdout_sessions)]
        holdout_outcomes = base._load_outcomes(event_path, base._raw_sessions(causal, holdout_sessions))
        holdout_masks = masks(holdout, final_cut)
        for mechanism in names:
            signals = select(holdout, holdout_masks[mechanism], mechanism, holdout_sessions)
            primary = prev.attach(signals, holdout_outcomes, "holdout")
            mirror = prev.mirror_control(signals, holdout, holdout_outcomes)
            delayed = prev.delayed_control(signals, holdout, holdout_outcomes)
            pm = common.calculate_metrics(primary)
            mm = common.calculate_metrics(mirror)
            dm = common.calculate_metrics(delayed)
            economic = holdout_gate(pm)
            controls = control_gate(pm, mm, dm)
            passed = economic and controls
            holdout_records.append({
                "mechanism": mechanism,
                "primary": asdict(pm),
                "mirror_control": asdict(mm),
                "delayed_control": asdict(dm),
                "holdout_economic_gate": economic,
                "control_gate": controls,
                "holdout_gate": passed,
            })
            if not primary.empty:
                holdout_ledgers.append(primary.assign(partition="holdout_primary"))
            if not mirror.empty:
                holdout_ledgers.append(mirror.assign(partition="holdout_mirror"))
            if not delayed.empty:
                holdout_ledgers.append(delayed.assign(partition="holdout_delayed"))
            if passed:
                validated.append(mechanism)
    stable_json(out / "holdout_screen.json", {"records": holdout_records, "validated_candidates": validated, "holdout_outcomes_materialized": bool(names)})

    all_ledgers = oof_ledgers + holdout_ledgers
    if all_ledgers:
        pd.concat(all_ledgers, ignore_index=True, sort=False).to_csv(out / "trade_ledger.csv", index=False)

    verdict = (
        "STRUCTURAL_EDGE_FOUND_SYNCHRONISED_SURFACE_DISCOUNT_REBOUND_CANDLE_PROXY"
        if validated
        else ("NO_OOF_SURVIVOR_IN_SYNCHRONISED_SURFACE_DISCOUNT_REBOUND_FAMILY" if not names else "OOF_SURVIVORS_FAILED_HOLDOUT_OR_CONTROLS")
    )
    final = {
        "principal_verdict": verdict,
        "structural_edge_found": bool(validated),
        "oof_survivors": names,
        "holdout_survivors": validated,
        "holdout_outcomes_materialized": bool(names),
        "contract_semantic_sha256": contract["semantic_sha256"],
        "claim_boundary": "HISTORICAL_FIVE_MINUTE_CANDLE_PROXY_RESEARCH_ONLY",
        "execution_certification": "BLOCKED_AUTHORITATIVE_TIMESTAMP_ALIGNED_SPREAD_MISSING",
        "research_only": True,
        "paper_or_live_authorized": False,
        "allowed_for_live_execution": False,
    }
    final["semantic_sha256"] = common.semantic_hash(final)
    stable_json(out / "final_decision.json", final)
    (research / "RESULT.md").write_text(
        "# Synchronised Surface Discount Rebound V1\n\n"
        f"Principal verdict: `{verdict}`\n\n"
        f"OOF survivors: `{names}`\n\n"
        f"Holdout survivors: `{validated}`\n\n"
        f"Research sessions: `{len(research_sessions)}`; holdout sessions: `{len(holdout_sessions)}`.\n\n"
        "Historical five-minute OHLCV candle proxy only. No paper or live authorization.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
