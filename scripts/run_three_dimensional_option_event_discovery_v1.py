#!/usr/bin/env python3
"""Three-dimensional option-event discovery over preserved NIFTY option OHLCV.

This campaign deliberately moves away from single-contract rebound masks.  A
candidate must be supported by a causal event tensor with three completed-bar
axes:

1. time transition: current bar versus the same contract's previous bar;
2. strike neighbourhood: the contract versus nearby strikes in the same wing;
3. CE/PE mirror: the same strike on the opposite wing at the same timestamp.

All thresholds are recomputed only from prior training sessions inside expanding
chronological folds.  The latest 25% chronological holdout is opened only for at
most two OOF survivors.  Research only; no paper, broker, or live action is
possible from this runner.
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

from scripts import run_inventory_absorption_transition_v1 as common
from scripts import run_option_surface_transition_discovery_v1 as base
from scripts.run_conditional_precursor_discrimination_v2 import PRIOR_REL, stable_json

OUT_REL = Path("runtime/research/three_dimensional_option_event_discovery_v1")
RESEARCH_REL = Path("research/three_dimensional_option_event_discovery_v1")
EVENT_FILE = "event_universe_5m.parquet"
SEED = 20260729
NORMAL_COST_PCT = 0.10
STRESS_COST_PCT = 1.00
MAX_SIGNALS_PER_SESSION = 3
COOLDOWN_MINUTES = 10
TARGET_PREMIUM = 150.0

MECHANISMS = (
    "local_cluster_washout_repair",
    "strike_tube_absorption",
    "isolated_contract_reclaim",
    "mirror_pin_reversal_3d",
    "local_volume_node_repair",
    "oi_tube_defence_3d",
    "wing_edge_convexity_snapback",
    "center_mass_snapback_3d",
    "late_session_3d_repair",
    "near_expiry_3d_repair",
)


def _finite(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)


def _q(frame: pd.DataFrame, column: str, quantile: float, default: float = 0.0) -> float:
    values = _finite(frame[column]).dropna()
    return float(values.quantile(quantile)) if not values.empty else float(default)


def semantic_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def add_three_dimensional_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add causal local-strike and tensor features.

    The rolling neighbourhood is cross-sectional only: same session, timestamp,
    expiry and option type, sorted by strike.  It never uses later timestamps or
    future outcomes.
    """
    frame = frame.copy()
    surface_keys = ["session_id", "timestamp", "expiry_id", "option_type"]
    frame = frame.sort_values(surface_keys + ["strike"], kind="mergesort")

    group = frame.groupby(surface_keys, sort=False, observed=True)
    frame["_strike_pos"] = group.cumcount().astype(float)
    frame["_surface_size"] = group["strike"].transform("size").astype(float)
    denom = (frame["_surface_size"] - 1.0).replace(0.0, np.nan)
    frame["strike_rank_pct"] = (frame["_strike_pos"] / denom).fillna(0.5)
    frame["wing_edge_distance"] = (frame["strike_rank_pct"] - 0.5).abs() * 2.0

    frame["_positive_return_flag"] = (frame["prior_5m_return_pct"] > 0).astype(float)
    rolling_specs = {
        "local_median_return": ("prior_5m_return_pct", "median"),
        "local_median_acceleration": ("return_acceleration", "median"),
        "local_volume_ratio_mean": ("prior_5m_volume_ratio", "mean"),
        "local_breadth_positive": ("_positive_return_flag", "mean"),
        "local_return_dispersion": ("prior_5m_return_pct", "std"),
    }
    for output, (column, function) in rolling_specs.items():
        frame[output] = group[column].transform(
            lambda values, fn=function: values.rolling(window=5, center=True, min_periods=2).agg(fn)
        )
    frame["local_return_dispersion"] = frame["local_return_dispersion"].fillna(0.0)
    frame["local_return_residual"] = frame["prior_5m_return_pct"] - frame["local_median_return"]

    instrument = frame.groupby("expired_instrument_key", sort=False, observed=True)
    frame["previous_local_median_return"] = instrument["local_median_return"].shift(1)
    frame["local_median_repair"] = frame["local_median_return"] - frame["previous_local_median_return"]
    frame["tensor_mirror_pressure"] = frame["local_median_return"] - frame["mirror_return"]
    frame["tensor_repair_pressure"] = (
        -frame["local_median_return"].fillna(0)
        + frame["local_median_acceleration"].fillna(0)
        + frame["return_acceleration"].fillna(0)
        - frame["mirror_return"].fillna(0)
    )
    return frame.drop(columns=["_strike_pos", "_surface_size", "_positive_return_flag"], errors="ignore")


def prepare_causal(event_path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(event_path, columns=base.CAUSAL_COLUMNS)
    frame = base._surface_features(frame)
    frame = frame.loc[frame["minute_of_day"].between(585, 880, inclusive="both")].copy()
    return add_three_dimensional_features(frame)


def thresholds(training: pd.DataFrame) -> dict[str, float]:
    return {
        "ret10": _q(training, "prior_5m_return_pct", 0.10),
        "ret20": _q(training, "prior_5m_return_pct", 0.20),
        "ret30": _q(training, "prior_5m_return_pct", 0.30),
        "ret70": _q(training, "prior_5m_return_pct", 0.70),
        "prev10": _q(training, "previous_return", 0.10),
        "acc65": _q(training, "return_acceleration", 0.65),
        "acc75": _q(training, "return_acceleration", 0.75),
        "vol65": _q(training, "prior_5m_volume_ratio", 0.65, 1.0),
        "vol75": _q(training, "prior_5m_volume_ratio", 0.75, 1.0),
        "vacc60": _q(training, "volume_acceleration", 0.60),
        "oi65": _q(training, "oi_change_ratio", 0.65),
        "oi75": _q(training, "oi_change_ratio", 0.75),
        "breadth_delta60": _q(training, "breadth_delta", 0.60),
        "surface_acc60": _q(training, "surface_median_acceleration", 0.60),
        "local_ret25": _q(training, "local_median_return", 0.25),
        "local_ret35": _q(training, "local_median_return", 0.35),
        "local_acc65": _q(training, "local_median_acceleration", 0.65),
        "local_acc75": _q(training, "local_median_acceleration", 0.75),
        "local_breadth35": _q(training, "local_breadth_positive", 0.35),
        "local_breadth60": _q(training, "local_breadth_positive", 0.60),
        "local_disp35": _q(training, "local_return_dispersion", 0.35),
        "local_vol70": _q(training, "local_volume_ratio_mean", 0.70, 1.0),
        "local_repair65": _q(training, "local_median_repair", 0.65),
        "resid30": _q(training, "local_return_residual", 0.30),
        "resid70": _q(training, "local_return_residual", 0.70),
        "mirror40": _q(training, "mirror_return", 0.40),
        "mirror70": _q(training, "mirror_return", 0.70),
        "asym25": _q(training, "option_asymmetry", 0.25),
        "asym70": _q(training, "option_asymmetry", 0.70),
        "edge35": _q(training, "wing_edge_distance", 0.35),
        "edge70": _q(training, "wing_edge_distance", 0.70),
        "mass_shift70": _q(training, "directional_mass_shift", 0.70),
    }


def mechanism_masks(frame: pd.DataFrame, cut: dict[str, float]) -> dict[str, pd.Series]:
    ret = frame["prior_5m_return_pct"]
    prev = frame["previous_return"]
    accel = frame["return_acceleration"]
    volume = frame["prior_5m_volume_ratio"]
    vacc = frame["volume_acceleration"]
    oi = frame["oi_change_ratio"]
    mirror = frame["mirror_return"]
    asym = frame["option_asymmetry"]
    local_ret = frame["local_median_return"]
    local_acc = frame["local_median_acceleration"]
    local_breadth = frame["local_breadth_positive"]
    local_disp = frame["local_return_dispersion"]
    local_vol = frame["local_volume_ratio_mean"]
    residual = frame["local_return_residual"]
    local_repair = frame["local_median_repair"]
    edge = frame["wing_edge_distance"]

    local_washout_repair = (
        (local_ret <= cut["local_ret25"])
        & (ret < 0)
        & (accel >= cut["acc65"])
        & (local_acc >= cut["local_acc65"])
        & (local_breadth <= max(cut["local_breadth35"], 0.45))
        & (volume >= cut["vol65"])
    )
    tube_absorption = (
        (prev <= cut["prev10"])
        & (ret < 0)
        & (ret >= cut["ret30"])
        & (local_ret <= cut["local_ret35"])
        & (local_disp <= cut["local_disp35"])
        & ((mirror >= cut["mirror70"]) | (asym <= cut["asym25"]))
    )
    isolated_reclaim = (
        (ret >= cut["ret70"])
        & (residual >= cut["resid70"])
        & (frame["surface_median_return"] < 0)
        & (local_breadth <= 0.50)
        & (mirror <= cut["mirror40"])
    )
    mirror_pin = (
        (ret < 0)
        & (local_ret <= cut["local_ret35"])
        & (local_acc >= cut["local_acc75"])
        & (mirror >= cut["mirror70"])
        & (asym <= cut["asym25"])
        & (volume >= cut["vol65"])
    )
    volume_node = (
        (prev <= cut["ret20"])
        & (local_ret <= cut["local_ret35"])
        & (local_vol >= cut["local_vol70"])
        & (vacc >= cut["vacc60"])
        & ((local_acc >= cut["local_acc65"]) | (local_repair >= cut["local_repair65"]))
    )
    oi_tube = (
        (oi >= cut["oi65"])
        & (local_ret <= cut["local_ret35"])
        & (accel >= cut["acc65"])
        & (frame["breadth_delta"] >= 0)
        & (local_breadth <= cut["local_breadth60"])
    )
    wing_edge_snapback = (
        (edge >= cut["edge70"])
        & (prev <= cut["ret20"])
        & (accel >= cut["acc75"])
        & (local_acc >= cut["local_acc65"])
        & (volume >= cut["vol65"])
    )
    center_mass_snapback = (
        (edge <= cut["edge35"])
        & (local_ret <= cut["local_ret35"])
        & (accel >= cut["acc65"])
        & ((frame["directional_mass_shift"] >= cut["mass_shift70"]) | (frame["surface_median_acceleration"] >= cut["surface_acc60"]))
        & (local_disp <= cut["local_disp35"])
    )

    masks = {
        "local_cluster_washout_repair": local_washout_repair,
        "strike_tube_absorption": tube_absorption,
        "isolated_contract_reclaim": isolated_reclaim,
        "mirror_pin_reversal_3d": mirror_pin,
        "local_volume_node_repair": volume_node,
        "oi_tube_defence_3d": oi_tube,
        "wing_edge_convexity_snapback": wing_edge_snapback,
        "center_mass_snapback_3d": center_mass_snapback,
        "late_session_3d_repair": (
            frame["minute_of_day"].between(780, 880, inclusive="both")
            & (local_washout_repair | mirror_pin | volume_node)
        ),
        "near_expiry_3d_repair": (
            frame["days_to_expiry"].between(0, 2, inclusive="both")
            & (local_washout_repair | tube_absorption | oi_tube)
            & (volume >= cut["vol75"])
        ),
    }
    return {name: mask.fillna(False) for name, mask in masks.items()}


def _eligible(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["entry_price_next_open"].between(30.0, 300.0, inclusive="both")
        & frame["days_to_expiry"].between(0, 7, inclusive="both")
        & (frame["surface_count"] >= 3)
        & (frame["volume"] > 0)
        & frame["previous_return"].notna()
        & frame["mirror_return"].notna()
        & frame["local_median_return"].notna()
        & frame["local_median_acceleration"].notna()
    )


def _onset(frame: pd.DataFrame, mask: pd.Series) -> pd.Series:
    prior = mask.groupby(frame["expired_instrument_key"], sort=False).shift(1, fill_value=False)
    return mask & ~prior


def select_signals(frame: pd.DataFrame, mask: pd.Series, mechanism: str, sessions: list[str]) -> pd.DataFrame:
    candidates = frame.loc[_onset(frame, mask) & _eligible(frame) & frame["session_id"].isin(sessions)].copy()
    if candidates.empty:
        return candidates
    candidates["mechanism"] = mechanism
    candidates["premium_distance"] = (candidates["entry_price_next_open"] - TARGET_PREMIUM).abs()
    candidates["mechanism_score"] = (
        -1.25 * candidates["local_median_return"].fillna(0)
        + 1.20 * candidates["local_median_acceleration"].fillna(0)
        + 0.90 * candidates["return_acceleration"].fillna(0)
        + 0.65 * candidates["local_return_residual"].fillna(0)
        + 5.00 * (1.0 - candidates["local_breadth_positive"].fillna(0.5))
        + 0.40 * candidates["prior_5m_volume_ratio"].fillna(0)
        + 0.35 * candidates["oi_change_ratio"].fillna(0)
        - 0.40 * candidates["local_return_dispersion"].fillna(0)
        - 0.10 * candidates["mirror_return"].fillna(0)
    )
    candidates = candidates.sort_values(
        ["session_id", "timestamp", "mechanism_score", "premium_distance", "expired_instrument_key"],
        ascending=[True, True, False, True, True],
        kind="mergesort",
    )
    candidates = candidates.drop_duplicates(["session_id", "timestamp"], keep="first")

    selected_indices: list[int] = []
    cooldown = pd.Timedelta(minutes=COOLDOWN_MINUTES)
    for _, session_frame in candidates.groupby("session_id", sort=True, observed=True):
        last_timestamp: pd.Timestamp | None = None
        count = 0
        for index, row in session_frame.iterrows():
            timestamp = row["timestamp"]
            if last_timestamp is not None and timestamp - last_timestamp < cooldown:
                continue
            selected_indices.append(index)
            last_timestamp = timestamp
            count += 1
            if count >= MAX_SIGNALS_PER_SESSION:
                break
    return candidates.loc[selected_indices].copy() if selected_indices else candidates.iloc[0:0].copy()


def attach(signals: pd.DataFrame, outcomes: pd.DataFrame, fold_id: str) -> pd.DataFrame:
    trades = base._attach_outcomes(signals, outcomes)
    if trades.empty:
        return trades
    horizons = set(pd.to_numeric(trades["label_horizon_minutes"], errors="coerce").dropna().astype(int).tolist())
    if horizons != {5}:
        raise RuntimeError(f"Expected exact five-minute outcomes, got {sorted(horizons)}")
    trades["fold_id"] = fold_id
    return trades


def oof_gate(metric: common.Metrics) -> bool:
    return bool(
        metric.trades >= 90
        and metric.sessions >= 65
        and metric.profit_factor is not None and metric.profit_factor >= 1.30
        and metric.mean_return_pct is not None and metric.mean_return_pct > 0
        and metric.median_return_pct is not None and metric.median_return_pct >= 0
        and metric.remove_top_five_profit_factor is not None and metric.remove_top_five_profit_factor >= 1.10
        and metric.stress_profit_factor is not None and metric.stress_profit_factor >= 1.05
        and metric.bootstrap_mean_ci_low is not None and metric.bootstrap_mean_ci_low > 0
        and metric.total_folds == 4 and metric.positive_folds >= 3
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.18)
        and (metric.largest_session_share is None or metric.largest_session_share <= 0.18)
    )


def holdout_gate(metric: common.Metrics) -> bool:
    return bool(
        metric.trades >= 24
        and metric.sessions >= 18
        and metric.profit_factor is not None and metric.profit_factor >= 1.15
        and metric.mean_return_pct is not None and metric.mean_return_pct > 0
        and metric.median_return_pct is not None and metric.median_return_pct >= 0
        and metric.remove_top_three_profit_factor is not None and metric.remove_top_three_profit_factor >= 1.00
        and metric.stress_profit_factor is not None and metric.stress_profit_factor >= 1.00
        and metric.total_halves == 2 and metric.positive_halves >= 1
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.25)
        and (metric.largest_session_share is None or metric.largest_session_share <= 0.25)
    )


def _concat(parts: list[pd.DataFrame]) -> pd.DataFrame:
    valid = [part for part in parts if part is not None and not part.empty]
    return pd.concat(valid, ignore_index=True, sort=False) if valid else pd.DataFrame()


def _metric_record(metric: common.Metrics) -> dict[str, Any]:
    return asdict(metric)


def _write_ledger(out: Path, ledgers: list[pd.DataFrame]) -> None:
    ledger = _concat(ledgers)
    if ledger.empty:
        return
    keep = [
        "partition", "mechanism", "session_id", "timestamp", "expired_instrument_key",
        "expiry_id", "option_type", "strike", "entry_price_next_open", "gross_return_pct",
        "net_return_pct", "stress_return_pct", "forward_mfe_points", "forward_mae_points",
        "forward_expansion_pct", "label_horizon_minutes", "is_expansion_event", "move_cluster_id",
        "prior_5m_return_pct", "previous_return", "return_acceleration", "surface_median_return",
        "surface_median_acceleration", "breadth_positive", "breadth_delta", "option_asymmetry",
        "mirror_return", "local_median_return", "local_median_acceleration", "local_breadth_positive",
        "local_return_dispersion", "local_return_residual", "local_median_repair", "wing_edge_distance",
        "prior_5m_volume_ratio", "oi_change_ratio", "days_to_expiry", "minute_of_day", "fold_id",
    ]
    ledger[[column for column in keep if column in ledger.columns]].to_csv(out / "trade_ledger.csv", index=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    root = args.repo_root.resolve()
    event_path = root / PRIOR_REL / EVENT_FILE
    out = root / OUT_REL
    research = root / RESEARCH_REL
    out.mkdir(parents=True, exist_ok=True)
    research.mkdir(parents=True, exist_ok=True)

    causal = prepare_causal(event_path)
    research_sessions, holdout_sessions = common.research_holdout_sessions(causal)
    folds = common.expanding_folds(research_sessions)
    research_outcomes = base._load_outcomes(event_path, base._raw_sessions(causal, research_sessions))

    contract = {
        "schema_version": "three_dimensional_option_event_discovery_v1",
        "mechanism_hypothesis": "causal_event_tensor_across_time_strike_neighbourhood_and_ce_pe_mirror_context",
        "mechanisms": list(MECHANISMS),
        "mechanism_count": len(MECHANISMS),
        "side": "BUY_CE_OR_PE_ONLY",
        "outcome_horizon_minutes": 5,
        "entry": "same_contract_open_exactly_one_minute_after_completed_signal",
        "max_signals_per_session": MAX_SIGNALS_PER_SESSION,
        "cooldown_minutes": COOLDOWN_MINUTES,
        "premium_range": [30.0, 300.0],
        "days_to_expiry": [0, 7],
        "normal_cost_pct": NORMAL_COST_PCT,
        "stress_cost_pct": STRESS_COST_PCT,
        "research_sessions": len(research_sessions),
        "holdout_sessions": len(holdout_sessions),
        "three_dimensions": ["time_transition", "local_strike_neighbourhood", "same_strike_ce_pe_mirror"],
        "threshold_policy": "quantiles_recomputed_using_prior_training_sessions_only_per_expanding_fold",
        "selection_policy": "state_onset_then_best_contract_per_timestamp_then_max_three_session_signals_with_10m_cooldown",
        "multiplicity_policy": "ten_preregistered_mechanisms_top_two_oof_survivors_only_open_holdout",
        "holdout_policy": "latest_25pct_chronological_outcomes_unopened_until_oof_survivor_freeze",
        "claim_boundary": "HISTORICAL_FIVE_MINUTE_CANDLE_PROXY_RESEARCH_ONLY",
        "research_only": True,
        "paper_or_live_authorized": False,
        "allowed_for_live_execution": False,
    }
    contract["semantic_sha256"] = semantic_hash(contract)
    stable_json(out / "frozen_contract.json", contract)

    ledgers: dict[str, list[pd.DataFrame]] = {name: [] for name in MECHANISMS}
    mirror_ledgers: dict[str, list[pd.DataFrame]] = {name: [] for name in MECHANISMS}
    delayed_ledgers: dict[str, list[pd.DataFrame]] = {name: [] for name in MECHANISMS}
    fold_thresholds: list[dict[str, Any]] = []

    for training_sessions, testing_sessions, fold_id in folds:
        training = causal.loc[causal["session_id"].isin(training_sessions)]
        testing = causal.loc[causal["session_id"].isin(testing_sessions)]
        cut = thresholds(training)
        fold_thresholds.append({"fold_id": fold_id, "training_sessions": len(training_sessions), "testing_sessions": len(testing_sessions), "thresholds": cut})
        masks = mechanism_masks(testing, cut)
        for mechanism in MECHANISMS:
            signals = select_signals(testing, masks[mechanism], mechanism, testing_sessions)
            trades = attach(signals, research_outcomes, fold_id)
            if not trades.empty:
                ledgers[mechanism].append(trades.assign(partition="research_oof"))
            mirror = common.mirror_control(signals, causal, research_outcomes, fold_id)
            if not mirror.empty:
                mirror_ledgers[mechanism].append(mirror.assign(partition="research_oof_mirror_control"))
            delayed = common.delayed_control(signals, causal, research_outcomes, fold_id)
            if not delayed.empty:
                delayed_ledgers[mechanism].append(delayed.assign(partition="research_oof_delayed_control"))

    stable_json(out / "fold_thresholds.json", fold_thresholds)

    oof_records: list[dict[str, Any]] = []
    survivors: list[tuple[str, common.Metrics]] = []
    all_ledgers: list[pd.DataFrame] = []
    for mechanism in MECHANISMS:
        trades = _concat(ledgers[mechanism])
        mirror = _concat(mirror_ledgers[mechanism])
        delayed = _concat(delayed_ledgers[mechanism])
        metric = common.calculate_metrics(trades)
        mirror_metric = common.calculate_metrics(mirror)
        delayed_metric = common.calculate_metrics(delayed)
        passed = oof_gate(metric) and common.control_gate(metric, mirror_metric, delayed_metric)
        oof_records.append(
            {
                "mechanism": mechanism,
                **_metric_record(metric),
                "mirror_control": _metric_record(mirror_metric),
                "delayed_control": _metric_record(delayed_metric),
                "oof_gate": passed,
            }
        )
        if not trades.empty:
            all_ledgers.append(trades)
        if passed:
            survivors.append((mechanism, metric))

    survivors = sorted(
        survivors,
        key=lambda item: (
            item[1].stress_profit_factor or -math.inf,
            item[1].remove_top_five_profit_factor or -math.inf,
            item[1].profit_factor or -math.inf,
            item[1].trades,
            item[0],
        ),
        reverse=True,
    )[:2]
    survivor_names = [name for name, _ in survivors]
    stable_json(
        out / "oof_screen.json",
        {
            "records": oof_records,
            "survivors_frozen_for_holdout": survivor_names,
            "holdout_outcomes_materialized": bool(survivor_names),
        },
    )

    holdout_records: list[dict[str, Any]] = []
    holdout_survivors: list[str] = []
    if survivor_names:
        holdout_training = causal.loc[causal["session_id"].isin(research_sessions)]
        holdout_frame = causal.loc[causal["session_id"].isin(holdout_sessions)]
        cut = thresholds(holdout_training)
        masks = mechanism_masks(holdout_frame, cut)
        holdout_outcomes = base._load_outcomes(event_path, base._raw_sessions(causal, holdout_sessions))
        for mechanism in survivor_names:
            signals = select_signals(holdout_frame, masks[mechanism], mechanism, holdout_sessions)
            trades = attach(signals, holdout_outcomes, "holdout")
            mirror = common.mirror_control(signals, causal, holdout_outcomes, "holdout")
            delayed = common.delayed_control(signals, causal, holdout_outcomes, "holdout")
            metric = common.calculate_metrics(trades)
            mirror_metric = common.calculate_metrics(mirror)
            delayed_metric = common.calculate_metrics(delayed)
            passed = holdout_gate(metric) and common.control_gate(metric, mirror_metric, delayed_metric)
            holdout_records.append(
                {
                    "mechanism": mechanism,
                    **_metric_record(metric),
                    "mirror_control": _metric_record(mirror_metric),
                    "delayed_control": _metric_record(delayed_metric),
                    "holdout_gate": passed,
                }
            )
            if not trades.empty:
                all_ledgers.append(trades.assign(partition="holdout"))
            if passed:
                holdout_survivors.append(mechanism)

    stable_json(
        out / "holdout_screen.json",
        {
            "records": holdout_records,
            "holdout_survivors": holdout_survivors,
            "holdout_outcomes_materialized": bool(survivor_names),
        },
    )
    _write_ledger(out, all_ledgers)

    verdict = (
        "STRUCTURAL_EDGE_FOUND_THREE_DIMENSIONAL_OPTION_EVENT_CANDLE_PROXY"
        if holdout_survivors
        else (
            "NO_OOF_SURVIVOR_IN_THREE_DIMENSIONAL_OPTION_EVENT_FAMILY"
            if not survivor_names
            else "OOF_SURVIVORS_FAILED_UNTOUCHED_HOLDOUT_CONTROLS"
        )
    )
    final = {
        "principal_verdict": verdict,
        "structural_edge_found": bool(holdout_survivors),
        "oof_survivors": survivor_names,
        "holdout_survivors": holdout_survivors,
        "holdout_outcomes_materialized": bool(survivor_names),
        "contract_semantic_sha256": contract["semantic_sha256"],
        "semantic_sha256": semantic_hash({"contract": contract, "oof": oof_records, "holdout": holdout_records}),
        "claim_boundary": "HISTORICAL_FIVE_MINUTE_CANDLE_PROXY_RESEARCH_ONLY",
        "execution_certification": "BLOCKED_AUTHORITATIVE_TIMESTAMP_ALIGNED_SPREAD_MISSING",
        "paper_or_live_authorized": False,
        "allowed_for_live_execution": False,
        "research_only": True,
    }
    stable_json(out / "final_decision.json", final)

    best = sorted(
        oof_records,
        key=lambda record: (
            record.get("profit_factor") or -math.inf,
            record.get("stress_profit_factor") or -math.inf,
            record.get("trades") or 0,
        ),
        reverse=True,
    )[:3]
    result_md = [
        "# Three-Dimensional Option Event Discovery V1",
        "",
        f"Principal verdict: `{verdict}`",
        "",
        "## Boundary",
        "",
        "Historical five-minute candle-proxy research only. No paper/live authorization. Execution remains blocked without timestamp-aligned bid/ask/spread evidence.",
        "",
        "## OOF survivors",
        "",
        json.dumps(survivor_names, indent=2),
        "",
        "## Holdout survivors",
        "",
        json.dumps(holdout_survivors, indent=2),
        "",
        "## Best OOF records by PF",
        "",
        "```json",
        json.dumps(best, indent=2, default=str),
        "```",
        "",
    ]
    (research / "RESULT.md").write_text("\n".join(result_md), encoding="utf-8")
    print(json.dumps(final, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
