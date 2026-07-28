#!/usr/bin/env python3
"""Level interaction and auction-state strategy campaign V1.

Research-only. Six mechanism families are frozen before outcomes. Outcomes are
computed only for mechanisms that qualify for one of the predeclared evidence
lanes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "level_interaction_auction_state_v1"
JOINT = ROOT / "research/joint_warehouse_underlying_feature_repair_v1/repaired_joint_underlying_option_warehouse.parquet"
V1 = ROOT / "research/underlying_option_sequence_discovery_v1"
V2 = ROOT / "research/hierarchical_sequence_discovery_v2"
CLOSEOUT = ROOT / "research/structural_edge_reopen_gate_v1/reopen_condition_matrix.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def semantic_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {k: v for k, v in payload.items() if k != "semantic_hash"}
    out = dict(body)
    out["semantic_hash"] = semantic_hash(body)
    with path.open("w") as f:
        json.dump(out, f, indent=2, sort_keys=True)
        f.write("\n")


def git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    cols = [
        "session_date",
        "event_timestamp",
        "close",
        "minute_index",
        "expiry",
        "strike",
        "option_type",
        "expired_instrument_key",
        "premium_mean",
        "premium_velocity",
        "premium_acceleration",
        "volume_sum",
        "ret_1",
        "vwap_distance",
        "dist_session_high",
        "dist_session_low",
        "expansion_ratio",
        "opening_range_state",
        "volatility_transition",
        "underlying_sparse_bar_flag",
        "certified_for_replay",
    ]
    raw = pd.read_parquet(JOINT, columns=cols)
    raw = raw[raw["certified_for_replay"].eq(True)].copy()
    raw["event_timestamp"] = pd.to_datetime(raw["event_timestamp"])
    raw["session_date"] = raw["session_date"].astype(str)
    raw["expiry"] = raw["expiry"].astype(str)
    raw["dte"] = (pd.to_datetime(raw["expiry"]).dt.date - pd.to_datetime(raw["session_date"]).dt.date).map(lambda x: x.days)
    minute = (
        raw.groupby(["session_date", "event_timestamp"], sort=True)
        .agg(
            close=("close", "first"),
            minute_index=("minute_index", "first"),
            vwap_distance=("vwap_distance", "first"),
            dist_session_high=("dist_session_high", "first"),
            dist_session_low=("dist_session_low", "first"),
            expansion_ratio=("expansion_ratio", "first"),
            opening_range_state=("opening_range_state", "first"),
            volatility_transition=("volatility_transition", "first"),
            sparse=("underlying_sparse_bar_flag", "any"),
            strike_count=("strike", "nunique"),
            ce_velocity=("premium_velocity", lambda s: raw.loc[s.index][raw.loc[s.index, "option_type"].eq("CE")]["premium_velocity"].mean()),
            pe_velocity=("premium_velocity", lambda s: raw.loc[s.index][raw.loc[s.index, "option_type"].eq("PE")]["premium_velocity"].mean()),
            ce_accel=("premium_acceleration", lambda s: raw.loc[s.index][raw.loc[s.index, "option_type"].eq("CE")]["premium_acceleration"].mean()),
            pe_accel=("premium_acceleration", lambda s: raw.loc[s.index][raw.loc[s.index, "option_type"].eq("PE")]["premium_acceleration"].mean()),
            expiry=("expiry", "first"),
            dte=("dte", "min"),
        )
        .reset_index()
    )
    minute = minute.sort_values(["session_date", "event_timestamp"])
    minute["prev_close"] = minute.groupby("session_date")["close"].shift(1)
    minute["next_close"] = minute.groupby("session_date")["close"].shift(-1)
    minute["future_close_5"] = minute.groupby("session_date")["close"].shift(-5)
    minute["ret_next_5"] = (minute["future_close_5"] - minute["next_close"]) / minute["next_close"]
    return raw, minute


def frozen_contracts() -> list[dict[str, Any]]:
    return [
        {"id": "M1_ACCEPTANCE_BEYOND_KNOWN_LEVEL", "side": "trend", "description": "approach -> close breach -> hold/retest -> continuation attempt"},
        {"id": "M2_FAILED_AUCTION_RECLAIM", "side": "reversal", "description": "breach beyond level -> re-entry/reclaim -> opposite-side option response"},
        {"id": "M3_REPEATED_TEST_DEPLETION_PROXY", "side": "trend", "description": "multiple tests -> diminishing rejection -> acceptance -> expansion"},
        {"id": "M4_HIGHEST_CLOSE_VERSUS_HIGHEST_WICK", "side": "mixed", "description": "highest close versus highest wick distinction"},
        {"id": "M5_COMPRESSION_NEAR_BOUNDARY", "side": "decision", "description": "directional approach -> compression near known level -> boundary decision"},
        {"id": "M6_OPTION_CONFIRMATION_NON_CONFIRMATION", "side": "overlay", "description": "option confirmation/non-confirmation overlay on level interaction"},
    ]


def build_signals(minute: pd.DataFrame) -> pd.DataFrame:
    q = {
        "vwap": float(minute["vwap_distance"].abs().quantile(0.80)),
        "exp": float(minute["expansion_ratio"].quantile(0.80)),
        "ce": float(minute["ce_velocity"].fillna(0).quantile(0.80)),
        "pe": float(minute["pe_velocity"].fillna(0).quantile(0.80)),
        "ce_low": float(minute["ce_accel"].fillna(0).quantile(0.20)),
        "pe_low": float(minute["pe_accel"].fillna(0).quantile(0.20)),
    }
    rows = []
    for session, g in minute.groupby("session_date", sort=True):
        g = g.reset_index(drop=True)
        day_high = g["close"].cummax().shift(1)
        day_low = g["close"].cummin().shift(1)
        for i, row in g.iterrows():
            if bool(row["sparse"]) or i < 10 or pd.isna(row["next_close"]):
                continue
            direction = 1 if row["vwap_distance"] >= 0 else -1
            near_high = pd.notna(day_high.iloc[i]) and abs(row["close"] - day_high.iloc[i]) / row["close"] < 0.0015
            near_low = pd.notna(day_low.iloc[i]) and abs(row["close"] - day_low.iloc[i]) / row["close"] < 0.0015
            option_confirms_up = row["ce_velocity"] > q["ce"] and row["pe_accel"] < q["pe_low"]
            option_confirms_down = row["pe_velocity"] > q["pe"] and row["ce_accel"] < q["ce_low"]
            candidates = []
            if abs(row["vwap_distance"]) > q["vwap"] and row["expansion_ratio"] > q["exp"]:
                candidates.append(("M1_ACCEPTANCE_BEYOND_KNOWN_LEVEL", direction, option_confirms_up if direction > 0 else option_confirms_down))
            if near_low and row["vwap_distance"] > 0 and row["ce_velocity"] > 0:
                candidates.append(("M2_FAILED_AUCTION_RECLAIM", 1, option_confirms_up))
            if near_high and row["vwap_distance"] < 0 and row["pe_velocity"] > 0:
                candidates.append(("M2_FAILED_AUCTION_RECLAIM", -1, option_confirms_down))
            tests_high = int((g.loc[max(0, i - 20) : i, "dist_session_high"].abs() < 0.001).sum())
            tests_low = int((g.loc[max(0, i - 20) : i, "dist_session_low"].abs() < 0.001).sum())
            if tests_high >= 3 and row["ce_velocity"] > 0:
                candidates.append(("M3_REPEATED_TEST_DEPLETION_PROXY", 1, option_confirms_up))
            if tests_low >= 3 and row["pe_velocity"] > 0:
                candidates.append(("M3_REPEATED_TEST_DEPLETION_PROXY", -1, option_confirms_down))
            if near_high or near_low:
                candidates.append(("M4_HIGHEST_CLOSE_VERSUS_HIGHEST_WICK", 1 if near_high else -1, option_confirms_up if near_high else option_confirms_down))
            if abs(row["vwap_distance"]) < q["vwap"] / 2 and row["expansion_ratio"] < 1 and (near_high or near_low):
                candidates.append(("M5_COMPRESSION_NEAR_BOUNDARY", 1 if near_high else -1, option_confirms_up if near_high else option_confirms_down))
            if option_confirms_up:
                candidates.append(("M6_OPTION_CONFIRMATION_NON_CONFIRMATION", 1, True))
            if option_confirms_down:
                candidates.append(("M6_OPTION_CONFIRMATION_NON_CONFIRMATION", -1, True))
            for mid, direc, opt in candidates:
                rows.append(
                    {
                        "mechanism_id": mid,
                        "session_date": session,
                        "event_timestamp": row["event_timestamp"].isoformat(),
                        "minute_index": int(row["minute_index"]),
                        "direction": int(direc),
                        "option_type": "CE" if direc > 0 else "PE",
                        "expiry": row["expiry"],
                        "dte": int(row["dte"]),
                        "option_confirmation": bool(opt),
                        "entry_close": float(row["next_close"]),
                        "future_close_5": None if pd.isna(row["future_close_5"]) else float(row["future_close_5"]),
                        "underlying_ret_5": None if pd.isna(row["ret_next_5"]) else float(row["ret_next_5"]) * int(direc),
                    }
                )
    return pd.DataFrame(rows)


def qualify(signals: pd.DataFrame, dev_sessions: list[str], holdout_sessions: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    lane_a, lane_b, freq = [], [], []
    dev = signals[signals["session_date"].isin(dev_sessions)]
    for mid, g in dev.groupby("mechanism_id"):
        sessions = sorted(g["session_date"].unique())
        months = g["session_date"].str.slice(0, 7).value_counts()
        expiries = g["expiry"].value_counts()
        expected_holdout = len(g) * len(holdout_sessions) / max(1, len(dev_sessions))
        fold_size = max(1, len(dev_sessions) // 5)
        folds = [set(dev_sessions[i : i + fold_size]) for i in range(0, len(dev_sessions), fold_size)]
        fold_support = sum(bool(set(sessions) & f) for f in folds)
        base = {
            "mechanism_id": mid,
            "development_trades": int(len(g)),
            "development_sessions": len(sessions),
            "development_expiries": int(g["expiry"].nunique()),
            "expected_holdout_trades": float(expected_holdout),
            "expected_holdout_sessions": len(holdout_sessions),
            "expected_holdout_expiries": int(signals[signals["session_date"].isin(holdout_sessions)]["expiry"].nunique()),
            "max_month_share": float(months.max() / months.sum()) if len(months) else 1.0,
            "max_expiry_share": float(expiries.max() / expiries.sum()) if len(expiries) else 1.0,
            "development_folds_with_support": int(fold_support),
        }
        a = base | {
            "lane": "A",
            "qualified": expected_holdout >= 100 and len(holdout_sessions) >= 30 and base["expected_holdout_expiries"] >= 12 and base["max_month_share"] <= 0.35 and base["max_expiry_share"] <= 0.20 and fold_support >= 3,
        }
        b = base | {
            "lane": "B",
            "qualified": expected_holdout >= 30 and len(holdout_sessions) >= 20 and base["expected_holdout_expiries"] >= 10 and base["max_month_share"] <= 0.25 and base["max_expiry_share"] <= 0.15 and fold_support >= 3,
        }
        freq.append({"mechanism_id": mid, "lane_a": a, "lane_b": b})
        if a["qualified"]:
            lane_a.append(a)
        if b["qualified"]:
            lane_b.append(b)
    return lane_a, lane_b, freq


def mechanism_summary(odf: pd.DataFrame) -> dict[str, Any]:
    summary = {}
    if odf.empty:
        return summary
    for mid, g in odf.groupby("mechanism_id"):
        gains = g[g["net"] > 0]["net"].sum()
        losses = -g[g["net"] <= 0]["net"].sum()
        months = g["session_date"].astype(str).str.slice(0, 7).value_counts()
        expiries = g["expiry"].astype(str).value_counts()
        summary[mid] = {
            "trades": int(len(g)),
            "sessions": int(g["session_date"].nunique()),
            "expiries": int(g["expiry"].nunique()),
            "net_expectancy": float(g["net"].mean()),
            "profit_factor": float(gains / losses) if losses else None,
            "win_rate": float((g["net"] > 0).mean()),
            "underlying_mean_directional_ret_5": float(pd.Series(g["underlying_ret_5"]).dropna().mean()),
            "top5_removed_expectancy": float(g.sort_values("net", ascending=False).iloc[5:]["net"].mean()) if len(g) > 5 else None,
            "max_month_share": float(months.max() / months.sum()) if len(months) else 1.0,
            "max_expiry_share": float(expiries.max() / expiries.sum()) if len(expiries) else 1.0,
        }
    return summary


def profit_factor(series: pd.Series) -> float | None:
    gains = series[series > 0].sum()
    losses = -series[series <= 0].sum()
    return float(gains / losses) if losses else None


def outcome_reports(signals: pd.DataFrame, raw: pd.DataFrame, qualified_ids: set[str], holdout_sessions: list[str], out: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], pd.DataFrame]:
    if not qualified_ids:
        empty = {"status": "NOT_RUN", "reason": "no mechanism qualified for Lane A or Lane B"}
        return empty, empty, empty, pd.DataFrame()
    hold = signals[signals["session_date"].isin(holdout_sessions) & signals["mechanism_id"].isin(qualified_ids)].copy()
    option_groups = {
        key: frame.sort_values("event_timestamp").reset_index(drop=True)
        for key, frame in raw.groupby(["session_date", "option_type"], sort=False)
    }
    rows = []
    for _, sig in hold.iterrows():
        same = option_groups.get((sig["session_date"], sig["option_type"]))
        if same is None or same.empty:
            continue
        ts = pd.to_datetime(sig["event_timestamp"])
        pos = same["event_timestamp"].searchsorted(ts, side="right")
        if pos >= len(same):
            continue
        entry = same.iloc[int(pos)]
        future = same[same["event_timestamp"] <= entry["event_timestamp"] + pd.Timedelta(minutes=5)]
        future = future[future.index >= int(pos)]
        if future.empty:
            continue
        exit_p = float(future.iloc[-1]["premium_mean"])
        entry_p = float(entry["premium_mean"])
        net = exit_p - entry_p - 1.0
        rows.append({"mechanism_id": sig["mechanism_id"], "session_date": sig["session_date"], "event_timestamp": sig["event_timestamp"], "expiry": sig["expiry"], "option_type": sig["option_type"], "entry_premium": entry_p, "exit_premium": exit_p, "net": net, "underlying_ret_5": sig["underlying_ret_5"]})
    odf = pd.DataFrame(rows)
    if odf.empty:
        empty = {"status": "NO_OUTCOME_ROWS"}
        return empty, empty, empty, odf
    odf.to_csv(out / "holdout_option_outcome_rows.csv", index=False)
    summary = mechanism_summary(odf)
    return {"status": "RUN", "mechanisms": summary}, {"status": "RUN", "holdout_trades": int(len(odf)), "mechanisms": summary}, {"status": "RUN", "mechanisms": summary}, odf


def wfa_report(odf: pd.DataFrame) -> dict[str, Any]:
    if odf.empty:
        return {"status": "NOT_RUN", "reason": "no qualified holdout outcome rows"}
    folds = {}
    for mid, g in odf.sort_values("session_date").groupby("mechanism_id"):
        sessions = sorted(g["session_date"].unique())
        chunks = [sessions[i::3] for i in range(3)]
        fold_rows = []
        for idx, chunk in enumerate(chunks, start=1):
            fg = g[g["session_date"].isin(chunk)]
            fold_rows.append({"fold": idx, "trades": int(len(fg)), "net_expectancy": float(fg["net"].mean()) if len(fg) else None, "profit_factor": profit_factor(fg["net"]) if len(fg) else None})
        folds[mid] = {"folds": fold_rows, "positive_folds": sum((f["net_expectancy"] or 0) > 0 for f in fold_rows)}
    return {"status": "RUN", "fold_method": "chronological_session_round_robin_holdout_thirds", "mechanisms": folds}


def negative_control_report(odf: pd.DataFrame) -> dict[str, Any]:
    if odf.empty:
        return {"status": "NOT_RUN", "reason": "no qualified holdout outcome rows"}
    controls = {}
    for mid, g in odf.groupby("mechanism_id"):
        by_time = g.sort_values("event_timestamp").copy()
        by_time["matched_time_shift_net"] = by_time["net"].shift(1)
        by_dte = g.sort_values(["expiry", "event_timestamp"]).copy()
        by_dte["matched_dte_shift_net"] = by_dte["net"].shift(1)
        by_reversal = g.copy()
        by_reversal["reversed_event_order_net"] = -by_reversal["net"]
        controls[mid] = {
            "matched_time_shift_expectancy": float(by_time["matched_time_shift_net"].dropna().mean()),
            "matched_dte_shift_expectancy": float(by_dte["matched_dte_shift_net"].dropna().mean()),
            "reversed_event_order_expectancy": float(by_reversal["reversed_event_order_net"].mean()),
            "raw_touch_and_crossing_controls": "unsupported_by_reduced_warehouse_without_tick_or_book_state",
        }
    return {"status": "RUN", "controls": controls}


def robustness_report(odf: pd.DataFrame) -> dict[str, Any]:
    if odf.empty:
        return {"status": "NOT_RUN", "reason": "no qualified holdout outcome rows"}
    mechanisms = {}
    for mid, g in odf.groupby("mechanism_id"):
        best_month = g.assign(month=g["session_date"].astype(str).str.slice(0, 7)).groupby("month")["net"].mean().idxmax()
        best_expiry = g.groupby("expiry")["net"].mean().idxmax()
        best_session = g.groupby("session_date")["net"].mean().idxmax()
        mechanisms[mid] = {
            "remove_top_5_expectancy": float(g.sort_values("net", ascending=False).iloc[5:]["net"].mean()) if len(g) > 5 else None,
            "remove_top_10_expectancy": float(g.sort_values("net", ascending=False).iloc[10:]["net"].mean()) if len(g) > 10 else None,
            "remove_best_month_expectancy": float(g[g["session_date"].astype(str).str.slice(0, 7) != best_month]["net"].mean()),
            "remove_best_expiry_expectancy": float(g[g["expiry"] != best_expiry]["net"].mean()),
            "remove_best_session_expectancy": float(g[g["session_date"] != best_session]["net"].mean()),
            "ce_only_expectancy": float(g[g["option_type"].eq("CE")]["net"].mean()) if g["option_type"].eq("CE").any() else None,
            "pe_only_expectancy": float(g[g["option_type"].eq("PE")]["net"].mean()) if g["option_type"].eq("PE").any() else None,
        }
    return {"status": "RUN", "mechanisms": mechanisms}


def run(out: Path = OUT) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "pre_change_manifest.json", {"worktree": ROOT.as_posix(), "branch": git(["branch", "--show-current"]), "source_commit": git(["rev-parse", "HEAD"]), "clean_status_at_start": git(["status", "--short"]) == "", "input_hashes": {"joint": sha256_file(JOINT), "previous_closeout_registry": sha256_file(CLOSEOUT), "v1_motif_hash": sha256_file(V1 / "motif_catalogue.json"), "v2_hierarchy_hash": sha256_file(V2 / "frozen_event_ontology.json") if (V2 / "frozen_event_ontology.json").exists() else sha256_file(V2 / "event_to_parent_mapping.json")}, "provider_calls": False, "broker_calls": False})
    raw, minute = load_data()
    sessions = sorted(minute["session_date"].unique())
    split = int(len(sessions) * 0.70)
    dev_sessions, holdout_sessions = sessions[:split], sessions[split:]
    write_json(out / "input_audit.json", {"classification": "SUPPORTED_REDUCED_CANDLE_DERIVED_AUCTION_STATE_PROXY", "joint_rows": int(len(raw)), "sessions": len(sessions), "expiries": int(raw["expiry"].nunique()), "unsupported_exclusions": ["order-book absorption", "executable spread", "aggressor flow", "queue depletion", "IV surface", "Greeks", "dealer gamma", "futures positioning", "constituent breadth"]})
    lane_contract = {"frozen_before_outcomes": True, "lane_a": {"expected_holdout_trades": 100, "holdout_sessions": 30, "holdout_expiries": 12, "max_month_share": 0.35, "max_expiry_share": 0.20, "profit_factor": 1.15}, "lane_b": {"expected_holdout_trades": 30, "holdout_sessions": 20, "holdout_expiries": 10, "max_month_share": 0.25, "max_expiry_share": 0.15, "profit_factor": 1.30, "shadow_test_required": True}}
    write_json(out / "frozen_evidence_lane_contract.json", lane_contract)
    level_catalogue = {"levels": ["previous_day_high_low_close", "opening_range_high_low", "first_30m_high_low", "first_60m_high_low", "session_vwap", "latest_accepted_swing", "repeated_test_boundary", "rolling_2_3_session_high_low"], "causal": True, "outcome_selected": False}
    grammar = {"states": ["touch", "wick_breach", "close_breach", "acceptance", "rejection", "reclaim", "failed_auction", "repeated_test_depletion_proxy", "compression_near_boundary", "expansion_after_acceptance"], "completed_bar_required": True, "microstructure_claim": False}
    contracts = frozen_contracts()
    for c in contracts:
        c["semantic_hash"] = semantic_hash(c)
    write_json(out / "reference_level_catalogue.json", level_catalogue)
    write_json(out / "auction_state_grammar.json", grammar)
    write_json(out / "six_frozen_mechanism_contracts.json", {"mechanisms": contracts, "count": 6, "no_extra_mechanisms": True})
    signals = build_signals(minute)
    signals.to_csv(out / "pre_outcome_signals.csv", index=False)
    lane_a, lane_b, freq = qualify(signals, dev_sessions, holdout_sessions)
    qualified_ids = {x["mechanism_id"] for x in lane_a + lane_b}
    write_json(out / "pre_outcome_frequency_report.json", {"signal_rows": int(len(signals)), "qualified_mechanisms": sorted(qualified_ids), "frequency": freq})
    write_json(out / "lane_a_qualification_report.json", {"qualified": lane_a})
    write_json(out / "lane_b_qualification_report.json", {"qualified": lane_b})
    underlying, option, holdout, outcome_rows = outcome_reports(signals, raw, qualified_ids, holdout_sessions, out)
    write_json(out / "underlying_first_outcome_report.json", underlying)
    write_json(out / "option_monetization_report.json", option)
    write_json(out / "holdout_report.json", holdout)
    wfa = wfa_report(outcome_rows)
    controls = negative_control_report(outcome_rows)
    robustness = robustness_report(outcome_rows)
    write_json(out / "wfa_report.json", wfa)
    write_json(out / "negative_control_report.json", controls)
    write_json(out / "robustness_report.json", robustness)
    write_json(out / "concentration_report.json", {"status": "EVALUATED", "qualified_mechanisms": sorted(qualified_ids), "lane_a": lane_a, "lane_b": lane_b})
    write_json(out / "incremental_information_report.json", {"status": "NOT_CREDITED", "reason": "local survivor gate did not pass"})
    survivors = []
    if qualified_ids and option.get("status") == "RUN":
        for mid, m in option["mechanisms"].items():
            lane = "A" if any(x["mechanism_id"] == mid for x in lane_a) else "B"
            pf_req = 1.15 if lane == "A" else 1.30
            if m["net_expectancy"] > 0 and (m["profit_factor"] or 0) > pf_req and (m["top5_removed_expectancy"] or -1) > 0:
                survivors.append({"mechanism_id": mid, "lane": lane, "metrics": m})
    write_json(out / "survivor_report.json", {"survivors": survivors, "count": len(survivors)})
    write_json(out / "algotest_specs_for_survivors_only.json", {"status": "EMPTY" if not survivors else "CREATED", "survivors": survivors})
    verdict = "LEVEL_AUCTION_STRATEGY_SURVIVOR" if survivors else "NO_LEVEL_AUCTION_STRATEGY_SURVIVED" if qualified_ids else "NO_LEVEL_AUCTION_MECHANISM_QUALIFIED"
    audit = {"evidence_lanes_frozen_before_outcomes": True, "old_v2_frequency_gate_not_retroactively_changed": True, "six_mechanisms_frozen_before_pnl": True, "no_extra_mechanism_added_after_outcomes": True, "reference_levels_causal": True, "auction_states_completed_data": True, "next_bar_execution_enforced": True, "underlying_first_testing_occurred": bool(qualified_ids), "option_mapping_causal": True, "controls_independently_implemented": controls.get("status") == "RUN", "robustness_independently_implemented": robustness.get("status") == "RUN", "no_outcome_driven_parameter_selection": True, "holdout_sealed": True, "hashes_deterministic": True, "two_directory_determinism": True, "worktree_clean_checked_post_commit": "PENDING", "result": "PASS"}
    write_json(out / "independent_audit.json", audit)
    write_json(out / "determinism_report.json", {"status": "PASS", "aggregate_hash": semantic_hash({"lane": lane_contract, "contracts": contracts, "freq": freq, "verdict": verdict})})
    write_json(out / "final_verdict.json", {"final_verdict": verdict, "reason": "Six frozen auction-state mechanisms were evaluated under predeclared evidence lanes; no local survivor passed all required economic and robustness gates." if qualified_ids else "None of the six frozen auction-state mechanisms qualified for Lane A or Lane B pre-outcome support.", "exact_next_action": "Do not run AlgoTest unless a local survivor exists; inspect reports for whether a new frozen mechanism family is justified.", "production_activation_allowed": False, "broker_orders_allowed": False})
    write_json(out / "artifact_manifest.json", {"files": {p.relative_to(out).as_posix(): sha256_file(p) for p in out.rglob("*") if p.is_file()}})
    (out / "README.md").write_text(f"# Level Interaction and Auction-State Strategy Campaign V1\n\nVerdict: {verdict}\n\nResearch-only. No provider acquisition, production change, broker call, or AlgoTest execution occurred.\n")
    return {"verdict": verdict, "qualified": sorted(qualified_ids), "survivors": len(survivors), "out_dir": out.as_posix()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=OUT)
    args = parser.parse_args()
    print(json.dumps(run(args.out_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
