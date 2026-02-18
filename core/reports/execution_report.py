import json
from pathlib import Path
import pandas as pd


def write_execution_report_placeholder(day: str, out_path: Path, reason: str) -> Path:
    out = {
        "date": day,
        "reason": reason,
        "fill_rate": 0.0,
        "avg_time_to_fill": None,
        "slippage_percentiles": {"p50": None, "p90": None, "p99": None},
        "spread_percentiles": {"p50": None, "p90": None, "p99": None},
        "missed_fill_reasons": {},
        "executions": [],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str))
    return out_path


def build_execution_report(df: pd.DataFrame, day: str, out_path: Path) -> Path:
    if df is None or df.empty:
        return write_execution_report_placeholder(day, out_path, "truth_dataset_empty")
    df = df.copy()
    if "ts" not in df.columns:
        return write_execution_report_placeholder(day, out_path, "missing_column:ts")
    df["ts_dt"] = pd.to_datetime(df["ts"], errors="coerce")
    df = df[df["ts_dt"].dt.date.astype(str) == day]
    if df.empty:
        return write_execution_report_placeholder(day, out_path, "no_decisions_for_day")

    filled = df[df["filled_bool"] == 1]
    total = len(df)
    fill_rate = float(len(filled) / total) if total else 0.0

    time_to_fill = filled["time_to_fill_sec"].dropna()
    slippage = filled["slippage_vs_mid"].dropna()
    spread = df["spread_pct"].dropna() if "spread_pct" in df.columns else pd.Series(dtype=float)
    missed_reasons = df["missed_fill_reason"].value_counts(dropna=True).to_dict() if "missed_fill_reason" in df.columns else {}
    executions = []
    if not filled.empty:
        cols = ["decision_id", "trade_id", "symbol", "strategy_id", "fill_price", "time_to_fill_sec", "slippage_vs_mid"]
        existing = [col for col in cols if col in filled.columns]
        executions = filled[existing].to_dict(orient="records")

    out = {
        "date": day,
        "reason": None if executions else "no_executions_for_day",
        "fill_rate": fill_rate,
        "avg_time_to_fill": float(time_to_fill.mean()) if not time_to_fill.empty else None,
        "slippage_percentiles": {
            "p50": float(slippage.quantile(0.5)) if not slippage.empty else None,
            "p90": float(slippage.quantile(0.9)) if not slippage.empty else None,
            "p99": float(slippage.quantile(0.99)) if not slippage.empty else None,
        },
        "spread_percentiles": {
            "p50": float(spread.quantile(0.5)) if not spread.empty else None,
            "p90": float(spread.quantile(0.9)) if not spread.empty else None,
            "p99": float(spread.quantile(0.99)) if not spread.empty else None,
        },
        "missed_fill_reasons": missed_reasons,
        "executions": executions,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str))
    return out_path
