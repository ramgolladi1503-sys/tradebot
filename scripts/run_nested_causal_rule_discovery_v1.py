#!/usr/bin/env python3
"""Nested causal rule discovery for frequent NIFTY option signals.

This campaign replaces manual threshold invention with shallow, interpretable
training-only decision trees. At each minute, one liquid representative CE and
one PE are chosen causally. Each outer expanding WFA fold discovers at most two
depth-three leaves on prior sessions using winsorized 1%-friction returns, checks
those leaves across three chronological inner blocks, freezes them, and applies
them to the next fold. The latest 25% chronological holdout is evaluated only if
the aggregate OOF gate passes.

Research only. No broker, provider, paper or live action.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeRegressor, _tree

from scripts import run_inventory_absorption_transition_v1 as common
from scripts import run_option_surface_transition_discovery_v1 as base
from scripts.run_conditional_precursor_discrimination_v2 import PRIOR_REL, stable_json

OUT_REL = Path("runtime/research/nested_causal_rule_discovery_v1")
RESEARCH_REL = Path("research/nested_causal_rule_discovery_v1")
EVENT_FILE = "event_universe_5m.parquet"
NORMAL_COST_PCT = 0.10
STRESS_COST_PCT = 1.00
TARGET_PREMIUM = 150.0
MAX_SIGNALS_PER_SESSION = 2
COOLDOWN_MINUTES = 20
SEED = 20260729
MAX_DEPTH = 3
MAX_SELECTED_LEAVES = 2

FEATURES = [
    "prior_5m_return_pct",
    "prior_10m_range_pct",
    "prior_5m_volume_ratio",
    "return_acceleration",
    "volume_acceleration",
    "oi_change_ratio",
    "bar_acceptance_numeric",
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
    "mirror_return",
    "mirror_acceleration",
    "mirror_volume_ratio",
    "option_asymmetry",
    "days_to_expiry",
    "minute_of_day",
    "entry_price_next_open",
    "is_ce",
]


def prepare_causal(event_path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(event_path, columns=base.CAUSAL_COLUMNS)
    frame = base._surface_features(frame)
    frame = frame.loc[
        frame["minute_of_day"].between(585, 870, inclusive="both")
        & frame["entry_price_next_open"].between(30.0, 300.0, inclusive="both")
        & frame["days_to_expiry"].between(0, 7, inclusive="both")
        & (frame["surface_count"] >= 3)
        & (frame["volume"] > 0)
    ].copy()
    frame["bar_acceptance_numeric"] = frame["bar_acceptance"].fillna(False).astype("float32")
    frame["is_ce"] = frame["option_type"].eq("CE").astype("float32")
    frame["premium_distance"] = (frame["entry_price_next_open"] - TARGET_PREMIUM).abs()
    frame["liquidity_score"] = (
        np.log1p(frame["volume"].clip(lower=0).fillna(0))
        + np.log1p(frame["open_interest"].clip(lower=0).fillna(0))
        - 0.01 * frame["premium_distance"].fillna(9999)
    )
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
    return frame.drop_duplicates(
        ["session_id", "timestamp", "option_type"],
        keep="first",
    ).copy()


def attach_all_outcomes(
    decisions: pd.DataFrame,
    event_path: Path,
    sessions: list[str],
) -> pd.DataFrame:
    outcomes = base._load_outcomes(event_path, base._raw_sessions(decisions, sessions))
    trades = base._attach_outcomes(
        decisions.loc[decisions["session_id"].isin(sessions)].copy(),
        outcomes,
    )
    return trades.loc[
        trades["label_horizon_minutes"].eq(5)
        & trades["stress_return_pct"].notna()
    ].copy()


def impute_fit(frame: pd.DataFrame) -> dict[str, float]:
    medians: dict[str, float] = {}
    for feature in FEATURES:
        values = pd.to_numeric(frame[feature], errors="coerce").replace([np.inf, -np.inf], np.nan)
        median = float(values.median()) if values.notna().any() else 0.0
        medians[feature] = median
    return medians


def matrix(frame: pd.DataFrame, medians: dict[str, float]) -> np.ndarray:
    columns: list[np.ndarray] = []
    for feature in FEATURES:
        values = pd.to_numeric(frame[feature], errors="coerce").replace([np.inf, -np.inf], np.nan)
        columns.append(values.fillna(medians[feature]).to_numpy(dtype="float64"))
    return np.column_stack(columns)


def inner_blocks(sessions: list[str]) -> list[list[str]]:
    return [list(block) for block in np.array_split(np.asarray(sessions, dtype=object), 3) if len(block)]


def pf(values: pd.Series) -> float | None:
    return common._profit_factor(pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float))


def trim_pf(values: pd.Series, count: int) -> float | None:
    clean = np.sort(pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float))[::-1]
    return common._profit_factor(clean[count:]) if len(clean) > count else None


def leaf_stats(frame: pd.DataFrame, sessions: list[str], leaf_id: int) -> dict[str, Any]:
    selected = frame.loc[frame["leaf_id"].eq(leaf_id)].copy()
    stress = pd.to_numeric(selected["stress_return_pct"], errors="coerce").dropna()
    blocks = inner_blocks(sessions)
    block_means: list[float] = []
    block_pfs: list[float | None] = []
    for block in blocks:
        part = selected.loc[selected["session_id"].isin(block), "stress_return_pct"]
        block_means.append(float(part.mean()) if part.notna().any() else math.nan)
        block_pfs.append(pf(part))
    ordered = np.sort(stress.to_numpy(dtype=float))[::-1] if len(stress) else np.asarray([], dtype=float)
    gross_positive = float(ordered[ordered > 0].sum()) if len(ordered) else 0.0
    largest_share = (
        float(max(ordered[0], 0.0) / gross_positive)
        if len(ordered) and gross_positive > 0
        else None
    )
    return {
        "leaf_id": int(leaf_id),
        "rows": int(len(stress)),
        "sessions": int(selected["session_id"].nunique()),
        "profit_factor_1pct": pf(stress),
        "mean_1pct": float(stress.mean()) if len(stress) else None,
        "median_1pct": float(stress.median()) if len(stress) else None,
        "trim_top_20_profit_factor_1pct": trim_pf(stress, 20),
        "positive_inner_blocks": int(sum(math.isfinite(value) and value > 0 for value in block_means)),
        "inner_blocks": int(len(blocks)),
        "inner_block_means": block_means,
        "inner_block_profit_factors": block_pfs,
        "largest_winner_share": largest_share,
    }


def leaf_gate(stats: dict[str, Any]) -> bool:
    return bool(
        stats["rows"] >= 500
        and stats["sessions"] >= 80
        and stats["profit_factor_1pct"] is not None
        and stats["profit_factor_1pct"] >= 1.15
        and stats["mean_1pct"] is not None
        and stats["mean_1pct"] > 0
        and stats["median_1pct"] is not None
        and stats["median_1pct"] >= 0
        and stats["trim_top_20_profit_factor_1pct"] is not None
        and stats["trim_top_20_profit_factor_1pct"] >= 1.05
        and stats["inner_blocks"] == 3
        and stats["positive_inner_blocks"] >= 2
        and (
            stats["largest_winner_share"] is None
            or stats["largest_winner_share"] <= 0.05
        )
    )


def tree_rules(model: DecisionTreeRegressor) -> dict[int, list[str]]:
    tree = model.tree_
    rules: dict[int, list[str]] = {}

    def walk(node: int, conditions: list[str]) -> None:
        if tree.feature[node] == _tree.TREE_UNDEFINED:
            rules[int(node)] = list(conditions)
            return
        feature = FEATURES[int(tree.feature[node])]
        threshold = float(tree.threshold[node])
        walk(int(tree.children_left[node]), conditions + [f"{feature} <= {threshold:.12g}"])
        walk(int(tree.children_right[node]), conditions + [f"{feature} > {threshold:.12g}"])

    walk(0, [])
    return rules


def discover_model(
    training: pd.DataFrame,
    training_sessions: list[str],
    seed: int,
) -> tuple[DecisionTreeRegressor, dict[str, float], list[int], list[dict[str, Any]], dict[int, list[str]]]:
    medians = impute_fit(training)
    x = matrix(training, medians)
    raw_y = pd.to_numeric(training["stress_return_pct"], errors="coerce").to_numpy(dtype=float)
    lower, upper = np.nanquantile(raw_y, [0.02, 0.98])
    y = np.clip(raw_y, lower, upper)
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
    stats = [leaf_stats(evaluated, training_sessions, int(leaf)) for leaf in sorted(evaluated["leaf_id"].unique())]
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
    return model, medians, selected, stats, tree_rules(model)


def apply_model(
    frame: pd.DataFrame,
    model: DecisionTreeRegressor,
    medians: dict[str, float],
    selected_leaves: list[int],
    fold_id: str,
) -> pd.DataFrame:
    if frame.empty or not selected_leaves:
        return frame.iloc[0:0].copy()
    scored = frame.copy()
    x = matrix(scored, medians)
    scored["leaf_id"] = model.apply(x).astype(int)
    scored["predicted_stress_return"] = model.predict(x)
    scored["rule_selected"] = scored["leaf_id"].isin(selected_leaves)
    scored = scored.sort_values(
        ["session_id", "option_type", "timestamp"],
        kind="mergesort",
    )
    prior = scored.groupby(
        ["session_id", "option_type"],
        sort=False,
        observed=True,
    )["rule_selected"].shift(1, fill_value=False)
    candidates = scored.loc[scored["rule_selected"] & ~prior].copy()
    if candidates.empty:
        return candidates
    candidates = candidates.sort_values(
        [
            "session_id",
            "timestamp",
            "predicted_stress_return",
            "premium_distance",
            "expired_instrument_key",
        ],
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
    selected = candidates.loc[chosen].copy() if chosen else candidates.iloc[0:0].copy()
    selected["fold_id"] = fold_id
    return selected


def permutation_oof(
    folds: list[tuple[list[str], list[str], str]],
    all_trades: pd.DataFrame,
) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    outputs: list[pd.DataFrame] = []
    for index, (training_sessions, testing_sessions, fold_id) in enumerate(folds, start=1):
        training = all_trades.loc[all_trades["session_id"].isin(training_sessions)].copy()
        testing = all_trades.loc[all_trades["session_id"].isin(testing_sessions)].copy()
        shuffled = training.copy()
        shuffled["stress_return_pct"] = rng.permutation(shuffled["stress_return_pct"].to_numpy())
        shuffled["net_return_pct"] = shuffled["stress_return_pct"]
        model, medians, selected, _, _ = discover_model(shuffled, training_sessions, SEED + 100 + index)
        signals = apply_model(testing, model, medians, selected, f"permutation_{fold_id}")
        if not signals.empty:
            outputs.append(signals)
    return pd.concat(outputs, ignore_index=True, sort=False) if outputs else pd.DataFrame()


def mirror_control(signals: pd.DataFrame, causal_trades: pd.DataFrame) -> pd.DataFrame:
    if signals.empty:
        return signals.copy()
    lookup = causal_trades.drop_duplicates(["session_id", "timestamp", "option_type"])
    source = signals[["session_id", "timestamp", "option_type", "leaf_id"]].copy()
    source["option_type"] = source["option_type"].map({"CE": "PE", "PE": "CE"})
    mirrored = source.merge(
        lookup,
        on=["session_id", "timestamp", "option_type"],
        how="inner",
        suffixes=("", "_control"),
        validate="many_to_one",
    )
    mirrored["fold_id"] = "holdout_mirror"
    return mirrored


def delayed_control(signals: pd.DataFrame, causal_trades: pd.DataFrame) -> pd.DataFrame:
    if signals.empty:
        return signals.copy()
    source = signals[["session_id", "timestamp", "option_type", "leaf_id"]].copy()
    source["timestamp"] = source["timestamp"] + pd.Timedelta(minutes=5)
    delayed = source.merge(
        causal_trades.drop_duplicates(["session_id", "timestamp", "option_type"]),
        on=["session_id", "timestamp", "option_type"],
        how="inner",
        suffixes=("", "_control"),
        validate="many_to_one",
    )
    delayed["fold_id"] = "holdout_delayed"
    return delayed


def oof_gate(metric: common.Metrics, permutation_metric: common.Metrics) -> bool:
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
        and metric.profit_factor is not None and metric.profit_factor >= 1.30
        and metric.mean_return_pct is not None and metric.mean_return_pct > 0
        and metric.median_return_pct is not None and metric.median_return_pct >= 0
        and metric.remove_top_five_profit_factor is not None and metric.remove_top_five_profit_factor >= 1.10
        and metric.stress_profit_factor is not None and metric.stress_profit_factor >= 1.05
        and metric.bootstrap_mean_ci_low is not None and metric.bootstrap_mean_ci_low > 0
        and metric.total_folds == 4 and metric.positive_folds >= 3
        and (metric.largest_winner_share is None or metric.largest_winner_share <= 0.15)
        and (metric.largest_session_share is None or metric.largest_session_share <= 0.15)
        and permutation_rejected
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


def control_gate(primary: common.Metrics, mirror: common.Metrics, delayed: common.Metrics) -> bool:
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
    return mirror_rejected and delayed_degrades


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    root = parser.parse_args().repo_root.resolve()
    event_path = root / PRIOR_REL / EVENT_FILE
    out = root / OUT_REL
    research = root / RESEARCH_REL
    out.mkdir(parents=True, exist_ok=True)
    research.mkdir(parents=True, exist_ok=True)

    decisions = prepare_causal(event_path)
    research_sessions, holdout_sessions = common.research_holdout_sessions(decisions)
    all_sessions = research_sessions + holdout_sessions
    all_trades = attach_all_outcomes(decisions, event_path, all_sessions)
    folds = common.expanding_folds(research_sessions)

    contract = {
        "schema_version": "nested_causal_rule_discovery_v1",
        "decision_unit": "one_causally_selected_representative_contract_per_option_wing_per_minute",
        "features": FEATURES,
        "max_depth": MAX_DEPTH,
        "max_selected_leaves": MAX_SELECTED_LEAVES,
        "training_target": "winsorized_same_contract_five_minute_return_after_1pct_total_friction",
        "inner_stability": "three_chronological_training_blocks",
        "outer_validation": "four_expanding_walk_forward_folds",
        "signal_policy": "selected_leaf_state_onset_max_two_session_signals_twenty_minute_cooldown",
        "entry": "same_contract_open_exactly_one_minute_after_completed_signal",
        "outcome_horizon_minutes": 5,
        "normal_cost_pct": NORMAL_COST_PCT,
        "stress_cost_pct": STRESS_COST_PCT,
        "permutation_control": "fixed_seed_training_label_permutation_pipeline",
        "holdout_policy": "latest_25pct_evaluated_only_after_aggregate_oof_gate",
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
    for index, (training_sessions, testing_sessions, fold_id) in enumerate(folds, start=1):
        training = all_trades.loc[all_trades["session_id"].isin(training_sessions)].copy()
        testing = all_trades.loc[all_trades["session_id"].isin(testing_sessions)].copy()
        model, medians, selected, stats, rules = discover_model(training, training_sessions, SEED + index)
        signals = apply_model(testing, model, medians, selected, fold_id)
        if not signals.empty:
            oof_parts.append(signals)
        fold_models.append({
            "fold_id": fold_id,
            "training_sessions": len(training_sessions),
            "testing_sessions": len(testing_sessions),
            "selected_leaves": selected,
            "leaf_stats": stats,
            "rules": {str(key): value for key, value in rules.items()},
            "imputation_medians": medians,
        })
    stable_json(out / "fold_models.json", fold_models)

    oof = pd.concat(oof_parts, ignore_index=True, sort=False) if oof_parts else pd.DataFrame()
    permutation = permutation_oof(folds, all_trades)
    oof_metric = common.calculate_metrics(oof)
    permutation_metric = common.calculate_metrics(permutation)
    oof_pass = oof_gate(oof_metric, permutation_metric)
    stable_json(out / "oof_screen.json", {
        "primary": asdict(oof_metric),
        "permutation_control": asdict(permutation_metric),
        "oof_gate": oof_pass,
        "holdout_outcomes_materialized": bool(oof_pass),
    })

    holdout_records: dict[str, Any] = {
        "holdout_outcomes_materialized": bool(oof_pass),
        "primary": asdict(common.calculate_metrics(pd.DataFrame())),
        "mirror_control": asdict(common.calculate_metrics(pd.DataFrame())),
        "delayed_control": asdict(common.calculate_metrics(pd.DataFrame())),
        "holdout_economic_gate": False,
        "control_gate": False,
        "holdout_gate": False,
    }
    final_model_record: dict[str, Any] = {}
    holdout_ledgers: list[pd.DataFrame] = []
    if oof_pass:
        research_frame = all_trades.loc[all_trades["session_id"].isin(research_sessions)].copy()
        holdout_frame = all_trades.loc[all_trades["session_id"].isin(holdout_sessions)].copy()
        model, medians, selected, stats, rules = discover_model(research_frame, research_sessions, SEED + 999)
        holdout = apply_model(holdout_frame, model, medians, selected, "holdout")
        mirror = mirror_control(holdout, holdout_frame)
        delayed = delayed_control(holdout, holdout_frame)
        primary_metric = common.calculate_metrics(holdout)
        mirror_metric = common.calculate_metrics(mirror)
        delayed_metric = common.calculate_metrics(delayed)
        economic = holdout_gate(primary_metric)
        controls = control_gate(primary_metric, mirror_metric, delayed_metric)
        passed = economic and controls
        holdout_records = {
            "holdout_outcomes_materialized": True,
            "primary": asdict(primary_metric),
            "mirror_control": asdict(mirror_metric),
            "delayed_control": asdict(delayed_metric),
            "holdout_economic_gate": economic,
            "control_gate": controls,
            "holdout_gate": passed,
        }
        final_model_record = {
            "selected_leaves": selected,
            "leaf_stats": stats,
            "rules": {str(key): value for key, value in rules.items()},
            "imputation_medians": medians,
        }
        for partition, ledger in (
            ("holdout_primary", holdout),
            ("holdout_mirror", mirror),
            ("holdout_delayed", delayed),
        ):
            if not ledger.empty:
                holdout_ledgers.append(ledger.assign(partition=partition))
    stable_json(out / "holdout_screen.json", holdout_records)
    stable_json(out / "final_model.json", final_model_record)

    ledgers: list[pd.DataFrame] = []
    if not oof.empty:
        ledgers.append(oof.assign(partition="research_oof"))
    if not permutation.empty:
        ledgers.append(permutation.assign(partition="permutation_oof"))
    ledgers.extend(holdout_ledgers)
    if ledgers:
        pd.concat(ledgers, ignore_index=True, sort=False).to_csv(out / "trade_ledger.csv", index=False)

    found = bool(oof_pass and holdout_records["holdout_gate"])
    verdict = (
        "STRUCTURAL_EDGE_FOUND_NESTED_CAUSAL_RULE_DISCOVERY_CANDLE_PROXY"
        if found
        else ("NO_NESTED_RULE_OOF_EDGE" if not oof_pass else "NESTED_RULE_OOF_EDGE_FAILED_HOLDOUT_OR_CONTROLS")
    )
    final = {
        "principal_verdict": verdict,
        "structural_edge_found": found,
        "oof_gate": oof_pass,
        "holdout_gate": bool(holdout_records["holdout_gate"]),
        "holdout_outcomes_materialized": bool(oof_pass),
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
        "# Nested Causal Rule Discovery V1\n\n"
        f"Principal verdict: `{verdict}`\n\n"
        f"OOF gate: `{oof_pass}`; holdout gate: `{holdout_records['holdout_gate']}`.\n\n"
        f"OOF trades: `{oof_metric.trades}`; OOF sessions: `{oof_metric.sessions}`.\n\n"
        "Depth-three interpretable rules, training-only inner stability, four-fold expanding WFA, "
        "fixed permutation control, historical five-minute OHLCV candle proxy only. "
        "No paper or live authorization.\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
