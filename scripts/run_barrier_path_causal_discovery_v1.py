#!/usr/bin/env python3
"""Nested causal discovery using exact target-before-stop option paths.

Economic contract:
- signal uses completed causal data only;
- enter the same contract at the exact next-minute open;
- target +10% premium, stop -5% premium;
- maximum hold ten minutes;
- exact one-minute OHLC path;
- if target and stop are touched in the same candle, stop is assumed first;
- subtract 0.1% base and 1.0% stress total premium-return friction.

A shallow depth-three tree discovers broad leaves on prior sessions only, with
three inner chronological stability blocks and four expanding outer WFA folds.
The latest 25% chronological holdout remains sealed until the aggregate OOF gate.
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
from sklearn.tree import DecisionTreeRegressor

from scripts import run_inventory_absorption_transition_v1 as common
from scripts import run_nested_causal_rule_discovery_v1 as nested
from scripts import run_option_surface_transition_discovery_v1 as base
from scripts.run_conditional_precursor_discrimination_v2 import PRIOR_REL, stable_json

OUT_REL = Path("runtime/research/barrier_path_causal_discovery_v1")
RESEARCH_REL = Path("research/barrier_path_causal_discovery_v1")
EVENT_FILE = "event_universe_5m.parquet"
TARGET_PCT = 10.0
STOP_PCT = 5.0
MAX_HOLD_MINUTES = 10
NORMAL_COST_PCT = 0.10
STRESS_COST_PCT = 1.00
MAX_DEPTH = 3
MAX_SELECTED_LEAVES = 2
MAX_SIGNALS_PER_SESSION = 2
COOLDOWN_MINUTES = 20
TARGET_PREMIUM = 150.0
SEED = 20260729


def build_barrier_frame(event_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame = pd.read_parquet(event_path, columns=base.CAUSAL_COLUMNS)
    frame = base._surface_features(frame)
    frame = frame.sort_values(["expired_instrument_key", "timestamp"], kind="mergesort").copy()
    instrument = frame.groupby("expired_instrument_key", sort=False, observed=True)

    next_timestamp = instrument["timestamp"].shift(-1)
    next_open = pd.to_numeric(instrument["open"].shift(-1), errors="coerce")
    exact_entry = (next_timestamp - frame["timestamp"]).eq(pd.Timedelta(minutes=1))
    declared_entry = pd.to_numeric(frame["entry_price_next_open"], errors="coerce")
    entry_matches = (declared_entry - next_open).abs().fillna(np.inf) <= 1e-9
    entry = declared_entry
    target = entry * (1.0 + TARGET_PCT / 100.0)
    stop = entry * (1.0 - STOP_PCT / 100.0)

    gross = pd.Series(np.nan, index=frame.index, dtype="float64")
    exit_minute = pd.Series(pd.NA, index=frame.index, dtype="Int64")
    exit_reason = pd.Series(pd.NA, index=frame.index, dtype="string")
    valid_path = exact_entry & entry_matches & entry.gt(0)

    for minute in range(1, MAX_HOLD_MINUTES + 1):
        future_timestamp = instrument["timestamp"].shift(-minute)
        exact = (future_timestamp - frame["timestamp"]).eq(pd.Timedelta(minutes=minute))
        future_high = pd.to_numeric(instrument["high"].shift(-minute), errors="coerce")
        future_low = pd.to_numeric(instrument["low"].shift(-minute), errors="coerce")
        unresolved = gross.isna() & valid_path & exact
        stop_hit = unresolved & future_low.le(stop)
        target_hit = unresolved & future_high.ge(target)
        assign_stop = stop_hit
        assign_target = target_hit & ~stop_hit
        gross.loc[assign_stop] = -STOP_PCT
        exit_minute.loc[assign_stop] = minute
        exit_reason.loc[assign_stop] = "STOP"
        gross.loc[assign_target] = TARGET_PCT
        exit_minute.loc[assign_target] = minute
        exit_reason.loc[assign_target] = "TARGET"

    final_timestamp = instrument["timestamp"].shift(-MAX_HOLD_MINUTES)
    final_close = pd.to_numeric(instrument["close"].shift(-MAX_HOLD_MINUTES), errors="coerce")
    exact_final = (final_timestamp - frame["timestamp"]).eq(pd.Timedelta(minutes=MAX_HOLD_MINUTES))
    unresolved_final = gross.isna() & valid_path & exact_final & final_close.notna()
    gross.loc[unresolved_final] = (final_close.loc[unresolved_final] / entry.loc[unresolved_final] - 1.0) * 100.0
    exit_minute.loc[unresolved_final] = MAX_HOLD_MINUTES
    exit_reason.loc[unresolved_final] = "TIME"

    frame["gross_return_pct"] = gross
    frame["net_return_pct"] = gross - NORMAL_COST_PCT
    frame["stress_return_pct"] = gross - STRESS_COST_PCT
    frame["barrier_exit_minute"] = exit_minute
    frame["barrier_exit_reason"] = exit_reason
    frame["label_horizon_minutes"] = MAX_HOLD_MINUTES
    frame["bar_acceptance_numeric"] = frame["bar_acceptance"].fillna(False).astype("float32")
    frame["is_ce"] = frame["option_type"].eq("CE").astype("float32")
    frame["premium_distance"] = (entry - TARGET_PREMIUM).abs()
    frame["liquidity_score"] = (
        np.log1p(pd.to_numeric(frame["volume"], errors="coerce").clip(lower=0).fillna(0))
        + np.log1p(pd.to_numeric(frame["open_interest"], errors="coerce").clip(lower=0).fillna(0))
        - 0.01 * frame["premium_distance"].fillna(9999)
    )

    eligible = (
        valid_path
        & gross.notna()
        & frame["minute_of_day"].between(585, 860, inclusive="both")
        & entry.between(30.0, 300.0, inclusive="both")
        & frame["days_to_expiry"].between(0, 7, inclusive="both")
        & frame["surface_count"].ge(3)
        & pd.to_numeric(frame["volume"], errors="coerce").gt(0)
    )
    frame = frame.loc[eligible].copy()
    frame = frame.sort_values(
        [
            "session_id",
            "timestamp",
            "option_type",
            "premium_distance",
            "liquidity_score",
            "expired_instrument_key",
        ],
        ascending=[True, True, True, True, False, True],
        kind="mergesort",
    )
    decisions = frame.drop_duplicates(
        ["session_id", "timestamp", "option_type"],
        keep="first",
    ).copy()

    audit = {
        "source_rows": int(len(exact_entry)),
        "exact_next_minute_entry_rows": int(exact_entry.sum()),
        "entry_value_match_rows": int((exact_entry & entry_matches).sum()),
        "eligible_barrier_rows": int(len(frame)),
        "representative_decision_rows": int(len(decisions)),
        "sessions": int(decisions["session_id"].nunique()),
        "target_exits": int(decisions["barrier_exit_reason"].eq("TARGET").sum()),
        "stop_exits": int(decisions["barrier_exit_reason"].eq("STOP").sum()),
        "time_exits": int(decisions["barrier_exit_reason"].eq("TIME").sum()),
        "target_pct": TARGET_PCT,
        "stop_pct": STOP_PCT,
        "max_hold_minutes": MAX_HOLD_MINUTES,
        "same_bar_ambiguity": "STOP_FIRST",
    }
    return decisions, audit


def pf(values: pd.Series) -> float | None:
    return common._profit_factor(
        pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)
    )


def trim_pf(values: pd.Series, count: int) -> float | None:
    clean = np.sort(
        pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)
    )[::-1]
    return common._profit_factor(clean[count:]) if len(clean) > count else None


def barrier_leaf_stats(
    frame: pd.DataFrame,
    training_sessions: list[str],
    leaf_id: int,
) -> dict[str, Any]:
    selected = frame.loc[frame["leaf_id"].eq(leaf_id)].copy()
    stress = pd.to_numeric(selected["stress_return_pct"], errors="coerce").dropna()
    blocks = nested.inner_blocks(training_sessions)
    block_means: list[float] = []
    block_pfs: list[float | None] = []
    for block in blocks:
        part = selected.loc[
            selected["session_id"].isin(block),
            "stress_return_pct",
        ]
        block_means.append(float(part.mean()) if part.notna().any() else math.nan)
        block_pfs.append(pf(part))
    ordered = (
        np.sort(stress.to_numpy(dtype=float))[::-1]
        if len(stress)
        else np.asarray([], dtype=float)
    )
    gross_positive = float(ordered[ordered > 0].sum()) if len(ordered) else 0.0
    largest_share = (
        float(max(ordered[0], 0.0) / gross_positive)
        if len(ordered) and gross_positive > 0
        else None
    )
    target_rate = (
        float(selected["barrier_exit_reason"].eq("TARGET").mean())
        if len(selected)
        else None
    )
    minimum_sessions = max(30, int(math.ceil(len(training_sessions) * 0.30)))
    return {
        "leaf_id": int(leaf_id),
        "rows": int(len(stress)),
        "sessions": int(selected["session_id"].nunique()),
        "minimum_required_sessions": minimum_sessions,
        "profit_factor_1pct": pf(stress),
        "mean_1pct": float(stress.mean()) if len(stress) else None,
        "median_1pct": float(stress.median()) if len(stress) else None,
        "target_hit_rate": target_rate,
        "trim_top_20_profit_factor_1pct": trim_pf(stress, 20),
        "positive_inner_blocks": int(
            sum(math.isfinite(value) and value > 0 for value in block_means)
        ),
        "inner_blocks": int(len(blocks)),
        "inner_block_means": block_means,
        "inner_block_profit_factors": block_pfs,
        "largest_winner_share": largest_share,
    }


def leaf_gate(stats: dict[str, Any]) -> bool:
    return bool(
        stats["rows"] >= 500
        and stats["sessions"] >= stats["minimum_required_sessions"]
        and stats["profit_factor_1pct"] is not None
        and stats["profit_factor_1pct"] >= 1.15
        and stats["mean_1pct"] is not None
        and stats["mean_1pct"] > 0
        and stats["target_hit_rate"] is not None
        and stats["target_hit_rate"] >= 0.38
        and stats["trim_top_20_profit_factor_1pct"] is not None
        and stats["trim_top_20_profit_factor_1pct"] >= 1.05
        and stats["inner_blocks"] == 3
        and stats["positive_inner_blocks"] >= 2
        and (
            stats["largest_winner_share"] is None
            or stats["largest_winner_share"] <= 0.05
        )
    )


def discover_model(
    training: pd.DataFrame,
    training_sessions: list[str],
    seed: int,
) -> tuple[
    DecisionTreeRegressor,
    dict[str, float],
    list[int],
    list[dict[str, Any]],
    dict[int, list[str]],
]:
    medians = nested.impute_fit(training)
    x = nested.matrix(training, medians)
    y = pd.to_numeric(
        training["stress_return_pct"],
        errors="coerce",
    ).to_numpy(dtype=float)
    min_leaf = max(500, int(math.ceil(len(training) * 0.015)))
    model = DecisionTreeRegressor(
        max_depth=MAX_DEPTH,
        min_samples_leaf=min_leaf,
        random_state=seed,
        criterion="squared_error",
    )
    model.fit(x, y)
    evaluated = training.copy()
    evaluated["leaf_id"] = model.apply(x).astype(int)
    stats = [
        barrier_leaf_stats(evaluated, training_sessions, int(leaf))
        for leaf in sorted(evaluated["leaf_id"].unique())
    ]
    qualified = [item for item in stats if leaf_gate(item)]
    qualified = sorted(
        qualified,
        key=lambda item: (
            item["trim_top_20_profit_factor_1pct"] or -math.inf,
            item["profit_factor_1pct"] or -math.inf,
            item["mean_1pct"] or -math.inf,
            item["rows"],
        ),
        reverse=True,
    )[:MAX_SELECTED_LEAVES]
    selected = [int(item["leaf_id"]) for item in qualified]
    return model, medians, selected, stats, nested.tree_rules(model)


def apply_model(
    frame: pd.DataFrame,
    model: DecisionTreeRegressor,
    medians: dict[str, float],
    selected_leaves: list[int],
    fold_id: str,
) -> pd.DataFrame:
    return nested.apply_model(
        frame,
        model,
        medians,
        selected_leaves,
        fold_id,
    )


def permutation_oof(
    folds: list[tuple[list[str], list[str], str]],
    all_trades: pd.DataFrame,
) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    outputs: list[pd.DataFrame] = []
    for index, (training_sessions, testing_sessions, fold_id) in enumerate(
        folds,
        start=1,
    ):
        training = all_trades.loc[
            all_trades["session_id"].isin(training_sessions)
        ].copy()
        testing = all_trades.loc[
            all_trades["session_id"].isin(testing_sessions)
        ].copy()
        shuffled = training.copy()
        shuffled["stress_return_pct"] = rng.permutation(
            shuffled["stress_return_pct"].to_numpy()
        )
        shuffled["net_return_pct"] = shuffled["stress_return_pct"]
        model, medians, selected, _, _ = discover_model(
            shuffled,
            training_sessions,
            SEED + 100 + index,
        )
        signals = apply_model(
            testing,
            model,
            medians,
            selected,
            f"permutation_{fold_id}",
        )
        if not signals.empty:
            outputs.append(signals)
    return (
        pd.concat(outputs, ignore_index=True, sort=False)
        if outputs
        else pd.DataFrame()
    )


def opposite_wing_control(
    signals: pd.DataFrame,
    decisions: pd.DataFrame,
) -> pd.DataFrame:
    if signals.empty:
        return signals.copy()
    lookup = decisions.drop_duplicates(
        ["session_id", "timestamp", "option_type"]
    )
    source = signals[
        ["session_id", "timestamp", "option_type", "leaf_id"]
    ].copy()
    source["option_type"] = source["option_type"].map({"CE": "PE", "PE": "CE"})
    control = source.merge(
        lookup,
        on=["session_id", "timestamp", "option_type"],
        how="inner",
        suffixes=("", "_control"),
        validate="many_to_one",
    )
    control["fold_id"] = "holdout_opposite_wing"
    return control


def delayed_control(
    signals: pd.DataFrame,
    decisions: pd.DataFrame,
) -> pd.DataFrame:
    if signals.empty:
        return signals.copy()
    source = signals[
        ["session_id", "timestamp", "option_type", "leaf_id"]
    ].copy()
    source["timestamp"] = source["timestamp"] + pd.Timedelta(minutes=5)
    control = source.merge(
        decisions.drop_duplicates(
            ["session_id", "timestamp", "option_type"]
        ),
        on=["session_id", "timestamp", "option_type"],
        how="inner",
        suffixes=("", "_control"),
        validate="many_to_one",
    )
    control["fold_id"] = "holdout_delayed"
    return control


def oof_gate(
    metric: common.Metrics,
    permutation_metric: common.Metrics,
) -> bool:
    permutation_rejected = bool(
        permutation_metric.trades < 50
        or permutation_metric.profit_factor is None
        or permutation_metric.profit_factor <= 1.10
        or permutation_metric.mean_return_pct is None
        or permutation_metric.mean_return_pct <= 0
    )
    return bool(
        metric.trades >= 100
        and metric.sessions >= 70
        and metric.profit_factor is not None
        and metric.profit_factor >= 1.30
        and metric.mean_return_pct is not None
        and metric.mean_return_pct > 0
        and metric.win_rate is not None
        and metric.win_rate >= 0.40
        and metric.remove_top_five_profit_factor is not None
        and metric.remove_top_five_profit_factor >= 1.15
        and metric.stress_profit_factor is not None
        and metric.stress_profit_factor >= 1.10
        and metric.bootstrap_mean_ci_low is not None
        and metric.bootstrap_mean_ci_low > 0
        and metric.total_folds == 4
        and metric.positive_folds >= 3
        and (
            metric.largest_winner_share is None
            or metric.largest_winner_share <= 0.15
        )
        and (
            metric.largest_session_share is None
            or metric.largest_session_share <= 0.15
        )
        and permutation_rejected
    )


def holdout_gate(metric: common.Metrics) -> bool:
    return bool(
        metric.trades >= 30
        and metric.sessions >= 22
        and metric.profit_factor is not None
        and metric.profit_factor >= 1.20
        and metric.mean_return_pct is not None
        and metric.mean_return_pct > 0
        and metric.win_rate is not None
        and metric.win_rate >= 0.40
        and metric.remove_top_three_profit_factor is not None
        and metric.remove_top_three_profit_factor >= 1.05
        and metric.stress_profit_factor is not None
        and metric.stress_profit_factor >= 1.05
        and metric.total_halves == 2
        and metric.positive_halves == 2
        and (
            metric.largest_winner_share is None
            or metric.largest_winner_share <= 0.20
        )
        and (
            metric.largest_session_share is None
            or metric.largest_session_share <= 0.20
        )
    )


def control_gate(
    primary: common.Metrics,
    opposite: common.Metrics,
    delayed: common.Metrics,
) -> bool:
    opposite_rejected = bool(
        opposite.trades >= max(12, int(primary.trades * 0.50))
        and (
            opposite.mean_return_pct is None
            or primary.mean_return_pct is None
            or primary.mean_return_pct > opposite.mean_return_pct
        )
        and (
            opposite.profit_factor is None
            or primary.profit_factor is None
            or primary.profit_factor >= opposite.profit_factor
        )
    )
    delayed_degrades = bool(
        delayed.trades >= max(12, int(primary.trades * 0.50))
        and primary.mean_return_pct is not None
        and delayed.mean_return_pct is not None
        and primary.mean_return_pct > delayed.mean_return_pct
        and primary.profit_factor is not None
        and delayed.profit_factor is not None
        and primary.profit_factor >= delayed.profit_factor
    )
    return opposite_rejected and delayed_degrades


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    root = parser.parse_args().repo_root.resolve()
    event_path = root / PRIOR_REL / EVENT_FILE
    out = root / OUT_REL
    research = root / RESEARCH_REL
    out.mkdir(parents=True, exist_ok=True)
    research.mkdir(parents=True, exist_ok=True)

    decisions, barrier_audit = build_barrier_frame(event_path)
    research_sessions, holdout_sessions = common.research_holdout_sessions(
        decisions
    )
    folds = common.expanding_folds(research_sessions)
    stable_json(out / "barrier_reconstruction_audit.json", barrier_audit)

    contract = {
        "schema_version": "barrier_path_causal_discovery_v1",
        "target_pct": TARGET_PCT,
        "stop_pct": STOP_PCT,
        "max_hold_minutes": MAX_HOLD_MINUTES,
        "same_bar_ambiguity": "STOP_FIRST",
        "entry": "same_contract_open_exactly_one_minute_after_signal",
        "decision_unit": "one_causal_representative_CE_and_PE_per_minute",
        "features": nested.FEATURES,
        "max_depth": MAX_DEPTH,
        "max_selected_leaves": MAX_SELECTED_LEAVES,
        "inner_stability": "three_chronological_training_blocks",
        "outer_validation": "four_expanding_walk_forward_folds",
        "signal_policy": "selected_leaf_state_onset_max_two_session_signals_twenty_minute_cooldown",
        "normal_cost_pct": NORMAL_COST_PCT,
        "stress_cost_pct": STRESS_COST_PCT,
        "permutation_control": "fixed_seed_training_label_permutation",
        "holdout_policy": "latest_25pct_evaluated_only_after_OOF_gate",
        "research_sessions": len(research_sessions),
        "holdout_sessions": len(holdout_sessions),
        "research_only": True,
        "paper_or_live_authorized": False,
        "allowed_for_live_execution": False,
    }
    contract["semantic_sha256"] = common.semantic_hash(contract)
    stable_json(out / "frozen_contract.json", contract)

    oof_parts: list[pd.DataFrame] = []
    fold_models: list[dict[str, Any]] = []
    for index, (training_sessions, testing_sessions, fold_id) in enumerate(
        folds,
        start=1,
    ):
        training = decisions.loc[
            decisions["session_id"].isin(training_sessions)
        ].copy()
        testing = decisions.loc[
            decisions["session_id"].isin(testing_sessions)
        ].copy()
        model, medians, selected, stats, rules = discover_model(
            training,
            training_sessions,
            SEED + index,
        )
        signals = apply_model(
            testing,
            model,
            medians,
            selected,
            fold_id,
        )
        if not signals.empty:
            oof_parts.append(signals)
        fold_models.append(
            {
                "fold_id": fold_id,
                "training_sessions": len(training_sessions),
                "testing_sessions": len(testing_sessions),
                "selected_leaves": selected,
                "leaf_stats": stats,
                "rules": {
                    str(key): value for key, value in rules.items()
                },
                "imputation_medians": medians,
            }
        )
    stable_json(out / "fold_models.json", fold_models)

    oof = (
        pd.concat(oof_parts, ignore_index=True, sort=False)
        if oof_parts
        else pd.DataFrame()
    )
    permutation = permutation_oof(folds, decisions)
    oof_metric = common.calculate_metrics(oof)
    permutation_metric = common.calculate_metrics(permutation)
    oof_pass = oof_gate(oof_metric, permutation_metric)
    stable_json(
        out / "oof_screen.json",
        {
            "primary": asdict(oof_metric),
            "permutation_control": asdict(permutation_metric),
            "oof_gate": oof_pass,
            "holdout_outcomes_materialized": bool(oof_pass),
        },
    )

    empty_metric = asdict(common.calculate_metrics(pd.DataFrame()))
    holdout_record: dict[str, Any] = {
        "holdout_outcomes_materialized": bool(oof_pass),
        "primary": empty_metric,
        "opposite_wing_control": empty_metric,
        "delayed_control": empty_metric,
        "holdout_economic_gate": False,
        "control_gate": False,
        "holdout_gate": False,
    }
    final_model: dict[str, Any] = {}
    holdout_ledgers: list[pd.DataFrame] = []
    if oof_pass:
        research_frame = decisions.loc[
            decisions["session_id"].isin(research_sessions)
        ].copy()
        holdout_frame = decisions.loc[
            decisions["session_id"].isin(holdout_sessions)
        ].copy()
        model, medians, selected, stats, rules = discover_model(
            research_frame,
            research_sessions,
            SEED + 999,
        )
        holdout = apply_model(
            holdout_frame,
            model,
            medians,
            selected,
            "holdout",
        )
        opposite = opposite_wing_control(holdout, holdout_frame)
        delayed = delayed_control(holdout, holdout_frame)
        pm = common.calculate_metrics(holdout)
        om = common.calculate_metrics(opposite)
        dm = common.calculate_metrics(delayed)
        economic = holdout_gate(pm)
        controls = control_gate(pm, om, dm)
        passed = economic and controls
        holdout_record = {
            "holdout_outcomes_materialized": True,
            "primary": asdict(pm),
            "opposite_wing_control": asdict(om),
            "delayed_control": asdict(dm),
            "holdout_economic_gate": economic,
            "control_gate": controls,
            "holdout_gate": passed,
        }
        final_model = {
            "selected_leaves": selected,
            "leaf_stats": stats,
            "rules": {
                str(key): value for key, value in rules.items()
            },
            "imputation_medians": medians,
        }
        for partition, ledger in (
            ("holdout_primary", holdout),
            ("holdout_opposite", opposite),
            ("holdout_delayed", delayed),
        ):
            if not ledger.empty:
                holdout_ledgers.append(
                    ledger.assign(partition=partition)
                )
    stable_json(out / "holdout_screen.json", holdout_record)
    stable_json(out / "final_model.json", final_model)

    ledgers: list[pd.DataFrame] = []
    if not oof.empty:
        ledgers.append(oof.assign(partition="research_oof"))
    if not permutation.empty:
        ledgers.append(
            permutation.assign(partition="permutation_oof")
        )
    ledgers.extend(holdout_ledgers)
    if ledgers:
        pd.concat(
            ledgers,
            ignore_index=True,
            sort=False,
        ).to_csv(out / "trade_ledger.csv", index=False)

    found = bool(oof_pass and holdout_record["holdout_gate"])
    verdict = (
        "STRUCTURAL_EDGE_FOUND_BARRIER_PATH_CAUSAL_DISCOVERY_CANDLE_PROXY"
        if found
        else (
            "NO_BARRIER_PATH_OOF_EDGE"
            if not oof_pass
            else "BARRIER_PATH_OOF_EDGE_FAILED_HOLDOUT_OR_CONTROLS"
        )
    )
    final = {
        "principal_verdict": verdict,
        "structural_edge_found": found,
        "oof_gate": oof_pass,
        "holdout_gate": bool(holdout_record["holdout_gate"]),
        "holdout_outcomes_materialized": bool(oof_pass),
        "contract_semantic_sha256": contract["semantic_sha256"],
        "claim_boundary": "HISTORICAL_ONE_MINUTE_OHLC_BARRIER_PATH_RESEARCH_ONLY",
        "execution_certification": "BLOCKED_AUTHORITATIVE_BID_ASK_AND_STOP_SLIPPAGE_MISSING",
        "research_only": True,
        "paper_or_live_authorized": False,
        "allowed_for_live_execution": False,
    }
    final["semantic_sha256"] = common.semantic_hash(final)
    stable_json(out / "final_decision.json", final)
    (research / "RESULT.md").write_text(
        "# Barrier-Path Causal Discovery V1\n\n"
        f"Principal verdict: `{verdict}`\n\n"
        f"OOF gate: `{oof_pass}`; holdout gate: `{holdout_record['holdout_gate']}`.\n\n"
        f"OOF trades: `{oof_metric.trades}`; OOF sessions: `{oof_metric.sessions}`.\n\n"
        "Exact next-minute entry, +10% target, -5% stop, ten-minute maximum hold, "
        "stop-first same-bar ambiguity, nested causal rule discovery and fixed "
        "permutation control. Historical one-minute OHLC path proxy only. "
        "No paper or live authorization.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
