from __future__ import annotations

import json
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import pandas as pd


def _load_jsonl(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    rows = []
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return pd.DataFrame(rows)


def run_execution_report(output_path: str = "logs/execution_report.json", report_date: Optional[date] = None) -> dict:
    df = _load_jsonl("logs/fill_quality.jsonl")
    if df.empty:
        report = {"generated_at": datetime.now().isoformat(), "status": "no_data"}
        Path(output_path).write_text(json.dumps(report, indent=2))
        return report

    df["ts"] = pd.to_datetime(df.get("ts"), unit="s", errors="coerce")
    if report_date:
        df = df[df["ts"].dt.date == report_date]

    report = {
        "generated_at": datetime.now().isoformat(),
        "fills": int(df.get("fill_price").notna().sum()),
        "fill_ratio": float(df.get("fill_price").notna().mean() if len(df) else 0),
        "avg_slippage": float(pd.to_numeric(df.get("slippage_vs_mid"), errors="coerce").mean() or 0),
        "avg_time_to_fill": float(pd.to_numeric(df.get("time_to_fill"), errors="coerce").mean() or 0),
        "avg_execution_quality": float(pd.to_numeric(df.get("execution_quality_score"), errors="coerce").mean() or 0),
    }

    Path(output_path).parent.mkdir(exist_ok=True)
    Path(output_path).write_text(json.dumps(report, indent=2))
    return report
