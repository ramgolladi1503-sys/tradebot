import argparse
import sys
from datetime import timedelta
from pathlib import Path
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import config as cfg
from core import model_registry
from core.reports.promotion_report import evaluate_promotion, write_promotion_report
from core.time_utils import now_ist


def _psi(expected, actual, bins=10):
    expected = np.asarray(expected, dtype=float)
    actual = np.asarray(actual, dtype=float)
    if len(expected) < 2 or len(actual) < 2:
        return 0.0
    quantiles = np.quantile(expected, np.linspace(0, 1, bins + 1))
    quantiles[0] -= 1e-9
    quantiles[-1] += 1e-9
    e_counts, _ = np.histogram(expected, bins=quantiles)
    a_counts, _ = np.histogram(actual, bins=quantiles)
    e_perc = e_counts / max(len(expected), 1)
    a_perc = a_counts / max(len(actual), 1)
    psi = 0.0
    for e, a in zip(e_perc, a_perc):
        e = max(e, 1e-6)
        a = max(a, 1e-6)
        psi += (a - e) * np.log(a / e)
    return float(psi)


def _ks(expected, actual):
    expected = np.sort(np.asarray(expected, dtype=float))
    actual = np.sort(np.asarray(actual, dtype=float))
    if len(expected) == 0 or len(actual) == 0:
        return 0.0
    data_all = np.sort(np.concatenate([expected, actual]))
    cdf_exp = np.searchsorted(expected, data_all, side="right") / len(expected)
    cdf_act = np.searchsorted(actual, data_all, side="right") / len(actual)
    return float(np.max(np.abs(cdf_exp - cdf_act)))


def _drift_gate(df: pd.DataFrame, features: list[str], psi_thr: float, ks_thr: float) -> tuple[bool, dict]:
    if df is None or df.empty:
        return False, {"reason": "empty_df"}
    df = df.copy()
    df["ts_dt"] = pd.to_datetime(df["ts"], errors="coerce")
    max_ts = df["ts_dt"].max()
    if pd.isna(max_ts):
        return False, {"reason": "missing_ts"}
    mid = max_ts - timedelta(days=max(1, cfg.PROMOTION_MIN_DAYS))
    recent = df[df["ts_dt"] >= mid]
    prev = df[df["ts_dt"] < mid]
    if recent.empty or prev.empty:
        return False, {"reason": "insufficient_history"}
    report = {}
    psi_max = 0.0
    ks_max = 0.0
    for col in features:
        if col not in df.columns:
            return False, {"reason": "missing_feature", "feature": col}
        psi = _psi(prev[col].dropna().values, recent[col].dropna().values)
        ks = _ks(prev[col].dropna().values, recent[col].dropna().values)
        report[col] = {"psi": psi, "ks": ks}
        psi_max = max(psi_max, psi)
        ks_max = max(ks_max, ks)
    ok = (psi_max <= psi_thr) and (ks_max <= ks_thr)
    report["psi_max"] = psi_max
    report["ks_max"] = ks_max
    return ok, report


def decide_promotion(report: dict, gates: dict) -> tuple[bool, list[str]]:
    reasons = []
    if report.get("chall_brier") is None or report.get("champ_brier") is None:
        reasons.append("missing_brier")
    if report.get("chall_ece") is None or report.get("champ_ece") is None:
        reasons.append("missing_ece")
    if report.get("chall_tail") is None or report.get("champ_tail") is None:
        reasons.append("missing_tail")
    if reasons:
        return False, reasons

    if report["chall_brier"] >= report["champ_brier"]:
        reasons.append("brier_not_improved")
    if (report["chall_ece"] - report["champ_ece"]) > gates["ece_max_delta"]:
        reasons.append("ece_worse")
    if report["chall_tail"] < report["champ_tail"]:
        reasons.append("tail_worse")

    for seg, vals in report.get("segments", {}).items():
        if vals.get("chall_brier") is None or vals.get("champ_brier") is None:
            continue
        delta = vals["chall_brier"] - vals["champ_brier"]
        if seg == "EVENT" and delta > gates["event_seg_max"]:
            reasons.append(f"event_segment_regress_{delta:.4f}")
        if delta > gates["seg_max"]:
            reasons.append(f"segment_regress_{seg}_{delta:.4f}")

    return (len(reasons) == 0), reasons


def main():
    parser = argparse.ArgumentParser(description="Promote challenger model using truth dataset and gates.")
    parser.add_argument("--family", default="xgb")
    parser.add_argument("--truth", default="data/truth_dataset.parquet")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    truth_path = Path(args.truth)
    if not truth_path.exists():
        raise SystemExit("truth_dataset.parquet not found. Run scripts/build_truth_dataset.py first.")

    df = pd.read_parquet(truth_path)
    if df.empty:
        raise SystemExit("truth_dataset.parquet is empty.")

    min_days = int(getattr(cfg, "PROMOTION_MIN_DAYS", 7))
    min_rows = int(getattr(cfg, "PROMOTION_MIN_ROWS", 100))
    start_day = (now_ist() - timedelta(days=min_days)).date().isoformat()

    required_cols = ["champion_proba", "challenger_proba"]
    for col in required_cols:
        if col not in df.columns or df[col].dropna().empty:
            raise SystemExit(f"Missing required column: {col}. Promotion requires logged shadow predictions.")

    try:
        report = evaluate_promotion(df, start_day, gates={"ece_bins": 10, "tail_k": cfg.PROMOTION_TAIL_WORST_K})
    except ValueError as e:
        raise SystemExit(str(e))
    if len(df) < min_rows:
        raise SystemExit("Insufficient rows for promotion window.")
    if "ts" in df.columns:
        ts = pd.to_datetime(df["ts"], errors="coerce").dropna()
        if ts.empty or (ts.max() - ts.min()).days < min_days:
            raise SystemExit("Insufficient shadow days for promotion window.")

    drift_ok, drift_report = _drift_gate(
        df,
        features=["score_0_100", "spread_pct", "xgb_proba", "ensemble_proba"],
        psi_thr=float(cfg.PROMOTION_PSI_MAX),
        ks_thr=float(cfg.PROMOTION_KS_MAX),
    )
    if not drift_ok:
        raise SystemExit(f"Drift gate failed: {json.dumps(drift_report)}")

    promote, reasons = decide_promotion(
        report,
        gates={
            "ece_max_delta": cfg.PROMOTION_ECE_MAX_DELTA,
            "seg_max": cfg.PROMOTION_SEGMENT_MAX_BRIER_WORSEN,
            "event_seg_max": cfg.PROMOTION_EVENT_MAX_BRIER_WORSEN,
        },
    )
    report["drift"] = drift_report
    report["decision"] = {"promote": promote, "reasons": reasons}

    out_path = Path(f"logs/models/promotion_{now_ist().date()}_{args.family}.json")
    write_promotion_report(report, out_path)

    if args.dry_run or not promote:
        print(json.dumps(report["decision"], indent=2))
        return

    shadow_path = model_registry.get_shadow(args.family)
    if not shadow_path:
        raise SystemExit("No shadow model registered for promotion.")
    model_registry.activate_model(args.family, shadow_path)
    print(f"Promoted shadow model to active: {shadow_path}")


if __name__ == "__main__":
    main()
