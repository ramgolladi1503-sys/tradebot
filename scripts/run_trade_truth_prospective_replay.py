#!/usr/bin/env python3
"""Run Trade Truth Prospective Replay against recorded input bundles."""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.trade_truth.prospective_capture_engine import (
    CALL_COUNTS,
    arm_broker_write_guards,
    sha256_file,
)
from core.trade_truth.prospective_replay_engine import (
    compare_replay_against_expected,
    run_prospective_causal_replay,
)
from core.trade_truth.raw_tick_causal_replay import RawTickSessionStore
from core.trade_truth.real_option_provider import RealOptionQuoteProvider


def run_prospective_replay_campaign(
    captures_file: Path,
    raw_tick_source: Path,
) -> dict:
    arm_broker_write_guards()
    captures = json.loads(captures_file.read_text())
    raw_store = RawTickSessionStore(raw_tick_source, session_date="2026-09-10")
    option_provider = RealOptionQuoteProvider(raw_tick_source)

    results = []
    all_parity = True

    for cap in captures:
        trace_id = cap["trace_id"]
        # 1. Strict causal input bundle
        input_bundle = {
            "trace_id": trace_id,
            "session_id": cap["session_id"],
            "session_date": cap["session_date"],
            "decision_ts_epoch": cap["decision_ts_epoch"],
            "decision_ts_str": cap["decision_ts_str"],
            "raw_market_events_source": {
                "source_path": str(raw_tick_source),
                "source_sha256": sha256_file(raw_tick_source),
            },
            "instrument_master_source": {
                "master_path": str(raw_tick_source),
                "master_sha256": sha256_file(raw_tick_source),
            },
            "code_lineage": {
                "git_sha": cap["code_lineage"]["git_sha"],
                "config_hash": cap["code_lineage"]["config_hash"],
                "strategy_catalog_hash": cap["code_lineage"]["strategy_catalog_hash"],
            },
            "historical_risk_state_snapshot": cap["risk_state_evaluation"]["risk_input_snapshot"],
        }

        # 2. Run causal replay with ZERO access to expected output
        actual = run_prospective_causal_replay(
            input_bundle,
            session_store=raw_store,
            option_provider=option_provider,
        )

        # 3. Expected truth (physically isolated comparison)
        expected_output = {
            "trace_id": trace_id,
            "stage_hashes": cap["stage_hashes"],
            "final_decision": cap["final_decision"],
            "record_hash": cap["truth_record"]["record_hash"],
        }

        comp = compare_replay_against_expected(actual, expected_output)
        results.append(comp)
        if not comp["parity"]:
            all_parity = False

    broker_calls = sum(CALL_COUNTS.values())
    summary = {
        "all_replay_parity": all_parity,
        "traces_replayed": len(results),
        "traces_diverged": sum(1 for r in results if not r["parity"]),
        "broker_write_calls": broker_calls,
        "results": results,
    }

    out_path = REPO_ROOT / "TRADE_TRUTH_PROSPECTIVE_REPLAY_RESULTS.json"
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"Replay completed. Parity: {all_parity}. Divergences: {summary['traces_diverged']}")
    return summary

if __name__ == "__main__":
    captures_p = REPO_ROOT / "TRADE_TRUTH_PROSPECTIVE_FULL_CAPTURES.json"
    raw_p = Path("/Volumes/TradeBotData/live market capture/2026-09-10/upstox_full_ticks_20260910_stitched.parquet")
    res = run_prospective_replay_campaign(captures_p, raw_p)
    print(res)
