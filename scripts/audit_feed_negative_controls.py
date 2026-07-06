#!/usr/bin/env python3
import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from copy import deepcopy

# Mock all broker modules BEFORE importing core
class MockKiteClient:
    def __init__(self, *args, **kwargs):
        pass
    def quotes(self, *args, **kwargs):
        return {}

sys.modules["core.kite_client"] = type("MockModule", (), {"KiteAPIClient": MockKiteClient, "KITE_USE_API": False, "kite_client": MockKiteClient()})
sys.modules["core.kite_depth_ws"] = type("MockModule", (), {"KiteDepthWS": MockKiteClient})

from config import config as cfg
import core.market_data as market_data
from core.depth_store import depth_store
from core.time_utils import now_ist
from strategies.trade_builder import TradeBuilder

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger("audit_feed_negative_controls")

ROOT = Path(__file__).resolve().parents[1]

# Disable Kite API and set required mocks
cfg.KITE_USE_API = False
cfg.EXECUTION_MODE = "LIVE"
cfg.REQUIRE_LIVE_QUOTES = True
cfg.SYMBOLS = ["NIFTY"]

class DummyRegimeModel:
    def predict(self, _features):
        return {"primary_regime": "TREND"}

market_data._REGIME_MODEL = DummyRegimeModel()

def load_replay_data():
    data_path = ROOT / "data" / "active_options_replay.json"
    if not data_path.exists():
        return []
    with open(data_path, "r") as f:
        return json.load(f)

def run_scenario(scenario_name, ticks):
    stats = {
        "scenario": scenario_name,
        "total_input_events": 0,
        "quotes_classified": 0,
        "REAL_BID_ASK": 0,
        "REAL_LTP_ONLY": 0,
        "MOCKED_FROM_LTP": 0,
        "STALE_QUOTE": 0,
        "MISSING_QUOTE": 0,
        "execution_feed_ready_true": 0,
        "execution_feed_ready_false": 0,
        "blocked_candidates": 0,
        "executable_candidates": 0,
        "executable_fallback_violations": 0,
        "expected_degradation_observed": True
    }

    builder = TradeBuilder()
    market_data._DATA_CACHE.clear()
    depth_store.__init__()

    if not ticks:
        return stats

    base_time = datetime.fromisoformat(ticks[0]["timestamp"])
    original_now = market_data.now_ist

    for i, tick_raw in enumerate(ticks):
        tick = deepcopy(tick_raw)
        tick["NIFTY"] = 25000.0
        stats["total_input_events"] += 1
        
        current_time = datetime.fromisoformat(tick.get("timestamp"))

        # Apply mutations
        if scenario_name == "shift_timestamps":
            current_time += timedelta(seconds=120)  # advance time so ticks look stale
            
        market_data.now_ist = lambda: current_time
        market_data.now_utc_epoch = lambda: current_time.timestamp()

        if scenario_name == "shuffle_events" and i % 2 == 1 and i > 0:
            # Swap timestamps to violate monotonicity
            tick["timestamp"] = ticks[i-1]["timestamp"]
        tick["NIFTY"] = 25000.0

        # Parse cross asset and populate caches
        for symbol, price in tick.items():
            if symbol == "timestamp": continue
            if scenario_name == "remove_option_symbols" and "OPT" in symbol:
                continue
            
            # Construct a mock depth tick
            depth_tick = {
                "instrument_token": hash(symbol),
                "last_price": price,
                "timestamp": current_time,
                "depth": {
                    "buy": [{"price": price - 1, "quantity": 100}],
                    "sell": [{"price": price + 1, "quantity": 100}]
                }
            }

            if scenario_name == "drop_bid_ask":
                depth_tick["depth"]["buy"] = []
                depth_tick["depth"]["sell"] = []
            elif scenario_name == "inject_crossed_market":
                depth_tick["depth"]["buy"] = [{"price": price + 10, "quantity": 100}]
                depth_tick["depth"]["sell"] = [{"price": price - 10, "quantity": 100}]

            market_data._DATA_CACHE[symbol] = {
                "ltp": price,
                "ltp_source": "live",
                "ltp_ts_epoch": current_time.timestamp(),
                "ohlc": {"close": price}
            }
            depth_store.update(hash(symbol), depth_tick["depth"])

        if scenario_name == "simulate_connected_no_ticks":
            # Clear caches to simulate no ticks flowing
            market_data._DATA_CACHE.clear()
            depth_store.__init__()
            
        try:
            # fetch_live_market_data computes quote truth and feed supervisor states
            market_data.fetch_option_chain = lambda *args, **kwargs: ["NIFTY25JUL15000CE"]
            snapshots = market_data.fetch_live_market_data()
            
            for snap in snapshots:
                stats["quotes_classified"] += 1
                qt = snap.get("quote_truth", {})
                cat = qt.get("category", "")
                
                if cat == "REAL_BID_ASK": stats["REAL_BID_ASK"] += 1
                elif cat == "REAL_LTP_ONLY": stats["REAL_LTP_ONLY"] += 1
                elif cat == "MOCKED_FROM_LTP": stats["MOCKED_FROM_LTP"] += 1
                elif cat == "STALE_QUOTE": stats["STALE_QUOTE"] += 1
                elif cat == "MISSING_QUOTE": stats["MISSING_QUOTE"] += 1

                fs = snap.get("feed_health", {})
                if fs.get("execution_feed_ready", False):
                    stats["execution_feed_ready_true"] += 1
                else:
                    stats["execution_feed_ready_false"] += 1

                if snap.get("instrument") == "OPT":
                    cand = builder.build(snap, quick_mode=True)
                    if cand:
                        if getattr(cand, "candidate_class", "") == "BLOCKED":
                            stats["blocked_candidates"] += 1
                        else:
                            stats["executable_candidates"] += 1

                        if getattr(cand, "is_executable_quote", False) and cat in ["MOCKED_FROM_LTP", "STALE_QUOTE", "MISSING_QUOTE"]:
                            stats["executable_fallback_violations"] += 1
                    else:
                        stats["blocked_candidates"] += 1
        except Exception as e:
            import traceback
            traceback.print_exc()
            pass

    market_data.now_ist = original_now
    return stats

def main():
    ticks = load_replay_data()
    ticks = ticks[:100] if len(ticks) > 100 else ticks

    scenarios = [
        "baseline",
        "drop_bid_ask",
        "shift_timestamps",
        "shuffle_events",
        "inject_crossed_market",
        "remove_option_symbols",
        "simulate_connected_no_ticks"
    ]

    results = []
    for sc in scenarios:
        res = run_scenario(sc, ticks)
        # Verify degradation heuristics
        if sc == "drop_bid_ask" and res["REAL_BID_ASK"] > 0:
            res["expected_degradation_observed"] = False
        if sc == "shift_timestamps" and res["STALE_QUOTE"] == 0:
            res["expected_degradation_observed"] = False
        if sc == "inject_crossed_market" and res["REAL_BID_ASK"] > 0:
            res["expected_degradation_observed"] = False
        if sc == "simulate_connected_no_ticks" and res["execution_feed_ready_true"] > 0:
            res["expected_degradation_observed"] = False
        results.append(res)

    headers = list(results[0].keys())
    print("| " + " | ".join(headers) + " |")
    print("| " + " | ".join(["---"] * len(headers)) + " |")
    for r in results:
        print("| " + " | ".join(str(r[h]) for h in headers) + " |")

if __name__ == "__main__":
    main()
