#!/usr/bin/env python3
import json
import argparse
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
import sys
import os
from datetime import datetime

# Ensure we can import TradeBot modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from strategies.movement.vwap_reclaim import generate_vwap_reclaim_rejection_candidates
from core.movement_contract import has_hard_blocker

from unittest.mock import patch
from dataclasses import dataclass

@dataclass
class MockProfile:
    params: dict
    params_hash: str = "override"

def generate_ledger(
    start_date: str,
    end_date: str,
    config_override: str,
    aeron7_source_root: str,
    symbol_filter: str = "NIFTY",
    base_dir: str = "runtime/strategy_validation/VWAP_RECLAIM",
):
    overrides = {}
    if config_override:
        overrides = json.loads(config_override)

    def get_cfg(path, default):
        keys = path.split('.')
        d = overrides
        for k in keys:
            if isinstance(d, dict) and k in d:
                d = d[k]
            else:
                return default
        return d

    # Strategy-level parameter overrides
    min_vwap_dist = get_cfg("entry.min_vwap_distance_pct", 0.00035)
    max_vwap_dist = get_cfg("entry.max_vwap_entry_distance_pct", 0.0035)
    max_chop = get_cfg("entry.max_chop_score", 0.55)
    allow_bearish_reclaim = bool(get_cfg("entry.allow_bearish_reclaim", False))

    strategy_params = {
        "MIN_VWAP_DISTANCE_PCT": min_vwap_dist,
        "MAX_VWAP_ENTRY_DISTANCE_PCT": max_vwap_dist,
        "MAX_CHOP_SCORE": max_chop
    }
    strategy_flags = {
        "ALLOW_BEARISH_RECLAIM": allow_bearish_reclaim,
    }

    # Execution overrides
    stop_atr_mult = get_cfg("stop_loss.atr_multiple", 1.0)
    target_rr = get_cfg("target.minimum_rr", 2.0)
    pnl_model = get_cfg("backtest.pnl_model", "underlying_points")
    
    out_dir = Path(base_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = out_dir / "phase_4_trade_ledger.jsonl"
    candidates_path = out_dir / "phase_4_candidates.jsonl"
    
    total_trades = 0
    setup_types = {}
    
    active_symbol_days = 0
    symbol_days_at_cap = 0
    zero_trade_symbol_days = 0
    max_trades_per_day = 5
    
    def get_mock_profile(*args, **kwargs):
        params = dict(strategy_params)
        params.update(strategy_flags)
        return MockProfile(params=params)

    aeron7_root = Path(aeron7_source_root)
    if not aeron7_root.exists() or not list(aeron7_root.iterdir()):
        raise FileNotFoundError(f"Aeron7 data source missing or empty at {aeron7_source_root}. Real multi-year backtest is structurally required.")

    def _collect_source_dates(root: Path) -> tuple[str | None, str | None, set[str]]:
        month_map = {
            "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
            "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
        }
        dates: set[str] = set()
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".txt", ".csv"}:
                continue
            parts = path.relative_to(root).parts
            if len(parts) < 4:
                continue
            year = parts[0]
            month = parts[1]
            day_folder = parts[2]
            if not year or not month or not day_folder:
                continue
            if not (year.isdigit() and len(year) == 4):
                continue
            day = day_folder[:2]
            month_num = month_map.get(month[:3].upper())
            if month_num is None or not day.isdigit() or len(day) != 2:
                continue
            try:
                dates.add(datetime.strptime(f"{year}{month_num}{day}", "%Y%m%d").strftime("%Y%m%d"))
            except Exception:
                continue
        if not dates:
            return None, None, set()
        ordered = sorted(dates)
        return ordered[0], ordered[-1], dates

    source_min_date, source_max_date, source_dates = _collect_source_dates(aeron7_root)
    if source_dates and (end_date < source_min_date or start_date > source_max_date):
        raise ValueError(
            f"Requested date range {start_date}-{end_date} is outside Aeron7 coverage "
            f"{source_min_date}-{source_max_date} at {aeron7_source_root}."
        )

    aeron7_cache = Path(".runtime/aeron7_cache")
    symbol_filters = [s.strip() for s in symbol_filter.split(",")]
    aeron7_symbols = ["NIFTY_F1" if s == "NIFTY" else s for s in symbol_filters]
    
    from scripts.convert_aeron7_intraday import convert_aeron7_intraday
    convert_report = convert_aeron7_intraday(
        source_root=aeron7_root, 
        output_dir=aeron7_cache, 
        symbols=aeron7_symbols,
        start_date=start_date,
        end_date=end_date
    )
    written_files = convert_report.get("written_files", [])

    if not written_files:
        raise ValueError(
            f"No canonical CSV generated for {aeron7_symbols} in requested window "
            f"{start_date}-{end_date}. Aeron7 coverage is available only for "
            f"{source_min_date}-{source_max_date}."
        )

    df_list = [pd.read_csv(f) for f in written_files]
    df_all = pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()
    if df_all.empty:
        raise ValueError(f"Canonical CSVs are empty for {aeron7_symbols}. Missing Aeron7 coverage.")
        
    df_all['dt'] = pd.to_datetime(df_all['timestamp'])

    with open(ledger_path, 'w') as f_ledg, open(candidates_path, 'w') as f_cand:
        
        for (date_obj, sym), group in df_all.groupby([df_all['dt'].dt.date, 'symbol']):
            d_str = date_obj.strftime("%Y%m%d")
            if not (start_date <= d_str <= end_date): continue
            
            df = group.copy()
            df = df.sort_values("timestamp").reset_index(drop=True)
            if df.empty: continue
            
            mapped_symbol = "NIFTY" if sym == "NIFTY_F1" else sym
            if mapped_symbol not in symbol_filters: continue
            
            symbol = mapped_symbol
            candles = df.copy()
            
            candles['tr'] = np.maximum(candles['high'] - candles['low'], 
                                    np.maximum(abs(candles['high'] - candles['close'].shift(1)), 
                                                abs(candles['low'] - candles['close'].shift(1))))
            candles['atr'] = candles['tr'].rolling(14, min_periods=1).mean()
            
            cum_vol = candles['volume'].cumsum()
            cum_tp_vol = (candles['volume'] * (candles['high'] + candles['low'] + candles['close']) / 3.0).cumsum()
            candles['vwap'] = np.where(cum_vol > 0, cum_tp_vol / cum_vol, ((candles['high'] + candles['low'] + candles['close']) / 3.0).expanding().mean())
            candles['vwap_slope'] = candles['vwap'].diff(3) / 3.0
            
            active_symbol_days += 1
            daily_trades = 0
            pending_signal = None

            for idx, row in candles.iterrows():
                ts_str = row['dt'].isoformat()
                
                # 1. Execution of pending signals from previous candle
                if pending_signal is not None:
                    is_buy = pending_signal['direction'] == "BUY_CALL"
                    
                    entry_open = row['open']
                    atr = row['atr'] if not pd.isna(row['atr']) else 10.0
                    if atr == 0: atr = 10.0
                    
                    stop_loss = entry_open - (atr * stop_atr_mult) if is_buy else entry_open + (atr * stop_atr_mult)
                    target = entry_open + (atr * stop_atr_mult * target_rr) if is_buy else entry_open - (atr * stop_atr_mult * target_rr)
                    
                    planned_target_dist = abs(target - entry_open)
                    stop_dist = abs(entry_open - stop_loss)
                    cost_hurdle = planned_target_dist - stop_dist

                    cand_meta = {
                        "signal_time": pending_signal['generated_epoch'],
                        "entry_eval_time": ts_str,
                        "symbol": symbol_filter,
                        "setup_type": pending_signal['direction'],
                        "entry_open": entry_open,
                        "stop_loss": stop_loss,
                        "target": target,
                        "planned_target_distance": planned_target_dist,
                        "pnl_model": pnl_model,
                        "cost_hurdle_margin": cost_hurdle,
                        "reject_reason": "SELECTED"
                    }

                    if cost_hurdle <= 0:
                        cand_meta["reject_reason"] = "NEXT_OPEN_COST_HURDLE_FAILED"
                        f_cand.write(json.dumps(cand_meta) + "\n")
                        pending_signal = None
                        continue

                    if (is_buy and entry_open < stop_loss) or (not is_buy and entry_open > stop_loss):
                        cand_meta["reject_reason"] = "NEXT_OPEN_GAP_INVALID"
                        f_cand.write(json.dumps(cand_meta) + "\n")
                        pending_signal = None
                        continue
                        
                    f_cand.write(json.dumps(cand_meta) + "\n")
                    
                    win = False
                    for f_idx in range(idx, len(candles)):
                        f_row = candles.iloc[f_idx]
                        if is_buy:
                            if f_row['low'] <= stop_loss:
                                break # Stopped out
                            if f_row['high'] >= target:
                                win = True
                                break
                        else:
                            if f_row['high'] >= stop_loss:
                                break # Stopped out
                            if f_row['low'] <= target:
                                win = True
                                break
                    
                    if pnl_model == "underlying_points":
                        gross_pnl = planned_target_dist if win else -stop_dist
                        net_pnl = gross_pnl
                    else:
                        proxy_option_cost = 1.5
                        proxy_option_delta = 0.50
                        proxy_expected = planned_target_dist * proxy_option_delta
                        gross_pnl = proxy_expected if win else -stop_dist * proxy_option_delta
                        net_pnl = gross_pnl - proxy_option_cost
                    
                    trade_record = {
                        "trade_id": f"T-{symbol_filter}-{ts_str}",
                        "symbol": symbol_filter,
                        "setup_type": pending_signal['direction'],
                        "signal_time": cand_meta['signal_time'],
                        "entry_time": ts_str,
                        "entry_price": entry_open,
                        "stop_loss": stop_loss,
                        "target": target,
                        "gross_pnl": gross_pnl,
                        "net_pnl": net_pnl,
                        "proxy_option_net_pnl": net_pnl,
                        "pnl_model": pnl_model,
                        "evidence": pending_signal['evidence']
                    }
                    f_ledg.write(json.dumps(trade_record) + "\n")
                    
                    total_trades += 1
                    daily_trades += 1
                    setup_types[pending_signal['direction']] = setup_types.get(pending_signal['direction'], 0) + 1
                    pending_signal = None

                if daily_trades >= max_trades_per_day:
                    break

                # 2. Candidate Generation on candle close
                if idx > 0:
                    prev_row = candles.iloc[idx - 1]
                    
                    ctx = StrategyContext(
                        symbol=symbol_filter,
                        ts_epoch=row['dt'].timestamp(),
                        spot_ltp=row['close'],
                        open_price=candles.iloc[0]['open'],
                        vwap=row['vwap'],
                        vwap_slope=row['vwap_slope'],
                        atr=row['atr'],
                        metadata={"previous_spot_ltp": prev_row['close']}
                    )
                    
                    regime = MovementRegimeResult(
                        schema_version=1,
                        primary_regime="TREND_UP",
                        scores={"CHOP": 0.1, "TREND_UP": 0.8}
                    )
                    
                    with patch('strategies.movement.vwap_reclaim.get_default_profile', side_effect=get_mock_profile):
                        candidates = generate_vwap_reclaim_rejection_candidates(ctx, regime)
                    
                    if candidates:
                        filtered = [
                            c for c in candidates
                            if c.status == "VALIDATED_CANDIDATE"
                            and (c.direction != "BUY_PUT" or allow_bearish_reclaim)
                        ]
                        if not filtered:
                            continue
                        best_cand = max(filtered, key=lambda c: c.price_structure_score)
                        pending_signal = best_cand.to_dict()
                        pending_signal['generated_epoch'] = ts_str 

            if daily_trades == 0:
                zero_trade_symbol_days += 1
            if daily_trades >= max_trades_per_day:
                symbol_days_at_cap += 1

    max_possible_trades = active_symbol_days * max_trades_per_day
    cap_saturation = symbol_days_at_cap / active_symbol_days if active_symbol_days > 0 else 0
    percent_symbol_days_at_cap = symbol_days_at_cap / active_symbol_days if active_symbol_days > 0 else 0
    zero_trade_symbol_days_ratio = zero_trade_symbol_days / active_symbol_days if active_symbol_days > 0 else 0
    selected_symbol_days = active_symbol_days - zero_trade_symbol_days

    summary = {
        "metrics": {
            "total_trades": total_trades,
            "buy_call_count": setup_types.get("BUY_CALL", 0),
            "buy_put_count": setup_types.get("BUY_PUT", 0),
            "active_symbol_days": active_symbol_days,
            "max_possible_trades": max_possible_trades,
            "cap_saturation_ratio": cap_saturation,
            "symbol_days_at_cap": symbol_days_at_cap,
            "zero_trade_symbol_days": zero_trade_symbol_days,
            "max_trades_per_symbol_day": max_trades_per_day,
            "selected_symbol_days": selected_symbol_days,
            "percent_symbol_days_at_cap": percent_symbol_days_at_cap,
            "zero_trade_symbol_days_ratio": zero_trade_symbol_days_ratio
        },
        "provenance": {
            "aeron7_source_root": str(aeron7_source_root),
            "requested_start_date": start_date,
            "requested_end_date": end_date,
            "actual_symbols_converted": convert_report.get("symbols", []),
            "total_rows_converted": sum(len(df) for df in df_list) if df_list else 0,
            "cache_hit": convert_report.get("cache_hit", False),
            "cache_dir": convert_report.get("output_dir", "")
        }
    }
    with open(out_dir / "phase_4_trade_ledger_summary.json", 'w') as f:
        json.dump(summary, f, indent=2)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--config-override", default="{}")
    parser.add_argument("--aeron7-source-root", default="data/aeron7_data", help="Root of Aeron7 dataset")
    parser.add_argument("--base-dir", default="runtime/strategy_validation/VWAP_RECLAIM", help="Output directory for Phase 4 artifacts")
    args = parser.parse_args()
    
    s_date = args.start_date.replace("-", "")
    e_date = args.end_date.replace("-", "")
    generate_ledger(s_date, e_date, args.config_override, args.aeron7_source_root, base_dir=args.base_dir)
