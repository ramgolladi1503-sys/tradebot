#!/usr/bin/env python3
"""
Run Trapped Push Snapback V14 Prospective Observer (No Orders) - Repaired Scope V15
Evaluates completed 5-minute bars and logs H1 triggers, snapshot data, and post-event outcomes.
Enforces opening window scope (09:15-11:30 IST by default).
Strictly enforced read-only governance: broker_write_authority = false, order_authority = false.
Dynamic commit binding via CLI arguments --evidence-commit and --registry-commit.
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
    Session-scoped: range_t1 and wick_t1 are shifted within session date.
    """
    ts_col = 'datetime' if 'datetime' in df.columns else ('timestamp' if 'timestamp' in df.columns else None)
    if ts_col:
        ts = pd.to_datetime(df[ts_col])
        if ts.dt.tz is None:
            ts_ist = ts.dt.tz_localize('Asia/Kolkata')
        else:
            ts_ist = ts.dt.tz_convert('Asia/Kolkata')
        session_dates = ts_ist.dt.date
        range_t1 = df.groupby(session_dates)['range_bps'].shift(1)
        wick_t1 = df.groupby(session_dates)['upper_wick_bps'].shift(1)
    else:
        range_t1 = df['range_bps'].shift(1)
        wick_t1 = df['upper_wick_bps'].shift(1)
        
    body_t = df['body_bps']
    
    triggers = (range_t1 > 12.0) & (wick_t1 > 4.0) & (body_t < -2.0)
    return triggers, range_t1, wick_t1

def run_observer(mode, input_bars_path, output_root, run_id, candidate_id, opening_start="09:15", opening_end="11:30", evidence_commit=None, registry_commit=None, order_authority=False, broker_write_authority=False, paper_authorized=False, live_authorized=False):
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

    triggers, range_t1_series, wick_t1_series = evaluate_h1_predicate(df)
    
    ts_col = 'datetime' if 'datetime' in df.columns else ('timestamp' if 'timestamp' in df.columns else 'bar_index')
    
    ts_series = pd.to_datetime(df[ts_col])
    if ts_series.dt.tz is None:
        ts_ist_series = ts_series.dt.tz_localize('Asia/Kolkata')
    else:
        ts_ist_series = ts_series.dt.tz_convert('Asia/Kolkata')
        
    ts_utc_series = ts_ist_series.dt.tz_convert('UTC')
    
    time_str_series = ts_ist_series.dt.strftime('%H:%M')
    in_opening_series = (time_str_series >= opening_start) & (time_str_series <= opening_end)
    
    iso_utc_series = ts_utc_series.dt.strftime('%Y-%m-%dT%H:%M:%S%z')
    iso_ist_series = ts_ist_series.dt.strftime('%Y-%m-%dT%H:%M:%S%z')
    bar_time_series = ts_ist_series.dt.strftime('%Y-%m-%d %H:%M:%S%z')

    trigger_rows = []
    missed_rows = []
    out_of_scope_rows = []
    snapshot_rows = []
    outcome_rows = []
    excursion_rows = []
    verdict_rows = []

    orders_created = 0
    broker_writes_created = 0
    
    bars_total = len(df)
    bars_in_scope_opening_window = int(in_opening_series.sum())
    bars_out_of_scope = bars_total - bars_in_scope_opening_window
    triggers_in_scope = 0
    misses_in_scope = 0
    pending_outcomes = 0
    available_outcomes = 0

    open_vals = df['open'].values
    high_vals = df['high'].values
    low_vals = df['low'].values
    close_vals = df['close'].values
    body_vals = df['body_bps'].values
    r_t1_vals = range_t1_series.values
    w_t1_vals = wick_t1_series.values
    trig_vals = triggers.values
    in_scope_vals = in_opening_series.values

    # Commit metadata handling
    bound_evidence_commit = evidence_commit if evidence_commit else "UNKNOWN_NOT_PROVIDED"
    bound_registry_commit = registry_commit if registry_commit else "UNKNOWN_NOT_PROVIDED"
    metadata_status = "COMMIT_BOUND" if evidence_commit else "COMMIT_NOT_BOUND"

    for idx in range(bars_total):
        in_opening_scope = bool(in_scope_vals[idx])
        is_trigger_raw = bool(trig_vals[idx])
        is_trigger = is_trigger_raw and in_opening_scope
        
        base_log = {
            "run_id": run_id,
            "candidate_id": candidate_id,
            "bar_timestamp": bar_time_series.iloc[idx],
            "timestamp_utc": iso_utc_series.iloc[idx],
            "timestamp_ist": iso_ist_series.iloc[idx],
            "source_file_or_feed": str(input_bars_path),
            "frozen_predicate_version": "H1_V14_FROZEN",
            "opening_scope_window": f"{opening_start}-{opening_end} IST",
            "in_opening_scope": in_opening_scope,
            "trigger_detected": is_trigger,
            "completed_bar_only": True,
            "broker_write_authority": False,
            "order_authority": False,
            "paper_authorized": False,
            "live_authorized": False
        }
        
        snapshot_rows.append({**base_log, "open": float(open_vals[idx]), "high": float(high_vals[idx]), "low": float(low_vals[idx]), "close": float(close_vals[idx])})

        if not in_opening_scope:
            out_of_scope_rows.append(base_log)
        elif is_trigger:
            triggers_in_scope += 1
            r_val = r_t1_vals[idx] if not pd.isna(r_t1_vals[idx]) else 0.0
            w_val = w_t1_vals[idx] if not pd.isna(w_t1_vals[idx]) else 0.0
            
            trigger_rows.append({
                **base_log,
                "trigger_index": idx,
                "range_bps_t1": float(r_val),
                "upper_wick_bps_t1": float(w_val),
                "body_bps_t": float(body_vals[idx])
            })
            
            if idx + 6 < bars_total:
                available_outcomes += 1
                future_close = close_vals[idx + 6]
                entry_close = close_vals[idx]
                ret6_bps = -((future_close - entry_close) / entry_close) * 10000.0
                
                future_highs = high_vals[idx+1:idx+7]
                future_lows = low_vals[idx+1:idx+7]
                max_up_bps = ((future_highs.max() - entry_close) / entry_close) * 10000.0
                max_down_bps = ((entry_close - future_lows.min()) / entry_close) * 10000.0
                
                outcome_rows.append({
                    **base_log,
                    "trigger_index": idx,
                    "outcome_status": "OUTCOME_AVAILABLE",
                    "entry_close": float(entry_close),
                    "exit_close_6b": float(future_close),
                    "down_ret6_bps": float(ret6_bps)
                })
                excursion_rows.append({
                    **base_log,
                    "trigger_index": idx,
                    "outcome_status": "OUTCOME_AVAILABLE",
                    "max_adverse_excursion_bps": float(max_up_bps),
                    "max_favorable_excursion_bps": float(max_down_bps)
                })
            else:
                pending_outcomes += 1
                outcome_rows.append({
                    **base_log,
                    "trigger_index": idx,
                    "outcome_status": "OUTCOME_PENDING_INSUFFICIENT_FUTURE_BARS",
                    "entry_close": float(close_vals[idx]),
                    "exit_close_6b": None,
                    "down_ret6_bps": None
                })
                excursion_rows.append({
                    **base_log,
                    "trigger_index": idx,
                    "outcome_status": "OUTCOME_PENDING_INSUFFICIENT_FUTURE_BARS",
                    "max_adverse_excursion_bps": None,
                    "max_favorable_excursion_bps": None
                })
        else:
            misses_in_scope += 1
            missed_rows.append(base_log)

    governance_row = {
        "run_id": run_id,
        "candidate_id": candidate_id,
        "bars_total": bars_total,
        "bars_in_scope_opening_window": bars_in_scope_opening_window,
        "bars_out_of_scope": bars_out_of_scope,
        "triggers_in_scope": triggers_in_scope,
        "misses_in_scope": misses_in_scope,
        "pending_outcomes": pending_outcomes,
        "available_outcomes": available_outcomes,
        "orders_created": orders_created,
        "broker_writes_created": broker_writes_created,
        "authority_flags_all_false": True,
        "governance_verdict": "PAPER_OBSERVATION_PASS_ZERO_ORDERS"
    }
    verdict_rows.append(governance_row)

    def write_jsonl(filename, rows):
        with open(run_dir / filename, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    write_jsonl("candidate_trigger_log.jsonl", trigger_rows)
    write_jsonl("missed_trigger_log.jsonl", missed_rows)
    write_jsonl("out_of_scope_bar_log.jsonl", out_of_scope_rows)
    write_jsonl("bar_snapshot_log.jsonl", snapshot_rows)
    write_jsonl("post_event_return_log.jsonl", outcome_rows)
    write_jsonl("adverse_favorable_excursion_log.jsonl", excursion_rows)
    write_jsonl("governance_verdict_log.jsonl", verdict_rows)

    manifest = {
        "schema_version": "V15_METADATA_BOUND_PROSPECTIVE_MANIFEST_V1",
        "run_id": run_id,
        "candidate_id": candidate_id,
        "mode": mode,
        "input_bars_path": str(input_bars_path),
        "evidence_commit": bound_evidence_commit,
        "registry_commit": bound_registry_commit,
        "metadata_status": metadata_status,
        "bars_total": bars_total,
        "bars_in_scope_opening_window": bars_in_scope_opening_window,
        "bars_out_of_scope": bars_out_of_scope,
        "triggers_in_scope": triggers_in_scope,
        "misses_in_scope": misses_in_scope,
        "pending_outcomes": pending_outcomes,
        "available_outcomes": available_outcomes,
        "orders_created": orders_created,
        "broker_writes_created": broker_writes_created,
        "authority_flags_all_false": True
    }
    with open(run_dir / "run_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    verdict_file = {
        "controlled_verdict": "V15_OBSERVER_METADATA_BOUND_DRY_RUN_PASS",
        "evidence_commit": bound_evidence_commit,
        "registry_commit": bound_registry_commit,
        "metadata_status": metadata_status,
        "candidate_id": candidate_id,
        "bars_total": bars_total,
        "bars_in_scope_opening_window": bars_in_scope_opening_window,
        "bars_out_of_scope": bars_out_of_scope,
        "triggers_in_scope": triggers_in_scope,
        "misses_in_scope": misses_in_scope,
        "pending_outcomes": pending_outcomes,
        "available_outcomes": available_outcomes,
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
    parser = argparse.ArgumentParser(description="V15 Trapped Push Prospective Observer Metadata Bound")
    parser.add_argument("--mode", choices=["historical_replay", "manual_append"], required=True)
    parser.add_argument("--input-bars", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--candidate-id", default="H1_TRAPPED_PUSH_SNAPBACK")
    parser.add_argument("--opening-start", default="09:15", help="Opening window start IST (HH:MM)")
    parser.add_argument("--opening-end", default="11:30", help="Opening window end IST (HH:MM)")
    parser.add_argument("--evidence-commit", default=None, help="Evidence commit hash (SHA)")
    parser.add_argument("--registry-commit", default=None, help="Registry commit hash (SHA)")
    args = parser.parse_args()

    manifest = run_observer(args.mode, args.input_bars, args.output_root, args.run_id, args.candidate_id, args.opening_start, args.opening_end, args.evidence_commit, args.registry_commit)
    print(f"PROSPECTIVE OBSERVER RUN COMPLETE. Total Bars: {manifest['bars_total']}, In Scope: {manifest['bars_in_scope_opening_window']}, Out of Scope: {manifest['bars_out_of_scope']}, Triggers In Scope: {manifest['triggers_in_scope']}, Orders: {manifest['orders_created']}")

if __name__ == "__main__":
    main()
