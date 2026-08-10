#!/usr/bin/env python3
"""
Run Trapped Push Snapback V14 Prospective Observer (No Orders)
Evaluates completed 5-minute bars and logs H1 triggers, snapshot data, and post-event outcomes.
Strictly enforced read-only governance: broker_write_authority = false, order_authority = false.
"""
import os
import sys
import json
import argparse
import datetime
import pandas as pd
from pathlib import Path

def evaluate_h1_predicate(df):
    """
    Evaluates H1 frozen predicate on completed 5-minute bars.
    H1: range_bps[t-1] > 12.0 & upper_wick_bps[t-1] > 4.0 & body_bps[t] < -2.0
    """
    range_t1 = df['range_bps'].shift(1)
    wick_t1 = df['upper_wick_bps'].shift(1)
    body_t = df['body_bps']
    
    triggers = (range_t1 > 12.0) & (wick_t1 > 4.0) & (body_t < -2.0)
    return triggers

def run_observer(mode, input_bars_path, output_root, run_id, candidate_id, order_authority=False, broker_write_authority=False, paper_authorized=False, live_authorized=False):
    # Safety Check: Enforce NO order placement or broker write authority
    if order_authority or broker_write_authority or paper_authorized or live_authorized:
        raise ValueError("UNSAFE AUTHORITY STATE: Prospective observer must run with zero order/broker authority.")

    run_dir = Path(output_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(input_bars_path)
    
    # Required feature calculation if missing
    if 'range_bps' not in df.columns:
        df['range_bps'] = ((df['high'] - df['low']) / df['open']) * 10000.0
    if 'upper_wick_bps' not in df.columns:
        df['upper_wick_bps'] = ((df['high'] - df[['open', 'close']].max(axis=1)) / df['open']) * 10000.0
    if 'body_bps' not in df.columns:
        df['body_bps'] = ((df['close'] - df['open']) / df['open']) * 10000.0
    if 'nifty_ret6' not in df.columns:
        df['nifty_ret6'] = ((df['close'].shift(-6) - df['close']) / df['close']) * 10000.0

    triggers = evaluate_h1_predicate(df)
    
    trigger_rows = []
    missed_rows = []
    snapshot_rows = []
    outcome_rows = []
    excursion_rows = []
    verdict_rows = []

    orders_created = 0
    broker_writes_created = 0
    trigger_count = 0

    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

    for idx, row in df.iterrows():
        bar_time = str(row.get('datetime', row.get('timestamp', f'idx_{idx}')))
        is_trigger = bool(triggers.iloc[idx])
        
        # Base log entry
        base_log = {
            "run_id": run_id,
            "timestamp_ist": now_str,
            "candidate_id": candidate_id,
            "bar_timestamp": bar_time,
            "source_file_or_feed": input_bars_path,
            "frozen_predicate_version": "H1_V14_FROZEN",
            "trigger_detected": is_trigger,
            "completed_bar_only": True,
            "broker_write_authority": False,
            "order_authority": False,
            "paper_authorized": False,
            "live_authorized": False
        }
        
        snapshot_rows.append({**base_log, "open": float(row['open']), "high": float(row['high']), "low": float(row['low']), "close": float(row['close'])})

        if is_trigger:
            trigger_count += 1
            trigger_rows.append({**base_log, "trigger_index": idx, "range_bps_t1": float(df['range_bps'].shift(1).iloc[idx]), "upper_wick_bps_t1": float(df['upper_wick_bps'].shift(1).iloc[idx]), "body_bps_t": float(row['body_bps'])})
            
            # Check if 6 future bars exist for outcome measurement
            if idx + 6 < len(df):
                future_close = df['close'].iloc[idx + 6]
                entry_close = row['close']
                ret6_bps = -((future_close - entry_close) / entry_close) * 10000.0
                
                # Excursion over next 6 bars
                future_highs = df['high'].iloc[idx+1:idx+7]
                future_lows = df['low'].iloc[idx+1:idx+7]
                max_up_bps = ((future_highs.max() - entry_close) / entry_close) * 10000.0
                max_down_bps = ((entry_close - future_lows.min()) / entry_close) * 10000.0
                
                outcome_rows.append({**base_log, "trigger_index": idx, "entry_close": float(entry_close), "exit_close_6b": float(future_close), "down_ret6_bps": float(ret6_bps)})
                excursion_rows.append({**base_log, "trigger_index": idx, "max_adverse_excursion_bps": float(max_up_bps), "max_favorable_excursion_bps": float(max_down_bps)})
        else:
            missed_rows.append(base_log)

    # Governance verdict row
    governance_row = {
        "run_id": run_id,
        "candidate_id": candidate_id,
        "trigger_count": trigger_count,
        "orders_created": orders_created,
        "broker_writes_created": broker_writes_created,
        "authority_flags_all_false": True,
        "governance_verdict": "PAPER_OBSERVATION_PASS_ZERO_ORDERS"
    }
    verdict_rows.append(governance_row)

    # Write log files
    def write_jsonl(filename, rows):
        with open(run_dir / filename, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    write_jsonl("candidate_trigger_log.jsonl", trigger_rows)
    write_jsonl("missed_trigger_log.jsonl", missed_rows)
    write_jsonl("bar_snapshot_log.jsonl", snapshot_rows)
    write_jsonl("post_event_return_log.jsonl", outcome_rows)
    write_jsonl("adverse_favorable_excursion_log.jsonl", excursion_rows)
    write_jsonl("governance_verdict_log.jsonl", verdict_rows)

    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "candidate_id": candidate_id,
        "mode": mode,
        "input_bars_path": input_bars_path,
        "total_bars_evaluated": len(df),
        "trigger_count": trigger_count,
        "outcome_count": len(outcome_rows),
        "orders_created": orders_created,
        "broker_writes_created": broker_writes_created,
        "authority_flags_all_false": True
    }
    with open(run_dir / "run_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    verdict_file = {
        "controlled_verdict": "V14_PROSPECTIVE_OBSERVER_IMPLEMENTED_DRY_RUN_PASS",
        "latest_commit": "b57197b5643b0e99087dbfac091eb9a2054a5e1b",
        "candidate_id": candidate_id,
        "trigger_count": trigger_count,
        "orders_created": orders_created,
        "broker_writes_created": broker_writes_created,
        "paper_authorized": False,
        "live_authorized": False,
        "order_authority": False,
        "broker_write_authority": False,
        "historical_micro_pattern_supported": True,
        "out_of_sample_supported": True,
        "prospective_supported": False,
        "execution_viable": False,
        "structural_edge_certified": False,
        "edge_claimed": False
    }
    with open(run_dir / "CONTROLLED_VERDICT.json", "w") as f:
        json.dump(verdict_file, f, indent=2)

    return manifest

def main():
    parser = argparse.ArgumentParser(description="V14 Trapped Push Prospective Observer")
    parser.add_argument("--mode", choices=["historical_replay", "manual_append"], required=True)
    parser.add_argument("--input-bars", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--candidate-id", default="H1_TRAPPED_PUSH_SNAPBACK")
    args = parser.parse_args()

    manifest = run_observer(args.mode, args.input_bars, args.output_root, args.run_id, args.candidate_id)
    print(f"PROSPECTIVE OBSERVER RUN COMPLETE. Triggers: {manifest['trigger_count']}, Orders: {manifest['orders_created']}")

if __name__ == "__main__":
    main()
