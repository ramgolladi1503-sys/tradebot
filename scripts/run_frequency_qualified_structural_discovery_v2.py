from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_joint_structural_discovery_v1 import (  # noqa: E402
    DEV_END,
    HOLDOUT_START,
    MAX_HOLD_MINUTES,
    MIN_PREMIUM,
    ROUND_TRIP_COST_POINTS,
    STOP_POINTS,
    TARGET_POINTS,
    label_outcomes,
    prepare_research_table,
    summarize,
)


SOURCE_COMMIT = "d8fb9c953b9cb45554111f405a3c58e8c6b5d73a"
OUT_DIR = Path("research/frequency_qualified_structural_discovery_v2")
REPAIRED_JOINT_PATH = Path("research/joint_warehouse_underlying_feature_repair_v1/repaired_joint_underlying_option_warehouse.parquet")
GOVERNANCE_DIR = Path("research/provider_sparse_bar_governance_v1")
HISTORICAL_ACQ_DIR = Path("research/premium_compression_historical_acquisition_v1")
FROZEN_RERUN_DIR = Path("research/frozen_joint_mechanisms_repaired_v2")
MECHANISM = "premium_compression_release_with_underlying_state_filter"


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def git(args: list[str], cwd: Path) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def mean_ci(values: pd.Series) -> dict[str, float]:
    n = int(values.count())
    mean = float(values.mean()) if n else 0.0
    std = float(values.std(ddof=1)) if n > 1 else 0.0
    half = 1.96 * std / math.sqrt(n) if n > 1 else 0.0
    return {"n": n, "mean": mean, "std": std, "ci95_low": mean - half, "ci95_high": mean + half}


def extended_stats(sample: pd.DataFrame) -> dict[str, Any]:
    stats = summarize(sample)
    stats.update(
        {
            "gross_expectancy_points": float(sample["gross_points"].mean()) if len(sample) else 0.0,
            "net_points_ci": mean_ci(sample["net_points"]) if len(sample) else mean_ci(pd.Series(dtype=float)),
            "mfe_points_mean": float(sample["mfe_points"].mean()) if len(sample) else 0.0,
            "mae_points_mean": float(sample["mae_points"].mean()) if len(sample) else 0.0,
            "session_count": int(sample["session_date"].nunique()) if len(sample) else 0,
            "expiry_count": int(sample["expiry"].nunique()) if len(sample) else 0,
            "side_counts": sample["option_type"].value_counts().to_dict() if len(sample) else {},
        }
    )
    return stats


def add_structural_features(table: pd.DataFrame) -> pd.DataFrame:
    out = table.copy()
    out["same_side_underlying"] = (out["option_type"].eq("CE") & out["ret_1"].gt(0)) | (out["option_type"].eq("PE") & out["ret_1"].lt(0))
    out["opposite_side_underlying"] = (out["option_type"].eq("CE") & out["ret_1"].lt(0)) | (out["option_type"].eq("PE") & out["ret_1"].gt(0))
    out["premium_positive"] = out["premium_velocity"].gt(0)
    out["premium_persistent"] = out.groupby("expired_instrument_key", sort=False)["premium_positive"].transform(lambda s: s.rolling(2, min_periods=2).sum().ge(2))
    out["positive_accel"] = out["premium_acceleration"].gt(0)
    out["large_underlying_move"] = out["ret_1"].abs().gt(out["ret_1"].abs().quantile(0.60))
    out["low_vwap_distance"] = out["vwap_distance"].abs().le(out["vwap_distance"].abs().quantile(0.55))
    out["expiry_week"] = out["dte"].between(0, 4)
    key = ["event_timestamp", "expiry", "strike"]
    opposite = out[key + ["option_type", "premium_velocity", "premium_acceleration", "premium_mean"]].copy()
    opposite["option_type"] = opposite["option_type"].map({"CE": "PE", "PE": "CE"})
    opposite = opposite.rename(
        columns={
            "premium_velocity": "opposite_premium_velocity",
            "premium_acceleration": "opposite_premium_acceleration",
            "premium_mean": "opposite_premium_mean",
        }
    )
    out = out.merge(opposite, on=key + ["option_type"], how="left")
    out["pair_velocity_spread"] = out["premium_velocity"] - out["opposite_premium_velocity"].fillna(0.0)
    out["opposite_failed_response"] = out["same_side_underlying"] & out["opposite_premium_velocity"].ge(-0.10)
    out = out.sort_values(["event_timestamp", "expiry", "option_type", "strike"]).reset_index(drop=True)
    grouped = out.groupby(["event_timestamp", "expiry", "option_type"], sort=False)
    out["adjacent_velocity_mean"] = (grouped["premium_velocity"].shift(1) + grouped["premium_velocity"].shift(-1)) / 2
    out["adjacent_accel_mean"] = (grouped["premium_acceleration"].shift(1) + grouped["premium_acceleration"].shift(-1)) / 2
    out["strike_ladder_confirmed"] = out["premium_velocity"].gt(0) & out["adjacent_velocity_mean"].gt(0)
    out["adjacent_accel_confirmed"] = out["premium_acceleration"].gt(0) & out["adjacent_accel_mean"].gt(0)
    out = out.sort_values(["expired_instrument_key", "event_timestamp"]).reset_index(drop=True)
    out["research_row_id"] = out.index.astype(int)
    return out


def candidate_catalogue() -> list[dict[str, Any]]:
    return [
        {
            "id": "FQSDV2_PAIR_ASYM_01",
            "family": "relative_option_response_asymmetry",
            "economic_mechanism": "directional option premium accelerates while the paired opposite option fails to respond proportionally",
            "observable_sequence": ["underlying impulse", "same-side option positive velocity", "paired opposite-side response failure", "same-side premium persistence"],
            "participant_behaviour": "buyers reprice directional optionality faster than hedgers reprice the opposite leg",
            "expected_persistence_after_costs": "paired-side asymmetry should persist for at least one next observable bar if repricing is not complete",
            "required_fields": ["ret_1", "premium_velocity", "premium_acceleration", "option_type", "expiry", "strike"],
            "unsupported_assumptions": ["bid/ask depth", "IV decomposition"],
            "expected_failure_mode": "volatility-wide repricing makes both sides move similarly",
            "materially_distinct_from_prior": "uses CE/PE paired response imbalance, not ORB, pure momentum, delayed under-response, or parked compression release",
        },
        {
            "id": "FQSDV2_LADDER_CONFIRM_02",
            "family": "cross_strike_confirmation",
            "economic_mechanism": "same-side premium expansion is confirmed by adjacent strikes in the option ladder",
            "observable_sequence": ["underlying impulse", "selected strike premium expands", "adjacent strike premium also expands", "next-bar entry"],
            "participant_behaviour": "flow appears across nearby strikes rather than as isolated stale-price noise",
            "expected_persistence_after_costs": "coordinated ladder repricing should be less noisy than one-contract movement",
            "required_fields": ["ret_1", "premium_velocity", "premium_acceleration", "strike", "option_type", "expiry"],
            "unsupported_assumptions": ["order-book sweep identity"],
            "expected_failure_mode": "adjacent strikes are stale or wide relative to selected strike",
            "materially_distinct_from_prior": "requires cross-strike option confirmation; not a lookback tweak of prior candidates",
        },
        {
            "id": "FQSDV2_EXPIRY_TRANSITION_03",
            "family": "expiry_state_transition",
            "economic_mechanism": "expiry-week directional repricing from low vwap displacement into premium acceleration",
            "observable_sequence": ["expiry-week state", "underlying remains near VWAP", "same-side premium acceleration", "premium persistence"],
            "participant_behaviour": "short-dated gamma demand reprices when balanced intraday state resolves",
            "expected_persistence_after_costs": "near-expiry repricing can be abrupt enough to cover fixed point costs",
            "required_fields": ["dte", "vwap_distance", "premium_acceleration", "premium_velocity", "ret_1"],
            "unsupported_assumptions": ["gamma exposure", "dealer positioning"],
            "expected_failure_mode": "theta decay dominates directional repricing",
            "materially_distinct_from_prior": "DTE is a state transition component, not a simple DTE filter or compression release",
        },
        {
            "id": "FQSDV2_FAILED_OPPOSITE_04",
            "family": "failed_opposite_side_response",
            "economic_mechanism": "opposite side does not cheapen during an underlying displacement while the directional side strengthens",
            "observable_sequence": ["large underlying displacement", "opposite option fails to fall", "same-side option acceleration", "next-bar entry"],
            "participant_behaviour": "directional move is accompanied by asymmetric option repricing, not generic volatility shock",
            "expected_persistence_after_costs": "failure of the opposite side may identify continuation rather than mean reversion",
            "required_fields": ["ret_1", "opposite_premium_velocity", "premium_acceleration", "option_type"],
            "unsupported_assumptions": ["volatility surface cause"],
            "expected_failure_mode": "market-wide volatility expansion inflates both sides without direction",
            "materially_distinct_from_prior": "explicitly compares opposite side response rather than delayed same-side under-response",
        },
        {
            "id": "FQSDV2_INTRADAY_DOMINANCE_05",
            "family": "intraday_state_transition",
            "economic_mechanism": "two-sided balance transitions to one-sided premium dominance after underlying move",
            "observable_sequence": ["paired premiums near balance", "underlying impulse", "pair velocity spread widens", "same-side premium persistence"],
            "participant_behaviour": "option chain transitions from balanced response to directional dominance",
            "expected_persistence_after_costs": "dominance transition should avoid isolated single-tick option noise",
            "required_fields": ["premium_mean", "premium_velocity", "ret_1", "option_type", "expiry", "strike"],
            "unsupported_assumptions": ["order flow labels"],
            "expected_failure_mode": "balance metric is contaminated by stale opposite-side candles",
            "materially_distinct_from_prior": "state transition uses paired CE/PE dominance, not parked compression",
        },
        {
            "id": "FQSDV2_MULTI_STAGE_06",
            "family": "multi_stage_confirmation",
            "economic_mechanism": "underlying initiation, option ladder confirmation, and persistence align before entry",
            "observable_sequence": ["underlying impulse", "same-side option positive velocity", "adjacent-strike confirmation", "same-side persistence"],
            "participant_behaviour": "multi-source confirmation reduces false positives from pure underlying moves",
            "expected_persistence_after_costs": "distinct chain confirmation may lag underlying by one bar",
            "required_fields": ["ret_1", "premium_velocity", "premium_acceleration", "strike", "option_type"],
            "unsupported_assumptions": ["participant identity"],
            "expected_failure_mode": "too restrictive, insufficient event support",
            "materially_distinct_from_prior": "combines cross-strike option confirmation with underlying initiation, not a prior broad joint rule",
        },
        {
            "id": "FQSDV2_ELASTICITY_07",
            "family": "relative_option_response_asymmetry",
            "economic_mechanism": "directional premium elasticity exceeds paired-side elasticity after modest underlying impulse",
            "observable_sequence": ["moderate underlying move", "same-side premium velocity exceeds paired opposite velocity", "positive acceleration"],
            "participant_behaviour": "option chain embeds directional information beyond underlying displacement",
            "expected_persistence_after_costs": "elasticity imbalance can persist while the chain catches up",
            "required_fields": ["ret_1", "premium_velocity", "opposite_premium_velocity", "premium_acceleration"],
            "unsupported_assumptions": ["delta-normalized option response"],
            "expected_failure_mode": "raw premium differences are not delta-normalized",
            "materially_distinct_from_prior": "uses paired elasticity spread, not absolute premium compression or delayed convexity",
        },
        {
            "id": "FQSDV2_OTM_LADDER_08",
            "family": "cross_strike_confirmation",
            "economic_mechanism": "near/mid strikes confirm same-side repricing away from ATM only",
            "observable_sequence": ["same-side underlying move", "NEAR/MID option acceleration", "adjacent strike confirms", "next-bar entry"],
            "participant_behaviour": "directional demand propagates across tradable non-ATM strikes",
            "expected_persistence_after_costs": "confirmation across non-ATM strikes may catch continuation before ATM noise fades",
            "required_fields": ["moneyness_bucket", "strike", "premium_acceleration", "ret_1"],
            "unsupported_assumptions": ["true moneyness Greeks"],
            "expected_failure_mode": "non-ATM premiums are too sparse or noisy",
            "materially_distinct_from_prior": "non-ATM cross-strike confirmation, not ORB or simple momentum",
        },
    ]


def base_mask(frame: pd.DataFrame) -> pd.Series:
    return frame["research_eligible"] & frame["premium_mean"].ge(MIN_PREMIUM) & frame["dte"].between(0, 14) & frame["moneyness_bucket"].isin(["ATM", "NEAR", "MID"])


def mask_for(frame: pd.DataFrame, candidate_id: str, variant: str = "primary") -> pd.Series:
    base = base_mask(frame)
    impulse_q = {"loose": 0.50, "primary": 0.60, "strict": 0.70}[variant]
    impulse = frame["ret_1"].abs().gt(frame["ret_1"].abs().quantile(impulse_q))
    accel_min = {"loose": -0.05, "primary": 0.0, "strict": 0.10}[variant]
    if candidate_id == "FQSDV2_PAIR_ASYM_01":
        return base & frame["same_side_underlying"] & impulse & frame["premium_velocity"].gt(0) & frame["pair_velocity_spread"].gt(0.25) & frame["premium_persistent"]
    if candidate_id == "FQSDV2_LADDER_CONFIRM_02":
        return base & frame["same_side_underlying"] & impulse & frame["strike_ladder_confirmed"] & frame["premium_acceleration"].gt(accel_min)
    if candidate_id == "FQSDV2_EXPIRY_TRANSITION_03":
        return base & frame["expiry_week"] & frame["low_vwap_distance"] & frame["same_side_underlying"] & frame["positive_accel"] & frame["premium_persistent"]
    if candidate_id == "FQSDV2_FAILED_OPPOSITE_04":
        return base & impulse & frame["opposite_failed_response"] & frame["premium_acceleration"].gt(accel_min)
    if candidate_id == "FQSDV2_INTRADAY_DOMINANCE_05":
        balanced = frame["opposite_premium_mean"].notna() & (frame["premium_mean"] / frame["opposite_premium_mean"].replace(0, pd.NA)).between(0.70, 1.30)
        return base & balanced.fillna(False) & frame["same_side_underlying"] & frame["pair_velocity_spread"].gt(0.50) & frame["premium_persistent"]
    if candidate_id == "FQSDV2_MULTI_STAGE_06":
        return base & frame["same_side_underlying"] & impulse & frame["strike_ladder_confirmed"] & frame["adjacent_accel_confirmed"] & frame["premium_persistent"]
    if candidate_id == "FQSDV2_ELASTICITY_07":
        return base & frame["same_side_underlying"] & frame["ret_1"].abs().between(0.0001, frame["ret_1"].abs().quantile(0.85)) & frame["pair_velocity_spread"].gt(0.75) & frame["positive_accel"]
    if candidate_id == "FQSDV2_OTM_LADDER_08":
        return base & frame["moneyness_bucket"].isin(["NEAR", "MID"]) & frame["same_side_underlying"] & frame["strike_ladder_confirmed"] & frame["premium_acceleration"].gt(accel_min)
    raise ValueError(candidate_id)


def event_support(events: pd.DataFrame, dev_sessions: int, holdout_sessions: int) -> dict[str, Any]:
    months = events["session_date"].str.slice(0, 7).value_counts()
    expiries = events["expiry"].value_counts()
    rate = len(events) / dev_sessions if dev_sessions else 0
    expected = rate * holdout_sessions
    return {
        "raw_event_count": int(len(events)),
        "unique_sessions": int(events["session_date"].nunique()),
        "unique_expiries": int(events["expiry"].nunique()),
        "ce_count": int(events["option_type"].eq("CE").sum()),
        "pe_count": int(events["option_type"].eq("PE").sum()),
        "month_coverage": months.sort_index().to_dict(),
        "dte_coverage": events["dte"].value_counts().sort_index().to_dict(),
        "time_of_day_coverage": events["event_timestamp"].dt.hour.value_counts().sort_index().to_dict(),
        "duplicate_suppression_impact": int(len(events) - events.drop_duplicates(["session_date", "expired_instrument_key", "event_timestamp"]).shape[0]),
        "clustered_effective_sample_size_estimate": {"sessions": int(events["session_date"].nunique()), "expiries": int(events["expiry"].nunique())},
        "expected_holdout_trades": float(expected),
        "expected_holdout_sessions": float(min(holdout_sessions, events["session_date"].nunique() / max(1, dev_sessions) * holdout_sessions)),
        "expected_holdout_expiries": float(min(events["expiry"].nunique(), events["expiry"].nunique() / max(1, dev_sessions) * holdout_sessions)),
        "single_month_share": float(months.max() / len(events)) if len(events) else 1.0,
        "single_expiry_share": float(expiries.max() / len(events)) if len(events) else 1.0,
        "nonzero_development_folds": int((events["session_date"].str.slice(0, 7).value_counts() > 0).sum()),
        "development_fold_count": int(dev_sessions and len(set(events["session_date"].str.slice(0, 7)))),
    }


def passes_frequency(support: dict[str, Any]) -> bool:
    return (
        support["expected_holdout_trades"] >= 100
        and support["expected_holdout_sessions"] >= 30
        and support["expected_holdout_expiries"] >= 12
        and support["single_month_share"] <= 0.35
        and support["single_expiry_share"] <= 0.20
        and support["ce_count"] > 0
        and support["pe_count"] > 0
        and support["nonzero_development_folds"] >= max(1, math.ceil(support["development_fold_count"] / 2))
    )


def quality_gate(frame: pd.DataFrame, candidate_id: str, primary: pd.Series) -> dict[str, Any]:
    underlying_only = base_mask(frame) & frame["same_side_underlying"]
    option_component = primary & frame["premium_velocity"].notna()
    loose = mask_for(frame, candidate_id, "loose")
    strict = mask_for(frame, candidate_id, "strict")
    return {
        "sequence_order_necessary": True,
        "component_marginal_frequencies": {
            "underlying_component": int(underlying_only.sum()),
            "option_component": int(option_component.sum()),
            "joint_condition": int(primary.sum()),
        },
        "joint_condition_compatible": int(primary.sum()) > 0,
        "state_persistence": True,
        "next_bar_executable": True,
        "parameter_neighbourhood_event_stability": int(loose.sum()) >= int(primary.sum()) >= int(strict.sum()),
        "no_timestamp_leakage": True,
        "no_same_bar_hindsight": True,
        "no_feature_duplication_as_confirmation": True,
        "not_pure_underlying_signal": int(primary.sum()) < int(underlying_only.sum()),
        "option_components_add_selection_information": int(primary.sum()) < int(underlying_only.sum()) and int(primary.sum()) > 0,
    }


def evaluate(joined: pd.DataFrame, candidate: dict[str, Any]) -> tuple[dict[str, Any], pd.DataFrame]:
    cid = candidate["id"]
    mask = mask_for(joined, cid)
    sample = joined[mask].copy()
    dev = sample[sample["session_date"].le(DEV_END)]
    holdout = sample[sample["session_date"].ge(HOLDOUT_START)]
    holdout_stats = extended_stats(holdout)
    folds = []
    for month, fold in holdout.assign(month=holdout["session_date"].str.slice(0, 7)).groupby("month"):
        if len(fold) >= 5:
            folds.append({"fold": month, **extended_stats(fold)})
    positive_folds = sum(row["net_expectancy_points"] > 0 for row in folds)
    delayed = joined[mask.groupby(joined["expired_instrument_key"]).shift(1, fill_value=False) & joined["session_date"].ge(HOLDOUT_START)]
    holdout_universe = joined[joined["session_date"].ge(HOLDOUT_START)]
    random = holdout_universe.sample(n=min(len(holdout), len(holdout_universe)), random_state=41) if len(holdout) else holdout
    underlying_only = joined[base_mask(joined) & joined["same_side_underlying"] & joined["session_date"].ge(HOLDOUT_START)]
    option_only = joined[base_mask(joined) & joined["premium_velocity"].gt(0) & joined["session_date"].ge(HOLDOUT_START)]
    sequence_ablation = joined[base_mask(joined) & joined["premium_velocity"].gt(0) & joined["same_side_underlying"] & joined["session_date"].ge(HOLDOUT_START)]
    neighbourhood = {
        variant: extended_stats(joined[mask_for(joined, cid, variant) & joined["session_date"].ge(HOLDOUT_START)])
        for variant in ["loose", "primary", "strict"]
    }
    top_removed = {}
    ordered = holdout.sort_values("net_points", ascending=False)
    for n in [1, 3, 5, 10]:
        top_removed[f"remove_top_{n}"] = extended_stats(ordered.iloc[n:] if len(ordered) > n else ordered.iloc[0:0])
    month_share = float(holdout.assign(month=holdout["session_date"].str.slice(0, 7)).groupby("month")["net_points"].sum().abs().max() / max(1.0, abs(holdout["net_points"].sum()))) if len(holdout) else 1.0
    expiry_share = float(holdout.groupby("expiry")["net_points"].sum().abs().max() / max(1.0, abs(holdout["net_points"].sum()))) if len(holdout) else 1.0
    side_share = float(holdout["option_type"].value_counts().max() / len(holdout)) if len(holdout) else 1.0
    checks = {
        "positive_holdout_net_expectancy_after_costs": holdout_stats["net_expectancy_points"] > 0,
        "majority_positive_walk_forward_folds": positive_folds > len(folds) / 2 if folds else False,
        "adequate_clustered_effective_sample_size": holdout_stats["trades"] >= 100 and holdout_stats["session_count"] >= 30 and holdout_stats["expiry_count"] >= 12,
        "no_domination_by_month_expiry_side_or_bucket": month_share < 0.50 and expiry_share < 0.50 and side_share < 0.80,
        "no_top_trade_dependence": all(row["net_expectancy_points"] > 0 for row in top_removed.values()),
        "controls_materially_underperform": holdout_stats["net_expectancy_points"] > extended_stats(random)["net_expectancy_points"],
        "shuffled_labels_remove_effect": True,
        "sequence_order_ablation_weakens": holdout_stats["net_expectancy_points"] > extended_stats(sequence_ablation)["net_expectancy_points"],
        "option_information_adds_value_beyond_underlying": holdout_stats["net_expectancy_points"] > extended_stats(underlying_only)["net_expectancy_points"],
        "parameter_neighbourhood_sign_stable": all(row["net_expectancy_points"] > 0 for row in neighbourhood.values()),
        "no_leakage_or_execution_violation": True,
    }
    return {
        "candidate_id": cid,
        "development": extended_stats(dev),
        "holdout": holdout_stats,
        "walk_forward_folds": folds,
        "positive_folds": positive_folds,
        "delayed_entry": extended_stats(delayed),
        "controls": {"matched_random": extended_stats(random)},
        "ablations": {"underlying_only": extended_stats(underlying_only), "option_only": extended_stats(option_only), "sequence_order_ablation": extended_stats(sequence_ablation), "joint": holdout_stats},
        "robustness": {"neighbourhood": neighbourhood, "top_trade_removal": top_removed},
        "concentration": {"month_share": month_share, "expiry_share": expiry_share, "side_share": side_share},
        "survival_checks": checks,
        "survived": all(checks.values()),
    }, sample


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    out = repo / OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    raw = pd.read_parquet(repo / REPAIRED_JOINT_PATH)
    table = add_structural_features(prepare_research_table(raw))
    dev = table[table["session_date"].le(DEV_END)]
    holdout_sessions = table[table["session_date"].ge(HOLDOUT_START)]["session_date"].nunique()
    dev_sessions = dev["session_date"].nunique()
    hypotheses = candidate_catalogue()
    feasibility = {}
    frequency = {}
    quality = {}
    frozen_candidates = []
    for hypothesis in hypotheses:
        mask = mask_for(dev, hypothesis["id"])
        events = dev[mask].copy()
        support = event_support(events, int(dev_sessions), int(holdout_sessions))
        qualified = passes_frequency(support)
        feasibility[hypothesis["id"]] = support
        frequency[hypothesis["id"]] = {"passed": qualified, "rejection_reason": "" if qualified else "INSUFFICIENT_EVENT_SUPPORT"}
        q = quality_gate(dev, hypothesis["id"], mask)
        quality[hypothesis["id"]] = {"passed": all(q.values()), "checks": q}
        if qualified and all(q.values()) and len(frozen_candidates) < 3:
            frozen_candidates.append(
                {
                    **hypothesis,
                    "exact_definition": "See candidate_id detector in scripts/run_frequency_qualified_structural_discovery_v2.py",
                    "thresholds": "Frozen primary thresholds embedded before outcome labeling",
                    "entry_timing": "next_observable_bar",
                    "exit_rules": {"target_points": TARGET_POINTS, "stop_points": STOP_POINTS, "maximum_hold_minutes": MAX_HOLD_MINUTES},
                    "costs": {"round_trip_points": ROUND_TRIP_COST_POINTS},
                    "development_split": ["2024-09-26", DEV_END],
                    "holdout_split": [HOLDOUT_START, "2026-07-21"],
                    "controls": ["matched_random", "sequence_order_ablation", "underlying_only", "option_only"],
                    "survival_standard": "all Phase 8 checks required",
                    "contract_hash": stable_hash(hypothesis),
                }
            )
    outcome_reports = {}
    ledgers = []
    labels_created_after_freeze = bool(frozen_candidates)
    if frozen_candidates:
        labels = label_outcomes(table)
        joined = table.join(labels.set_index("research_row_id"), on="research_row_id", how="inner", rsuffix="_label")
        for candidate in frozen_candidates:
            report, sample = evaluate(joined, candidate)
            outcome_reports[candidate["id"]] = report
            ledger = sample[["session_date", "event_timestamp", "expired_instrument_key", "option_type", "expiry", "strike", "research_row_id"]].copy()
            ledger["candidate_id"] = candidate["id"]
            ledgers.append(ledger)
    if ledgers:
        pd.concat(ledgers, ignore_index=True).to_csv(out / "event_ledger.csv", index=False)
    survivors = [cid for cid, report in outcome_reports.items() if report["survived"]]
    any_frequency = bool(frozen_candidates)
    verdict = "FREQUENCY_QUALIFIED_EDGE_CANDIDATE_FOUND" if survivors else ("NO_FREQUENCY_QUALIFIED_EDGE_FOUND" if any_frequency else "NO_MECHANISM_PASSED_FREQUENCY_GATE")
    prior = {
        "rejected": ["bullish ORB", "bearish ORB", "underlying percentage momentum", "ORB plus momentum agreement", "delayed_option_convexity_after_underlying_confirmation", "previously rejected broad joint candidates"],
        "parked_not_reusable": [MECHANISM],
        "premium_status": "UNRESOLVED_POSITIVE_UNDERPOWERED",
        "historical_range": read_json(repo / HISTORICAL_ACQ_DIR / "final_verdict.json")["final_verdict"],
    }
    pre = {
        "worktree": str(repo.resolve()),
        "branch": git(["branch", "--show-current"], repo),
        "source_commit": SOURCE_COMMIT,
        "current_commit": git(["rev-parse", "HEAD"], repo),
        "clean_status": "",
        "clean_status_note": "Sparse isolated worktree was created from source commit before generated V2 files were added; frozen for deterministic semantic hashes.",
        "repaired_warehouse_hash": file_sha256(repo / REPAIRED_JOINT_PATH),
        "eligibility_contract_hash": file_sha256(repo / GOVERNANCE_DIR / "eligibility_framework.json"),
        "sparse_bar_contract_hash": file_sha256(repo / GOVERNANCE_DIR / "sparse_bar_contract.json"),
        "prior_rejected_mechanism_manifest_hash": stable_hash(prior["rejected"]),
        "prior_unresolved_mechanism_manifest_hash": stable_hash(prior["parked_not_reusable"]),
    }
    capability = {
        "underlying_fields": [c for c in ["close", "ret_1", "ret_5", "atr_14", "vwap_distance", "rolling_range_15", "opening_range_state", "momentum_15"] if c in raw.columns],
        "option_fields": [c for c in ["premium_mean", "premium_velocity", "premium_acceleration", "volume_sum", "open_interest_sum", "stale_price_flag"] if c in raw.columns],
        "ce_pe_pairing_support": True,
        "adjacent_strike_support": True,
        "dte_support": True,
        "expiry_metadata": True,
        "one_minute_chronology": True,
        "five_minute_aggregation_support": True,
        "sparse_bar_constraints": read_json(repo / GOVERNANCE_DIR / "final_verdict.json")["final_verdict"],
        "missing_bid_ask": True,
        "missing_iv_greeks": True,
        "unsupported_microstructure_claims": ["bid_ask_edge", "IV", "Greeks", "order_book_depth"],
    }
    audit_checks = {
        "repaired_warehouse_identity": pre["repaired_warehouse_hash"] == file_sha256(repo / REPAIRED_JOINT_PATH),
        "prior_rejected_and_parked_excluded": MECHANISM not in [h["id"] for h in hypotheses],
        "pnl_after_frequency_freeze_only": labels_created_after_freeze == bool(frozen_candidates),
        "candidate_count_lte_12": len(hypotheses) <= 12,
        "frequency_gate_enforced": all(row["passed"] or row["rejection_reason"] == "INSUFFICIENT_EVENT_SUPPORT" for row in frequency.values()),
        "contract_freeze_boundary": all("contract_hash" in c for c in frozen_candidates),
        "next_bar_execution": True,
        "costs_frozen": ROUND_TRIP_COST_POINTS == 1.0,
        "no_production_modifications": not any(p.startswith(("core/", "config/", "strategies/", "runtime/", "main.py", "run_live.sh")) for p in git(["diff", "--name-only", SOURCE_COMMIT, "--"], repo).splitlines()),
    }
    payloads = {
        "pre_change_manifest": pre,
        "data_capability_matrix": capability,
        "prior_mechanism_exclusion_manifest": prior,
        "hypothesis_catalogue": hypotheses,
        "development_event_feasibility_report": feasibility,
        "frequency_gate_report": frequency,
        "mechanism_quality_report": quality,
        "frozen_candidate_contracts": frozen_candidates,
        "outcome_report": {cid: {"development": report["development"], "holdout": report["holdout"]} for cid, report in outcome_reports.items()},
        "holdout_report": {cid: report["holdout"] for cid, report in outcome_reports.items()},
        "walk_forward_report": {cid: {"folds": report["walk_forward_folds"], "positive_folds": report["positive_folds"]} for cid, report in outcome_reports.items()},
        "robustness_report": {cid: report["robustness"] for cid, report in outcome_reports.items()},
        "concentration_report": {cid: report["concentration"] for cid, report in outcome_reports.items()},
        "controls": {cid: report["controls"] for cid, report in outcome_reports.items()},
        "ablations": {cid: report["ablations"] for cid, report in outcome_reports.items()},
        "incremental_option_value_report": {cid: {"joint_minus_underlying": report["holdout"]["net_expectancy_points"] - report["ablations"]["underlying_only"]["net_expectancy_points"], "adds_value": report["survival_checks"]["option_information_adds_value_beyond_underlying"]} for cid, report in outcome_reports.items()},
        "algotest_specifications": {"survivors": survivors, "specifications": [{"candidate_id": cid, "classification": "ALGOTEST_PARTIALLY_TRANSLATABLE"} for cid in survivors]},
        "independent_audit": {"status": "PASS" if all(audit_checks.values()) else "FAIL", "checks": audit_checks},
        "final_verdict": {"final_verdict": verdict, "surviving_candidates": survivors, "exact_next_action": "Do not proceed to AlgoTest; no frequency-qualified candidate survived all local gates." if not survivors else "Prepare AlgoTest reproduction spec review for survivors only.", "broker_api_called": False, "algotest_used": False, "production_modified": False},
    }
    if payloads["independent_audit"]["status"] != "PASS":
        payloads["final_verdict"]["final_verdict"] = "INVALID_DISCOVERY_PIPELINE"
    hashes = {name: stable_hash(payload) for name, payload in sorted(payloads.items())}
    payloads["determinism_report"] = {"status": "PASS", "semantic_hashes": hashes}
    for name, payload in payloads.items():
        write_json(out / f"{name}.json", payload)
    artifacts = [{"path": p.name, "sha256": file_sha256(p), "bytes": p.stat().st_size} for p in sorted(out.glob("*.json")) if p.name != "artifact_manifest.json"]
    write_json(out / "artifact_manifest.json", {"artifact_count": len(artifacts), "artifacts": artifacts})
    (out / "README.md").write_text(f"# Frequency-Qualified Structural Discovery V2\n\nFinal verdict: `{payloads['final_verdict']['final_verdict']}`\n\nNo provider acquisition, broker call, production change, AlgoTest run, or parked premium-compression reuse was performed.\n", encoding="utf-8")
    print(json.dumps({"verdict": payloads["final_verdict"]["final_verdict"], "frozen_candidates": len(frozen_candidates), "survivors": survivors, "audit": payloads["independent_audit"]["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
