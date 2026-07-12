#!/usr/bin/env python3
import json
import argparse
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import time
from pathlib import Path
from pprint import pprint

from core.market_snapshot_builder import build_market_snapshot_from_raw_tick
from core.runtime_snapshot_producer import _strategy_context_from_market_symbol
from core.ranking_orchestrator import build_ranked_opportunity_report
from strategies.movement.vwap_reclaim import generate_vwap_reclaim_rejection_candidates

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="Path to index_ticks.jsonl")
    parser.add_argument("--event-id", help="Event ID to trace")
    parser.add_argument("--row-index", type=int, help="Fallback to trace by row index if no event id")
    parser.add_argument("--strategy-id", default="vwap_reclaim_rejection_v1", help="Strategy to run")
    parser.add_argument("--output", required=True, help="Path to write the evidence")
    args = parser.parse_args()

    # 1. Read one raw recorded event
    raw_event = None
    with open(args.source, "r") as f:
        for idx, line in enumerate(f):
            if not line.strip():
                continue
            payload = json.loads(line)
            if args.event_id and str(payload.get("event_id")) == str(args.event_id):
                raw_event = payload
                break
            if args.row_index is not None and idx == args.row_index:
                raw_event = payload
                break

    if not raw_event:
        print(f"Error: Event not found in {args.source}")
        sys.exit(1)

    replay_event_id = raw_event.get("event_id") or raw_event.get("local_ts") or args.row_index

    trace = {
        "replay_event_id": replay_event_id,
        "instrument": "NIFTY",
        "strategy": args.strategy_id,
    }

    # 2. Normalize
    try:
        normalized_snapshot = build_market_snapshot_from_raw_tick(raw_event)
        trace["normalized_snapshot"] = "SUCCESS"
    except Exception as e:
        trace["normalized_snapshot"] = f"FAILED: {e}"
        print(f"Normalization blocked: {e}")
        _persist_trace(args.output, trace)
        sys.exit(1)

    # 3. StrategyContext Construction
    try:
        ctx = _strategy_context_from_market_symbol("NIFTY", normalized_snapshot)
        trace["strategy_context"] = "SUCCESS"
    except Exception as e:
        trace["strategy_context"] = f"FAILED: {e}"
        print(f"StrategyContext blocked: {e}")
        _persist_trace(args.output, trace)
        sys.exit(1)

    # 4. Strategy & 5. Ranking
    # Disable execution and baseline logic
    try:
        strategy_generators = [generate_vwap_reclaim_rejection_candidates]
        now_epoch = float(raw_event.get("local_ts") or time.time())
        report = build_ranked_opportunity_report(
            ctx=ctx,
            regime=None,
            candidate_generators=strategy_generators,
            include_no_trade_candidate=False,
            include_strategy_id_in_normalization_key=True
        )

        candidates = getattr(report, "ranked_candidates", [])
        if not candidates:
            trace["decision"] = "EXPLICIT_REJECTION"
            trace["ranking_status"] = "N/A"
            trace["reason"] = "No candidate produced by strategy"
        else:
            top = candidates[0]
            trace["decision"] = "CANDIDATE"
            trace["ranking_status"] = "SUPPRESSED" if getattr(top, "suppressed", False) else "PROMOTED"
            trace["reason"] = getattr(top, "suppress_reason", "") if getattr(top, "suppressed", False) else "Valid candidate"

        trace["read_only"] = True
    except Exception as e:
        trace["decision"] = "FAILED"
        trace["reason"] = str(e)
        print(f"Ranking blocked: {e}")
        _persist_trace(args.output, trace)
        sys.exit(1)

    # 6. Persist Trace
    _persist_trace(args.output, trace)
    print("Replay Vertical Slice Successful.")
    sys.exit(0)

def _persist_trace(output_path: str, trace: dict):
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as f:
        f.write(json.dumps(trace) + "\n")

if __name__ == "__main__":
    main()
