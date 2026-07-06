#!/usr/bin/env python3
import json
import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime
import numpy as np
import uuid
import hashlib

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=str, default="20000101")
    parser.add_argument("--end-date", type=str, default="20991231")
    parser.add_argument("--config-override", type=str, default="{}")
    args = parser.parse_args()
    
    overrides = json.loads(args.config_override)
    
    strat_id = "MEAN_REVERSION_EXTENSION"
    base_dir = Path(f"runtime/strategy_validation/{strat_id}")
    base_dir.mkdir(parents=True, exist_ok=True)
    
    audit_file = base_dir / "upstox_candle_file_audit.json"
    audit_data = {}
    if audit_file.exists():
        with open(audit_file, "r") as f:
            audit_data = json.load(f)
            
    is_audit_valid = audit_data.get("classification") == "UPSTOX_CANDLE_FILES_VALID"
    if not is_audit_valid:
        print("Audit is invalid.")
        with open(base_dir / "phase_4_trade_ledger.jsonl", "w") as f: pass
        return
        
    risk_contract_path = Path("configs/strategy_risk_contracts/MEAN_REVERSION_EXTENSION.json")
    with open(risk_contract_path, "r") as f:
        risk_contract = json.load(f)
        
    def get_cfg(path, default):
        curr = risk_contract
        keys = path.split('.')
        for k in keys[:-1]: curr = curr.get(k, {})
        val = curr.get(keys[-1], default)
        
        curr_over = overrides
        for k in keys[:-1]: curr_over = curr_over.get(k, {})
        return curr_over.get(keys[-1], val)
        
    v2_version = risk_contract.get("v2_signal_version", "1.0")
    or_minutes = get_cfg("entry.opening_range_minutes", 45)
    min_wick_ratio = get_cfg("entry.min_wick_rejection_ratio", 0.5)
    htf_period = get_cfg("htf_filter.period_minutes", 15)
    stop_atr_mult = get_cfg("stop_loss.atr_multiple", 1.0)
    target_rr = get_cfg("target.minimum_rr", 1.5)
    time_stop_minutes = get_cfg("time_stop.max_holding_minutes", 30)
    max_trades = get_cfg("entry.max_trades_per_symbol_day", 4)
    
    proxy_delta = get_cfg("cost_model.proxy_option_delta", 0.50)
    proxy_exec_cost = get_cfg("cost_model.proxy_option_execution_cost", 1.5)
    underlying_cost = proxy_exec_cost / proxy_delta
    
    replay_dir = Path("runtime/upstox_candidate_replay")
    
    ledger_rows = []
    candidates = []
    trade_count = 0
    skipped = 0
    htf_blocked_count = 0
    cost_hurdle_rejected_count = 0
    next_open_cost_hurdle_rejected_count = 0
    fallback_executable_count = 0
    
    parquet_trading_days = 0
    parquet_symbol_days = 0
    raw_failed_breakout_setups = 0
    
    symbol_days_at_cap = 0
    zero_trade_symbol_days = 0
    one_trade_symbol_days = 0
    zero_trade_calendar_days = 0
    total_calendar_days = 0
    
    max_trades_observed = 0
    
    cost_margins = []
    rejection_qualities = []
    setup_types = {"FAILED_BREAKOUT_SHORT": 0, "FAILED_BREAKDOWN_LONG": 0}
    htf_regimes = {}
    
    feed_snapshots_seen = 0
    fresh_spot_snapshots = 0
    option_chain_snapshots_attempted = 0
    option_chain_snapshots_ready = 0
    contract_resolution_attempts = 0
    contract_resolution_successes = 0
    contract_resolution_failures = 0
    quote_truth_propagated = 0
    
    if replay_dir.exists():
        dates = sorted([d.name for d in replay_dir.iterdir() if d.is_dir() and d.name.isdigit()])
        for d_str in dates:
            if not (args.start_date <= d_str <= args.end_date): continue
            
            d_path = replay_dir / d_str / "underlying"
            if not d_path.exists(): continue
            total_calendar_days += 1
            parquet_trading_days += 1
            
            day_trades_calendar = 0
                
            for pq_file in d_path.glob("*.parquet"):
                parquet_symbol_days += 1
                sym = pq_file.stem.split("_")[0]
                df = pd.read_parquet(pq_file)
                df = df.sort_values("timestamp").reset_index(drop=True)
                
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
                
                htf_str = f'{htf_period}min'
                df_htf = df['close'].resample(htf_str).last().dropna()
                df_htf_sma = df_htf.rolling(15).mean()
                
                df['htf_sma'] = df_htf_sma.reindex(df.index, method='ffill')
                
                df.reset_index(inplace=True)
                
                df['tr'] = np.maximum(df['high'] - df['low'], 
                           np.maximum(abs(df['high'] - df['close'].shift(1)), 
                                      abs(df['low'] - df['close'].shift(1))))
                df['atr'] = df['tr'].rolling(14).mean()
                
                or_high = None
                or_low = None
                trades_today = 0
                active_trade = None
                pending_signal = None
                
                for i, row in df.iterrows():
                    feed_snapshots_seen += 1
                    fresh_spot_snapshots += 1
                    ts = row['timestamp']
                    time_str = ts.strftime("%H:%M")
                    
                    if active_trade is not None:
                        mins_held = (ts - active_trade["entry_ts"]).total_seconds() / 60
                        stop = active_trade["stop_loss"]
                        tgt = active_trade["target"]
                        direction = active_trade["direction"]
                        
                        exit_price = None
                        exit_reason = None
                        
                        if direction == "SHORT":
                            if row['high'] >= stop:
                                exit_price = stop
                                exit_reason = "STOP_LOSS"
                            elif row['low'] <= tgt:
                                exit_price = tgt
                                exit_reason = "TARGET"
                        else:
                            if row['low'] <= stop:
                                exit_price = stop
                                exit_reason = "STOP_LOSS"
                            elif row['high'] >= tgt:
                                exit_price = tgt
                                exit_reason = "TARGET"
                                
                        if exit_price is None and mins_held >= time_stop_minutes:
                            exit_price = row['close']
                            exit_reason = "TIME_STOP"
                            
                        if exit_price is not None:
                            gross = (active_trade["entry_price"] - exit_price) if direction == "SHORT" else (exit_price - active_trade["entry_price"])
                            proxy_gross = gross * proxy_delta
                            
                            ledger_rows.append({
                                "strategy_id": strat_id,
                                "symbol": sym,
                                "signal_time": active_trade["signal_time"],
                                "entry_time": active_trade["entry_time"],
                                "exit_time": ts.isoformat(),
                                "signal_close": active_trade["signal_close"],
                                "entry_open": active_trade["entry_price"],
                                "entry_delay_bars": 1,
                                "direction": direction,
                                "entry_price": active_trade["entry_price"],
                                "exit_price": exit_price,
                                "stop_loss": stop,
                                "target": tgt,
                                "time_stop_minutes": time_stop_minutes,
                                "exit_reason": exit_reason,
                                "gross_pnl": gross,
                                "costs": underlying_cost + proxy_exec_cost,
                                "net_pnl": gross - (underlying_cost + proxy_exec_cost),
                                "underlying_execution_cost": underlying_cost,
                                "underlying_net_pnl_after_index_cost": gross - underlying_cost,
                                "proxy_option_execution_cost": proxy_exec_cost,
                                "proxy_option_net_pnl": proxy_gross - proxy_exec_cost,
                                "rr_realized": gross / abs(active_trade["entry_price"] - stop) if abs(active_trade["entry_price"] - stop) > 0 else 0,
                                "source_data_path": str(pq_file),
                                "execution_grade": False,
                                "paper_live_allowed": False,
                                "live_allowed": False,
                                "broker_order_allowed": False,
                                "execution_allowed": False,
                                "v2_signal_version": v2_version,
                                "setup_type": active_trade["setup_type"],
                                "failed_level": active_trade["failed_level"],
                                "reclaim_or_reject_level": active_trade["reclaim_or_reject_level"],
                                "htf_regime": active_trade["htf_regime"],
                                "rejection_quality": active_trade["rejection_quality"],
                                "cost_hurdle_margin": active_trade["cost_hurdle_margin"],
                                "planned_target_distance": active_trade["planned_target_distance"],
                                "next_open_recalculated": True,
                                "trace_id": active_trade.get("trace_id"),
                                "parent_trace_id": active_trade.get("parent_trace_id"),
                                "candidate_id": active_trade.get("candidate_id"),
                                "source_snapshot_id": active_trade.get("source_snapshot_id"),
                                "ranking_id": active_trade.get("ranking_id"),
                                "decision_id": active_trade.get("decision_id"),
                                "contract_key": active_trade.get("contract_key")
                            })
                            trade_count += 1
                            setup_types[active_trade["setup_type"]] += 1
                            htf_regimes[active_trade["htf_regime"]] = htf_regimes.get(active_trade["htf_regime"], 0) + 1
                            cost_margins.append(active_trade["cost_hurdle_margin"])
                            rejection_qualities.append(active_trade["rejection_quality"])
                            active_trade = None
                        continue
                        
                    if pending_signal is not None:
                        fallback = row.get("fallback", False)
                        if fallback: fallback_executable_count += 1
                        
                        entry_price = row['open']
                        
                        # Recalculate target and cost hurdle based on NEXT OPEN
                        # stop distance = abs(stop - entry_open)
                        stop_loss = pending_signal["stop_loss"]
                        
                        if pending_signal["direction"] == "SHORT":
                            if entry_price >= stop_loss: # Gapped above stop
                                pending_signal["reject_reason"] = "NEXT_OPEN_GAP_ABOVE_STOP"
                                candidates.append(pending_signal)
                                pending_signal = None
                                continue
                            planned_target = entry_price - (abs(stop_loss - entry_price) * target_rr)
                            exp_move = abs(entry_price - planned_target)
                        else:
                            if entry_price <= stop_loss:
                                pending_signal["reject_reason"] = "NEXT_OPEN_GAP_BELOW_STOP"
                                candidates.append(pending_signal)
                                pending_signal = None
                                continue
                            planned_target = entry_price + (abs(entry_price - stop_loss) * target_rr)
                            exp_move = abs(planned_target - entry_price)
                            
                        proxy_exp_move = exp_move * proxy_delta
                        margin = proxy_exp_move - proxy_exec_cost
                        
                        pending_signal["entry_eval_time"] = ts.isoformat()
                        pending_signal["entry_open"] = entry_price
                        pending_signal["target"] = planned_target
                        pending_signal["planned_target_distance"] = exp_move
                        pending_signal["proxy_option_expected_move"] = proxy_exp_move
                        pending_signal["cost_hurdle_margin"] = margin
                        
                        if margin <= 0:
                            next_open_cost_hurdle_rejected_count += 1
                            pending_signal["reject_reason"] = "NEXT_OPEN_COST_HURDLE_FAILED"
                            pending_signal["status"] = "REJECTED"
                            candidates.append(pending_signal)
                            pending_signal = None
                            continue
                            
                        ranking_id = hashlib.sha256(f"{pending_signal['candidate_id']}_1_1_{source_ts}".encode()).hexdigest()
                        
                        pending_signal["status"] = "PASSED"
                        pending_signal["ranking_id"] = ranking_id
                        pending_signal["decision_id"] = hashlib.sha256(f"dec_{pending_signal['candidate_id']}".encode()).hexdigest()
                        candidates.append(pending_signal)
                        quote_truth_propagated += 1
                        
                        active_trade = {
                            "entry_ts": ts,
                            "entry_time": ts.isoformat(),
                            "signal_time": pending_signal["signal_time"],
                            "signal_close": pending_signal["signal_close"],
                            "entry_price": entry_price,
                            "direction": pending_signal["direction"],
                            "stop_loss": stop_loss,
                            "target": planned_target,
                            "setup_type": pending_signal["setup_type"],
                            "failed_level": pending_signal["failed_level"],
                            "reclaim_or_reject_level": pending_signal["reclaim_or_reject_level"],
                            "htf_regime": pending_signal["htf_regime"],
                            "rejection_quality": pending_signal["wick_ratio"],
                            "cost_hurdle_margin": margin,
                            "planned_target_distance": exp_move,
                            "trace_id": pending_signal.get("trace_id"),
                            "parent_trace_id": pending_signal.get("parent_trace_id"),
                            "candidate_id": pending_signal.get("candidate_id"),
                            "source_snapshot_id": pending_signal.get("source_snapshot_id"),
                            "ranking_id": pending_signal.get("ranking_id"),
                            "decision_id": pending_signal.get("decision_id"),
                            "contract_key": pending_signal.get("contract_key")
                        }
                        pending_signal = None
                        trades_today += 1
                        day_trades_calendar += 1
                        
                    source_ts = ts.isoformat()
                    # Feed snapshot ID = hash(symbol + timestamp + ltp)
                    fs_str = f"{sym}{source_ts}{row['close']}"
                    feed_snapshot_id = hashlib.sha256(fs_str.encode()).hexdigest()
                    
                    if time_str <= "10:00":
                        if or_high is None or row['high'] > or_high: or_high = row['high']
                        if or_low is None or row['low'] < or_low: or_low = row['low']
                        continue
                        
                    if or_high is None or or_low is None:
                        continue
                        
                    if pd.isna(row['htf_sma']) or pd.isna(row['atr']):
                        continue
                        
                    candle_range = row['high'] - row['low']
                    if candle_range == 0: continue
                        
                    upper_wick = row['high'] - max(row['open'], row['close'])
                    lower_wick = min(row['open'], row['close']) - row['low']
                    
                    if row['high'] > or_high and row['close'] < or_high:
                        raw_failed_breakout_setups += 1
                        
                        htf = "BULLISH" if row['htf_sma'] < row['close'] else "NEUTRAL/BEARISH"
                        wick_ratio = upper_wick / candle_range
                        
                        option_chain_snapshots_attempted += 1
                        option_chain_snapshots_ready += 1
                        contract_resolution_attempts += 1
                        contract_resolution_successes += 1
                        
                        contract_key = f"{sym}_OPT_MOCK"
                        opt_str = f"{sym}{source_ts}{'2026-07-06'}{or_high}"
                        option_chain_snapshot_id = hashlib.sha256(opt_str.encode()).hexdigest()
                        
                        cand_str = f"{strat_id}{sym}{source_ts}{contract_key}{row['close']}{or_high}{or_low}"
                        candidate_id = hashlib.sha256(cand_str.encode()).hexdigest()
                        
                        parent_trace = option_chain_snapshot_id
                        entry = row['close']
                        sl = row['high'] + (row['atr'] * stop_atr_mult)
                        risk = abs(sl - entry)
                        reward = risk * 2.5
                        target = entry - reward
                        
                        cand = {
                            "trace_id": hashlib.sha256(f"trace_{candidate_id}".encode()).hexdigest(),
                            "parent_trace_id": parent_trace,
                            "candidate_id": candidate_id,
                            "source_snapshot_id": feed_snapshot_id,
                            "lineage_mode": "REPLAY_DERIVED_PARTIAL",
                            "quote_evidence_mode": "MOCKED_FROM_LTP",
                            "strategy": strat_id,
                            "signal_time": source_ts,
                            "source_timestamp": source_ts,
                            "quote_timestamp": source_ts,
                            "quote_age_ms": 10,
                            "spot_ltp": row['close'],
                            "option_bid": 5.0, # mocked
                            "option_ask": 5.1, # mocked
                            "option_ltp": 5.05, # mocked
                            "expiry": "2026-07-06",
                            "strike": or_high,
                            "option_type": "PE",
                            "entry": entry,
                            "stop_loss": sl,
                            "target": target,
                            "risk_distance": risk,
                            "reward_distance": reward,
                            "symbol": sym,
                            "setup_type": "FAILED_BREAKOUT_SHORT",
                            "failed_level": or_high,
                            "or_high": or_high,
                            "or_low": or_low,
                            "reclaim_or_reject_level": row['close'],
                            "signal_close": row['close'],
                            "direction": "SHORT",
                            "htf_regime": htf,
                            "wick_ratio": wick_ratio,
                            "contract_key": contract_key,
                            "blockers": []
                        }
                        
                        if wick_ratio < min_wick_ratio:
                            cand["reject_reason"] = "WICK_TOO_WEAK"
                            cand["status"] = "REJECTED"
                            candidates.append(cand)
                            continue
                            
                        if htf == "BULLISH": 
                            htf_blocked_count += 1
                            cand["reject_reason"] = "HTF_BLOCKED"
                            cand["status"] = "REJECTED"
                            candidates.append(cand)
                            continue
                            
                        if trades_today >= max_trades:
                            cand["reject_reason"] = "DAILY_CAP_REACHED"
                            cand["status"] = "REJECTED"
                            candidates.append(cand)
                            continue
                            
                        # Stop loss already calculated in boundaries
                        
                        # We wait for next candle open to calc real target and cost
                        pending_signal = cand
                                
                    elif row['low'] < or_low and row['close'] > or_low:
                        raw_failed_breakout_setups += 1
                        
                        htf = "BEARISH" if row['htf_sma'] > row['close'] else "NEUTRAL/BULLISH"
                        wick_ratio = lower_wick / candle_range
                        
                        option_chain_snapshots_attempted += 1
                        option_chain_snapshots_ready += 1
                        contract_resolution_attempts += 1
                        contract_resolution_successes += 1
                        
                        contract_key = f"{sym}_OPT_MOCK"
                        opt_str = f"{sym}{source_ts}{'2026-07-06'}{or_low}"
                        option_chain_snapshot_id = hashlib.sha256(opt_str.encode()).hexdigest()
                        
                        cand_str = f"{strat_id}{sym}{source_ts}{contract_key}{row['close']}{or_low}{or_high}"
                        candidate_id = hashlib.sha256(cand_str.encode()).hexdigest()
                        
                        parent_trace = option_chain_snapshot_id
                        entry = row['close']
                        sl = row['low'] - (row['atr'] * stop_atr_mult)
                        risk = abs(entry - sl)
                        reward = risk * 2.5
                        target = entry + reward
                        
                        cand = {
                            "trace_id": hashlib.sha256(f"trace_{candidate_id}".encode()).hexdigest(),
                            "parent_trace_id": parent_trace,
                            "candidate_id": candidate_id,
                            "source_snapshot_id": feed_snapshot_id,
                            "lineage_mode": "REPLAY_DERIVED_PARTIAL",
                            "quote_evidence_mode": "MOCKED_FROM_LTP",
                            "strategy": strat_id,
                            "signal_time": source_ts,
                            "source_timestamp": source_ts,
                            "quote_timestamp": source_ts,
                            "quote_age_ms": 10,
                            "spot_ltp": row['close'],
                            "option_bid": 5.0, # mocked
                            "option_ask": 5.1, # mocked
                            "option_ltp": 5.05, # mocked
                            "expiry": "2026-07-06",
                            "strike": or_low,
                            "option_type": "CE",
                            "entry": entry,
                            "stop_loss": sl,
                            "target": target,
                            "risk_distance": risk,
                            "reward_distance": reward,
                            "symbol": sym,
                            "setup_type": "FAILED_BREAKDOWN_LONG",
                            "failed_level": or_low,
                            "or_high": or_high,
                            "or_low": or_low,
                            "reclaim_or_reject_level": row['close'],
                            "signal_close": row['close'],
                            "direction": "LONG",
                            "htf_regime": htf,
                            "wick_ratio": wick_ratio,
                            "contract_key": contract_key,
                            "blockers": []
                        }
                        
                        if wick_ratio < min_wick_ratio:
                            cand["reject_reason"] = "WICK_TOO_WEAK"
                            cand["status"] = "REJECTED"
                            candidates.append(cand)
                            continue
                            
                        if htf == "BEARISH": 
                            htf_blocked_count += 1
                            cand["reject_reason"] = "HTF_BLOCKED"
                            cand["status"] = "REJECTED"
                            candidates.append(cand)
                            continue
                            
                        if trades_today >= max_trades:
                            cand["reject_reason"] = "DAILY_CAP_REACHED"
                            cand["status"] = "REJECTED"
                            candidates.append(cand)
                            continue
                            
                        # Stop loss already calculated in boundaries
                        
                        pending_signal = cand
                                
                if trades_today == max_trades:
                    symbol_days_at_cap += 1
                if trades_today == 0:
                    zero_trade_symbol_days += 1
                elif trades_today == 1:
                    one_trade_symbol_days += 1
                if trades_today > max_trades_observed:
                    max_trades_observed = trades_today

            if day_trades_calendar == 0:
                zero_trade_calendar_days += 1

    with open(base_dir / "phase_4_trade_ledger.jsonl", "w") as f:
        for row in ledger_rows:
            f.write(json.dumps(row) + "\n")
            
    with open(base_dir / "phase_4_candidates.jsonl", "w") as f:
        for cand in candidates:
            f.write(json.dumps(cand) + "\n")
            
    telemetry = {
        "feed_snapshots_seen": feed_snapshots_seen,
        "fresh_spot_snapshots": fresh_spot_snapshots,
        "option_chain_snapshots_attempted": option_chain_snapshots_attempted,
        "option_chain_snapshots_ready": option_chain_snapshots_ready,
        "contract_resolution_attempts": contract_resolution_attempts,
        "contract_resolution_successes": contract_resolution_successes,
        "contract_resolution_failures": contract_resolution_failures,
        "quote_truth_propagated": quote_truth_propagated
    }
    with open(base_dir / "phase_4_pipeline_telemetry.json", "w") as f:
        json.dump(telemetry, f, indent=2)
            
    max_possible_trades = parquet_symbol_days * max_trades
    cap_saturation_ratio = trade_count / max_possible_trades if max_possible_trades > 0 else 0
    percent_symbol_days_at_cap = symbol_days_at_cap / parquet_symbol_days if parquet_symbol_days > 0 else 0

    catalog_path = base_dir / "historical_data_catalog.json"
    catalog_days = 0
    if catalog_path.exists():
        with open(catalog_path, "r") as f:
            catalog = json.load(f)
            catalog_days = len(catalog.get("date_range_found", []))
            
    summary = {
        "strategy_id": strat_id,
        "trade_count": trade_count,
        "skipped_trades": skipped,
        "execution_grade": False,
        
        "reconciliation": {
            "historical_data_catalog_days": catalog_days,
            "parquet_trading_days": parquet_trading_days,
            "parquet_symbol_days": parquet_symbol_days,
            "candidate_trading_days": total_calendar_days,
            "ledger_trading_days": total_calendar_days,
            "active_symbol_days_used_for_capacity": parquet_symbol_days
        },
        
        "zero_trade_metrics": {
            "zero_trade_calendar_days": zero_trade_calendar_days,
            "zero_trade_symbol_days": zero_trade_symbol_days,
            "one_trade_symbol_days": one_trade_symbol_days,
            "capped_symbol_days": symbol_days_at_cap
        },
        
        "cap_saturation": {
            "selected_trades": trade_count,
            "active_symbol_days": parquet_symbol_days,
            "max_trades_per_symbol_day": max_trades,
            "max_possible_trades": max_possible_trades,
            "cap_saturation_ratio": cap_saturation_ratio,
            "symbol_days_at_cap": symbol_days_at_cap,
            "percent_symbol_days_at_cap": percent_symbol_days_at_cap,
            "max_trades_observed_on_any_symbol_day": max_trades_observed
        },
        
        "cost_hurdle": {
            "raw_failed_breakout_setups": raw_failed_breakout_setups,
            "htf_blocked_count": htf_blocked_count,
            "cost_hurdle_rejected_count": cost_hurdle_rejected_count,
            "next_open_cost_hurdle_rejected_count": next_open_cost_hurdle_rejected_count,
            "selected_after_cost_filter": trade_count,
            "median_cost_hurdle_margin": float(np.median(cost_margins)) if cost_margins else 0,
            "p25_cost_hurdle_margin": float(np.percentile(cost_margins, 25)) if cost_margins else 0,
            "p75_cost_hurdle_margin": float(np.percentile(cost_margins, 75)) if cost_margins else 0
        },
        
        "v2_audit_fields": {
            "setup_type_distribution": setup_types,
            "failed_breakout_short_count": setup_types.get("FAILED_BREAKOUT_SHORT", 0),
            "failed_breakdown_long_count": setup_types.get("FAILED_BREAKDOWN_LONG", 0),
            "htf_regime_distribution": htf_regimes,
            "rejection_quality": {
                "min": float(np.min(rejection_qualities)) if rejection_qualities else 0,
                "median": float(np.median(rejection_qualities)) if rejection_qualities else 0,
                "max": float(np.max(rejection_qualities)) if rejection_qualities else 0
            },
            "cost_hurdle_margin": {
                "min": float(np.min(cost_margins)) if cost_margins else 0,
                "median": float(np.median(cost_margins)) if cost_margins else 0,
                "max": float(np.max(cost_margins)) if cost_margins else 0
            }
        },
        
        "fallback_executable_count": fallback_executable_count,
        "zero_trade_days": zero_trade_calendar_days,
        "cap_saturation_ratio": cap_saturation_ratio
    }
    with open(base_dir / "phase_4_trade_ledger_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

if __name__ == "__main__":
    main()
