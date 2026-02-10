"""CLI explainability report for Decision objects stored in SQLite."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from typing import Any, Dict, List, Optional

from config import config as cfg


def _load_decision_by_id(db_path: str, decision_id: str) -> Optional[Dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            "SELECT decision_json FROM decision_log WHERE decision_id=?",
            (decision_id,),
        )
        row = cur.fetchone()
        return json.loads(row[0]) if row else None


def _load_latest_by_symbol(db_path: str, symbol: str) -> Optional[Dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            """
            SELECT decision_json FROM decision_log
            WHERE symbol=? ORDER BY ts_epoch DESC LIMIT 1
            """,
            (symbol,),
        )
        row = cur.fetchone()
        return json.loads(row[0]) if row else None


def _data_quality_flags(decision: Dict[str, Any]) -> List[str]:
    flags: List[str] = []
    market = decision.get("market", {})
    if market.get("spot") in (None, 0, 0.0):
        flags.append("missing_spot")
    if market.get("iv") is None and market.get("ivp") is None:
        flags.append("missing_iv_ivp")
    if market.get("vwap") is None:
        flags.append("missing_vwap")
    return flags


def _format_report(decision: Dict[str, Any]) -> str:
    strategy = decision.get("strategy", {})
    signals = decision.get("signals", {})
    outcome = decision.get("outcome", {})
    market = decision.get("market", {})
    status = outcome.get("status", "planned")
    headline = "TRADE" if status in ("planned", "submitted", "filled") else "NO TRADE"
    name = strategy.get("name", "")

    lines: List[str] = []
    lines.append(f"{headline}: {name}")
    lines.append("")
    lines.append("Reasons:")
    lines.append(f"- entry_reason: {strategy.get('entry_reason', '')}")
    lines.append(f"- pattern_flags: {signals.get('pattern_flags', [])}")
    lines.append(f"- rank_score: {signals.get('rank_score')}")
    lines.append(f"- confidence: {signals.get('confidence')}")

    reject = outcome.get("reject_reasons", [])
    if reject:
        lines.append("")
        lines.append("Reject reasons:")
        for r in reject:
            lines.append(f"- {r}")

    lines.append("")
    lines.append("Risk summary:")
    lines.append(f"- rr: {strategy.get('rr')}")
    lines.append(f"- max_loss: {strategy.get('max_loss')}")
    lines.append(f"- size: {strategy.get('size')}")
    lines.append(f"- stop/target: {strategy.get('stop')}/{strategy.get('target')}")

    lines.append("")
    lines.append("Data quality:")
    flags = _data_quality_flags(decision)
    lines.append(f"- flags: {flags}")
    lines.append(f"- spot: {market.get('spot')}")
    lines.append(f"- vwap: {market.get('vwap')}")
    lines.append(f"- iv: {market.get('iv')} ivp: {market.get('ivp')}")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Explain a Decision from decision_log")
    parser.add_argument("--decision-id", help="Decision ID to load")
    parser.add_argument("--symbol", help="Symbol to load latest decision")
    parser.add_argument("--db", default=getattr(cfg, "DECISION_DB_PATH", "data/trades.db"))
    args = parser.parse_args()

    if not args.decision_id and not args.symbol:
        print("Provide --decision-id or --symbol", file=sys.stderr)
        return 2

    if args.decision_id:
        decision = _load_decision_by_id(args.db, args.decision_id)
    else:
        decision = _load_latest_by_symbol(args.db, args.symbol)

    if not decision:
        print("Decision not found", file=sys.stderr)
        return 2

    print(_format_report(decision))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
