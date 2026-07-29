#!/usr/bin/env python3
"""Observed option-state motif discovery V1.

Observe first, hypothesize second. This campaign mines recurring pre-outcome
option-state motifs from the earliest research slice, freezes only those observed
motif signatures, then validates them chronologically on later data. Research
only; no broker, paper, live, provider, order, or production action.
"""
from __future__ import annotations

import argparse
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scripts import run_compression_gamma_ignition_v1 as prior
from scripts import run_inventory_absorption_transition_v1 as common
from scripts import run_option_surface_transition_discovery_v1 as base
from scripts.run_conditional_precursor_discrimination_v2 import PRIOR_REL, stable_json

OUT_REL = Path("runtime/research/observed_option_state_motif_discovery_v1")
RESEARCH_REL = Path("research/observed_option_state_motif_discovery_v1")
EVENT_FILE = "event_universe_5m.parquet"
NORMAL_COST_PCT = 0.10
STRESS_COST_PCT = 1.00
MAX_OBSERVED_MOTIFS = 320
MAX_FROZEN_MOTIFS = 8
MAX_HOLDOUT_MOTIFS = 2


def q(frame: pd.DataFrame, column: str, quantile: float, default: float = 0.0) -> float:
    values = common._finite(frame[column]).dropna()
    return float(values.quantile(quantile)) if not values.empty else float(default)


def observation_cuts(observation: pd.DataFrame) -> dict[str, float]:
    abs_ret = common._finite(observation["prior_5m_return_pct"]).abs().dropna()
    return {
        "quiet_abs_ret": float(abs_ret.quantile(0.25)) if not abs_ret.empty else 0.01,
        "ret30": q(observation, "prior_5m_return_pct", 0.30),
        "ret70": q(observation, "prior_5m_return_pct", 0.70),
        "acc30": q(observation, "return_acceleration", 0.30),
        "acc70": q(observation, "return_acceleration", 0.70),
        "vol70": q(observation, "prior_5m_volume_ratio", 0.70, 1.0),
        "vol85": q(observation, "prior_5m_volume_ratio", 0.85, 1.0),
        "oi70": q(observation, "oi_change_ratio", 0.70),
        "breadth35": q(observation, "breadth_positive", 0.35, 0.35),
        "breadth65": q(observation, "breadth_positive", 0.65, 0.65),
        "disp35": q(observation, "surface_return_dispersion", 0.35),
        "disp70": q(observation, "surface_return_dispersion", 0.70),
        "range30": q(observation, "prior_10m_range_pct", 0.30),
        "range70": q(observation, "prior_10m_range_pct", 0.70),
        "asym30": q(observation, "option_asymmetry", 0.30),
        "asym70": q(observation, "option_asymmetry", 0.70),
    }


def motif_labels(frame: pd.DataFrame, cuts: dict[str, float]) -> pd.Series:
    premium = pd.cut(frame["entry_price_next_open"], [-math.inf, 60, 120, 180, math.inf], labels=["prem_low", "prem_mid", "prem_high", "prem_xhigh"]).astype("object")
    dte = pd.cut(frame["days_to_expiry"], [-math.inf, 0, 2, 7, math.inf], labels=["dte_0", "dte_1_2", "dte_3_7", "dte_far"]).astype("object")
    tod = pd.cut(frame["minute_of_day"], [-math.inf, 660, 780, math.inf], labels=["tod_early", "tod_mid", "tod_late"]).astype("object")

    ret = frame["prior_5m_return_pct"]
    ret_state = pd.Series("ret_mixed", index=frame.index, dtype="object")
    ret_state = ret_state.mask(ret.abs() <= max(cuts["quiet_abs_ret"], 0.01), "ret_quiet")
    ret_state = ret_state.mask(ret <= cuts["ret30"], "ret_down")
    ret_state = ret_state.mask(ret >= cuts["ret70"], "ret_up")

    acc = frame["return_acceleration"]
    acc_state = pd.Series("acc_flat", index=frame.index, dtype="object")
    acc_state = acc_state.mask(acc <= cuts["acc30"], "acc_falling")
    acc_state = acc_state.mask(acc >= cuts["acc70"], "acc_rising")

    vol = frame["prior_5m_volume_ratio"]
    vol_state = pd.Series("vol_calm", index=frame.index, dtype="object")
    vol_state = vol_state.mask(vol >= cuts["vol70"], "vol_active")
    vol_state = vol_state.mask(vol >= cuts["vol85"], "vol_shock")

    mirror = frame["mirror_return"]
    mirror_state = pd.Series("mirror_flat", index=frame.index, dtype="object")
    mirror_state = mirror_state.mask(mirror < 0, "mirror_down")
    mirror_state = mirror_state.mask(mirror > 0, "mirror_up")

    breadth = frame["breadth_positive"]
    breadth_state = pd.Series("breadth_mid", index=frame.index, dtype="object")
    breadth_state = breadth_state.mask(breadth <= cuts["breadth35"], "breadth_low")
    breadth_state = breadth_state.mask(breadth >= cuts["breadth65"], "breadth_high")

    dispersion = frame["surface_return_dispersion"]
    dispersion_state = pd.Series("disp_mid", index=frame.index, dtype="object")
    dispersion_state = dispersion_state.mask(dispersion <= cuts["disp35"], "disp_low")
    dispersion_state = dispersion_state.mask(dispersion >= cuts["disp70"], "disp_high")

    rng = frame["prior_10m_range_pct"]
    range_state = pd.Series("range_mid", index=frame.index, dtype="object")
    range_state = range_state.mask(rng <= cuts["range30"], "range_compressed")
    range_state = range_state.mask(rng >= cuts["range70"], "range_expanded")

    surface = frame["surface_median_return"]
    surface_state = pd.Series("surface_mixed", index=frame.index, dtype="object")
    surface_state = surface_state.mask(surface < 0, "surface_discount")
    surface_state = surface_state.mask(surface > 0, "surface_premium")

    oi_state = pd.Series(np.where(frame["oi_change_ratio"] >= cuts["oi70"], "oi_participating", "oi_neutral"), index=frame.index, dtype="object")
    asym = frame["option_asymmetry"]
    asym_state = pd.Series("asym_mixed", index=frame.index, dtype="object")
    asym_state = asym_state.mask(asym <= cuts["asym30"], "asym_against")
    asym_state = asym_state.mask(asym >= cuts["asym70"], "asym_for")

    return (
        frame["option_type"].astype(str)
        + "|" + premium.fillna("prem_unknown").astype(str)
        + "|" + dte.fillna("dte_unknown").astype(str)
        + "|" + tod.fillna("tod_unknown").astype(str)
        + "|" + ret_state.astype(str)
        + "|" + acc_state.astype(str)
        + "|" + vol_state.astype(str)
        + "|" + mirror_state.astype(str)
        + "|" + breadth_state.astype(str)
        + "|" + dispersion_state.astype(str)
        + "|" + range_state.astype(str)
        + "|" + surface_state.astype(str)
        + "|" + oi_state.astype(str)
        + "|" + asym_state.astype(str)
    )


def split_research_sessions(research_sessions: list[str]) -> tuple[list[str], list[list[str]]]:
    cut = max(40, int(len(research_sessions) * 0.50))
    observation = research_sessions[:cut]
    remaining = np.asarray(research_sessions[cut:], dtype=object)
    folds = [part.tolist() for part in np.array_split(remaining, 3) if len(part)]
    return observation, folds


def metric_score(metric: common.Metrics) -> float:
    return float((metric.remove_top_five_profit_factor or 0) + (metric.stress_profit_factor or 0) + 0.5 * (metric.profit_factor or 0) + 0.02 * (metric.mean_return_pct or 0) + 0.001 * metric.sessions)


def observation_gate(metric: common.Metrics) -> bool:
    return bool(metric.trades >= 35 and metric.sessions >= 25 and metric.profit_factor is not None and metric.profit_factor >= 1.20 and metric.mean_return_pct is not None and metric.mean_return_pct > 0 and metric.median_return_pct is not None and metric.median_return_pct >= 0 and metric.remove_top_five_profit_factor is not None and metric.remove_top_five_profit_factor >= 0.95 and metric.stress_profit_factor is not None and metric.stress_profit_factor >= 0.95 and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.25))


def validation_gate(metric: common.Metrics) -> bool:
    return bool(metric.trades >= 80 and metric.sessions >= 55 and metric.profit_factor is not None and metric.profit_factor >= 1.30 and metric.mean_return_pct is not None and metric.mean_return_pct > 0 and metric.median_return_pct is not None and metric.median_return_pct >= 0 and metric.remove_top_five_profit_factor is not None and metric.remove_top_five_profit_factor >= 1.10 and metric.stress_profit_factor is not None and metric.stress_profit_factor >= 1.05 and metric.bootstrap_mean_ci_low is not None and metric.bootstrap_mean_ci_low > 0 and metric.total_folds == 3 and metric.positive_folds >= 2 and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.18) and (metric.largest_session_share is None or metric.largest_session_share <= 0.18))


def holdout_gate(metric: common.Metrics) -> bool:
    return bool(metric.trades >= 20 and metric.sessions >= 16 and metric.profit_factor is not None and metric.profit_factor >= 1.20 and metric.mean_return_pct is not None and metric.mean_return_pct > 0 and metric.median_return_pct is not None and metric.median_return_pct >= 0 and metric.remove_top_three_profit_factor is not None and metric.remove_top_three_profit_factor >= 1.05 and metric.stress_profit_factor is not None and metric.stress_profit_factor >= 1.00 and metric.total_halves == 2 and metric.positive_halves == 2 and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.24) and (metric.largest_session_share is None or metric.largest_session_share <= 0.24))


def control_gate(primary: common.Metrics, mirror: common.Metrics, delayed: common.Metrics) -> bool:
    mirror_bad = mirror.trades >= max(8, int(primary.trades * 0.40)) and mirror.mean_return_pct is not None and mirror.mean_return_pct <= 0 and (mirror.profit_factor is None or mirror.profit_factor <= 1.05)
    delayed_bad = delayed.trades >= max(8, int(primary.trades * 0.40)) and primary.mean_return_pct is not None and delayed.mean_return_pct is not None and primary.mean_return_pct > delayed.mean_return_pct and primary.profit_factor is not None and delayed.profit_factor is not None and primary.profit_factor >= delayed.profit_factor
    return bool(mirror_bad and delayed_bad)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    root = parser.parse_args().repo_root.resolve()
    event_path = root / PRIOR_REL / EVENT_FILE
    out = root / OUT_REL
    research = root / RESEARCH_REL
    out.mkdir(parents=True, exist_ok=True)
    research.mkdir(parents=True, exist_ok=True)

    causal = prior.prepare(event_path)
    research_sessions, holdout_sessions = common.research_holdout_sessions(causal)
    observation_sessions, validation_folds = split_research_sessions(research_sessions)
    observation = causal.loc[causal["session_id"].isin(observation_sessions)].copy()
    cuts = observation_cuts(observation)
    causal["motif"] = motif_labels(causal, cuts)
    observation = causal.loc[causal["session_id"].isin(observation_sessions)].copy()
    observation_outcomes = base._load_outcomes(event_path, base._raw_sessions(causal, observation_sessions))

    contract = {
        "schema_version": "observed_option_state_motif_discovery_v1",
        "workflow": "observe_pre_outcome_motifs_first_freeze_then_chronological_validation",
        "entry": "same_contract_open_exactly_one_minute_after_completed_signal",
        "outcome_horizon_minutes": 5,
        "normal_cost_pct": NORMAL_COST_PCT,
        "stress_cost_pct": STRESS_COST_PCT,
        "observation_sessions": len(observation_sessions),
        "validation_fold_sessions": [len(fold) for fold in validation_folds],
        "holdout_sessions": len(holdout_sessions),
        "motif_feature_policy": "pre_outcome_option_state_buckets_from_observation_quantiles_only",
        "freeze_policy": "motif_signatures_selected_only_from_observation_slice_before_validation",
        "holdout_policy": "latest_25pct_unopened_until_validation_survivor_freeze",
        "research_only": True,
        "paper_or_live_authorized": False,
        "allowed_for_live_execution": False,
    }
    contract["semantic_sha256"] = common.semantic_hash(contract)
    stable_json(out / "frozen_contract.json", contract)
    stable_json(out / "observation_quantile_cuts.json", cuts)

    counts = observation.groupby("motif", observed=True).agg(rows=("motif", "size"), sessions=("session_id", "nunique")).reset_index()
    counts = counts.loc[(counts["rows"] >= 50) & (counts["sessions"] >= 25)]
    counts = counts.sort_values(["sessions", "rows", "motif"], ascending=[False, False, True], kind="mergesort").head(MAX_OBSERVED_MOTIFS)

    observation_records: list[dict[str, Any]] = []
    frozen_candidates: list[tuple[str, common.Metrics]] = []
    for motif in counts["motif"].tolist():
        signals = prior.select(observation, observation["motif"].eq(motif), motif, observation_sessions)
        trades = prior.attach(signals, observation_outcomes, "observation")
        metric = common.calculate_metrics(trades)
        passed = observation_gate(metric)
        observation_records.append({"motif": motif, **asdict(metric), "observation_gate": passed, "score": metric_score(metric)})
        if passed:
            frozen_candidates.append((motif, metric))
    frozen_candidates = sorted(frozen_candidates, key=lambda item: (metric_score(item[1]), item[1].sessions, item[1].trades, item[0]), reverse=True)[:MAX_FROZEN_MOTIFS]
    frozen_motifs = [motif for motif, _ in frozen_candidates]
    stable_json(out / "observation_screen.json", {"evaluated_motifs": observation_records, "frozen_motifs": frozen_motifs})

    validation_records: list[dict[str, Any]] = []
    validation_ledgers: list[pd.DataFrame] = []
    survivors: list[tuple[str, common.Metrics]] = []
    for motif in frozen_motifs:
        parts: list[pd.DataFrame] = []
        for fold_index, fold_sessions in enumerate(validation_folds, start=1):
            fold = causal.loc[causal["session_id"].isin(fold_sessions)]
            outcomes = base._load_outcomes(event_path, base._raw_sessions(causal, fold_sessions))
            signals = prior.select(fold, fold["motif"].eq(motif), motif, fold_sessions)
            trades = prior.attach(signals, outcomes, f"validation_{fold_index}")
            if not trades.empty:
                parts.append(trades)
        combined = pd.concat(parts, ignore_index=True, sort=False) if parts else pd.DataFrame()
        metric = common.calculate_metrics(combined)
        passed = validation_gate(metric)
        validation_records.append({"motif": motif, **asdict(metric), "validation_gate": passed, "score": metric_score(metric)})
        if not combined.empty:
            validation_ledgers.append(combined.assign(partition="research_validation"))
        if passed:
            survivors.append((motif, metric))
    survivors = sorted(survivors, key=lambda item: (metric_score(item[1]), item[1].sessions, item[1].trades, item[0]), reverse=True)[:MAX_HOLDOUT_MOTIFS]
    survivor_motifs = [motif for motif, _ in survivors]
    stable_json(out / "validation_screen.json", {"records": validation_records, "survivors_frozen_for_holdout": survivor_motifs, "holdout_outcomes_materialized": bool(survivor_motifs)})

    holdout_records: list[dict[str, Any]] = []
    holdout_ledgers: list[pd.DataFrame] = []
    validated: list[str] = []
    if survivor_motifs:
        holdout = causal.loc[causal["session_id"].isin(holdout_sessions)]
        holdout_outcomes = base._load_outcomes(event_path, base._raw_sessions(causal, holdout_sessions))
        for motif in survivor_motifs:
            signals = prior.select(holdout, holdout["motif"].eq(motif), motif, holdout_sessions)
            primary = prior.attach(signals, holdout_outcomes, "holdout")
            mirror = prior.mirror_control(signals, holdout, holdout_outcomes)
            delayed = prior.delayed_control(signals, holdout, holdout_outcomes)
            pm = common.calculate_metrics(primary)
            mm = common.calculate_metrics(mirror)
            dm = common.calculate_metrics(delayed)
            economic = holdout_gate(pm)
            controls = control_gate(pm, mm, dm)
            passed = economic and controls
            holdout_records.append({"motif": motif, "primary": asdict(pm), "mirror_control": asdict(mm), "delayed_control": asdict(dm), "holdout_economic_gate": economic, "control_gate": controls, "holdout_gate": passed})
            if not primary.empty:
                holdout_ledgers.append(primary.assign(partition="holdout_primary"))
            if not mirror.empty:
                holdout_ledgers.append(mirror.assign(partition="holdout_mirror"))
            if not delayed.empty:
                holdout_ledgers.append(delayed.assign(partition="holdout_delayed"))
            if passed:
                validated.append(motif)
    stable_json(out / "holdout_screen.json", {"records": holdout_records, "validated_motifs": validated, "holdout_outcomes_materialized": bool(survivor_motifs)})

    all_ledgers = validation_ledgers + holdout_ledgers
    if all_ledgers:
        pd.concat(all_ledgers, ignore_index=True, sort=False).to_csv(out / "trade_ledger.csv", index=False)

    verdict = "STRUCTURAL_EDGE_FOUND_OBSERVED_OPTION_STATE_MOTIF_CANDLE_PROXY" if validated else ("NO_OBSERVED_MOTIF_SURVIVED_VALIDATION" if not survivor_motifs else "OBSERVED_MOTIFS_FAILED_HOLDOUT_OR_CONTROLS")
    final = {
        "principal_verdict": verdict,
        "structural_edge_found": bool(validated),
        "frozen_observation_motifs": frozen_motifs,
        "validation_survivors": survivor_motifs,
        "holdout_survivors": validated,
        "holdout_outcomes_materialized": bool(survivor_motifs),
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
        "# Observed Option-State Motif Discovery V1\n\n"
        f"Principal verdict: `{verdict}`\n\n"
        f"Frozen observation motifs: `{frozen_motifs}`\n\n"
        f"Validation survivors: `{survivor_motifs}`\n\n"
        f"Holdout survivors: `{validated}`\n\n"
        f"Observation sessions: `{len(observation_sessions)}`; validation folds: `{[len(fold) for fold in validation_folds]}`; holdout sessions: `{len(holdout_sessions)}`.\n\n"
        "Historical five-minute OHLCV candle proxy only. No paper or live authorization.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
