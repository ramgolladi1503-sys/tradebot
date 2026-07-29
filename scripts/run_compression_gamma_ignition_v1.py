#!/usr/bin/env python3
"""Compression gamma-ignition discovery V1.

A fresh buy-option mechanism family using the preserved NIFTY option OHLCV corpus:
quiet/low-range option contracts or option wings that show first participation
shock before a short convex expansion. This is neither late-day capitulation,
leading-wing continuation, nor synchronized discount rebound.

Research only. No broker, paper, live, provider, order, or production action.
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
from scripts import run_option_surface_transition_discovery_v1 as base
from scripts.run_conditional_precursor_discrimination_v2 import PRIOR_REL, stable_json

OUT_REL = Path("runtime/research/compression_gamma_ignition_v1")
RESEARCH_REL = Path("research/compression_gamma_ignition_v1")
EVENT_FILE = "event_universe_5m.parquet"
NORMAL_COST_PCT = 0.10
STRESS_COST_PCT = 1.00
TARGET_PREMIUM = 100.0
MAX_SIGNALS_PER_SESSION = 2
COOLDOWN_MINUTES = 20

MECHANISMS = (
    "quiet_contract_volume_ignition",
    "quiet_surface_breadth_ignition",
    "low_premium_gamma_kick",
    "near_expiry_compression_ignition",
    "oi_volume_spark_after_compression",
    "mirror_decay_compression_ignite",
    "two_bar_compression_acceptance",
    "mass_shift_after_quiet_surface",
    "midday_gamma_ignition",
    "late_day_gamma_ignition",
)


def q(frame: pd.DataFrame, column: str, quantile: float, default: float = 0.0) -> float:
    values = common._finite(frame[column]).dropna()
    return float(values.quantile(quantile)) if not values.empty else float(default)


def thresholds(training: pd.DataFrame) -> dict[str, float]:
    abs_ret = common._finite(training["prior_5m_return_pct"]).abs()
    return {
        "range20": q(training, "prior_10m_range_pct", 0.20),
        "range30": q(training, "prior_10m_range_pct", 0.30),
        "absret25": float(abs_ret.dropna().quantile(0.25)) if abs_ret.notna().any() else 0.0,
        "ret45": q(training, "prior_5m_return_pct", 0.45),
        "ret55": q(training, "prior_5m_return_pct", 0.55),
        "acc60": q(training, "return_acceleration", 0.60),
        "acc70": q(training, "return_acceleration", 0.70),
        "vol70": q(training, "prior_5m_volume_ratio", 0.70, 1.0),
        "vol80": q(training, "prior_5m_volume_ratio", 0.80, 1.0),
        "vacc70": q(training, "volume_acceleration", 0.70),
        "vacc80": q(training, "volume_acceleration", 0.80),
        "oi65": q(training, "oi_change_ratio", 0.65),
        "oi75": q(training, "oi_change_ratio", 0.75),
        "breadth55": q(training, "breadth_positive", 0.55, 0.50),
        "breadth65": q(training, "breadth_positive", 0.65, 0.60),
        "bdelta65": q(training, "breadth_delta", 0.65),
        "bdelta75": q(training, "breadth_delta", 0.75),
        "bvol65": q(training, "breadth_volume", 0.65, 0.50),
        "disp30": q(training, "surface_return_dispersion", 0.30),
        "disp40": q(training, "surface_return_dispersion", 0.40),
        "mass70": q(training, "directional_mass_shift", 0.70),
        "asym60": q(training, "option_asymmetry", 0.60),
    }


def masks(frame: pd.DataFrame, cut: dict[str, float]) -> dict[str, pd.Series]:
    ret = frame["prior_5m_return_pct"]
    prev = frame["previous_return"]
    acc = frame["return_acceleration"]
    vol = frame["prior_5m_volume_ratio"]
    vacc = frame["volume_acceleration"]
    oi = frame["oi_change_ratio"]
    mirror = frame["mirror_return"]
    macc = frame["mirror_acceleration"]
    asym = frame["option_asymmetry"]
    breadth = frame["breadth_positive"]
    bdelta = frame["breadth_delta"]
    bvol = frame["breadth_volume"]
    dispersion = frame["surface_return_dispersion"]
    smedian = frame["surface_median_return"]
    sacc = frame["surface_median_acceleration"]
    mass = frame["directional_mass_shift"]
    low_range = frame["prior_10m_range_pct"] <= cut["range30"]
    very_low_range = frame["prior_10m_range_pct"] <= cut["range20"]
    quiet_contract = low_range & (ret.abs() <= max(cut["absret25"], 0.01))
    spark = (vol >= cut["vol70"]) & (vacc >= cut["vacc70"])
    strong_spark = (vol >= cut["vol80"]) & (vacc >= cut["vacc80"])
    first_positive = (ret >= cut["ret55"]) & (acc >= cut["acc60"])
    mirror_not_confirming = mirror.fillna(0) <= 0
    mirror_decay = mirror_not_confirming & (macc.fillna(0) <= 0)
    surface_quiet = (dispersion <= cut["disp40"]) & (bvol >= max(0.45, cut["bvol65"]))
    surface_turn = (breadth >= max(0.50, cut["breadth55"])) & (bdelta >= cut["bdelta65"]) & (sacc >= 0)
    result = {
        "quiet_contract_volume_ignition": quiet_contract & spark & first_positive & mirror_not_confirming,
        "quiet_surface_breadth_ignition": surface_quiet & very_low_range & surface_turn & (ret >= cut["ret45"]),
        "low_premium_gamma_kick": quiet_contract & strong_spark & (frame["entry_price_next_open"].between(20.0, 90.0, inclusive="both")) & (acc >= cut["acc70"]),
        "near_expiry_compression_ignition": quiet_contract & frame["days_to_expiry"].between(0, 2, inclusive="both") & strong_spark & surface_turn,
        "oi_volume_spark_after_compression": low_range & spark & (oi >= cut["oi75"]) & first_positive & (breadth >= 0.45),
        "mirror_decay_compression_ignite": quiet_contract & spark & mirror_decay & (asym >= cut["asym60"]),
        "two_bar_compression_acceptance": low_range & (prev <= cut["ret55"]) & (ret > prev) & frame["bar_acceptance"].fillna(False) & spark,
        "mass_shift_after_quiet_surface": surface_quiet & surface_turn & (mass >= cut["mass70"]) & (vol >= cut["vol70"]),
        "midday_gamma_ignition": quiet_contract & frame["minute_of_day"].between(660, 780, inclusive="both") & spark & surface_turn,
        "late_day_gamma_ignition": quiet_contract & frame["minute_of_day"].between(780, 870, inclusive="both") & strong_spark & mirror_decay,
    }
    return {name: value.fillna(False) for name, value in result.items()}


def prepare(event_path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(event_path, columns=base.CAUSAL_COLUMNS)
    frame = base._surface_features(frame)
    return frame.loc[frame["minute_of_day"].between(585, 870, inclusive="both")].copy()


def eligible(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["entry_price_next_open"].between(20.0, 180.0, inclusive="both")
        & frame["days_to_expiry"].between(0, 7, inclusive="both")
        & (frame["surface_count"] >= 3)
        & (frame["volume"] > 0)
        & frame["previous_return"].notna()
        & frame["prior_10m_range_pct"].notna()
        & frame["mirror_return"].notna()
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
        -0.35 * candidates["prior_10m_range_pct"].fillna(0)
        + 1.0 * candidates["return_acceleration"].fillna(0)
        + 0.75 * candidates["volume_acceleration"].fillna(0)
        + 0.50 * candidates["prior_5m_volume_ratio"].fillna(0)
        + 7.0 * candidates["breadth_delta"].fillna(0)
        + 0.35 * candidates["oi_change_ratio"].fillna(0)
        + 0.01 * candidates["directional_mass_shift"].fillna(0)
        + 0.25 * candidates["option_asymmetry"].fillna(0)
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


def attach(signals: pd.DataFrame, outcomes: pd.DataFrame, fold_id: str) -> pd.DataFrame:
    trades = base._attach_outcomes(signals, outcomes)
    if trades.empty:
        return trades
    horizons = set(pd.to_numeric(trades["label_horizon_minutes"], errors="coerce").dropna().astype(int))
    if horizons != {5}:
        raise RuntimeError(f"Expected exact five-minute outcomes, got {sorted(horizons)}")
    trades["fold_id"] = fold_id
    return trades


def mirror_control(signals: pd.DataFrame, causal: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    lookup = causal[["session_id", "timestamp", "expiry_id", "strike", "option_type", "expired_instrument_key", "entry_price_next_open"]].drop_duplicates(
        ["session_id", "timestamp", "expiry_id", "strike", "option_type"]
    )
    source = signals[["session_id", "timestamp", "expiry_id", "strike", "option_type", "mechanism"]].copy()
    source["option_type"] = source["option_type"].map({"CE": "PE", "PE": "CE"})
    mirrored = source.merge(lookup, on=["session_id", "timestamp", "expiry_id", "strike", "option_type"], how="inner", validate="many_to_one")
    return attach(mirrored, outcomes, "holdout_mirror") if not mirrored.empty else mirrored


def delayed_control(signals: pd.DataFrame, causal: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    source = signals[["expired_instrument_key", "timestamp", "mechanism"]].copy()
    source["timestamp"] = source["timestamp"] + pd.Timedelta(minutes=5)
    delayed = source.merge(causal.drop_duplicates(["expired_instrument_key", "timestamp"]), on=["expired_instrument_key", "timestamp"], how="inner", validate="many_to_one")
    return attach(delayed, outcomes, "holdout_delayed") if not delayed.empty else delayed


def oof_gate(metric: common.Metrics) -> bool:
    return bool(
        metric.trades >= 80
        and metric.sessions >= 55
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
        "schema_version": "compression_gamma_ignition_v1",
        "mechanism_hypothesis": "quiet_low_range_option_contract_or_wing_first_participation_shock_before_short_convex_expansion",
        "mechanisms": list(MECHANISMS),
        "side": "BUY_CE_OR_PE_ONLY",
        "entry": "same_contract_open_exactly_one_minute_after_completed_signal",
        "outcome_horizon_minutes": 5,
        "premium_range": [20.0, 180.0],
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
            trades = attach(signals, research_outcomes, fold_id)
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
        key=lambda item: (item[1].remove_top_five_profit_factor or -math.inf, item[1].stress_profit_factor or -math.inf, item[1].profit_factor or -math.inf, item[1].trades),
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
            primary = attach(signals, holdout_outcomes, "holdout")
            mirror = mirror_control(signals, holdout, holdout_outcomes)
            delayed = delayed_control(signals, holdout, holdout_outcomes)
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
        "STRUCTURAL_EDGE_FOUND_COMPRESSION_GAMMA_IGNITION_CANDLE_PROXY"
        if validated
        else ("NO_OOF_SURVIVOR_IN_COMPRESSION_GAMMA_IGNITION_FAMILY" if not names else "OOF_SURVIVORS_FAILED_HOLDOUT_OR_CONTROLS")
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
        "# Compression Gamma Ignition V1\n\n"
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
