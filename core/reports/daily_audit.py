from __future__ import annotations

import json
import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import pandas as pd

from config import config as cfg


def _conn():
    Path(cfg.TRADE_DB_PATH).parent.mkdir(exist_ok=True)
    return sqlite3.connect(cfg.TRADE_DB_PATH)


def _load_decisions(for_date: Optional[date] = None) -> pd.DataFrame:
    try:
        with _conn() as conn:
            df = pd.read_sql_query("SELECT * FROM decision_events", conn)
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    try:
        df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
        if for_date:
            df = df[df["ts"].dt.date == for_date]
    except Exception:
        pass
    return df


def _load_governance(for_date: Optional[date] = None) -> pd.DataFrame:
    path = Path("logs/trade_ledger.jsonl")
    if not path.exists():
        return pd.DataFrame()
    rows = []
    for line in path.read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    try:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        if for_date:
            df = df[df["timestamp"].dt.date == for_date]
    except Exception:
        pass
    return df


def _summary_tables(df: pd.DataFrame) -> dict:
    out = {}
    if df.empty:
        return out
    out["total"] = int(len(df))
    out["approved"] = int((df.get("risk_allowed") == 1).sum())
    out["blocked"] = int((df.get("risk_allowed") == 0).sum())

    if "veto_reasons" in df.columns:
        reasons = df["veto_reasons"].dropna().astype(str)
        reason_counts = {}
        for raw in reasons:
            try:
                if raw.startswith("["):
                    r = json.loads(raw)
                    for x in r:
                        reason_counts[x] = reason_counts.get(x, 0) + 1
                else:
                    reason_counts[raw] = reason_counts.get(raw, 0) + 1
            except Exception:
                reason_counts[raw] = reason_counts.get(raw, 0) + 1
        out["top_veto_reasons"] = sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    if "strategy_id" in df.columns and "pnl_horizon_15m" in df.columns:
        strat = df.groupby("strategy_id")["pnl_horizon_15m"].mean().sort_values(ascending=False)
        out["strategy_pnl_15m"] = strat.head(10).round(3).to_dict()

    return out


def _html_report(summary: dict, decisions: pd.DataFrame, governance: pd.DataFrame, report_date: Optional[date]) -> str:
    title = f"Daily Audit Report — {report_date or datetime.now().date()}"
    css = """
    <style>
    body { font-family: Arial, sans-serif; color: #111; padding: 24px; }
    h1, h2 { margin: 8px 0; }
    .box { border: 1px solid #ddd; padding: 12px; margin: 12px 0; border-radius: 6px; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #ddd; padding: 6px 8px; font-size: 12px; }
    th { background: #f5f5f5; }
    .muted { color: #666; }
    </style>
    """
    html = ["<html><head>", css, f"<title>{title}</title></head><body>"]
    html.append(f"<h1>{title}</h1>")

    html.append("<div class='box'>")
    html.append(f"<b>Total decisions:</b> {summary.get('total', 0)}<br>")
    html.append(f"<b>Approved:</b> {summary.get('approved', 0)}<br>")
    html.append(f"<b>Blocked:</b> {summary.get('blocked', 0)}")
    html.append("</div>")

    if summary.get("top_veto_reasons"):
        html.append("<div class='box'><h2>Top Veto Reasons</h2><ul>")
        for reason, count in summary["top_veto_reasons"]:
            html.append(f"<li>{reason}: {count}</li>")
        html.append("</ul></div>")

    if summary.get("strategy_pnl_15m"):
        html.append("<div class='box'><h2>Strategy Avg PnL (15m)</h2><ul>")
        for strat, val in summary["strategy_pnl_15m"].items():
            html.append(f"<li>{strat}: {val}</li>")
        html.append("</ul></div>")

    if not decisions.empty:
        html.append("<div class='box'><h2>Recent Decisions</h2>")
        cols = [c for c in ["ts", "symbol", "strategy_id", "side", "score_0_100", "risk_allowed", "exec_guard_allowed", "veto_reasons"] if c in decisions.columns]
        html.append(decisions[cols].tail(200).to_html(index=False))
        html.append("</div>")

    if not governance.empty:
        html.append("<div class='box'><h2>Governance Ledger (latest)</h2>")
        cols = [c for c in ["timestamp", "trade_id", "symbol", "strategy", "regime"] if c in governance.columns]
        html.append(governance[cols].tail(200).to_html(index=False))
        html.append("</div>")

    html.append("</body></html>")
    return "\n".join(html)


def generate_audit_report(output_html: str, output_pdf: Optional[str] = None, report_date: Optional[date] = None) -> dict:
    d = report_date or datetime.now().date()
    decisions = _load_decisions(for_date=d)
    governance = _load_governance(for_date=d)
    summary = _summary_tables(decisions)
    html = _html_report(summary, decisions, governance, d)

    Path(output_html).parent.mkdir(exist_ok=True)
    Path(output_html).write_text(html)

    pdf_written = False
    if output_pdf:
        try:
            from weasyprint import HTML  # type: ignore
            HTML(string=html).write_pdf(output_pdf)
            pdf_written = True
        except Exception:
            pdf_written = False

    return {
        "date": str(d),
        "output_html": output_html,
        "output_pdf": output_pdf if pdf_written else None,
        "summary": summary,
    }
