#!/usr/bin/env python3
"""Theory-led option-surface transition discovery using preserved NIFTY option OHLCV.

The runner is deliberately staged:
1. build causal option-surface features without future outcome columns;
2. calibrate fixed quantile cutoffs on chronological development sessions only;
3. evaluate exactly twelve preregistered mechanisms on development outcomes;
4. materialize validation outcomes only for development survivors;
5. never materialize the latest 25% holdout outcomes.

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

from scripts.run_conditional_precursor_discrimination_v2 import PRIOR_REL, stable_json

OUT_REL = Path("runtime/research/option_surface_transition_discovery_v1")
RESEARCH_REL = Path("research/option_surface_transition_discovery_v1")
EVENT_FILE = "event_universe_5m.parquet"
SEED = 20260729
NORMAL_COST_PCT = 0.10  # 5 bps per side expressed in percentage points.
STRESS_COST_PCT = 1.00  # 50 bps per side.
TARGET_ENTRY_PREMIUM = 150.0

CAUSAL_COLUMNS = [
    "expired_instrument_key",
    "expiry",
    "option_type",
    "strike",
    "timestamp",
    "session",
    "minute_of_day",
    "days_to_expiry",
    "premium_band",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "open_interest",
    "entry_price_next_open",
    "prior_5m_return_pct",
    "prior_10m_range_pct",
    "prior_5m_volume_ratio",
    "transition_compression_to_lift",
    "transition_put_call_selloff_or_lift",
    "transition_volume_participation",
]

OUTCOME_COLUMNS = [
    "expired_instrument_key",
    "timestamp",
    "session",
    "expiry",
    "option_type",
    "strike",
    "entry_price_next_open",
    "forward_mfe_points",
    "forward_mae_points",
    "forward_close_change_points",
    "forward_expansion_pct",
    "label_horizon_minutes",
    "is_expansion_event",
    "move_cluster_id",
]

MECHANISMS = (
    "compression_breadth_release",
    "second_push_surface_acceleration",
    "opposing_wing_decay",
    "synchronised_low_dispersion_lift",
    "divergence_catchup",
    "acceptance_persistence",
    "oi_volume_confirmation",
    "near_expiry_convexity",
    "late_day_pe_cascade",
    "late_day_ce_cascade",
    "surface_mass_migration",
    "triple_transition_alignment",
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
    positive_walk_forward_folds: int
    walk_forward_folds: int
    largest_winner_share: float | None


def _finite(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)


def _profit_factor(values: Iterable[float]) -> float | None:
    vals = [float(value) for value in values if math.isfinite(float(value))]
    gross_profit = sum(value for value in vals if value > 0)
    gross_loss = -sum(value for value in vals if value < 0)
    if gross_loss > 0:
        return gross_profit / gross_loss
    return math.inf if gross_profit > 0 else None


def _bootstrap_mean_ci(values: np.ndarray) -> tuple[float | None, float | None]:
    if len(values) < 8:
        return None, None
    rng = np.random.default_rng(SEED)
    means = np.empty(2000, dtype=float)
    for index in range(len(means)):
        means[index] = rng.choice(values, size=len(values), replace=True).mean()
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def _walk_forward(values: pd.DataFrame) -> tuple[int, int]:
    if values.empty:
        return 0, 0
    ordered = values.sort_values(["session_id", "timestamp"])
    folds = [fold for fold in np.array_split(ordered, 4) if len(fold) >= 3]
    positive = sum(float(fold["net_return_pct"].mean()) > 0 for fold in folds)
    return int(positive), int(len(folds))


def calculate_metrics(trades: pd.DataFrame) -> Metrics:
    if trades.empty:
        return Metrics(0, None, None, None, None, 0.0, None, None, None, None, 0, 0, None)
    normal = _finite(trades["net_return_pct"]).dropna().to_numpy(dtype=float)
    stress = _finite(trades["stress_return_pct"]).dropna().to_numpy(dtype=float)
    if len(normal) == 0:
        return Metrics(0, None, None, None, None, 0.0, None, None, None, None, 0, 0, None)
    ordered = np.sort(normal)[::-1]
    trimmed = ordered[2:] if len(ordered) > 2 else np.array([], dtype=float)
    ci_low, ci_high = _bootstrap_mean_ci(normal)
    positive_folds, total_folds = _walk_forward(trades)
    positive_total = float(ordered[ordered > 0].sum())
    largest_share = float(max(ordered[0], 0.0) / positive_total) if positive_total > 0 else None
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
        positive_walk_forward_folds=positive_folds,
        walk_forward_folds=total_folds,
        largest_winner_share=largest_share,
    )


def _robust_quantile(series: pd.Series, quantile: float, default: float = 0.0) -> float:
    values = _finite(series).dropna()
    return float(values.quantile(quantile)) if not values.empty else float(default)


def _surface_features(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    numeric = [
        "strike",
        "minute_of_day",
        "days_to_expiry",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "open_interest",
        "entry_price_next_open",
        "prior_5m_return_pct",
        "prior_10m_range_pct",
        "prior_5m_volume_ratio",
        "transition_compression_to_lift",
        "transition_put_call_selloff_or_lift",
        "transition_volume_participation",
    ]
    for column in numeric:
        frame[column] = _finite(frame[column])
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="raise", utc=True)
    frame["session_id"] = frame["session"].astype(str)
    frame["expiry_id"] = frame["expiry"].astype(str)
    frame["option_type"] = frame["option_type"].astype(str).str.upper()
    frame = frame.sort_values(["expired_instrument_key", "timestamp"], kind="mergesort")

    instrument = frame.groupby("expired_instrument_key", sort=False, observed=True)
    frame["previous_return"] = instrument["prior_5m_return_pct"].shift(1)
    frame["previous_close"] = instrument["close"].shift(1)
    frame["previous_volume_ratio"] = instrument["prior_5m_volume_ratio"].shift(1)
    frame["previous_open_interest"] = instrument["open_interest"].shift(1)
    frame["return_acceleration"] = frame["prior_5m_return_pct"] - frame["previous_return"]
    frame["volume_acceleration"] = frame["prior_5m_volume_ratio"] - frame["previous_volume_ratio"]
    denominator = frame["previous_open_interest"].abs().clip(lower=1.0)
    frame["oi_change_ratio"] = (frame["open_interest"] - frame["previous_open_interest"]) / denominator
    frame["bar_acceptance"] = frame["low"] >= frame["previous_close"]
    frame["positive_return"] = (frame["prior_5m_return_pct"] > 0).astype("float32")
    frame["positive_acceleration"] = (frame["return_acceleration"] > 0).astype("float32")
    frame["volume_participating"] = (frame["prior_5m_volume_ratio"] > 1).astype("float32")
    frame["positive_weight"] = (
        frame["prior_5m_return_pct"].clip(lower=0).fillna(0)
        * np.log1p(frame["volume"].clip(lower=0).fillna(0))
    )
    frame["weighted_strike_numerator"] = frame["strike"] * frame["positive_weight"]

    surface_keys = ["session_id", "timestamp", "expiry_id", "option_type"]
    grouped = frame.groupby(surface_keys, sort=False, observed=True)
    surface = grouped.agg(
        surface_count=("expired_instrument_key", "size"),
        breadth_positive=("positive_return", "mean"),
        breadth_acceleration=("positive_acceleration", "mean"),
        breadth_volume=("volume_participating", "mean"),
        surface_median_return=("prior_5m_return_pct", "median"),
        surface_median_acceleration=("return_acceleration", "median"),
        surface_return_dispersion=("prior_5m_return_pct", "std"),
        positive_weight_sum=("positive_weight", "sum"),
        weighted_strike_sum=("weighted_strike_numerator", "sum"),
        compression_transition_breadth=("transition_compression_to_lift", "mean"),
        put_call_transition_breadth=("transition_put_call_selloff_or_lift", "mean"),
        participation_transition_breadth=("transition_volume_participation", "mean"),
    ).reset_index()
    surface["weighted_strike"] = surface["weighted_strike_sum"] / surface["positive_weight_sum"].replace(0, np.nan)
    surface = surface.sort_values(["session_id", "expiry_id", "option_type", "timestamp"], kind="mergesort")
    chain = surface.groupby(["session_id", "expiry_id", "option_type"], sort=False, observed=True)
    surface["breadth_delta"] = surface["breadth_positive"] - chain["breadth_positive"].shift(1)
    surface["acceleration_breadth_delta"] = surface["breadth_acceleration"] - chain["breadth_acceleration"].shift(1)
    surface["weighted_strike_delta"] = surface["weighted_strike"] - chain["weighted_strike"].shift(1)
    direction = np.where(surface["option_type"].eq("CE"), 1.0, -1.0)
    surface["directional_mass_shift"] = surface["weighted_strike_delta"] * direction
    keep_surface = surface_keys + [
        "surface_count",
        "breadth_positive",
        "breadth_acceleration",
        "breadth_volume",
        "surface_median_return",
        "surface_median_acceleration",
        "surface_return_dispersion",
        "breadth_delta",
        "acceleration_breadth_delta",
        "directional_mass_shift",
        "compression_transition_breadth",
        "put_call_transition_breadth",
        "participation_transition_breadth",
    ]
    frame = frame.merge(surface[keep_surface], on=surface_keys, how="left", validate="many_to_one")

    mirror = frame[
        [
            "session_id",
            "timestamp",
            "expiry_id",
            "strike",
            "option_type",
            "prior_5m_return_pct",
            "return_acceleration",
            "prior_5m_volume_ratio",
        ]
    ].copy()
    mirror["option_type"] = mirror["option_type"].map({"CE": "PE", "PE": "CE"})
    mirror = mirror.rename(
        columns={
            "prior_5m_return_pct": "mirror_return",
            "return_acceleration": "mirror_acceleration",
            "prior_5m_volume_ratio": "mirror_volume_ratio",
        }
    )
    mirror = mirror.drop_duplicates(["session_id", "timestamp", "expiry_id", "strike", "option_type"])
    frame = frame.merge(
        mirror,
        on=["session_id", "timestamp", "expiry_id", "strike", "option_type"],
        how="left",
        validate="many_to_one",
    )
    frame["option_asymmetry"] = frame["prior_5m_return_pct"] - frame["mirror_return"]
    return frame


def _partition_sessions(frame: pd.DataFrame) -> dict[str, list[str]]:
    sessions = sorted(frame["session_id"].dropna().unique().tolist())
    development_end = int(math.floor(len(sessions) * 0.60))
    validation_end = int(math.floor(len(sessions) * 0.75))
    return {
        "development": sessions[:development_end],
        "validation": sessions[development_end:validation_end],
        "holdout": sessions[validation_end:],
    }


def _thresholds(frame: pd.DataFrame, development_sessions: list[str]) -> dict[str, float]:
    development = frame.loc[frame["session_id"].isin(development_sessions)]
    return {
        "range_low": _robust_quantile(development["prior_10m_range_pct"], 0.30),
        "return_low": _robust_quantile(development["prior_5m_return_pct"], 0.30),
        "return_high": _robust_quantile(development["prior_5m_return_pct"], 0.70),
        "acceleration_high": _robust_quantile(development["return_acceleration"], 0.70),
        "breadth_delta_high": _robust_quantile(development["breadth_delta"], 0.70),
        "asymmetry_high": _robust_quantile(development["option_asymmetry"], 0.70),
        "dispersion_low": _robust_quantile(development["surface_return_dispersion"], 0.30),
        "volume_high": _robust_quantile(development["prior_5m_volume_ratio"], 0.70, 1.0),
        "oi_change_high": _robust_quantile(development["oi_change_ratio"], 0.70),
        "mass_shift_high": _robust_quantile(development["directional_mass_shift"], 0.70),
    }


def _mechanism_masks(frame: pd.DataFrame, threshold: dict[str, float]) -> dict[str, pd.Series]:
    ret = frame["prior_5m_return_pct"]
    previous = frame["previous_return"]
    acceleration = frame["return_acceleration"]
    breadth = frame["breadth_positive"]
    breadth_acceleration = frame["breadth_acceleration"]
    breadth_delta = frame["breadth_delta"]
    volume_breadth = frame["breadth_volume"]
    mirror = frame["mirror_return"]
    asymmetry = frame["option_asymmetry"]
    common_second_push = (
        (previous > 0)
        & (ret > previous)
        & (acceleration >= threshold["acceleration_high"])
        & (breadth_acceleration >= 0.60)
        & (breadth >= 0.60)
    )
    return {
        "compression_breadth_release": (
            (frame["prior_10m_range_pct"] <= threshold["range_low"])
            & (acceleration >= threshold["acceleration_high"])
            & (breadth_delta >= threshold["breadth_delta_high"])
            & (volume_breadth >= 0.50)
        ),
        "second_push_surface_acceleration": common_second_push,
        "opposing_wing_decay": (
            (ret > 0)
            & (mirror <= 0)
            & (asymmetry >= threshold["asymmetry_high"])
            & (breadth >= 0.60)
        ),
        "synchronised_low_dispersion_lift": (
            (frame["surface_median_return"] > 0)
            & (breadth >= 0.70)
            & (frame["surface_return_dispersion"] <= threshold["dispersion_low"])
            & (volume_breadth >= 0.50)
        ),
        "divergence_catchup": (
            (previous <= threshold["return_low"])
            & (ret >= threshold["return_high"])
            & (acceleration >= threshold["acceleration_high"])
            & (breadth_delta > 0)
        ),
        "acceptance_persistence": (
            (previous > 0)
            & (ret > 0)
            & frame["bar_acceptance"].fillna(False)
            & (breadth >= 0.60)
        ),
        "oi_volume_confirmation": (
            (ret > 0)
            & (frame["prior_5m_volume_ratio"] >= threshold["volume_high"])
            & (frame["oi_change_ratio"] >= threshold["oi_change_high"])
            & (breadth >= 0.50)
        ),
        "near_expiry_convexity": (
            (frame["days_to_expiry"].between(0, 2, inclusive="both"))
            & (acceleration >= threshold["acceleration_high"])
            & (breadth_delta >= threshold["breadth_delta_high"])
            & (asymmetry > 0)
        ),
        "late_day_pe_cascade": (
            frame["option_type"].eq("PE")
            & (frame["minute_of_day"] >= 780)
            & common_second_push
            & (mirror <= 0)
        ),
        "late_day_ce_cascade": (
            frame["option_type"].eq("CE")
            & (frame["minute_of_day"] >= 780)
            & common_second_push
            & (mirror <= 0)
        ),
        "surface_mass_migration": (
            (frame["directional_mass_shift"] >= threshold["mass_shift_high"])
            & (breadth >= 0.60)
            & (volume_breadth >= 0.50)
            & (ret > 0)
        ),
        "triple_transition_alignment": (
            (frame["transition_compression_to_lift"] > 0)
            & (frame["transition_put_call_selloff_or_lift"] > 0)
            & (frame["transition_volume_participation"] > 0)
            & (ret > 0)
            & (breadth >= 0.50)
        ),
    }


def _base_eligibility(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["entry_price_next_open"].between(30.0, 500.0, inclusive="both")
        & frame["minute_of_day"].between(570, 890, inclusive="both")
        & frame["days_to_expiry"].between(0, 7, inclusive="both")
        & (frame["surface_count"] >= 3)
        & (frame["volume"] > 0)
        & frame["previous_return"].notna()
    )


def _select_first_signal(
    frame: pd.DataFrame,
    mask: pd.Series,
    mechanism: str,
    sessions: list[str],
) -> pd.DataFrame:
    eligible = frame.loc[mask & _base_eligibility(frame) & frame["session_id"].isin(sessions)].copy()
    if eligible.empty:
        return eligible
    eligible["mechanism"] = mechanism
    eligible["premium_distance"] = (eligible["entry_price_next_open"] - TARGET_ENTRY_PREMIUM).abs()
    eligible["mechanism_score"] = (
        eligible["return_acceleration"].fillna(0)
        + eligible["option_asymmetry"].fillna(0)
        + 10.0 * eligible["breadth_delta"].fillna(0)
        + eligible["prior_5m_volume_ratio"].fillna(0)
        + 0.01 * eligible["directional_mass_shift"].fillna(0)
    )
    earliest = eligible.groupby("session_id", observed=True)["timestamp"].transform("min")
    eligible = eligible.loc[eligible["timestamp"].eq(earliest)]
    eligible = eligible.sort_values(
        [
            "session_id",
            "mechanism_score",
            "premium_distance",
            "prior_5m_volume_ratio",
            "expired_instrument_key",
        ],
        ascending=[True, False, True, False, True],
        kind="mergesort",
    )
    return eligible.drop_duplicates("session_id", keep="first")


def _load_outcomes(path: Path, raw_sessions: list[Any]) -> pd.DataFrame:
    # Fail closed: never fall back to reading all outcomes if partition filtering fails.
    outcomes = pd.read_parquet(
        path,
        columns=OUTCOME_COLUMNS,
        filters=[("session", "in", raw_sessions)],
    )
    outcomes["timestamp"] = pd.to_datetime(outcomes["timestamp"], errors="raise", utc=True)
    outcomes["session_id"] = outcomes["session"].astype(str)
    outcomes["expiry_id"] = outcomes["expiry"].astype(str)
    outcomes["option_type"] = outcomes["option_type"].astype(str).str.upper()
    outcomes = outcomes.drop_duplicates(["expired_instrument_key", "timestamp"])
    return outcomes


def _attach_outcomes(signals: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    if signals.empty:
        return signals.copy()
    columns = [
        "expired_instrument_key",
        "timestamp",
        "forward_mfe_points",
        "forward_mae_points",
        "forward_close_change_points",
        "forward_expansion_pct",
        "label_horizon_minutes",
        "is_expansion_event",
        "move_cluster_id",
    ]
    trades = signals.merge(
        outcomes[columns],
        on=["expired_instrument_key", "timestamp"],
        how="inner",
        validate="one_to_one",
    )
    trades["gross_return_pct"] = (
        _finite(trades["forward_close_change_points"])
        / _finite(trades["entry_price_next_open"]).replace(0, np.nan)
        * 100.0
    )
    trades["net_return_pct"] = trades["gross_return_pct"] - NORMAL_COST_PCT
    trades["stress_return_pct"] = trades["gross_return_pct"] - STRESS_COST_PCT
    return trades


def _raw_sessions(frame: pd.DataFrame, session_ids: list[str]) -> list[Any]:
    mapping = frame[["session_id", "session"]].drop_duplicates("session_id")
    return mapping.loc[mapping["session_id"].isin(session_ids), "session"].tolist()


def _development_gate(metrics: Metrics) -> bool:
    return bool(
        metrics.trades >= 30
        and metrics.profit_factor is not None
        and metrics.profit_factor >= 1.20
        and metrics.mean_return_pct is not None
        and metrics.mean_return_pct > 0
        and metrics.remove_top_two_profit_factor is not None
        and metrics.remove_top_two_profit_factor >= 1.05
        and metrics.stress_profit_factor is not None
        and metrics.stress_profit_factor >= 1.05
        and metrics.bootstrap_mean_ci_low is not None
        and metrics.bootstrap_mean_ci_low > 0
        and metrics.walk_forward_folds >= 3
        and metrics.positive_walk_forward_folds >= metrics.walk_forward_folds - 1
        and (metrics.largest_winner_share is None or metrics.largest_winner_share <= 0.35)
    )


def _validation_gate(metrics: Metrics) -> bool:
    return bool(
        metrics.trades >= 10
        and metrics.profit_factor is not None
        and metrics.profit_factor >= 1.15
        and metrics.mean_return_pct is not None
        and metrics.mean_return_pct > 0
        and metrics.remove_top_two_profit_factor is not None
        and metrics.remove_top_two_profit_factor >= 1.00
        and metrics.stress_profit_factor is not None
        and metrics.stress_profit_factor >= 1.00
        and (metrics.largest_winner_share is None or metrics.largest_winner_share <= 0.40)
    )


def _semantic_hash(payload: Any) -> str:
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

    causal = pd.read_parquet(event_path, columns=CAUSAL_COLUMNS)
    causal = _surface_features(causal)
    partitions = _partition_sessions(causal)
    threshold = _thresholds(causal, partitions["development"])
    masks = _mechanism_masks(causal, threshold)

    contract = {
        "schema_version": "option_surface_transition_discovery_v1",
        "mechanisms": list(MECHANISMS),
        "mechanism_count": len(MECHANISMS),
        "target_entry_premium": TARGET_ENTRY_PREMIUM,
        "normal_cost_pct": NORMAL_COST_PCT,
        "stress_cost_pct": STRESS_COST_PCT,
        "partition_counts": {key: len(value) for key, value in partitions.items()},
        "holdout_policy": "latest_25pct_sessions_outcomes_not_materialized",
        "thresholds_calibrated_on": "development_causal_features_only",
        "thresholds": threshold,
        "research_only": True,
        "allowed_for_live_execution": False,
    }
    contract["semantic_sha256"] = _semantic_hash(contract)
    stable_json(out / "frozen_mechanism_contract.json", contract)

    development_outcomes = _load_outcomes(
        event_path,
        _raw_sessions(causal, partitions["development"]),
    )
    development_records: list[dict[str, Any]] = []
    development_ledgers: list[pd.DataFrame] = []
    survivors: list[tuple[str, Metrics]] = []
    for mechanism in MECHANISMS:
        signals = _select_first_signal(causal, masks[mechanism], mechanism, partitions["development"])
        trades = _attach_outcomes(signals, development_outcomes)
        metric = calculate_metrics(trades)
        passed = _development_gate(metric)
        development_records.append({"mechanism": mechanism, **asdict(metric), "development_gate": passed})
        if not trades.empty:
            development_ledgers.append(trades.assign(partition="development"))
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
    )[:4]
    survivor_names = [name for name, _ in survivors]
    stable_json(
        out / "development_screen.json",
        {
            "records": development_records,
            "survivors_advanced": survivor_names,
            "validation_outcomes_materialized": bool(survivor_names),
            "holdout_outcomes_materialized": False,
        },
    )

    validation_records: list[dict[str, Any]] = []
    validation_ledgers: list[pd.DataFrame] = []
    validated: list[str] = []
    if survivor_names:
        validation_outcomes = _load_outcomes(
            event_path,
            _raw_sessions(causal, partitions["validation"]),
        )
        for mechanism in survivor_names:
            signals = _select_first_signal(causal, masks[mechanism], mechanism, partitions["validation"])
            trades = _attach_outcomes(signals, validation_outcomes)
            metric = calculate_metrics(trades)
            passed = _validation_gate(metric)
            validation_records.append({"mechanism": mechanism, **asdict(metric), "validation_gate": passed})
            if not trades.empty:
                validation_ledgers.append(trades.assign(partition="validation"))
            if passed:
                validated.append(mechanism)

    stable_json(
        out / "validation_screen.json",
        {
            "records": validation_records,
            "validated_candidates": validated,
            "holdout_outcomes_materialized": False,
        },
    )

    ledgers = development_ledgers + validation_ledgers
    if ledgers:
        ledger = pd.concat(ledgers, ignore_index=True, sort=False)
        keep = [
            "partition",
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
            "is_expansion_event",
            "move_cluster_id",
            "prior_5m_return_pct",
            "previous_return",
            "return_acceleration",
            "breadth_positive",
            "breadth_delta",
            "breadth_acceleration",
            "breadth_volume",
            "option_asymmetry",
            "directional_mass_shift",
            "prior_5m_volume_ratio",
            "days_to_expiry",
            "minute_of_day",
        ]
        ledger[[column for column in keep if column in ledger.columns]].to_csv(
            out / "trade_ledger.csv",
            index=False,
        )

    verdict = (
        "PROMISING_STRUCTURAL_EDGE_VALIDATION_SURVIVOR_HOLDOUT_UNOPENED"
        if validated
        else (
            "NO_DEVELOPMENT_SURVIVOR_IN_FROZEN_SURFACE_MECHANISMS"
            if not survivor_names
            else "DEVELOPMENT_SURVIVORS_FAILED_VALIDATION"
        )
    )
    final = {
        "principal_verdict": verdict,
        "development_survivors": survivor_names,
        "validation_survivors": validated,
        "holdout_outcomes_materialized": False,
        "holdout_sessions": len(partitions["holdout"]),
        "execution_certification": "BLOCKED_AUTHORITATIVE_TIMESTAMP_ALIGNED_SPREAD_MISSING",
        "research_only": True,
        "allowed_for_live_execution": False,
        "contract_semantic_sha256": contract["semantic_sha256"],
    }
    stable_json(out / "final_decision.json", final)
    (research / "RESULT.md").write_text(
        "# Option Surface Transition Discovery V1\n\n"
        f"Principal verdict: `{verdict}`\n\n"
        f"Development survivors: `{survivor_names}`\n\n"
        f"Validation survivors: `{validated}`\n\n"
        "The latest 25% chronological holdout outcomes were not materialized.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
