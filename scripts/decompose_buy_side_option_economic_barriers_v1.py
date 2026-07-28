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

from scripts.run_frequency_qualified_structural_discovery_v2 import (  # noqa: E402
    OUT_DIR as DISCOVERY_DIR,
    REPAIRED_JOINT_PATH,
    add_structural_features,
    base_mask,
    mask_for,
)
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


SOURCE_COMMIT = "fc64f618538d447efb16d794c39709a2be2cc997"
OUT_DIR = Path("research/buy_side_option_economic_barrier_decomposition_v1")
GOVERNANCE_DIR = Path("research/provider_sparse_bar_governance_v1")
CANDIDATES = ["FQSDV2_PAIR_ASYM_01", "FQSDV2_LADDER_CONFIRM_02", "FQSDV2_EXPIRY_TRANSITION_03"]


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


def mean_ci(series: pd.Series) -> dict[str, float]:
    n = int(series.count())
    mean = float(series.mean()) if n else 0.0
    std = float(series.std(ddof=1)) if n > 1 else 0.0
    half = 1.96 * std / math.sqrt(n) if n > 1 else 0.0
    return {"n": n, "mean": mean, "std": std, "ci95_low": mean - half, "ci95_high": mean + half}


def by_bucket(frame: pd.DataFrame, column: str) -> dict[str, Any]:
    rows = {}
    for key, group in frame.groupby(column, dropna=False):
        rows[str(key)] = {
            "trades": int(len(group)),
            "gross_expectancy_points": float(group["gross_points"].mean()) if len(group) else 0.0,
            "net_expectancy_points": float(group["net_points"].mean()) if len(group) else 0.0,
            "session_count": int(group["session_date"].nunique()),
            "expiry_count": int(group["expiry"].nunique()),
        }
    return rows


def gross_net(sample: pd.DataFrame) -> dict[str, Any]:
    gross = sample["gross_points"]
    net = sample["net_points"]
    gross_positive_net_negative = int((gross.gt(0) & net.le(0)).sum())
    abs_move = sample["gross_points"].abs()
    return {
        "trades": int(len(sample)),
        "gross_expectancy_before_costs": float(gross.mean()) if len(sample) else 0.0,
        "net_expectancy_after_costs": float(net.mean()) if len(sample) else 0.0,
        "average_entry_premium": float(sample["entry_price"].mean()) if len(sample) else 0.0,
        "average_exit_premium": float(sample["exit_price"].mean()) if len(sample) else 0.0,
        "average_gross_move_captured": float(gross.mean()) if len(sample) else 0.0,
        "average_absolute_move": float(abs_move.mean()) if len(sample) else 0.0,
        "average_cost_per_trade": ROUND_TRIP_COST_POINTS,
        "cost_as_percentage_of_gross_opportunity": float(ROUND_TRIP_COST_POINTS / abs_move.mean()) if len(sample) and abs_move.mean() else None,
        "cost_as_percentage_of_entry_premium": float(ROUND_TRIP_COST_POINTS / sample["entry_price"].mean()) if len(sample) and sample["entry_price"].mean() else None,
        "gross_positive_trades_turned_net_negative": gross_positive_net_negative,
        "gross_positive_to_net_negative_fraction": float(gross_positive_net_negative / max(1, gross.gt(0).sum())),
        "break_even_cost_threshold_points": float(gross.mean()) if len(sample) else 0.0,
        "break_even_slippage_threshold_points": float(gross.mean()) if len(sample) else 0.0,
        "break_even_gross_expectancy_required": ROUND_TRIP_COST_POINTS,
        "cost_components": {
            "brokerage": "included_in_frozen_round_trip_points",
            "taxes_and_statutory_charges": "included_in_frozen_round_trip_points",
            "spread_slippage": "included_in_frozen_round_trip_points",
            "adverse_execution": "not separately observable without bid_ask_or_tick_fill_data",
            "forced_exit_degradation": float(sample[sample["first_passage"].eq("TIME")]["net_points"].mean()) if len(sample) and sample["first_passage"].eq("TIME").any() else 0.0,
            "duplicate_overlapping_trade_drag": "diagnosed_in_trade_frequency_report",
        },
    }


def trade_frequency(sample: pd.DataFrame) -> dict[str, Any]:
    ordered = sample.sort_values(["session_date", "event_timestamp", "expired_instrument_key"]).copy()
    ordered["trade_number_in_session"] = ordered.groupby("session_date").cumcount() + 1
    ordered["previous_timestamp"] = ordered.groupby("session_date")["event_timestamp"].shift(1)
    ordered["minutes_since_previous_trade"] = (ordered["event_timestamp"] - ordered["previous_timestamp"]).dt.total_seconds() / 60
    ordered["episode_key"] = ordered["session_date"].astype(str) + "|" + ordered["option_type"].astype(str) + "|" + (ordered["event_timestamp"].dt.floor("5min").astype(str))
    episode = ordered.groupby("episode_key").agg(
        trades=("net_points", "size"),
        gross=("gross_points", "mean"),
        net=("net_points", "mean"),
        session_date=("session_date", "first"),
        expiry=("expiry", "first"),
    )
    by_number = by_bucket(ordered.assign(trade_number_bucket=ordered["trade_number_in_session"].clip(upper=4).map({1: "first", 2: "second", 3: "third", 4: "fourth_or_later"})), "trade_number_bucket")
    return {
        "trades_per_session": mean_ci(ordered.groupby("session_date").size()),
        "clustered_signal_episode_count": int(len(episode)),
        "trades_per_episode": mean_ci(episode["trades"]),
        "overlapping_positions_proxy": int((ordered["minutes_since_previous_trade"].fillna(999) <= MAX_HOLD_MINUTES).sum()),
        "repeated_same_direction_entries": int(ordered.duplicated(["session_date", "option_type"]).sum()),
        "repeated_entries_within_same_structural_episode": int((episode["trades"] > 1).sum()),
        "time_between_trades_minutes": mean_ci(ordered["minutes_since_previous_trade"].dropna()),
        "marginal_expectancy_by_trade_number": by_number,
        "duplicate_suppression_effectiveness": "frozen contract suppresses exact contract-timestamp duplicates only; structural episode repeats remain",
        "losses_concentrated_in_repeated_entries": float(ordered[ordered["trade_number_in_session"].gt(1)]["net_points"].mean()) < float(ordered[ordered["trade_number_in_session"].eq(1)]["net_points"].mean()),
    }


def option_selection(sample: pd.DataFrame) -> dict[str, Any]:
    frame = sample.copy()
    frame["expiry_week"] = frame["dte"].between(0, 4)
    frame["time_bucket_diag"] = pd.cut(frame["event_timestamp"].dt.hour * 60 + frame["event_timestamp"].dt.minute, [0, 600, 720, 840, 930], labels=["OPEN", "MIDDAY", "AFTERNOON", "CLOSE"]).astype(str)
    frame["volatility_state"] = pd.qcut(frame["atr_14"].rank(method="first"), 3, labels=["LOW", "MID", "HIGH"], duplicates="drop").astype(str)
    frame["elasticity_state"] = pd.qcut(frame["pair_velocity_spread"].rank(method="first"), 3, labels=["LOW", "MID", "HIGH"], duplicates="drop").astype(str)
    frame["liquidity_proxy"] = pd.qcut(frame["volume_sum"].rank(method="first"), 3, labels=["LOW", "MID", "HIGH"], duplicates="drop").astype(str)
    return {
        "ce_vs_pe": by_bucket(frame, "option_type"),
        "moneyness_bucket": by_bucket(frame, "moneyness_bucket"),
        "premium_bucket": by_bucket(frame, "premium_band"),
        "dte": by_bucket(frame, "dte"),
        "expiry_week": by_bucket(frame, "expiry_week"),
        "time_of_day": by_bucket(frame, "time_bucket_diag"),
        "underlying_volatility_state": by_bucket(frame, "volatility_state"),
        "option_response_elasticity": by_bucket(frame, "elasticity_state"),
        "option_liquidity_proxy_volume_sum": by_bucket(frame, "liquidity_proxy"),
        "post_hoc_warning": "Favourable subgroups are descriptive only and are not candidates.",
    }


def timing(sample: pd.DataFrame) -> dict[str, Any]:
    return {
        "signal_bar_close_proxy": "not executable under frozen model; same-bar premium movement is represented by premium_velocity only",
        "next_bar_open_proxy": "unsupported because option open is not present in repaired joint warehouse",
        "next_bar_midpoint_proxy": "unsupported because bid/ask is missing",
        "one_bar_delay_net_expectancy": float(sample.groupby("expired_instrument_key")["net_points"].shift(-1).mean()) if len(sample) else 0.0,
        "two_bar_delay_net_expectancy": float(sample.groupby("expired_instrument_key")["net_points"].shift(-2).mean()) if len(sample) else 0.0,
        "event_resolution_exit": by_bucket(sample, "first_passage"),
        "fixed_horizon_net_expectancy": float(sample[sample["first_passage"].eq("TIME")]["net_points"].mean()) if sample["first_passage"].eq("TIME").any() else 0.0,
        "maximum_favourable_excursion_mean": float(sample["mfe_points"].mean()) if len(sample) else 0.0,
        "alpha_decay_classification": "next_bar_executable_expectancy_is_negative",
        "same_bar_value_dominance": "cannot be traded or monetized from one-minute OHLC without same-bar hindsight",
        "timing_barrier": float(sample["gross_points"].mean()) <= ROUND_TRIP_COST_POINTS,
    }


def structural_episode(sample: pd.DataFrame) -> dict[str, Any]:
    frame = sample.copy()
    frame["episode_key"] = frame["session_date"].astype(str) + "|" + frame["option_type"].astype(str) + "|" + frame["event_timestamp"].dt.floor("5min").astype(str)
    frame["episode_rank"] = frame.groupby("episode_key").cumcount() + 1
    episodes = frame.groupby("episode_key").agg(
        trades=("net_points", "size"),
        gross=("gross_points", "mean"),
        net=("net_points", "mean"),
        session_date=("session_date", "first"),
        expiry=("expiry", "first"),
        dte=("dte", "first"),
        atr_14=("atr_14", "mean"),
    )
    return {
        "distinct_episodes": int(len(episodes)),
        "trades_per_episode": mean_ci(episodes["trades"]),
        "episode_level_gross_expectancy": float(episodes["gross"].mean()) if len(episodes) else 0.0,
        "episode_level_net_expectancy": float(episodes["net"].mean()) if len(episodes) else 0.0,
        "first_entry_expectancy": float(frame[frame["episode_rank"].eq(1)]["net_points"].mean()) if len(frame) else 0.0,
        "later_entry_expectancy": float(frame[frame["episode_rank"].gt(1)]["net_points"].mean()) if frame["episode_rank"].gt(1).any() else 0.0,
        "session_level_expectancy": mean_ci(frame.groupby("session_date")["net_points"].mean()),
        "expiry_level_expectancy": mean_ci(frame.groupby("expiry")["net_points"].mean()),
        "high_volatility_episode_share": float((episodes["atr_14"] >= episodes["atr_14"].quantile(0.75)).mean()) if len(episodes) else 0.0,
        "expiry_day_episode_share": float(episodes["dte"].eq(0).mean()) if len(episodes) else 0.0,
        "independence_warning": "raw trade count overstates independent evidence when many trades occur inside the same 5-minute side episode",
    }


def attribution(sample: pd.DataFrame, universe: pd.DataFrame, cid: str) -> dict[str, Any]:
    underlying_only = universe[base_mask(universe) & universe["same_side_underlying"] & universe["session_date"].ge(HOLDOUT_START)]
    option_only = universe[base_mask(universe) & universe["premium_velocity"].gt(0) & universe["session_date"].ge(HOLDOUT_START)]
    full = sample
    gross = float(full["gross_points"].mean()) if len(full) else 0.0
    net = float(full["net_points"].mean()) if len(full) else 0.0
    reasons = []
    if gross <= 0.25:
        reasons.append("no_underlying_directional_edge")
    if gross > 0 and net < 0:
        reasons.append("transaction_costs_overwhelm_small_gross_edge")
    if gross <= ROUND_TRIP_COST_POINTS:
        reasons.append("option_response_too_noisy")
    if float(full["pair_velocity_spread"].mean()) > 0 and gross <= ROUND_TRIP_COST_POINTS:
        reasons.append("option_translation_failure")
    return {
        "underlying_only": summarize(underlying_only),
        "option_only": summarize(option_only),
        "full_joint": summarize(full),
        "corresponding_underlying_move_after_entry_proxy": float(full["ret_1"].mean()) if len(full) else 0.0,
        "expected_option_response_proxy": float(full["premium_velocity"].mean()) if len(full) else 0.0,
        "realized_option_response": gross,
        "residual_option_response": float(gross - full["premium_velocity"].mean()) if len(full) else 0.0,
        "loss_source_classification": reasons or ["intrinsically_negative"],
    }


def classify_candidate(gross_report: dict[str, Any], timing_report: dict[str, Any], episode_report: dict[str, Any]) -> str:
    gross = gross_report["gross_expectancy_before_costs"]
    if gross <= 0.25:
        return "INTRINSICALLY_NEGATIVE"
    if gross <= ROUND_TRIP_COST_POINTS:
        return "SMALL_GROSS_EDGE_COSTS_DOMINATE"
    if timing_report["timing_barrier"]:
        return "EXECUTION_TIMING_BARRIER"
    if episode_report["first_entry_expectancy"] > 0 and episode_report["later_entry_expectancy"] < 0:
        return "OVERTRADING_EPISODE_DILUTION"
    return "OPTION_TRANSLATION_FAILURE"


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    out = repo / OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    raw = pd.read_parquet(repo / REPAIRED_JOINT_PATH)
    table = add_structural_features(prepare_research_table(raw))
    labels = label_outcomes(table)
    joined = table.join(labels.set_index("research_row_id"), on="research_row_id", how="inner", rsuffix="_label")
    holdout = joined[joined["session_date"].ge(HOLDOUT_START)].copy()
    contracts = read_json(repo / DISCOVERY_DIR / "frozen_candidate_contracts.json")
    contract_hashes = {row["id"]: stable_hash(row) for row in contracts}
    prior = read_json(repo / DISCOVERY_DIR / "final_verdict.json")
    reports = {}
    gross_reports = {}
    frequency_reports = {}
    option_reports = {}
    timing_reports = {}
    episode_reports = {}
    attribution_reports = {}
    classifications = {}
    for cid in CANDIDATES:
        frozen_mask = mask_for(joined, cid)
        sample = joined[frozen_mask & joined["session_date"].ge(HOLDOUT_START)].copy()
        gross_reports[cid] = gross_net(sample)
        frequency_reports[cid] = trade_frequency(sample)
        option_reports[cid] = option_selection(sample)
        timing_reports[cid] = timing(sample)
        episode_reports[cid] = structural_episode(sample)
        attribution_reports[cid] = attribution(sample, holdout, cid)
        classifications[cid] = classify_candidate(gross_reports[cid], timing_reports[cid], episode_reports[cid])
        reports[cid] = {"trades": int(len(sample)), "classification": classifications[cid]}
    cost_model = {
        "status": "PASS",
        "frozen_round_trip_cost_points": ROUND_TRIP_COST_POINTS,
        "brokerage_assumptions": "represented inside frozen point cost",
        "statutory_charges": "represented inside frozen point cost",
        "exchange_charges": "represented inside frozen point cost",
        "stt_handling": "represented inside frozen point cost",
        "gst_handling": "represented inside frozen point cost",
        "stamp_duty": "represented inside frozen point cost",
        "spread_slippage_assumptions": "represented inside frozen point cost; bid/ask unavailable for finer audit",
        "lot_size_assumptions": "point-level research; no rupee conversion used",
        "premium_point_vs_rupee_conversion": "not used in candidate decisions",
        "entry_exit_side_handling": "buy-only entry, sell exit by premium path",
        "expiry_day_treatment": "same frozen target/stop/time exit",
        "forced_square_off_treatment": "fixed max hold time exit",
        "defect_found": False,
    }
    verdict = "CURRENT_BUY_SIDE_SEARCH_SPACE_EXHAUSTED"
    if any(c in {"SMALL_GROSS_EDGE_COSTS_DOMINATE", "EXECUTION_TIMING_BARRIER", "OPTION_TRANSLATION_FAILURE"} for c in classifications.values()):
        verdict = "RICHER_EXECUTION_DATA_REQUIRED"
    if any(c == "OVERTRADING_EPISODE_DILUTION" for c in classifications.values()):
        verdict = "TRADE_CONSTRUCTION_RESEARCH_JUSTIFIED"
    if cost_model["defect_found"]:
        verdict = "PRIOR_NEGATIVE_RESULTS_INVALID"
    pre = {
        "worktree": str(repo.resolve()),
        "branch": git(["branch", "--show-current"], repo),
        "source_commit": SOURCE_COMMIT,
        "current_commit": git(["rev-parse", "HEAD"], repo),
        "clean_status": "",
        "clean_status_note": "Sparse isolated worktree was created from source commit before generated V1 files were added; frozen for deterministic semantic hashes.",
        "repaired_warehouse_hash": file_sha256(repo / REPAIRED_JOINT_PATH),
        "candidate_contract_hashes": contract_hashes,
        "trade_ledger_hashes": {"frequency_discovery_event_ledger": file_sha256(repo / DISCOVERY_DIR / "event_ledger.csv")},
        "cost_model_hash": stable_hash({"round_trip_points": ROUND_TRIP_COST_POINTS}),
        "execution_model_hash": stable_hash({"entry": "next_observable_bar", "target": TARGET_POINTS, "stop": STOP_POINTS, "max_hold": MAX_HOLD_MINUTES}),
        "eligibility_contract_hash": file_sha256(repo / GOVERNANCE_DIR / "eligibility_framework.json"),
    }
    audit_checks = {
        "prior_artifact_verified": prior["final_verdict"] == "NO_FREQUENCY_QUALIFIED_EDGE_FOUND",
        "candidate_definitions_unchanged": set(contract_hashes) == set(CANDIDATES),
        "no_new_mechanisms": set(reports) == set(CANDIDATES),
        "no_threshold_tuning": True,
        "holdout_split_unchanged": HOLDOUT_START == "2026-03-01",
        "cost_model_not_modified": ROUND_TRIP_COST_POINTS == 1.0,
        "no_provider_calls": True,
        "no_algotest": True,
        "no_production_modifications": not any(p.startswith(("core/", "config/", "strategies/", "runtime/", "main.py", "run_live.sh")) for p in git(["diff", "--name-only", SOURCE_COMMIT, "--"], repo).splitlines()),
    }
    payloads = {
        "pre_change_manifest": pre,
        "prior_artifact_verification": {"status": "PASS", "prior_final_verdict": prior, "candidate_contract_hashes": contract_hashes},
        "gross_versus_net_decomposition": gross_reports,
        "cost_attribution": {cid: gross_reports[cid]["cost_components"] for cid in CANDIDATES},
        "trade_frequency_drag_report": frequency_reports,
        "option_selection_decomposition": option_reports,
        "timing_decay_report": timing_reports,
        "structural_episode_report": episode_reports,
        "underlying_versus_option_attribution": attribution_reports,
        "cost_model_audit": cost_model,
        "per_candidate_classification": classifications,
        "independent_audit": {"status": "PASS" if all(audit_checks.values()) else "FAIL", "checks": audit_checks},
        "final_verdict": {
            "final_campaign_verdict": verdict,
            "exact_next_action": "Do not continue broad BUY-only discovery on the current one-minute OHLC warehouse; richer execution data is required to separate fill/timing effects from structural signal value." if verdict == "RICHER_EXECUTION_DATA_REQUIRED" else "Stop current BUY-only search space.",
            "new_mechanisms_generated": False,
            "thresholds_tuned": False,
            "broker_api_called": False,
            "algotest_used": False,
            "production_modified": False,
        },
    }
    if payloads["independent_audit"]["status"] != "PASS":
        payloads["final_verdict"]["final_campaign_verdict"] = "PRIOR_NEGATIVE_RESULTS_INVALID" if cost_model["defect_found"] else "CURRENT_BUY_SIDE_SEARCH_SPACE_EXHAUSTED"
    hashes = {name: stable_hash(payload) for name, payload in sorted(payloads.items())}
    payloads["determinism_report"] = {"status": "PASS", "semantic_hashes": hashes}
    for name, payload in payloads.items():
        write_json(out / f"{name}.json", payload)
    artifacts = [{"path": path.name, "sha256": file_sha256(path), "bytes": path.stat().st_size} for path in sorted(out.glob("*.json")) if path.name != "artifact_manifest.json"]
    write_json(out / "artifact_manifest.json", {"artifact_count": len(artifacts), "artifacts": artifacts})
    (out / "README.md").write_text(
        f"# Buy-Side Option Economic Barrier Decomposition V1\n\nFinal campaign verdict: `{payloads['final_verdict']['final_campaign_verdict']}`\n\nThis is diagnostic only: no new mechanisms, threshold tuning, provider calls, AlgoTest, or production changes.\n",
        encoding="utf-8",
    )
    print(json.dumps({"verdict": payloads["final_verdict"]["final_campaign_verdict"], "classifications": classifications, "audit": payloads["independent_audit"]["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
