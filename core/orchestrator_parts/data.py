import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from config import config as cfg
from core.reports.daily_audit import build_daily_audit, write_daily_audit_placeholder
from core.reports.execution_report import build_execution_report, write_execution_report_placeholder
from core.risk_utils import to_pct
from core.time_utils import now_ist, now_utc_epoch


def update_risk_pct_fields(orch):
    try:
        equity_high = orch.portfolio.get("equity_high", orch.portfolio.get("capital", 0.0))
        daily_pnl = orch.portfolio.get("daily_profit", 0.0) + orch.portfolio.get("daily_loss", 0.0)
        orch.portfolio["daily_pnl"] = daily_pnl
        orch.portfolio["daily_pnl_pct"] = to_pct(daily_pnl, equity_high)
        open_risk = orch._open_risk()
        orch.portfolio["open_risk"] = open_risk
        orch.portfolio["open_risk_pct"] = to_pct(open_risk, equity_high)
    except Exception:
        pass


def quote_age_sec(quote_ts):
    if not quote_ts:
        return None
    try:
        if isinstance(quote_ts, (int, float)):
            ts = float(quote_ts)
        else:
            text = str(quote_ts)
            try:
                ts = float(text)
            except Exception:
                ts = datetime.fromisoformat(text).timestamp()
        return max(0.0, now_utc_epoch() - ts)
    except Exception:
        return None


def quote_ts_epoch(quote_ts):
    if not quote_ts:
        return None
    if isinstance(quote_ts, (int, float)):
        return float(quote_ts)
    try:
        return float(quote_ts)
    except Exception:
        pass
    try:
        text = str(quote_ts)
        if text.endswith("Z"):
            text = text.replace("Z", "+00:00")
        return datetime.fromisoformat(text).timestamp()
    except Exception:
        return None


def load_truth_dataset_for_reports():
    truth_path = Path(getattr(cfg, "TRUTH_DATASET_PATH", "data/truth_dataset.parquet"))
    if not truth_path.exists():
        return pd.DataFrame(), f"truth_dataset_missing:{truth_path}"
    try:
        return pd.read_parquet(truth_path), None
    except Exception as exc:
        return pd.DataFrame(), f"truth_dataset_read_error:{type(exc).__name__}"


def write_cycle_reports(cycle_reason=None, decision_traces=None, config_snapshot=None):
    day = now_ist().date().isoformat()
    audit_path = Path(f"logs/daily_audit_{day}.json")
    execution_path = Path(f"logs/execution_report_{day}.json")
    report_reason = cycle_reason or "cycle_complete"
    decision_traces = list(decision_traces or [])
    config_snapshot = dict(config_snapshot or {})
    dataset, data_reason = load_truth_dataset_for_reports()
    if data_reason:
        report_reason = f"{report_reason}|{data_reason}"
    try:
        if dataset.empty:
            write_daily_audit_placeholder(
                day,
                audit_path,
                report_reason,
                decision_traces=decision_traces,
                config_snapshot=config_snapshot,
            )
        else:
            build_daily_audit(
                dataset,
                day,
                audit_path,
                decision_traces=decision_traces,
                config_snapshot=config_snapshot,
            )
    except Exception as exc:
        write_daily_audit_placeholder(
            day,
            audit_path,
            f"audit_write_error:{type(exc).__name__}|{report_reason}",
            decision_traces=decision_traces,
            config_snapshot=config_snapshot,
        )
    try:
        if dataset.empty:
            write_execution_report_placeholder(day, execution_path, report_reason)
        else:
            build_execution_report(dataset, day, execution_path)
    except Exception as exc:
        write_execution_report_placeholder(
            day,
            execution_path,
            f"execution_write_error:{type(exc).__name__}|{report_reason}",
        )
