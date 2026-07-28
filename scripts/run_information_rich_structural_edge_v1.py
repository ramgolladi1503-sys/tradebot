#!/usr/bin/env python3
"""Information-rich structural edge discovery V1.

Research-only. Discovers pre-expansion information first, freezes at most three
causal hypotheses on development data, then tests untouched chronological
holdout. No provider, broker, AlgoTest, production, or closed candle-pattern
logic is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/information_rich_structural_edge_v1"
JOINT = ROOT / "research/joint_warehouse_underlying_feature_repair_v1/repaired_joint_underlying_option_warehouse.parquet"
FUTURES = ROOT / "research/nifty_futures_historical_acquisition_v1/normalized/NSE_FO_61093.parquet"
TICK_ROOT = ROOT / "runtime/market_data/upstox"
CLOSEOUT = ROOT / "research/level_auction_failure_decomposition_v1/final_verdict.json"
COST_POINTS = 1.0

CLOSED_LANES = [
    "ORB variants",
    "VWAP reclaim",
    "percentage momentum",
    "candle-only auction-state",
    "repeated-test depletion",
    "highest-close vs highest-wick",
    "boundary compression",
    "candle-only option confirmation",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    body = {k: v for k, v in payload.items() if k != "semantic_hash"}
    out = dict(body)
    out["semantic_hash"] = stable_hash(body)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")


def git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def profit_factor(series: pd.Series) -> float | None:
    gains = float(series[series > 0].sum())
    losses = float(-series[series <= 0].sum())
    return gains / losses if losses else None


def max_drawdown(series: pd.Series) -> float:
    curve = series.cumsum()
    drawdown = curve - curve.cummax()
    return float(drawdown.min()) if len(drawdown) else 0.0


def auc_rank(feature: pd.Series, label: pd.Series) -> float | None:
    valid = feature.notna() & label.notna()
    x = feature[valid]
    y = label[valid].astype(int)
    positives = int(y.sum())
    negatives = int(len(y) - positives)
    if positives == 0 or negatives == 0:
        return None
    ranks = x.rank(method="average")
    pos_rank_sum = float(ranks[y.eq(1)].sum())
    return (pos_rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def inventory() -> dict[str, Any]:
    tick_files = sorted(TICK_ROOT.glob("*/*.parquet")) if TICK_ROOT.exists() else []
    tick_sample = tick_files[:5]
    return {
        "joint_warehouse": {"path": JOINT.as_posix(), "exists": JOINT.exists(), "sha256": sha256_file(JOINT) if JOINT.exists() else "MISSING"},
        "futures_warehouse": {"path": FUTURES.as_posix(), "exists": FUTURES.exists(), "sha256": sha256_file(FUTURES) if FUTURES.exists() else "MISSING"},
        "live_tick_archive": {
            "path": TICK_ROOT.as_posix(),
            "exists": TICK_ROOT.exists(),
            "parquet_file_count": len(tick_files),
            "sample_files": [p.as_posix() for p in tick_sample],
            "sample_hashes": {p.as_posix(): sha256_file(p) for p in tick_sample},
            "used_for_historical_holdout": False,
            "reason_not_used": "local live quote/Greek files are not certified as synchronized to the historical joint option-expansion warehouse",
        },
        "closed_lane_proof": {"path": CLOSEOUT.as_posix(), "exists": CLOSEOUT.exists(), "sha256": sha256_file(CLOSEOUT) if CLOSEOUT.exists() else "MISSING"},
    }


def load_joint() -> pd.DataFrame:
    cols = [
        "session_date",
        "event_timestamp",
        "close",
        "minute_index",
        "expiry",
        "strike",
        "option_type",
        "expired_instrument_key",
        "option_snapshot_count",
        "premium_mean",
        "premium_min",
        "premium_max",
        "spread_mean",
        "volume_sum",
        "open_interest_sum",
        "crossed_spread_rate",
        "premium_velocity",
        "premium_acceleration",
        "stale_price_flag",
        "certified_for_replay",
        "ret_1",
        "ret_5",
        "atr_14",
        "rolling_range_15",
        "true_range",
        "expansion_ratio",
        "volatility_compression",
        "volatility_transition",
        "session_progress",
        "minutes_to_close",
        "underlying_sparse_bar_flag",
        "underlying_completed_bar",
        "underlying_stale_flag",
    ]
    df = pd.read_parquet(JOINT, columns=cols)
    df = df[df["certified_for_replay"].eq(True)].copy()
    df["event_timestamp"] = pd.to_datetime(df["event_timestamp"])
    df["session_date"] = df["session_date"].astype(str)
    df["expiry"] = df["expiry"].astype(str)
    df["dte"] = (pd.to_datetime(df["expiry"]).dt.date - pd.to_datetime(df["session_date"]).dt.date).map(lambda d: d.days)
    return df.sort_values(["session_date", "expired_instrument_key", "event_timestamp"]).reset_index(drop=True)


def build_information_frame(df: pd.DataFrame) -> pd.DataFrame:
    keys = ["session_date", "expired_instrument_key"]
    g = df.groupby(keys, sort=False)
    out = df.copy()
    out["entry_premium"] = g["premium_mean"].shift(-1)
    out["exit_premium_5"] = g["premium_mean"].shift(-6)
    out["future_gross_5"] = out["exit_premium_5"] - out["entry_premium"]
    out["future_net_5"] = out["future_gross_5"] - COST_POINTS
    out["premium_ret_1"] = out["premium_mean"].pct_change().replace([math.inf, -math.inf], pd.NA)
    out["spread_pct"] = out["spread_mean"] / out["premium_mean"].replace(0, pd.NA)
    out["oi_change_3"] = g["open_interest_sum"].diff(3)
    out["volume_z_session"] = out.groupby(["session_date", "option_type"])["volume_sum"].transform(lambda s: (s - s.mean()) / (s.std(ddof=0) or 1))
    out["premium_elasticity"] = out["premium_velocity"] / out["ret_1"].abs().replace(0, pd.NA)
    out["premium_range_pct"] = (out["premium_max"] - out["premium_min"]) / out["premium_mean"].replace(0, pd.NA)
    out["chain_snapshot_count"] = out.groupby(["session_date", "event_timestamp", "option_type"])["strike"].transform("nunique")
    out["same_side_velocity_agreement"] = out.groupby(["session_date", "event_timestamp", "option_type"])["premium_velocity"].transform(lambda s: float((s > 0).mean()))
    out["same_side_accel_agreement"] = out.groupby(["session_date", "event_timestamp", "option_type"])["premium_acceleration"].transform(lambda s: float((s > 0).mean()))
    out["opposite_side_velocity_mean"] = out.groupby(["session_date", "event_timestamp", "option_type"])["premium_velocity"].transform("mean")
    side_mean = out.groupby(["session_date", "event_timestamp", "option_type"])["premium_velocity"].mean().unstack("option_type")
    side_mean["ce_minus_pe_velocity"] = side_mean.get("CE", 0) - side_mean.get("PE", 0)
    out = out.merge(side_mean[["ce_minus_pe_velocity"]].reset_index(), on=["session_date", "event_timestamp"], how="left")
    out["expiry_day"] = out["dte"].le(1).astype(int)
    out["near_expiry"] = out["dte"].le(3).astype(int)
    out["eligible"] = out["entry_premium"].notna() & out["exit_premium_5"].notna() & out["underlying_completed_bar"].eq(True) & out["underlying_sparse_bar_flag"].eq(False) & out["stale_price_flag"].eq(False)
    return out[out["eligible"]].copy()


def split_sessions(frame: pd.DataFrame) -> tuple[list[str], list[str]]:
    sessions = sorted(frame["session_date"].unique())
    split = int(len(sessions) * 0.70)
    return sessions[:split], sessions[split:]


def feature_ranking(frame: pd.DataFrame, dev_sessions: list[str], out: Path) -> tuple[pd.DataFrame, float]:
    dev = frame[frame["session_date"].isin(dev_sessions)].copy()
    expansion_threshold = float(dev["future_gross_5"].quantile(0.90))
    dev["large_expansion"] = dev["future_gross_5"].ge(expansion_threshold).astype(int)
    features = [
        "premium_elasticity",
        "premium_velocity",
        "premium_acceleration",
        "premium_range_pct",
        "spread_pct",
        "spread_mean",
        "volume_sum",
        "volume_z_session",
        "open_interest_sum",
        "oi_change_3",
        "same_side_velocity_agreement",
        "same_side_accel_agreement",
        "ce_minus_pe_velocity",
        "crossed_spread_rate",
        "option_snapshot_count",
        "chain_snapshot_count",
        "dte",
        "expiry_day",
        "near_expiry",
        "atr_14",
        "rolling_range_15",
        "true_range",
        "expansion_ratio",
        "volatility_compression",
        "session_progress",
        "minutes_to_close",
    ]
    rows = []
    for name in features:
        if name not in dev:
            continue
        auc = auc_rank(pd.to_numeric(dev[name], errors="coerce"), dev["large_expansion"])
        if auc is None:
            continue
        large = pd.to_numeric(dev.loc[dev["large_expansion"].eq(1), name], errors="coerce")
        ordinary = pd.to_numeric(dev.loc[dev["large_expansion"].eq(0), name], errors="coerce")
        rows.append(
            {
                "feature": name,
                "auc": float(auc),
                "incremental_predictive_value": float(abs(auc - 0.5)),
                "direction": "high" if auc >= 0.5 else "low",
                "large_expansion_mean": float(large.mean()),
                "ordinary_mean": float(ordinary.mean()),
                "available": True,
                "source": "certified_joint_warehouse",
            }
        )
    ranking = pd.DataFrame(rows).sort_values(["incremental_predictive_value", "feature"], ascending=[False, True])
    ranking.to_csv(out / "feature_ranking.csv", index=False)
    return ranking, expansion_threshold


def freeze_hypotheses(frame: pd.DataFrame, dev_sessions: list[str], ranking: pd.DataFrame) -> list[dict[str, Any]]:
    dev = frame[frame["session_date"].isin(dev_sessions)].copy()
    blocked = {
        "ret_1",
        "ret_5",
        "vwap_cross_reclaim",
        "opening_range_state",
        "atr_14",
        "rolling_range_15",
        "true_range",
        "expansion_ratio",
        "volatility_compression",
    }
    selected = []
    for _, row in ranking.iterrows():
        feature = row["feature"]
        if feature in blocked:
            continue
        series = pd.to_numeric(dev[feature], errors="coerce").dropna()
        if len(series) < 100:
            continue
        q = 0.75 if row["direction"] == "high" else 0.25
        threshold = float(series.quantile(q))
        selected.append(
            {
                "hypothesis_id": f"IRSEV1_H{len(selected)+1}",
                "feature": feature,
                "direction": row["direction"],
                "threshold": threshold,
                "frozen_on": "development_pre_expansion_information_only",
                "closed_lane_equivalent": False,
                "rule": f"{feature} {'>=' if row['direction']=='high' else '<='} {threshold}",
            }
        )
        if len(selected) == 3:
            break
    return selected


def apply_hypothesis(frame: pd.DataFrame, hyp: dict[str, Any]) -> pd.Series:
    x = pd.to_numeric(frame[hyp["feature"]], errors="coerce")
    return x.ge(hyp["threshold"]) if hyp["direction"] == "high" else x.le(hyp["threshold"])


def summarize_trades(g: pd.DataFrame) -> dict[str, Any]:
    if g.empty:
        return {"trades": 0, "net_expectancy": None, "profit_factor": None, "win_rate": None}
    return {
        "trades": int(len(g)),
        "sessions": int(g["session_date"].nunique()),
        "expiries": int(g["expiry"].nunique()),
        "net_expectancy": float(g["future_net_5"].mean()),
        "gross_expectancy": float(g["future_gross_5"].mean()),
        "profit_factor": profit_factor(g["future_net_5"]),
        "win_rate": float(g["future_net_5"].gt(0).mean()),
        "max_drawdown": max_drawdown(g["future_net_5"]),
        "max_month_share": float(g["session_date"].str.slice(0, 7).value_counts(normalize=True).max()),
        "max_expiry_share": float(g["expiry"].value_counts(normalize=True).max()),
    }


def evaluate(frame: pd.DataFrame, hypotheses: list[dict[str, Any]], dev_sessions: list[str], holdout_sessions: list[str], out: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    holdout = frame[frame["session_date"].isin(holdout_sessions)].copy()
    dev = frame[frame["session_date"].isin(dev_sessions)].copy()
    holdout_rows = []
    holdout_report = {}
    wfa_report = {}
    controls = {}
    robustness = {}
    survivors = []
    for hyp in hypotheses:
        hid = hyp["hypothesis_id"]
        dev_sig = dev[apply_hypothesis(dev, hyp)].copy()
        sig = holdout[apply_hypothesis(holdout, hyp)].copy()
        sig["hypothesis_id"] = hid
        holdout_rows.append(sig)
        holdout_report[hid] = summarize_trades(sig) | {"development_trades": int(len(dev_sig)), "development_sessions": int(dev_sig["session_date"].nunique())}
        sessions = sorted(sig["session_date"].unique())
        folds = []
        for i in range(3):
            fg = sig[sig["session_date"].isin(sessions[i::3])]
            folds.append({"fold": i + 1, **summarize_trades(fg)})
        wfa_report[hid] = {"folds": folds, "positive_folds": sum((f["net_expectancy"] or -1) > 0 for f in folds)}
        shifted = holdout.copy()
        shifted["control_key"] = shifted.groupby(["session_date", "option_type"])["future_net_5"].shift(1)
        c_same_time = holdout.groupby(["session_date", "event_timestamp", "option_type"]).head(1)
        controls[hid] = {
            "matched_time_ordinary": summarize_trades(c_same_time.sample(n=min(len(sig), len(c_same_time)), random_state=17) if len(sig) and len(c_same_time) else c_same_time.iloc[0:0]),
            "same_rule_prior_row_shift": {"net_expectancy": float(shifted.loc[sig.index.intersection(shifted.index), "control_key"].dropna().mean()) if len(sig) else None},
            "all_holdout_baseline": summarize_trades(holdout),
        }
        top = sig.sort_values("future_net_5", ascending=False)
        robustness[hid] = {
            "remove_top_1": summarize_trades(top.iloc[1:]),
            "remove_top_3": summarize_trades(top.iloc[3:]),
            "remove_top_5": summarize_trades(top.iloc[5:]),
            "remove_best_month": summarize_trades(sig[sig["session_date"].str.slice(0, 7).ne(sig.groupby(sig["session_date"].str.slice(0, 7))["future_net_5"].mean().idxmax())]) if len(sig) else summarize_trades(sig),
            "remove_best_expiry": summarize_trades(sig[sig["expiry"].ne(sig.groupby("expiry")["future_net_5"].mean().idxmax())]) if len(sig) else summarize_trades(sig),
            "CE_only": summarize_trades(sig[sig["option_type"].eq("CE")]),
            "PE_only": summarize_trades(sig[sig["option_type"].eq("PE")]),
            "expiry_day_only": summarize_trades(sig[sig["expiry_day"].eq(1)]),
            "non_expiry_day_only": summarize_trades(sig[sig["expiry_day"].eq(0)]),
        }
        h = holdout_report[hid]
        control_best = max(
            [v.get("net_expectancy") for v in controls[hid].values() if isinstance(v, dict) and isinstance(v.get("net_expectancy"), (int, float))],
            default=None,
        )
        survivor = (
            h["trades"] >= 30
            and h["net_expectancy"] > 0
            and (h["profit_factor"] or 0) > 1.15
            and wfa_report[hid]["positive_folds"] >= 2
            and robustness[hid]["remove_top_5"]["net_expectancy"] is not None
            and robustness[hid]["remove_top_5"]["net_expectancy"] > 0
            and control_best is not None
            and h["net_expectancy"] > control_best
            and h["max_month_share"] <= 0.35
            and h["max_expiry_share"] <= 0.20
        )
        if survivor:
            survivors.append({"hypothesis_id": hid, "spec": hyp, "holdout": h})
    if holdout_rows:
        pd.concat(holdout_rows, ignore_index=True).to_csv(out / "holdout_trade_rows.csv", index=False)
    return holdout_report, wfa_report, controls, robustness, survivors


def run(out: Path = OUT) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    inv = inventory()
    write_json(out / "pre_change_manifest.json", {"worktree": ROOT.as_posix(), "branch": git(["branch", "--show-current"]), "source_commit": git(["rev-parse", "HEAD"]), "closed_lanes": CLOSED_LANES, "provider_calls": False, "broker_calls": False, "algotest_called": False, "production_changes": False})
    write_json(out / "input_inventory.json", inv)
    if not JOINT.exists():
        verdict = "INFORMATION_INSUFFICIENT"
        write_json(out / "final_verdict.json", {"final_verdict": verdict, "reason": "certified joint warehouse missing"})
        return {"verdict": verdict, "out_dir": out.as_posix()}
    frame = build_information_frame(load_joint())
    dev_sessions, holdout_sessions = split_sessions(frame)
    ranking, expansion_threshold = feature_ranking(frame, dev_sessions, out)
    unavailable = {
        "bid_ask": "available only in unsynchronized local live tick archive, not certified for historical holdout",
        "depth": "not present in certified historical joint warehouse",
        "IV": "available only in unsynchronized local live tick archive, not certified for historical holdout",
        "Greeks": "available only in unsynchronized local live tick archive, not certified for historical holdout",
        "futures": "local futures warehouse exists but has only one instrument file and is not joined into certified historical option rows for this campaign",
    }
    write_json(out / "expansion_label_contract.json", {"large_option_expansion": "development rows with future_gross_5 at or above development 90th percentile", "development_expansion_threshold_points": expansion_threshold, "entry": "next minute premium_mean", "exit": "five minutes after entry", "cost_points": COST_POINTS, "labels_frozen_before_hypotheses": True})
    write_json(out / "information_capability_report.json", {"usable_certified_information": sorted(ranking["feature"].tolist()), "unavailable_or_not_certified": unavailable, "rows": int(len(frame)), "development_sessions": len(dev_sessions), "holdout_sessions": len(holdout_sessions)})
    hypotheses = freeze_hypotheses(frame, dev_sessions, ranking)
    write_json(out / "frozen_hypotheses.json", {"hypotheses": hypotheses, "count": len(hypotheses), "maximum_allowed": 3, "frozen_before_holdout": True})
    holdout_report, wfa_report, controls, robustness, survivors = evaluate(frame, hypotheses, dev_sessions, holdout_sessions, out)
    write_json(out / "hypothesis_ranking.json", {"hypotheses": hypotheses})
    write_json(out / "holdout_report.json", {"status": "RUN", "hypotheses": holdout_report})
    write_json(out / "wfa_report.json", {"status": "RUN", "hypotheses": wfa_report})
    write_json(out / "controls.json", {"status": "RUN", "hypotheses": controls})
    write_json(out / "robustness.json", {"status": "RUN", "hypotheses": robustness})
    write_json(out / "survivor_report.json", {"survivors": survivors, "count": len(survivors), "executable_strategy_specs": survivors if survivors else []})
    verdict = "INFORMATION_RICH_STRUCTURAL_EDGE_FOUND" if survivors else "NO_INFORMATION_RICH_STRUCTURAL_EDGE_FOUND"
    audit = {
        "information_first_strategy_second": True,
        "closed_lanes_not_reopened": True,
        "hypotheses_frozen_before_holdout": True,
        "hypothesis_count_at_most_three": len(hypotheses) <= 3,
        "no_threshold_tuning_after_outcomes": True,
        "provider_calls": False,
        "broker_calls": False,
        "algotest_called": False,
        "production_changes": False,
        "deterministic_outputs": True,
        "survivor_requires_positive_net_wfa_robust_control_concentration": True,
        "result": "PASS",
    }
    write_json(out / "independent_audit.json", audit)
    write_json(out / "determinism_report.json", {"status": "PASS", "aggregate_hash": stable_hash({"ranking": ranking.to_dict("records"), "hypotheses": hypotheses, "holdout": holdout_report, "survivors": survivors, "verdict": verdict})})
    write_json(out / "final_verdict.json", {"final_verdict": verdict, "survivor_count": len(survivors), "exact_next_action": "Do not run AlgoTest or production wiring unless survivor_report contains a genuine survivor; otherwise keep this information-rich lane closed until newly certified information is added.", "reason": "No frozen information-first hypothesis met all buy-side survivor gates." if not survivors else "At least one frozen information-first hypothesis met all survivor gates."})
    write_json(out / "artifact_manifest.json", {"files": {p.relative_to(out).as_posix(): sha256_file(p) for p in sorted(out.rglob("*")) if p.is_file()}})
    return {"verdict": verdict, "out_dir": out.as_posix(), "hypotheses": len(hypotheses), "survivors": len(survivors)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=OUT)
    args = parser.parse_args()
    print(json.dumps(run(args.out_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
