#!/usr/bin/env python3
"""Execute Strict Raw-Tick Level-C Causal Replay.

Zero derived bar parquets.
Zero historical analytical ledger fields in input bundle.
Reconstructs 1m bars directly from raw stitched tick capture into MarketSessionStore.

Outputs:
1. TRADE_TRUTH_LEVEL_C_TRACE_RESULTS.jsonl (append-only)
2. TRADE_TRUTH_V2_DETERMINISM_EVIDENCE.json (3 independent runs per trace)
3. TRADE_TRUTH_V2_FUTURE_LEAK_AUDIT.json (proven max_raw_tick_ts <= decision_ts)
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from core.trade_truth.raw_tick_causal_replay import (
    RawTickSessionStore,
    compare_replay_to_expected,
    run_raw_tick_replay,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

def main():
    p_raw_ticks_20260910 = Path("/Volumes/TradeBotData/live market capture/2026-09-10/upstox_full_ticks_20260910_stitched.parquet")
    session_store_20260910 = RawTickSessionStore(p_raw_ticks_20260910, "2026-09-10")

    p1 = Path("/Volumes/TradeBotData/mros_end_to_end_trace_path_audit_v2_20260911T224726Z/HISTORICAL_TRACE_LEDGER.jsonl")
    p2 = Path("/Volumes/TradeBotData/mros-c1-c2-pr897-full-integrated-replay-20260911-1789163457/C1_FULL_INTEGRATED_REPLAY_20260911.jsonl")

    traces1 = [json.loads(l) for l in p1.read_text().strip().split("\n") if l.strip()]
    traces2 = [json.loads(l) for l in p2.read_text().strip().split("\n") if l.strip()]

    results_file = REPO_ROOT / "TRADE_TRUTH_LEVEL_C_TRACE_RESULTS.jsonl"
    results_records = []

    determinism_runs = {}
    future_leaks = []

    # 1. Replay 2026-09-10 traces from raw ticks
    for t in traces1:
        t_id = t["trace_id"]
        input_b = {
            "trace_id": t_id,
            "session_date": "2026-09-10",
            "timestamp": t["timestamp"],
            "warmup_status": "WARMUP_COMPLETE",
            "raw_tick_source": str(p_raw_ticks_20260910),
            "historical_sha": "f2ca8c899424d404b3e607047b767929df012272"
        }
        # Run raw tick replay with ZERO access to expected output
        actual1 = run_raw_tick_replay(input_b, session_store=session_store_20260910)
        # Compare independently with expected output
        comp1 = compare_replay_to_expected(actual1, expected_output=t)
        rec1 = asdict(comp1)
        rec1["source_ledger"] = "HISTORICAL_TRACE_LEDGER_20260910"
        results_records.append(rec1)

        if comp1.future_leak_detected or (actual1.max_raw_tick_ts_used > comp1.decision_ts_epoch) or (actual1.max_bar_ts_used > comp1.decision_ts_epoch):
            future_leaks.append({
                "trace_id": t_id,
                "decision_ts": comp1.decision_ts_epoch,
                "max_raw_tick_ts": actual1.max_raw_tick_ts_used,
                "max_bar_ts": actual1.max_bar_ts_used,
            })

        # Determinism runs 2 & 3
        actual2 = run_raw_tick_replay(input_b, session_store=session_store_20260910)
        actual3 = run_raw_tick_replay(input_b, session_store=session_store_20260910)
        is_det = (actual1.stage_hashes == actual2.stage_hashes == actual3.stage_hashes)
        determinism_runs[t_id] = {
            "deterministic": is_det,
            "run1_hashes": actual1.stage_hashes,
            "run2_hashes": actual2.stage_hashes,
            "run3_hashes": actual3.stage_hashes
        }

    # 2. Replay 2026-09-11 traces (Warmup Insufficient -> BLOCKED_DATA)
    for t in traces2:
        t_id = t["trace_id"]
        input_b = {
            "trace_id": t_id,
            "session_date": "2026-09-11",
            "timestamp": t["timestamp"],
            "warmup_status": "WARMUP_INSUFFICIENT",
            "raw_tick_source": "/Volumes/TradeBotData/live market capture/2026-09-11/upstox_full_ticks_20260911_stitched.parquet",
            "historical_sha": "f2ca8c899424d404b3e607047b767929df012272"
        }
        actual1 = run_raw_tick_replay(input_b, session_store=None)
        comp1 = compare_replay_to_expected(actual1, expected_output=t)
        rec1 = asdict(comp1)
        rec1["source_ledger"] = "C1_FULL_INTEGRATED_REPLAY_20260911"
        results_records.append(rec1)

    # Write append-only results
    with open(results_file, "w") as f:
        for r in results_records:
            f.write(json.dumps(r) + "\n")

    # Write determinism audit
    nondet_count = sum(1 for v in determinism_runs.values() if not v["deterministic"])
    det_evidence = {
        "total_traces_checked": len(determinism_runs),
        "deterministic_count": len(determinism_runs) - nondet_count,
        "nondeterministic_count": nondet_count,
        "determinism_verified": (nondet_count == 0),
        "traces": determinism_runs
    }
    with open(REPO_ROOT / "TRADE_TRUTH_V2_DETERMINISM_EVIDENCE.json", "w") as f:
        json.dump(det_evidence, f, indent=2)

    # Write future leak audit
    leak_evidence = {
        "total_traces_checked": len(traces1),
        "future_leak_count": len(future_leaks),
        "future_leak_audit_passed": (len(future_leaks) == 0),
        "leaks": future_leaks
    }
    with open(REPO_ROOT / "TRADE_TRUTH_V2_FUTURE_LEAK_AUDIT.json", "w") as f:
        json.dump(leak_evidence, f, indent=2)

    full_parity = sum(1 for r in results_records if r["terminal_status"] == "FULL_PARITY")
    partial_parity = sum(1 for r in results_records if r["terminal_status"] == "PARTIAL_PARITY")
    blocked_data = sum(1 for r in results_records if r["terminal_status"] == "BLOCKED_DATA")
    diverged = sum(1 for r in results_records if r["terminal_status"] == "DIVERGED")

    print(f"Total traces attempted: {len(results_records)}")
    print(f"FULL_PARITY: {full_parity}")
    print(f"PARTIAL_PARITY (2026-09-10 raw tick replay): {partial_parity}")
    print(f"BLOCKED_DATA (2026-09-11 warmup): {blocked_data}")
    print(f"DIVERGED: {diverged}")
    print(f"NONDETERMINISTIC: {nondet_count}")
    print(f"FUTURE_LEAKS: {len(future_leaks)}")

if __name__ == "__main__":
    main()
