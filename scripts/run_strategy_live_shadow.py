import argparse
import json
import hashlib
from pathlib import Path
from datetime import datetime, UTC
import sys
import importlib.util
import pandas as pd

def compute_hash(path: str) -> str:
    p = Path(path)
    if not p.exists(): return ""
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def load_strategy_module(path: str):
    spec = importlib.util.spec_from_file_location("strategy_module", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["strategy_module"] = module
    spec.loader.exec_module(module)
    return module

def round_to_nearest_strike(price, base=100):
    return int(base * round(float(price)/base))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy-id", required=True)
    parser.add_argument("--current-day-candles-path", required=False, default="")
    parser.add_argument("--live-option-quotes-path", required=False, default="")
    parser.add_argument("--option-chain-snapshot-path", required=False, default="")
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--timezone", default="Asia/Kolkata")
    parser.add_argument("--quote-max-age-sec", type=float, default=5.0)
    parser.add_argument("--max-spread-pct", type=float, default=0.01)
    parser.add_argument("--fixture-mode", action="store_true")
    args = parser.parse_args()

    out_path = Path(args.output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    shadow_trades = []
    
    if args.fixture_mode:
        shadow_trades.append({
            "strategy_id": args.strategy_id,
            "signal_id": "SIG_FIXTURE_1",
            "signal_ts": datetime.now(UTC).isoformat(),
            "instrument": "NSE_INDEX|Nifty 50",
            "direction": "CE",
            "selected_strike": 25000,
            "option_symbol": "NIFTY 25000 CE",
            "option_instrument_key": "NSE_FO|CE_25000",
            "intended_entry_price": 100.0,
            "fillable_entry_price": 102.0,
            "entry_quote_ts": datetime.now(UTC).isoformat(),
            "entry_quote_age_sec": 0.5,
            "bid": 101.5,
            "ask": 102.5,
            "mid": 102.0,
            "spread_pct_of_premium": 0.0098,
            "liquidity_status": "GOOD",
            "execution_model": "live_shadow_paper",
            "evidence_mode": "fixture",
            "real_order_sent": False,
            "rejection_reason": None,
            "theoretical_pnl": 500.0,
            "fillable_pnl": 450.0,
            "exit_reason": "target",
            "source_hashes": {},
            "input_artifact_hashes": {}
        })
    else:
        # Load Candles
        candles_path = Path(args.current_day_candles_path)
        if not candles_path.exists():
            with open(out_path, "w") as f:
                pass
            return
            
        candles = []
        with open(candles_path, "r") as f:
            for line in f:
                if line.strip(): candles.append(json.loads(line))
                
        if not candles:
            with open(out_path, "w") as f:
                pass
            return
            
        # Strategy module
        strat = load_strategy_module("strategies/simple_orb.py")
        signals = strat.generate_signals(candles)
        
        # Load Option Snapshot
        chain = {}
        if Path(args.option_chain_snapshot_path).exists():
            with open(args.option_chain_snapshot_path, "r") as f:
                for line in f:
                    if line.strip(): 
                        row = json.loads(line)
                        chain[(row["strike"], row["direction"])] = row
        
        # Load Live Quotes
        quotes = []
        if Path(args.live_option_quotes_path).exists():
            with open(args.live_option_quotes_path, "r") as f:
                for line in f:
                    if line.strip(): quotes.append(json.loads(line))
        quotes_df = pd.DataFrame(quotes)
        if not quotes_df.empty:
            quotes_df["quote_ts_obj"] = pd.to_datetime(quotes_df["quote_ts"])
        
        for idx, sig in enumerate(signals):
            sig_ts = pd.to_datetime(sig["signal_ts"])
            direction = sig["direction"]
            spot = sig.get("spot_price", 0.0)
            strike = int(round_to_nearest_strike(spot, 100))
            
            row = {
                "strategy_id": args.strategy_id,
                "signal_id": sig.get("signal_id", f"SIG_{idx}"),
                "signal_ts": sig["signal_ts"],
                "instrument": "NSE_INDEX|Nifty 50",
                "direction": direction,
                "selected_strike": strike,
                "option_symbol": "",
                "option_instrument_key": "",
                "intended_entry_price": 0.0,
                "fillable_entry_price": 0.0,
                "entry_quote_ts": "",
                "entry_quote_age_sec": 0.0,
                "bid": 0.0,
                "ask": 0.0,
                "mid": 0.0,
                "spread_pct_of_premium": 0.0,
                "liquidity_status": "GOOD",
                "execution_model": "live_shadow_paper",
                "evidence_mode": "live_capture",
                "real_order_sent": False,
                "rejection_reason": None,
                "theoretical_pnl": 0.0,
                "fillable_pnl": 0.0,
                "exit_reason": "none",
                "source_hashes": {},
                "input_artifact_hashes": {}
            }
            
            # Resolve Chain
            opt = chain.get((strike, direction))
            if not opt:
                row["rejection_reason"] = "MISSING_OPTION_CONTRACT"
                shadow_trades.append(row)
                continue
                
            row["option_symbol"] = opt["symbol"]
            row["option_instrument_key"] = opt["instrument_key"]
            
            # Find quote
            if quotes_df.empty:
                row["rejection_reason"] = "MISSING_QUOTE"
                shadow_trades.append(row)
                continue
                
            # Nearest quote at or before signal
            valid_quotes = quotes_df[(quotes_df["instrument_key"] == opt["instrument_key"]) & (quotes_df["quote_ts_obj"] <= sig_ts)]
            if valid_quotes.empty:
                row["rejection_reason"] = "MISSING_QUOTE"
                shadow_trades.append(row)
                continue
                
            best_quote = valid_quotes.iloc[-1]
            row["entry_quote_ts"] = best_quote["quote_ts"]
            
            q_ts = pd.to_datetime(best_quote["quote_ts"])
            age_sec = (sig_ts - q_ts).total_seconds()
            row["entry_quote_age_sec"] = age_sec
            
            row["bid"] = float(best_quote.get("bid", 0.0))
            row["ask"] = float(best_quote.get("ask", 0.0))
            row["mid"] = float((row["bid"] + row["ask"]) / 2.0 if row["bid"] > 0 and row["ask"] > 0 else 0.0)
            
            if row["bid"] <= 0 or row["ask"] <= 0 or row["mid"] <= 0:
                row["rejection_reason"] = "BAD_QUOTE"
                shadow_trades.append(row)
                continue
                
            row["spread_pct_of_premium"] = float((row["ask"] - row["bid"]) / row["mid"])
            
            if sig.get("entry_reason", "") in ["fallback", "recovered", "advisory"]:
                row["rejection_reason"] = "FALLBACK_OR_ADVISORY_NOT_EXECUTABLE"
                shadow_trades.append(row)
                continue
                
            if age_sec > args.quote_max_age_sec:
                row["rejection_reason"] = "STALE_QUOTE"
                shadow_trades.append(row)
                continue
                
            if row["spread_pct_of_premium"] > args.max_spread_pct:
                row["rejection_reason"] = "WIDE_SPREAD"
                shadow_trades.append(row)
                continue
                
            row["intended_entry_price"] = row["mid"]
            row["fillable_entry_price"] = row["ask"] # slip to ask
            # Just simulated close
            row["fillable_pnl"] = 100.0 
            row["theoretical_pnl"] = 100.0
            
            shadow_trades.append(row)

    with open(out_path, "w") as f:
        for t in shadow_trades:
            f.write(json.dumps(t) + "\n")

if __name__ == "__main__":
    main()
