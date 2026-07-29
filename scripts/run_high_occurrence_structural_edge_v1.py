#!/usr/bin/env python3
"""High-occurrence structural edge campaign V1.

Distinct from the late-day CE inventory rebound. Tests predeclared, moderate-frequency
option-surface transitions with expanding chronological WFA and untouched holdout.
Research only; no trading authorization.
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

from scripts import run_extreme_option_pressure_discovery_v2 as research
from scripts import run_option_surface_transition_discovery_v1 as base
from scripts.run_conditional_precursor_discrimination_v2 import PRIOR_REL, stable_json

OUT_REL = Path("runtime/research/high_occurrence_structural_edge_v1")
RESEARCH_REL = Path("research/high_occurrence_structural_edge_v1")
EVENT_FILE = "event_universe_5m.parquet"
MECHANISMS = (
    "surface_breadth_impulse_continuation",
    "surface_breadth_exhaustion_rebound",
    "compression_breadth_release",
    "cross_wing_absorption_rebound",
    "surface_consensus_continuation",
    "failed_extension_reversal",
    "underreaction_with_participation",
    "midday_acceptance_break",
)


def _q(frame: pd.DataFrame, column: str, q: float, default: float = 0.0) -> float:
    values = pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    return float(values.quantile(q)) if not values.empty else default


def thresholds(training: pd.DataFrame) -> dict[str, float]:
    abs_ret = pd.to_numeric(training["prior_5m_return_pct"], errors="coerce").abs().dropna()
    return {
        "ret_p30": _q(training, "prior_5m_return_pct", 0.30),
        "ret_p40": _q(training, "prior_5m_return_pct", 0.40),
        "ret_p60": _q(training, "prior_5m_return_pct", 0.60),
        "ret_p70": _q(training, "prior_5m_return_pct", 0.70),
        "abs_ret_p40": float(abs_ret.quantile(0.40)) if not abs_ret.empty else 0.0,
        "volume_p60": _q(training, "prior_5m_volume_ratio", 0.60, 1.0),
        "volume_p70": _q(training, "prior_5m_volume_ratio", 0.70, 1.0),
        "accel_p30": _q(training, "return_acceleration", 0.30),
        "accel_p70": _q(training, "return_acceleration", 0.70),
        "breadth_delta_p30": _q(training, "breadth_delta", 0.30),
        "breadth_delta_p70": _q(training, "breadth_delta", 0.70),
        "dispersion_p40": _q(training, "surface_return_dispersion", 0.40),
        "range_p30": _q(training, "prior_10m_range_pct", 0.30),
        "asym_p30": _q(training, "option_asymmetry", 0.30),
        "asym_p70": _q(training, "option_asymmetry", 0.70),
        "mass_p60": _q(training, "directional_mass_shift", 0.60),
        "mass_p40": _q(training, "directional_mass_shift", 0.40),
        "oi_p60": _q(training, "oi_change_ratio", 0.60),
    }


def masks(frame: pd.DataFrame, c: dict[str, float]) -> dict[str, pd.Series]:
    ret = frame["prior_5m_return_pct"]
    vol = frame["prior_5m_volume_ratio"]
    breadth = frame["breadth_positive"]
    bdelta = frame["breadth_delta"]
    accel = frame["return_acceleration"]
    mirror = frame["mirror_return"]
    asym = frame["option_asymmetry"]
    median = frame["surface_median_return"]
    dispersion = frame["surface_return_dispersion"]
    mass = frame["directional_mass_shift"]
    oi = frame["oi_change_ratio"]
    return {
        "surface_breadth_impulse_continuation": (
            (ret >= c["ret_p60"]) & (vol >= c["volume_p60"]) & (breadth >= 0.60)
            & (bdelta >= c["breadth_delta_p70"]) & (asym >= c["asym_p70"])
        ),
        "surface_breadth_exhaustion_rebound": (
            (ret <= c["ret_p40"]) & (vol >= c["volume_p60"]) & (breadth <= 0.40)
            & (accel <= c["accel_p30"]) & (mirror > 0)
        ),
        "compression_breadth_release": (
            (frame["prior_10m_range_pct"] <= c["range_p30"]) & (vol >= c["volume_p60"])
            & (accel >= c["accel_p70"]) & (bdelta >= c["breadth_delta_p70"])
            & (dispersion >= c["dispersion_p40"])
        ),
        "cross_wing_absorption_rebound": (
            (ret < 0) & (mirror > 0) & (asym <= c["asym_p30"])
            & (vol >= c["volume_p60"]) & (mass <= c["mass_p40"])
        ),
        "surface_consensus_continuation": (
            (median > 0) & (breadth >= 0.67) & (dispersion <= c["dispersion_p40"])
            & (vol >= c["volume_p60"]) & (mass >= c["mass_p60"])
        ),
        "failed_extension_reversal": (
            (ret <= c["ret_p30"]) & (accel >= c["accel_p70"]) & (mirror > 0)
            & (bdelta >= c["breadth_delta_p70"]) & (asym <= c["asym_p30"])
        ),
        "underreaction_with_participation": (
            (ret.abs() <= c["abs_ret_p40"]) & (vol >= c["volume_p70"])
            & (oi >= c["oi_p60"]) & (breadth >= 0.55) & (bdelta > 0)
        ),
        "midday_acceptance_break": (
            frame["minute_of_day"].between(660, 810, inclusive="both")
            & (ret >= c["ret_p60"]) & (vol >= c["volume_p60"])
            & (breadth >= 0.60) & (mass >= c["mass_p60"])
        ),
    }


def eligible(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["entry_price_next_open"].between(30.0, 300.0, inclusive="both")
        & frame["minute_of_day"].between(585, 885, inclusive="both")
        & frame["days_to_expiry"].between(0, 7, inclusive="both")
        & (frame["surface_count"] >= 3)
        & (frame["volume"] > 0)
        & frame["previous_return"].notna()
    )


def select_independent(frame: pd.DataFrame, mask: pd.Series, mechanism: str, sessions: list[str]) -> pd.DataFrame:
    candidates = frame.loc[mask & eligible(frame) & frame["session_id"].isin(sessions)].copy()
    if candidates.empty:
        return candidates
    candidates["mechanism"] = mechanism
    candidates["score"] = (
        candidates["breadth_delta"].abs().fillna(0)
        + candidates["return_acceleration"].abs().fillna(0)
        + candidates["option_asymmetry"].abs().fillna(0)
        + 0.25 * candidates["prior_5m_volume_ratio"].fillna(0)
    )
    selected: list[pd.Series] = []
    for _, session in candidates.sort_values(["session_id", "timestamp", "score"], ascending=[True, True, False], kind="mergesort").groupby("session_id", observed=True):
        kept_times: list[pd.Timestamp] = []
        for _, row in session.iterrows():
            ts = pd.Timestamp(row["timestamp"])
            if all(abs((ts - prior).total_seconds()) >= 1800 for prior in kept_times):
                selected.append(row)
                kept_times.append(ts)
            if len(kept_times) == 2:
                break
    return pd.DataFrame(selected).reset_index(drop=True) if selected else candidates.iloc[0:0].copy()


def oof_gate(m: research.Metrics, trades: pd.DataFrame) -> bool:
    sessions = trades["session_id"].nunique() if not trades.empty else 0
    return bool(
        m.trades >= 60 and sessions >= 45 and m.profit_factor is not None and m.profit_factor >= 1.35
        and m.mean_return_pct is not None and m.mean_return_pct > 0
        and m.median_return_pct is not None and m.median_return_pct > 0
        and m.remove_top_two_profit_factor is not None and m.remove_top_two_profit_factor >= 1.15
        and m.stress_profit_factor is not None and m.stress_profit_factor >= 1.10
        and m.bootstrap_mean_ci_low is not None and m.bootstrap_mean_ci_low > 0
        and m.total_folds == 4 and m.positive_folds >= 3
        and (m.largest_winner_share is None or m.largest_winner_share <= 0.20)
    )


def holdout_gate(m: research.Metrics, trades: pd.DataFrame) -> bool:
    sessions = trades["session_id"].nunique() if not trades.empty else 0
    return bool(
        m.trades >= 20 and sessions >= 15 and m.profit_factor is not None and m.profit_factor >= 1.20
        and m.mean_return_pct is not None and m.mean_return_pct > 0
        and m.median_return_pct is not None and m.median_return_pct >= 0
        and m.remove_top_two_profit_factor is not None and m.remove_top_two_profit_factor >= 1.05
        and m.stress_profit_factor is not None and m.stress_profit_factor >= 1.00
        and (m.largest_winner_share is None or m.largest_winner_share <= 0.25)
    )


def semantic_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


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

    causal = research.prepare_causal(event_path)
    research_sessions, holdout_sessions = research.research_holdout_sessions(causal)
    folds = research.expanding_folds(research_sessions)
    outcomes = base._load_outcomes(event_path, base._raw_sessions(causal, research_sessions))

    contract = {
        "schema_version": "high_occurrence_structural_edge_v1",
        "mechanisms": list(MECHANISMS),
        "threshold_policy": "fixed_quantiles_recomputed_from_prior_fold_sessions_only",
        "selection": "maximum_two_signals_per_session_with_30_minute_cooldown",
        "research_sessions": len(research_sessions),
        "holdout_sessions": len(holdout_sessions),
        "normal_cost_pct": research.NORMAL_COST_PCT,
        "stress_cost_pct": research.STRESS_COST_PCT,
        "holdout_policy": "sealed_until_oof_survivor_freeze",
        "research_only": True,
        "allowed_for_live_execution": False,
    }
    contract["semantic_sha256"] = semantic_hash(contract)
    stable_json(out / "frozen_contract.json", contract)

    ledgers: dict[str, list[pd.DataFrame]] = {m: [] for m in MECHANISMS}
    threshold_records = []
    for train_sessions, test_sessions, fold_id in folds:
        train = causal.loc[causal["session_id"].isin(train_sessions)]
        test = causal.loc[causal["session_id"].isin(test_sessions)]
        cut = thresholds(train)
        threshold_records.append({"fold_id": fold_id, "thresholds": cut})
        mm = masks(test, cut)
        for mechanism in MECHANISMS:
            signals = select_independent(test, mm[mechanism], mechanism, test_sessions)
            trades = research.attach(signals, outcomes, fold_id)
            if not trades.empty:
                ledgers[mechanism].append(trades)
    stable_json(out / "fold_thresholds.json", threshold_records)

    oof_records = []
    survivors = []
    all_ledgers = []
    for mechanism in MECHANISMS:
        trades = pd.concat(ledgers[mechanism], ignore_index=True, sort=False) if ledgers[mechanism] else pd.DataFrame()
        metric = research.calculate_metrics(trades)
        passed = oof_gate(metric, trades)
        oof_records.append({"mechanism": mechanism, "sessions": int(trades["session_id"].nunique()) if not trades.empty else 0, **asdict(metric), "oof_gate": passed})
        if not trades.empty:
            all_ledgers.append(trades.assign(partition="research_oof"))
        if passed:
            survivors.append((mechanism, metric))
    survivors = sorted(survivors, key=lambda x: (x[1].remove_top_two_profit_factor or -math.inf, x[1].trades), reverse=True)[:3]
    names = [x[0] for x in survivors]
    stable_json(out / "oof_screen.json", {"records": oof_records, "survivors_frozen_for_holdout": names, "holdout_opened": bool(names)})

    holdout_records = []
    validated = []
    if names:
        final_cut = thresholds(causal.loc[causal["session_id"].isin(research_sessions)])
        holdout = causal.loc[causal["session_id"].isin(holdout_sessions)]
        holdout_masks = masks(holdout, final_cut)
        holdout_outcomes = base._load_outcomes(event_path, base._raw_sessions(causal, holdout_sessions))
        for mechanism in names:
            signals = select_independent(holdout, holdout_masks[mechanism], mechanism, holdout_sessions)
            trades = research.attach(signals, holdout_outcomes, "holdout")
            metric = research.calculate_metrics(trades)
            passed = holdout_gate(metric, trades)
            holdout_records.append({"mechanism": mechanism, "sessions": int(trades["session_id"].nunique()) if not trades.empty else 0, **asdict(metric), "holdout_gate": passed})
            if not trades.empty:
                all_ledgers.append(trades.assign(partition="holdout"))
            if passed:
                validated.append(mechanism)
    stable_json(out / "holdout_screen.json", {"records": holdout_records, "validated_candidates": validated, "holdout_opened": bool(names)})

    if all_ledgers:
        pd.concat(all_ledgers, ignore_index=True, sort=False).to_csv(out / "trade_ledger.csv", index=False)

    verdict = "VALIDATED_HIGH_OCCURRENCE_CANDLE_PROXY_EDGE" if validated else ("NO_OOF_SURVIVOR_HIGH_OCCURRENCE_MECHANISMS" if not names else "HIGH_OCCURRENCE_MECHANISMS_FAILED_HOLDOUT")
    decision = {
        "principal_verdict": verdict,
        "validated_candidates": validated,
        "oof_survivors": names,
        "execution_certification": "BLOCKED_AUTHORITATIVE_TIMESTAMP_ALIGNED_SPREAD_MISSING",
        "research_only": True,
        "paper_or_live_authorized": False,
        "allowed_for_live_execution": False,
    }
    decision["semantic_sha256"] = semantic_hash(decision)
    stable_json(out / "final_decision.json", decision)
    (research_dir / "RESULT.md").write_text(f"# High-Occurrence Structural Edge V1\n\nPrincipal verdict: `{verdict}`\n\nValidated candidates: `{validated}`\n\nResearch only. No paper or live authorization.\n", encoding="utf-8")
    print(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
