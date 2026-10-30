#!/usr/bin/env python3
"""Run Sentinel Daily Forensic Decision Journal & Post-Market Digest.

Compiles end-of-day summary, finalizes pending shadow barriers at close,
and produces authoritative DailyForensicSummary.

Usage:
    python scripts/run_daily_forensic_journal.py [--date YYYY-MM-DD] [--journal-dir logs]

Preserves trading safety invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import datetime, date
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.sentinel_realtime_journal import (
    DailyForensicSummary,
    SentinelRealtimeJournal,
    ShadowBarrierOutcomeRecord,
    VetoRecord,
    TradeExecutionRecord,
    TradeExitAttributionRecord,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DailyForensicJournal")


def compile_daily_forensic_digest(session_date_str: str, logs_dir: Path) -> DailyForensicSummary:
    """Reads journal records from logs/sentinel_decision_journal_YYYYMMDD.jsonl
    and compiles the authoritative DailyForensicSummary.
    """
    date_clean = session_date_str.replace("-", "")
    journal_file = logs_dir / f"sentinel_decision_journal_{date_clean}.jsonl"

    journal = SentinelRealtimeJournal(logs_dir=logs_dir, enable_writer_thread=False)

    vetoes: list[VetoRecord] = []
    executions: list[TradeExecutionRecord] = []
    exits: list[TradeExitAttributionRecord] = []
    shadow_records: list[ShadowBarrierOutcomeRecord] = []

    if journal_file.exists():
        logger.info(f"Loading existing journal records from {journal_file}...")
        with open(journal_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    rtype = data.get("record_type")
                    if rtype == "VETO":
                        vr = VetoRecord(**{k: v for k, v in data.items() if k in VetoRecord.__slots__})
                        vetoes.append(vr)
                        journal.veto_history.append(vr)
                        # Also register with evaluator
                        journal.evaluator.register_veto(vr)
                    elif rtype == "EXECUTION":
                        er = TradeExecutionRecord(**{k: v for k, v in data.items() if k in TradeExecutionRecord.__slots__})
                        executions.append(er)
                        journal.execution_history.append(er)
                    elif rtype == "EXIT":
                        xr = TradeExitAttributionRecord(**{k: v for k, v in data.items() if k in TradeExitAttributionRecord.__slots__})
                        exits.append(xr)
                        journal.exit_history.append(xr)
                    elif rtype == "SHADOW_OUTCOME":
                        sr = ShadowBarrierOutcomeRecord(**{k: v for k, v in data.items() if k in ShadowBarrierOutcomeRecord.__slots__})
                        shadow_records.append(sr)
                except Exception as e:
                    logger.warning(f"Error parsing line from journal: {e}")

    # Generate daily summary
    summary = journal.generate_daily_summary(session_date_str=session_date_str)

    # Persist summary directly to journal file as append-only record
    with open(journal_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(summary), default=str) + "\n")

    # Also save dedicated digest JSON
    digest_path = logs_dir / f"sentinel_daily_forensic_digest_{date_clean}.json"
    with open(digest_path, "w", encoding="utf-8") as f:
        json.dump(asdict(summary), f, indent=2, default=str)

    logger.info(f"Daily forensic digest written to {digest_path}")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Sentinel Daily Forensic Journal Compiler")
    parser.add_argument("--date", type=str, default=datetime.now().strftime("%Y-%m-%d"), help="Session date (YYYY-MM-DD)")
    parser.add_argument("--journal-dir", type=str, default="logs", help="Directory containing decision journal jsonl files")
    args = parser.parse_args()

    logs_dir = Path(args.journal_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    summary = compile_daily_forensic_digest(args.date, logs_dir)

    print("\n" + "=" * 70)
    print(f"🏛️ SENTINEL POST-MARKET FORENSIC DECISION DIGEST — {summary.session_date}")
    print("=" * 70)
    print(f"Total Vetoes:                    {summary.total_vetoes}")
    for reason, count in summary.vetoes_by_reason.items():
        print(f"   • {reason:30s}: {count}")
    print(f"Total Executions:                {summary.total_executions}")
    print(f"Total Exits:                     {summary.total_exits} (Win Rate: {summary.win_rate_executed_pct:.1f}%)")
    print(f"Realized Executed PnL:           ₹{summary.executed_total_pnl_inr:,.2f}")
    print("-" * 70)
    print("🛡️ SHADOW BARRIER COUNTERFACTUAL VERIFICATION:")
    print(f"Resolved Barriers:               {summary.resolved_shadow_barriers}")
    print(f"   • True Positive (Capital Saved): {summary.true_positive_capital_saved_count} (Avoided Loss: ₹{summary.capital_saved_inr:,.2f})")
    print(f"   • False Positive (Missed Alpha): {summary.false_positive_missed_alpha_count} (Missed Profit: ₹{summary.missed_alpha_inr:,.2f})")
    print(f"   • Neutral Chop:                  {summary.neutral_chop_count}")
    print(f"NET VETO DEFENSE BENEFIT:        ₹{summary.net_veto_defense_benefit_inr:,.2f}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
