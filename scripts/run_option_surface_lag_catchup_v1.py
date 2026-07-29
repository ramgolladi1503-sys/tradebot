#!/usr/bin/env python3
"""Option-surface lag catch-up discovery.

This family buys a liquid CE or PE that is lagging its own expiry/wing surface
while the surface itself is moving positively and the opposite wing confirms the
direction. It tests cross-sectional underreaction rather than outright momentum
or capitulation reversal.

All thresholds use prior training sessions inside four expanding WFA folds.
Signal onset and contract selection occur before outcomes are attached. Latest
25% chronological holdout remains sealed until an OOF survivor is frozen.
Research only; no broker, paper or live action.
"""
from __future__ import annotations

import argparse
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scripts import run_inventory_absorption_transition_v1 as common
from scripts import run_option_surface_transition_discovery_v1 as base
from scripts.run_conditional_precursor_discrimination_v2 import PRIOR_REL, stable_json

OUT_REL = Path("runtime/research/option_surface_lag_catchup_v1")
RESEARCH_REL = Path("research/option_surface_lag_catchup_v1")
EVENT_FILE = "event_universe_5m.parquet"
NORMAL_COST_PCT = 0.10
STRESS_COST_PCT = 1.00
TARGET_PREMIUM = 150.0
MAX_SIGNALS_PER_SESSION = 2
COOLDOWN_MINUTES = 20

MECHANISMS = (
    "broad_surface_contract_lag",
    "accelerating_surface_lag",
    "liquid_laggard_catchup",
    "oi_supported_surface_lag",
    "mass_migration_surface_lag",
    "mirror_confirmed_surface_lag",
    "high_dispersion_deep_lag",
    "near_expiry_surface_lag",
    "midday_surface_lag",
    "late_session_surface_lag",
)


def q(frame: pd.DataFrame, column: str, quantile: float, default: float = 0.0) -> float:
    values = common._finite(frame[column]).dropna()
    return float(values.quantile(quantile)) if not values.empty else float(default)


def prepare(event_path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(event_path, columns=base.CAUSAL_COLUMNS)
    frame = base._surface_features(frame)
    frame = frame.loc[frame["minute_of_day"].between(585, 870, inclusive="both")].copy()
    surface_keys = ["session_id", "timestamp", "expiry_id", "option_type"]
    frame["surface_residual"] = frame["prior_5m_return_pct"] - frame["surface_median_return"]
    frame["surface_acceleration_residual"] = (
        frame["return_acceleration"] - frame["surface_median_acceleration"]
    )
    grouped = frame.groupby(surface_keys, sort=False, observed=True)
    frame["surface_residual_rank"] = grouped["surface_residual"].rank(method="average", pct=True)
    frame["surface_volume_rank"] = grouped["volume"].rank(method="average", pct=True)
    frame["surface_oi_rank"] = grouped["open_interest"].rank(method="average", pct=True)
    return frame


def thresholds(training: pd.DataFrame) -> dict[str, float]:
    return {
        "surface_ret60": q(training, "surface_median_return", 0.60),
        "surface_ret70": q(training, "surface_median_return", 0.70),
        "surface_acc60": q(training, "surface_median_acceleration", 0.60),
        "surface_acc70": q(training, "surface_median_acceleration", 0.70),
        "resid10": q(training, "surface_residual", 0.10),
        "resid20": q(training, "surface_residual", 0.20),
        "resid30": q(training, "surface_residual", 0.30),
        "ret20": q(training, "prior_5m_return_pct", 0.20),
        "ret40": q(training, "prior_5m_return_pct", 0.40),
        "vol50": q(training, "prior_5m_volume_ratio", 0.50, 1.0),
        "vol60": q(training, "prior_5m_volume_ratio", 0.60, 1.0),
        "oi60": q(training, "oi_change_ratio", 0.60),
        "oi70": q(training, "oi_change_ratio", 0.70),
        "breadth60": q(training, "breadth_positive", 0.60, 0.50),
        "breadth70": q(training, "breadth_positive", 0.70, 0.60),
        "bdelta60": q(training, "breadth_delta", 0.60),
        "mass60": q(training, "directional_mass_shift", 0.60),
        "mass70": q(training, "directional_mass_shift", 0.70),
        "disp60": q(training, "surface_return_dispersion", 0.60),
        "disp70": q(training, "surface_return_dispersion", 0.70),
    }


def masks(frame: pd.DataFrame, cut: dict[str, float]) -> dict[str, pd.Series]:
    surface = frame["surface_median_return"]
    sacc = frame["surface_median_acceleration"]
    residual = frame["surface_residual"]
    rank = frame["surface_residual_rank"]
    vrank = frame["surface_volume_rank"]
    ret = frame["prior_5m_return_pct"]
    vol = frame["prior_5m_volume_ratio"]
    oi = frame["oi_change_ratio"]
    breadth = frame["breadth_positive"]
    bdelta = frame["breadth_delta"]
    mass = frame["directional_mass_shift"]
    dispersion = frame["surface_return_dispersion"]
    mirror = frame["mirror_return"]
    macc = frame["mirror_acceleration"]

    positive_surface = (
        (surface >= cut["surface_ret60"])
        & (surface > 0)
        & (breadth >= max(0.55, cut["breadth60"]))
    )
    liquid_lag = (
        (residual <= cut["resid20"])
        & (ret >= cut["ret20"])
        & (vol >= cut["vol50"])
    )
    mirror_confirm = (mirror <= 0) & (macc <= 0)

    result = {
        "broad_surface_contract_lag": positive_surface & liquid_lag & mirror_confirm,
        "accelerating_surface_lag": (
            (surface > 0)
            & (sacc >= cut["surface_acc70"])
            & (residual <= cut["resid20"])
            & (ret >= cut["ret20"])
            & (bdelta >= cut["bdelta60"])
            & (vol >= cut["vol50"])
            & (mirror <= 0)
        ),
        "liquid_laggard_catchup": (
            positive_surface
            & (rank <= 0.25)
            & (vrank >= 0.50)
            & (ret <= surface)
            & (ret >= cut["ret20"])
            & mirror_confirm
        ),
        "oi_supported_surface_lag": (
            positive_surface
            & liquid_lag
            & (oi >= cut["oi70"])
            & (vol >= cut["vol60"])
            & (mirror <= 0)
        ),
        "mass_migration_surface_lag": (
            positive_surface
            & (residual <= cut["resid30"])
            & (ret >= cut["ret20"])
            & (mass >= cut["mass70"])
            & (vol >= cut["vol50"])
            & mirror_confirm
        ),
        "mirror_confirmed_surface_lag": (
            positive_surface
            & (residual <= cut["resid20"])
            & (ret >= cut["ret20"])
            & mirror_confirm
            & (frame["option_asymmetry"] > 0)
            & (vol >= cut["vol50"])
        ),
        "high_dispersion_deep_lag": (
            (surface > 0)
            & (sacc >= cut["surface_acc60"])
            & (dispersion >= cut["disp70"])
            & (residual <= cut["resid10"])
            & (ret >= cut["ret20"])
            & (vol >= cut["vol60"])
            & mirror_confirm
        ),
        "near_expiry_surface_lag": (
            positive_surface
            & liquid_lag
            & frame["days_to_expiry"].between(0, 2, inclusive="both")
            & (oi >= cut["oi60"])
            & mirror_confirm
        ),
        "midday_surface_lag": (
            positive_surface
            & liquid_lag
            & frame["minute_of_day"].between(660, 750, inclusive="both")
            & (sacc >= cut["surface_acc60"])
            & mirror_confirm
        ),
        "late_session_surface_lag": (
            positive_surface
            & liquid_lag
            & frame["minute_of_day"].between(751, 870, inclusive="both")
            & (sacc >= cut["surface_acc60"])
            & mirror_confirm
        ),
    }
    return {name: value.fillna(False) for name, value in result.items()}


def eligible(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["entry_price_next_open"].between(30.0, 300.0, inclusive="both")
        & frame["days_to_expiry"].between(0, 7, inclusive="both")
        & (frame["surface_count"] >= 4)
        & (frame["volume"] > 0)
        & frame["surface_residual"].notna()
        & frame["mirror_return"].notna()
    )


def onset(frame: pd.DataFrame, mask: pd.Series) -> pd.Series:
    prior = mask.groupby(frame["expired_instrument_key"], sort=False).shift(1, fill_value=False)
    return mask & ~prior


def select(frame: pd.DataFrame, mask: pd.Series, mechanism: str, sessions: list[str]) -> pd.DataFrame:
    candidates = frame.loc[
        onset(frame, mask) & eligible(frame) & frame["session_id"].isin(sessions)
    ].copy()
    if candidates.empty:
        return candidates
    candidates["mechanism"] = mechanism
    candidates["premium_distance"] = (candidates["entry_price_next_open"] - TARGET_PREMIUM).abs()
    candidates["score"] = (
        candidates["surface_median_return"].fillna(0)
        + candidates["surface_median_acceleration"].fillna(0)
        - 1.5 * candidates["surface_residual"].fillna(0)
        + 8.0 * candidates["breadth_delta"].fillna(0)
        + 0.5 * candidates["prior_5m_volume_ratio"].fillna(0)
        + 0.5 * candidates["oi_change_ratio"].fillna(0)
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
    lookup = causal[
        ["session_id", "timestamp", "expiry_id", "strike", "option_type", "expired_instrument_key", "entry_price_next_open"]
    ].drop_duplicates(["session_id", "timestamp", "expiry_id", "strike", "option_type"])
    source = signals[["session_id", "timestamp", "expiry_id", "strike", "option_type", "mechanism"]].copy()
    source["option_type"] = source["option_type"].map({"CE": "PE", "PE": "CE"})
    mirrored = source.merge(
        lookup,
        on=["session_id", "timestamp", "expiry_id", "strike", "option_type"],
        how="inner",
        validate="many_to_one",
    )
    return attach(mirrored, outcomes, "holdout_mirror") if not mirrored.empty else mirrored


def delayed_control(signals: pd.DataFrame, causal: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    source = signals[["expired_instrument_key", "timestamp", "mechanism"]].copy()
    source["timestamp"] = source["timestamp"] + pd.Timedelta(minutes=5)
    delayed = source.merge(
        causal.drop_duplicates(["expired_instrument_key", "timestamp"]),
        on=["expired_instrument_key", "timestamp"],
        how="inner",
        suffixes=("", "_causal"),
        validate="many_to_one",
    )
    return attach(delayed, outcomes, "holdout_delayed") if not delayed.empty else delayed


def leader_control(signals: pd.DataFrame, causal: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    if signals.empty:
        return signals.copy()
    keys = ["session_id", "timestamp", "expiry_id", "option_type"]
    source = signals[keys + ["mechanism"]].drop_duplicates(keys).copy()
    pool = causal.loc[
        eligible(causal),
        keys + [
            "expired_instrument_key",
            "entry_price_next_open",
            "surface_residual",
            "strike",
        ],
    ].copy()
    leaders = source.merge(pool, on=keys, how="inner", validate="one_to_many")
    if leaders.empty:
        return leaders
    leaders = leaders.sort_values(
        keys + ["surface_residual", "expired_instrument_key"],
        ascending=[True, True, True, True, False, True],
        kind="mergesort",
    ).drop_duplicates(keys, keep="first")
    return attach(leaders, outcomes, "holdout_surface_leader")


def oof_gate(metric: common.Metrics) -> bool:
    return bool(
        metric.trades >= 100
        and metric.sessions >= 70
        and metric.profit_factor is not None and metric.profit_factor >= 1.30
        and metric.mean_return_pct is not None and metric.mean_return_pct > 0
        and metric.median_return_pct is not None and metric.median_return_pct >= 0
        and metric.remove_top_five_profit_factor is not None and metric.remove_top_five_profit_factor >= 1.10
        and metric.stress_profit_factor is not None and metric.stress_profit_factor >= 1.05
        and metric.bootstrap_mean_ci_low is not None and metric.bootstrap_mean_ci_low > 0
        and metric.total_folds == 4 and metric.positive_folds >= 3
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.15)
        and (metric.largest_session_share is None or metric.largest_session_share <= 0.15)
    )


def holdout_gate(metric: common.Metrics) -> bool:
    return bool(
        metric.trades >= 30
        and metric.sessions >= 22
        and metric.profit_factor is not None and metric.profit_factor >= 1.20
        and metric.mean_return_pct is not None and metric.mean_return_pct > 0
        and metric.median_return_pct is not None and metric.median_return_pct >= 0
        and metric.remove_top_three_profit_factor is not None and metric.remove_top_three_profit_factor >= 1.05
        and metric.stress_profit_factor is not None and metric.stress_profit_factor >= 1.00
        and metric.total_halves == 2 and metric.positive_halves == 2
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.20)
        and (metric.largest_session_share is None or metric.largest_session_share <= 0.20)
    )


def control_gate(
    primary: common.Metrics,
    mirror: common.Metrics,
    delayed: common.Metrics,
    leader: common.Metrics,
) -> bool:
    mirror_rejected = bool(
        mirror.trades >= max(12, int(primary.trades * 0.50))
        and mirror.mean_return_pct is not None and mirror.mean_return_pct <= 0
        and (mirror.profit_factor is None or mirror.profit_factor <= 1.05)
    )
    delayed_degrades = bool(
        delayed.trades >= max(12, int(primary.trades * 0.50))
        and primary.mean_return_pct is not None and delayed.mean_return_pct is not None
        and primary.mean_return_pct > delayed.mean_return_pct
        and primary.profit_factor is not None and delayed.profit_factor is not None
        and primary.profit_factor >= delayed.profit_factor
    )
    lag_specific = bool(
        leader.trades >= max(12, int(primary.trades * 0.50))
        and primary.mean_return_pct is not None and leader.mean_return_pct is not None
        and primary.mean_return_pct > leader.mean_return_pct
        and primary.profit_factor is not None and leader.profit_factor is not None
        and primary.profit_factor >= leader.profit_factor
    )
    return mirror_rejected and delayed_degrades and lag_specific


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
        "schema_version": "option_surface_lag_catchup_v1",
        "mechanism_hypothesis": "liquid_contract_underreaction_to_confirmed_positive_same_wing_surface_transition",
        "mechanisms": list(MECHANISMS),
        "side": "BUY_CE_OR_PE_ONLY",
        "entry": "same_contract_open_exactly_one_minute_after_completed_signal",
        "outcome_horizon_minutes": 5,
        "premium_range": [30.0, 300.0],
        "days_to_expiry": [0, 7],
        "max_signals_per_session": MAX_SIGNALS_PER_SESSION,
        "cooldown_minutes": COOLDOWN_MINUTES,
        "normal_cost_pct": NORMAL_COST_PCT,
        "stress_cost_pct": STRESS_COST_PCT,
        "threshold_policy": "prior_training_session_quantiles_per_expanding_fold",
        "holdout_policy": "latest_25pct_unopened_until_oof_survivor_freeze",
        "controls": ["same_strike_opposite_wing", "five_minute_delay", "same_surface_leader"],
        "research_sessions": len(research_sessions),
        "holdout_sessions": len(holdout_sessions),
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

    oof_records: list[dict[str, Any]] = []
    oof_ledgers: list[pd.DataFrame] = []
    survivors: list[tuple[str, common.Metrics]] = []
    for mechanism in MECHANISMS:
        trades = pd.concat(ledgers[mechanism], ignore_index=True, sort=False) if ledgers[mechanism] else pd.DataFrame()
        metric = common.calculate_metrics(trades)
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
        ),
        reverse=True,
    )[:2]
    names = [name for name, _ in survivors]
    stable_json(out / "oof_screen.json", {"records": oof_records, "survivors_frozen_for_holdout": names, "holdout_outcomes_materialized": bool(names)})

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
            leader = leader_control(signals, holdout, holdout_outcomes)
            pm = common.calculate_metrics(primary)
            mm = common.calculate_metrics(mirror)
            dm = common.calculate_metrics(delayed)
            lm = common.calculate_metrics(leader)
            economic = holdout_gate(pm)
            controls = control_gate(pm, mm, dm, lm)
            passed = economic and controls
            holdout_records.append({
                "mechanism": mechanism,
                "primary": asdict(pm),
                "mirror_control": asdict(mm),
                "delayed_control": asdict(dm),
                "surface_leader_control": asdict(lm),
                "holdout_economic_gate": economic,
                "control_gate": controls,
                "holdout_gate": passed,
            })
            for partition, ledger in (
                ("holdout_primary", primary),
                ("holdout_mirror", mirror),
                ("holdout_delayed", delayed),
                ("holdout_surface_leader", leader),
            ):
                if not ledger.empty:
                    holdout_ledgers.append(ledger.assign(partition=partition))
            if passed:
                validated.append(mechanism)
    stable_json(out / "holdout_screen.json", {"records": holdout_records, "validated_candidates": validated, "holdout_outcomes_materialized": bool(names)})

    all_ledgers = oof_ledgers + holdout_ledgers
    if all_ledgers:
        pd.concat(all_ledgers, ignore_index=True, sort=False).to_csv(out / "trade_ledger.csv", index=False)

    verdict = (
        "STRUCTURAL_EDGE_FOUND_OPTION_SURFACE_LAG_CATCHUP_CANDLE_PROXY"
        if validated
        else ("NO_OOF_SURVIVOR_IN_OPTION_SURFACE_LAG_FAMILY" if not names else "OOF_SURVIVORS_FAILED_HOLDOUT_OR_CONTROLS")
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
        "# Option-Surface Lag Catch-Up V1\n\n"
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
