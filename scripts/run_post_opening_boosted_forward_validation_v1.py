#!/usr/bin/env python3
"""Two-stage forward validation of the post-opening boosted candidate.

The 10:00 IST gate was discovered from development OOF diagnostics and is
therefore not treated as independent WFA evidence. This campaign freezes that
candidate, trains horizon/confidence/model only on the original research period,
then splits the previously unopened 98 chronological sessions into an initial
validation block and a final certification block. The certification block is not
materialized unless validation passes. No model, threshold, horizon or time gate
is changed after validation.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from scripts import run_inventory_absorption_transition_v1 as common
from scripts import run_multi_horizon_boosted_causal_discovery_v1 as mh
from scripts.run_conditional_precursor_discrimination_v2 import PRIOR_REL, stable_json

OUT_REL = Path("runtime/research/post_opening_boosted_forward_validation_v1")
RESEARCH_REL = Path("research/post_opening_boosted_forward_validation_v1")
EVENT_FILE = "event_universe_5m.parquet"
START_MINUTE_IST = 600
VALIDATION_FRACTION = 0.50
SEED = 20260729


def validation_gate(metric: common.Metrics) -> bool:
    return bool(
        metric.trades >= 30
        and metric.sessions >= 22
        and metric.profit_factor is not None and metric.profit_factor >= 1.25
        and metric.mean_return_pct is not None and metric.mean_return_pct > 0
        and metric.median_return_pct is not None and metric.median_return_pct >= 0
        and metric.remove_top_five_profit_factor is not None and metric.remove_top_five_profit_factor >= 1.05
        and metric.stress_profit_factor is not None and metric.stress_profit_factor >= 1.05
        and metric.total_halves == 2 and metric.positive_halves == 2
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.20)
        and (metric.largest_session_share is None or metric.largest_session_share <= 0.20)
    )


def certification_gate(metric: common.Metrics) -> bool:
    return bool(
        metric.trades >= 25
        and metric.sessions >= 18
        and metric.profit_factor is not None and metric.profit_factor >= 1.20
        and metric.mean_return_pct is not None and metric.mean_return_pct > 0
        and metric.median_return_pct is not None and metric.median_return_pct >= 0
        and metric.remove_top_three_profit_factor is not None and metric.remove_top_three_profit_factor >= 1.00
        and metric.stress_profit_factor is not None and metric.stress_profit_factor >= 1.00
        and metric.total_halves == 2 and metric.positive_halves == 2
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.25)
        and (metric.largest_session_share is None or metric.largest_session_share <= 0.25)
    )


def combined_gate(metric: common.Metrics) -> bool:
    return bool(
        metric.trades >= 60
        and metric.sessions >= 45
        and metric.profit_factor is not None and metric.profit_factor >= 1.25
        and metric.mean_return_pct is not None and metric.mean_return_pct > 0
        and metric.median_return_pct is not None and metric.median_return_pct >= 0
        and metric.remove_top_five_profit_factor is not None and metric.remove_top_five_profit_factor >= 1.10
        and metric.stress_profit_factor is not None and metric.stress_profit_factor >= 1.05
        and metric.bootstrap_mean_ci_low is not None and metric.bootstrap_mean_ci_low > 0
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.15)
        and (metric.largest_session_share is None or metric.largest_session_share <= 0.15)
    )


def degraded(primary: common.Metrics, control: common.Metrics) -> bool:
    return bool(
        control.trades >= max(12, int(primary.trades * 0.50))
        and primary.mean_return_pct is not None and control.mean_return_pct is not None
        and primary.mean_return_pct > control.mean_return_pct
        and primary.profit_factor is not None and control.profit_factor is not None
        and primary.profit_factor >= control.profit_factor
    )


def controls_gate(primary: common.Metrics, opposite: common.Metrics, delayed: common.Metrics, baseline: common.Metrics) -> bool:
    return degraded(primary, opposite) and degraded(primary, delayed) and degraded(primary, baseline)


def apply_frozen(frame: pd.DataFrame, fitted, medians: dict[str, float], threshold: float, horizon: int, fold_id: str) -> pd.DataFrame:
    return mh.select(frame, mh.predict(frame, fitted, medians), threshold, horizon, fold_id)


def control_bundle(signals: pd.DataFrame, frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        mh.opposite_control(signals, frame),
        mh.delayed_control(signals, frame),
        mh.baseline_control(signals, frame),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    root = parser.parse_args().repo_root.resolve()
    out = root / OUT_REL
    research_dir = root / RESEARCH_REL
    out.mkdir(parents=True, exist_ok=True)
    research_dir.mkdir(parents=True, exist_ok=True)

    decisions, source_audit = mh.prepare(root / PRIOR_REL / EVENT_FILE)
    decisions = decisions.loc[decisions["minute_of_day"].ge(START_MINUTE_IST)].copy()
    research_sessions, unopened_sessions = common.research_holdout_sessions(decisions)
    split = int(len(unopened_sessions) * VALIDATION_FRACTION)
    validation_sessions = unopened_sessions[:split]
    certification_sessions = unopened_sessions[split:]
    research = decisions.loc[decisions["session_id"].isin(research_sessions)].copy()
    validation = decisions.loc[decisions["session_id"].isin(validation_sessions)].copy()
    certification = decisions.loc[decisions["session_id"].isin(certification_sessions)].copy()

    contract: dict[str, Any] = {
        "schema_version": "post_opening_boosted_forward_validation_v1",
        "development_origin": "10am_gate_selected_after_inspection_of_parent_OOF_and_not_counted_as_independent_WFA",
        "start_minute_ist": START_MINUTE_IST,
        "entry": "same_contract_open_exactly_one_minute_after_completed_signal",
        "candidate_horizons_minutes": list(mh.HORIZONS),
        "candidate_confidence_quantiles": list(mh.QUANTILES),
        "model": "frozen_parent_HistGradientBoostingRegressor_configuration",
        "model_selection": "research_sessions_only_chronological_70_30_discovery_calibration",
        "training_objective": "return_after_1pct_total_friction",
        "validation_sessions": len(validation_sessions),
        "certification_sessions": len(certification_sessions),
        "certification_seal": "not_materialized_unless_validation_gate_passes",
        "no_retraining_after_validation": True,
        "research_only": True,
        "paper_or_live_authorized": False,
        "allowed_for_live_execution": False,
    }
    contract["semantic_sha256"] = common.semantic_hash(contract)
    stable_json(out / "frozen_contract.json", contract)
    stable_json(out / "source_audit.json", {
        **source_audit,
        "post_opening_decisions": int(len(decisions)),
        "post_opening_sessions": int(decisions["session_id"].nunique()),
        "research_first_session": research_sessions[0],
        "research_last_session": research_sessions[-1],
        "validation_first_session": validation_sessions[0],
        "validation_last_session": validation_sessions[-1],
        "certification_first_session": certification_sessions[0],
        "certification_last_session": certification_sessions[-1],
    })

    spec, calibration_records = mh.choose_spec(research, research_sessions, SEED)
    if spec is None:
        final = {
            "principal_verdict": "NO_RESEARCH_CALIBRATION_SPEC_POST_OPENING",
            "structural_edge_found": False,
            "validation_gate": False,
            "certification_materialized": False,
            "certification_gate": False,
            "allowed_for_live_execution": False,
        }
        final["semantic_sha256"] = common.semantic_hash(final)
        stable_json(out / "model_freeze.json", {"selected_spec": None, "calibration_records": calibration_records})
        stable_json(out / "validation_screen.json", {})
        stable_json(out / "certification_screen.json", {})
        stable_json(out / "final_decision.json", final)
        return 0

    horizon = int(spec["horizon"])
    quantile = float(spec["quantile"])
    fitted, medians = mh.fit(research, horizon, SEED + 1000)
    threshold = float(pd.Series(mh.predict(research, fitted, medians)).quantile(quantile))
    stable_json(out / "model_freeze.json", {
        "selected_spec": spec,
        "calibration_records": calibration_records,
        "horizon": horizon,
        "quantile": quantile,
        "retrained_research_threshold": threshold,
        "imputation_medians": medians,
    })

    validation_trades = apply_frozen(validation, fitted, medians, threshold, horizon, "validation")
    validation_metric = common.calculate_metrics(validation_trades)
    validation_pass = validation_gate(validation_metric)
    stable_json(out / "validation_screen.json", {
        "primary": asdict(validation_metric),
        "validation_gate": validation_pass,
        "certification_materialized": bool(validation_pass),
    })

    certification_trades = pd.DataFrame()
    opposite = pd.DataFrame()
    delayed = pd.DataFrame()
    baseline = pd.DataFrame()
    certification_metric = common.calculate_metrics(pd.DataFrame())
    opposite_metric = common.calculate_metrics(pd.DataFrame())
    delayed_metric = common.calculate_metrics(pd.DataFrame())
    baseline_metric = common.calculate_metrics(pd.DataFrame())
    certification_pass = False
    control_pass = False
    combined_pass = False
    combined_metric = common.calculate_metrics(pd.DataFrame())
    if validation_pass:
        certification_trades = apply_frozen(certification, fitted, medians, threshold, horizon, "certification")
        opposite, delayed, baseline = control_bundle(certification_trades, certification)
        certification_metric = common.calculate_metrics(certification_trades)
        opposite_metric = common.calculate_metrics(opposite)
        delayed_metric = common.calculate_metrics(delayed)
        baseline_metric = common.calculate_metrics(baseline)
        certification_pass = certification_gate(certification_metric)
        control_pass = controls_gate(certification_metric, opposite_metric, delayed_metric, baseline_metric)
        combined = pd.concat([validation_trades, certification_trades], ignore_index=True, sort=False)
        combined["fold_id"] = combined["fold_id"].astype(str)
        combined_metric = common.calculate_metrics(combined)
        combined_pass = combined_gate(combined_metric)
    stable_json(out / "certification_screen.json", {
        "certification_materialized": bool(validation_pass),
        "primary": asdict(certification_metric),
        "opposite_wing_control": asdict(opposite_metric),
        "delayed_control": asdict(delayed_metric),
        "baseline_control": asdict(baseline_metric),
        "certification_economic_gate": certification_pass,
        "control_gate": control_pass,
        "combined_forward": asdict(combined_metric),
        "combined_gate": combined_pass,
        "certification_gate": bool(certification_pass and control_pass and combined_pass),
    })

    ledgers = []
    if not validation_trades.empty:
        ledgers.append(validation_trades.assign(partition="validation"))
    for partition, ledger in (
        ("certification", certification_trades),
        ("certification_opposite", opposite),
        ("certification_delayed", delayed),
        ("certification_baseline", baseline),
    ):
        if not ledger.empty:
            ledgers.append(ledger.assign(partition=partition))
    if ledgers:
        pd.concat(ledgers, ignore_index=True, sort=False).to_csv(out / "trade_ledger.csv", index=False)

    found = bool(validation_pass and certification_pass and control_pass and combined_pass)
    verdict = (
        "STRUCTURAL_EDGE_FOUND_POST_OPENING_BOOSTED_FORWARD_CERTIFICATION_CANDLE_PROXY"
        if found else (
            "POST_OPENING_CANDIDATE_FAILED_VALIDATION"
            if not validation_pass else "POST_OPENING_CANDIDATE_FAILED_CERTIFICATION_OR_CONTROLS"
        )
    )
    final = {
        "principal_verdict": verdict,
        "structural_edge_found": found,
        "validation_gate": validation_pass,
        "certification_materialized": bool(validation_pass),
        "certification_economic_gate": certification_pass,
        "control_gate": control_pass,
        "combined_gate": combined_pass,
        "selected_horizon_minutes": horizon,
        "selected_quantile": quantile,
        "contract_semantic_sha256": contract["semantic_sha256"],
        "claim_boundary": "TWO_STAGE_CHRONOLOGICAL_FORWARD_OPTION_OHLCV_CANDLE_PROXY_RESEARCH_ONLY",
        "execution_certification": "BLOCKED_AUTHORITATIVE_BID_ASK_AND_SLIPPAGE_MISSING",
        "research_only": True,
        "paper_or_live_authorized": False,
        "allowed_for_live_execution": False,
    }
    final["semantic_sha256"] = common.semantic_hash(final)
    stable_json(out / "final_decision.json", final)
    (research_dir / "RESULT.md").write_text(
        "# Post-Opening Boosted Forward Validation V1\n\n"
        f"Principal verdict: `{verdict}`\n\n"
        f"Validation gate: `{validation_pass}`; certification materialized: `{validation_pass}`; certification gate: `{found}`.\n\n"
        f"Selected horizon: `{horizon}` minutes; confidence quantile: `{quantile}`.\n\n"
        f"Validation trades: `{validation_metric.trades}`; certification trades: `{certification_metric.trades}`; combined forward trades: `{combined_metric.trades}`.\n\n"
        "The 10:00 IST gate is development-derived and is not represented as independent WFA. The two chronological unopened blocks provide validation and final certification. Historical exact OHLCV candle proxy only; no paper or live authorization.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
