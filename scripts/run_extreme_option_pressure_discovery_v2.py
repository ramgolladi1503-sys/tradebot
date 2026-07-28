#!/usr/bin/env python3
"""Extreme option-pressure, inventory-reversal and underreaction discovery V2.

This campaign is intentionally different from the broad transition mechanisms in
V1. It tests rare, extreme option-surface states motivated by two competing
microstructure mechanisms:

- informed-pressure continuation / delayed repricing;
- dealer-inventory absorption followed by premium reversal.

The first 75% of sessions form a research universe. Thresholds are recalculated
using only prior sessions inside four expanding out-of-fold tests. The latest
25% chronological holdout is never materialized unless a mechanism passes every
out-of-fold economic and concentration gate.

Research only. No broker, provider, order, paper, or live action is possible.
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

OUT_REL = Path("runtime/research/extreme_option_pressure_discovery_v2")
RESEARCH_REL = Path("research/extreme_option_pressure_discovery_v2")
EVENT_FILE = "event_universe_5m.parquet"
SEED = 20260729
NORMAL_COST_PCT = 0.10
STRESS_COST_PCT = 1.00

MECHANISMS = (
    "extreme_pressure_continuation",
    "extreme_negative_pressure_rebound",
    "volume_leads_price_underreaction",
    "oi_accumulation_underreaction",
    "extreme_mass_migration_continuation",
    "extreme_mass_migration_rebound",
    "mirror_spike_opposite_wing_rebound",
    "opposite_wing_capitulation_rebound",
    "synchronised_negative_surface_rebound",
    "late_day_inventory_reversal",
    "near_expiry_underreaction",
    "extreme_compression_release",
)


@dataclass(frozen=True)
class Metrics:
    trades: int
    profit_factor: float | None
    mean_return_pct: float | None
    median_return_pct: float | None
    win_rate: float | None
    net_return_pct_sum: float
    remove_top_two_profit_factor: float | None
    stress_profit_factor: float | None
    bootstrap_mean_ci_low: float | None
    bootstrap_mean_ci_high: float | None
    positive_folds: int
    total_folds: int
    largest_winner_share: float | None


def _finite(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)


def _profit_factor(values: Iterable[float]) -> float | None:
    clean = np.asarray([float(value) for value in values if math.isfinite(float(value))], dtype=float)
    if len(clean) == 0:
        return None
    gross_profit = float(clean[clean > 0].sum())
    gross_loss = float(-clean[clean < 0].sum())
    if gross_loss > 0:
        return gross_profit / gross_loss
    return math.inf if gross_profit > 0 else None


def _bootstrap_ci(values: np.ndarray) -> tuple[float | None, float | None]:
    if len(values) < 12:
        return None, None
    rng = np.random.default_rng(SEED)
    means = np.empty(3000, dtype=float)
    for index in range(len(means)):
        means[index] = rng.choice(values, size=len(values), replace=True).mean()
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def calculate_metrics(trades: pd.DataFrame) -> Metrics:
    if trades.empty:
        return Metrics(0, None, None, None, None, 0.0, None, None, None, None, 0, 0, None)
    normal = _finite(trades["net_return_pct"]).dropna().to_numpy(dtype=float)
    stress = _finite(trades["stress_return_pct"]).dropna().to_numpy(dtype=float)
    if len(normal) == 0:
        return Metrics(0, None, None, None, None, 0.0, None, None, None, None, 0, 0, None)
    ordered = np.sort(normal)[::-1]
    trimmed = ordered[2:] if len(ordered) > 2 else np.asarray([], dtype=float)
    ci_low, ci_high = _bootstrap_ci(normal)
    fold_means = trades.groupby("fold_id", observed=True)["net_return_pct"].mean() if "fold_id" in trades else pd.Series(dtype=float)
    gross_positive = float(ordered[ordered > 0].sum())
    largest_share = float(max(ordered[0], 0.0) / gross_positive) if gross_positive > 0 else None
    return Metrics(
        trades=int(len(normal)),
        profit_factor=_profit_factor(normal),
        mean_return_pct=float(normal.mean()),
        median_return_pct=float(np.median(normal)),
        win_rate=float(np.mean(normal > 0)),
        net_return_pct_sum=float(normal.sum()),
        remove_top_two_profit_factor=_profit_factor(trimmed) if len(trimmed) else None,
        stress_profit_factor=_profit_factor(stress),
        bootstrap_mean_ci_low=ci_low,
        bootstrap_mean_ci_high=ci_high,
        positive_folds=int((fold_means > 0).sum()),
        total_folds=int(len(fold_means)),
        largest_winner_share=largest_share,
    )


def _q(frame: pd.DataFrame, column: str, quantile: float, default: float = 0.0) -> float:
    values = _finite(frame[column]).dropna()
    return float(values.quantile(quantile)) if not values.empty else default


def thresholds(training: pd.DataFrame) -> dict[str, float]:
    absolute_return = _finite(training["prior_5m_return_pct"]).abs().dropna()
    return {
        "ret_p10": _q(training, "prior_5m_return_pct", 0.10),
        "ret_p20": _q(training, "prior_5m_return_pct", 0.20),
        "ret_p40": _q(training, "prior_5m_return_pct", 0.40),
        "ret_p60": _q(training, "prior_5m_return_pct", 0.60),
        "ret_p80": _q(training, "prior_5m_return_pct", 0.80),
        "ret_p90": _q(training, "prior_5m_return_pct", 0.90),
        "abs_ret_p30": float(absolute_return.quantile(0.30)) if not absolute_return.empty else 0.0,
        "volume_p80": _q(training, "prior_5m_volume_ratio", 0.80, 1.0),
        "volume_p90": _q(training, "prior_5m_volume_ratio", 0.90, 1.0),
        "accel_p10": _q(training, "return_acceleration", 0.10),
        "accel_p90": _q(training, "return_acceleration", 0.90),
        "asym_p10": _q(training, "option_asymmetry", 0.10),
        "asym_p80": _q(training, "option_asymmetry", 0.80),
        "asym_p90": _q(training, "option_asymmetry", 0.90),
        "dispersion_p20": _q(training, "surface_return_dispersion", 0.20),
        "dispersion_p80": _q(training, "surface_return_dispersion", 0.80),
        "mass_p10": _q(training, "directional_mass_shift", 0.10),
        "mass_p90": _q(training, "directional_mass_shift", 0.90),
        "oi_p80": _q(training, "oi_change_ratio", 0.80),
        "oi_p90": _q(training, "oi_change_ratio", 0.90),
        "range_p20": _q(training, "prior_10m_range_pct", 0.20),
        "breadth_delta_p80": _q(training, "breadth_delta", 0.80),
    }


def mechanism_masks(frame: pd.DataFrame, cut: dict[str, float]) -> dict[str, pd.Series]:
    ret = frame["prior_5m_return_pct"]
    volume = frame["prior_5m_volume_ratio"]
    breadth = frame["breadth_positive"]
    dispersion = frame["surface_return_dispersion"]
    asymmetry = frame["option_asymmetry"]
    mirror = frame["mirror_return"]
    mass = frame["directional_mass_shift"]
    oi = frame["oi_change_ratio"]
    surface_median = frame["surface_median_return"]
    return {
        "extreme_pressure_continuation": (
            (ret >= cut["ret_p90"])
            & (volume >= cut["volume_p90"])
            & (breadth >= 0.75)
            & (asymmetry >= cut["asym_p80"])
        ),
        "extreme_negative_pressure_rebound": (
            (ret <= cut["ret_p10"])
            & (volume >= cut["volume_p80"])
            & (frame["return_acceleration"] <= cut["accel_p10"])
            & (surface_median < 0)
        ),
        "volume_leads_price_underreaction": (
            (volume >= cut["volume_p90"])
            & (ret.abs() <= cut["abs_ret_p30"])
            & (breadth >= 0.50)
            & (oi >= cut["oi_p80"])
        ),
        "oi_accumulation_underreaction": (
            (oi >= cut["oi_p90"])
            & (volume >= cut["volume_p80"])
            & ret.between(cut["ret_p40"], cut["ret_p60"], inclusive="both")
        ),
        "extreme_mass_migration_continuation": (
            (mass >= cut["mass_p90"])
            & (breadth >= 0.75)
            & (volume >= cut["volume_p80"])
            & (ret > 0)
        ),
        "extreme_mass_migration_rebound": (
            (mass <= cut["mass_p10"])
            & (ret <= cut["ret_p20"])
            & (volume >= cut["volume_p80"])
        ),
        "mirror_spike_opposite_wing_rebound": (
            (mirror >= cut["ret_p90"])
            & (ret <= cut["ret_p20"])
            & (asymmetry <= cut["asym_p10"])
            & (volume >= cut["volume_p80"])
        ),
        "opposite_wing_capitulation_rebound": (
            (ret <= cut["ret_p10"])
            & (mirror >= cut["ret_p80"])
            & (volume >= cut["volume_p90"])
            & (asymmetry <= cut["asym_p10"])
        ),
        "synchronised_negative_surface_rebound": (
            (surface_median <= cut["ret_p10"])
            & (breadth <= 0.25)
            & (dispersion <= cut["dispersion_p20"])
            & (frame["breadth_volume"] >= 0.50)
        ),
        "late_day_inventory_reversal": (
            (frame["minute_of_day"] >= 780)
            & (ret <= cut["ret_p10"])
            & (volume >= cut["volume_p90"])
            & (frame["return_acceleration"] <= cut["accel_p10"])
        ),
        "near_expiry_underreaction": (
            (frame["days_to_expiry"].between(0, 1, inclusive="both"))
            & (volume >= cut["volume_p90"])
            & (ret.abs() <= cut["abs_ret_p30"])
            & (oi >= cut["oi_p80"])
        ),
        "extreme_compression_release": (
            (frame["prior_10m_range_pct"] <= cut["range_p20"])
            & (volume >= cut["volume_p90"])
            & (frame["return_acceleration"] >= cut["accel_p90"])
            & (frame["breadth_delta"] >= cut["breadth_delta_p80"])
        ),
    }


def prepare_causal(event_path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(event_path, columns=base.CAUSAL_COLUMNS)
    frame = base._surface_features(frame)
    # Avoid overnight previous-bar transitions: every eligible observation must have
    # at least six completed five-minute bars in the same market session.
    frame = frame.loc[frame["minute_of_day"] >= 585].copy()
    return frame


def research_holdout_sessions(frame: pd.DataFrame) -> tuple[list[str], list[str]]:
    sessions = sorted(frame["session_id"].dropna().unique().tolist())
    cut = int(math.floor(len(sessions) * 0.75))
    return sessions[:cut], sessions[cut:]


def expanding_folds(research_sessions: list[str]) -> list[tuple[list[str], list[str], str]]:
    initial = int(math.floor(len(research_sessions) * 0.40))
    remaining = np.asarray(research_sessions[initial:], dtype=object)
    test_blocks = [list(block) for block in np.array_split(remaining, 4) if len(block)]
    folds: list[tuple[list[str], list[str], str]] = []
    train_end = initial
    for index, test_sessions in enumerate(test_blocks, start=1):
        train_sessions = research_sessions[:train_end]
        folds.append((train_sessions, test_sessions, f"fold_{index}"))
        train_end += len(test_sessions)
    return folds


def _eligible(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["entry_price_next_open"].between(30.0, 500.0, inclusive="both")
        & frame["minute_of_day"].between(585, 890, inclusive="both")
        & frame["days_to_expiry"].between(0, 7, inclusive="both")
        & (frame["surface_count"] >= 3)
        & (frame["volume"] > 0)
        & frame["previous_return"].notna()
    )


def select_signal(frame: pd.DataFrame, mask: pd.Series, mechanism: str, sessions: list[str]) -> pd.DataFrame:
    candidates = frame.loc[mask & _eligible(frame) & frame["session_id"].isin(sessions)].copy()
    if candidates.empty:
        return candidates
    candidates["mechanism"] = mechanism
    candidates["premium_distance"] = (candidates["entry_price_next_open"] - 150.0).abs()
    candidates["extremity_score"] = (
        candidates["prior_5m_return_pct"].abs().fillna(0)
        + candidates["return_acceleration"].abs().fillna(0)
        + candidates["option_asymmetry"].abs().fillna(0)
        + candidates["prior_5m_volume_ratio"].fillna(0)
        + 0.02 * candidates["directional_mass_shift"].abs().fillna(0)
    )
    earliest = candidates.groupby("session_id", observed=True)["timestamp"].transform("min")
    candidates = candidates.loc[candidates["timestamp"].eq(earliest)]
    candidates = candidates.sort_values(
        ["session_id", "extremity_score", "premium_distance", "expired_instrument_key"],
        ascending=[True, False, True, True],
        kind="mergesort",
    )
    return candidates.drop_duplicates("session_id", keep="first")


def attach(signals: pd.DataFrame, outcomes: pd.DataFrame, fold_id: str) -> pd.DataFrame:
    trades = base._attach_outcomes(signals, outcomes)
    if trades.empty:
        return trades
    trades["fold_id"] = fold_id
    return trades


def oof_gate(metric: Metrics) -> bool:
    return bool(
        metric.trades >= 30
        and metric.profit_factor is not None
        and metric.profit_factor >= 1.25
        and metric.mean_return_pct is not None
        and metric.mean_return_pct > 0
        and metric.median_return_pct is not None
        and metric.median_return_pct >= 0
        and metric.remove_top_two_profit_factor is not None
        and metric.remove_top_two_profit_factor >= 1.05
        and metric.stress_profit_factor is not None
        and metric.stress_profit_factor >= 1.05
        and metric.bootstrap_mean_ci_low is not None
        and metric.bootstrap_mean_ci_low > 0
        and metric.total_folds == 4
        and metric.positive_folds >= 3
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.35)
    )


def holdout_gate(metric: Metrics) -> bool:
    return bool(
        metric.trades >= 10
        and metric.profit_factor is not None
        and metric.profit_factor >= 1.15
        and metric.mean_return_pct is not None
        and metric.mean_return_pct > 0
        and metric.median_return_pct is not None
        and metric.median_return_pct >= 0
        and metric.remove_top_two_profit_factor is not None
        and metric.remove_top_two_profit_factor >= 1.00
        and metric.stress_profit_factor is not None
        and metric.stress_profit_factor >= 1.00
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.40)
    )


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
    research = root / RESEARCH_REL
    out.mkdir(parents=True, exist_ok=True)
    research.mkdir(parents=True, exist_ok=True)

    causal = prepare_causal(event_path)
    research_sessions, holdout_sessions = research_holdout_sessions(causal)
    folds = expanding_folds(research_sessions)
    research_outcomes = base._load_outcomes(event_path, base._raw_sessions(causal, research_sessions))

    contract = {
        "schema_version": "extreme_option_pressure_discovery_v2",
        "mechanisms": list(MECHANISMS),
        "mechanism_count": len(MECHANISMS),
        "research_sessions": len(research_sessions),
        "holdout_sessions": len(holdout_sessions),
        "folds": [
            {
                "fold_id": fold_id,
                "training_sessions": len(training),
                "test_sessions": len(testing),
                "training_last": training[-1] if training else None,
                "test_first": testing[0] if testing else None,
                "test_last": testing[-1] if testing else None,
            }
            for training, testing, fold_id in folds
        ],
        "threshold_policy": "fixed_quantiles_recomputed_on_prior_fold_sessions_only",
        "normal_cost_pct": NORMAL_COST_PCT,
        "stress_cost_pct": STRESS_COST_PCT,
        "holdout_policy": "latest_25pct_outcomes_not_materialized_until_oof_survivor_freeze",
        "research_only": True,
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
        fold_thresholds.append({"fold_id": fold_id, "thresholds": cut})
        masks = mechanism_masks(testing, cut)
        for mechanism in MECHANISMS:
            signals = select_signal(testing, masks[mechanism], mechanism, testing_sessions)
            trades = attach(signals, research_outcomes, fold_id)
            if not trades.empty:
                ledgers[mechanism].append(trades)

    stable_json(out / "fold_thresholds.json", fold_thresholds)
    oof_records: list[dict[str, Any]] = []
    survivors: list[tuple[str, Metrics]] = []
    oof_ledgers: list[pd.DataFrame] = []
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
            item[1].remove_top_two_profit_factor or -math.inf,
            item[1].profit_factor or -math.inf,
            item[1].trades,
            item[0],
        ),
        reverse=True,
    )[:3]
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
    holdout_ledgers: list[pd.DataFrame] = []
    validated: list[str] = []
    if survivor_names:
        final_cut = thresholds(causal.loc[causal["session_id"].isin(research_sessions)])
        holdout_frame = causal.loc[causal["session_id"].isin(holdout_sessions)]
        final_masks = mechanism_masks(holdout_frame, final_cut)
        holdout_outcomes = base._load_outcomes(event_path, base._raw_sessions(causal, holdout_sessions))
        for mechanism in survivor_names:
            signals = select_signal(holdout_frame, final_masks[mechanism], mechanism, holdout_sessions)
            trades = attach(signals, holdout_outcomes, "holdout")
            metric = calculate_metrics(trades)
            passed = holdout_gate(metric)
            holdout_records.append({"mechanism": mechanism, **asdict(metric), "holdout_gate": passed})
            if not trades.empty:
                holdout_ledgers.append(trades.assign(partition="holdout"))
            if passed:
                validated.append(mechanism)

    stable_json(
        out / "holdout_screen.json",
        {
            "records": holdout_records,
            "validated_candidates": validated,
            "holdout_outcomes_materialized": bool(survivor_names),
        },
    )

    all_ledgers = oof_ledgers + holdout_ledgers
    if all_ledgers:
        ledger = pd.concat(all_ledgers, ignore_index=True, sort=False)
        keep = [
            "partition",
            "fold_id",
            "mechanism",
            "session_id",
            "timestamp",
            "expired_instrument_key",
            "expiry_id",
            "option_type",
            "strike",
            "entry_price_next_open",
            "gross_return_pct",
            "net_return_pct",
            "stress_return_pct",
            "forward_mfe_points",
            "forward_mae_points",
            "forward_expansion_pct",
            "label_horizon_minutes",
            "prior_5m_return_pct",
            "previous_return",
            "return_acceleration",
            "prior_5m_volume_ratio",
            "oi_change_ratio",
            "breadth_positive",
            "breadth_delta",
            "surface_return_dispersion",
            "option_asymmetry",
            "mirror_return",
            "directional_mass_shift",
            "days_to_expiry",
            "minute_of_day",
        ]
        ledger[[column for column in keep if column in ledger.columns]].to_csv(out / "trade_ledger.csv", index=False)

    verdict = (
        "STRUCTURAL_EDGE_FOUND_CANDLE_PROXY_HOLDOUT_SURVIVOR"
        if validated
        else (
            "NO_OOF_SURVIVOR_IN_EXTREME_PRESSURE_FAMILIES"
            if not survivor_names
            else "OOF_SURVIVORS_FAILED_UNTOUCHED_HOLDOUT"
        )
    )
    final = {
        "principal_verdict": verdict,
        "oof_survivors": survivor_names,
        "holdout_survivors": validated,
        "holdout_outcomes_materialized": bool(survivor_names),
        "execution_certification": "BLOCKED_AUTHORITATIVE_TIMESTAMP_ALIGNED_SPREAD_MISSING",
        "contract_semantic_sha256": contract["semantic_sha256"],
        "research_only": True,
        "allowed_for_live_execution": False,
    }
    stable_json(out / "final_decision.json", final)
    (research / "RESULT.md").write_text(
        "# Extreme Option Pressure Discovery V2\n\n"
        f"Principal verdict: `{verdict}`\n\n"
        f"OOF survivors: `{survivor_names}`\n\n"
        f"Holdout survivors: `{validated}`\n\n"
        f"Holdout outcomes materialized: `{bool(survivor_names)}`\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
