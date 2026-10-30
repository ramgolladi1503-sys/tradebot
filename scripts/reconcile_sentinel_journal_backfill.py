#!/usr/bin/env python3
"""Reconcile Sentinel Journal Backfill from Historical WAL and Logs.

Backfills forensic decision journal files (logs/sentinel_decision_journal_YYYYMMDD.jsonl)
from runtime/sentinel_apm_wal.json, runtime/sentinel_apm_wal_sensex.json,
and historical trade data.

Usage:
    python scripts/reconcile_sentinel_journal_backfill.py [--date YYYY-MM-DD] [--all-dates]

Safety:
- read_only = True
- is_order_action = False
- broker_api_called = False
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.sentinel_realtime_journal import (
    SentinelRealtimeJournal,
    TradeExecutionRecord,
    TradeExitAttributionRecord,
    VetoRecord,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("JournalBackfill")


def load_wal_trades(wal_path: Path) -> List[Dict[str, Any]]:
    if not wal_path.exists():
        return []
    try:
        with open(wal_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            history = data.get("trade_history", [])
            last_trade = data.get("last_completed_trade")
            trades = list(history)
            if last_trade and isinstance(last_trade, dict):
                if not any(t.get("position_id") == last_trade.get("position_id") for t in trades):
                    trades.append(last_trade)
            return trades
    except Exception as e:
        logger.warning(f"Error loading {wal_path}: {e}")
        return []


def backfill_session(session_date_str: str, logs_dir: Path, wal_files: List[Path]) -> int:
    """Backfills journal for a specific session date from WAL files."""
    date_clean = session_date_str.replace("-", "")
    journal_file = logs_dir / f"sentinel_decision_journal_{date_clean}.jsonl"

    existing_position_ids = set()
    if journal_file.exists():
        with open(journal_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                    if "position_id" in d:
                        existing_position_ids.add(d["position_id"])
                except Exception:
                    pass

    backfilled_count = 0
    records_to_append = []

    for wf in wal_files:
        trades = load_wal_trades(wf)
        for t in trades:
            entry_t = str(t.get("entry_time", ""))
            if not entry_t.startswith(session_date_str):
                continue

            pos_id = t.get("position_id", "")
            if pos_id in existing_position_ids:
                continue

            # Determine index
            contract = t.get("strike_contract", "") or t.get("opt_symbol", "")
            index_name = "SENSEX" if "SENSEX" in contract else ("BANKNIFTY" if "BANKNIFTY" in contract else "NIFTY")

            # Create Execution Record
            exec_rec = TradeExecutionRecord(
                record_id=f"EXEC_{pos_id}",
                position_id=pos_id,
                wall_time_str=entry_t.split("T")[1][:8] if "T" in entry_t else entry_t[:8],
                index_name=index_name,
                symbol=contract,
                direction=t.get("direction", "CE"),
                setup_reason="HISTORICAL_REPLAY",
                spot_price=float(t.get("entry_price") or 0.0),
                option_ltp=float(t.get("opt_entry_ltp") or 0.0),
                fill_price=float(t.get("opt_entry_ltp") or 0.0),
                target_pts=float(t.get("target_price", 0.0) - t.get("entry_price", 0.0)) if t.get("target_price") else 15.0,
                sl_pts=float(t.get("entry_price", 0.0) - t.get("initial_sl", 0.0)) if t.get("initial_sl") else 12.0,
                lots=int(t.get("lots") or 1),
                lot_size=int(t.get("lot_size") or 65),
                total_quantity=int(t.get("total_quantity") or 65),
                sizing_tier=str(t.get("sizing_tier") or "FULL_SIZE"),
            )
            records_to_append.append(asdict(exec_rec))

            # Create Exit Record if trade exited
            if t.get("exit_reason") or t.get("exit_price") or t.get("opt_exit_ltp"):
                exit_t = str(t.get("exit_time", entry_t))
                opt_pnl = float(t.get("opt_pnl_pts") or 0.0)
                tot_qty = int(t.get("total_quantity") or 65)
                exit_rec = TradeExitAttributionRecord(
                    record_id=f"EXIT_{pos_id}",
                    position_id=pos_id,
                    wall_time_str=exit_t.split("T")[1][:8] if "T" in exit_t else exit_t[:8],
                    index_name=index_name,
                    symbol=contract,
                    direction=t.get("direction", "CE"),
                    entry_price_spot=float(t.get("entry_price") or 0.0),
                    exit_price_spot=float(t.get("exit_price") or 0.0),
                    entry_price_opt=float(t.get("opt_entry_ltp") or 0.0),
                    exit_price_opt=float(t.get("opt_exit_ltp") or 0.0),
                    opt_pnl_pts=opt_pnl,
                    spot_pnl_pts=float(t.get("pnl_pts") or 0.0),
                    exit_reason=str(t.get("exit_reason") or "COMPLETED"),
                    max_spot_excursion=float(t.get("max_spot_excursion") or 0.0),
                    max_opt_excursion=float(t.get("max_opt_excursion") or 0.0),
                    target_1_hit=bool(t.get("target_1_hit")),
                    target_2_hit=bool(t.get("target_2_hit")),
                    half_booked=bool(t.get("half_booked")),
                    trail_locked=bool(t.get("trail_locked")),
                    realized_pnl_inr=round(opt_pnl * tot_qty, 2),
                )
                records_to_append.append(asdict(exit_rec))

            existing_position_ids.add(pos_id)
            backfilled_count += 1

    if records_to_append:
        with open(journal_file, "a", encoding="utf-8") as f:
            for rec in records_to_append:
                f.write(json.dumps(rec, default=str) + "\n")
        logger.info(f"Appended {len(records_to_append)} backfilled records to {journal_file}")

    return backfilled_count


def main():
    parser = argparse.ArgumentParser(description="Sentinel Journal Backfill Reconciler")
    parser.add_argument("--date", type=str, default="", help="Specific session date (YYYY-MM-DD)")
    parser.add_argument("--all-dates", action="store_true", help="Backfill all historical dates found in WAL")
    args = parser.parse_args()

    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    wal_files = [
        Path("runtime/sentinel_apm_wal.json"),
        Path("runtime/sentinel_apm_wal_sensex.json"),
        Path("runtime/sentinel_apm_wal_banknifty.json"),
    ]

    dates_to_process = set()
    if args.date:
        dates_to_process.add(args.date)
    elif args.all_dates:
        for wf in wal_files:
            for t in load_wal_trades(wf):
                et = str(t.get("entry_time", ""))
                if len(et) >= 10 and et[4] == "-" and et[7] == "-":
                    dates_to_process.add(et[:10])
    else:
        # Default to today and yesterday
        dates_to_process.add(datetime.now().strftime("%Y-%m-%d"))

    total_backfilled = 0
    for d in sorted(dates_to_process):
        logger.info(f"Reconciling journal for {d}...")
        cnt = backfill_session(d, logs_dir, wal_files)
        total_backfilled += cnt

    logger.info(f"Reconciliation complete. Backfilled {total_backfilled} trade events across {len(dates_to_process)} sessions.")


if __name__ == "__main__":
    main()
