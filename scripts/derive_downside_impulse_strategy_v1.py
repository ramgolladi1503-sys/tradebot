from __future__ import annotations

import argparse
import json
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

EXPANSION_THRESHOLD = -0.0011372
HORIZON = 15
BASE_COST_BPS = 2.0


def _pf(values: pd.Series) -> float:
    wins = float(values[values > 0].sum())
    losses = float(-values[values < 0].sum())
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return wins / losses


def _metrics(frame: pd.DataFrame, value_col: str = "net_bps") -> dict[str, float]:
    if frame.empty:
        return {"trades": 0, "sessions": 0, "mean_bps": 0.0, "median_bps": 0.0, "win_rate": 0.0, "profit_factor": 0.0, "sum_bps": 0.0, "top5_session_share": 1.0}
    per_session = frame.groupby("session_date", sort=False)[value_col].sum().sort_values(ascending=False)
    positive_total = float(per_session[per_session > 0].sum())
    top5 = float(per_session.head(5).clip(lower=0).sum())
    return {
        "trades": int(len(frame)),
        "sessions": int(frame["session_date"].nunique()),
        "mean_bps": float(frame[value_col].mean()),
        "median_bps": float(frame[value_col].median()),
        "win_rate": float((frame[value_col] > 0).mean()),
        "profit_factor": float(_pf(frame[value_col])),
        "sum_bps": float(frame[value_col].sum()),
        "top5_session_share": float(top5 / positive_total) if positive_total > 0 else 1.0,
    }


def _dedupe(frame: pd.DataFrame, cooldown: int = HORIZON) -> pd.DataFrame:
    kept = []
    for _, group in frame.sort_values(["session_date", "timestamp"]).groupby("session_date", sort=False):
        last = -10**9
        for idx, row in group.iterrows():
            pos = int(row["session_pos"])
            if pos - last >= cooldown:
                kept.append(idx)
                last = pos
    return frame.loc[kept].sort_values(["session_date", "timestamp"]).reset_index(drop=True)


def _prepare(states: pd.DataFrame, delay: int = 1, cost_bps: float = BASE_COST_BPS) -> pd.DataFrame:
    df = states.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values(["session_date", "timestamp"]).reset_index(drop=True)
    df["session_pos"] = df.groupby("session_date", sort=False).cumcount()
    g = df.groupby("session_date", sort=False)
    df["entry_close"] = g["close"].shift(-delay)
    df["exit_close"] = g["close"].shift(-(delay + HORIZON))
    df["forward_return"] = df["exit_close"] / df["entry_close"] - 1.0
    df["signal"] = df["trend_return_medium"] <= EXPANSION_THRESHOLD
    candidates = df[df["signal"] & df["forward_return"].notna()].copy()
    candidates = _dedupe(candidates)
    candidates["pe_gross_bps"] = -candidates["forward_return"] * 10000.0
    candidates["ce_gross_bps"] = candidates["forward_return"] * 10000.0
    candidates["pe_net_bps"] = candidates["pe_gross_bps"] - cost_bps
    candidates["ce_net_bps"] = candidates["ce_gross_bps"] - cost_bps
    return candidates


def _splits(frame: pd.DataFrame) -> tuple[set[str], set[str], set[str]]:
    sessions = sorted(frame["session_date"].astype(str).unique())
    c1 = int(len(sessions) * 0.60)
    c2 = int(len(sessions) * 0.80)
    return set(sessions[:c1]), set(sessions[c1:c2]), set(sessions[c2:])


def _thresholds(train: pd.DataFrame) -> dict[str, list[float]]:
    quantiles = [0.25, 0.50, 0.75]
    features = [
        "below_vwap_dwell",
        "directional_efficiency_signed",
        "trend_path_efficiency",
        "lower_rejection_wick",
        "close_location_value",
        "vwap_cross_frequency",
        "range_short_long_ratio",
    ]
    return {feature: [float(train[feature].quantile(q)) for q in quantiles] for feature in features}


def _rules(train: pd.DataFrame) -> list[dict[str, object]]:
    q = _thresholds(train)
    rules: list[dict[str, object]] = []
    for dwell, eff, path, wick in product(q["below_vwap_dwell"][1:], q["directional_efficiency_signed"][:2], q["trend_path_efficiency"][1:], q["lower_rejection_wick"][:2]):
        rules.append({
            "name": f"PE_CONT_dwell{dwell:.4g}_eff{eff:.4g}_path{path:.4g}_wick{wick:.4g}",
            "side": "PE",
            "conditions": [
                ["below_vwap_dwell", ">=", dwell],
                ["directional_efficiency_signed", "<=", eff],
                ["trend_path_efficiency", ">=", path],
                ["lower_rejection_wick", "<=", wick],
                ["failed_progress_down", "==", 0.0],
            ],
        })
    for wick, clv, cross in product(q["lower_rejection_wick"][1:], q["close_location_value"][1:], q["vwap_cross_frequency"][:2]):
        rules.append({
            "name": f"CE_REV_wick{wick:.4g}_clv{clv:.4g}_cross{cross:.4g}",
            "side": "CE",
            "conditions": [
                ["failed_progress_down", "==", 1.0],
                ["lower_rejection_wick", ">=", wick],
                ["close_location_value", ">=", clv],
                ["vwap_cross_frequency", ">=", cross],
            ],
        })
    return rules


def _apply(frame: pd.DataFrame, rule: dict[str, object], cost_bps: float = BASE_COST_BPS) -> pd.DataFrame:
    mask = pd.Series(True, index=frame.index)
    for feature, op, threshold in rule["conditions"]:  # type: ignore[index]
        if op == ">=": mask &= frame[feature] >= threshold
        elif op == "<=": mask &= frame[feature] <= threshold
        elif op == "==": mask &= frame[feature] == threshold
        else: raise ValueError(op)
    selected = frame[mask].copy()
    gross_col = "pe_gross_bps" if rule["side"] == "PE" else "ce_gross_bps"
    selected["net_bps"] = selected[gross_col] - cost_bps
    return selected


def _eligible(metrics: dict[str, float]) -> bool:
    return metrics["trades"] >= 40 and metrics["sessions"] >= 25 and metrics["mean_bps"] > 0 and metrics["profit_factor"] > 1.05 and metrics["top5_session_share"] < 0.55


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    states = pd.read_parquet(args.dataset)
    base = _prepare(states, delay=1, cost_bps=BASE_COST_BPS)
    train_sessions, validation_sessions, holdout_sessions = _splits(states)
    train = base[base["session_date"].astype(str).isin(train_sessions)]
    validation = base[base["session_date"].astype(str).isin(validation_sessions)]
    holdout = base[base["session_date"].astype(str).isin(holdout_sessions)]

    scored = []
    for rule in _rules(train):
        vm = _metrics(_apply(validation, rule))
        if _eligible(vm):
            scored.append((vm["mean_bps"] * np.log1p(vm["trades"]) * (1.0 - vm["top5_session_share"]), rule, vm))
    scored.sort(key=lambda x: x[0], reverse=True)
    finalists = scored[:3]

    results = []
    for score, rule, vm in finalists:
        hm = _metrics(_apply(holdout, rule))
        delayed = _prepare(states, delay=2, cost_bps=BASE_COST_BPS)
        delayed_holdout = delayed[delayed["session_date"].astype(str).isin(holdout_sessions)]
        dm = _metrics(_apply(delayed_holdout, rule))
        stress = _metrics(_apply(holdout, rule, cost_bps=4.0))
        results.append({"rule": rule, "validation_score": float(score), "validation": vm, "holdout": hm, "one_extra_bar_delay_holdout": dm, "double_cost_holdout": stress})

    passed = [r for r in results if _eligible(r["holdout"]) and r["one_extra_bar_delay_holdout"]["mean_bps"] > 0 and r["double_cost_holdout"]["mean_bps"] > 0]
    verdict = "UNDERLYING_DIRECTIONAL_STRATEGY_CANDIDATE_FOUND" if passed else ("PROMISING_BUT_NOT_ROBUST" if results else "NO_DIRECTIONAL_STRATEGY_FOUND")
    report = {
        "verdict": verdict,
        "scope": "underlying directional proxy only; exact option contract replay still required",
        "frozen_expansion_threshold": EXPANSION_THRESHOLD,
        "entry_delay_bars": 1,
        "holding_bars": HORIZON,
        "round_trip_cost_bps": BASE_COST_BPS,
        "candidate_events": {"train": len(train), "validation": len(validation), "holdout": len(holdout)},
        "finalists": results,
        "passed": passed,
    }
    (args.output_dir / "strategy_derivation_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    pd.DataFrame([{**{"name": r["rule"]["name"], "side": r["rule"]["side"]}, **{f"validation_{k}": v for k, v in r["validation"].items()}, **{f"holdout_{k}": v for k, v in r["holdout"].items()}} for r in results]).to_csv(args.output_dir / "strategy_candidates.csv", index=False)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
