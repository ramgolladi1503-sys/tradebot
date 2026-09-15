#!/usr/bin/env python3
"""Run Trade Truth Prospective Observer with Real Production State."""

import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.trade_truth.prospective_capture_engine import (
    CALL_COUNTS,
    ProspectiveCaptureEngine,
    arm_broker_write_guards,
    get_current_git_lineage,
)
from core.trade_truth.raw_tick_causal_replay import RawTickSessionStore
from core.trade_truth.real_option_provider import RealOptionQuoteProvider
from core.trade_truth.risk_state_provider import ReadOnlyRiskStateProvider


def run_observer_session(
    raw_tick_source: Path,
    session_id: str = "session_20260910_prospective_dryrun",
    session_date: str = "2026-09-10",
    timestamps: list[tuple[str, float, str]] = None,
) -> dict:
    arm_broker_write_guards()
    raw_store = RawTickSessionStore(raw_tick_source, session_date=session_date)
    option_provider = RealOptionQuoteProvider(raw_tick_source)
    risk_provider = ReadOnlyRiskStateProvider(mode="OFFLINE_DRY_RUN")

    engine = ProspectiveCaptureEngine(
        raw_tick_store=raw_store,
        session_id=session_id,
        session_date=session_date,
        option_provider=option_provider,
        risk_provider=risk_provider,
    )

    if timestamps is None:
        timestamps = [
            ("trace_p01", 1789098720.0, "2026-09-10 09:22:00"),
            ("trace_p02", 1789098780.0, "2026-09-10 09:23:00"),
            ("trace_p03", 1789098840.0, "2026-09-10 09:24:00"),
            ("trace_p04", 1789098900.0, "2026-09-10 09:25:00"),
            ("trace_p05", 1789098960.0, "2026-09-10 09:26:00"),
        ]

    portfolio_override = {
        "capital": 1000000.0,
        "equity_high": 1000000.0,
        "daily_pnl": 0.0,
        "open_risk_pct": 0.0,
        "trades_today": 0,
        "kill_switch_active": False,
    }

    captured_traces = []
    trace_ledger_entries = []

    for trace_id, ts_epoch, ts_str in timestamps:
        rec = engine.capture_decision_cycle(
            trace_id=trace_id,
            decision_ts_epoch=ts_epoch,
            decision_ts_str=ts_str,
            portfolio_override=portfolio_override,
        )
        captured_traces.append(rec)

        ledger_entry = {
            "trace_id": trace_id,
            "session_id": session_id,
            "decision_ts_epoch": ts_epoch,
            "terminal_trace_status": rec["terminal_trace_status"],
            "stages_captured_count": sum(1 for s in rec["stage_status_map"].values() if s in ("CAPTURED", "NOT_APPLICABLE_WITH_PROOF")),
            "total_stages_required": 14,
            "all_stages_complete": (rec["terminal_trace_status"] == "CAPTURE_COMPLETE"),
            "future_leak_detected": rec["future_leak_audit"]["future_leak_detected"],
            "decision_action": rec["final_decision"]["action"],
            "stage_hashes": rec["stage_hashes"],
            "record_hash": rec["truth_record"]["record_hash"],
        }
        trace_ledger_entries.append(ledger_entry)

    # Save outputs
    ledger_path = REPO_ROOT / "TRADE_TRUTH_PROSPECTIVE_TRACE_LEDGER.jsonl"
    with open(ledger_path, "w") as f:
        for entry in trace_ledger_entries:
            f.write(json.dumps(entry) + chr(10))

    captures_path = REPO_ROOT / "TRADE_TRUTH_PROSPECTIVE_FULL_CAPTURES.json"
    captures_path.write_text(json.dumps(captured_traces, indent=2))

    broker_calls = sum(CALL_COUNTS.values())
    print(f"Captured {len(captured_traces)} prospective traces with real production state. Broker calls: {broker_calls}")
    return {
        "traces_count": len(captured_traces),
        "broker_calls": broker_calls,
        "ledger_file": str(ledger_path),
        "captures_file": str(captures_path),
    }

if __name__ == "__main__":
    raw_p = Path("/Volumes/TradeBotData/live market capture/2026-09-10/upstox_full_ticks_20260910_stitched.parquet")
    res = run_observer_session(raw_p)
    print(res)
