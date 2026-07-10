from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from config import config as cfg
from core.paths import data_root, logs_dir
from core.reports.daily_audit import build_daily_audit, write_daily_audit_placeholder
from core.reports.execution_report import build_execution_report, write_execution_report_placeholder
from core.time_utils import now_ist, now_utc_epoch


def snapshot_symbol_payload(market_data: dict, warnings: list[str]) -> dict:
    return {"symbol": market_data.get("symbol"), "warnings": list(warnings or []), "ohlc": {k: market_data.get(k) for k in ("open", "high", "low", "close")}, "atm_strike": market_data.get("atm_strike") or market_data.get("strike")}


def scan_visible_suggestions(path: Path) -> dict:
    try:
        visible = 0
        if path.exists():
            visible = sum(1 for _ in path.open("r", encoding="utf-8"))
        return {"path": str(path), "visible_count": visible}
    except Exception:
        return {"path": str(path), "visible_count": 0}


def zero_visible_counts(counts: dict) -> dict:
    out = dict(counts or {})
    for key in list(out.keys()):
        if isinstance(out[key], (int, float)):
            out[key] = 0
    return out


def build_pipeline_funnel_payload(*, counts: dict | None = None) -> dict:
    return {"counts": dict(counts or {})}


def build_top_opportunities_payload(*, rows: list | None = None, label: str | None = None) -> dict:
    return {"label": label, "rows": list(rows or [])}


def build_ranked_pipeline_runtime_report(*, rows: list | None = None, label: str | None = None) -> dict:
    return {"label": label, "rows": list(rows or [])}


def write_ranked_pipeline_runtime_evidence(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


def load_truth_dataset_for_reports():
    truth_path = Path(getattr(cfg, "TRUTH_DATASET_PATH", str(data_root() / "truth_dataset.parquet")))
    if not truth_path.exists():
        return pd.DataFrame(), f"truth_dataset_missing:{truth_path}"
    try:
        return pd.read_parquet(truth_path), None
    except Exception as exc:
        return pd.DataFrame(), f"truth_dataset_read_error:{type(exc).__name__}"


def write_cycle_reports(cycle_reason=None, decision_traces=None, config_snapshot=None):
    day = now_ist().date().isoformat()
    audit_path = logs_dir() / f"daily_audit_{day}.json"
    execution_path = logs_dir() / f"execution_report_{day}.json"
    report_reason = cycle_reason or "cycle_complete"
    decision_traces = list(decision_traces or [])
    config_snapshot = dict(config_snapshot or {})
    dataset, data_reason = load_truth_dataset_for_reports()
    if data_reason:
        report_reason = f"{report_reason}|{data_reason}"
    try:
        if dataset.empty:
            write_daily_audit_placeholder(day, audit_path, report_reason, decision_traces=decision_traces, config_snapshot=config_snapshot)
        else:
            build_daily_audit(dataset, day, audit_path, decision_traces=decision_traces, config_snapshot=config_snapshot)
    except Exception as exc:
        write_daily_audit_placeholder(day, audit_path, f"audit_write_error:{type(exc).__name__}|{report_reason}", decision_traces=decision_traces, config_snapshot=config_snapshot)
    try:
        if dataset.empty:
            write_execution_report_placeholder(day, execution_path, report_reason)
        else:
            build_execution_report(dataset, day, execution_path)
    except Exception as exc:
        write_execution_report_placeholder(day, execution_path, f"execution_write_error:{type(exc).__name__}|{report_reason}")

