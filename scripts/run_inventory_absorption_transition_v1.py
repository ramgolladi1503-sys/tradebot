#!/usr/bin/env python3
"""Chronological discovery of frequent option inventory-absorption transitions.

This campaign tests a mechanism family that is deliberately different from the
late-day CE capitulation candidate. It searches both NIFTY option wings for a
failed extension: premium sold aggressively with volume and/or OI participation,
then the decline decelerates while surface breadth and the same-strike mirror stop
confirming. The economic hypothesis is short-horizon inventory absorption and
premium rebound.

All thresholds are recomputed from prior training sessions inside expanding
walk-forward folds. Candidate outcomes are attached only after signal selection.
The latest 25% chronological holdout is opened only for OOF survivors. Research
only; no broker, provider, paper, or live action is possible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from scripts import run_option_surface_transition_discovery_v1 as base
from scripts.run_conditional_precursor_discrimination_v2 import PRIOR_REL, stable_json

OUT_REL = Path("runtime/research/inventory_absorption_transition_v1")
RESEARCH_REL = Path("research/inventory_absorption_transition_v1")
EVENT_FILE = "event_universe_5m.parquet"
SEED = 20260729
NORMAL_COST_PCT = 0.10
STRESS_COST_PCT = 1.00
MAX_SIGNALS_PER_SESSION = 2
COOLDOWN_MINUTES = 15
TARGET_PREMIUM = 150.0

MECHANISMS = (
    "decelerating_capitulation",
    "mirror_stall_absorption",
    "surface_breadth_recovery",
    "oi_absorption_turn",
    "volume_climax_failed_extension",
    "compression_failed_breakdown",
    "near_expiry_absorption",
    "morning_absorption",
    "midday_absorption",
    "late_day_absorption",
)


@dataclass(frozen=True)
class Metrics:
    trades: int
    sessions: int
    profit_factor: float | None
    mean_return_pct: float | None
    median_return_pct: float | None
    win_rate: float | None
    net_return_pct_sum: float
    remove_top_five_profit_factor: float | None
    remove_top_three_profit_factor: float | None
    stress_profit_factor: float | None
    bootstrap_mean_ci_low: float | None
    bootstrap_mean_ci_high: float | None
    positive_folds: int
    total_folds: int
    positive_halves: int
    total_halves: int
    largest_winner_share: float | None
    largest_session_share: float | None


def _finite(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)


def _profit_factor(values: Iterable[float]) -> float | None:
    clean = np.asarray([float(value) for value in values if math.isfinite(float(value))], dtype=float)
    if not len(clean):
        return None
    gross_profit = float(clean[clean > 0].sum())
    gross_loss = float(-clean[clean < 0].sum())
    if gross_loss > 0:
        return gross_profit / gross_loss
    return math.inf if gross_profit > 0 else None


def _bootstrap_ci(values: np.ndarray) -> tuple[float | None, float | None]:
    if len(values) < 20:
        return None, None
    rng = np.random.default_rng(SEED)
    means = np.empty(4000, dtype=float)
    for index in range(len(means)):
        means[index] = rng.choice(values, size=len(values), replace=True).mean()
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def _positive_halves(trades: pd.DataFrame) -> tuple[int, int]:
    if len(trades) < 8:
        return 0, 0
    ordered = trades.sort_values(["session_id", "timestamp"], kind="mergesort")
    index_parts = [part for part in np.array_split(np.arange(len(ordered)), 2) if len(part) >= 4]
    halves = [ordered.iloc[index_part] for index_part in index_parts]
    return int(sum(float(part["net_return_pct"].mean()) > 0 for part in halves)), int(len(halves))


def calculate_metrics(trades: pd.DataFrame) -> Metrics:
    if trades.empty:
        return Metrics(0, 0, None, None, None, None, 0.0, None, None, None, None, None, 0, 0, 0, 0, None, None)
    normal = _finite(trades["net_return_pct"]).dropna().to_numpy(dtype=float)
    stress = _finite(trades["stress_return_pct"]).dropna().to_numpy(dtype=float)
    if not len(normal):
        return Metrics(0, 0, None, None, None, None, 0.0, None, None, None, None, None, 0, 0, 0, 0, None, None)
    ordered = np.sort(normal)[::-1]
    trim_five = ordered[5:] if len(ordered) > 5 else np.asarray([], dtype=float)
    trim_three = ordered[3:] if len(ordered) > 3 else np.asarray([], dtype=float)
    ci_low, ci_high = _bootstrap_ci(normal)
    fold_means = trades.groupby("fold_id", observed=True)["net_return_pct"].mean() if "fold_id" in trades else pd.Series(dtype=float)
    positive_halves, total_halves = _positive_halves(trades)
    gross_positive = float(ordered[ordered > 0].sum())
    largest_winner_share = float(max(ordered[0], 0.0) / gross_positive) if gross_positive > 0 else None
    session_net = trades.groupby("session_id", observed=True)["net_return_pct"].sum()
    positive_session_net = session_net[session_net > 0]
    positive_session_total = float(positive_session_net.sum())
    largest_session_share = (
        float(positive_session_net.max() / positive_session_total)
        if positive_session_total > 0 and not positive_session_net.empty
        else None
    )
    return Metrics(
        trades=int(len(normal)),
        sessions=int(trades["session_id"].nunique()),
        profit_factor=_profit_factor(normal),
        mean_return_pct=float(normal.mean()),
        median_return_pct=float(np.median(normal)),
        win_rate=float(np.mean(normal > 0)),
        net_return_pct_sum=float(normal.sum()),
        remove_top_five_profit_factor=_profit_factor(trim_five) if len(trim_five) else None,
        remove_top_three_profit_factor=_profit_factor(trim_three) if len(trim_three) else None,
        stress_profit_factor=_profit_factor(stress),
        bootstrap_mean_ci_low=ci_low,
        bootstrap_mean_ci_high=ci_high,
        positive_folds=int((fold_means > 0).sum()),
        total_folds=int(len(fold_means)),
        positive_halves=positive_halves,
        total_halves=total_halves,
        largest_winner_share=largest_winner_share,
        largest_session_share=largest_session_share,
    )


def _q(frame: pd.DataFrame, column: str, quantile: float, default: float = 0.0) -> float:
    values = _finite(frame[column]).dropna()
    return float(values.quantile(quantile)) if not values.empty else float(default)


def thresholds(training: pd.DataFrame) -> dict[str, float]:
    return {
        "ret_p05": _q(training, "prior_5m_return_pct", 0.05),
        "ret_p10": _q(training, "prior_5m_return_pct", 0.10),
        "ret_p20": _q(training, "prior_5m_return_pct", 0.20),
        "ret_p35": _q(training, "prior_5m_return_pct", 0.35),
        "accel_p65": _q(training, "return_acceleration", 0.65),
        "accel_p75": _q(training, "return_acceleration", 0.75),
        "accel_p85": _q(training, "return_acceleration", 0.85),
        "volume_p65": _q(training, "prior_5m_volume_ratio", 0.65, 1.0),
        "volume_p75": _q(training, "prior_5m_volume_ratio", 0.75, 1.0),
        "volume_p85": _q(training, "prior_5m_volume_ratio", 0.85, 1.0),
        "volume_accel_p65": _q(training, "volume_acceleration", 0.65),
        "oi_p65": _q(training, "oi_change_ratio", 0.65),
        "oi_p75": _q(training, "oi_change_ratio", 0.75),
        "breadth_delta_p60": _q(training, "breadth_delta", 0.60),
        "breadth_delta_p70": _q(training, "breadth_delta", 0.70),
        "surface_accel_p60": _q(training, "surface_median_acceleration", 0.60),
        "surface_accel_p70": _q(training, "surface_median_acceleration", 0.70),
        "mirror_accel_p40": _q(training, "mirror_acceleration", 0.40),
        "range_p35": _q(training, "prior_10m_range_pct", 0.35),
        "dispersion_p65": _q(training, "surface_return_dispersion", 0.65),
    }


def mechanism_masks(frame: pd.DataFrame, cut: dict[str, float]) -> dict[str, pd.Series]:
    ret = frame["prior_5m_return_pct"]
    prev = frame["previous_return"]
    accel = frame["return_acceleration"]
    volume = frame["prior_5m_volume_ratio"]
    volume_accel = frame["volume_acceleration"]
    oi = frame["oi_change_ratio"]
    breadth_delta = frame["breadth_delta"]
    surface_accel = frame["surface_median_acceleration"]
    mirror = frame["mirror_return"]
    mirror_accel = frame["mirror_acceleration"]

    deceleration = (
        (prev <= cut["ret_p10"])
        & (ret < 0)
        & (ret >= cut["ret_p35"])
        & (accel >= cut["accel_p75"])
    )
    strong_deceleration = (
        (prev <= cut["ret_p05"])
        & (ret < 0)
        & (accel >= cut["accel_p85"])
    )
    breadth_recovery = (
        (frame["surface_median_return"] < 0)
        & (surface_accel >= cut["surface_accel_p60"])
        & (breadth_delta >= cut["breadth_delta_p60"])
    )
    mirror_stall = (
        (mirror > 0)
        & (mirror_accel <= cut["mirror_accel_p40"])
        & (frame["option_asymmetry"] < 0)
    )

    masks = {
        "decelerating_capitulation": (
            deceleration
            & (volume >= cut["volume_p65"])
            & (surface_accel >= cut["surface_accel_p60"])
        ),
        "mirror_stall_absorption": (
            deceleration
            & mirror_stall
            & (volume >= cut["volume_p65"])
        ),
        "surface_breadth_recovery": (
            (prev <= cut["ret_p20"])
            & (ret < 0)
            & (accel >= cut["accel_p65"])
            & breadth_recovery
            & (volume >= cut["volume_p65"])
        ),
        "oi_absorption_turn": (
            deceleration
            & (oi >= cut["oi_p65"])
            & (volume >= cut["volume_p65"])
            & (breadth_delta >= 0)
        ),
        "volume_climax_failed_extension": (
            strong_deceleration
            & (volume >= cut["volume_p85"])
            & (volume_accel >= cut["volume_accel_p65"])
            & (surface_accel >= cut["surface_accel_p60"])
        ),
        "compression_failed_breakdown": (
            (frame["prior_10m_range_pct"] <= cut["range_p35"])
            & (prev <= cut["ret_p20"])
            & (ret < 0)
            & (accel >= cut["accel_p75"])
            & (breadth_delta >= cut["breadth_delta_p70"])
        ),
        "near_expiry_absorption": (
            deceleration
            & frame["days_to_expiry"].between(0, 2, inclusive="both")
            & (volume >= cut["volume_p75"])
            & (surface_accel >= cut["surface_accel_p60"])
        ),
        "morning_absorption": (
            deceleration
            & frame["minute_of_day"].between(585, 690, inclusive="both")
            & (volume >= cut["volume_p65"])
            & (breadth_delta >= 0)
        ),
        "midday_absorption": (
            deceleration
            & frame["minute_of_day"].between(691, 779, inclusive="both")
            & (volume >= cut["volume_p65"])
            & (breadth_delta >= 0)
        ),
        "late_day_absorption": (
            deceleration
            & frame["minute_of_day"].between(780, 880, inclusive="both")
            & (volume >= cut["volume_p65"])
            & (surface_accel >= cut["surface_accel_p60"])
        ),
    }
    return {name: mask.fillna(False) for name, mask in masks.items()}


def prepare_causal(event_path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(event_path, columns=base.CAUSAL_COLUMNS)
    frame = base._surface_features(frame)
    frame = frame.loc[frame["minute_of_day"].between(585, 880, inclusive="both")].copy()
    return frame


def research_holdout_sessions(frame: pd.DataFrame) -> tuple[list[str], list[str]]:
    sessions = sorted(frame["session_id"].dropna().unique().tolist())
    cut = int(math.floor(len(sessions) * 0.75))
    return sessions[:cut], sessions[cut:]


def expanding_folds(research_sessions: list[str]) -> list[tuple[list[str], list[str], str]]:
    initial = int(math.floor(len(research_sessions) * 0.40))
    remaining = np.asarray(research_sessions[initial:], dtype=object)
    blocks = [list(block) for block in np.array_split(remaining, 4) if len(block)]
    folds: list[tuple[list[str], list[str], str]] = []
    train_end = initial
    for index, testing in enumerate(blocks, start=1):
        training = research_sessions[:train_end]
        folds.append((training, testing, f"fold_{index}"))
        train_end += len(testing)
    return folds


def _eligible(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["entry_price_next_open"].between(30.0, 300.0, inclusive="both")
        & frame["days_to_expiry"].between(0, 7, inclusive="both")
        & (frame["surface_count"] >= 3)
        & (frame["volume"] > 0)
        & frame["previous_return"].notna()
        & frame["mirror_return"].notna()
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
        1.5 * candidates["return_acceleration"].fillna(0)
        + 0.75 * candidates["surface_median_acceleration"].fillna(0)
        + 8.0 * candidates["breadth_delta"].fillna(0)
        + 0.5 * candidates["prior_5m_volume_ratio"].fillna(0)
        + 0.5 * candidates["oi_change_ratio"].fillna(0)
        - 0.25 * candidates["mirror_acceleration"].fillna(0)
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


def mirror_control(signals: pd.DataFrame, causal: pd.DataFrame, outcomes: pd.DataFrame, fold_id: str) -> pd.DataFrame:
    if signals.empty:
        return signals.copy()
    lookup = causal[
        [
            "session_id", "timestamp", "expiry_id", "strike", "option_type",
            "expired_instrument_key", "entry_price_next_open",
        ]
    ].drop_duplicates(["session_id", "timestamp", "expiry_id", "strike", "option_type"])
    source = signals[["session_id", "timestamp", "expiry_id", "strike", "option_type", "mechanism"]].copy()
    source["option_type"] = source["option_type"].map({"CE": "PE", "PE": "CE"})
    mirrored = source.merge(
        lookup,
        on=["session_id", "timestamp", "expiry_id", "strike", "option_type"],
        how="inner",
        validate="many_to_one",
    )
    if mirrored.empty:
        return mirrored
    return attach(mirrored, outcomes, fold_id)


def delayed_control(signals: pd.DataFrame, causal: pd.DataFrame, outcomes: pd.DataFrame, fold_id: str) -> pd.DataFrame:
    if signals.empty:
        return signals.copy()
    source = signals[["expired_instrument_key", "timestamp", "mechanism"]].copy()
    source["timestamp"] = source["timestamp"] + pd.Timedelta(minutes=5)
    lookup = causal.drop_duplicates(["expired_instrument_key", "timestamp"])
    delayed = source.merge(
        lookup,
        on=["expired_instrument_key", "timestamp"],
        how="inner",
        suffixes=("", "_causal"),
        validate="many_to_one",
    )
    if delayed.empty:
        return delayed
    return attach(delayed, outcomes, fold_id)


def oof_gate(metric: Metrics) -> bool:
    return bool(
        metric.trades >= 60
        and metric.sessions >= 45
        and metric.profit_factor is not None and metric.profit_factor >= 1.25
        and metric.mean_return_pct is not None and metric.mean_return_pct > 0
        and metric.median_return_pct is not None and metric.median_return_pct >= 0
        and metric.remove_top_five_profit_factor is not None and metric.remove_top_five_profit_factor >= 1.05
        and metric.stress_profit_factor is not None and metric.stress_profit_factor >= 1.00
        and metric.bootstrap_mean_ci_low is not None and metric.bootstrap_mean_ci_low > 0
        and metric.total_folds == 4 and metric.positive_folds >= 3
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.20)
        and (metric.largest_session_share is None or metric.largest_session_share <= 0.20)
    )


def holdout_gate(metric: Metrics) -> bool:
    return bool(
        metric.trades >= 18
        and metric.sessions >= 14
        and metric.profit_factor is not None and metric.profit_factor >= 1.15
        and metric.mean_return_pct is not None and metric.mean_return_pct > 0
        and metric.median_return_pct is not None and metric.median_return_pct >= 0
        and metric.remove_top_three_profit_factor is not None and metric.remove_top_three_profit_factor >= 1.00
        and metric.stress_profit_factor is not None and metric.stress_profit_factor >= 1.00
        and metric.total_halves == 2 and metric.positive_halves == 2
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.25)
        and (metric.largest_session_share is None or metric.largest_session_share <= 0.25)
    )


def control_gate(primary: Metrics, mirror: Metrics, delayed: Metrics) -> bool:
    mirror_bad = bool(
        mirror.trades >= max(8, int(primary.trades * 0.50))
        and mirror.mean_return_pct is not None
        and mirror.mean_return_pct <= 0
        and (mirror.profit_factor is None or mirror.profit_factor <= 1.05)
    )
    delayed_not_better = bool(
        delayed.trades < 8
        or primary.mean_return_pct is None
        or delayed.mean_return_pct is None
        or primary.mean_return_pct >= delayed.mean_return_pct
    )
    return mirror_bad and delayed_not_better


def semantic_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


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
    research_sessions, holdout_sessions = research_holdout_sessions(causal)
    folds = expanding_folds(research_sessions)
    research_outcomes = base._load_outcomes(event_path, base._raw_sessions(causal, research_sessions))

    contract = {
        "schema_version": "inventory_absorption_transition_v1",
        "mechanism_hypothesis": "failed_option_premium_extension_after_volume_or_oi_shock_then_inventory_absorption_rebound",
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
        "threshold_policy": "quantiles_recomputed_using_prior_training_sessions_only_per_expanding_fold",
        "selection_policy": "state_onset_then_best_contract_per_timestamp_then_max_two_session_signals_with_15m_cooldown",
        "multiplicity_policy": "ten_preregistered_mechanisms_top_two_oof_survivors_only_open_holdout",
        "holdout_policy": "latest_25pct_chronological_outcomes_unopened_until_oof_survivor_freeze",
        "research_only": True,
        "paper_or_live_authorized": False,
        "allowed_for_live_execution": False,
    }
    contract["semantic_sha256"] = semantic_hash(contract)
    stable_json(out / "frozen_contract.json", contract)

    ledgers: dict[str, list[pd.DataFrame]] = {name: [] for name in MECHANISMS}
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
                ledgers[mechanism].append(trades)
    stable_json(out / "fold_thresholds.json", fold_thresholds)

    oof_records: list[dict[str, Any]] = []
    oof_ledgers: list[pd.DataFrame] = []
    survivors: list[tuple[str, Metrics]] = []
    for mechanism in MECHANISMS:
        trades = pd.concat(ledgers[mechanism], ignore_index=True, sort=False) if ledgers[mechanism] else pd.DataFrame()
        metric = calculate_metrics(trades)
        passed = oof_gate(metric)
        oof_records.append({"mechanism": mechanism, **asdict(metric), "oof_gate": passed})
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
            item[0],
        ),
        reverse=True,
    )[:2]
    survivor_names = [name for name, _ in survivors]
    stable_json(out / "oof_screen.json", {"records": oof_records, "survivors_frozen_for_holdout": survivor_names, "holdout_outcomes_materialized": bool(survivor_names)})

    holdout_records: list[dict[str, Any]] = []
    holdout_ledgers: list[pd.DataFrame] = []
    validated: list[str] = []
    if survivor_names:
        final_cut = thresholds(causal.loc[causal["session_id"].isin(research_sessions)])
        holdout_frame = causal.loc[causal["session_id"].isin(holdout_sessions)]
        holdout_outcomes = base._load_outcomes(event_path, base._raw_sessions(causal, holdout_sessions))
        final_masks = mechanism_masks(holdout_frame, final_cut)
        for mechanism in survivor_names:
            signals = select_signals(holdout_frame, final_masks[mechanism], mechanism, holdout_sessions)
            primary_trades = attach(signals, holdout_outcomes, "holdout")
            mirror_trades = mirror_control(signals, holdout_frame, holdout_outcomes, "holdout_mirror")
            delayed_trades = delayed_control(signals, holdout_frame, holdout_outcomes, "holdout_delayed")
            primary_metric = calculate_metrics(primary_trades)
            mirror_metric = calculate_metrics(mirror_trades)
            delayed_metric = calculate_metrics(delayed_trades)
            economic_pass = holdout_gate(primary_metric)
            controls_pass = control_gate(primary_metric, mirror_metric, delayed_metric)
            passed = economic_pass and controls_pass
            holdout_records.append(
                {
                    "mechanism": mechanism,
                    "primary": asdict(primary_metric),
                    "mirror_control": asdict(mirror_metric),
                    "delayed_control": asdict(delayed_metric),
                    "holdout_economic_gate": economic_pass,
                    "control_gate": controls_pass,
                    "holdout_gate": passed,
                }
            )
            if not primary_trades.empty:
                holdout_ledgers.append(primary_trades.assign(partition="holdout_primary"))
            if not mirror_trades.empty:
                holdout_ledgers.append(mirror_trades.assign(partition="holdout_mirror"))
            if not delayed_trades.empty:
                holdout_ledgers.append(delayed_trades.assign(partition="holdout_delayed"))
            if passed:
                validated.append(mechanism)
    stable_json(out / "holdout_screen.json", {"records": holdout_records, "validated_candidates": validated, "holdout_outcomes_materialized": bool(survivor_names)})

    all_ledgers = oof_ledgers + holdout_ledgers
    if all_ledgers:
        ledger = pd.concat(all_ledgers, ignore_index=True, sort=False)
        keep = [
            "partition", "fold_id", "mechanism", "session_id", "timestamp",
            "expired_instrument_key", "expiry_id", "option_type", "strike",
            "entry_price_next_open", "gross_return_pct", "net_return_pct", "stress_return_pct",
            "forward_mfe_points", "forward_mae_points", "forward_expansion_pct", "label_horizon_minutes",
            "prior_5m_return_pct", "previous_return", "return_acceleration",
            "prior_5m_volume_ratio", "volume_acceleration", "oi_change_ratio",
            "breadth_positive", "breadth_delta", "surface_median_return",
            "surface_median_acceleration", "option_asymmetry", "mirror_return",
            "mirror_acceleration", "days_to_expiry", "minute_of_day",
        ]
        ledger[[column for column in keep if column in ledger.columns]].to_csv(out / "trade_ledger.csv", index=False)

    verdict = (
        "STRUCTURAL_EDGE_FOUND_INVENTORY_ABSORPTION_TRANSITION_CANDLE_PROXY"
        if validated
        else ("NO_OOF_SURVIVOR_IN_INVENTORY_ABSORPTION_FAMILY" if not survivor_names else "OOF_SURVIVORS_FAILED_HOLDOUT_OR_CONTROLS")
    )
    final = {
        "principal_verdict": verdict,
        "structural_edge_found": bool(validated),
        "oof_survivors": survivor_names,
        "holdout_survivors": validated,
        "holdout_outcomes_materialized": bool(survivor_names),
        "contract_semantic_sha256": contract["semantic_sha256"],
        "execution_certification": "BLOCKED_AUTHORITATIVE_TIMESTAMP_ALIGNED_SPREAD_MISSING",
        "claim_boundary": "HISTORICAL_FIVE_MINUTE_CANDLE_PROXY_RESEARCH_ONLY",
        "research_only": True,
        "paper_or_live_authorized": False,
        "allowed_for_live_execution": False,
    }
    final["semantic_sha256"] = semantic_hash(final)
    stable_json(out / "final_decision.json", final)

    (research / "RESULT.md").write_text(
        "# Inventory Absorption Transition V1\n\n"
        f"Principal verdict: `{verdict}`\n\n"
        f"OOF survivors: `{survivor_names}`\n\n"
        f"Holdout survivors: `{validated}`\n\n"
        f"Research sessions: `{len(research_sessions)}`; holdout sessions: `{len(holdout_sessions)}`.\n\n"
        "Mechanism: a losing option wing fails to extend after a volume/OI shock, "
        "while premium acceleration, surface breadth, and the same-strike mirror indicate absorption.\n\n"
        "Maximum two non-overlapping signals per session with a 15-minute cooldown.\n\n"
        "Historical five-minute OHLCV candle proxy only. No paper or live authorization.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
