#!/usr/bin/env python3
"""Surface-wide exhaustion and opposite-wing reversal discovery V1.

This campaign is materially different from cross-strike lag/leadership research.
It detects a broad directional option-surface impulse that loses acceleration,
participation or acceptance while the same-strike opposite option becomes resilient.
The candidate trade buys that opposite option at its next one-minute open and
exits ten minutes after the completed signal.

Design:
- earliest 70% sessions: five expanding OOF folds for eight frozen mechanisms;
- middle 15% sessions: validation for at most one frozen OOF survivor;
- latest 15% sessions: sealed campaign master holdout, never read here.

Research only. No broker, order, paper, live, registry or production action.
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

from scripts import run_cross_strike_diffusion_discovery_v1 as metrics_mod
from scripts import run_cross_strike_diffusion_campaign_v2 as splitmod
from scripts import run_selective_option_leadership_campaign_v3 as leadership_mod
from scripts import run_option_surface_transition_discovery_v1 as surface_mod
from scripts import run_peer_reclaim_horizon_campaign_v5 as horizon_mod
from scripts import run_peer_reclaim_horizon_campaign_v5_1 as fixed_delay
from scripts.run_conditional_precursor_discrimination_v2 import PRIOR_REL, stable_json

OUT_REL = Path("runtime/research/surface_exhaustion_mirror_reversal_v1")
RESEARCH_REL = Path("research/surface_exhaustion_mirror_reversal_v1")
EVENT_FILE = "event_universe_5m.parquet"
EXIT_HORIZON_MINUTES = 10
MIN_OOF_TRADES = 80
MIN_OOF_SESSIONS = 60
MIN_VALIDATION_TRADES = 20
MIN_VALIDATION_SESSIONS = 15
MAX_SIGNALS_PER_SESSION = 2
MIN_SIGNAL_SEPARATION_MINUTES = 15
CUMULATIVE_MECHANISM_COUNT = 39
SEED = 20260729

MECHANISMS = (
    "breadth_rollover_opposite_resilience",
    "second_push_failure_opposite_turn",
    "participation_exhaustion_opposite_turn",
    "dispersion_spike_exhaustion",
    "mass_migration_stall",
    "acceptance_failure_opposite_turn",
    "near_expiry_surface_exhaustion",
    "late_session_surface_exhaustion",
)


def semantic_hash(payload: Any) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(body).hexdigest()


def _finite(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)


def _q(frame: pd.DataFrame, column: str, quantile: float, default: float = 0.0) -> float:
    values = _finite(frame[column]).dropna()
    return float(values.quantile(quantile)) if not values.empty else float(default)


def prepare_causal(event_path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(event_path, columns=surface_mod.CAUSAL_COLUMNS)
    frame = surface_mod._surface_features(frame)
    frame = frame.sort_values(["expired_instrument_key", "timestamp"], kind="mergesort")
    instrument = frame.groupby("expired_instrument_key", sort=False, observed=True)
    frame["previous_option_asymmetry"] = instrument["option_asymmetry"].shift(1)
    frame["asymmetry_rollover"] = frame["option_asymmetry"] - frame["previous_option_asymmetry"]
    frame["previous_mirror_return"] = instrument["mirror_return"].shift(1)
    frame["mirror_turn"] = frame["mirror_return"] - frame["previous_mirror_return"]
    frame["participation_gap"] = frame["breadth_positive"] - frame["breadth_volume"]
    frame["surface_impulse_rollover"] = (
        frame["surface_median_acceleration"].fillna(0)
        + frame["acceleration_breadth_delta"].fillna(0)
    )
    return frame


def thresholds(training: pd.DataFrame) -> dict[str, float]:
    return {
        "return_p60": _q(training, "prior_5m_return_pct", 0.60),
        "return_p65": _q(training, "prior_5m_return_pct", 0.65),
        "breadth_p60": _q(training, "breadth_positive", 0.60),
        "breadth_p70": _q(training, "breadth_positive", 0.70),
        "dispersion_p70": _q(training, "surface_return_dispersion", 0.70),
        "volume_breadth_p50": _q(training, "breadth_volume", 0.50),
        "mirror_return_p40": _q(training, "mirror_return", 0.40),
        "mirror_turn_p55": _q(training, "mirror_turn", 0.55),
        "mass_shift_p70": _q(training, "directional_mass_shift", 0.70),
        "participation_gap_p65": _q(training, "participation_gap", 0.65),
    }


def mechanism_masks(frame: pd.DataFrame, cut: dict[str, float]) -> dict[str, pd.Series]:
    source_return = frame["prior_5m_return_pct"]
    breadth = frame["breadth_positive"]
    mirror_resilient = (
        (frame["mirror_return"] >= cut["mirror_return_p40"])
        & (frame["mirror_turn"] >= cut["mirror_turn_p55"])
    )
    broad_impulse = (source_return >= cut["return_p65"]) & (breadth >= cut["breadth_p60"])
    rollover = (
        (frame["return_acceleration"] <= 0)
        | (frame["breadth_delta"] <= 0)
        | (frame["acceleration_breadth_delta"] < 0)
    )
    return {
        "breadth_rollover_opposite_resilience": (
            broad_impulse
            & (frame["breadth_delta"] <= 0)
            & (frame["return_acceleration"] <= 0)
            & mirror_resilient
        ),
        "second_push_failure_opposite_turn": (
            (frame["previous_return"] > 0)
            & (source_return > 0)
            & (source_return < frame["previous_return"])
            & (breadth >= cut["breadth_p60"])
            & (frame["asymmetry_rollover"] < 0)
            & mirror_resilient
        ),
        "participation_exhaustion_opposite_turn": (
            broad_impulse
            & (frame["participation_gap"] >= cut["participation_gap_p65"])
            & (frame["breadth_volume"] <= cut["volume_breadth_p50"])
            & mirror_resilient
        ),
        "dispersion_spike_exhaustion": (
            broad_impulse
            & (frame["surface_return_dispersion"] >= cut["dispersion_p70"])
            & (frame["acceleration_breadth_delta"] < 0)
            & mirror_resilient
        ),
        "mass_migration_stall": (
            (frame["directional_mass_shift"] >= cut["mass_shift_p70"])
            & (breadth >= cut["breadth_p60"])
            & (frame["surface_median_acceleration"] < 0)
            & (frame["breadth_delta"] <= 0)
            & mirror_resilient
        ),
        "acceptance_failure_opposite_turn": (
            broad_impulse
            & (~frame["bar_acceptance"].fillna(False))
            & rollover
            & mirror_resilient
        ),
        "near_expiry_surface_exhaustion": (
            frame["days_to_expiry"].between(0, 2, inclusive="both")
            & broad_impulse
            & (breadth >= cut["breadth_p70"])
            & rollover
            & mirror_resilient
        ),
        "late_session_surface_exhaustion": (
            frame["minute_of_day"].between(780, 875, inclusive="both")
            & (source_return >= cut["return_p60"])
            & (breadth >= cut["breadth_p60"])
            & (frame["surface_impulse_rollover"] < 0)
            & mirror_resilient
        ),
    }


def source_eligibility(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["minute_of_day"].between(585, 875, inclusive="both")
        & frame["days_to_expiry"].between(0, 7, inclusive="both")
        & (frame["surface_count"] >= 3)
        & (frame["volume"] > 0)
        & frame["previous_return"].notna()
        & frame["mirror_return"].notna()
        & frame["mirror_turn"].notna()
    )


def _mirror_lookup(frame: pd.DataFrame) -> pd.DataFrame:
    lookup = frame[
        [
            "session_id",
            "timestamp",
            "expiry_id",
            "strike",
            "option_type",
            "expired_instrument_key",
            "entry_price_next_open",
            "volume",
            "days_to_expiry",
            "minute_of_day",
        ]
    ].copy()
    lookup = lookup.rename(
        columns={
            "option_type": "target_option_type",
            "expired_instrument_key": "target_expired_instrument_key",
            "entry_price_next_open": "target_entry_price_next_open",
            "volume": "target_volume",
            "days_to_expiry": "target_days_to_expiry",
            "minute_of_day": "target_minute_of_day",
        }
    )
    return lookup.drop_duplicates(
        ["session_id", "timestamp", "expiry_id", "strike", "target_option_type"]
    )


def build_mirror_candidates(
    frame: pd.DataFrame,
    mask: pd.Series,
    mechanism: str,
    sessions: list[str],
) -> pd.DataFrame:
    source_columns = [
        "session_id",
        "timestamp",
        "expiry_id",
        "strike",
        "option_type",
        "expired_instrument_key",
        "entry_price_next_open",
        "days_to_expiry",
        "minute_of_day",
        "prior_5m_return_pct",
        "previous_return",
        "return_acceleration",
        "breadth_positive",
        "breadth_delta",
        "breadth_acceleration",
        "acceleration_breadth_delta",
        "breadth_volume",
        "surface_median_return",
        "surface_median_acceleration",
        "surface_return_dispersion",
        "directional_mass_shift",
        "mirror_return",
        "mirror_acceleration",
        "mirror_turn",
        "option_asymmetry",
        "asymmetry_rollover",
        "participation_gap",
    ]
    source = frame.loc[
        mask & source_eligibility(frame) & frame["session_id"].isin(sessions),
        source_columns,
    ].copy()
    if source.empty:
        return source
    source["target_option_type"] = source["option_type"].map({"CE": "PE", "PE": "CE"})
    source = source.rename(
        columns={
            "option_type": "source_option_type",
            "expired_instrument_key": "source_expired_instrument_key",
            "entry_price_next_open": "source_entry_price_next_open",
            "days_to_expiry": "source_days_to_expiry",
            "minute_of_day": "source_minute_of_day",
        }
    )
    candidates = source.merge(
        _mirror_lookup(frame),
        on=["session_id", "timestamp", "expiry_id", "strike", "target_option_type"],
        how="inner",
        validate="many_to_one",
    )
    candidates = candidates.loc[
        candidates["target_entry_price_next_open"].between(30.0, 300.0, inclusive="both")
        & candidates["source_entry_price_next_open"].between(30.0, 500.0, inclusive="both")
        & (candidates["target_volume"] > 0)
        & candidates["target_days_to_expiry"].between(0, 7, inclusive="both")
    ].copy()
    if candidates.empty:
        return candidates
    candidates["mechanism"] = mechanism
    candidates["premium_distance"] = (candidates["target_entry_price_next_open"] - 120.0).abs()
    candidates["exhaustion_score"] = (
        candidates["prior_5m_return_pct"].fillna(0)
        + 2.0 * candidates["breadth_positive"].fillna(0)
        - candidates["breadth_delta"].fillna(0)
        - candidates["return_acceleration"].fillna(0)
        + candidates["mirror_turn"].fillna(0)
        - candidates["asymmetry_rollover"].fillna(0)
    )
    best = candidates.groupby(["session_id", "timestamp"], observed=True)["exhaustion_score"].transform("max")
    candidates = candidates.loc[candidates["exhaustion_score"].eq(best)]
    candidates = candidates.sort_values(
        ["session_id", "timestamp", "exhaustion_score", "premium_distance", "target_expired_instrument_key"],
        ascending=[True, True, False, True, True],
        kind="mergesort",
    ).drop_duplicates(["session_id", "timestamp"], keep="first")

    selected_parts: list[pd.DataFrame] = []
    for _, group in candidates.groupby("session_id", sort=False, observed=True):
        selected: list[int] = []
        last_timestamp: pd.Timestamp | None = None
        for index, row in group.iterrows():
            timestamp = pd.Timestamp(row["timestamp"])
            if last_timestamp is not None:
                elapsed = (timestamp - last_timestamp).total_seconds() / 60.0
                if elapsed < MIN_SIGNAL_SEPARATION_MINUTES:
                    continue
            selected.append(index)
            last_timestamp = timestamp
            if len(selected) >= MAX_SIGNALS_PER_SESSION:
                break
        selected_parts.append(group.loc[selected])
    if not selected_parts:
        return candidates.iloc[0:0]
    return pd.concat(selected_parts, ignore_index=False).sort_values(
        ["session_id", "timestamp"], kind="mergesort"
    )


def target_signals(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return candidates.copy()
    signals = candidates.copy()
    signals["expired_instrument_key"] = signals["target_expired_instrument_key"]
    signals["entry_price_next_open"] = signals["target_entry_price_next_open"]
    signals["option_type"] = signals["target_option_type"]
    signals["days_to_expiry"] = signals["target_days_to_expiry"]
    signals["minute_of_day"] = signals["target_minute_of_day"]
    return signals


def source_control_signals(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return candidates.copy()
    signals = candidates.copy()
    signals["expired_instrument_key"] = signals["source_expired_instrument_key"]
    signals["entry_price_next_open"] = signals["source_entry_price_next_open"]
    signals["option_type"] = signals["source_option_type"]
    signals["days_to_expiry"] = signals["source_days_to_expiry"]
    signals["minute_of_day"] = signals["source_minute_of_day"]
    return signals


def adjusted_cluster_ci_low(trades: pd.DataFrame, family_count: int) -> float | None:
    return leadership_mod.cluster_bootstrap_ci_low(trades, family_count)


def control_gate(primary: metrics_mod.Metrics, delayed: metrics_mod.Metrics, source: metrics_mod.Metrics) -> bool:
    if primary.mean_return_pct is None:
        return False
    delayed_ok = (
        delayed.trades >= max(10, int(primary.trades * 0.50))
        and delayed.mean_return_pct is not None
        and primary.mean_return_pct >= delayed.mean_return_pct + 0.20
    )
    source_ok = (
        source.trades >= max(10, int(primary.trades * 0.70))
        and source.mean_return_pct is not None
        and primary.mean_return_pct >= source.mean_return_pct + 0.50
    )
    return delayed_ok and source_ok


def oof_gate(metric: metrics_mod.Metrics, ci_low: float | None) -> bool:
    return bool(
        metric.trades >= MIN_OOF_TRADES
        and metric.sessions >= MIN_OOF_SESSIONS
        and metric.profit_factor is not None
        and metric.profit_factor >= 1.25
        and metric.mean_return_pct is not None
        and metric.mean_return_pct > 0
        and metric.median_return_pct is not None
        and metric.median_return_pct >= 0
        and metric.remove_top_five_profit_factor is not None
        and metric.remove_top_five_profit_factor >= 1.05
        and metric.stress_profit_factor is not None
        and metric.stress_profit_factor >= 1.00
        and ci_low is not None
        and ci_low > 0
        and metric.total_folds == 5
        and metric.positive_folds >= 4
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.20)
        and (metric.top_five_session_profit_share is None or metric.top_five_session_profit_share <= 0.30)
    )


def validation_gate(metric: metrics_mod.Metrics, ci_low: float | None) -> bool:
    return bool(
        metric.trades >= MIN_VALIDATION_TRADES
        and metric.sessions >= MIN_VALIDATION_SESSIONS
        and metric.profit_factor is not None
        and metric.profit_factor >= 1.20
        and metric.mean_return_pct is not None
        and metric.mean_return_pct > 0
        and metric.median_return_pct is not None
        and metric.median_return_pct > 0
        and metric.remove_top_five_profit_factor is not None
        and metric.remove_top_five_profit_factor >= 1.00
        and metric.stress_profit_factor is not None
        and metric.stress_profit_factor >= 1.00
        and ci_low is not None
        and ci_low > 0
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.25)
        and (metric.top_five_session_profit_share is None or metric.top_five_session_profit_share <= 0.45)
    )


def _attach(signals: pd.DataFrame, causal: pd.DataFrame, fold_id: str) -> pd.DataFrame:
    return horizon_mod.attach_exact_horizon(signals, causal, EXIT_HORIZON_MINUTES, fold_id)


def _write_ledger(frames: list[pd.DataFrame], path: Path) -> None:
    if not frames:
        return
    ledger = pd.concat(frames, ignore_index=True, sort=False)
    keep = [
        "partition",
        "control",
        "fold_id",
        "mechanism",
        "session_id",
        "timestamp",
        "exit_timestamp",
        "expired_instrument_key",
        "expiry_id",
        "option_type",
        "strike",
        "entry_price_next_open",
        "exit_close",
        "gross_return_pct",
        "net_return_pct",
        "stress_return_pct",
        "label_horizon_minutes",
        "source_option_type",
        "target_option_type",
        "source_expired_instrument_key",
        "target_expired_instrument_key",
        "prior_5m_return_pct",
        "previous_return",
        "return_acceleration",
        "breadth_positive",
        "breadth_delta",
        "breadth_volume",
        "surface_return_dispersion",
        "mirror_return",
        "mirror_turn",
        "asymmetry_rollover",
        "days_to_expiry",
        "minute_of_day",
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

    causal = prepare_causal(event_path)
    partitions = splitmod.partition_sessions(causal)
    folds = splitmod.expanding_folds(partitions["research"])
    contract = {
        "schema_version": "surface_exhaustion_mirror_reversal_v1",
        "hypothesis": "broad_source_option_impulse_exhaustion_precedes_same_strike_opposite_option_reversal",
        "mechanisms": list(MECHANISMS),
        "mechanism_count": len(MECHANISMS),
        "cumulative_mechanisms_in_all_adaptive_campaigns": CUMULATIVE_MECHANISM_COUNT,
        "multiplicity_policy": "session_cluster_bootstrap_lower_quantile_0_05_divided_by_2_times_39",
        "entry": "next_same_contract_open_of_opposite_option_after_completed_signal_candle",
        "exit_horizon_minutes": EXIT_HORIZON_MINUTES,
        "maximum_signals_per_session": MAX_SIGNALS_PER_SESSION,
        "minimum_signal_separation_minutes": MIN_SIGNAL_SEPARATION_MINUTES,
        "research_sessions": len(partitions["research"]),
        "validation_sessions": len(partitions["validation"]),
        "master_holdout_sessions": len(partitions["master_holdout"]),
        "master_holdout_policy": "latest_15pct_sessions_sealed_and_never_materialized",
        "normal_cost_pct": metrics_mod.NORMAL_COST_PCT,
        "stress_cost_pct": metrics_mod.STRESS_COST_PCT,
        "controls": ["same_source_contract_continuation", "opposite_contract_entry_delayed_five_minutes"],
        "research_only": True,
        "allowed_for_live_execution": False,
    }
    contract["semantic_sha256"] = semantic_hash(contract)
    stable_json(out / "frozen_contract.json", contract)
    stable_json(
        out / "session_partitions.json",
        {
            "research": partitions["research"],
            "validation": partitions["validation"],
            "master_holdout_count": len(partitions["master_holdout"]),
            "master_holdout_sha256": semantic_hash(partitions["master_holdout"]),
            "master_holdout_sessions_redacted": True,
        },
    )

    primary_ledgers: dict[str, list[pd.DataFrame]] = {name: [] for name in MECHANISMS}
    delayed_ledgers: dict[str, list[pd.DataFrame]] = {name: [] for name in MECHANISMS}
    source_ledgers: dict[str, list[pd.DataFrame]] = {name: [] for name in MECHANISMS}
    thresholds_by_fold: list[dict[str, Any]] = []
    evidence_frames: list[pd.DataFrame] = []

    for training_sessions, testing_sessions, fold_id in folds:
        training = causal.loc[causal["session_id"].isin(training_sessions)]
        testing = causal.loc[causal["session_id"].isin(testing_sessions)]
        cut = thresholds(training)
        thresholds_by_fold.append({"fold_id": fold_id, "training_sessions": len(training_sessions), "thresholds": cut})
        masks = mechanism_masks(testing, cut)
        for mechanism in MECHANISMS:
            candidates = build_mirror_candidates(testing, masks[mechanism], mechanism, testing_sessions)
            target = target_signals(candidates)
            source = source_control_signals(candidates)
            delayed_target = fixed_delay.shift_signal_entry(target, testing, 5)
            primary = _attach(target, testing, fold_id)
            delayed = _attach(delayed_target, testing, fold_id)
            source_control = _attach(source, testing, fold_id)
            if not primary.empty:
                primary["mechanism"] = mechanism
                primary_ledgers[mechanism].append(primary)
            if not delayed.empty:
                delayed["mechanism"] = mechanism + "__delayed_target_control"
                delayed_ledgers[mechanism].append(delayed)
            if not source_control.empty:
                source_control["mechanism"] = mechanism + "__source_continuation_control"
                source_ledgers[mechanism].append(source_control)
    stable_json(out / "fold_thresholds.json", thresholds_by_fold)

    oof_records: list[dict[str, Any]] = []
    survivors: list[tuple[str, metrics_mod.Metrics, float]] = []
    for mechanism in MECHANISMS:
        primary = pd.concat(primary_ledgers[mechanism], ignore_index=True, sort=False) if primary_ledgers[mechanism] else pd.DataFrame()
        delayed = pd.concat(delayed_ledgers[mechanism], ignore_index=True, sort=False) if delayed_ledgers[mechanism] else pd.DataFrame()
        source = pd.concat(source_ledgers[mechanism], ignore_index=True, sort=False) if source_ledgers[mechanism] else pd.DataFrame()
        primary_metric = metrics_mod.calculate_metrics(primary)
        delayed_metric = metrics_mod.calculate_metrics(delayed)
        source_metric = metrics_mod.calculate_metrics(source)
        ci_low = adjusted_cluster_ci_low(primary, CUMULATIVE_MECHANISM_COUNT)
        economic_pass = oof_gate(primary_metric, ci_low)
        controls_pass = control_gate(primary_metric, delayed_metric, source_metric) if economic_pass else False
        passed = economic_pass and controls_pass
        oof_records.append(
            {
                "mechanism": mechanism,
                **asdict(primary_metric),
                "multiplicity_adjusted_cluster_bootstrap_ci_low": ci_low,
                "delayed_target_control": asdict(delayed_metric),
                "source_continuation_control": asdict(source_metric),
                "economic_gate": economic_pass,
                "control_gate": controls_pass,
                "oof_gate": passed,
            }
        )
        if not primary.empty:
            evidence_frames.append(primary.assign(partition="research_oof", control="primary_opposite_option"))
        if not delayed.empty:
            evidence_frames.append(delayed.assign(partition="research_oof", control="delayed_target_5m"))
        if not source.empty:
            evidence_frames.append(source.assign(partition="research_oof", control="source_contract_continuation"))
        if passed and ci_low is not None:
            survivors.append((mechanism, primary_metric, ci_low))

    survivors = sorted(
        survivors,
        key=lambda item: (
            item[2],
            item[1].remove_top_five_profit_factor or -math.inf,
            item[1].trades,
            item[0],
        ),
        reverse=True,
    )[:1]
    survivor_names = [name for name, _, _ in survivors]
    stable_json(out / "oof_screen.json", {"records": oof_records, "validation_survivors_frozen": survivor_names})

    validation_records: list[dict[str, Any]] = []
    validation_survivors: list[str] = []
    if survivor_names:
        final_cut = thresholds(causal.loc[causal["session_id"].isin(partitions["research"])])
        validation = causal.loc[causal["session_id"].isin(partitions["validation"])]
        masks = mechanism_masks(validation, final_cut)
        for mechanism in survivor_names:
            candidates = build_mirror_candidates(validation, masks[mechanism], mechanism, partitions["validation"])
            target = target_signals(candidates)
            source = source_control_signals(candidates)
            delayed_target = fixed_delay.shift_signal_entry(target, validation, 5)
            primary = _attach(target, validation, "validation")
            delayed = _attach(delayed_target, validation, "validation")
            source_control = _attach(source, validation, "validation")
            primary_metric = metrics_mod.calculate_metrics(primary)
            delayed_metric = metrics_mod.calculate_metrics(delayed)
            source_metric = metrics_mod.calculate_metrics(source_control)
            ci_low = adjusted_cluster_ci_low(primary, 1)
            economic_pass = validation_gate(primary_metric, ci_low)
            controls_pass = control_gate(primary_metric, delayed_metric, source_metric) if economic_pass else False
            passed = economic_pass and controls_pass
            validation_records.append(
                {
                    "mechanism": mechanism,
                    **asdict(primary_metric),
                    "session_cluster_bootstrap_ci_low": ci_low,
                    "delayed_target_control": asdict(delayed_metric),
                    "source_continuation_control": asdict(source_metric),
                    "economic_gate": economic_pass,
                    "control_gate": controls_pass,
                    "validation_gate": passed,
                }
            )
            if not primary.empty:
                evidence_frames.append(primary.assign(partition="validation", control="primary_opposite_option"))
            if not delayed.empty:
                evidence_frames.append(delayed.assign(partition="validation", control="delayed_target_5m"))
            if not source_control.empty:
                evidence_frames.append(source_control.assign(partition="validation", control="source_contract_continuation"))
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
        "PROMISING_HIGH_OCCURRENCE_SURFACE_EXHAUSTION_REVERSAL_MASTER_HOLDOUT_UNOPENED"
        if validation_survivors
        else (
            "NO_MULTIPLICITY_ADJUSTED_OOF_SURVIVOR_IN_SURFACE_EXHAUSTION_FAMILY"
            if not survivor_names
            else "SURFACE_EXHAUSTION_OOF_SURVIVOR_FAILED_VALIDATION"
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
    final["semantic_sha256"] = semantic_hash(final)
    stable_json(out / "final_decision.json", final)
    (research_dir / "RESULT.md").write_text(
        "# Surface Exhaustion Mirror Reversal V1\n\n"
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
