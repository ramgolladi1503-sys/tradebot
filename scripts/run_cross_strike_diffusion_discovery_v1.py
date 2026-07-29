#!/usr/bin/env python3
"""Cross-strike price-discovery diffusion research for NIFTY options.

The hypothesis is deliberately different from the late-day CE capitulation rebound:
adjacent strikes can reprice coherently before a liquid lagging contract catches up.
The runner tests eight frozen diffusion mechanisms using prior-only expanding WFA,
then opens the latest chronological holdout only for OOF survivors.

Research only. No broker, order, paper, live, strategy-registry or production action.
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

OUT_REL = Path("runtime/research/cross_strike_diffusion_discovery_v1")
RESEARCH_REL = Path("research/cross_strike_diffusion_discovery_v1")
EVENT_FILE = "event_universe_5m.parquet"
SEED = 20260729
NORMAL_COST_PCT = 0.10
STRESS_COST_PCT = 1.00
MIN_SIGNAL_SEPARATION_MINUTES = 15
MAX_SIGNALS_PER_SESSION = 2

MECHANISMS = (
    "adjacent_two_sided_laggard_catchup",
    "orderly_peer_wave_laggard_catchup",
    "persistent_peer_impulse_catchup",
    "mirror_decay_peer_diffusion",
    "volume_confirmed_peer_diffusion",
    "near_expiry_peer_diffusion",
    "midday_orderly_diffusion",
    "late_session_peer_diffusion",
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
    stress_profit_factor: float | None
    bootstrap_mean_ci_low: float | None
    bootstrap_mean_ci_high: float | None
    positive_folds: int
    total_folds: int
    largest_winner_share: float | None
    top_five_session_profit_share: float | None


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
    if len(values) < 20:
        return None, None
    rng = np.random.default_rng(SEED)
    means = np.empty(4000, dtype=float)
    for index in range(len(means)):
        means[index] = rng.choice(values, size=len(values), replace=True).mean()
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def calculate_metrics(trades: pd.DataFrame) -> Metrics:
    if trades.empty:
        return Metrics(0, 0, None, None, None, None, 0.0, None, None, None, None, 0, 0, None, None)
    normal = _finite(trades["net_return_pct"]).dropna()
    if normal.empty:
        return Metrics(0, 0, None, None, None, None, 0.0, None, None, None, None, 0, 0, None, None)
    stress = _finite(trades.loc[normal.index, "stress_return_pct"]).dropna().to_numpy(dtype=float)
    values = normal.to_numpy(dtype=float)
    ordered = np.sort(values)[::-1]
    trimmed = ordered[5:] if len(ordered) > 5 else np.asarray([], dtype=float)
    ci_low, ci_high = _bootstrap_ci(values)
    fold_means = (
        trades.loc[normal.index].groupby("fold_id", observed=True)["net_return_pct"].mean()
        if "fold_id" in trades.columns
        else pd.Series(dtype=float)
    )
    positive_total = float(ordered[ordered > 0].sum())
    largest_share = float(max(ordered[0], 0.0) / positive_total) if positive_total > 0 else None
    session_pnl = trades.loc[normal.index].groupby("session_id", observed=True)["net_return_pct"].sum()
    positive_session_total = float(session_pnl[session_pnl > 0].sum())
    top_five_session_share = (
        float(session_pnl.nlargest(5).clip(lower=0).sum() / positive_session_total)
        if positive_session_total > 0
        else None
    )
    return Metrics(
        trades=int(len(values)),
        sessions=int(trades.loc[normal.index, "session_id"].nunique()),
        profit_factor=_profit_factor(values),
        mean_return_pct=float(values.mean()),
        median_return_pct=float(np.median(values)),
        win_rate=float(np.mean(values > 0)),
        net_return_pct_sum=float(values.sum()),
        remove_top_five_profit_factor=_profit_factor(trimmed) if len(trimmed) else None,
        stress_profit_factor=_profit_factor(stress),
        bootstrap_mean_ci_low=ci_low,
        bootstrap_mean_ci_high=ci_high,
        positive_folds=int((fold_means > 0).sum()),
        total_folds=int(len(fold_means)),
        largest_winner_share=largest_share,
        top_five_session_profit_share=top_five_session_share,
    )


def semantic_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _q(frame: pd.DataFrame, column: str, quantile: float, default: float = 0.0) -> float:
    values = _finite(frame[column]).dropna()
    return float(values.quantile(quantile)) if not values.empty else default


def prepare_causal(event_path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(event_path, columns=base.CAUSAL_COLUMNS)
    frame = base._surface_features(frame)
    frame = frame.loc[frame["minute_of_day"] >= 585].copy()
    frame = frame.sort_values(
        ["session_id", "timestamp", "expiry_id", "option_type", "strike", "expired_instrument_key"],
        kind="mergesort",
    )
    keys = ["session_id", "timestamp", "expiry_id", "option_type"]
    grouped = frame.groupby(keys, sort=False, observed=True)
    frame["strike_rank"] = grouped["strike"].rank(method="first")
    frame["left_return"] = grouped["prior_5m_return_pct"].shift(1)
    frame["right_return"] = grouped["prior_5m_return_pct"].shift(-1)
    frame["left_volume_ratio"] = grouped["prior_5m_volume_ratio"].shift(1)
    frame["right_volume_ratio"] = grouped["prior_5m_volume_ratio"].shift(-1)
    frame["left_strike"] = grouped["strike"].shift(1)
    frame["right_strike"] = grouped["strike"].shift(-1)
    frame["adjacent_count"] = frame[["left_return", "right_return"]].notna().sum(axis=1)
    frame["adjacent_mean_return"] = frame[["left_return", "right_return"]].mean(axis=1, skipna=True)
    frame["adjacent_min_return"] = frame[["left_return", "right_return"]].min(axis=1, skipna=True)
    frame["adjacent_positive_breadth"] = frame[["left_return", "right_return"]].gt(0).sum(axis=1) / frame[
        "adjacent_count"
    ].replace(0, np.nan)
    frame["adjacent_mean_volume_ratio"] = frame[["left_volume_ratio", "right_volume_ratio"]].mean(
        axis=1, skipna=True
    )
    frame["peer_lead_gap"] = frame["adjacent_mean_return"] - frame["prior_5m_return_pct"]
    frame["peer_dispersion"] = frame[["left_return", "right_return"]].std(axis=1, skipna=True)
    instrument = frame.groupby("expired_instrument_key", sort=False, observed=True)
    frame["previous_peer_mean"] = instrument["adjacent_mean_return"].shift(1)
    frame["previous_peer_gap"] = instrument["peer_lead_gap"].shift(1)
    frame["peer_impulse_acceleration"] = frame["adjacent_mean_return"] - frame["previous_peer_mean"]
    frame["target_catchup_acceleration"] = frame["prior_5m_return_pct"] - frame["previous_return"]
    return frame


def split_sessions(frame: pd.DataFrame) -> tuple[list[str], list[str]]:
    sessions = sorted(frame["session_id"].dropna().unique().tolist())
    cut = int(math.floor(len(sessions) * 0.75))
    return sessions[:cut], sessions[cut:]


def expanding_folds(research_sessions: list[str]) -> list[tuple[list[str], list[str], str]]:
    initial = int(math.floor(len(research_sessions) * 0.35))
    remaining = np.asarray(research_sessions[initial:], dtype=object)
    blocks = [list(block) for block in np.array_split(remaining, 5) if len(block)]
    folds: list[tuple[list[str], list[str], str]] = []
    train_end = initial
    for index, test_sessions in enumerate(blocks, start=1):
        folds.append((research_sessions[:train_end], test_sessions, f"fold_{index}"))
        train_end += len(test_sessions)
    return folds


def thresholds(training: pd.DataFrame) -> dict[str, float]:
    target_abs = _finite(training["prior_5m_return_pct"]).abs().dropna()
    return {
        "gap_p65": _q(training, "peer_lead_gap", 0.65),
        "gap_p75": _q(training, "peer_lead_gap", 0.75),
        "gap_p85": _q(training, "peer_lead_gap", 0.85),
        "peer_p55": _q(training, "adjacent_mean_return", 0.55),
        "peer_p65": _q(training, "adjacent_mean_return", 0.65),
        "peer_p75": _q(training, "adjacent_mean_return", 0.75),
        "target_abs_p50": float(target_abs.quantile(0.50)) if not target_abs.empty else 0.0,
        "target_abs_p65": float(target_abs.quantile(0.65)) if not target_abs.empty else 0.0,
        "volume_p50": _q(training, "prior_5m_volume_ratio", 0.50, 1.0),
        "volume_p65": _q(training, "prior_5m_volume_ratio", 0.65, 1.0),
        "adj_volume_p55": _q(training, "adjacent_mean_volume_ratio", 0.55, 1.0),
        "dispersion_p50": _q(training, "peer_dispersion", 0.50),
        "mirror_p45": _q(training, "mirror_return", 0.45),
        "previous_peer_p55": _q(training, "previous_peer_mean", 0.55),
        "peer_accel_p55": _q(training, "peer_impulse_acceleration", 0.55),
    }


def mechanism_masks(frame: pd.DataFrame, cut: dict[str, float]) -> dict[str, pd.Series]:
    target = frame["prior_5m_return_pct"]
    peer = frame["adjacent_mean_return"]
    gap = frame["peer_lead_gap"]
    adjacent_breadth = frame["adjacent_positive_breadth"]
    target_quiet = target.abs() <= cut["target_abs_p65"]
    peer_orderly = frame["peer_dispersion"] <= cut["dispersion_p50"]
    common = (peer > 0) & (gap >= cut["gap_p65"]) & (adjacent_breadth >= 0.50)
    return {
        "adjacent_two_sided_laggard_catchup": (
            (frame["adjacent_count"] == 2)
            & (frame["adjacent_min_return"] > 0)
            & (gap >= cut["gap_p75"])
            & target_quiet
        ),
        "orderly_peer_wave_laggard_catchup": (
            common
            & peer_orderly
            & (peer >= cut["peer_p65"])
            & (frame["surface_return_dispersion"] > 0)
        ),
        "persistent_peer_impulse_catchup": (
            common
            & (frame["previous_peer_mean"] >= cut["previous_peer_p55"])
            & (frame["previous_peer_gap"] > 0)
            & (frame["target_catchup_acceleration"] >= 0)
        ),
        "mirror_decay_peer_diffusion": (
            common
            & (frame["mirror_return"] <= cut["mirror_p45"])
            & (frame["option_asymmetry"] <= cut["gap_p75"])
        ),
        "volume_confirmed_peer_diffusion": (
            common
            & (frame["prior_5m_volume_ratio"] >= cut["volume_p50"])
            & (frame["adjacent_mean_volume_ratio"] >= cut["adj_volume_p55"])
            & (peer >= cut["peer_p55"])
        ),
        "near_expiry_peer_diffusion": (
            common
            & frame["days_to_expiry"].between(0, 2, inclusive="both")
            & (gap >= cut["gap_p75"])
            & (frame["prior_5m_volume_ratio"] >= cut["volume_p50"])
        ),
        "midday_orderly_diffusion": (
            common
            & frame["minute_of_day"].between(690, 810, inclusive="both")
            & peer_orderly
            & (frame["peer_impulse_acceleration"] >= cut["peer_accel_p55"])
        ),
        "late_session_peer_diffusion": (
            common
            & frame["minute_of_day"].between(810, 885, inclusive="both")
            & (gap >= cut["gap_p75"])
            & (frame["adjacent_mean_volume_ratio"] >= cut["adj_volume_p55"])
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
        & frame["adjacent_mean_return"].notna()
    )


def _select_independent(group: pd.DataFrame) -> pd.DataFrame:
    selected: list[int] = []
    last_timestamp: pd.Timestamp | None = None
    for index, row in group.sort_values(
        ["timestamp", "diffusion_score", "premium_distance", "expired_instrument_key"],
        ascending=[True, False, True, True],
        kind="mergesort",
    ).iterrows():
        timestamp = pd.Timestamp(row["timestamp"])
        if last_timestamp is not None:
            elapsed = (timestamp - last_timestamp).total_seconds() / 60.0
            if elapsed < MIN_SIGNAL_SEPARATION_MINUTES:
                continue
        selected.append(index)
        last_timestamp = timestamp
        if len(selected) >= MAX_SIGNALS_PER_SESSION:
            break
    return group.loc[selected]


def select_signals(frame: pd.DataFrame, mask: pd.Series, mechanism: str, sessions: list[str]) -> pd.DataFrame:
    candidates = frame.loc[mask & eligibility(frame) & frame["session_id"].isin(sessions)].copy()
    if candidates.empty:
        return candidates
    candidates["mechanism"] = mechanism
    candidates["premium_distance"] = (candidates["entry_price_next_open"] - 120.0).abs()
    candidates["diffusion_score"] = (
        candidates["peer_lead_gap"].fillna(0)
        + candidates["adjacent_mean_return"].fillna(0)
        + 2.0 * candidates["adjacent_positive_breadth"].fillna(0)
        + 0.25 * candidates["adjacent_mean_volume_ratio"].fillna(0)
        - 0.25 * candidates["peer_dispersion"].fillna(0)
    )
    best_timestamp = candidates.groupby(["session_id", "timestamp"], observed=True)["diffusion_score"].transform("max")
    candidates = candidates.loc[candidates["diffusion_score"].eq(best_timestamp)]
    candidates = candidates.sort_values(
        ["session_id", "timestamp", "diffusion_score", "premium_distance", "expired_instrument_key"],
        ascending=[True, True, False, True, True],
        kind="mergesort",
    ).drop_duplicates(["session_id", "timestamp"], keep="first")
    selected = [part for _, part in candidates.groupby("session_id", sort=False, observed=True) if not part.empty]
    if not selected:
        return candidates.iloc[0:0]
    return pd.concat([_select_independent(part) for part in selected], ignore_index=False).sort_values(
        ["session_id", "timestamp"], kind="mergesort"
    )


def attach(signals: pd.DataFrame, outcomes: pd.DataFrame, fold_id: str) -> pd.DataFrame:
    trades = base._attach_outcomes(signals, outcomes)
    if trades.empty:
        return trades
    trades = trades.loc[trades["label_horizon_minutes"].eq(5)].copy()
    trades["fold_id"] = fold_id
    return trades


def delayed_control(signals: pd.DataFrame, causal: pd.DataFrame, outcomes: pd.DataFrame, fold_id: str) -> pd.DataFrame:
    if signals.empty:
        return signals.copy()
    delayed = signals[["expired_instrument_key", "timestamp", "session_id", "mechanism"]].copy()
    delayed["timestamp"] = delayed["timestamp"] + pd.Timedelta(minutes=5)
    lookup_columns = [
        "expired_instrument_key",
        "timestamp",
        "entry_price_next_open",
        "session_id",
        "expiry_id",
        "option_type",
        "strike",
    ]
    lookup = causal[lookup_columns].drop_duplicates(["expired_instrument_key", "timestamp"])
    delayed = delayed.drop(columns=["session_id"]).merge(
        lookup, on=["expired_instrument_key", "timestamp"], how="inner", validate="one_to_one"
    )
    delayed["mechanism"] = delayed["mechanism"] + "__delayed_5m_control"
    return attach(delayed, outcomes, fold_id)


def oof_gate(metric: Metrics) -> bool:
    return bool(
        metric.trades >= 80
        and metric.sessions >= 60
        and metric.profit_factor is not None
        and metric.profit_factor >= 1.20
        and metric.mean_return_pct is not None
        and metric.mean_return_pct > 0
        and metric.median_return_pct is not None
        and metric.median_return_pct >= 0
        and metric.remove_top_five_profit_factor is not None
        and metric.remove_top_five_profit_factor >= 1.05
        and metric.stress_profit_factor is not None
        and metric.stress_profit_factor >= 1.00
        and metric.bootstrap_mean_ci_low is not None
        and metric.bootstrap_mean_ci_low > 0
        and metric.total_folds == 5
        and metric.positive_folds >= 4
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.20)
        and (metric.top_five_session_profit_share is None or metric.top_five_session_profit_share <= 0.30)
    )


def holdout_gate(metric: Metrics) -> bool:
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


def control_gate(primary: Metrics, delayed: Metrics) -> bool:
    if delayed.trades < max(10, int(primary.trades * 0.50)):
        return False
    if delayed.mean_return_pct is None or primary.mean_return_pct is None:
        return False
    return bool(primary.mean_return_pct >= delayed.mean_return_pct + 0.20)


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
    research_sessions, holdout_sessions = split_sessions(causal)
    folds = expanding_folds(research_sessions)
    contract = {
        "schema_version": "cross_strike_diffusion_discovery_v1",
        "hypothesis": "coherent_adjacent_strike_repricing_precedes_lagging_contract_catchup",
        "mechanisms": list(MECHANISMS),
        "mechanism_count": len(MECHANISMS),
        "research_sessions": len(research_sessions),
        "holdout_sessions": len(holdout_sessions),
        "fold_count": len(folds),
        "threshold_policy": "fixed_quantiles_recomputed_from_prior_fold_sessions_only",
        "maximum_signals_per_session": MAX_SIGNALS_PER_SESSION,
        "minimum_signal_separation_minutes": MIN_SIGNAL_SEPARATION_MINUTES,
        "minimum_oof_trades": 80,
        "minimum_holdout_trades": 25,
        "normal_cost_pct": NORMAL_COST_PCT,
        "stress_cost_pct": STRESS_COST_PCT,
        "holdout_policy": "latest_25pct_outcomes_unread_until_oof_survivor_freeze",
        "research_only": True,
        "allowed_for_live_execution": False,
    }
    contract["semantic_sha256"] = semantic_hash(contract)
    stable_json(out / "frozen_contract.json", contract)

    research_outcomes = base._load_outcomes(event_path, base._raw_sessions(causal, research_sessions))
    ledgers: dict[str, list[pd.DataFrame]] = {name: [] for name in MECHANISMS}
    delayed_ledgers: dict[str, list[pd.DataFrame]] = {name: [] for name in MECHANISMS}
    threshold_records: list[dict[str, Any]] = []
    for train_sessions, test_sessions, fold_id in folds:
        training = causal.loc[causal["session_id"].isin(train_sessions)]
        testing = causal.loc[causal["session_id"].isin(test_sessions)]
        cut = thresholds(training)
        threshold_records.append({"fold_id": fold_id, "training_sessions": len(train_sessions), "thresholds": cut})
        masks = mechanism_masks(testing, cut)
        for mechanism in MECHANISMS:
            signals = select_signals(testing, masks[mechanism], mechanism, test_sessions)
            trades = attach(signals, research_outcomes, fold_id)
            delayed = delayed_control(signals, testing, research_outcomes, fold_id)
            if not trades.empty:
                ledgers[mechanism].append(trades)
            if not delayed.empty:
                delayed_ledgers[mechanism].append(delayed)
    stable_json(out / "fold_thresholds.json", threshold_records)

    oof_records: list[dict[str, Any]] = []
    survivors: list[tuple[str, Metrics]] = []
    combined_ledgers: list[pd.DataFrame] = []
    for mechanism in MECHANISMS:
        trades = pd.concat(ledgers[mechanism], ignore_index=True, sort=False) if ledgers[mechanism] else pd.DataFrame()
        delayed = (
            pd.concat(delayed_ledgers[mechanism], ignore_index=True, sort=False)
            if delayed_ledgers[mechanism]
            else pd.DataFrame()
        )
        metric = calculate_metrics(trades)
        delayed_metric = calculate_metrics(delayed)
        economic_pass = oof_gate(metric)
        delayed_pass = control_gate(metric, delayed_metric) if economic_pass else False
        passed = economic_pass and delayed_pass
        oof_records.append(
            {
                "mechanism": mechanism,
                **asdict(metric),
                "delayed_control": asdict(delayed_metric),
                "economic_gate": economic_pass,
                "delayed_control_gate": delayed_pass,
                "oof_gate": passed,
            }
        )
        if not trades.empty:
            combined_ledgers.append(trades.assign(partition="research_oof", control="primary"))
        if not delayed.empty:
            combined_ledgers.append(delayed.assign(partition="research_oof", control="delayed_5m"))
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
    stable_json(
        out / "oof_screen.json",
        {
            "records": oof_records,
            "survivors_frozen_for_holdout": survivor_names,
            "holdout_outcomes_materialized": bool(survivor_names),
        },
    )

    holdout_records: list[dict[str, Any]] = []
    validated: list[str] = []
    if survivor_names:
        final_cut = thresholds(causal.loc[causal["session_id"].isin(research_sessions)])
        holdout = causal.loc[causal["session_id"].isin(holdout_sessions)]
        masks = mechanism_masks(holdout, final_cut)
        holdout_outcomes = base._load_outcomes(event_path, base._raw_sessions(causal, holdout_sessions))
        for mechanism in survivor_names:
            signals = select_signals(holdout, masks[mechanism], mechanism, holdout_sessions)
            trades = attach(signals, holdout_outcomes, "holdout")
            delayed = delayed_control(signals, holdout, holdout_outcomes, "holdout")
            metric = calculate_metrics(trades)
            delayed_metric = calculate_metrics(delayed)
            economic_pass = holdout_gate(metric)
            delayed_pass = control_gate(metric, delayed_metric) if economic_pass else False
            passed = economic_pass and delayed_pass
            holdout_records.append(
                {
                    "mechanism": mechanism,
                    **asdict(metric),
                    "delayed_control": asdict(delayed_metric),
                    "economic_gate": economic_pass,
                    "delayed_control_gate": delayed_pass,
                    "holdout_gate": passed,
                }
            )
            if not trades.empty:
                combined_ledgers.append(trades.assign(partition="holdout", control="primary"))
            if not delayed.empty:
                combined_ledgers.append(delayed.assign(partition="holdout", control="delayed_5m"))
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

    if combined_ledgers:
        ledger = pd.concat(combined_ledgers, ignore_index=True, sort=False)
        keep = [
            "partition", "control", "fold_id", "mechanism", "session_id", "timestamp",
            "expired_instrument_key", "expiry_id", "option_type", "strike", "entry_price_next_open",
            "gross_return_pct", "net_return_pct", "stress_return_pct", "forward_mfe_points",
            "forward_mae_points", "label_horizon_minutes", "prior_5m_return_pct", "previous_return",
            "adjacent_mean_return", "adjacent_min_return", "adjacent_positive_breadth", "peer_lead_gap",
            "peer_dispersion", "previous_peer_mean", "previous_peer_gap", "adjacent_mean_volume_ratio",
            "mirror_return", "days_to_expiry", "minute_of_day",
        ]
        ledger[[column for column in keep if column in ledger.columns]].to_csv(out / "trade_ledger.csv", index=False)

    verdict = (
        "STRUCTURAL_EDGE_FOUND_CROSS_STRIKE_DIFFUSION_WITH_HIGHER_OCCURRENCE_HOLDOUT_SURVIVOR"
        if validated
        else (
            "NO_HIGH_OCCURRENCE_OOF_SURVIVOR_IN_CROSS_STRIKE_DIFFUSION_FAMILIES"
            if not survivor_names
            else "CROSS_STRIKE_DIFFUSION_OOF_SURVIVORS_FAILED_UNTOUCHED_HOLDOUT"
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
        "paper_or_live_authorized": False,
        "allowed_for_live_execution": False,
    }
    final["semantic_sha256"] = semantic_hash(final)
    stable_json(out / "final_decision.json", final)
    (research / "RESULT.md").write_text(
        "# Cross-Strike Diffusion Discovery V1\n\n"
        f"Principal verdict: `{verdict}`\n\n"
        f"OOF survivors: `{survivor_names}`\n\n"
        f"Holdout survivors: `{validated}`\n\n"
        f"Holdout outcomes materialized: `{bool(survivor_names)}`\n\n"
        "This is historical OHLCV research only. No paper or live authorization is granted.\n",
        encoding="utf-8",
    )
    print(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
