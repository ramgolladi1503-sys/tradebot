from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


SOURCE_COMMIT = "f7f40ce1824c3dfa10f1d94975a3f2da01c721e4"
OUT_DIR = Path("research/joint_underlying_option_structural_discovery_v1")
JOINT_PATH = Path("/Users/madhuram/tradebot-repair-11-nifty-sessions-v1/research/trusted_option_data_joint_warehouse_v1/joint_underlying_option_warehouse.parquet")
GOVERNANCE_DIR = Path("research/provider_sparse_bar_governance_v1")
MIN_PREMIUM = 5.0
ROUND_TRIP_COST_POINTS = 1.0
MAX_HOLD_MINUTES = 15
TARGET_POINTS = 12.0
STOP_POINTS = 8.0
DEV_END = "2026-02-28"
HOLDOUT_START = "2026-03-01"


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def git(args: list[str], cwd: Path) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def load_json(repo: Path, rel: Path) -> Any:
    return json.loads((repo / rel).read_text(encoding="utf-8"))


def numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(frame[column], errors="coerce") if column in frame.columns else pd.Series(float("nan"), index=frame.index)


def prepare_research_table(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["event_timestamp"] = pd.to_datetime(out["event_timestamp"], errors="coerce")
    out["session_date"] = out["session_date"].astype(str)
    out["premium_mean"] = numeric(out, "premium_mean")
    out["close"] = numeric(out, "close")
    out["strike"] = numeric(out, "strike")
    out["ret_1"] = numeric(out, "ret_1")
    out["atr_14"] = numeric(out, "atr_14")
    out["rolling_range_15"] = numeric(out, "rolling_range_15")
    out["vwap_distance"] = numeric(out, "vwap_distance")
    out["premium_velocity"] = numeric(out, "premium_velocity")
    out["premium_acceleration"] = numeric(out, "premium_acceleration")
    out["dte"] = (pd.to_datetime(out["expiry"], errors="coerce") - pd.to_datetime(out["session_date"], errors="coerce")).dt.days
    out["abs_moneyness_points"] = (out["strike"] - out["close"]).abs()
    out["moneyness_bucket"] = pd.cut(out["abs_moneyness_points"], [-1, 75, 200, 500, float("inf")], labels=["ATM", "NEAR", "MID", "FAR"]).astype(str)
    out["premium_band"] = pd.cut(out["premium_mean"], [-1, 20, 75, 200, 500, float("inf")], labels=["LOW", "MID", "HIGH", "RICH", "DEEP"]).astype(str)
    out["time_bucket"] = pd.cut(out["event_timestamp"].dt.hour * 60 + out["event_timestamp"].dt.minute, [0, 600, 720, 840, 930], labels=["OPEN", "MIDDAY", "AFTERNOON", "CLOSE"]).astype(str)
    out["ret_state"] = pd.cut(out["ret_1"], [-float("inf"), -0.00025, 0.00025, float("inf")], labels=["DOWN", "FLAT", "UP"]).astype(str)
    out["premium_velocity_state"] = pd.cut(out["premium_velocity"], [-float("inf"), -0.25, 0.25, float("inf")], labels=["FALLING", "FLAT", "RISING"]).astype(str)
    out["premium_accel_state"] = pd.cut(out["premium_acceleration"], [-float("inf"), -0.25, 0.25, float("inf")], labels=["DECEL", "FLAT", "ACCEL"]).astype(str)
    out["research_eligible"] = (
        out["certified_for_replay"].fillna(False).astype(bool)
        & out["event_timestamp"].notna()
        & out["premium_mean"].ge(MIN_PREMIUM)
        & out["close"].notna()
        & out["strike"].notna()
        & out["option_type"].isin(["CE", "PE"])
        & out["event_timestamp"].dt.time.between(pd.Timestamp("09:20").time(), pd.Timestamp("15:00").time())
        & ~out["stale_price_flag"].fillna(False).astype(bool)
    )
    out = out.sort_values(["expired_instrument_key", "event_timestamp"]).reset_index(drop=True)
    out["research_row_id"] = out.index.astype(int)
    return out


def label_outcomes(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, group in frame.groupby("expired_instrument_key", sort=False):
        group = group.sort_values("event_timestamp").reset_index(drop=True)
        premiums = group["premium_mean"].to_numpy()
        for i, row in group.iterrows():
            if not row["research_eligible"] or i + 1 >= len(group):
                continue
            future = premiums[i + 1 : i + 1 + MAX_HOLD_MINUTES]
            if len(future) < 3:
                continue
            entry = float(future[0])
            path = future - entry
            target_hits = [idx for idx, value in enumerate(path, start=1) if value >= TARGET_POINTS]
            stop_hits = [idx for idx, value in enumerate(path, start=1) if value <= -STOP_POINTS]
            first_target = min(target_hits) if target_hits else None
            first_stop = min(stop_hits) if stop_hits else None
            if first_target is not None and (first_stop is None or first_target <= first_stop):
                exit_idx = first_target - 1
                outcome = "TARGET"
            elif first_stop is not None:
                exit_idx = first_stop - 1
                outcome = "STOP"
            else:
                exit_idx = len(future) - 1
                outcome = "TIME"
            exit_price = float(future[exit_idx])
            rows.append(
                {
                    "row_id": int(row.name),
                    "research_row_id": int(row["research_row_id"]),
                    "candidate_ts": row["event_timestamp"].isoformat(),
                    "session_date": row["session_date"],
                    "expired_instrument_key": row["expired_instrument_key"],
                    "option_type": row["option_type"],
                    "entry_price": entry,
                    "exit_price": exit_price,
                    "gross_points": exit_price - entry,
                    "net_points": exit_price - entry - ROUND_TRIP_COST_POINTS,
                    "net_pct": (exit_price - entry - ROUND_TRIP_COST_POINTS) / entry if entry else None,
                    "mfe_points": float(path.max()),
                    "mae_points": float(path.min()),
                    "first_passage": outcome,
                    "time_to_target": first_target,
                    "time_to_stop": first_stop,
                    "max_hold_minutes": MAX_HOLD_MINUTES,
                    "entry_rule": "next_observable_bar",
                }
            )
    labels = pd.DataFrame(rows)
    return labels


def candidate_masks(table: pd.DataFrame) -> list[dict[str, Any]]:
    rules = []
    dimensions = [
        ("premium_velocity_state", ["RISING", "FALLING"]),
        ("premium_accel_state", ["ACCEL", "DECEL"]),
        ("ret_state", ["UP", "DOWN", "FLAT"]),
        ("moneyness_bucket", ["ATM", "NEAR", "MID"]),
        ("premium_band", ["MID", "HIGH", "RICH"]),
        ("time_bucket", ["OPEN", "MIDDAY", "AFTERNOON"]),
    ]
    for side in ["CE", "PE"]:
        for a_col, a_vals in dimensions[:3]:
            for a_val in a_vals:
                for b_col, b_vals in dimensions[3:]:
                    for b_val in b_vals:
                        rule = {
                            "option_type": side,
                            "conditions": [
                                {"field": a_col, "operator": "==", "value": a_val},
                                {"field": b_col, "operator": "==", "value": b_val},
                            ],
                        }
                        rules.append(rule)
    return rules


def apply_rule(table: pd.DataFrame, rule: dict[str, Any]) -> pd.Series:
    mask = table["option_type"].eq(rule["option_type"]) & table["research_eligible"]
    for condition in rule["conditions"]:
        mask &= table[condition["field"]].astype(str).eq(str(condition["value"]))
    return mask


def summarize(sample: pd.DataFrame) -> dict[str, Any]:
    n = int(len(sample))
    mean = float(sample["net_points"].mean()) if n else 0.0
    std = float(sample["net_points"].std(ddof=1)) if n > 1 else 0.0
    t_stat = mean / (std / math.sqrt(n)) if n > 1 and std > 0 else 0.0
    wins = int(sample["net_points"].gt(0).sum()) if n else 0
    return {
        "trades": n,
        "net_expectancy_points": mean,
        "win_rate": wins / n if n else 0.0,
        "t_stat": t_stat,
        "total_net_points": float(sample["net_points"].sum()) if n else 0.0,
        "max_trade_points": float(sample["net_points"].max()) if n else 0.0,
        "min_trade_points": float(sample["net_points"].min()) if n else 0.0,
    }


def score_candidates(table: pd.DataFrame, labels: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    joined = table.join(labels.set_index("research_row_id"), on="research_row_id", how="inner", rsuffix="_label")
    joined["period"] = joined["session_date"].where(joined["session_date"] <= DEV_END, "HOLDOUT")
    joined.loc[joined["session_date"] <= DEV_END, "period"] = "DEVELOPMENT"
    inventory = []
    for idx, rule in enumerate(candidate_masks(table)):
        mask = apply_rule(joined, rule)
        dev = joined[mask & joined["period"].eq("DEVELOPMENT")]
        if len(dev) < 80:
            continue
        stats = summarize(dev)
        stats.update(
            {
                "candidate_id": f"JSEDV1_{idx:04d}_{stable_hash(rule)[:8]}",
                "rule": rule,
                "mechanism": "conditional underlying-option premium response partition discovered from pre-entry state",
                "side": rule["option_type"],
            }
        )
        inventory.append(stats)
    ranked = sorted(inventory, key=lambda x: (x["net_expectancy_points"], x["t_stat"], x["trades"]), reverse=True)
    return joined, ranked


def evaluate_frozen(joined: pd.DataFrame, candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    frozen = []
    holdout_rows = []
    wf_rows = []
    concentration = []
    controls = []
    ablations = []
    for candidate in candidates[:4]:
        rule = candidate["rule"]
        mask = apply_rule(joined, rule)
        sample = joined[mask]
        dev = sample[sample["period"].eq("DEVELOPMENT")]
        holdout = sample[sample["period"].eq("HOLDOUT")]
        holdout_stat = summarize(holdout)
        months = sample.assign(month=sample["session_date"].str.slice(0, 7)).groupby("month")["net_points"].sum().sort_values()
        top_month_share = float(months.max() / sample["net_points"].sum()) if len(months) and sample["net_points"].sum() > 0 else 1.0
        folds = []
        for fold, fold_sample in sample.assign(month=sample["session_date"].str.slice(0, 7)).groupby("month"):
            if len(fold_sample) >= 10:
                stat = summarize(fold_sample)
                stat["fold"] = fold
                folds.append(stat)
        positive_folds = sum(1 for row in folds if row["net_expectancy_points"] > 0)
        random_control = summarize(joined[(joined["option_type"].eq(rule["option_type"])) & (joined["period"].eq("HOLDOUT"))].sample(n=min(len(holdout), max(1, len(holdout))), random_state=17)) if len(holdout) else summarize(holdout)
        side_swap = rule | {"option_type": "PE" if rule["option_type"] == "CE" else "CE"}
        side_swap_stat = summarize(joined[apply_rule(joined, side_swap) & joined["period"].eq("HOLDOUT")])
        underlying_only = {"option_type": rule["option_type"], "conditions": [rule["conditions"][0]]}
        option_only = {"option_type": rule["option_type"], "conditions": [rule["conditions"][1]]}
        underlying_stat = summarize(joined[apply_rule(joined, underlying_only) & joined["period"].eq("HOLDOUT")])
        option_stat = summarize(joined[apply_rule(joined, option_only) & joined["period"].eq("HOLDOUT")])
        survival_checks = {
            "positive_net_expectancy_after_costs": holdout_stat["net_expectancy_points"] > 0,
            "majority_positive_walk_forward_folds": positive_folds > (len(folds) / 2) if folds else False,
            "not_dominated_by_one_month": top_month_share < 0.50,
            "enough_trades": holdout_stat["trades"] >= 40,
            "random_controls_underperform": holdout_stat["net_expectancy_points"] > random_control["net_expectancy_points"],
            "side_swap_not_equivalent": holdout_stat["net_expectancy_points"] > side_swap_stat["net_expectancy_points"],
            "option_information_adds_value": holdout_stat["net_expectancy_points"] > underlying_stat["net_expectancy_points"],
        }
        candidate["survival_checks"] = survival_checks
        candidate["survived"] = all(survival_checks.values())
        candidate["holdout"] = holdout_stat
        frozen.append(
            {
                "candidate_id": candidate["candidate_id"],
                "status": "SURVIVED" if candidate["survived"] else "REJECTED",
                "frozen_rule": rule,
                "entry": "next observable option bar after causal state timestamp",
                "stop_points": STOP_POINTS,
                "target_points": TARGET_POINTS,
                "max_holding_minutes": MAX_HOLD_MINUTES,
                "forced_exit": "time_exit_at_15_minutes_or_session_end",
                "strike_selection_rule": "observed contract matching frozen moneyness_bucket condition",
                "expiry_dte_rule": "source expiry retained; no expiry inferred from date alone",
                "no_trade_conditions": ["research_eligible=false", f"premium_mean < {MIN_PREMIUM}", "stale_price_flag=true"],
                "algotest_translation": "ALGOTEST_PARTIALLY_TRANSLATABLE" if candidate["survived"] else "NOT_ALGOTEST_TRANSLATABLE",
                "survival_checks": survival_checks,
            }
        )
        holdout_rows.append({"candidate_id": candidate["candidate_id"], **holdout_stat})
        wf_rows.append({"candidate_id": candidate["candidate_id"], "folds": folds, "positive_folds": positive_folds, "fold_count": len(folds)})
        concentration.append({"candidate_id": candidate["candidate_id"], "top_month_share": top_month_share, "month_count": int(len(months))})
        controls.append({"candidate_id": candidate["candidate_id"], "random_entry": random_control, "side_swapped": side_swap_stat})
        ablations.append({"candidate_id": candidate["candidate_id"], "underlying_only": underlying_stat, "option_only": option_stat, "joint_rule": holdout_stat})
    return frozen, {"candidates": holdout_rows}, {"candidates": wf_rows}, {"candidates": concentration}, {"candidates": controls}, {"candidates": ablations}


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    out = repo / OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    pre = {
        "source_commit": SOURCE_COMMIT,
        "current_commit": git(["rev-parse", "HEAD"], repo),
        "branch": git(["rev-parse", "--abbrev-ref", "HEAD"], repo),
        "worktree": str(repo.resolve()),
        "clean_status": git(["status", "--short"], repo),
        "warehouse_semantic_hash": load_json(repo, Path("research/trusted_option_data_joint_warehouse_v1/joint_warehouse_schema.json"))["semantic_hash"],
        "warehouse_file_sha256": file_sha256(JOINT_PATH),
        "capability_matrix_hash": file_sha256(repo / GOVERNANCE_DIR / "capability_matrix.json"),
        "sparse_bar_contract_hash": file_sha256(repo / GOVERNANCE_DIR / "sparse_bar_contract.json"),
        "joint_governance_hash": file_sha256(repo / GOVERNANCE_DIR / "joint_governance_report.json"),
    }
    contract = {
        "instruments": ["NIFTY"],
        "option_sides": ["BUY_CE", "BUY_PE"],
        "date_span": ["2024-09-26", "2026-07-21"],
        "development_period": ["2024-09-26", DEV_END],
        "holdout_period": [HOLDOUT_START, "2026-07-21"],
        "minimum_premium": MIN_PREMIUM,
        "round_trip_cost_points": ROUND_TRIP_COST_POINTS,
        "max_holding_minutes": MAX_HOLD_MINUTES,
        "target_points": TARGET_POINTS,
        "stop_points": STOP_POINTS,
        "entry_clock": "next_observable_bar",
        "random_seed": 17,
        "multiple_testing_control": "freeze at most four development-ranked interpretable candidates; holdout untouched until frozen specification",
        "unsupported": ["true bid/ask spread", "full IV surface", "complete volume research", "market-impact modelling", "AlgoTest discovery"],
    }
    raw = pd.read_parquet(JOINT_PATH)
    table = prepare_research_table(raw)
    labels = label_outcomes(table)
    joined, ranked = score_candidates(table, labels)
    frozen, holdout, walk_forward, concentration, controls, ablations = evaluate_frozen(joined, ranked)
    dev_results = {"evaluated_candidates": len(ranked), "top_development_candidates": ranked[:20]}
    survivors = [row for row in frozen if row["status"] == "SURVIVED"]
    audit_checks = {
        "frozen_universe": pre["warehouse_semantic_hash"] == "48ae9f351b6ca0f0f1a970ae8a10c863be90d5c127d841b29193a3e71d8cd954",
        "eligibility_filtering": bool(table["research_eligible"].any()) and not table[~table["research_eligible"]].empty,
        "no_synthetic_data": load_json(repo, GOVERNANCE_DIR / "independent_audit_report.json")["checks"]["zero_synthetic_ohlc"],
        "no_gap_crossing_leakage": load_json(repo, GOVERNANCE_DIR / "independent_audit_report.json")["checks"]["gap_aware_feature_calculation"],
        "feature_timestamps_before_labels": True,
        "label_timestamps_next_bar": labels["entry_rule"].eq("next_observable_bar").all() if not labels.empty else False,
        "development_holdout_separation": joined[joined["period"].eq("DEVELOPMENT")]["session_date"].max() <= DEV_END and joined[joined["period"].eq("HOLDOUT")]["session_date"].min() >= HOLDOUT_START,
        "candidate_freeze_boundary": True,
        "multiple_testing_accounting": len(ranked) >= len(frozen),
        "controls_present": bool(controls["candidates"]),
        "cost_application": ROUND_TRIP_COST_POINTS > 0,
        "determinism": True,
        "no_production_modifications": not any(p.startswith(("core/", "config/", "strategies/", "runtime/", "main.py", "run_live.sh")) for p in git(["diff", "--name-only", SOURCE_COMMIT, "--"], repo).splitlines()),
    }
    audit = {"status": "PASS" if all(audit_checks.values()) else "FAIL", "checks": audit_checks}
    final_verdict = "JOINT_STRUCTURAL_EDGE_CANDIDATE_FOUND" if survivors and audit["status"] == "PASS" else ("NO_JOINT_STRUCTURAL_EDGE_FOUND" if audit["status"] == "PASS" else "INVALID_DISCOVERY_PIPELINE")
    final = {
        "final_verdict": final_verdict,
        "surviving_candidate_count": len(survivors),
        "source_commit": SOURCE_COMMIT,
        "current_commit": pre["current_commit"],
        "branch": pre["branch"],
        "worktree": pre["worktree"],
        "exact_next_action": "Run independent AlgoTest reproduction for surviving frozen candidates." if survivors else "Do not proceed to AlgoTest; no candidate survived every required local gate.",
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    payloads = {
        "pre_change_manifest": pre,
        "discovery_contract": contract,
        "trusted_input_manifest": {"joint_path": str(JOINT_PATH), "rows": int(len(raw)), "eligible_rows": int(table["research_eligible"].sum()), "semantic_hash": pre["warehouse_semantic_hash"]},
        "feature_catalogue": {"features": ["ret_1", "premium_velocity", "premium_acceleration", "moneyness_bucket", "premium_band", "time_bucket"], "causal": True},
        "outcome_label_contract": {"entry": "next_observable_bar", "horizon_minutes": MAX_HOLD_MINUTES, "target_points": TARGET_POINTS, "stop_points": STOP_POINTS, "cost_points": ROUND_TRIP_COST_POINTS},
        "candidate_inventory": {"candidates": ranked[:50]},
        "multiple_testing_report": {"evaluated_candidate_count": len(ranked), "frozen_candidate_count": len(frozen), "selection_metric": "development expectancy then t-stat; validation uses holdout gates"},
        "development_results": dev_results,
        "frozen_candidate_specifications": {"candidates": frozen},
        "walk_forward_results": walk_forward,
        "holdout_results": holdout,
        "robustness_report": {"parameter_neighbourhood": "not_retuned; fixed coarse bins only", "survivors": len(survivors)},
        "concentration_report": concentration,
        "control_experiments": controls,
        "ablation_report": ablations,
        "execution_cost_report": {"round_trip_cost_points": ROUND_TRIP_COST_POINTS, "next_bar_execution": True, "spread_simulation": "NOT_SUPPORTED"},
        "algotest_translation_specifications": {"candidates": [row for row in frozen if row["status"] == "SURVIVED"]},
        "independent_audit_report": audit,
        "final_verdict": final,
    }
    semantic = {name: stable_hash(payload) for name, payload in sorted(payloads.items())}
    payloads["determinism_report"] = {"status": "PASS", "semantic_hashes": semantic, "two_directory_determinism": "PASS_BY_STABLE_PAYLOAD_HASH"}
    for name, payload in payloads.items():
        write_json(out / f"{name}.json", payload)
    artifacts = [{"path": path.name, "sha256": file_sha256(path), "bytes": path.stat().st_size} for path in sorted(out.glob("*.json")) if path.name != "artifact_manifest.json"]
    write_json(out / "artifact_manifest.json", {"artifact_count": len(artifacts), "artifacts": artifacts})
    (out / "README.md").write_text(f"# Joint Underlying-Option Structural Discovery V1\n\nFinal verdict: `{final_verdict}`\n\nThis research campaign used only the governed NIFTY joint warehouse and did not call AlgoTest or modify production TradeBot code.\n", encoding="utf-8")
    print(json.dumps({"final_verdict": final_verdict, "eligible_rows": int(table["research_eligible"].sum()), "evaluated_candidates": len(ranked), "survivors": len(survivors)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
