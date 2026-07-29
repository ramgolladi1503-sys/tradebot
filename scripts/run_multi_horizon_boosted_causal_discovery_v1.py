#!/usr/bin/env python3
"""Nested multi-horizon boosted causal discovery for NIFTY buy-options.

One causal representative CE and PE are selected per minute. A fixed shallow
HistGradientBoostingRegressor chooses among exact 5/10/15/20-minute exits using
only earlier sessions. Each outer training period is split chronologically into
discovery and calibration; horizon and confidence quantile are frozen before the
next outer fold. The latest 25% holdout remains sealed until aggregate OOF passes.
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
from sklearn.ensemble import HistGradientBoostingRegressor

from scripts import run_inventory_absorption_transition_v1 as common
from scripts import run_nested_causal_rule_discovery_v1 as nested
from scripts import run_option_surface_transition_discovery_v1 as base
from scripts.run_conditional_precursor_discrimination_v2 import PRIOR_REL, stable_json

OUT_REL = Path("runtime/research/multi_horizon_boosted_causal_discovery_v1")
RESEARCH_REL = Path("research/multi_horizon_boosted_causal_discovery_v1")
EVENT_FILE = "event_universe_5m.parquet"
HORIZONS = (5, 10, 15, 20)
QUANTILES = (0.85, 0.90, 0.95)
NORMAL_COST_PCT = 0.10
STRESS_COST_PCT = 1.00
MAX_SIGNALS_PER_SESSION = 2
COOLDOWN_MINUTES = 20
TARGET_PREMIUM = 150.0
SEED = 20260729


def prepare(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame = pd.read_parquet(path, columns=base.CAUSAL_COLUMNS)
    frame = base._surface_features(frame)
    frame = frame.sort_values(["expired_instrument_key", "timestamp"], kind="mergesort").copy()
    instrument = frame.groupby("expired_instrument_key", sort=False, observed=True)
    entry_timestamp = instrument["timestamp"].shift(-1)
    shifted_open = pd.to_numeric(instrument["open"].shift(-1), errors="coerce")
    entry = pd.to_numeric(frame["entry_price_next_open"], errors="coerce")
    exact_entry = (entry_timestamp - frame["timestamp"]).eq(pd.Timedelta(minutes=1))
    entry_match = (entry - shifted_open).abs().fillna(np.inf).le(1e-9)
    exact_counts: dict[str, int] = {}
    for horizon in HORIZONS:
        exit_timestamp = instrument["timestamp"].shift(-horizon)
        exit_close = pd.to_numeric(instrument["close"].shift(-horizon), errors="coerce")
        exact = (exit_timestamp - frame["timestamp"]).eq(pd.Timedelta(minutes=horizon))
        gross = (exit_close / entry.replace(0, np.nan) - 1.0) * 100.0
        frame[f"gross_return_{horizon}m"] = gross.where(exact & exact_entry & entry_match)
        frame[f"net_return_{horizon}m"] = frame[f"gross_return_{horizon}m"] - NORMAL_COST_PCT
        frame[f"stress_return_{horizon}m"] = frame[f"gross_return_{horizon}m"] - STRESS_COST_PCT
        exact_counts[f"exact_{horizon}m_exit_rows"] = int(exact.sum())
    frame["bar_acceptance_numeric"] = frame["bar_acceptance"].fillna(False).astype("float32")
    frame["is_ce"] = frame["option_type"].eq("CE").astype("float32")
    frame["premium_distance"] = (entry - TARGET_PREMIUM).abs()
    frame["liquidity_score"] = (
        np.log1p(pd.to_numeric(frame["volume"], errors="coerce").clip(lower=0).fillna(0))
        + np.log1p(pd.to_numeric(frame["open_interest"], errors="coerce").clip(lower=0).fillna(0))
        - 0.01 * frame["premium_distance"].fillna(9999)
    )
    eligible = (
        exact_entry & entry_match
        & entry.between(30.0, 300.0, inclusive="both")
        & frame["minute_of_day"].between(585, 850, inclusive="both")
        & frame["days_to_expiry"].between(0, 7, inclusive="both")
        & frame["surface_count"].ge(3)
        & pd.to_numeric(frame["volume"], errors="coerce").gt(0)
        & frame[[f"gross_return_{h}m" for h in HORIZONS]].notna().all(axis=1)
    )
    frame = frame.loc[eligible].sort_values(
        ["session_id", "timestamp", "option_type", "premium_distance", "liquidity_score", "expired_instrument_key"],
        ascending=[True, True, True, True, False, True], kind="mergesort"
    )
    decisions = frame.drop_duplicates(["session_id", "timestamp", "option_type"], keep="first").copy()
    return decisions, {
        "source_rows": int(len(exact_entry)),
        "exact_next_minute_entry_rows": int(exact_entry.sum()),
        "entry_value_match_rows": int((exact_entry & entry_match).sum()),
        "eligible_rows_all_horizons": int(len(frame)),
        "representative_decision_rows": int(len(decisions)),
        "sessions": int(decisions["session_id"].nunique()),
        "horizons": list(HORIZONS), **exact_counts,
    }


def new_model(seed: int) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        loss="squared_error", learning_rate=0.05, max_iter=120,
        max_leaf_nodes=15, max_depth=3, min_samples_leaf=150,
        l2_regularization=3.0, random_state=seed, early_stopping=False,
    )


def fit(frame: pd.DataFrame, horizon: int, seed: int):
    medians = nested.impute_fit(frame)
    x = nested.matrix(frame, medians)
    y = pd.to_numeric(frame[f"stress_return_{horizon}m"], errors="coerce").to_numpy(float)
    lo, hi = np.nanquantile(y, [0.02, 0.98])
    fitted = new_model(seed).fit(x, np.clip(y, lo, hi))
    return fitted, medians


def predict(frame: pd.DataFrame, fitted, medians: dict[str, float]) -> np.ndarray:
    return fitted.predict(nested.matrix(frame, medians))


def materialize(frame: pd.DataFrame, horizon: int, fold_id: str) -> pd.DataFrame:
    out = frame.copy()
    out["selected_horizon_minutes"] = int(horizon)
    out["gross_return_pct"] = pd.to_numeric(out[f"gross_return_{horizon}m"], errors="coerce")
    out["net_return_pct"] = pd.to_numeric(out[f"net_return_{horizon}m"], errors="coerce")
    out["stress_return_pct"] = pd.to_numeric(out[f"stress_return_{horizon}m"], errors="coerce")
    out["fold_id"] = fold_id
    return out


def select(frame: pd.DataFrame, score: np.ndarray, threshold: float, horizon: int, fold_id: str) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    scored = frame.copy()
    scored["model_score"] = score
    scored["qualifies"] = scored["model_score"].ge(threshold)
    scored = scored.sort_values(["session_id", "option_type", "timestamp"], kind="mergesort")
    prior = scored.groupby(["session_id", "option_type"], sort=False, observed=True)["qualifies"].shift(1, fill_value=False)
    candidates = scored.loc[scored["qualifies"] & ~prior].copy()
    if candidates.empty:
        return candidates
    candidates = candidates.sort_values(
        ["session_id", "timestamp", "model_score", "premium_distance", "expired_instrument_key"],
        ascending=[True, True, False, True, True], kind="mergesort"
    ).drop_duplicates(["session_id", "timestamp"], keep="first")
    chosen: list[int] = []
    cooldown = pd.Timedelta(minutes=COOLDOWN_MINUTES)
    for _, group in candidates.groupby("session_id", sort=True, observed=True):
        last = None
        count = 0
        for index, row in group.iterrows():
            stamp = row["timestamp"]
            if last is not None and stamp - last < cooldown:
                continue
            chosen.append(index); last = stamp; count += 1
            if count >= MAX_SIGNALS_PER_SESSION:
                break
    picked = candidates.loc[chosen].copy() if chosen else candidates.iloc[0:0].copy()
    return materialize(picked, horizon, fold_id)


def calibration_gate(metric: common.Metrics) -> bool:
    return bool(
        metric.trades >= 20 and metric.sessions >= 15
        and metric.profit_factor is not None and metric.profit_factor >= 1.15
        and metric.mean_return_pct is not None and metric.mean_return_pct > 0
        and metric.median_return_pct is not None and metric.median_return_pct >= 0
        and metric.remove_top_three_profit_factor is not None and metric.remove_top_three_profit_factor >= 1.00
        and metric.total_halves == 2 and metric.positive_halves >= 1
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.25)
        and (metric.largest_session_share is None or metric.largest_session_share <= 0.25)
    )


def choose_spec(training: pd.DataFrame, sessions: list[str], seed: int):
    split = max(1, int(math.floor(len(sessions) * 0.70)))
    discovery = training.loc[training["session_id"].isin(sessions[:split])].copy()
    calibration = training.loc[training["session_id"].isin(sessions[split:])].copy()
    records = []
    accepted = []
    for horizon in HORIZONS:
        fitted, medians = fit(discovery, horizon, seed + horizon)
        discovery_score = predict(discovery, fitted, medians)
        calibration_score = predict(calibration, fitted, medians)
        for quantile in QUANTILES:
            threshold = float(np.quantile(discovery_score, quantile))
            trades = select(calibration, calibration_score, threshold, horizon, "calibration")
            metric = common.calculate_metrics(trades)
            record = {"horizon": horizon, "quantile": quantile, "threshold": threshold,
                      "metrics": asdict(metric), "calibration_gate": calibration_gate(metric)}
            records.append(record)
            if record["calibration_gate"]:
                accepted.append(record)
    if not accepted:
        return None, records
    accepted.sort(key=lambda r: (
        r["metrics"]["remove_top_three_profit_factor"] or -math.inf,
        r["metrics"]["profit_factor"] or -math.inf,
        r["metrics"]["mean_return_pct"] or -math.inf,
        r["metrics"]["trades"], -r["horizon"], -r["quantile"]
    ), reverse=True)
    return accepted[0], records


def fit_apply(training, testing, spec, seed: int, fold_id: str):
    horizon = int(spec["horizon"]); quantile = float(spec["quantile"])
    fitted, medians = fit(training, horizon, seed)
    threshold = float(np.quantile(predict(training, fitted, medians), quantile))
    trades = select(testing, predict(testing, fitted, medians), threshold, horizon, fold_id)
    return trades, {"horizon": horizon, "quantile": quantile,
                    "retrained_threshold": threshold, "imputation_medians": medians}


def permutation_oof(folds, decisions):
    rng = np.random.default_rng(SEED); outputs = []
    for i, (train_sessions, test_sessions, fold_id) in enumerate(folds, 1):
        training = decisions.loc[decisions["session_id"].isin(train_sessions)].copy()
        testing = decisions.loc[decisions["session_id"].isin(test_sessions)].copy()
        shuffled = training.copy()
        for horizon in HORIZONS:
            values = rng.permutation(shuffled[f"stress_return_{horizon}m"].to_numpy())
            shuffled[f"stress_return_{horizon}m"] = values
            shuffled[f"net_return_{horizon}m"] = values
            shuffled[f"gross_return_{horizon}m"] = values
        spec, _ = choose_spec(shuffled, train_sessions, SEED + 1000 + i)
        if spec is not None:
            trades, _ = fit_apply(shuffled, testing, spec, SEED + 2000 + i, f"permutation_{fold_id}")
            if not trades.empty: outputs.append(trades)
    return pd.concat(outputs, ignore_index=True, sort=False) if outputs else pd.DataFrame()


def opposite_control(signals, decisions):
    if signals.empty: return signals.copy()
    source = signals[["session_id", "timestamp", "option_type"]].copy()
    source["option_type"] = source["option_type"].map({"CE": "PE", "PE": "CE"})
    control = source.merge(decisions.drop_duplicates(["session_id", "timestamp", "option_type"]),
                           on=["session_id", "timestamp", "option_type"], how="inner", validate="many_to_one")
    return materialize(control, int(signals["selected_horizon_minutes"].mode().iloc[0]), "holdout_opposite") if not control.empty else control


def delayed_control(signals, decisions):
    if signals.empty: return signals.copy()
    source = signals[["session_id", "timestamp", "option_type"]].copy()
    source["timestamp"] += pd.Timedelta(minutes=5)
    control = source.merge(decisions.drop_duplicates(["session_id", "timestamp", "option_type"]),
                           on=["session_id", "timestamp", "option_type"], how="inner", validate="many_to_one")
    return materialize(control, int(signals["selected_horizon_minutes"].mode().iloc[0]), "holdout_delayed") if not control.empty else control


def baseline_control(signals, decisions):
    if signals.empty: return signals.copy()
    stamps = signals[["session_id", "timestamp"]].drop_duplicates()
    pool = stamps.merge(decisions, on=["session_id", "timestamp"], how="inner", validate="one_to_many")
    pool = pool.sort_values(["session_id", "timestamp", "premium_distance", "liquidity_score", "expired_instrument_key"],
                            ascending=[True, True, True, False, True], kind="mergesort").drop_duplicates(["session_id", "timestamp"])
    return materialize(pool, int(signals["selected_horizon_minutes"].mode().iloc[0]), "holdout_baseline")


def oof_gate(metric, permutation, records) -> bool:
    horizons = [r["selected_spec"]["horizon"] for r in records if r.get("selected_spec")]
    stable = bool(horizons and max(horizons.count(h) for h in set(horizons)) >= 2)
    permutation_rejected = bool(permutation.trades < 50 or permutation.profit_factor is None
                                or permutation.profit_factor <= 1.10 or permutation.mean_return_pct is None
                                or permutation.mean_return_pct <= 0)
    return bool(
        metric.trades >= 100 and metric.sessions >= 70
        and metric.profit_factor is not None and metric.profit_factor >= 1.30
        and metric.mean_return_pct is not None and metric.mean_return_pct > 0
        and metric.median_return_pct is not None and metric.median_return_pct >= 0
        and metric.remove_top_five_profit_factor is not None and metric.remove_top_five_profit_factor >= 1.10
        and metric.stress_profit_factor is not None and metric.stress_profit_factor >= 1.05
        and metric.bootstrap_mean_ci_low is not None and metric.bootstrap_mean_ci_low > 0
        and metric.total_folds == 4 and metric.positive_folds >= 3
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.15)
        and (metric.largest_session_share is None or metric.largest_session_share <= 0.15)
        and stable and permutation_rejected
    )


def holdout_gate(metric) -> bool:
    return bool(
        metric.trades >= 40 and metric.sessions >= 30
        and metric.profit_factor is not None and metric.profit_factor >= 1.20
        and metric.mean_return_pct is not None and metric.mean_return_pct > 0
        and metric.median_return_pct is not None and metric.median_return_pct >= 0
        and metric.remove_top_three_profit_factor is not None and metric.remove_top_three_profit_factor >= 1.05
        and metric.stress_profit_factor is not None and metric.stress_profit_factor >= 1.00
        and metric.total_halves == 2 and metric.positive_halves == 2
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.20)
        and (metric.largest_session_share is None or metric.largest_session_share <= 0.20)
    )


def control_gate(primary, opposite, delayed, baseline) -> bool:
    def degraded(control):
        return bool(control.trades >= max(15, int(primary.trades * 0.50))
                    and primary.mean_return_pct is not None and control.mean_return_pct is not None
                    and primary.mean_return_pct > control.mean_return_pct
                    and primary.profit_factor is not None and control.profit_factor is not None
                    and primary.profit_factor >= control.profit_factor)
    return degraded(opposite) and degraded(delayed) and degraded(baseline)


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    root = parser.parse_args().repo_root.resolve(); path = root / PRIOR_REL / EVENT_FILE
    out = root / OUT_REL; research = root / RESEARCH_REL; out.mkdir(parents=True, exist_ok=True); research.mkdir(parents=True, exist_ok=True)
    decisions, audit = prepare(path)
    research_sessions, holdout_sessions = common.research_holdout_sessions(decisions)
    folds = common.expanding_folds(research_sessions)
    stable_json(out / "multi_horizon_reconstruction_audit.json", audit)
    contract = {
        "schema_version": "multi_horizon_boosted_causal_discovery_v1",
        "horizons_minutes": list(HORIZONS), "confidence_quantiles": list(QUANTILES),
        "entry": "same_contract_open_exactly_one_minute_after_completed_signal",
        "exit": "same_contract_close_at_training_selected_exact_horizon",
        "training_objective": "winsorized_return_after_1pct_total_friction",
        "model": {"type": "HistGradientBoostingRegressor", "learning_rate": 0.05, "max_iter": 120,
                  "max_leaf_nodes": 15, "max_depth": 3, "min_samples_leaf": 150, "l2_regularization": 3.0},
        "features": nested.FEATURES,
        "nested_selection": "first_70pct_training_discovery_last_30pct_calibration_then_outer_test",
        "outer_validation": "four_expanding_walk_forward_folds",
        "signal_policy": "prediction_threshold_state_onset_max_two_per_session_twenty_minute_cooldown",
        "normal_cost_pct": NORMAL_COST_PCT, "stress_cost_pct": STRESS_COST_PCT,
        "permutation_control": "full_nested_training_label_permutation",
        "holdout_policy": "latest_25pct_evaluated_only_after_aggregate_OOF_gate",
        "research_sessions": len(research_sessions), "holdout_sessions": len(holdout_sessions),
        "research_only": True, "paper_or_live_authorized": False, "allowed_for_live_execution": False,
    }
    contract["semantic_sha256"] = common.semantic_hash(contract); stable_json(out / "frozen_contract.json", contract)
    oof_parts = []; fold_records = []
    for i, (train_sessions, test_sessions, fold_id) in enumerate(folds, 1):
        training = decisions.loc[decisions["session_id"].isin(train_sessions)].copy()
        testing = decisions.loc[decisions["session_id"].isin(test_sessions)].copy()
        spec, calibration = choose_spec(training, train_sessions, SEED + i * 100)
        record = {"fold_id": fold_id, "training_sessions": len(train_sessions), "testing_sessions": len(test_sessions),
                  "selected_spec": spec, "calibration_records": calibration}
        if spec is not None:
            trades, fitted_record = fit_apply(training, testing, spec, SEED + i * 1000, fold_id)
            record["fitted_model"] = fitted_record; record["outer_metrics"] = asdict(common.calculate_metrics(trades))
            if not trades.empty: oof_parts.append(trades)
        else: record["outer_metrics"] = asdict(common.calculate_metrics(pd.DataFrame()))
        fold_records.append(record)
    stable_json(out / "fold_models.json", fold_records)
    oof = pd.concat(oof_parts, ignore_index=True, sort=False) if oof_parts else pd.DataFrame()
    permutation_trades = permutation_oof(folds, decisions)
    oof_metric = common.calculate_metrics(oof); permutation_metric = common.calculate_metrics(permutation_trades)
    passed_oof = oof_gate(oof_metric, permutation_metric, fold_records)
    stable_json(out / "oof_screen.json", {"primary": asdict(oof_metric), "permutation_control": asdict(permutation_metric),
                "selected_horizons": [r["selected_spec"]["horizon"] for r in fold_records if r.get("selected_spec")],
                "oof_gate": passed_oof, "holdout_outcomes_materialized": bool(passed_oof)})
    empty = asdict(common.calculate_metrics(pd.DataFrame()))
    holdout_record = {"holdout_outcomes_materialized": bool(passed_oof), "selected_spec": None, "primary": empty,
                      "opposite_wing_control": empty, "delayed_control": empty, "baseline_control": empty,
                      "holdout_economic_gate": False, "control_gate": False, "holdout_gate": False}
    holdout_ledgers = []
    if passed_oof:
        research_frame = decisions.loc[decisions["session_id"].isin(research_sessions)].copy()
        holdout_frame = decisions.loc[decisions["session_id"].isin(holdout_sessions)].copy()
        spec, calibration = choose_spec(research_frame, research_sessions, SEED + 9999)
        if spec is not None:
            holdout, fitted_record = fit_apply(research_frame, holdout_frame, spec, SEED + 19999, "holdout")
            opposite = opposite_control(holdout, holdout_frame); delayed = delayed_control(holdout, holdout_frame); baseline = baseline_control(holdout, holdout_frame)
            pm = common.calculate_metrics(holdout); om = common.calculate_metrics(opposite); dm = common.calculate_metrics(delayed); bm = common.calculate_metrics(baseline)
            economic = holdout_gate(pm); controls = control_gate(pm, om, dm, bm); passed = economic and controls
            holdout_record = {"holdout_outcomes_materialized": True, "selected_spec": spec, "calibration_records": calibration,
                              "fitted_model": fitted_record, "primary": asdict(pm), "opposite_wing_control": asdict(om),
                              "delayed_control": asdict(dm), "baseline_control": asdict(bm), "holdout_economic_gate": economic,
                              "control_gate": controls, "holdout_gate": passed}
            for partition, ledger in (("holdout_primary", holdout), ("holdout_opposite", opposite), ("holdout_delayed", delayed), ("holdout_baseline", baseline)):
                if not ledger.empty: holdout_ledgers.append(ledger.assign(partition=partition))
    stable_json(out / "holdout_screen.json", holdout_record)
    ledgers = []
    if not oof.empty: ledgers.append(oof.assign(partition="research_oof"))
    if not permutation_trades.empty: ledgers.append(permutation_trades.assign(partition="permutation_oof"))
    ledgers.extend(holdout_ledgers)
    if ledgers: pd.concat(ledgers, ignore_index=True, sort=False).to_csv(out / "trade_ledger.csv", index=False)
    found = bool(passed_oof and holdout_record["holdout_gate"])
    verdict = "STRUCTURAL_EDGE_FOUND_MULTI_HORIZON_BOOSTED_CAUSAL_DISCOVERY_CANDLE_PROXY" if found else ("NO_MULTI_HORIZON_BOOSTED_OOF_EDGE" if not passed_oof else "MULTI_HORIZON_BOOSTED_OOF_EDGE_FAILED_HOLDOUT_OR_CONTROLS")
    final = {"principal_verdict": verdict, "structural_edge_found": found, "oof_gate": passed_oof,
             "holdout_gate": bool(holdout_record["holdout_gate"]), "holdout_outcomes_materialized": bool(passed_oof),
             "contract_semantic_sha256": contract["semantic_sha256"], "claim_boundary": "HISTORICAL_EXACT_MULTI_HORIZON_OPTION_OHLCV_RESEARCH_ONLY",
             "execution_certification": "BLOCKED_AUTHORITATIVE_BID_ASK_AND_SLIPPAGE_MISSING", "research_only": True,
             "paper_or_live_authorized": False, "allowed_for_live_execution": False}
    final["semantic_sha256"] = common.semantic_hash(final); stable_json(out / "final_decision.json", final)
    selected_horizons = [r["selected_spec"]["horizon"] for r in fold_records if r.get("selected_spec")]
    (research / "RESULT.md").write_text(
        "# Multi-Horizon Boosted Causal Discovery V1\n\n"
        f"Principal verdict: `{verdict}`\n\nOOF gate: `{passed_oof}`; holdout gate: `{holdout_record['holdout_gate']}`.\n\n"
        f"OOF trades: `{oof_metric.trades}`; OOF sessions: `{oof_metric.sessions}`.\n\nSelected outer horizons: `{selected_horizons}`.\n\n"
        "Nested training-only horizon/confidence selection, fixed regularized shallow boosting, four-fold expanding WFA and full permutation control. Historical exact option OHLCV exits only. No paper or live authorization.\n",
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
